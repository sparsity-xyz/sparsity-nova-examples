/**
 * WebCrypto-based encryption module for P-384 ECDH + AES-GCM.
 * 
 * This module implements the same encryption protocol as the enclave:
 * - P-384 (secp384r1) ECDH for key exchange
 * - HKDF-SHA256 for key derivation
 * - AES-256-GCM for encryption
 */

export interface EncryptedPayload {
    nonce: string;     // hex-encoded 32 bytes
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
function bufferToHex(buffer: ArrayBuffer): string {
    return Array.from(new Uint8Array(buffer))
        .map(b => b.toString(16).padStart(2, '0'))
        .join('');
}

// Convert hex string to ArrayBuffer
function hexToBuffer(hex: string): ArrayBuffer {
    const bytes = new Uint8Array(hex.length / 2);
    for (let i = 0; i < hex.length; i += 2) {
        bytes[i / 2] = parseInt(hex.substr(i, 2), 16);
    }
    return bytes.buffer;
}

// Convert DER SubjectPublicKeyInfo to raw EC point (for WebCrypto import)
function derToRaw(derKey: ArrayBuffer): ArrayBuffer {
    const der = new Uint8Array(derKey);
    // P-384 DER SPKI is 120 bytes, raw point is last 97 bytes (04 || x || y)
    if (der.length === 120) {
        return der.slice(23).buffer;
    }
    // Already raw format
    return derKey;
}

// Convert raw EC point to DER SubjectPublicKeyInfo (for protocol compatibility)
function rawToDer(rawKey: ArrayBuffer): ArrayBuffer {
    const raw = new Uint8Array(rawKey);
    if (raw.length !== 97) {
        throw new Error(`Invalid raw P-384 public key length: ${raw.length}`);
    }
    // P-384 SPKI header
    const spkiHeader = new Uint8Array([
        0x30, 0x76, // SEQUENCE, 118 bytes
        0x30, 0x10, // SEQUENCE, 16 bytes
        0x06, 0x07, // OID, 7 bytes
        0x2a, 0x86, 0x48, 0xce, 0x3d, 0x02, 0x01, // ecPublicKey OID
        0x06, 0x05, // OID, 5 bytes
        0x2b, 0x81, 0x04, 0x00, 0x22, // secp384r1 OID
        0x03, 0x62, // BIT STRING, 98 bytes
        0x00, // unused bits
    ]);
    const der = new Uint8Array(120);
    der.set(spkiHeader, 0);
    der.set(raw, 23);
    return der.buffer;
}

export class EnclaveClient {
    private keyPair: CryptoKeyPair | null = null;
    private serverPublicKey: CryptoKey | null = null;
    private enclaveBaseUrl: string = '';
    private isConnected: boolean = false;

    /**
     * Connect to enclave and initialize crypto.
     * Fetches attestation from /.well-known/attestation to get server public key.
     */
    async connect(baseUrl: string): Promise<AttestationDoc> {
        // Normalize base URL
        this.enclaveBaseUrl = baseUrl.replace(/\/$/, '');

        // Generate P-384 key pair
        this.keyPair = await crypto.subtle.generateKey(
            {
                name: 'ECDH',
                namedCurve: 'P-384',
            },
            true,
            ['deriveBits']
        );

        // Fetch attestation to get server's public key
        const attestation = await this.fetchAttestation();

        // Import server's public key
        const serverPubKeyDer = hexToBuffer(attestation.public_key);
        const serverPubKeyRaw = derToRaw(serverPubKeyDer);

        this.serverPublicKey = await crypto.subtle.importKey(
            'raw',
            serverPubKeyRaw,
            {
                name: 'ECDH',
                namedCurve: 'P-384',
            },
            true,
            []
        );

        this.isConnected = true;
        return attestation;
    }

