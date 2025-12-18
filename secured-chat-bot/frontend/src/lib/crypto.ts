/**
 * Crypto module for ECDH + AES-GCM.
 * 
 * Supports both P-384 (Odyn standard) and secp256k1 (ETH signing key) for encryption.
 * Automatically detects the curve from the enclave's public key.
 */

import * as secp256k1 from '@noble/secp256k1';
import { hkdf } from '@noble/hashes/hkdf.js';
import { sha256 } from '@noble/hashes/sha2.js';

export interface EncryptedPayload {
    nonce: string;     // hex-encoded bytes
    public_key: string; // hex-encoded DER public key
    data: string;      // hex-encoded encrypted data
}

export interface AttestationDoc {
    attestation_doc: string;  // Base64-encoded CBOR attestation
    public_key: string;       // hex-encoded DER public key
}

export interface ChatResponse {
    platform: string;
    ai_model: string;
    timestamp: number;
    message: string;
    response: string;
}

// Convert ArrayBuffer to hex string
function bufferToHex(buffer: ArrayBuffer | Uint8Array): string {
    const arr = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
    return Array.from(arr)
        .map(b => b.toString(16).padStart(2, '0'))
        .join('');
}

// Convert hex string to Uint8Array
function hexToBytes(hex: string): Uint8Array {
    if (hex.startsWith('0x')) hex = hex.slice(2);
    const bytes = new Uint8Array(hex.length / 2);
    for (let i = 0; i < hex.length; i += 2) {
        bytes[i / 2] = parseInt(hex.substr(i, 2), 16);
    }
    return bytes;
}

// Curve types
type CurveType = 'P-384' | 'secp256k1';

// DER SPKI OIDs
const OID_SEC_P384 = '2b81040022';
const OID_SECP256K1 = '2b8104000a';

function detectCurve(derKeyHex: string): CurveType {
    if (derKeyHex.includes(OID_SEC_P384) || derKeyHex.length === 240) {
        return 'P-384';
    }
    if (derKeyHex.includes(OID_SECP256K1) || derKeyHex.length === 176) {
        return 'secp256k1';
    }
    // Fallback based on length if OID not found
    if (derKeyHex.length > 200) return 'P-384';
    return 'secp256k1';
}

/**
 * Utility to convert DER to raw point.
 * P-384 DER (SPKI) -> 97 bytes raw point
 * secp256k1 DER (SPKI) -> 65 bytes raw point
 */
function derToRaw(derKey: Uint8Array, curve: CurveType): Uint8Array {
    if (curve === 'P-384' && derKey.length === 120) {
        return derKey.slice(23);
    }
    if (curve === 'secp256k1' && derKey.length === 88) {
        return derKey.slice(23);
    }
    return derKey;
}

/**
 * Utility to convert raw point back to DER SPKI.
 */
function rawToDer(rawKey: Uint8Array, curve: CurveType): Uint8Array {
    if (curve === 'P-384') {
        const header = hexToBytes('3076301006072a8648ce3d020106082b81040022036200');
        const der = new Uint8Array(header.length + rawKey.length);
        der.set(header, 0);
        der.set(rawKey, header.length);
        return der;
    } else {
        const header = hexToBytes('3056301006072a8648ce3d020106052b8104000a034200');
        const der = new Uint8Array(header.length + rawKey.length);
        der.set(header, 0);
        der.set(rawKey, header.length);
        return der;
    }
}

export class EnclaveClient {
    private enclaveBaseUrl: string = '';
    private isConnected: boolean = false;
    private curve: CurveType = 'P-384';

    // Keys for WebCrypto (P-384)
    private p384KeyPair: CryptoKeyPair | null = null;
    private serverP384Key: CryptoKey | null = null;

    // Keys for secp256k1
    private secpPrivKey: Uint8Array | null = null;
    private secpPubKey: Uint8Array | null = null;
    private serverSecpPubKeyRaw: Uint8Array | null = null;

    async connect(baseUrl: string): Promise<AttestationDoc> {
        this.enclaveBaseUrl = baseUrl.replace(/\/$/, '');

        // Fetch attestation first to determine the curve
        const attestation = await this.fetchAttestation();
        this.curve = detectCurve(attestation.public_key);

        console.log(`Detected enclave curve: ${this.curve}`);

        if (this.curve === 'P-384') {
            this.p384KeyPair = await crypto.subtle.generateKey(
                { name: 'ECDH', namedCurve: 'P-384' },
                true,
                ['deriveBits']
            );

            const serverPubKeyDer = hexToBytes(attestation.public_key);
            const serverPubKeyRaw = derToRaw(serverPubKeyDer, 'P-384');

            this.serverP384Key = await crypto.subtle.importKey(
                'raw',
                serverPubKeyRaw,
                { name: 'ECDH', namedCurve: 'P-384' },
                true,
                []
            );
        } else {
            this.secpPrivKey = secp256k1.utils.randomSecretKey();
            this.secpPubKey = secp256k1.getPublicKey(this.secpPrivKey, false); // uncompressed

            const serverPubKeyDer = hexToBytes(attestation.public_key);
            this.serverSecpPubKeyRaw = derToRaw(serverPubKeyDer, 'secp256k1');

            // Validate it
            secp256k1.Point.fromHex(this.serverSecpPubKeyRaw);
        }

        this.isConnected = true;
        return attestation;
    }

