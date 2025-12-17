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
   */
    async fetchAttestation(): Promise<AttestationDoc> {
        const response = await fetch(`${this.enclaveBaseUrl}/.well-known/attestation`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        if (!response.ok) {
            throw new Error(`Failed to fetch attestation: ${response.status}`);
        }
        return response.json();
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
     */
    async chat(message: string, model: string = 'gpt-4'): Promise<ChatResponse> {
        if (!this.isConnected) {
            throw new Error('Client not connected. Call connect() first.');
        }

        const payload = JSON.stringify({ message, ai_model: model });
        const encrypted = await this.encrypt(payload);

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
        return {
            ...JSON.parse(decrypted),
            signature: result.sig,
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
