# AI Chat-bot

This is an AI chatbot service running on the Sparsity Nova Platform using enclaver.

## Features

- Secure AI chat with signed responses
- Support for multiple AI platforms:
  - **OpenAI**: GPT-4, GPT-4-turbo, GPT-3.5-turbo
  - **Anthropic**: Claude 3 Sonnet, Claude 3 Opus
  - **Gemini**: Gemini 2.0 Flash, Gemini 1.5 Pro/Flash
- Attestation document for TEE verification
- Runs inside AWS Nitro Enclave

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    AWS Nitro Enclave                     │
│                                                          │
│  ┌─────────────┐     ┌─────────────┐     ┌───────────┐ │
│  │   app.py    │────▶│  enclave.py │────▶│ odyn API  │ │
│  │  (Flask)    │     │  (wrapper)  │     │ :18000    │ │
│  └──────┬──────┘     └─────────────┘     └───────────┘ │
│         │                                               │
│         ▼                                               │
│  ┌─────────────┐                                        │
│  │  AI Models  │──────▶ OpenAI / Anthropic / Gemini    │
│  └─────────────┘                                        │
└─────────────────────────────────────────────────────────┘
```

## Local Testing

### Requirements
- Python 3.11+
- Access to mock odyn API (for local testing)

### Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your configuration

# Run locally (uses mock odyn API)
python app.py
```

### Test Endpoints

```bash
# Health check
curl http://localhost:8000/

# Ping
curl http://localhost:8000/ping

# Attestation
curl http://localhost:8000/attestation

# Chat (requires API key)
curl -X POST http://localhost:8000/talk \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "your-openai-api-key",
    "message": "Hello!",
    "platform": "openai",
    "ai_model": "gpt-4"
  }'
```

## Deploy on Sparsity Nova Platform

### Build and Deploy

```bash
# Set up environment
cp .env.example .env
# Edit .env with EC2_KEY and EC2_HOST

# Deploy to EC2
make deploy-enclave

# Check status
make status
```

### Available Make Commands

```
make build            - Build Docker image locally
make deploy-enclave   - Deploy enclave to EC2
make get-address      - Get enclave wallet address
make status           - Check enclave status
make attestation      - Get attestation document
make logs             - View enclave logs
make stop             - Stop enclave on EC2
```

## API Reference

### GET /
Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "service": "AI Chatbot",
  "version": "1.0.0",
  "enclave_address": "0x...",
  "supported_platforms": ["openai", "anthropic", "gemini"],
  "endpoints": {...}
}
```

### GET /attestation
Get the TEE attestation document.

**Response:**
```json
{
  "attestation_doc": "..."
}
```

### POST /talk
Send a chat message and receive a signed AI response.

**Request:**
```json
{
  "api_key": "your-api-key",
  "message": "Hello, AI!",
  "platform": "openai",
  "ai_model": "gpt-4"
}
```

**Response:**
```json
{
  "sig": "hex-signature",
  "data": {
    "platform": "openai",
    "ai_model": "gpt-4",
    "timestamp": 1234567890,
    "message": "Hello, AI!",
    "response": "Hello! How can I help you today?"
  }
}
```

## Supported Models

| Platform | Models |
|----------|--------|
| OpenAI | gpt-4, gpt-4-turbo, gpt-3.5-turbo |
| Anthropic | claude-3-7-sonnet-20250219, claude-3-opus-20240229, claude-3-sonnet-20240229 |
| Gemini | gemini-2.0-flash-001, gemini-1.5-pro, gemini-1.5-flash |
