'use client';

import { useState, useRef, useEffect } from 'react';
import { enclaveClient, ChatResponse } from '@/lib/crypto';
import VerificationDialog, { VerificationData } from './VerificationDialog';

interface Message {
    role: 'user' | 'assistant';
    content: string;
    timestamp?: number;
    platform?: string;
    ai_model?: string;
    signature?: string;
    verificationData?: VerificationData;
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
    const [selectedModel, setSelectedModel] = useState('gpt-5.1');
    const [expandedSig, setExpandedSig] = useState<number | null>(null);
    const [verificationDialogOpen, setVerificationDialogOpen] = useState(false);
    const [selectedVerificationData, setSelectedVerificationData] = useState<VerificationData | null>(null);
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

            // Add assistant message with verification data
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: response.response,
                timestamp: response.timestamp,
                platform: response.platform,
                ai_model: response.ai_model,
                signature: response.signature,
                verificationData: {
                    attestation: response.verificationData.attestation,
                    publicKey: response.verificationData.publicKey,
                    ethAddr: response.verificationData.ethAddr,
                    encryptedRequest: response.verificationData.encryptedRequest,
                    decryptedRequest: response.verificationData.decryptedRequest,
                    rawResponse: response.verificationData.rawResponse,
                    encryptedResponse: response.verificationData.encryptedResponse,
                    decryptedResponse: response.verificationData.decryptedResponse,
                    signature: response.signature,
                },
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

    const openVerificationDialog = (data: VerificationData) => {
        setSelectedVerificationData(data);
        setVerificationDialogOpen(true);
    };

    return (
        <>
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
                                    <div className="inline">
                                        <p className="whitespace-pre-wrap inline">{msg.content}</p>
                                        {msg.role === 'assistant' && msg.signature && (
                                            <button
                                                onClick={() => setExpandedSig(expandedSig === index ? null : index)}
                                                className="inline-flex align-middle ml-2 text-primary hover:opacity-80 transition-opacity"
                                                title={expandedSig === index ? 'Hide Details' : 'Show Details'}
                                            >
                                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="h-4 w-4">
                                                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 5.25a3 3 0 0 1 3 3m3 0a6 6 0 0 1-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1 1 21.75 8.25Z" />
                                                </svg>
                                            </button>
                                        )}
                                    </div>

                                    {msg.role === 'assistant' && expandedSig === index && (
                                        <div className="mt-3 pt-3 border-t border-gray-700 space-y-2 text-xs text-gray-400">
                                            <div className="flex justify-between">
                                                <span>Platform:</span>
                                                <span className="text-white">{msg.platform}</span>
                                            </div>
                                            <div className="flex justify-between">
                                                <span>AI Model:</span>
                                                <span className="text-white">{msg.ai_model}</span>
                                            </div>
                                            <div className="flex justify-between">
                                                <span>Timestamp:</span>
                                                <span className="text-white">{formatTimestamp(msg.timestamp)}</span>
                                            </div>
                                            {msg.signature && (
                                                <div>
                                                    <div className="flex justify-between items-center mb-1">
                                                        <span>Verified Signature:</span>
                                                        {msg.verificationData && (
                                                            <button
                                                                onClick={() => openVerificationDialog(msg.verificationData!)}
                                                                className="text-primary hover:opacity-80 transition-opacity"
                                                                title="Full Chain Verification"
                                                            >
                                                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="h-4 w-4">
                                                                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
                                                                </svg>
                                                            </button>
                                                        )}
                                                    </div>
                                                    <div className="p-2 bg-[#0a0a0a] rounded font-mono text-primary break-all">
                                                        {msg.signature}
                                                    </div>
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

            {/* Verification Dialog */}
            <VerificationDialog
                isOpen={verificationDialogOpen}
                onClose={() => setVerificationDialogOpen(false)}
                data={selectedVerificationData}
            />
        </>
    );
}
