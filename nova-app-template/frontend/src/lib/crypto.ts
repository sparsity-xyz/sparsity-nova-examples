/**
 * RA-TLS Crypto Client
 * 
 * Provides ECDH + AES-GCM encrypted communication with Nova TEE enclave.
 * Supports both P-384 (Odyn standard) and secp256k1 curves.
 */

import * as secp256k1 from '@noble/secp256k1';
import { fetchAttestation, hexToBytes } from './attestation';

export interface EncryptedPayload {
    nonce: string;      // hex-encoded 32 bytes
    public_key: string; // hex-encoded DER public key
    data: string;       // hex-encoded encrypted data
}

export interface AttestationDoc {
    attestation_doc: string;  // Base64-encoded CBOR attestation
    public_key: string;       // hex-encoded DER public key
}

// Convert ArrayBuffer to hex string
function bufferToHex(buffer: ArrayBuffer | Uint8Array): string {
    const arr = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
    return Array.from(arr)
        .map(b => b.toString(16).padStart(2, '0'))
        .join('');
}

// Curve types
type CurveType = 'P-384' | 'secp256k1';

// DER SPKI OIDs
const OID_SEC_P384 = '2b81040022';
const OID_SECP256K1 = '2b8104000a';

function detectCurve(keyHex: string): CurveType {
    if (keyHex.includes(OID_SEC_P384)) return 'P-384';
    if (keyHex.includes(OID_SECP256K1)) return 'secp256k1';

    const len = keyHex.length;
    if (len === 240 || len === 194) return 'P-384';
    if (len === 176 || len === 130) return 'secp256k1';
    if (len > 160) return 'P-384';
    return 'secp256k1';
}

/**
 * Convert DER to raw point format.
 */
function derToRaw(derKey: Uint8Array, curve: CurveType): Uint8Array {
    if (curve === 'P-384') {
        if (derKey.length === 120) return derKey.slice(23);
        if (derKey.length === 97) return derKey;
    }
    if (curve === 'secp256k1') {
        if (derKey.length === 88) return derKey.slice(23);
        if (derKey.length === 65) return derKey;
    }
    console.warn(`[derToRaw] Unexpected key length ${derKey.length} for curve ${curve}`);
    return derKey;
}

/**
 * Convert raw point to DER SPKI format.
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

/**
 * EnclaveClient - RA-TLS client for secure communication with Nova TEE
 * 
 * Usage:
 *   const client = new EnclaveClient();
 *   await client.connect('https://your-app.app.sparsity.cloud');
 *   const response = await client.callEncrypted('/api/echo', { message: 'Hello' });
 */
export class EnclaveClient {
    private enclaveBaseUrl: string = '';
    private isConnected: boolean = false;
    private curve: CurveType = 'P-384';

    // P-384 keys (WebCrypto)
    private p384KeyPair: CryptoKeyPair | null = null;
    private serverP384Key: CryptoKey | null = null;

    // secp256k1 keys
    private secpPrivKey: Uint8Array | null = null;
    private secpPubKey: Uint8Array | null = null;
    private serverSecpPubKeyRaw: Uint8Array | null = null;

    get baseUrl() {
        return this.enclaveBaseUrl;
    }

    get connected() {
        return this.isConnected;
    }

