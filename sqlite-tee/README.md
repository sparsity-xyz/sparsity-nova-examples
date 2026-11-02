# SQLite inside a Nitro enclave

A small synthetic example: SQLite runs in the application process inside Capsule,
with its database file on Capsule hostfs at `/mnt/appdata`. No separate DB server,
KMS, Helios or paid proof is required to execute SQL.

The startup experiment creates accounts and transfers; inserts, updates and
removes rows; commits and rolls back transactions; executes JOIN, GROUP BY and SUM;
closes/reopens the database; and requires `PRAGMA integrity_check` to return `ok`.
Expected balances are Alice 8750, Bob 5750 and Carol 3000 cents (total 17500).

## Deploy through Nova

Use this repository, directory `sqlite-tee`, Dockerfile `Dockerfile`, app port
8080. Enable the file proxy with mount path `/mnt/appdata`, mount name `appdata`,
size 128 MiB and required=true. KMS, S3 and Helios may remain disabled. Build a
version, enroll it and deploy to the Standard tier. The example refuses to start
without the actual mounted filesystem, so it cannot silently test only RAM.

The homepage displays results. `/result` returns the captured startup checks;
`/accounts` executes a new fixed SELECT against the database. No endpoint accepts
arbitrary SQL or arbitrary file paths. `/attestation` accepts only a 32-byte
base64 nonce and requests Nitro attestation bound to the startup-result hash.

## Exact scope

This is **public example code with synthetic data**. The current Nova App Hub
pipeline publishes its built container image publicly. Do not put private source,
credentials or customer records in this example or assume private GitHub source
makes a publicly published image private.

The database backing file is **not encrypted**. SQLite executes inside Nitro but
the parent can read its plain hostfs backing file. This is not a confidentiality,
backup, restart-recovery, malicious-parent, full-disk or production-durability
example. DELETE journal mode and FULL synchronization are used; successful normal
queries do not establish power-loss guarantees for the underlying hostfs.

The 128-MiB mount is a small experiment quota, not a SQLite size limit. A new
synthetic database filename is generated at each app start; repeated starts use
additional space. This disposable example is intended for short lab deployments.
The startup assertions are checks, not cryptographic evidence by themselves:
independently verify a fresh Nitro attestation and the image measurements when
claiming an enclave run.
