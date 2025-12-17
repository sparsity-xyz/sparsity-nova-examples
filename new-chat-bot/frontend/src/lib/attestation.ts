/**
 * Attestation fetching and CBOR decoding utilities.
 * Note: Validation is skipped per requirements - only fetch and decode.
 */

// Convert base64 to hex string
export function base64ToHex(base64: string): string {
    try {
        const binary = atob(base64);
        let hex = '';
        for (let i = 0; i < binary.length; i++) {
            const byte = binary.charCodeAt(i).toString(16).padStart(2, '0');
            hex += byte;
        }
        return hex;
    } catch (e) {
        return base64;
    }
}

// Parse user_data - supports both raw ETH address and JSON format
export interface ParsedUserData {
    isJson: boolean;
    ethAddr?: string;
    rawHex: string;
    jsonData?: Record<string, unknown>;
}

export function parseUserData(base64UserData: string): ParsedUserData {
    const rawHex = base64ToHex(base64UserData);

    try {
        const binary = atob(base64UserData);
        const utf8String = decodeURIComponent(
            binary.split('').map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join('')
        );
        const jsonData = JSON.parse(utf8String);

        if (typeof jsonData === 'object' && jsonData !== null) {
            return {
                isJson: true,
                ethAddr: jsonData.eth_addr || undefined,
                rawHex,
                jsonData
            };
        }
    } catch (e) {
        // Not valid JSON
    }

    // Check if it's a 20-byte ETH address (40 hex chars)
    if (rawHex.length === 40) {
        return {
            isJson: false,
            ethAddr: '0x' + rawHex,
            rawHex
        };
    }

    return {
        isJson: false,
        rawHex
    };
}

export interface DecodedAttestation {
    module_id: string;
    digest: string;
    timestamp: number;
    pcrs: Record<string, string>;
    certificate: string;
    cabundle: string[];
    public_key: string;
    user_data: string;
    nonce: string;
}

/**
 * Decode CBOR attestation document using cbor-web library.
 * Dynamic import to avoid SSR issues.
 */
export async function decodeAttestationDoc(base64Doc: string): Promise<DecodedAttestation> {
    // Dynamic import for browser-only cbor library
    const cbor = await import('cbor-web');

    const binary = atob(base64Doc);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }

    // CBOR decode the COSE_Sign1 structure
    const coseSign1 = cbor.decode(bytes);

    // COSE_Sign1 is an array: [protected, unprotected, payload, signature]
    if (!Array.isArray(coseSign1) || coseSign1.length < 4) {
        throw new Error('Invalid COSE_Sign1 structure');
    }

    const payload = coseSign1[2];

    // Decode the payload which contains the attestation document
    const attDoc = cbor.decode(payload);

    // Convert PCRs to hex strings
    const pcrs: Record<string, string> = {};
    if (attDoc.pcrs) {
        for (const [key, value] of Object.entries(attDoc.pcrs)) {
            if (value instanceof Uint8Array) {
                pcrs[String(key)] = Array.from(value).map(b => b.toString(16).padStart(2, '0')).join('');
            } else {
                pcrs[String(key)] = String(value);
            }
        }
    }

    // Helper to convert Uint8Array to base64 for consistency
    const toBase64 = (data: Uint8Array | undefined): string => {
        if (!data) return '';
        return btoa(String.fromCharCode.apply(null, Array.from(data)));
    };

    return {
        module_id: attDoc.module_id || '',
        digest: attDoc.digest || '',
        timestamp: attDoc.timestamp || 0,
        pcrs,
        certificate: toBase64(attDoc.certificate),
        cabundle: (attDoc.cabundle || []).map((cert: Uint8Array) => toBase64(cert)),
        public_key: toBase64(attDoc.public_key),
        user_data: toBase64(attDoc.user_data),
        nonce: toBase64(attDoc.nonce),
    };
}

/**
 * Fetch attestation from enclave's /.well-known/attestation endpoint
 * Uses POST method (required by enclave runtime in Docker)
 */
export async function fetchAttestation(baseUrl: string): Promise<{
    attestation_doc: string;
    public_key: string;
}> {
    const url = `${baseUrl.replace(/\/$/, '')}/.well-known/attestation`;
    const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
    });

    if (!response.ok) {
        throw new Error(`Failed to fetch attestation: ${response.status}`);
    }

    return response.json();
}
