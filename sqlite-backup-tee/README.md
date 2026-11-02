# Encrypted SQLite checkpoint experiment

A synthetic web service runs SQLite inside Nitro. The live database is encrypted
with gocryptfs over Capsule hostfs. SQLite's online backup API makes a consistent
snapshot inside the enclave; AES-256-GCM encrypts that snapshot before S3 sees it.
Each accepted transfer also has an encrypted, numbered, hash-linked S3 journal
object. A small Base Sepolia contract stores the latest manifest hash and emits
checkpoint events. No production Nova registry or KMS state is changed.

Use directory `sqlite-backup-tee`, Dockerfile `Dockerfile`, app port 8080, a required
128-MiB file-proxy mount named `appdata` at `/mnt/appdata`, and enable persistent
storage plus S3 with region `us-west-1`. The platform selects its existing private
bucket and app-specific prefix. Allow egress to IMDS, AWS S3 and `sepolia.base.org`.
KMS, app-wallet and Helios remain off. Nova's Standard tier allocates 2 vCPU and
5120 MiB; these are enclave resources, not a disk-sized RAM allocation.

## Access and keys

`client-public.txt` is a public X25519 experiment client key. Replace it with your
own before building another experiment. No private key is in this repo or image.
The app generates a fresh boot key. Verify its fresh Nitro attestation, PCRs, boot
ID and public-key hash before initializing. `/rpc` uses X25519 + HKDF + AES-GCM,
with separate request/response keys, request replay detection and response binding.
The authenticated client provides the data key through this encrypted channel.
The public dashboard displays only synthetic account data and status.

A caller cannot submit arbitrary SQL, filesystem paths, shell commands or S3
locations outside this run's prefix. The lab data key is retained outside Git by
the operator for restore. This is a test key-delivery design, not production KMS.
The source and built image are public; encrypted database contents are separate.

## Commit and recovery rules

1. Commit a transfer and its outbox record in one SQLite transaction.
2. Upload the encrypted record and verify S3 read-back before acknowledging it.
3. Retry using the same transaction ID after a lost response; never debit twice.
4. Create a SQLite backup, encrypt it, upload it and verify read-back.
5. Upload its canonical manifest, then commit that manifest's SHA-256 to the chain.
6. Restore only the manifest matching the contract's latest state, authenticate the
   ciphertext, check SQLite integrity and sequence/hash-chain state, then serve it.

There is no atomic transaction spanning SQLite, S3 and the blockchain. The outbox
handles local-commit/S3-upload failures while the disk survives. The encrypted log
can restore acknowledged post-snapshot operations, but the client must retain
receipts or a newer external commitment to detect truncation of an unanchored tail.
The contract uses an authorized operator, not a verified-enclave proof. Its API
rejects stale epochs, decreasing sequences and a wrong previous manifest hash.

S3 objects are append-only by application convention, not enforced Object Lock.
The current Capsule S3 API does not expose conditional PUT. The existing app role
can overwrite/delete objects; hashes/authenticated encryption detect substitutions
but cannot prevent deletion. This demo uses a trusted HTTPS Base Sepolia RPC's
latest head, not independently verified finality. Production recovery must wait
for chosen chain finality and fail closed if current state is unavailable.

The crash test kills a SQLite writer during an uncommitted transaction. It is not
a host power-failure test. Capsule's previously documented disk-full/partial-write
behavior remains an unresolved durability concern. Do not treat this lab as
production storage approval. Do not share one live SQLite file across enclaves.

## Verified experiment, November 2, 2026

The running code at commit `fd53b019ed46012cf4efb6c058bea036ad99a54a` passed:

- External attested/encrypted API calls to SQLite inside a non-debug Nitro enclave.
- Six synthetic transfers; encrypted S3 snapshot upload, read-back and restore.
- Retry after local commit but before S3 upload, without applying a transfer twice.
- Rejection of an older checkpoint and corrupted encrypted snapshot.
- Recovery of a post-checkpoint transaction from an encrypted S3 journal record;
  repeating that replay did not apply the transaction again.
- SIGKILL of an uncommitted SQLite writer, preserving previously committed data.
- Termination of the original EC2, automatic provisioning of a fresh EC2/enclave,
  and restore from S3 plus the retained key and contract state. Writes were blocked
  before the fresh enclave restored the checkpoint.

The SQLite database was 315,392 bytes (308 KiB); its encrypted snapshot was
315,425 bytes. The configured hostfs image was 128 MiB, with about 114 MiB usable
after filesystem overhead, backed by the parent's 30-GiB EBS root volume. The
enclave had 2 vCPUs, 5,120 MiB RAM and no swap; the disk is not all held in RAM.
SQLite's configured page-cache target was 2 MiB. This implementation materializes
whole backup/encryption/base64 payloads in memory, so it needs streaming changes
before backing up databases approaching enclave RAM size.

The dedicated Base Sepolia contract is
`0x2304E3dEF91b5A477774Ca1d8DACb28785DFc433`. It recorded checkpoints at transaction
sequences 3, 5 and 6. This contract is separate from Nova's application registry.
The app was deployed without a paid proving or Nova registry enrollment step.

This is a single-instance synthetic experiment, not a power-cut durability test
or security audit. The public dashboard intentionally reveals synthetic balances;
real confidential data must only be served through an authenticated encrypted API.
The operator can authorize arbitrary commitments in this contract. A client uses
the built image's approved PCRs and fresh attestation, not a blockchain hash alone,
to authenticate the application receiving its data key.
