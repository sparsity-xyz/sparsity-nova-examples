'use client';

import { useState } from 'react';
import { enclaveClient } from '@/lib/crypto';

interface ApiKeyInputProps {
    isConnected: boolean;
    onApiKeySet: () => void;
}

const PLATFORMS = [
    { id: 'openai', name: 'OpenAI' },
    { id: 'anthropic', name: 'Anthropic' },
    { id: 'gemini', name: 'Google Gemini' },
];

export default function ApiKeyInput({ isConnected, onApiKeySet }: ApiKeyInputProps) {
    const [apiKey, setApiKey] = useState('');
    const [platform, setPlatform] = useState('openai');
    const [showKey, setShowKey] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [isSet, setIsSet] = useState(false);

    const handleSubmit = async () => {
        if (!apiKey.trim()) {
            setError('Please enter an API key');
            return;
        }

        if (!isConnected) {
            setError('Please connect to enclave first');
            return;
        }

        setIsSubmitting(true);
        setError(null);

        try {
            const result = await enclaveClient.setApiKey(apiKey.trim(), platform);
            console.log('API key set result:', result);
            setIsSet(true);
            setApiKey(''); // Clear the input for security
            onApiKeySet();
        } catch (err) {
            console.error('Error setting API key:', err);
            setError(err instanceof Error ? err.message : 'Failed to set API key');
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-6">
            <h2 className="text-xl font-semibold text-white mb-4">
                Set API Key
            </h2>

            {!isConnected ? (
                <p className="text-gray-400">Connect to enclave first to set API key.</p>
            ) : isSet ? (
                <div className="space-y-3">
                    <div className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded-full bg-green-500" />
                        <span className="text-green-400 font-medium">API Key Cached</span>
                    </div>
                    <p className="text-sm text-gray-400">
                        Platform: <span className="text-white">{PLATFORMS.find(p => p.id === platform)?.name}</span>
                    </p>
                    <button
                        onClick={() => setIsSet(false)}
                        className="text-sm text-primary hover:underline"
                    >
                        Update API Key
                    </button>
                </div>
            ) : (
                <div className="space-y-4">
                    <div>
                        <label htmlFor="platform" className="block text-sm font-medium text-gray-300 mb-2">
                            Platform
                        </label>
                        <select
                            id="platform"
                            value={platform}
                            onChange={(e) => setPlatform(e.target.value)}
                            className="w-full px-4 py-3 bg-[#0a0a0a] border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-primary"
                            disabled={isSubmitting}
                        >
                            {PLATFORMS.map((p) => (
                                <option key={p.id} value={p.id}>
                                    {p.name}
                                </option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label htmlFor="apiKey" className="block text-sm font-medium text-gray-300 mb-2">
                            API Key
                        </label>
                        <div className="relative">
                            <input
                                id="apiKey"
                                type={showKey ? 'text' : 'password'}
                                value={apiKey}
                                onChange={(e) => setApiKey(e.target.value)}
                                placeholder="sk-..."
                                className="w-full px-4 py-3 pr-12 bg-[#0a0a0a] border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary"
                                disabled={isSubmitting}
                            />
                            <button
                                type="button"
                                onClick={() => setShowKey(!showKey)}
                                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
                            >
                                {showKey ? '🙈' : '👁️'}
                            </button>
                        </div>
                        <p className="mt-2 text-xs text-gray-500">
                            Your API key is encrypted and sent securely to the enclave.
                        </p>
                    </div>

                    {error && (
                        <div className="p-3 bg-red-900/50 border border-red-800 rounded-lg text-red-400 text-sm">
                            {error}
                        </div>
                    )}

                    <button
                        onClick={handleSubmit}
                        disabled={isSubmitting || !apiKey.trim()}
                        className="w-full py-3 px-4 bg-primary text-black font-medium rounded-lg hover:bg-primary/90 disabled:bg-primary/50 disabled:cursor-not-allowed transition-colors"
                    >
                        {isSubmitting ? (
                            <span className="flex items-center justify-center gap-2">
                                <span className="w-2 h-2 rounded-full bg-black animate-bounce" style={{ animationDelay: '0ms' }} />
                                <span className="w-2 h-2 rounded-full bg-black animate-bounce" style={{ animationDelay: '150ms' }} />
                                <span className="w-2 h-2 rounded-full bg-black animate-bounce" style={{ animationDelay: '300ms' }} />
                            </span>
                        ) : (
                            'Set API Key'
                        )}
                    </button>
                </div>
            )}
        </div>
    );
}
