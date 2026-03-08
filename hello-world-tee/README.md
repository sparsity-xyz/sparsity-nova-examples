# hello-world-tee

A minimal TEE app example that returns:
- a Hello World greeting
- app identity (wallet address + public keys)

## Endpoints

- `GET /`:
  - Returns a simple greeting card HTML page with wallet address and TEE public key
- `POST /.well-known/attestation`:
  - Returns raw CBOR attestation document

## Local Development (Mock Odyn)

```bash
cd enclave
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
IN_ENCLAVE=false python app.py
```

Then open:
- `http://localhost:8000/`

## Docker Run

```bash
docker build -t hello-world-tee .
docker run --rm -p 8000:8000 -e IN_ENCLAVE=false hello-world-tee
```

## Notes

- `IN_ENCLAVE=true` uses `http://127.0.0.1:18000` (inside enclave)
- `IN_ENCLAVE=false` uses `http://odyn.sparsity.cloud:18000` (mock service)
- The backend vendors the canonical SDK under `enclave/nova_python_sdk/`
