# Nova Platform Development Guide

This guide explains how to develop enclave applications for the Nova Platform.

## 1. Enclave Architecture

On the Nova Platform, user applications run inside an AWS Nitro Enclave secure environment. **Odyn** is the enclave supervisor that runs alongside your application (the "entrypoint") within the same enclave.

### Odyn's Main Responsibilities

- **Platform Initialization**: Bring up loopback networking, seed RNG from NSM (Nitro Secure Module)
- **Infrastructure Services**: Provide ingress listeners, optional egress proxy, optional KMS proxy, and internal API server
- **Application Supervision**: Launch and supervise your application process, handle process lifecycle and cleanup
- **Logging & Status**: Capture and expose application logs and runtime status over VSOCK to the host

### Services Provided to Your Application

- Secure key management and Ethereum signing
- Cryptographic random number generation (from NSM)
- Hardware-level remote attestation
- End-to-end encryption (ECDH + AES-256-GCM)

## 2. Application Packaging and Deployment

Your application needs to be packaged as a **Docker image**. During development, you can follow standard practices:

- Use any programming language and framework
- Use network functionality normally (HTTP requests, database connections, etc.)
- Remember your application's listening port (needed for configuration)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install -r requirements.txt

# Remember your application's listening port
EXPOSE 8080
CMD ["python", "main.py"]
```

## 3. Odyn API Service

Inside the enclave, access Odyn's API service to use Nitro Enclave security features:

```
Base URL: http://localhost:18000
```

## 4. Odyn API Reference

Below are the main API endpoints provided by Odyn:

### Get Ethereum Address

```http
GET /v1/eth/address
```

**Response:**
```json
{
  "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
  "public_key": "0x04..."
}
```

### Sign Message (EIP-191)

```http
POST /v1/eth/sign
Content-Type: application/json

{
  "message": "hello world",
  "include_attestation": false
}
```

**Response:**
```json
{
  "signature": "0x...",
  "address": "0x...",
  "attestation": null
}
```

### Sign Transaction

```http
POST /v1/eth/sign-tx
Content-Type: application/json

{
  "include_attestation": false,
  "payload": {
    "kind": "structured",
    "chain_id": "0x1",
    "nonce": "0x0",
    "max_priority_fee_per_gas": "0x3b9aca00",
    "max_fee_per_gas": "0x77359400",
    "gas_limit": "0x5208",
    "to": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
    "value": "0xde0b6b3a7640000",
    "data": "0x",
    "access_list": []
  }
}
```

### Get Random Bytes

```http
GET /v1/random
```

**Response:**
```json
{
  "random_bytes": "0x..." // 32 bytes, hex-encoded
}
```

### Generate Attestation

```http
POST /v1/attestation
Content-Type: application/json

{
  "nonce": "base64_encoded_nonce",
  "public_key": "PEM_encoded_public_key",
  "user_data": "base64_encoded_user_data"
}
```

Returns a CBOR-formatted Attestation document.

### Get Encryption Public Key

```http
GET /v1/encryption/public_key
```

**Response:**
```json
{
  "public_key_der": "0x3076...",
  "public_key_pem": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
}
```

### Decrypt Data

```http
POST /v1/encryption/decrypt
Content-Type: application/json

{
  "nonce": "0x...",
  "client_public_key": "0x...",
  "encrypted_data": "0x..."
}
```

**Response:**
```json
{
  "plaintext": "decrypted string"
}
```

### Encrypt Data

```http
POST /v1/encryption/encrypt
Content-Type: application/json

{
  "plaintext": "string to encrypt",
  "client_public_key": "0x..."
}
```

**Response:**
```json
{
  "encrypted_data": "...",
  "enclave_public_key": "...",
  "nonce": "..."
}
```

> 📖 For complete API documentation, see: [Enclaver Internal API](https://github.com/sparsity-xyz/enclaver/blob/sparsity/docs/internal_api.md)

## 5. Mock Service (Development Environment)

Since Odyn only works inside an actual enclave environment, we provide a **Mock Service** for local development and testing:

```
Mock Base URL: http://odyn.sparsity.cloud:18000
```

This mock service simulates all Odyn API endpoints, allowing developers to develop and debug outside the enclave environment.

## 6. Best Practice: Environment Variable Configuration

We recommend using the `IN_ENCLAVE` environment variable to distinguish between development and production environments:

```python
import os

