# Private console compatibility lab

This public image contains Python/MariaDB dependencies and a small authenticated
launcher. It contains **no Nova console application source or production data**.
It lets the normal Nova app deployment workflow provision the test enclave,
without needing an operator to start a separate EC2 manually.

The operator verifies a fresh Nitro attestation against the build's PCRs and the
pinned AWS root. Attested user data binds the launcher's ephemeral X25519 key,
boot ID and approved private-package hash. A single client public key is pinned
in `policy.json`. Requests and responses use separately derived AES-256-GCM keys;
responses bind the request nonce and replays are rejected within the boot.

The authorized client sends the approved private package through that encrypted
channel. The launcher validates its SHA-256, archive paths, types and size before
installing it in enclave RAM and starting `/lab/bootstrap.py`. The uploaded
package supplies the private application and its test configuration.

The same channel can forward HTTP requests to a fixed loopback HTTPS application
endpoint. A client-side loopback proxy can therefore display the original console
UI without giving the Nova parent/Caddy proxy plaintext requests or responses.
The generic public landing page intentionally shows only launch status.

This is a bounded, single-operator, synthetic-data experiment. There is no durable
storage, production credential, public account administration, general URL proxy,
automatic trusted upgrade or claim of a comprehensive security audit. Ending the
enclave loses its loaded package, keys and test database. The host can still deny
service; TLS/AEAD does not protect against application bugs or hardware side channels.

Build this directory with the normal Nova App Hub workflow. Use application port
8080 and Standard enclave capacity (2 vCPU, 5 GiB); disable optional KMS, Helios,
S3 and hostfs integrations. `policy.json` pins one lab client and package, so another
experiment must generate its own policy and retain the private client key outside Git.

The upload key is bound in Nitro attestation's actual `public_key` field, not merely `user_data`. Capsule permits external callers to supply attestation metadata, so metadata alone is not an authenticated transport identity. The client checks the DER-encoded X25519 key exactly; Capsule's external Aux API strips public-key overrides.
