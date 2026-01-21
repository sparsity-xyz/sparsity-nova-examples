# Nova App Template

A production-ready template for building verifiable TEE applications on the Nova platform.

## Quick Start

```bash
# 1. Build frontend
make build-frontend

# 2. Run locally (uses odyn.sparsity.cloud for TEE simulation)
make dev-enclave

# 3. Access your app
#    API & Frontend: http://localhost:8000/
#    Metrics:        http://localhost:8000/status
```

## Project Structure

```
nova-app-template/
├── enclave/                 # Python FastAPI (runs in TEE)
│   ├── app.py               # Main entry point & status API
│   ├── routes.py            # User API & demo endpoints (MODIFY)
│   ├── tasks.py             # Background cron jobs (MODIFY)
│   ├── odyn.py              # TEE SDK wrapper
│   └── Dockerfile           # NSM-compatible build
├── frontend/                # Next.js + Tailwind (vibrant UI)
├── contracts/               # Solidity base contracts
├── enclaver.yaml            # Enclave networking & S3 config
└── Makefile                 # Build automation
```

## Key Capabilities

### 1. Trusted Identity & RA-TLS
Establish hardware-verifiable encrypted channels with the enclave.
- **Attestation**: Fetch and verify AWS Nitro Enclave documents.
- **ECDH**: Secure key exchange using P-384 or secp256k1.
- **Signing**: Hardware-backed EIP-191 and transaction signing.

### 2. S3 Persistent Storage
Store sensitive state in encrypted S3 buckets with per-app isolation.
- **`odyn.s3_put(key, value)`**: Store binary data (automatically scoped).
- **`odyn.s3_get(key)`**: Retrieve data.
- **`odyn.s3_list(prefix)`**: List stored keys.

### 3. Oracles (Internet → Chain)
Fetch external data and sign transactions within the secure environment.
- **Internet Access**: TEE can fetch data from public APIs.
- **On-Chain Signing**: TEE seeds generate a persistent Ethereum wallet.

### 4. Background Workers & Verification
Manage periodic tasks and anchor TEE state to the blockchain.
- **APScheduler**: Integrated runner for cron-like jobs.
- **State Hashing**: Periodically hash app state for on-chain integrity.
- **Smart Contracts**: Use `NovaAppBase.sol` to create an immutable trust anchor.

## Configuration (Ports & Connectivity)

The template defines a standard mapping for TEE services. 

> [!TIP]
> **S3 Storage** and **Egress Policies** are automatically managed and injected by the Nova platform during deployment. You do not need to manually configure them in `enclaver.yaml` unless you have specific custom requirements.

| Component | Port | Description |
|-----------|------|-------------|
| **App Listening Port** | `8000` | The user-facing API (Ingress). This is what you enter when creating the app on Nova. |
| **Odyn Primary** | `18000` | Internal TEE identity and storage services. |
| **Odyn Auxiliary** | `18001` | Sidecar services (e.g., attestation bridge). |

## Local Development

The template is designed for "simulate-first" development.

### Running with Mockup Service
When running outside a Nitro Enclave, `odyn.py` automatically connects to `mockup.sparsity.cloud:18000`. This allows you to test identity, signing, and storage without specialized hardware.

```bash
cd enclave
pip install -r requirements.txt
python app.py  # Starts on port 8000
```

### Building for Deployment
```bash
# 1. Sync frontend
make build-frontend

# 2. Deploy via Nova CLI or GitHub Action
# Nova will automatically detect enclaver.yaml and build the image.
```

## API Endpoints

| Endpoint | Method | Category | Description |
|----------|--------|----------|-------------|
| `/api/attestation` | GET | Identity | Fetch Nitro attestation doc |
| `/api/sign` | POST | Identity | Sign personal message (EIP-191) |
| `/api/oracle/price` | GET | Oracle | Fetch internet price & sign tx |
| `/api/storage` | POST/GET | Storage | Read/Write to isolated S3 |
| `/api/random` | GET | Utility | Hardware RNG bytes (NSM) |
| `/status` | GET | Platform | Telemetry & Job stats |

## License
Apache 2.0