# Choose Odyn endpoint based on environment variable
IN_ENCLAVE = os.getenv("IN_ENCLAVE", "false").lower() == "true"

if IN_ENCLAVE:
    ODYN_BASE_URL = "http://localhost:18000"
else:
    ODYN_BASE_URL = "http://odyn.sparsity.cloud:18000"
```

Set the default value in your Dockerfile:

```dockerfile
# Default to false during development
ENV IN_ENCLAVE=false

# When deployed to enclave, this will be set to true
```

| Environment | IN_ENCLAVE | Odyn Base URL |
|-------------|------------|---------------|
| Local Development/Testing | `false` | `http://odyn.sparsity.cloud:18000` |
| Enclave Production | `true` | `http://localhost:18000` |

## 7. Reference Implementation

Refer to the Odyn wrapper implementation in the `secured-chat-bot` example project:

📁 [`secured-chat-bot/enclave/odyn.py`](./secured-chat-bot/enclave/odyn.py)

This implementation demonstrates:
- Automatic environment detection and endpoint switching
- Complete API method wrappers
- Encryption/decryption usage examples
- Message signing functionality

```python
from odyn import Odyn

# Automatically selects endpoint based on environment
odyn = Odyn()

# Get Ethereum address
address = odyn.eth_address()

# Sign a message
signature = odyn.sign_message({"data": "hello"})

# Get random bytes
random_bytes = odyn.get_random_bytes(16)

# Get attestation document
attestation = odyn.get_attestation()
```

## 8. Frontend Deployment

Enclave applications typically run as API services. There are two approaches for frontend deployment:

### Option 1: Separate Frontend Deployment

Deploy frontend code separately on an external server or CDN, communicating with the enclave service via API.

> ⚠️ **CORS Configuration Required**: When your frontend is hosted on a different domain than your enclave API, you must configure CORS (Cross-Origin Resource Sharing) on your backend to allow cross-origin requests. Otherwise, browsers will block API requests from your frontend.

**FastAPI CORS Example:**
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend-domain.com"],  # Or ["*"] for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Option 2: Enclave-Embedded Frontend

Provide a static file serving endpoint within your enclave application, such as `/frontend`, to serve compiled frontend code:

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Mount static frontend files
app.mount("/frontend", StaticFiles(directory="frontend_dist", html=True), name="frontend")

# API routes
@app.get("/api/status")
def get_status():
    return {"status": "running"}
```

This approach allows users to access the complete application interface directly.

---

## Quick Start

1. **Create Application Directory Structure**
   ```
   my-enclave-app/
   ├── enclave/
   │   ├── main.py
   │   ├── odyn.py      # Copy from secured-chat-bot/enclave/odyn.py
   │   ├── requirements.txt
   │   └── Dockerfile
   └── frontend/        # Optional
       └── ...
   ```

2. **Copy Odyn Helper**
   ```bash
   cp secured-chat-bot/enclave/odyn.py my-enclave-app/enclave/
   ```

3. **Use Odyn Service**
   ```python
   from odyn import Odyn
   
   odyn = Odyn()
   # Now you can use all enclave features
   ```

4. **Local Testing**
   ```bash
   IN_ENCLAVE=false python main.py
   ```

5. **Build Docker Image and Deploy to Nova Platform**

---

## More Examples

| Example Project | Description |
|-----------------|-------------|
| [secured-chat-bot](./secured-chat-bot) | Secure chatbot demonstrating end-to-end encryption |
| [rng-oracle](./oracles/rng-oracle) | RNG Oracle for verifiable on-chain random numbers |
| [price-oracle](./oracles/price-oracle) | Price oracle demonstrating API signature verification |

---

## Related Links

- [Enclaver Internal API Documentation](https://github.com/sparsity-xyz/enclaver/blob/sparsity/docs/internal_api.md)
- [Nova Platform](https://sparsity.cloud)
