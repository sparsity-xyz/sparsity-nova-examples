"""
Configuration for Nova KMS Client.
"""
import os
import logging

logger = logging.getLogger("nova-kms-client.config")

# Environment / Defaults
SIMULATION_MODE = os.getenv("SIMULATION_MODE", "0").lower() in ("1", "true", "yes")
IN_ENCLAVE = os.getenv("IN_ENCLAVE", "false").lower() == "true"

# Chain Configuration
CHAIN_ID = 84532  # Base Sepolia
RPC_URL = "http://odyn.sparsity.cloud:8545"

# Registry Addresses (Fixed Parameters)
# TODO: Replace with actual deployed addresses
NOVA_APP_REGISTRY_ADDRESS = "0x0000000000000000000000000000000000000000"
KMS_REGISTRY_ADDRESS = "0x0000000000000000000000000000000000000000"

if NOVA_APP_REGISTRY_ADDRESS == "0x0000000000000000000000000000000000000000":
    logger.warning("NOVA_APP_REGISTRY_ADDRESS is not configured (using zero address). Service discovery will fail.")

if KMS_REGISTRY_ADDRESS == "0x0000000000000000000000000000000000000000":
    logger.warning("KMS_REGISTRY_ADDRESS is not configured (using zero address). KMS node discovery will fail.")

REGISTRY_CACHE_TTL_SECONDS = 60

# PoP Configuration
POP_MAX_AGE_SECONDS = 120

# Scheduler
TEST_CYCLE_INTERVAL_SECONDS = 10
