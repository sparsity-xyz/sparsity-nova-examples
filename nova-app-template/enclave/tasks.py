"""
=============================================================================
Background Tasks (tasks.py)
=============================================================================

Define your periodic background jobs here.

┌─────────────────────────────────────────────────────────────────────────────┐
│  MODIFY THIS FILE                                                           │
│  Add your own background tasks / cron jobs here.                            │
└─────────────────────────────────────────────────────────────────────────────┘

How it works:
    - background_task() is called every 5 minutes by the scheduler
    - You can access app_state and odyn after init() is called
    - Modify the interval in app.py if needed

Example use cases:
    - Auto-save state to S3 with hash on-chain
    - Periodic data sync from external APIs
    - Listen and respond to on-chain events
    - Scheduled on-chain transactions
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional, TYPE_CHECKING, Dict, Any

import requests
from eth_hash.auto import keccak

from chain import compute_state_hash, sign_update_state_hash

# Type hint for Odyn (actual import would cause circular dependency)
if TYPE_CHECKING:
    from odyn import Odyn

logger = logging.getLogger("nova-app.tasks")

# =============================================================================
# Shared References (set by app.py during startup)
# =============================================================================
app_state: Optional[dict] = None
odyn: Optional["Odyn"] = None

# =============================================================================
# Configuration (set via environment variables)
# =============================================================================
RPC_URL = os.getenv("RPC_URL", "https://sepolia.base.org")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "")
CHAIN_ID = int(os.getenv("CHAIN_ID", "84532"))  # Base Sepolia
BROADCAST_TX = os.getenv("BROADCAST_TX", "false").lower() == "true"


def init(state_ref: dict, odyn_ref: "Odyn"):
    """
    Initialize the tasks module with shared references.
    
    Called by app.py during startup. Do not call directly.
    
    Args:
        state_ref: Reference to app_state dict
        odyn_ref: Reference to Odyn instance
    """
    global app_state, odyn
    app_state = state_ref
    odyn = odyn_ref
    logger.info("Tasks module initialized")


# =============================================================================
# Helper Functions
# =============================================================================


def fetch_external_data() -> Optional[dict]:
    """
    Example: Fetch data from an external API.
    
    Replace this with your actual data source:
    - Price feeds (Chainlink, Binance, etc.)
    - Weather data
    - Sports scores
    - Any public API
    """
    try:
        # Example: Fetch ETH price from a public API
        # Replace with your actual data source
        response = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd",
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch external data: {e}")
        return None


def update_state_hash_on_chain(state_hash: str) -> Optional[str]:
    """
    Sign a transaction to update state hash on-chain.
    
    Args:
        state_hash: bytes32 hex string
        
    Returns:
        Raw signed transaction (ready for broadcast), or None on failure
    """
    if not odyn or not CONTRACT_ADDRESS:
        return None
    
    try:
        signed = sign_update_state_hash(
            odyn=odyn,
            contract_address=CONTRACT_ADDRESS,
            chain_id=CHAIN_ID,
            rpc_url=RPC_URL,
            state_hash=state_hash,
            broadcast=BROADCAST_TX,
        )
        logger.info(f"Signed state hash update tx: {signed['transaction_hash']}")
        return signed.get("raw_transaction")
    except Exception as e:
        logger.error(f"Failed to sign state hash tx: {e}")
        return None


# =============================================================================
# Main Background Task (MODIFY BELOW)
# =============================================================================

def background_task():
    """
    Main background task - runs every 5 minutes.
    
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  MODIFY THIS FUNCTION                                                   │
    │  Add your own periodic logic here.                                      │
    └─────────────────────────────────────────────────────────────────────────┘
    
    This example demonstrates:
    1. Fetching external data (e.g., price feed)
    2. Storing data to S3
    3. Computing hash and preparing on-chain update
    """
    if app_state is None:
        logger.warning("Tasks not initialized yet")
        return
    
    # --- Track task execution ---
    app_state["cron_counter"] = app_state.get("cron_counter", 0) + 1
    app_state["last_cron_run"] = datetime.utcnow().isoformat() + "Z"
    
    logger.info(f"Cron job #{app_state['cron_counter']} at {app_state['last_cron_run']}")
    
    # --- Example 1: Fetch external data ---
    external_data = fetch_external_data()
    if external_data:
        app_state["data"]["last_external_data"] = external_data
        app_state["data"]["last_fetch_time"] = app_state["last_cron_run"]
        logger.info(f"Fetched external data: {external_data}")
    
    # --- Example 2: Save state to S3 ---
    try:
        if app_state.get("initialized") and odyn:
            state_data = app_state.get("data", {})
            json_bytes = json.dumps(state_data).encode('utf-8')
            success = odyn.s3_put("app_state.json", json_bytes)
            if success:
                logger.info("Auto-saved state to S3")
                
                # --- Example 3: Compute hash and prepare on-chain update ---
                state_hash = compute_state_hash(state_data)
                app_state["data"]["last_state_hash"] = state_hash
                logger.info(f"State hash: {state_hash}")
                
                # Optionally sign tx for on-chain update (don't broadcast here)
                raw_tx = update_state_hash_on_chain(state_hash)
                if raw_tx:
                    app_state["data"]["pending_tx"] = raw_tx
            else:
                logger.warning("State save returned False")
    except Exception as e:
        logger.error(f"Cron auto-save failed: {e}")

    # --- Example 4: Poll on-chain events and respond ---
    try:
        poll_contract_events()
    except Exception as e:
        logger.warning(f"Event polling failed: {e}")



# =============================================================================
# On-Chain Event Listener (Optional Pattern)
# =============================================================================

def poll_contract_events():
    """
    Poll for on-chain events and respond.

    This demo listens for StateUpdateRequested(bytes32,address) events
    emitted by NovaAppBase and anchors the latest local state hash.
    """
    if not (odyn and app_state and CONTRACT_ADDRESS):
        return

    def rpc_call(method: str, params: list) -> Any:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        res = requests.post(RPC_URL, json=payload, timeout=15)
        res.raise_for_status()
        data = res.json()
        if "error" in data:
            raise RuntimeError(data["error"])
        return data["result"]

    current_block_hex = rpc_call("eth_blockNumber", [])
    current_block = int(current_block_hex, 16)

    last_block = app_state["data"].get("last_processed_block")
    if last_block is None:
        last_block = max(current_block - 1, 0)

    # Event signature: StateUpdateRequested(bytes32,address)
    topic0 = "0x" + keccak(b"StateUpdateRequested(bytes32,address)").hex()

    logs = rpc_call(
        "eth_getLogs",
        [{
            "fromBlock": hex(last_block + 1),
            "toBlock": hex(current_block),
            "address": CONTRACT_ADDRESS,
            "topics": [topic0],
        }],
    )

    if logs:
        app_state["data"]["last_event_count"] = app_state["data"].get("last_event_count", 0) + len(logs)

        state_hash = compute_state_hash(app_state.get("data", {}))
        app_state["data"]["last_state_hash"] = state_hash

        signed = sign_update_state_hash(
            odyn=odyn,
            contract_address=CONTRACT_ADDRESS,
            chain_id=CHAIN_ID,
            rpc_url=RPC_URL,
            state_hash=state_hash,
            broadcast=BROADCAST_TX,
        )
        app_state["data"]["last_event_anchor_tx"] = signed

    app_state["data"]["last_processed_block"] = current_block

