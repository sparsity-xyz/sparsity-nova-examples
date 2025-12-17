# RNG Enclave Service

The off-chain TEE (Trusted Execution Environment) service for the Random Number Generator.

## Overview

This service runs inside an AWS Nitro Enclave and:
- Listens for `RandomNumberRequested` events from the RNG contract
- Generates cryptographically secure random numbers using the enclave's secure random source
- Signs and submits fulfillment transactions to the blockchain

## Files

| File | Description |
|------|-------------|
| `main.py` | FastAPI application and event listener |
| `enclave.py` | Enclave API wrapper (attestation, signing, random) |
| `config.py` | Configuration settings |
| `abi.json` | RNG contract ABI |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container build file |

## Quick Start

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configure

Edit `config.py` with your settings:
```python
CONTRACT_ADDRESS = "0x..."  # RNG contract address
RPC_URL = "https://sepolia.base.org"  # RPC endpoint
ENCLAVER_ENDPOINT = "http://127.0.0.1:18000"  # Odyn API
```

### Run

```bash
python main.py
```

The service starts on `http://0.0.0.0:8000`.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service status, operator info, balance |
| `/request/{request_id}` | GET | Get specific request details |
| `/attestation` | GET | Get TEE attestation document |

## Service Status

```bash
curl http://localhost:8000/
```

Response:
```json
{
    "service": "Random Number Generator",
    "version": "1.0.0",
    "status": "running",
    "is_operator": true,
    "contract_address": "0x...",
    "operator": "0x...",
    "operator_balance": 0.998857,
    "processed_requests": 0,
    "explorer": "https://sepolia.basescan.org/address/0x..."
}
```

## How It Works

1. **Startup**: Service connects to RPC and loads contract
2. **Wait for Authorization**: Polls until TEE wallet is registered as operator
3. **Event Listening**: Creates filter for `RandomNumberRequested` events
4. **Random Generation**: When event received:
   - Gets secure random bytes from enclave
   - Seeds Python's random module
   - Generates requested random numbers in range
5. **Transaction Submission**:
   - Builds `fulfillRandomNumber` transaction
   - Signs using enclave's ETH key
   - Submits to blockchain
6. **Callback**: Contract triggers user's callback if specified

## Dependencies

- `fastapi` / `uvicorn` - Web framework
- `web3` - Ethereum interaction
- `requests` - HTTP client for enclave API
- `cryptography` - ECDH encryption support

## For Local Development

When testing locally without an actual enclave, you can use a mock odyn API:

```python
# In main.py or enclave.py, point to mock service
ENCLAVER_ENDPOINT = "http://3.101.68.206:18000"  # Mock odyn
```

## License

Apache-2.0
