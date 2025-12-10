# AI Chat-bot

A secure AI chatbot running on **Sparsity Nova Platform** inside an AWS Nitro Enclave.

> **🚀 Easy Deployment**: Deploy to Nova via [nova.sparsity.xyz](https://nova.sparsity.xyz)  
> **🌐 Web Interface**: Interact via [agents.sparsity.ai](https://agents.sparsity.ai)

## Features

- Secure AI chat with signed responses
- Support for multiple AI platforms:
  - **OpenAI**: GPT-5.1, GPT-5, GPT-4.1, GPT-4o, GPT-4
  - **Anthropic**: Claude 3 Sonnet, Claude 3 Opus
  - **Gemini**: Gemini 2.0 Flash, Gemini 1.5 Pro/Flash
- Attestation document for TEE verification
- End-to-end encrypted communication

## Build app image and run

Build the app image with:

```bash
docker build -t chat-bot .
```

Verify the app image with:

```bash
docker images chat-bot
```

You can run the app image directly with:

```bash
docker run --rm -p 8000:8000 chat-bot
curl http://localhost:8000
```

## Build the enclaver image

The content of `enclaver.yaml` is:

```yaml
version: v1
name: "chat-bot"
target: "chat-bot-enclave:latest"
sources:
  app: "chat-bot:latest"
defaults:
  memory_mb: 2048
ingress:
  - listen_port: 8000
egress:
  allow:
    - "api.openai.com"
    - "api.anthropic.com"
    - "generativelanguage.googleapis.com"
api:
  listen_port: 18000
aux_api:
  listen_port: 18001
```

The manifest includes:
- `ingress` - Allows external HTTP traffic on port 8000
- `egress` - Allows outbound requests to AI provider APIs
- `api` - Enables the internal API service on port 18000 (provides attestation and key management)
- `aux_api` - Enables the auxiliary API on port 18001

Build the enclaver image with:

```bash
enclaver build -f enclaver.yaml
```

Verify the enclave image with:

```bash
docker images chat-bot-enclave
```

## Run enclaver image

Run the enclave image with:

```bash
enclaver run --publish 8000:8000 --publish 18001:18001 chat-bot-enclave:latest
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
| OpenAI | gpt-5.1, gpt-5, gpt-5-mini, gpt-4.1, gpt-4.1-mini, gpt-4o, gpt-4o-mini, gpt-4 |
| Anthropic | claude-3-7-sonnet-20250219, claude-3-opus-20240229, claude-3-sonnet-20240229 |
| Gemini | gemini-2.0-flash-001, gemini-1.5-pro, gemini-1.5-flash |

## Deploy on Sparsity Nova Platform

This bot is designed to be deployed via the **Nova UI**:

1. Go to [nova.sparsity.xyz](https://nova.sparsity.xyz)
2. Connect your wallet
3. Select "Deploy New Agent"
4. Choose the chat-bot image or provide the Docker image
5. Configure resources and deploy

Once deployed, the bot will be accessible via [agents.sparsity.ai](https://agents.sparsity.ai).
