# Sparsity Nova Examples

This repository contains reference applications for the current Sparsity Nova stack and a practical guide for building enclave applications that match the latest `sparsity-nova-platform` and `capsule-cli` implementations.

The guidance here is aligned with:

- `sparsity-nova-platform`: control plane, build pipeline, runtime agent, attestation routing, and deployment behavior
- `capsule-cli`: build/run tooling, Capsule Runtime supervisor, Capsule API, Aux API, S3/KMS/app-wallet/Helios integrations

## How Nova Works Today

In the current Nova implementation, a production deployment looks like this:

1. You provide a normal Dockerized app.
2. Nova control plane generates `nova-build.yaml` and a deployment-specific `capsule.yaml`.
3. Nova App Hub / GitHub Actions builds `Docker -> EIF -> release image`, captures PCRs, and emits a signed `build-attestation.json`.
4. The runtime agent on EC2 pulls the pre-built image from ECR, verifies the image digest, and starts it with `capsule-cli run`.
5. The runtime fetches the enclave attestation from the Aux API, configures Caddy, and exposes:
   - your application on the deployment URL
   - `POST /.well-known/attestation` on the same hostname
6. ZK proof generation and on-chain registration happen after the enclave is running.

The examples in this repo are written for that flow: keep the application code simple and let Capsule APIs exposed through Capsule Runtime provide enclave-native services.

## Current Runtime Model

capsule-cli builds a release image that contains:

- your app image, amended with `/sbin/capsule-runtime` and `/etc/capsule/capsule.yaml`
- the generated `application.eif`
- the Capsule-Shell runtime image that launches Nitro Enclaves with `nitro-cli`

At runtime:

- `capsule-run` starts the enclave on the host side
- `capsule-runtime` runs as PID 1 inside the enclave
- your application runs under Capsule Runtime supervision
- outbound traffic goes through Capsule Runtime's egress proxy
- attestation, signing, encryption, storage, and optional KMS/app-wallet features are exposed through Capsule APIs served by Capsule Runtime

### Network Surfaces

| Surface | Inside Enclave | Public in Normal Nova Deployments | Notes |
|---------|----------------|-----------------------------------|-------|
| App ingress | app-defined port (for example `8000`) | Yes | Published by runtime and routed by Caddy |
| Primary API | `127.0.0.1:18000` | No | Full `/v1/*` API; loopback-only in normal deployments |
| Aux API | `127.0.0.1:18001` | Indirectly | Runtime maps a host attestation port to `18001` and routes `/.well-known/attestation*` there |
| Helios RPC | `127.0.0.1:18545+` | No | Public only in Nova's special mockup service |

Important current behavior from `sparsity-nova-platform`:

- the runtime publishes exactly two ports for normal apps:
  - host app port -> enclave app port
  - host attestation port -> enclave Aux API port `18001`
- `/.well-known/attestation*` is routed by Caddy to that host attestation port
- the Primary API (`18000`) is not exposed publicly for normal production apps

## What You Build

### 1. A Normal Docker Image

Your application can use any language or framework as long as it runs in a container and listens on a known port.

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install -r requirements.txt

# This is an app-level convention, not something Capsule injects automatically.
ENV IN_ENCLAVE=false

EXPOSE 8000
CMD ["python", "app.py"]
```

### 2. An `capsule.yaml`

For Nova deployments, the control plane generates the authoritative manifest from app settings. The committed example manifests in this repo are useful for local runs, but Nova production behavior is defined by the generated manifest.

A typical Nova-generated manifest looks like this:

```yaml
version: v1
name: my-app
target: nova-apps/my-app:v1

sources:
  app: my-app:v1

defaults:
  cpu_count: 2
  memory_mb: 4096

ingress:
  - listen_port: 8000
  - listen_port: 18001

egress:
  allow:
    - api.openai.com
    - "**.amazonaws.com"
    - 169.254.169.254

api:
  listen_port: 18000

aux_api:
  listen_port: 18001