    /**
   * Fetch attestation document from /.well-known/attestation
   * Uses POST method (required by enclave runtime in Docker)
   * Fetches raw CBOR and parses it properly
   */
    async fetchAttestation(): Promise<AttestationDoc & { parsedAttestation?: string }> {
        // First try to fetch as arraybuffer (raw CBOR)
        const response = await fetch(`${this.enclaveBaseUrl}/.well-known/attestation`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        if (!response.ok) {
            throw new Error(`Failed to fetch attestation: ${response.status}`);
        }

        // Check content-type to determine how to parse
        const contentType = response.headers.get('content-type') || '';

        if (contentType.includes('application/cbor') || contentType.includes('application/octet-stream')) {
            // Raw CBOR binary - decode it
            const cbor = await import('cbor-web');
            const arrayBuffer = await response.arrayBuffer();
            const cborData = cbor.decode(new Uint8Array(arrayBuffer));

            return this.parseCborAttestation(cborData);
        } else {
            // JSON response - might contain base64 CBOR or pre-parsed data
            const jsonData = await response.json();

            // If it's pre-parsed attestation_document format
            if (jsonData.attestation_document && typeof jsonData.attestation_document === 'object') {
                return {
                    attestation_doc: JSON.stringify(jsonData),
                    public_key: jsonData.attestation_document.public_key || '',
                    parsedAttestation: JSON.stringify(jsonData),
                };
            }

            // If it has attestation_doc as base64 string, decode it
            if (jsonData.attestation_doc && typeof jsonData.attestation_doc === 'string') {
                try {
                    const cbor = await import('cbor-web');
                    const binary = atob(jsonData.attestation_doc);
                    const bytes = new Uint8Array(binary.length);
                    for (let i = 0; i < binary.length; i++) {
                        bytes[i] = binary.charCodeAt(i);
                    }
                    const cborData = cbor.decode(bytes);
                    const parsed = await this.parseCborAttestation(cborData);
                    return {
                        ...parsed,
                        attestation_doc: jsonData.attestation_doc,
                    };
                } catch (e) {
                    console.warn('Failed to decode base64 CBOR attestation:', e);
                }
            }

            return jsonData;
        }
    }

    /**
     * Parse CBOR attestation data (COSE Sign1 format)
     * Robustly handles Map or Object formats and string or integer keys
     */
    private async parseCborAttestation(cborData: unknown): Promise<AttestationDoc & { parsedAttestation?: string }> {
        const cbor = await import('cbor-web');

        // Helper function to convert bytes to hex
        const bytesToHex = (bytes: Uint8Array | ArrayBuffer): string => {
            const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
            return Array.from(arr).map(b => b.toString(16).padStart(2, '0')).join('');
        };

        // Check if it's a COSE Sign1 message (array with 4 elements)
        let attDocRaw: any;
        let signature: Uint8Array | null = null;

        if (Array.isArray(cborData) && cborData.length >= 3) {
            // Extract payload (attestation document) and signature
            const payload = cborData[2];
            signature = cborData.length > 3 ? cborData[3] : null;
            attDocRaw = cbor.decode(payload);
        } else {
            attDocRaw = cborData;
        }

        // Robust field extraction helper (handles Map/Object and string/int keys)
        const getField = (doc: any, name: string, id: number) => {
            if (doc instanceof Map) {
                return doc.get(name) ?? doc.get(id);
            }
            return doc[name] ?? doc[id];
        };

        // Extract fields
        const moduleId = getField(attDocRaw, 'module_id', 1);
        const timestamp = getField(attDocRaw, 'timestamp', 2);
        const digest = getField(attDocRaw, 'digest', 3);
        const pcrsRaw = getField(attDocRaw, 'pcrs', 4);
        const certificate = getField(attDocRaw, 'certificate', 5);
        const cabundle = getField(attDocRaw, 'cabundle', 6);
        const publicKeyRaw = getField(attDocRaw, 'public_key', 7);
        const userDataRaw = getField(attDocRaw, 'user_data', 8);
        const nonce = getField(attDocRaw, 'nonce', 9);

        // Format PCRs as hex strings
        const pcrs: Record<string, string> = {};
        if (pcrsRaw) {
            if (pcrsRaw instanceof Map) {
                for (const [key, value] of Array.from(pcrsRaw.entries())) {
                    if (value instanceof Uint8Array || value instanceof ArrayBuffer) {
                        pcrs[String(key)] = bytesToHex(value as Uint8Array);
                    } else {
                        pcrs[String(key)] = String(value);
                    }
                }
            } else if (typeof pcrsRaw === 'object') {
                for (const [key, value] of Object.entries(pcrsRaw)) {
                    if (value instanceof Uint8Array || value instanceof ArrayBuffer) {
                        pcrs[String(key)] = bytesToHex(value as Uint8Array);
                    } else {
                        pcrs[String(key)] = String(value);
                    }
                }
            }
        }

        // Parse user_data
        let userData = null;
        if (userDataRaw) {
            try {
                if (userDataRaw instanceof Uint8Array || userDataRaw instanceof ArrayBuffer) {
                    const decoder = new TextDecoder();
                    const userDataStr = decoder.decode(new Uint8Array(userDataRaw));
                    userData = JSON.parse(userDataStr);
                } else if (typeof userDataRaw === 'string') {
                    userData = JSON.parse(userDataRaw);
                } else {
                    userData = userDataRaw;
                }
            } catch (e) {
                console.warn('Failed to parse user_data as JSON:', e);
            }
        }

        // Format public key
        let publicKey = '';
        if (publicKeyRaw instanceof Uint8Array || publicKeyRaw instanceof ArrayBuffer) {
            publicKey = bytesToHex(publicKeyRaw);
        } else if (typeof publicKeyRaw === 'string') {
            publicKey = publicKeyRaw;
        }

        // Helper function to convert bytes to base64
        const bytesToBase64 = (bytes: Uint8Array | ArrayBuffer): string => {
            const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
            return btoa(String.fromCharCode.apply(null, Array.from(new Uint8Array(arr))));
        };

        const parsedResult = {
            attestation_document: {
                module_id: moduleId ? String(moduleId) : '',
                timestamp: typeof timestamp === 'number' ? timestamp : 0,
                digest: digest instanceof Uint8Array || digest instanceof ArrayBuffer ? bytesToHex(digest) : String(digest || ''),
                pcrs,
                public_key: publicKey,
                user_data: userData,
                certificate: certificate ? bytesToBase64(certificate) : '',
                cabundle: Array.isArray(cabundle) ? cabundle.map((cert) => bytesToBase64(cert)) : [],
                nonce: nonce ? (nonce instanceof Uint8Array || nonce instanceof ArrayBuffer ? bytesToHex(nonce) : String(nonce)) : '',
            },
            signature: signature ? bytesToHex(signature) : null
        };

        return {
            attestation_doc: JSON.stringify(parsedResult),
            public_key: publicKey,
            parsedAttestation: JSON.stringify(parsedResult),
        };
    }

    /**
     * Get our public key in DER hex format (for sending to server)
     */
    async getPublicKeyHex(): Promise<string> {
        if (!this.keyPair) {
            throw new Error('Client not initialized. Call connect() first.');
        }
        const rawKey = await crypto.subtle.exportKey('raw', this.keyPair.publicKey);
        const derKey = rawToDer(rawKey);
        return bufferToHex(derKey);
    }

    /**
     * Derive shared AES key using ECDH + HKDF
     */
    private async deriveSharedKey(peerPublicKey: CryptoKey): Promise<CryptoKey> {
        if (!this.keyPair) {
            throw new Error('Client not initialized. Call connect() first.');
        }

        // Derive shared secret using ECDH
        const sharedSecret = await crypto.subtle.deriveBits(
            {
                name: 'ECDH',
                public: peerPublicKey,
            },
            this.keyPair.privateKey,
            384 // P-384 = 384 bits
        );

        // Use HKDF to derive AES key (matching Python implementation)
        const hkdfKey = await crypto.subtle.importKey(
            'raw',
            sharedSecret,
            { name: 'HKDF' },
            false,
            ['deriveBits', 'deriveKey']
        );

        // Derive 256-bit AES key
        return crypto.subtle.deriveKey(
            {
                name: 'HKDF',
                hash: 'SHA-256',
                salt: new ArrayBuffer(0), // No salt (matches Python salt=None)
                info: new TextEncoder().encode('encryption data'),
            },
            hkdfKey,
            { name: 'AES-GCM', length: 256 },
            false,
            ['encrypt', 'decrypt']
        );
    }

    /**
     * Encrypt data for sending to server
     */
    async encrypt(plaintext: string): Promise<EncryptedPayload> {
        if (!this.serverPublicKey || !this.keyPair) {
            throw new Error('Client not initialized. Call connect() first.');
        }

        // Derive shared key
        const aesKey = await this.deriveSharedKey(this.serverPublicKey);

        // Generate 32-byte nonce
        const nonce = crypto.getRandomValues(new Uint8Array(32));

        // Encrypt using AES-GCM
        const encoded = new TextEncoder().encode(plaintext);
        const ciphertext = await crypto.subtle.encrypt(
            {
                name: 'AES-GCM',
                iv: nonce,
            },
            aesKey,
            encoded
        );

        // Get our public key in DER format
        const publicKeyHex = await this.getPublicKeyHex();

        return {
            nonce: bufferToHex(nonce.buffer),
            public_key: publicKeyHex,
            data: bufferToHex(ciphertext),
        };
    }

    /**
     * Decrypt response from server
     */
    async decrypt(payload: { nonce: string; public_key: string; encrypted_data: string }): Promise<string> {
        if (!this.keyPair) {
            throw new Error('Client not initialized. Call connect() first.');
        }

        // Import server's response public key
        const serverPubKeyDer = hexToBuffer(payload.public_key);
        const serverPubKeyRaw = derToRaw(serverPubKeyDer);

        const serverResponseKey = await crypto.subtle.importKey(
            'raw',
            serverPubKeyRaw,
            {
                name: 'ECDH',
                namedCurve: 'P-384',
            },
            true,
            []
        );

        // Derive shared key with response key
        const aesKey = await this.deriveSharedKey(serverResponseKey);

        // Decrypt using AES-GCM
        const nonce = hexToBuffer(payload.nonce);
        const ciphertext = hexToBuffer(payload.encrypted_data);

        const plaintext = await crypto.subtle.decrypt(
            {
                name: 'AES-GCM',
                iv: new Uint8Array(nonce),
            },
            aesKey,
            ciphertext
        );

        return new TextDecoder().decode(plaintext);
    }

    /**
     * Set API key on the enclave (encrypted)
     */
    async setApiKey(apiKey: string, platform: string = 'openai'): Promise<{ status: string; message: string }> {
        if (!this.isConnected) {
            throw new Error('Client not connected. Call connect() first.');
        }

        const payload = JSON.stringify({ api_key: apiKey, platform });
        const encrypted = await this.encrypt(payload);

        const response = await fetch(`${this.enclaveBaseUrl}/set-api-key`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(encrypted),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || `Request failed: ${response.status}`);
        }

        const result = await response.json();

        // Decrypt response
        const decrypted = await this.decrypt(result.data);
        return JSON.parse(decrypted);
    }

