'use client';

import { useEffect, useState } from 'react';

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
    type?: string;
}

export default function Home() {
    const [client] = useState(() => new EnclaveClient());
    const [status, setStatus] = useState<ConnectionStatus>({
        connected: false,
        enclaveUrl: '',
    });
    const [loading, setLoading] = useState(false);
    const [activeTab, setActiveTab] = useState('identity');
    const [response, setResponse] = useState<ApiResponse | null>(null);

    const [showAttestation, setShowAttestation] = useState(false);
    const [attestationLoading, setAttestationLoading] = useState(false);
    const [attestationError, setAttestationError] = useState<string | null>(null);
    const [attestationData, setAttestationData] = useState<any>(null);

    // Form inputs
    const [echoMsg, setEchoMsg] = useState('Hello from Nova!');
    const [storageKey, setStorageKey] = useState('user_settings');
    const [storageVal, setStorageVal] = useState('{"theme": "dark"}');

    // Auto-detect enclave URL from current location
    useEffect(() => {
        if (typeof window !== 'undefined') {
            const currentHost = window.location.origin;
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
            const statusInfo = await client.call('/status');
            setStatus({
                ...status,
                connected: true,
                teeAddress: statusInfo.eth_address,
                error: undefined,
            });
            setResponse({ success: true, data: { attestation, statusInfo }, type: 'Connection' });
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

    const callApi = async (path: string, method: 'GET' | 'POST' = 'GET', body?: any, encrypted = false) => {
        setLoading(true);
        setResponse(null);
        try {
            let res;
            if (encrypted) {
                res = await client.callEncrypted(path, body);
            } else {
                res = await client.call(path, method, body);
            }
            setResponse({ success: true, data: res, type: path });
        } catch (error) {
            setResponse({ success: false, error: error instanceof Error ? error.message : 'Request failed', type: path });
        } finally {
            setLoading(false);
        }
    };

    const syntaxHighlight = (jsonString: string) => {
        if (!jsonString) return '';
        const escaped = jsonString.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        return escaped.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g, match => {
            if (/^".*"\s*:?$/.test(match)) {
                if (/":$/.test(match)) {
                    return `<span class="text-sky-700 font-semibold">${match}</span>`;
                }
                return `<span class="text-emerald-700">${match}</span>`;
            }
            if (/true|false/.test(match)) return `<span class="text-violet-700">${match}</span>`;
            if (/null/.test(match)) return `<span class="text-slate-500">${match}</span>`;
            return `<span class="text-amber-700">${match}</span>`;
        });
    };

    const handleViewAttestation = async () => {
        if (!status.connected) return;
        setShowAttestation(true);
        setAttestationLoading(true);
        setAttestationError(null);
        setAttestationData(null);
        try {
            const attestation = await client.fetchAttestation();
            setAttestationData(attestation);
        } catch (error) {
            setAttestationError(error instanceof Error ? error.message : 'Failed to fetch attestation');
        } finally {
            setAttestationLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-white via-slate-50 to-sky-50 text-slate-900 p-8 font-sans">
            <header className="max-w-7xl mx-auto mb-12">
                <div className="flex flex-col gap-6 rounded-3xl border border-slate-200 bg-white/95 backdrop-blur px-8 py-6 shadow-xl shadow-slate-200/50">
                    <div className="flex items-start justify-between gap-6 flex-wrap">
                        <div>
                            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Nova Platform</p>
                            <h1 className="text-3xl font-semibold text-slate-900 mt-2">
                                🛡️ Nova App Template
                            </h1>
                            <p className="text-slate-500 mt-2">Secure, verifiable TEE apps with RA‑TLS, S3, and on‑chain trust.</p>
                        </div>

                        <div className="min-w-[320px] flex-1 max-w-md">
                            <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
                                <div className="flex-1">
                                    <label className="text-[10px] uppercase tracking-widest text-slate-400">Enclave URL</label>
                                    <input
                                        className="mt-1 w-full bg-transparent text-sm text-slate-700 outline-none placeholder:text-slate-400"
                                        value={status.enclaveUrl}
                                        onChange={(e) => setStatus({ ...status, enclaveUrl: e.target.value })}
                                        placeholder="https://your-app.sparsity.cloud"
                                    />
                                </div>
                                <button
                                    onClick={handleConnect}
                                    disabled={loading || status.connected}
                                    className={`px-4 py-2 rounded-xl text-sm font-semibold transition ${status.connected
                                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                        : 'bg-blue-600 hover:bg-blue-500 text-white shadow-sm'
                                        }`}
                                >
                                    {loading ? 'Connecting...' : status.connected ? 'Connected' : 'Connect'}
                                </button>
                            </div>
                        </div>
                    </div>

                    <div className="flex flex-wrap gap-3 text-xs text-slate-500">
                        <span className="px-3 py-1 rounded-full bg-sky-50 border border-sky-100 text-sky-700">RA‑TLS</span>
                        <span className="px-3 py-1 rounded-full bg-sky-50 border border-sky-100 text-sky-700">S3 Storage</span>
                        <span className="px-3 py-1 rounded-full bg-sky-50 border border-sky-100 text-sky-700">Oracles</span>
                        <span className="px-3 py-1 rounded-full bg-sky-50 border border-sky-100 text-sky-700">Event Listener</span>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Left: Navigation & Info */}
                <div className="lg:col-span-1 space-y-6">
                    <section className="bg-white rounded-2xl border border-slate-200 p-6 shadow-lg shadow-slate-200/60">
                        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-[0.2em] mb-4">Capabilities</h2>
                        <nav className="flex flex-col gap-2">
                            {[
                                { id: 'identity', label: 'Identity & RA-TLS', icon: '🔑' },
                                { id: 'storage', label: 'S3 Storage', icon: '📦' },
                                { id: 'oracle', label: 'Oracle Demo', icon: '🌐' },
                                { id: 'events', label: 'Event Monitor', icon: '📊' },
                            ].map(tab => (
                                <button
                                    key={tab.id}
                                    onClick={() => setActiveTab(tab.id)}
                                    className={`group flex items-center gap-3 px-4 py-3 rounded-xl transition text-left border ${activeTab === tab.id
                                        ? 'bg-blue-50 text-slate-900 border-blue-200 shadow-sm shadow-blue-100/60'
                                        : 'text-slate-600 border-transparent hover:border-slate-200 hover:bg-slate-50'
                                        }`}
                                >
                                    <span className={`text-base ${activeTab === tab.id ? 'text-blue-600' : 'text-slate-400 group-hover:text-slate-600'}`}>{tab.icon}</span>
                                    <span className={`text-sm font-medium ${activeTab === tab.id ? 'text-slate-900' : 'text-slate-600 group-hover:text-slate-900'}`}>{tab.label}</span>
                                </button>
                            ))}
                        </nav>
                    </section>

                    {status.connected && (
                        <section className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
                            <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-[0.2em] mb-3">Enclave Identity</h2>
                            <div className="space-y-4">
                                <div>
                                    <label className="text-xs text-slate-500 block mb-1">TEE Wallet Address</label>
                                    <code className="text-xs bg-slate-50 px-2 py-1 rounded block truncate border border-slate-200 text-slate-700">
                                        {status.teeAddress}
                                    </code>
                                </div>
                                <div className="flex gap-2 text-xs">
                                    <span className="bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded border border-emerald-200">Active</span>
                                    <span className="bg-blue-50 text-blue-700 px-2 py-0.5 rounded border border-blue-200">Verifiable</span>
                                </div>
                            </div>
                        </section>
                    )}
                </div>

                {/* Right: Content Area */}
                <div className="lg:col-span-2 space-y-6">
                    <div className="bg-white rounded-2xl border border-slate-200 p-8 min-h-[400px] shadow-lg shadow-slate-200/60">
                        {activeTab === 'identity' && (
                            <div className="space-y-6">
                                <h2 className="text-xl font-semibold mb-4">Identity & RA-TLS</h2>
                                <p className="text-slate-600 text-sm leading-relaxed mb-6">
                                    Establish a secure, hardware-verifiable channel with the enclave using AWS Nitro Attestation
                                    and ECDH key exchange.
                                </p>

                                <div className="space-y-4">
                                    <div className="flex flex-col gap-2">
                                        <label className="text-sm text-slate-600">Message to Echo</label>
                                        <div className="flex gap-2">
                                            <input
                                                className="bg-white border border-slate-300 rounded-lg px-4 py-2 flex-1 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
                                                value={echoMsg}
                                                onChange={(e) => setEchoMsg(e.target.value)}
                                            />
                                            <button
                                                onClick={() => callApi('/api/echo', 'POST', { message: echoMsg }, true)}
                                                disabled={loading || !status.connected}
                                                className="bg-blue-600 hover:bg-blue-500 text-white px-6 py-2 rounded-lg font-semibold shadow-sm disabled:opacity-50"
                                            >
                                                Encrypted Send
                                            </button>
                                        </div>
                                    </div>
                                    <div className="flex gap-4">
                                        <button
                                            onClick={handleViewAttestation}
                                            disabled={loading || !status.connected}
                                            className="text-sm text-blue-600 hover:text-blue-700 font-medium"
                                        >
                                            View Attestation Document →
                                        </button>
                                        <button
                                            onClick={() => {
                                                setShowAttestation(false);
                                                callApi('/api/random', 'GET');
                                            }}
                                            disabled={loading || !status.connected}
                                            className="text-sm text-emerald-600 hover:text-emerald-700 font-medium"
                                        >
                                            Fetch Hardware Entropy (NSM) →
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )}

                        {activeTab === 'storage' && (
                            <div className="space-y-6">
                                <h2 className="text-xl font-semibold mb-4">S3 Persistent Storage</h2>
                                <p className="text-slate-600 text-sm leading-relaxed mb-6">
                                    Store and retrieve sensitive state in encrypted S3 objects. Access is restricted to
                                    this specific TEE instance.
                                </p>

                                <div className="grid grid-cols-2 gap-4">
                                    <div className="flex flex-col gap-2 col-span-1">
                                        <label className="text-sm text-slate-600">Key</label>
                                        <input
                                            className="bg-white border border-slate-300 rounded-lg px-4 py-2 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                                            value={storageKey}
                                            onChange={(e) => setStorageKey(e.target.value)}
                                        />
                                    </div>
                                    <div className="flex flex-col gap-2 col-span-1">
                                        <label className="text-sm text-slate-600">Value (JSON/Text)</label>
                                        <input
                                            className="bg-white border border-slate-300 rounded-lg px-4 py-2 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                                            value={storageVal}
                                            onChange={(e) => setStorageVal(e.target.value)}
                                        />
                                    </div>
                                </div>
                                <div className="flex gap-3">
                                    <button
                                        onClick={() => callApi('/api/storage', 'POST', { key: storageKey, value: storageVal })}
                                        disabled={loading || !status.connected}
                                        className="bg-emerald-600 hover:bg-emerald-500 text-white px-6 py-2 rounded-lg font-semibold shadow-sm flex-1"
                                    >
                                        Store Value
                                    </button>
                                    <button
                                        onClick={() => callApi(`/api/storage/${storageKey}`, 'GET')}
                                        disabled={loading || !status.connected}
                                        className="bg-slate-100 hover:bg-slate-200 text-slate-700 px-6 py-2 rounded-lg font-semibold flex-1"
                                    >
                                        Retrieve Key
                                    </button>
                                </div>
                                <button
                                    onClick={() => callApi('/api/storage', 'GET')}
                                    className="text-sm text-slate-500 hover:text-slate-700"
                                >
                                    List all stored keys...
                                </button>
                            </div>
                        )}

                        {activeTab === 'oracle' && (
                            <div className="space-y-6">
                                <h2 className="text-xl font-semibold mb-4">Oracle: Internet → Chain</h2>
                                <p className="text-slate-600 text-sm leading-relaxed mb-6">
                                    The enclave fetches real-time data from the internet, processes it, and signs a
                                    cryptographically secure transaction for on-chain execution.
                                </p>

                                <div className="bg-gradient-to-br from-slate-50 to-white border border-slate-200 rounded-2xl p-8 flex flex-col items-center justify-center gap-6 shadow-sm">
                                    <div className="text-center">
                                        <div className="text-4xl mb-2">💎</div>
                                        <div className="text-2xl font-mono text-slate-900 tracking-tight">ETH / USD</div>
                                    </div>
                                    <button
                                        onClick={() => callApi('/api/oracle/price', 'GET')}
                                        disabled={loading || !status.connected}
                                        className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white px-8 py-3 rounded-xl font-semibold shadow-lg shadow-blue-200/60"
                                    >
                                        Fetch & Sign Update
                                    </button>
                                </div>
                            </div>
                        )}

                        {activeTab === 'events' && (
                            <div className="space-y-6">
                                <h2 className="text-xl font-semibold mb-4">On-Chain Event Monitor</h2>
                                <p className="text-slate-600 text-sm leading-relaxed mb-6">
                                    Background workers in the enclave monitor blockchain events and respond automatically.
                                    The state hash is updated periodically to ensure data integrity.
                                </p>

                                <div className="space-y-4">
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                                            <label className="text-xs text-slate-500 block mb-1">Last Cron Run</label>
                                            <span className="text-sm font-mono text-emerald-600 italic">
                                                {status.connected && response?.data?.cron_info?.last_run
                                                    ? new Date(response.data.cron_info.last_run).toLocaleTimeString()
                                                    : 'Awaiting sync...'}
                                            </span>
                                        </div>
                                        <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                                            <label className="text-xs text-slate-500 block mb-1">State Hash (Keccak256)</label>
                                            <span className="text-sm font-mono text-blue-600 italic truncate block">
                                                {status.connected && response?.data?.last_state_hash
                                                    ? `0x${response.data.last_state_hash.slice(0, 16)}...`
                                                    : 'Awaiting sync...'}
                                            </span>
                                        </div>
                                    </div>
                                    <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                                        <label className="text-xs text-slate-500 block mb-1">Background Runner Status</label>
                                        <div className="flex items-center gap-2">
                                            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                                            <span className="text-xs text-slate-600">
                                                Worker active • {response?.data?.cron_info?.counter || 0} tasks completed
                                            </span>
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => callApi('/status', 'GET')}
                                        disabled={loading || !status.connected}
                                        className="w-full py-3 border border-slate-200 rounded-xl text-sm font-medium hover:bg-slate-50 transition"
                                    >
                                        Refresh Background Job Stats
                                    </button>
                                </div>
                            </div>
                        )}

                        {/* Universal Response Viewer */}
                        {response && (
                            <div className="mt-8 border-t border-slate-200 pt-8 animate-in fade-in slide-in-from-top-4 duration-300">
                                <div className="flex justify-between items-center mb-3">
                                    <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest">
                                        Latest Response: {response.type}
                                    </h3>
                                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${response.success ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                                        {response.success ? 'SUCCESS' : 'FAILED'}
                                    </span>
                                </div>
                                <pre className="bg-slate-50 rounded-xl p-5 text-xs font-mono text-slate-700 overflow-auto max-h-[300px] border border-slate-200 whitespace-pre-wrap">
                                    {JSON.stringify(response.data || response.error, null, 2)}
                                </pre>
                            </div>
                        )}
                    </div>
                </div>
            </main>

            <footer className="max-w-6xl mx-auto mt-12 text-center text-slate-500 text-sm">
                Built with <span className="text-blue-600 font-semibold">Nova Platform</span> • Powered by AWS Nitro Enclaves
            </footer>

            {showAttestation && (
                <div className="fixed inset-0 bg-slate-900/30 backdrop-blur-sm flex items-center justify-center z-50 p-6">
                    <div className="bg-white border border-slate-200 rounded-3xl shadow-2xl max-w-5xl w-full max-h-[90vh] flex flex-col overflow-hidden">
                        <div className="px-8 py-5 border-b border-slate-200 flex items-center justify-between">
                            <div>
                                <h2 className="text-lg font-semibold text-slate-900">Attestation Document</h2>
                                <p className="text-xs text-slate-500">Hardware-backed proof from AWS Nitro Enclave</p>
                            </div>
                            <button
                                onClick={() => setShowAttestation(false)}
                                className="text-slate-400 hover:text-slate-600 text-2xl font-bold"
                                aria-label="Close"
                            >
                                ×
                            </button>
                        </div>

                        <div className="px-8 py-6 overflow-auto flex-1">
                            {attestationLoading ? (
                                <div className="text-center py-12">
                                    <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                                    <p className="mt-4 text-slate-500">Loading attestation...</p>
                                </div>
                            ) : attestationError ? (
                                <div className="py-8">
                                    <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                                        <h3 className="text-red-700 font-semibold mb-2">Failed to fetch attestation</h3>
                                        <p className="text-red-600 text-sm">{attestationError}</p>
                                    </div>
                                </div>
                            ) : attestationData ? (
                                <div className="space-y-4">
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                        <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4">
                                            <p className="text-xs uppercase tracking-widest text-slate-500">Module ID</p>
                                            <p className="mt-2 text-sm text-slate-800 break-all">
                                                {attestationData.attestation_document?.module_id || '—'}
                                            </p>
                                        </div>
                                        <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4">
                                            <p className="text-xs uppercase tracking-widest text-slate-500">Timestamp</p>
                                            <p className="mt-2 text-sm text-slate-800">
                                                {attestationData.attestation_document?.timestamp
                                                    ? new Date(attestationData.attestation_document.timestamp * 1000).toISOString()
                                                    : '—'}
                                            </p>
                                        </div>
                                        <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4">
                                            <p className="text-xs uppercase tracking-widest text-slate-500">PCRs</p>
                                            <p className="mt-2 text-sm text-slate-800">
                                                {attestationData.attestation_document?.pcrs
                                                    ? Object.keys(attestationData.attestation_document.pcrs).length
                                                    : 0} slots
                                            </p>
                                        </div>
                                    </div>

                                    <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 overflow-auto max-h-[50vh]">
                                        <code
                                            className="text-xs text-slate-700 block whitespace-pre-wrap break-words"
                                            dangerouslySetInnerHTML={{
                                                __html: syntaxHighlight(JSON.stringify(attestationData, null, 2)),
                                            }}
                                        />
                                    </div>
                                </div>
                            ) : null}
                        </div>

                        <div className="px-8 py-5 border-t border-slate-200 flex justify-end">
                            <button
                                onClick={() => setShowAttestation(false)}
                                className="px-4 py-2 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200"
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