    async fetchAttestation(): Promise<AttestationDoc & { parsedAttestation?: string }> {
        const response = await fetch(`${this.enclaveBaseUrl}/.well-known/attestation`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        if (!response.ok) {
            throw new Error(`Failed to fetch attestation: ${response.status}`);
        }

        const contentType = response.headers.get('content-type') || '';

        if (contentType.includes('application/cbor') || contentType.includes('application/octet-stream')) {
            const cbor = await import('cbor-web');
            const arrayBuffer = await response.arrayBuffer();
            const cborData = cbor.decode(new Uint8Array(arrayBuffer));
            return this.parseCborAttestation(cborData);
        } else {
            const jsonData = await response.json();
            if (jsonData.attestation_document) {
                return {
                    attestation_doc: JSON.stringify(jsonData),
                    public_key: jsonData.attestation_document.public_key || '',
                    parsedAttestation: JSON.stringify(jsonData),
                };
            }
            if (jsonData.attestation_doc) {
                const cbor = await import('cbor-web');
                const binary = atob(jsonData.attestation_doc);
                const bytes = new Uint8Array(binary.length);
                for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
                const cborData = cbor.decode(bytes);
                const parsed = await this.parseCborAttestation(cborData);
                return { ...parsed, attestation_doc: jsonData.attestation_doc };
            }
            return jsonData;
        }
    }

    private async parseCborAttestation(cborData: any): Promise<AttestationDoc & { parsedAttestation?: string }> {
        const cbor = await import('cbor-web');
        const bytesToHex = (bytes: Uint8Array | ArrayBuffer): string => {
            const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
            return bufferToHex(arr);
        };

        const payload = Array.isArray(cborData) ? cborData[2] : cborData;
        const signature = Array.isArray(cborData) && cborData.length > 3 ? cborData[3] : null;
        const doc = cbor.decode(payload);

        const getField = (d: any, name: string, id: number) => {
            if (d instanceof Map) return d.get(name) ?? d.get(id);
            return d[name] ?? d[id];
        };

        const publicKeyRaw = getField(doc, 'public_key', 7);
        const publicKey = publicKeyRaw ? bytesToHex(publicKeyRaw) : '';
        const userDataRaw = getField(doc, 'user_data', 8);
        const moduleId = getField(doc, 'module_id', 1);
        const timestamp = getField(doc, 'timestamp', 2);
        const pcrsRaw = getField(doc, 'pcrs', 4);

        const pcrs: any = {};
        if (pcrsRaw) {
            const entries = pcrsRaw instanceof Map ? Array.from(pcrsRaw.entries()) : Object.entries(pcrsRaw);
            for (const [k, v] of entries) {
                pcrs[String(k)] = (v instanceof Uint8Array) ? bytesToHex(v) : String(v);
            }
        }

        let userData = null;
        if (userDataRaw) {
            try {
                const decoder = new TextDecoder();
                userData = JSON.parse(decoder.decode(new Uint8Array(userDataRaw)));
            } catch (e) { }
        }

        const parsedResult = {
            attestation_document: {
                module_id: String(moduleId || ''),
                timestamp: Number(timestamp || 0),
                public_key: publicKey,
                user_data: userData,
                pcrs: pcrs
            },
            signature: signature ? bytesToHex(signature) : null
        };

        return {
            attestation_doc: JSON.stringify(parsedResult),
            public_key: publicKey,
            parsedAttestation: JSON.stringify(parsedResult),
        };
    }

    private async deriveSharedKey(peerPublicKeyDer: string): Promise<CryptoKey> {
        const peerKeyBytes = hexToBytes(peerPublicKeyDer);
        const peerRaw = derToRaw(peerKeyBytes, this.curve);

        let sharedSecret: ArrayBuffer;

        if (this.curve === 'P-384') {
            if (!this.p384KeyPair) throw new Error('P-384 keys not initialized');
            const peerKey = await crypto.subtle.importKey(
                'raw', peerRaw, { name: 'ECDH', namedCurve: 'P-384' }, true, []
            );
            sharedSecret = await crypto.subtle.deriveBits(
                { name: 'ECDH', public: peerKey }, this.p384KeyPair.privateKey, 384
            );
        } else {
            if (!this.secpPrivKey) throw new Error('secp256k1 keys not initialized');
            const fullSecret = secp256k1.getSharedSecret(this.secpPrivKey, peerRaw);
            sharedSecret = fullSecret.slice(1, 33).buffer; // Use x-coordinate
        }

        const hkdfKey = await crypto.subtle.importKey(
            'raw', sharedSecret, { name: 'HKDF' }, false, ['deriveKey']
        );

        return crypto.subtle.deriveKey(
            {
                name: 'HKDF',
                hash: 'SHA-256',
                salt: new Uint8Array(0),
                info: new TextEncoder().encode('encryption data')
            },
            hkdfKey,
            { name: 'AES-GCM', length: 256 },
            false,
            ['encrypt', 'decrypt']
        );
    }

    async encrypt(plaintext: string): Promise<EncryptedPayload> {
        if (!this.isConnected) throw new Error('Not connected');

        // Use server key from connection initialization for the first encryption
        // Actually, we usually encrypt for the server's public key we got from attestation
        // In the first request (set-api-key), we use this.serverP384Key or similar.

        // However, deriveSharedKey expects a DER string.
        // Let's get the server key we stored or the one from attestation.
        const attestation = await this.fetchAttestation();
        const aesKey = await this.deriveSharedKey(attestation.public_key);

        const nonce = crypto.getRandomValues(new Uint8Array(32));
        const ciphertext = await crypto.subtle.encrypt(
            { name: 'AES-GCM', iv: nonce },
            aesKey,
            new TextEncoder().encode(plaintext)
        );

        let myPubKeyDer: Uint8Array;
        if (this.curve === 'P-384') {
            const raw = await crypto.subtle.exportKey('raw', this.p384KeyPair!.publicKey);
            myPubKeyDer = rawToDer(new Uint8Array(raw), 'P-384');
        } else {
            myPubKeyDer = rawToDer(this.secpPubKey!, 'secp256k1');
        }

        return {
            nonce: bufferToHex(nonce),
            public_key: bufferToHex(myPubKeyDer),
            data: bufferToHex(ciphertext)
        };
    }

    async decrypt(payload: { nonce: string; public_key: string; encrypted_data: string }): Promise<string> {
        if (!this.isConnected) throw new Error('Not connected');

        const aesKey = await this.deriveSharedKey(payload.public_key);

        // IMPORTANT: Odyn returns 32-byte nonces, but standard AES-GCM (WebCrypto) 
        // expects 12-byte IVs. We use the first 12 bytes.
        const nonceBytes = hexToBytes(payload.nonce).slice(0, 12);

        const plaintext = await crypto.subtle.decrypt(
            { name: 'AES-GCM', iv: nonceBytes },
            aesKey,
            hexToBytes(payload.encrypted_data)
        );

        return new TextDecoder().decode(plaintext);
    }

    async setApiKey(apiKey: string, platform: string = 'openai'): Promise<any> {
        const payload = JSON.stringify({ api_key: apiKey, platform });
        const encrypted = await this.encrypt(payload);
        const response = await fetch(`${this.enclaveBaseUrl}/set-api-key`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(encrypted)
        });
        if (!response.ok) throw new Error('Failed to set API key');
        const result = await response.json();
        const decrypted = await this.decrypt(result.data);
        return JSON.parse(decrypted);
    }

    async chat(message: string, model: string = 'gpt-4'): Promise<any> {
        const payload = JSON.stringify({ message, ai_model: model });
        const encrypted = await this.encrypt(payload);
        const response = await fetch(`${this.enclaveBaseUrl}/talk`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(encrypted)
        });
        if (!response.ok) throw new Error('Chat failed');
        const result = await response.json();
        const decrypted = await this.decrypt(result.data);
        const parsed = JSON.parse(decrypted);

        const attestation = await this.fetchAttestation();
        const health = await this.checkHealth();

        return {
            ...parsed,
            signature: result.sig,
            verificationData: {
                attestation: attestation.attestation_doc,
                publicKey: attestation.public_key,
                ethAddr: health.enclave_address,
                encryptedRequest: JSON.stringify(encrypted),
                decryptedRequest: payload,
                rawResponse: JSON.stringify(result),
                encryptedResponse: JSON.stringify(result.data),
                decryptedResponse: decrypted,
            },
        };
    }

    async checkHealth(): Promise<any> {
        const response = await fetch(`${this.enclaveBaseUrl}/`);
        return response.json();
    }
}

export const enclaveClient = new EnclaveClient();
