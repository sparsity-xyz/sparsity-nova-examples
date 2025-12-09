# Coin Price Bot

A TEE-based service for fetching and analyzing cryptocurrency prices using AI.

## Features

- Secure AI-powered price queries with signed responses
- TEE-to-TEE communication with chat-bot for AI inference
- Automatic URL discovery and content summarization
- Runs inside AWS Nitro Enclave

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         AWS Nitro Enclave                             │
│                                                                       │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────────────┐│
│  │   app.py    │────▶│ tee_client  │────▶│ chat-bot TEE            ││
│  │  (Flask)    │     │  (client)   │     │ (vmi.sparsity.ai)       ││
│  └──────┬──────┘     └─────────────┘     └─────────────────────────┘│
│         │                                                            │
│         ▼                                                            │
│  ┌─────────────┐     ┌─────────────┐                                │
│  │  utils.py   │────▶│ Web URLs    │                                │
│  │  (fetch)    │     │ (HTML)      │                                │
│  └─────────────┘     └─────────────┘                                │
│         │                                                            │
│         ▼                                                            │
│  ┌─────────────┐     ┌─────────────┐                                │
│  │  enclave.py │────▶│ odyn API    │                                │
│  │  (wrapper)  │     │ :18000      │                                │
│  └─────────────┘     └─────────────┘                                │
└──────────────────────────────────────────────────────────────────────┘
```

## Workflow

1. User sends a query (e.g., "What is the current price of Bitcoin?")
2. Coin-price-bot asks chat-bot TEE to find relevant URLs
3. Coin-price-bot fetches and cleans HTML from each URL
4. For each URL, chat-bot TEE summarizes the content
5. Chat-bot TEE creates a final summary combining all sources
6. Response is signed and returned to user

## Local Testing

### Requirements
- Python 3.11+
- Access to mock odyn API
- Access to chat-bot TEE endpoint

### Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your configuration

# Run locally
python app.py
```

### Test Endpoints

```bash
# Health check
curl http://localhost:8000/

# Ping
curl http://localhost:8000/ping

# Test network access
curl http://localhost:8000/query

# Query coin prices (requires API key)
curl -X POST http://localhost:8000/talk \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "your-openai-api-key",
    "message": "What is the current price of Bitcoin?",
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
make test-query       - Test network access
make test-talk        - Test coin price query
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
  "service": "Coin Price Bot",
  "version": "1.0.0",
  "enclave_address": "0x...",
  "chat_bot_endpoint": "https://vmi.sparsity.ai/chat_bot",
  "endpoints": {...}
}
```

### GET /attestation
Get the TEE attestation document.

### POST /talk
Query coin prices and get AI-powered analysis.

**Request:**
```json
{
  "api_key": "your-api-key",
  "message": "What is the current price of Bitcoin?",
  "platform": "openai",
  "ai_model": "gpt-4"
}
```

**Response:**
```json
{
  "sig": "hex-signature",
  "data": [
    {
      "description": "urls to resolve query",
      "attestation_endpoint": "https://vmi.sparsity.ai/chat_bot/attestation",
      "sig": "...",
      "data": {...}
    },
    {
      "description": "summaries for the url content",
      "attestation_endpoint": "...",
      "sig": "...",
      "data": {...}
    },
    {
      "description": "final summary combining all url content summaries",
      "attestation_endpoint": "...",
      "sig": "...",
      "data": {...}
    }
  ]
}
```

## Dependencies

This service depends on:
- **chat-bot TEE**: For AI inference (URL discovery and content summarization)
- **odyn API**: For attestation and signing (provided by enclaver)