    /**
     * Connect to enclave and establish ECDH key exchange.
     * Fetches attestation and generates ephemeral key pair.
     */
    async connect(baseUrl: string): Promise<AttestationDoc> {
        this.enclaveBaseUrl = baseUrl.replace(/\/$/, '');

        const attestation = await this.fetchAttestation();
        this.curve = detectCurve(attestation.public_key);

        console.log(`[EnclaveClient] Detected curve: ${this.curve}`);

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
                serverPubKeyRaw as any,
                { name: 'ECDH', namedCurve: 'P-384' },
                true,
                []
            );
        } else {
            this.secpPrivKey = secp256k1.utils.randomSecretKey();
            this.secpPubKey = secp256k1.getPublicKey(this.secpPrivKey, false);

            const serverPubKeyDer = hexToBytes(attestation.public_key);
            this.serverSecpPubKeyRaw = derToRaw(serverPubKeyDer, 'secp256k1');

            try {
                const rawHex = Array.from(this.serverSecpPubKeyRaw).map(b => b.toString(16).padStart(2, '0')).join('');
                secp256k1.Point.fromHex(rawHex);
            } catch (e) {
                throw new Error(`Invalid server public key: ${e instanceof Error ? e.message : String(e)}`);
            }
        }

        this.isConnected = true;
        return attestation;
    }

    /**
     * Fetch attestation document from enclave.
     */
    async fetchAttestation(): Promise<AttestationDoc & { parsedAttestation?: string }> {
        const result = await fetchAttestation(this.enclaveBaseUrl);
        const publicKey = result.attestation_document.public_key || '';

        return {
            attestation_doc: result.raw_doc,
            public_key: publicKey,
            parsedAttestation: JSON.stringify(result)
        };
    }

    /**
     * Derive shared AES-256 key from ECDH.
     */
    private async deriveSharedKey(peerPublicKeyDer: string): Promise<CryptoKey> {
        const peerKeyBytes = hexToBytes(peerPublicKeyDer);
        const peerRaw = derToRaw(peerKeyBytes, this.curve);

        let sharedSecret: ArrayBuffer;

        if (this.curve === 'P-384') {
            if (!this.p384KeyPair) throw new Error('P-384 keys not initialized');
            const peerKey = await crypto.subtle.importKey(
                'raw', peerRaw as any, { name: 'ECDH', namedCurve: 'P-384' }, true, []
            );
            sharedSecret = await crypto.subtle.deriveBits(
                { name: 'ECDH', public: peerKey }, (this.p384KeyPair as any).privateKey, 384
            );
        } else {
            if (!this.secpPrivKey) throw new Error('secp256k1 keys not initialized');
            const fullSecret = secp256k1.getSharedSecret(this.secpPrivKey, peerRaw);
            sharedSecret = fullSecret.slice(1, 33).buffer;
        }

        const hkdfKey = await crypto.subtle.importKey(
            'raw', sharedSecret as any, { name: 'HKDF' }, false, ['deriveKey']
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

    /**
     * Encrypt plaintext using ECDH-derived AES-GCM key.
     */
    async encrypt(plaintext: string): Promise<EncryptedPayload> {
        if (!this.isConnected) throw new Error('Not connected');

        const attestation = await this.fetchAttestation();
        const aesKey = await this.deriveSharedKey(attestation.public_key);

        const nonce = crypto.getRandomValues(new Uint8Array(32));
        const ciphertext = await crypto.subtle.encrypt(
            { name: 'AES-GCM', iv: nonce.slice(0, 12) as any },
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

    /**
     * Decrypt payload from enclave.
     */
    async decrypt(payload: { nonce: string; public_key: string; encrypted_data: string }): Promise<string> {
        if (!this.isConnected) throw new Error('Not connected');

        const aesKey = await this.deriveSharedKey(payload.public_key);
        const nonceBytes = hexToBytes(payload.nonce).slice(0, 12);

        const plaintext = await crypto.subtle.decrypt(
            { name: 'AES-GCM', iv: nonceBytes as any },
            aesKey,
            hexToBytes(payload.encrypted_data) as any
        );

        return new TextDecoder().decode(plaintext);
    }

    /**
     * Call enclave API endpoint with encrypted payload.
     * 
     * @param endpoint - API endpoint path (e.g., '/api/echo')
     * @param data - Request data object
     * @returns Decrypted response data
     */
    async callEncrypted<T = any>(endpoint: string, data: any): Promise<T> {
        const payload = JSON.stringify(data);
        const encrypted = await this.encrypt(payload);

        const response = await fetch(`${this.enclaveBaseUrl}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(encrypted)
        });

        if (!response.ok) {
            throw new Error(`Request failed: ${response.status} ${response.statusText}`);
        }

        const result = await response.json();

        // If response contains encrypted data, decrypt it
        if (result.data && result.data.encrypted_data) {
            const decrypted = await this.decrypt(result.data);
            return JSON.parse(decrypted);
        }

        return result;
    }

    /**
     * Call enclave API endpoint without encryption (for public endpoints).
     */
    async call<T = any>(endpoint: string, method: 'GET' | 'POST' = 'GET', data?: any): Promise<T> {
        const options: RequestInit = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };

        if (data && method === 'POST') {
            options.body = JSON.stringify(data);
        }

        const response = await fetch(`${this.enclaveBaseUrl}${endpoint}`, options);

        if (!response.ok) {
            throw new Error(`Request failed: ${response.status} ${response.statusText}`);
        }

        return response.json();
    }

    /**
     * Check enclave health status.
     */
    async checkHealth(): Promise<any> {
        return this.call('/health');
    }
}

// Singleton instance for convenience
export const enclaveClient = new EnclaveClient();
