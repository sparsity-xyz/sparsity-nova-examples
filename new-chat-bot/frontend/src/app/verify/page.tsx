'use client';

import { useEffect, useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { decodeAttestationDoc, fetchAttestation, base64ToHex, parseUserData } from '@/lib/attestation';

interface VerificationData {
    message: string;
    response: string;
    signature: string;
    platform?: string;
    ai_model?: string;
    timestamp?: number;
    enclave_url?: string;
}

function VerificationContent() {
    const searchParams = useSearchParams();
    const [data, setData] = useState<VerificationData | null>(null);
    const [attestation, setAttestation] = useState<any>(null);
    const [isLoadingAttestation, setIsLoadingAttestation] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const id = searchParams.get('id');
        if (!id) {
            setError('Missing verification ID');
            return;
        }

        try {
            const storedData = localStorage.getItem(`verification_${id}`);
            if (storedData) {
                setData(JSON.parse(storedData));
            } else {
                setError('Verification data not found');
            }
        } catch (err) {
            setError('Failed to load verification data');
        }
    }, [searchParams]);

    const handleGetAttestation = async () => {
        if (!data?.enclave_url) {
            setError('Enclave URL not available');
            return;
        }

        setIsLoadingAttestation(true);
        try {
            const attDoc = await fetchAttestation(data.enclave_url);
            const decoded = await decodeAttestationDoc(attDoc.attestation_doc);
            setAttestation(decoded);
        } catch (err) {
            console.error('Attestation error:', err);
            setError('Failed to fetch attestation');
        } finally {
            setIsLoadingAttestation(false);
        }
    };

    const formatTimestamp = (timestamp?: number) => {
        if (!timestamp) return 'Unknown';
        return new Date(timestamp * 1000).toLocaleString();
    };

    if (error) {
        return (
            <div className="min-h-screen bg-[#0a0a0a] p-8">
                <div className="max-w-4xl mx-auto">
                    <div className="p-4 bg-red-900/50 border border-red-800 rounded-lg text-red-400">
                        {error}
                    </div>
                </div>
            </div>
        );
    }

    if (!data) {
        return (
            <div className="min-h-screen bg-[#0a0a0a] p-8">
                <div className="max-w-4xl mx-auto text-gray-400">
                    Loading verification data...
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[#0a0a0a] p-8">
            <div className="max-w-4xl mx-auto">
                <h1 className="text-2xl font-bold text-white mb-6">Message Verification</h1>

                <div className="space-y-6">
                    {/* Request */}
                    <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-4">
                        <h2 className="text-lg font-medium text-gray-300 mb-2">Request</h2>
                        <pre className="text-white whitespace-pre-wrap break-words">{data.message}</pre>
                    </div>

                    {/* Response */}
                    <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-4">
                        <h2 className="text-lg font-medium text-gray-300 mb-2">Response</h2>
                        <pre className="text-white whitespace-pre-wrap break-words">{data.response}</pre>
                    </div>

                    {/* Metadata */}
                    <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-4">
                        <h2 className="text-lg font-medium text-gray-300 mb-2">Metadata</h2>
                        <div className="space-y-2 text-sm">
                            <div><span className="text-gray-400">Platform:</span> <span className="text-white">{data.platform || 'Unknown'}</span></div>
                            <div><span className="text-gray-400">Model:</span> <span className="text-white">{data.ai_model || 'Unknown'}</span></div>
                            <div><span className="text-gray-400">Timestamp:</span> <span className="text-white">{formatTimestamp(data.timestamp)}</span></div>
                        </div>
                    </div>

                    {/* Signature */}
                    <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-4">
                        <h2 className="text-lg font-medium text-gray-300 mb-2">Signature</h2>
                        <div className="p-3 bg-primary/10 rounded text-primary font-mono text-sm break-all">
                            {data.signature}
                        </div>
                    </div>

                    {/* Attestation */}
                    <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-4">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-medium text-gray-300">Attestation</h2>
                            <button
                                onClick={handleGetAttestation}
                                disabled={isLoadingAttestation}
                                className="px-4 py-2 bg-gray-800 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50"
                            >
                                {isLoadingAttestation ? 'Loading...' : attestation ? 'Refresh' : 'Get Attestation'}
                            </button>
                        </div>

                        {attestation && (
                            <div className="space-y-3 text-xs">
                                <div><span className="text-gray-400">Module ID:</span> <code className="text-white break-all">{attestation.module_id}</code></div>
                                <div><span className="text-gray-400">Digest:</span> <code className="text-white">{attestation.digest}</code></div>
                                <div><span className="text-gray-400">Timestamp:</span> <span className="text-white">{new Date(attestation.timestamp).toLocaleString()}</span></div>

                                <div>
                                    <span className="text-gray-400">PCRs:</span>
                                    <div className="mt-1 space-y-1">
                                        {Object.entries(attestation.pcrs).map(([key, value]) => (
                                            <div key={key} className="text-white">
                                                <span className="text-gray-500">PCR {key}:</span> <code className="break-all">{String(value)}</code>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                <div>
                                    <span className="text-gray-400">Public Key (hex):</span>
                                    <pre className="mt-1 p-2 bg-[#0a0a0a] rounded text-white break-all">{base64ToHex(attestation.public_key)}</pre>
                                </div>

                                <div>
                                    <span className="text-gray-400">User Data:</span>
                                    {(() => {
                                        const parsed = parseUserData(attestation.user_data);
                                        if (parsed.ethAddr) {
                                            return <div className="text-primary mt-1">ETH Address: {parsed.ethAddr}</div>;
                                        }
                                        return <code className="text-white break-all">{parsed.rawHex}</code>;
                                    })()}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

export default function VerifyPage() {
    return (
        <Suspense fallback={<div className="min-h-screen bg-[#0a0a0a] p-8 text-gray-400">Loading...</div>}>
            <VerificationContent />
        </Suspense>
    );
}
