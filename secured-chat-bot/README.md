# Secured Chat Bot

A verifiable AI chat application running on the Sparsity Nova TEE platform with end-to-end encryption.

> 📖 **[Development Tutorial](./tutorial.md)** — Step-by-step guide to build and deploy this application.

## Architecture

```mermaid
sequenceDiagram
    participant F as Frontend
    participant E as TEE Enclave
    participant AI as AI Provider
    
    F->>E: GET /.well-known/attestation
    E-->>F: Public Key + Attestation Doc
    Note over F: Verify attestation, derive shared secret (ECDH)
    F->>E: POST /set-api-key (AES-256-GCM encrypted)
    F->>E: POST /talk (encrypted message)
    E->>AI: Proxy to OpenAI
    AI-->>E: Response
    E-->>F: Encrypted + Signed response
```

**Crypto specs:** P-384 ECDH → HKDF-SHA256 → AES-256-GCM

## Features

| Feature              | Description                                     |
|----------------------|-------------------------------------------------|
| **E2E Encryption**   | P-384 ECDH + AES-256-GCM, API keys never exposed |
| **Signed Responses** | EIP-191 signature on every AI response          |
| **Attestation**      | AWS Nitro attestation verifiable in browser     |
| **Multi-Model**      | GPT-5.1, GPT-5, GPT-4.1, GPT-4o, GPT-4          |

## Quick Start

```bash
# Build frontend and copy to enclave
make build-frontend

# Run backend (uses mock Odyn for local dev)
cd enclave && python app.py
```

| Service          | URL                                |
|------------------|------------------------------------|
| Frontend (Dev)   | http://localhost:3000/frontend     |
| Backend API      | http://localhost:8000              |
| Frontend (Built) | http://localhost:8000/frontend     |

## API Endpoints

| Endpoint                   | Method | Description                      |
|----------------------------|--------|----------------------------------|
| `/`                        | GET    | Health check                     |
| `/frontend`                | GET    | Static frontend files            |
| `/set-api-key`             | POST   | Set API key (encrypted)          |
| `/talk`                    | POST   | Chat (encrypted)                 |
| `/.well-known/attestation` | POST   | Get attestation + encryption key |

## Project Structure

```
secured-chat-bot/
├── enclave/           # Python Flask backend (runs in TEE)
│   ├── app.py         # Main service
│   ├── odyn.py        # TEE API wrapper
│   └── frontend/      # Built frontend (ignored by git)
├── frontend/          # Next.js frontend source
├── Dockerfile         # Multi-stage build (builds frontend)
├── enclaver.yaml      # TEE configuration
├── Makefile           # Build automation
└── README.md
```

## Deploy to Nova Platform

See the **[Development Tutorial](./tutorial.md)** for detailed deployment instructions.
