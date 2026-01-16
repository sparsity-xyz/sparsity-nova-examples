# Nova App Template

A production-ready template for building verified TEE applications on the Nova platform.

## Project Structure

```
nova-app-template/
├── enclave/                 # Python FastAPI application (runs in TEE)
│   ├── app.py              # Main application entry point
│   ├── routes.py           # Your custom API endpoints
│   ├── tasks.py            # Background jobs / cron tasks
│   ├── odyn.py             # Odyn SDK for TEE services
│   ├── requirements.txt    # Python dependencies
│   ├── Dockerfile          # Enclave container image
│   └── frontend-dist/      # Built frontend (auto-generated)
├── frontend/               # React/Next.js frontend with RA-TLS
│   ├── src/
│   │   ├── app/            # Next.js app pages
│   │   └── lib/            # RA-TLS crypto utilities
│   │       ├── attestation.ts  # AWS Nitro attestation parser
│   │       └── crypto.ts       # ECDH + AES-GCM encryption
│   └── package.json        # Node.js dependencies
├── contracts/              # Solidity smart contracts
│   ├── src/
│   │   └── NovaAppBase.sol # State management contract
│   ├── script/
│   │   └── Deploy.s.sol    # Deployment script
│   └── foundry.toml        # Foundry configuration
├── enclaver.yaml           # Enclave configuration
├── Makefile                # Build commands
└── README.md               # This file
```

## Quick Start

### Prerequisites

- Node.js 18+
- Python 3.11+
- Foundry (for contract deployment)
- Nova Platform account

### 1. Build the Frontend

```bash
# Build frontend and copy to enclave
make build-frontend
```

This will:
- Install npm dependencies
- Build the Next.js static site (with basePath `/frontend`)
- Copy the output to `enclave/frontend-dist/`

### 2. Run Locally (Development)

```bash
# Terminal 1: Start enclave backend
make dev-enclave

# Terminal 2: Start frontend dev server (optional, for hot reload)
make dev-frontend
```

The enclave will serve:
- API endpoints at `http://localhost:5000/api/*`
- Frontend at `http://localhost:5000/frontend/`

### 3. Build Docker Image

```bash
make docker-build
make docker-run
```

### 4. Deploy to Nova Platform

1. Push your container to the Nova registry
2. Submit a build request with `enclaver.yaml`
3. Register your TEE wallet address with the deployed contract

After deployment, access your app at:
- **Frontend UI**: `https://your-app.app.sparsity.cloud/frontend/`
- **API**: `https://your-app.app.sparsity.cloud/api/*`

## Frontend (RA-TLS Client)

The frontend includes a secure RA-TLS client for encrypted communication with the TEE.

### Basic Usage

```typescript
import { EnclaveClient } from '@/lib/crypto';

const client = new EnclaveClient();

// 1. Connect to enclave (fetches attestation, establishes ECDH)
await client.connect('https://your-app.app.sparsity.cloud');

// 2. Call API endpoints
const response = await client.call('/api/echo', 'POST', { 
    message: 'Hello from TEE!' 
});

// 3. For encrypted communication (optional)
const encrypted = await client.callEncrypted('/api/secure', { 
    secret: 'sensitive data' 
});
```

### Key Features

| Feature | Description |
|---------|-------------|
| **ECDH Key Exchange** | Establishes shared secret with TEE's ephemeral public key |
| **AES-256-GCM Encryption** | All sensitive data encrypted end-to-end |
| **Attestation Verification** | Parses AWS Nitro COSE Sign1 attestation documents |
| **Dual Curve Support** | P-384 (Odyn standard) and secp256k1 (ETH signing) |

### Attestation Parsing

```typescript
import { fetchAttestation, decodeAttestationDoc } from '@/lib/attestation';

// Fetch and parse attestation
const attestation = await fetchAttestation('https://your-app.app.sparsity.cloud');

console.log(attestation.attestation_document.pcrs);     // PCR values
console.log(attestation.attestation_document.user_data); // ETH address
console.log(attestation.attestation_document.timestamp); // Timestamp
```

## Backend (Enclave)

### Adding Custom Endpoints

Edit `enclave/routes.py`:

```python
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["user"])

class MyRequest(BaseModel):
    data: str

@router.post("/my-endpoint")
def my_endpoint(req: MyRequest):
    """Your custom logic here."""
    # Access app state
    value = app_state["data"].get("key")
    
    # Use Odyn SDK
    address = odyn.eth_address()
    signature = odyn.sign_message(req.data.encode())
    
    return {"result": "success", "address": address}
```

### Adding Background Tasks

Edit `enclave/tasks.py`:

```python
from datetime import datetime

def background_task():
    """Runs every 5 minutes (configurable in app.py)."""
    # Update state
    app_state["data"]["last_update"] = datetime.now().isoformat()
    
    # Save to encrypted S3
    odyn.state_save(app_state["data"])
    
    app_state["cron_counter"] += 1
```

### Using Odyn SDK

```python
from odyn import Odyn

odyn = Odyn()

# Get TEE Ethereum address
address = odyn.eth_address()

# Sign a message
signature = odyn.sign_message(message_bytes)

# Sign an Ethereum transaction
signed_tx = odyn.sign_tx(tx_dict)

# Save encrypted state to S3
result = odyn.state_save({"key": "value"})
state_hash = result["state_hash"]  # keccak256 hash

# Load state from S3
data = odyn.state_load()
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check for load balancers |
| `/status` | GET | App status with TEE identity and state hash |
| `/frontend/` | GET | Serve frontend UI (static files) |
| `/api/echo` | POST | Echo message example |
| `/api/info` | GET | Get app info example |
| `/.well-known/attestation` | POST | Get TEE attestation document |

## Smart Contract

The `NovaAppBase.sol` contract provides:

- **TEE Wallet Registration**: Register the TEE's Ethereum address
- **State Hash Storage**: Store keccak256 hash of encrypted state
- **Access Control**: Only registered TEE can update state

### Deploy Contract

```bash
cd contracts
forge install
forge script script/Deploy.s.sol --broadcast --rpc-url $RPC_URL
```

## Make Commands

| Command | Description |
|---------|-------------|
| `make build-frontend` | Build frontend and copy to enclave |
| `make dev-frontend` | Start frontend dev server (port 3000) |
| `make dev-enclave` | Start enclave dev server (port 5000) |
| `make docker-build` | Build Docker image (includes frontend) |
| `make docker-run` | Run Docker container locally |
| `make clean` | Clean all build artifacts |
| `make help` | Show all available commands |

## Features

- ✅ **RA-TLS Frontend** - Secure encrypted browser-to-TEE communication
- ✅ **Static Frontend Serving** - Frontend served at `/frontend/` from enclave
- ✅ **Encrypted State Persistence** - S3 + TEE encryption via Odyn
- ✅ **On-Chain Verification** - keccak256 state hash stored on-chain
- ✅ **Odyn SDK** - Easy access to identity, signing, attestation
- ✅ **Background Tasks** - Built-in APScheduler for periodic jobs
- ✅ **AWS Nitro Attestation** - Hardware-backed TEE verification

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `S3_BUCKET` | S3 bucket for state storage | From enclaver.yaml |
| `S3_REGION` | AWS region | From enclaver.yaml |
| `S3_PREFIX` | State file prefix | From enclaver.yaml |

## License

Apache 2.0
