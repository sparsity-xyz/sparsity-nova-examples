# 8004-Agent

A TEE-based agent service running on AWS Nitro Enclave using [enclaver](https://github.com/sparsity-xyz/enclaver).

## Features

- **Agent Card**: Standard agent metadata endpoints
- **Demo Endpoints**: `/hello_world`, `/add_two`
- **Secure API Key**: Encrypted API key submission via ECDH
- **OpenAI Chat**: Secure chat integration
- **Attestation**: Enclave attestation support

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/ping` | GET | Ping/pong |
| `/attestation` | GET | Get attestation document |
| `/agent.json` | GET | Agent card |
| `/hello_world` | GET | Hello world demo |
| `/add_two` | POST | Add two numbers: `{"a": 5, "b": 3}` |
| `/get_encryption_key` | GET | Get public key for encrypting API key |
| `/set_encrypted_apikey` | POST | Set encrypted OpenAI API key |
| `/chat` | POST | Chat with OpenAI: `{"prompt": "..."}` |

## Quick Start

### 1. Setup Environment

```bash
cp .env.example .env
# Edit .env with your EC2 credentials
```

### 2. Build and Deploy

```bash
make build
make deploy-enclave
```

### 3. Set API Key (Encrypted)

The API key must be encrypted using the server's public key:

```python
import requests
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
import os

BASE_URL = "http://your-enclave-ip:8000"

# 1. Get server's public key
resp = requests.get(f"{BASE_URL}/get_encryption_key")
server_pub_key = serialization.load_der_public_key(
    bytes.fromhex(resp.json()["public_key"]), default_backend()
)

# 2. Generate ephemeral keypair
priv_key = ec.generate_private_key(ec.SECP384R1(), default_backend())
pub_key_der = priv_key.public_key().public_bytes(
    serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
)

# 3. ECDH + HKDF
shared = priv_key.exchange(ec.ECDH(), server_pub_key)
aes_key = HKDF(hashes.SHA256(), 32, None, b"encryption data").derive(shared)

# 4. Encrypt API key
nonce = os.urandom(32)
ciphertext = AESGCM(aes_key).encrypt(nonce, b"sk-your-openai-api-key", None)

# 5. Submit
requests.post(f"{BASE_URL}/set_encrypted_apikey", json={
    "nonce": nonce.hex(),
    "public_key": pub_key_der.hex(),
    "encrypted_key": ciphertext.hex()
})
```

### 4. Chat

```bash
curl -X POST http://your-enclave-ip:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello!"}'
```

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (uses mock odyn API)
python app.py
```

## Architecture

This application uses the enclaver framework to run inside AWS Nitro Enclaves:

- **app.py**: Flask-based main application
- **enclave.py**: Helper for odyn API interactions (attestation, encryption)
- **enclaver.yaml**: Enclave configuration

The enclave provides:
- Hardware-isolated execution environment
- Cryptographic attestation
- Secure key management via odyn API
- End-to-end encrypted API key submission
