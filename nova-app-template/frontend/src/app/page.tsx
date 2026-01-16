'use client';

import { useState, useEffect } from 'react';
import { EnclaveClient } from '@/lib/crypto';

interface ConnectionStatus {
    connected: boolean;
    enclaveUrl: string;
    teeAddress?: string;
    error?: string;
}

interface ApiResponse {
    success: boolean;
    data?: any;
    error?: string;
}

export default function Home() {
    const [client] = useState(() => new EnclaveClient());
    const [status, setStatus] = useState<ConnectionStatus>({
        connected: false,
        enclaveUrl: '',
    });
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState('');
    const [response, setResponse] = useState<ApiResponse | null>(null);

    // Auto-detect enclave URL from current location
    useEffect(() => {
        if (typeof window !== 'undefined') {
            const currentHost = window.location.origin;
            // If served from enclave, use current origin; otherwise use default
            if (currentHost.includes('sparsity.cloud') || currentHost.includes('localhost:8000')) {
                setStatus(prev => ({ ...prev, enclaveUrl: currentHost }));
            }
        }
    }, []);

    const handleConnect = async () => {
        if (!status.enclaveUrl) return;

        setLoading(true);
        try {
            const attestation = await client.connect(status.enclaveUrl);

            // Try to get TEE address from health endpoint
            let teeAddress = '';
            try {
                const health = await client.call('/health');
                teeAddress = health.tee_address || health.enclave_address || '';
            } catch (e) {
                console.warn('Could not fetch TEE address from health endpoint');
            }

            setStatus({
                ...status,
                connected: true,
                teeAddress,
                error: undefined,
            });
            console.log('Connected! Attestation:', attestation);
        } catch (error) {
            setStatus({
                ...status,
                connected: false,
                error: error instanceof Error ? error.message : 'Connection failed',
            });
        } finally {
            setLoading(false);
        }
    };

    const handleSendMessage = async () => {
        if (!message.trim()) return;

        setLoading(true);
        setResponse(null);

        try {
            // Call the echo endpoint with encrypted payload
            const result = await client.call('/api/echo', 'POST', { message });
            setResponse({ success: true, data: result });
        } catch (error) {
            setResponse({
                success: false,
                error: error instanceof Error ? error.message : 'Request failed',
            });
        } finally {
            setLoading(false);
        }
    };

    const handleGetInfo = async () => {
        setLoading(true);
        setResponse(null);

        try {
            const result = await client.call('/api/info');
            setResponse({ success: true, data: result });
        } catch (error) {
            setResponse({
                success: false,
                error: error instanceof Error ? error.message : 'Request failed',
            });
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{ minHeight: '100vh', padding: '2rem' }}>
            {/* Header */}
            <header style={{ marginBottom: '2rem' }}>
                <h1 style={{ fontSize: '1.5rem', fontWeight: 'bold', marginBottom: '0.5rem' }}>
                    🛡️ Nova App Template
                </h1>
                <p className="text-muted">
                    Secure TEE Application with RA-TLS Communication
                </p>
            </header>

            <div className="grid grid-cols-2 gap-4">
                {/* Connection Panel */}
                <div className="card">
                    <h2 style={{ fontSize: '1rem', fontWeight: '600', marginBottom: '1rem' }}>
                        Enclave Connection
                    </h2>

                    <div className="flex flex-col gap-2">
                        <label className="text-muted" style={{ fontSize: '0.875rem' }}>
                            Enclave URL
                        </label>
                        <input
                            type="text"
                            className="input mono"
                            placeholder="https://your-app.app.sparsity.cloud"
                            value={status.enclaveUrl}
                            onChange={(e) => setStatus({ ...status, enclaveUrl: e.target.value })}
                            disabled={status.connected}
                        />
                    </div>

                    <div className="mt-4">
                        <button
                            className="btn btn-primary"
                            onClick={handleConnect}
                            disabled={loading || status.connected || !status.enclaveUrl}
                            style={{ width: '100%' }}
                        >
                            {loading ? 'Connecting...' : status.connected ? '✓ Connected' : 'Connect to Enclave'}
                        </button>
                    </div>

                    {status.error && (
                        <div className="badge badge-error mt-4" style={{ width: '100%', justifyContent: 'center' }}>
                            {status.error}
                        </div>
                    )}

                    {status.connected && (
                        <div className="mt-4">
                            <div className="badge badge-success">
                                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--success)' }} />
                                Connected
                            </div>
                            {status.teeAddress && (
                                <p className="mono text-muted mt-2" style={{ fontSize: '0.75rem' }}>
                                    TEE: {status.teeAddress.slice(0, 10)}...{status.teeAddress.slice(-8)}
                                </p>
                            )}
                        </div>
                    )}
                </div>

                {/* API Test Panel */}
                <div className="card">
                    <h2 style={{ fontSize: '1rem', fontWeight: '600', marginBottom: '1rem' }}>
                        API Testing
                    </h2>

                    <div className="flex flex-col gap-2">
                        <label className="text-muted" style={{ fontSize: '0.875rem' }}>
                            Message to Echo
                        </label>
                        <input
                            type="text"
                            className="input"
                            placeholder="Enter a message..."
                            value={message}
                            onChange={(e) => setMessage(e.target.value)}
                            disabled={!status.connected}
                        />
                    </div>

                    <div className="mt-4 flex gap-2">
                        <button
                            className="btn btn-primary"
                            onClick={handleSendMessage}
                            disabled={loading || !status.connected || !message.trim()}
                            style={{ flex: 1 }}
                        >
                            Send Echo
                        </button>
                        <button
                            className="btn btn-secondary"
                            onClick={handleGetInfo}
                            disabled={loading || !status.connected}
                        >
                            Get Info
                        </button>
                    </div>

                    {response && (
                        <div className="mt-4">
                            <label className="text-muted" style={{ fontSize: '0.875rem', marginBottom: '0.5rem', display: 'block' }}>
                                Response
                            </label>
                            <pre
                                className="mono"
                                style={{
                                    padding: '1rem',
                                    background: 'var(--bg-tertiary)',
                                    borderRadius: '8px',
                                    fontSize: '0.75rem',
                                    overflow: 'auto',
                                    maxHeight: '200px',
                                    color: response.success ? 'var(--success)' : 'var(--error)',
                                }}
                            >
                                {JSON.stringify(response.data || response.error, null, 2)}
                            </pre>
                        </div>
                    )}
                </div>
            </div>

            {/* Footer */}
            <footer className="text-muted" style={{ marginTop: '2rem', fontSize: '0.875rem', textAlign: 'center' }}>
                <p>
                    Built with <span className="text-accent">Nova Platform</span> • End-to-end encrypted • Verifiable TEE
                </p>
            </footer>
        </div>
    );
}
