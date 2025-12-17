'use client';

import { useState, useRef, useEffect } from 'react';
import { enclaveClient, ChatResponse } from '@/lib/crypto';

interface Message {
    role: 'user' | 'assistant';
    content: string;
    timestamp?: number;
    platform?: string;
    ai_model?: string;
    signature?: string;
}

interface ChatProps {
    isReady: boolean;
}

const AI_MODELS = [
    { id: 'gpt-5.1', name: 'GPT-5.1' },
    { id: 'gpt-5', name: 'GPT-5' },
    { id: 'gpt-5-mini', name: 'GPT-5 Mini' },
    { id: 'gpt-4.1', name: 'GPT-4.1' },
    { id: 'gpt-4.1-mini', name: 'GPT-4.1 Mini' },
    { id: 'gpt-4o', name: 'GPT-4o' },
    { id: 'gpt-4o-mini', name: 'GPT-4o Mini' },
    { id: 'gpt-4', name: 'GPT-4' },
];

export default function Chat({ isReady }: ChatProps) {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [selectedModel, setSelectedModel] = useState('gpt-4');
    const [expandedSig, setExpandedSig] = useState<number | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || !isReady || isLoading) return;

        const userMessage = input.trim();
        setInput('');
        setError(null);

        // Add user message
        setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
        setIsLoading(true);

        try {
            const response = await enclaveClient.chat(userMessage, selectedModel);

            // Add assistant message
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: response.response,
                timestamp: response.timestamp,
                platform: response.platform,
                ai_model: response.ai_model,
                signature: (response as any).signature,
            }]);
        } catch (err) {
            console.error('Chat error:', err);
            setError(err instanceof Error ? err.message : 'Failed to send message');
        } finally {
            setIsLoading(false);
        }
    };

    const formatTimestamp = (timestamp?: number) => {
        if (!timestamp) return 'Unknown';
        const date = new Date(timestamp * 1000);
        return date.toLocaleString();
    };

    return (
        <div className="flex flex-col h-full">
            {/* Model Selector */}
            <div className="flex items-center gap-4 p-4 border-b border-gray-800">
                <label className="text-sm text-gray-400">Model:</label>
                <select
                    value={selectedModel}
                    onChange={(e) => setSelectedModel(e.target.value)}
                    className="px-3 py-2 bg-[#0a0a0a] border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-primary"
                    disabled={!isReady}
                >
                    {AI_MODELS.map((model) => (
                        <option key={model.id} value={model.id}>
                            {model.name}
                        </option>
                    ))}
                </select>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.length === 0 ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="text-center text-gray-500 max-w-md">
                            <h3 className="text-xl font-semibold text-white mb-2">
                                Start a Conversation
                            </h3>
                            <p className="text-sm">
                                Your messages are encrypted end-to-end. The enclave signs every response for verification.
                            </p>
                        </div>
                    </div>
                ) : (
                    messages.map((msg, index) => (
                        <div
                            key={index}
                            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                        >
                            <div
                                className={`max-w-[80%] p-4 rounded-lg ${msg.role === 'user'
                                        ? 'bg-primary/20 text-white'
                                        : 'bg-[#1a1a1a] border border-gray-800'
                                    }`}
                            >
                                <p className="whitespace-pre-wrap">{msg.content}</p>

                                {msg.role === 'assistant' && (
                                    <div className="mt-3 pt-3 border-t border-gray-700">
                                        <div className="flex items-center justify-between text-xs text-gray-400">
                                            <div className="flex items-center gap-4">
                                                <span>Platform: {msg.platform}</span>
                                                <span>Model: {msg.ai_model}</span>
                                                <span>{formatTimestamp(msg.timestamp)}</span>
                                            </div>
                                            {msg.signature && (
                                                <button
                                                    onClick={() => setExpandedSig(expandedSig === index ? null : index)}
                                                    className="text-primary hover:underline"
                                                >
                                                    {expandedSig === index ? 'Hide' : 'Show'} Signature
                                                </button>
                                            )}
                                        </div>

                                        {expandedSig === index && msg.signature && (
                                            <div className="mt-2 p-2 bg-[#0a0a0a] rounded text-xs font-mono text-primary break-all">
                                                {msg.signature}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                    ))
                )}

                {isLoading && (
                    <div className="flex justify-start">
                        <div className="max-w-[80%] p-4 rounded-lg bg-[#1a1a1a] border border-gray-800">
                            <div className="flex items-center gap-2">
                                <span className="w-2 h-2 rounded-full bg-primary animate-bounce" style={{ animationDelay: '0ms' }} />
                                <span className="w-2 h-2 rounded-full bg-primary animate-bounce" style={{ animationDelay: '150ms' }} />
                                <span className="w-2 h-2 rounded-full bg-primary animate-bounce" style={{ animationDelay: '300ms' }} />
                            </div>
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Error */}
            {error && (
                <div className="mx-4 mb-2 p-3 bg-red-900/50 border border-red-800 rounded-lg text-red-400 text-sm">
                    {error}
                </div>
            )}

            {/* Input */}
            <form onSubmit={handleSubmit} className="p-4 border-t border-gray-800">
                <div className="flex gap-2">
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder={isReady ? 'Type your message...' : 'Connect and set API key first...'}
                        className="flex-1 px-4 py-3 bg-[#0a0a0a] border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary"
                        disabled={!isReady || isLoading}
                    />
                    <button
                        type="submit"
                        disabled={!isReady || isLoading || !input.trim()}
                        className="px-6 py-3 bg-primary text-black font-medium rounded-lg hover:bg-primary/90 disabled:bg-primary/50 disabled:cursor-not-allowed transition-colors"
                    >
                        Send
                    </button>
                </div>
            </form>
        </div>
    );
}
