# Echo Vault

Echo Vault is a TEE-backed vault whose behavior is simple, deterministic, and remotely attestable: all inbound transfers are echoed back to the sender.

## Architecture

Echo Vault consists of two main components:

1.  **TEE Enclave (Backend)**:
    *   Runs a Python FastAPI service.
    *   Integrates the Helios light client for trustless, verified access to Base Sepolia.
    *   Polls for incoming transfers and automatically echoes them back using Odyn's transaction signing API.
    *   Persists progress (last scanned block) in S3.
2.  **Web Dashboard (Frontend)**:
    *   React-based dashboard to monitor vault status.
    *   Displays wallet address, balance, and transaction history.
    *   Allows users to verify the TEE attestation.

## Quick Start

### Prerequisites
- Python 3.12+
- Node.js 18+

### Local Development (Mock Mode)
To run the application locally without a real TEE:

1.  **Backend**:
    ```bash
    cd enclave
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    IN_ENCLAVE=false python -m uvicorn app:app --host 0.0.0.0 --port 8000
    ```
2.  **Frontend**:
    ```bash
    cd frontend
    npm install
    npm run dev
    ```

### Deploy to Nova
To build and prepare for deployment:
```bash
enclaver build .
```

## Security Model

The vault's private key is derived within the enclave and never leaves the TEE. Every echo transaction is performed by the deterministic logic of the enclave, which is verifiable via remote attestation.