    /**
     * Send chat message (encrypted, uses cached API key)
     * Returns response with full verification data for chain verification
     */
    async chat(message: string, model: string = 'gpt-4'): Promise<ChatResponse & {
        signature: string;
        verificationData: {
            attestation: string;
            publicKey: string;
            ethAddr: string;
            encryptedRequest: string;
            decryptedRequest: string;
            rawResponse: string;
            encryptedResponse: string;
            decryptedResponse: string;
        };
    }> {
        if (!this.isConnected) {
            throw new Error('Client not connected. Call connect() first.');
        }

        const requestPayload = JSON.stringify({ message, ai_model: model });
        const encrypted = await this.encrypt(requestPayload);

        const response = await fetch(`${this.enclaveBaseUrl}/talk`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(encrypted),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || `Request failed: ${response.status}`);
        }

        const result = await response.json();

        // Decrypt response
        const decrypted = await this.decrypt(result.data);
        const parsedResponse = JSON.parse(decrypted);

        // Get attestation for verification
        const attestation = await this.fetchAttestation();

        // Get enclave address for signature verification
        const health = await this.checkHealth();

        return {
            ...parsedResponse,
            signature: result.sig,
            verificationData: {
                attestation: attestation.attestation_doc,
                publicKey: attestation.public_key,
                ethAddr: health.enclave_address,
                encryptedRequest: JSON.stringify(encrypted),
                decryptedRequest: requestPayload,
                rawResponse: JSON.stringify(result),
                encryptedResponse: JSON.stringify(result.data),
                decryptedResponse: decrypted,
            },
        };
    }

    /**
     * Check health status of enclave
     */
    async checkHealth(): Promise<{ status: string; api_key_available: boolean; enclave_address: string }> {
        const response = await fetch(`${this.enclaveBaseUrl}/`);
        if (!response.ok) {
            throw new Error(`Health check failed: ${response.status}`);
        }
        return response.json();
    }

    get connected(): boolean {
        return this.isConnected;
    }

    get baseUrl(): string {
        return this.enclaveBaseUrl;
    }
}

// Singleton instance
export const enclaveClient = new EnclaveClient();
