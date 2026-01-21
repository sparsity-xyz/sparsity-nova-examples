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

    return (
        <div className="min-h-screen bg-slate-900 text-slate-100 p-8 font-sans">
            <header className="max-w-6xl mx-auto mb-12 flex justify-between items-center">
                <div>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-emerald-400 bg-clip-text text-transparent">
                        🛡️ Nova App Template
                    </h1>
                    <p className="text-slate-400 mt-2">Production-Ready TEE Application Demo</p>
                </div>

                <div className="bg-slate-800 p-1 rounded-lg border border-slate-700 flex gap-4 items-center">
                    <input
                        className="bg-transparent px-3 py-1 outline-none text-sm w-64"
                        value={status.enclaveUrl}
                        onChange={(e) => setStatus({ ...status, enclaveUrl: e.target.value })}
                        placeholder="Enclave URL"
                    />
                    <button
                        onClick={handleConnect}
                        disabled={loading || status.connected}
                        className={`px-4 py-1.5 rounded-md text-sm font-semibold transition ${status.connected
                            ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                            : 'bg-blue-600 hover:bg-blue-500 text-white'
                            }`}
                    >
                        {loading ? 'Connecting...' : status.connected ? '✓ Connected' : 'Connect'}
                    </button>
                </div>
            </header>

            <main className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Left: Navigation & Info */}
                <div className="lg:col-span-1 space-y-6">
                    <section className="bg-slate-800 rounded-xl border border-slate-700 p-6">
                        <h2 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-4">Capabilities</h2>
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
                                    className={`flex items-center gap-3 px-4 py-3 rounded-lg transition text-left ${activeTab === tab.id
                                        ? 'bg-slate-700 text-white border border-slate-600'
                                        : 'text-slate-400 hover:bg-slate-700/50'
                                        }`}
                                >
                                    <span>{tab.icon}</span>
                                    <span className="font-medium">{tab.label}</span>
                                </button>
                            ))}
                        </nav>
                    </section>

                    {status.connected && (
                        <section className="bg-emerald-500/5 rounded-xl border border-emerald-500/20 p-6">
                            <h2 className="text-sm font-bold text-emerald-500 uppercase tracking-wider mb-3">Enclave Identity</h2>
                            <div className="space-y-4">
                                <div>
                                    <label className="text-xs text-slate-500 block mb-1">TEE Wallet Address</label>
                                    <code className="text-xs bg-slate-900 px-2 py-1 rounded block truncate border border-slate-700">
                                        {status.teeAddress}
                                    </code>
                                </div>
                                <div className="flex gap-2 text-xs">
                                    <span className="bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded border border-emerald-500/20">Active</span>
                                    <span className="bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded border border-blue-500/20">Verifiable</span>
                                </div>
                            </div>
                        </section>
                    )}
                </div>

                {/* Right: Content Area */}
                <div className="lg:col-span-2 space-y-6">
                    <div className="bg-slate-800 rounded-2xl border border-slate-700 p-8 min-h-[400px]">
                        {activeTab === 'identity' && (
                            <div className="space-y-6">
                                <h2 className="text-xl font-bold mb-4">Identity & RA-TLS</h2>
                                <p className="text-slate-400 text-sm leading-relaxed mb-6">
                                    Establish a secure, hardware-verifiable channel with the enclave using AWS Nitro Attestation
                                    and ECDH key exchange.
                                </p>

                                <div className="space-y-4">
                                    <div className="flex flex-col gap-2">
                                        <label className="text-sm text-slate-300">Message to Echo</label>
                                        <div className="flex gap-2">
                                            <input
                                                className="bg-slate-900 border border-slate-700 rounded-lg px-4 py-2 flex-1 outline-none focus:border-blue-500 transition"
                                                value={echoMsg}
                                                onChange={(e) => setEchoMsg(e.target.value)}
                                            />
                                            <button
                                                onClick={() => callApi('/api/echo', 'POST', { message: echoMsg }, true)}
                                                disabled={loading || !status.connected}
                                                className="bg-blue-600 hover:bg-blue-500 text-white px-6 py-2 rounded-lg font-semibold disabled:opacity-50"
                                            >
                                                Encrypted Send
                                            </button>
                                        </div>
                                    </div>
                                    <div className="flex gap-4">
                                        <button
                                            onClick={() => callApi('/api/attestation', 'GET')}
                                            disabled={loading || !status.connected}
                                            className="text-sm text-blue-400 hover:text-blue-300 font-medium"
                                        >
                                            View Attestation Document →
                                        </button>
                                        <button
                                            onClick={() => callApi('/api/random', 'GET')}
                                            disabled={loading || !status.connected}
                                            className="text-sm text-emerald-400 hover:text-emerald-300 font-medium"
                                        >
                                            Fetch Hardware Entropy (NSM) →
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )}

                        {activeTab === 'storage' && (
                            <div className="space-y-6">
                                <h2 className="text-xl font-bold mb-4">S3 Persistent Storage</h2>
                                <p className="text-slate-400 text-sm leading-relaxed mb-6">
                                    Store and retrieve sensitive state in encrypted S3 objects. Access is restricted to
                                    this specific TEE instance.
                                </p>

                                <div className="grid grid-cols-2 gap-4">
                                    <div className="flex flex-col gap-2 col-span-1">
                                        <label className="text-sm text-slate-300">Key</label>
                                        <input
                                            className="bg-slate-900 border border-slate-700 rounded-lg px-4 py-2 outline-none focus:border-blue-500"
                                            value={storageKey}
                                            onChange={(e) => setStorageKey(e.target.value)}
                                        />
                                    </div>
                                    <div className="flex flex-col gap-2 col-span-1">
                                        <label className="text-sm text-slate-300">Value (JSON/Text)</label>
                                        <input
                                            className="bg-slate-900 border border-slate-700 rounded-lg px-4 py-2 outline-none focus:border-emerald-500"
                                            value={storageVal}
                                            onChange={(e) => setStorageVal(e.target.value)}
                                        />
                                    </div>
                                </div>
                                <div className="flex gap-3">
                                    <button
                                        onClick={() => callApi('/api/storage', 'POST', { key: storageKey, value: storageVal })}
                                        disabled={loading || !status.connected}
                                        className="bg-emerald-600 hover:bg-emerald-500 text-white px-6 py-2 rounded-lg font-semibold flex-1"
                                    >
                                        Store Value
                                    </button>
                                    <button
                                        onClick={() => callApi(`/api/storage/${storageKey}`, 'GET')}
                                        disabled={loading || !status.connected}
                                        className="bg-slate-700 hover:bg-slate-600 px-6 py-2 rounded-lg font-semibold flex-1"
                                    >
                                        Retrieve Key
                                    </button>
                                </div>
                                <button
                                    onClick={() => callApi('/api/storage', 'GET')}
                                    className="text-sm text-slate-500 hover:text-slate-300"
                                >
                                    List all stored keys...
                                </button>
                            </div>
                        )}

                        {activeTab === 'oracle' && (
                            <div className="space-y-6">
                                <h2 className="text-xl font-bold mb-4">Oracle: Internet → Chain</h2>
                                <p className="text-slate-400 text-sm leading-relaxed mb-6">
                                    The enclave fetches real-time data from the internet, processes it, and signs a
                                    cryptographically secure transaction for on-chain execution.
                                </p>

                                <div className="bg-slate-900/50 border border-slate-700 rounded-xl p-6 flex flex-col items-center justify-center gap-6">
                                    <div className="text-center">
                                        <div className="text-4xl mb-2">💎</div>
                                        <div className="text-2xl font-mono text-white tracking-tight">ETH / USD</div>
                                    </div>
                                    <button
                                        onClick={() => callApi('/api/oracle/price', 'GET')}
                                        disabled={loading || !status.connected}
                                        className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white px-8 py-3 rounded-xl font-bold shadow-lg shadow-blue-900/20"
                                    >
                                        Fetch & Sign Update
                                    </button>
                                </div>
                            </div>
                        )}

                        {activeTab === 'events' && (
                            <div className="space-y-6">
                                <h2 className="text-xl font-bold mb-4">On-Chain Event Monitor</h2>
                                <p className="text-slate-400 text-sm leading-relaxed mb-6">
                                    Background workers in the enclave monitor blockchain events and respond automatically.
                                    The state hash is updated periodically to ensure data integrity.
                                </p>

                                <div className="space-y-4">
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="bg-slate-900 p-4 rounded-xl border border-slate-700">
                                            <label className="text-xs text-slate-500 block mb-1">Last Cron Run</label>
                                            <span className="text-sm font-mono text-emerald-400 italic">
                                                {status.connected && response?.data?.cron_info?.last_run
                                                    ? new Date(response.data.cron_info.last_run).toLocaleTimeString()
                                                    : 'Awaiting sync...'}
                                            </span>
                                        </div>
                                        <div className="bg-slate-900 p-4 rounded-xl border border-slate-700">
                                            <label className="text-xs text-slate-500 block mb-1">State Hash (SHA256)</label>
                                            <span className="text-sm font-mono text-blue-400 italic truncate block">
                                                {status.connected && response?.data?.last_state_hash
                                                    ? `0x${response.data.last_state_hash.slice(0, 16)}...`
                                                    : 'Awaiting sync...'}
                                            </span>
                                        </div>
                                    </div>
                                    <div className="bg-slate-900 p-4 rounded-xl border border-slate-700">
                                        <label className="text-xs text-slate-500 block mb-1">Background Runner Status</label>
                                        <div className="flex items-center gap-2">
                                            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                                            <span className="text-xs text-slate-300">
                                                Worker active • {response?.data?.cron_info?.counter || 0} tasks completed
                                            </span>
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => callApi('/status', 'GET')}
                                        disabled={loading || !status.connected}
                                        className="w-full py-3 border border-slate-700 rounded-xl text-sm font-medium hover:bg-slate-700 transition"
                                    >
                                        Refresh Background Job Stats
                                    </button>
                                </div>
                            </div>
                        )}

                        {/* Universal Response Viewer */}
                        {response && (
                            <div className="mt-8 border-t border-slate-700 pt-8 animate-in fade-in slide-in-from-top-4 duration-300">
                                <div className="flex justify-between items-center mb-3">
                                    <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest">
                                        Latest Response: {response.type}
                                    </h3>
                                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${response.success ? 'bg-emerald-500/10 text-emerald-500' : 'bg-red-500/10 text-red-500'}`}>
                                        {response.success ? 'SUCCESS' : 'FAILED'}
                                    </span>
                                </div>
                                <pre className="bg-slate-900 rounded-xl p-5 text-xs font-mono text-blue-300 overflow-auto max-h-[300px] border border-slate-700 whitespace-pre-wrap">
                                    {JSON.stringify(response.data || response.error, null, 2)}
                                </pre>
                            </div>
                        )}
                    </div>
                </div>
            </main>

            <footer className="max-w-6xl mx-auto mt-12 text-center text-slate-500 text-sm">
                Built with <span className="text-blue-400 font-semibold">Nova Platform</span> • Powered by AWS Nitro Enclaves
            </footer>
        </div>
    );
}
