# Chat-bot Rewrite Walkthrough

## Summary

Successfully rewrote the chatbot from `nitro-toolkit/apps/chatbot` to an enclaver-based architecture in `/chat-bot/`, following the patterns established by `price-oracle` and `random-number-generator`.

## Key Changes

### Architecture Shift

| Aspect | Before (nitro-toolkit) | After (enclaver) |
|--------|------------------------|------------------|
| Main dependency | `nitro-toolkit` PyPI package | Direct HTTP calls to odyn API |
| Key management | `FixedKeyManager` class | Odyn API at `localhost:18000` |
| Request/Response | ECDH encrypted | Signed responses |
| Build tool | `nitro-cli build-enclave` | `enclaver build -f enclaver.yaml` |
| Network config | ENV vars + VSOCK | `enclaver.yaml` ingress/egress |

### Simplified API

The new implementation uses **signing instead of encryption**:
- Requests are sent in plain JSON
- Responses include a signature in the `sig` field
- Attestation document available at `/attestation`

---

## Created Files

### Core Application

| File | Description |
|------|-------------|
| [app.py](file:///Users/zfdang/workspaces/sparsity-nova-examples/chat-bot/app.py) | Main Flask application with endpoints |
| [enclave.py](file:///Users/zfdang/workspaces/sparsity-nova-examples/chat-bot/enclave.py) | Wrapper for enclaver's odyn API |

### AI Models

| File | Description |
|------|-------------|
| [ai_models/platform.py](file:///Users/zfdang/workspaces/sparsity-nova-examples/chat-bot/ai_models/platform.py) | Base Platform ABC class |
| [ai_models/open_ai.py](file:///Users/zfdang/workspaces/sparsity-nova-examples/chat-bot/ai_models/open_ai.py) | OpenAI integration |
| [ai_models/anthropic.py](file:///Users/zfdang/workspaces/sparsity-nova-examples/chat-bot/ai_models/anthropic.py) | Anthropic/Claude integration |
| [ai_models/gemini.py](file:///Users/zfdang/workspaces/sparsity-nova-examples/chat-bot/ai_models/gemini.py) | Google Gemini integration |

### Configuration & Build

| File | Description |
|------|-------------|
| [enclaver.yaml](file:///Users/zfdang/workspaces/sparsity-nova-examples/chat-bot/enclaver.yaml) | Enclaver configuration with egress rules |
| [Dockerfile](file:///Users/zfdang/workspaces/sparsity-nova-examples/chat-bot/Dockerfile) | Container image definition |
| [Makefile](file:///Users/zfdang/workspaces/sparsity-nova-examples/chat-bot/Makefile) | Build and deployment automation |
| [requirements.txt](file:///Users/zfdang/workspaces/sparsity-nova-examples/chat-bot/requirements.txt) | Python dependencies |
| [.env.example](file:///Users/zfdang/workspaces/sparsity-nova-examples/chat-bot/.env.example) | Example environment configuration |
| [README.md](file:///Users/zfdang/workspaces/sparsity-nova-examples/chat-bot/README.md) | Documentation |

---

## API Endpoints

### GET /
Health check with service info and enclave address.

### GET /ping
Simple ping/pong endpoint.

### GET /attestation
Returns the TEE attestation document.

### POST /talk
Main chat endpoint. Example:

```bash
curl -X POST http://localhost:8000/talk \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "sk-...",
    "message": "Hello!",
    "platform": "openai",
    "ai_model": "gpt-4"
  }'
```

Response:
```json
{
  "sig": "0x...",
  "data": {
    "platform": "openai",
    "ai_model": "gpt-4",
    "timestamp": 1733720959,
    "message": "Hello!",
    "response": "Hello! How can I help you today?"
  }
}
```

---

## Deployment

### Build and Deploy to EC2

```bash
cd chat-bot
cp .env.example .env
# Edit .env with EC2_KEY and EC2_HOST

make deploy-enclave
make status
```

### Makefile Commands

- `make build` - Build Docker image locally
- `make deploy-enclave` - Deploy to EC2 with enclaver
- `make status` - Check service status
- `make attestation` - Get attestation document
- `make logs` - View logs
- `make stop` - Stop the enclave

---

## Directory Structure

```
chat-bot/
├── ai_models/
│   ├── __init__.py
│   ├── anthropic.py
│   ├── gemini.py
│   ├── open_ai.py
│   └── platform.py
├── app.py
├── enclave.py
├── Dockerfile
├── enclaver.yaml
├── Makefile
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Next Steps

1. **Frontend Integration**: Update `agents.sparsity.ai/api-server/.env` with the new chatbot URL
2. **Update Frontend Client**: The frontend may need updates since we switched from encrypted to signed responses
3. **Deploy and Test**: Deploy to EC2 using `make deploy-enclave` and verify with `make status`
