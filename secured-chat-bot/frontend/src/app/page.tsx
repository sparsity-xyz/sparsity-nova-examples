'use client';

import { useState } from 'react';
import EnclaveConfig from '@/components/EnclaveConfig';
import ApiKeyInput from '@/components/ApiKeyInput';
import Chat from '@/components/Chat';

export default function Home() {
    const [isConnected, setIsConnected] = useState(false);
    const [isApiKeySet, setIsApiKeySet] = useState(false);
    const [enclaveAddress, setEnclaveAddress] = useState<string | null>(null);

    const handleConnected = (address: string) => {
        setIsConnected(true);
        setEnclaveAddress(address);
    };

    const handleApiKeySet = () => {
        setIsApiKeySet(true);
    };

    const isReady = isConnected && isApiKeySet;

    return (
        <div className="min-h-screen bg-[#0a0a0a]">
            {/* Header */}
            <header className="border-b border-gray-800 px-6 py-4">
                <div className="max-w-7xl mx-auto flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center">
                            <span className="text-white font-bold">N</span>
                        </div>
                        <div>
                            <h1 className="text-xl font-bold text-white">Fully Secured Chat Bot</h1>
                            <p className="text-sm text-gray-400">Sparsity Nova Platform</p>
                        </div>
                    </div>

                    <div className="flex items-center gap-4">
                        {isConnected && (
                            <div className="flex items-center gap-2 text-sm">
                                <div className={`w-2 h-2 rounded-full ${isApiKeySet ? 'bg-green-500' : 'bg-yellow-500'}`} />
                                <span className="text-gray-400">
                                    {isApiKeySet ? 'Ready' : 'API Key Required'}
                                </span>
                            </div>
                        )}
                    </div>
                </div>
            </header>

            {/* Main Content */}
            <main className="max-w-7xl mx-auto p-6">
                {!isReady ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl mx-auto">
                        <EnclaveConfig onConnected={handleConnected} />
                        <ApiKeyInput isConnected={isConnected} onApiKeySet={handleApiKeySet} />
                    </div>
                ) : (
                    <div className="h-[calc(100vh-10rem)] bg-[#111] rounded-lg border border-gray-800">
                        <Chat isReady={isReady} />
                    </div>
                )}
            </main>

            {/* Footer */}
            <footer className="fixed bottom-0 left-0 right-0 border-t border-gray-800 bg-[#0a0a0a] px-6 py-3">
                <div className="max-w-7xl mx-auto flex items-center justify-between text-sm text-gray-500">
                    <span>End-to-end encrypted • Verifiable AI responses</span>
                    {enclaveAddress && (
                        <span className="font-mono text-xs text-gray-600">
                            Enclave: {enclaveAddress.slice(0, 10)}...{enclaveAddress.slice(-8)}
                        </span>
                    )}
                </div>
            </footer>
        </div>
    );
}
