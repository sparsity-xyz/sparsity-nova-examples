# Coin Price Bot

A TEE-based service for fetching and analyzing cryptocurrency prices using AI, running on **Sparsity Nova Platform**.

> **🚀 Easy Deployment**: Deploy to Nova via [nova.sparsity.xyz](https://nova.sparsity.xyz)  
> **🌐 Web Interface**: Interact via [agents.sparsity.ai](https://agents.sparsity.ai)

## Features

- Secure AI-powered price queries with signed responses
- TEE-to-TEE communication with chat-bot for AI inference
- Automatic URL discovery and content summarization
- End-to-end encrypted communication

## Workflow

1. User sends a query (e.g., "What is the current price of Bitcoin?")
2. Coin-price-bot asks chat-bot TEE to find relevant URLs
3. Coin-price-bot fetches and cleans HTML from each URL
4. For each URL, chat-bot TEE summarizes the content
5. Chat-bot TEE creates a final summary combining all sources
6. Response is signed and returned to user

## Build app image and run

Build the app image with:

```bash
docker build -t coin-price-bot .
```

Verify the app image with:

```bash
docker images coin-price-bot
```

You can run the app image directly with:

```bash
docker run --rm -p 8000:8000 coin-price-bot
curl http://localhost:8000
```

## Build the enclaver image

The content of `enclaver.yaml` is:

```yaml
version: v1
name: "coin-price-bot"
target: "coin-price-bot-enclave:latest"
sources:
  app: "coin-price-bot:latest"
defaults:
  memory_mb: 2048
ingress:
  - listen_port: 8000
egress:
  allow:
    - "*"
api:
  listen_port: 18000
aux_api:
  listen_port: 18001
```

The manifest includes:
- `ingress` - Allows external HTTP traffic on port 8000
- `egress` - Allows outbound requests (to fetch web content and communicate with chat-bot TEE)
- `api` - Enables the internal API service on port 18000 (provides attestation and key management)
- `aux_api` - Enables the auxiliary API on port 18001

Build the enclaver image with:

```bash
enclaver build -f enclaver.yaml
```

Verify the enclave image with:

```bash
docker images coin-price-bot-enclave
```

## Run enclaver image

Run the enclave image with:

```bash
enclaver run --publish 8000:8000 --publish 18001:18001 coin-price-bot-enclave:latest
```

Test the application:

```bash
curl http://localhost:8000
```

## API Reference

### GET /
Health check endpoint.

### GET /ping
Simple ping endpoint.

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
      "attestation_endpoint": "https://chat-bot-endpoint/attestation",
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

## Deploy on Sparsity Nova Platform

This bot is designed to be deployed via the **Nova UI**:

1. Go to [nova.sparsity.xyz](https://nova.sparsity.xyz)
2. Connect your wallet
3. Select "Deploy New Agent"
4. Choose the coin-price-bot image or provide the Docker image
5. Configure resources and deploy

Once deployed, the bot will be accessible via [agents.sparsity.ai](https://agents.sparsity.ai).