storage:
  s3:
    enabled: true
    bucket: my-app-storage
    prefix: apps/my-app/
    region: us-west-1

kms_integration:
  enabled: true
  use_app_wallet: true
  kms_app_id: 49
  nova_app_registry: "0x..."

helios_rpc:
  enabled: true
  chains:
    - name: L2-base-sepolia
      network_id: "84532"
      kind: opstack
      network: base-sepolia
      execution_rpc: https://sepolia.base.org
      local_rpc_port: 18545
```

Key points:

- `api.listen_port` enables the full Capsule API on `127.0.0.1:18000`
- `aux_api.listen_port` enables the restricted attestation surface on `127.0.0.1:18001`
- Nova normally adds the app port and `18001` to `ingress`
- S3, KMS, app-wallet, and Helios are optional and manifest-driven
- if you use AWS SDK flows that rely on IMDS, allow `169.254.169.254` in `egress`

### 3. A `nova-build.yaml`

Nova also generates `nova-build.yaml` when a build is triggered:

```yaml
name: "my-app"
version: "v1"
repo: "https://github.com/you/my-app"
ref: "main"
build:
  directory: "enclave"
  dockerfile: "Dockerfile"
metadata:
  description: "My enclave application"
```

This config drives the build pipeline that produces the release image and build provenance.

## Current Capsule API Surface

Inside the enclave, Capsule Runtime serves localhost-only Capsule APIs. The full API lives on the Primary API port; the public attestation path used by Nova is backed by the Aux API.

### Core Endpoints

| Endpoint | Method | Current Behavior |
|----------|--------|------------------|
| `/v1/eth/address` | `GET` | Returns enclave Ethereum address and public key |
| `/v1/eth/sign` | `POST` | EIP-191 personal-sign; can optionally include attestation |
| `/v1/eth/sign-tx` | `POST` | Signs EIP-1559 transactions |
| `/v1/random` | `GET` | Returns 32 bytes from NSM-backed randomness |
| `/v1/attestation` | `POST` | Returns raw CBOR attestation bytes; not JSON |
| `/v1/encryption/public_key` | `GET` | Returns the enclave P-384 public key |
| `/v1/encryption/encrypt` | `POST` | Encrypts a response to a client |
| `/v1/encryption/decrypt` | `POST` | Decrypts client payloads |

### Optional Storage / KMS Endpoints

| Endpoint Group | Availability | Notes |
|----------------|--------------|-------|
| `/v1/s3/*` | `storage.s3.enabled=true` | Base64 object storage API backed by S3 |
| `/v1/kms/*` | `kms_integration.enabled=true` | Registry-backed key derivation and KV APIs |
| `/v1/app-wallet/*` | `kms_integration.use_app_wallet=true` | App-wallet identity and signing APIs |

### Attestation Rules That Matter

- `POST /v1/attestation` returns raw CBOR bytes with content type `application/cbor`
- `nonce` is optional
- `public_key` is optional; if omitted, Capsule Runtime uses the enclave encryption public key
- `user_data` must be a JSON object when provided
- Capsule Runtime injects `eth_addr` into `user_data`
- if app-wallet material is available, Capsule Runtime also injects `app_wallet`

## Public Attestation vs Internal Attestation

This distinction matters because older docs in this repo blurred the two:

- inside the enclave, your app can call `POST http://127.0.0.1:18000/v1/attestation`
- outside the enclave, Nova exposes `POST /.well-known/attestation`
- in current Nova runtime, `/.well-known/attestation` is not your app's responsibility in production; Caddy routes it to the Aux API port that the runtime published

Some examples in this repo still implement `/.well-known/attestation` in app code for local development convenience. Treat that as a dev shim, not as the production Nova routing model.

## Outbound Networking: Current Constraint

Nitro Enclaves do not have direct outbound network access. In the current Capsule implementation:

- Capsule Runtime provides an HTTP(S) egress proxy inside the enclave
- Capsule Runtime sets `http_proxy`, `https_proxy`, `HTTP_PROXY`, `HTTPS_PROXY`, `no_proxy`, and `NO_PROXY` for your app when egress is enabled
- your HTTP client library must respect proxy settings, or you must configure a proxy explicitly

Do not assume that "normal networking" always works unchanged inside the enclave. This is a common failure mode, especially with libraries that ignore proxy environment variables by default.

## Local Development

The examples in this repo commonly use an app-level `IN_ENCLAVE` convention:

```python
import os

IN_ENCLAVE = os.getenv("IN_ENCLAVE", "false").lower() == "true"
CAPSULE_RUNTIME_BASE_URL = "http://127.0.0.1:18000" if IN_ENCLAVE else "http://capsule-runtime.sparsity.cloud:18000"
```

Important caveats from the current Capsule docs:

- `IN_ENCLAVE` is not injected automatically by Capsule
- the external mock service is a convenience endpoint, not the authoritative implementation
- you should verify important behavior against the real Capsule code or a real enclave deployment

### Current Mock Endpoints Used by Examples

Nova currently operates a special mockup service that backs `capsule-runtime.sparsity.cloud`. It is useful for lightweight development loops and exposes:

- Primary API: `http://capsule-runtime.sparsity.cloud:18000`
- Aux API: `http://capsule-runtime.sparsity.cloud:18001`
- Helios RPC presets: `http://capsule-runtime.sparsity.cloud:18545` through `:18553`

Treat this as a development convenience. It is not version-locked to the Capsule repo.

## Build Provenance in the Current Platform

Nova's current build pipeline records provenance in `build-attestation.json`, including:

- source repository, ref, commit, directory, and Dockerfile
- PCR0 / PCR1 / PCR2 from the built EIF
- build timestamp and GitHub run metadata

The build attestation is signed with Sigstore/cosign, stored off-chain, and referenced by hash/URL in the platform flow. Runtime then deploys the pre-built image and verifies its digest before launch.

## Reference Implementations in This Repo

| Example | Why It Matters |
|---------|----------------|
| [hello-world-tee](./hello-world-tee) | Smallest identity + attestation example |
| [echo-vault](./echo-vault) | Best end-to-end backend reference; uses S3 persistence and Helios RPC |
| [secured-chat-bot](./secured-chat-bot) | Best reference for browser-to-enclave encryption with P-384 ECDH |
| [oracles/rng-oracle](./oracles/rng-oracle) | On-chain randomness flow with enclave signing |
| [oracles/price-oracle](./oracles/price-oracle) | External API verification and signing patterns |

For the most complete Python helper wrapper in this repo, start with:

- [`echo-vault/enclave/capsule_runtime.py`](./echo-vault/enclave/capsule_runtime.py)

## Quick Start

### Run an Example Locally

```bash
cd echo-vault/enclave
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
IN_ENCLAVE=false python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

For frontend-backed examples, start the frontend separately if the example README says so.

### Deploy Through Nova

The current production path is:

1. push your app repo with a normal Dockerfile
2. create the app in Nova Portal
3. configure advanced settings that determine generated `nova-build.yaml` and `capsule.yaml`
4. trigger a build
5. enroll the resulting version if on-chain registration is enabled
6. deploy the enrolled version
7. verify the app URL and `POST /.well-known/attestation`

## Related Reading

- [Capsule API](https://github.com/sparsity-xyz/nova-enclave-capsule/blob/main/docs/capsule-api.md)
- [Capsule Manifest Reference](https://github.com/sparsity-xyz/nova-enclave-capsule/blob/main/docs/capsule.yaml)
- [Capsule Architecture](https://github.com/sparsity-xyz/nova-enclave-capsule/blob/main/docs/capsule-architecture.md)
- [Nova Build Attestation](https://github.com/sparsity-xyz/sparsity-nova-platform/blob/main/docs/build-attestation.md)
- [Nova Runtime Port Exposure Flow](https://github.com/sparsity-xyz/sparsity-nova-platform/blob/main/docs/runtime-port-exposure-flow.md)
