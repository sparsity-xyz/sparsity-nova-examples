"""
=============================================================================
User Routes (routes.py)
=============================================================================

Define your custom API endpoints here.

┌─────────────────────────────────────────────────────────────────────────────┐
│  MODIFY THIS FILE                                                           │
│  Add your own API endpoints and business logic here.                        │
└─────────────────────────────────────────────────────────────────────────────┘

How it works:
    - All routes are prefixed with /api (e.g., /api/echo)
    - You can access app_state and odyn after init() is called
    - Use FastAPI's standard decorators (@router.get, @router.post, etc.)

Demo endpoints included:
    - POST /api/echo       → Echo back a message with TEE address
    - GET  /api/info       → Get app info and state keys
    - GET  /api/random     → Generate random bytes using NSM hardware RNG
    - POST /api/storage    → Save key-value data to S3 storage
    - GET  /api/storage    → Load key-value data from S3 storage
    - GET  /api/contract   → Read contract state (stateHash)
    - POST /api/contract   → Write to contract (updateStateHash)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
import json
import os

# Type hint for Odyn (actual import would cause circular dependency)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from odyn import Odyn

logger = logging.getLogger("nova-app.routes")

# =============================================================================
# Shared References (set by app.py during startup)
# =============================================================================
app_state: Optional[dict] = None
odyn: Optional["Odyn"] = None


def init(state_ref: dict, odyn_ref: "Odyn"):
    """
    Initialize the routes module with shared references.
    
    Called by app.py during startup. Do not call directly.
    
    Args:
        state_ref: Reference to app_state dict
        odyn_ref: Reference to Odyn instance
    """
    global app_state, odyn
    app_state = state_ref
    odyn = odyn_ref
    logger.info("Routes module initialized")


# =============================================================================
# Router Configuration
# =============================================================================
router = APIRouter(prefix="/api", tags=["user"])


# =============================================================================
# Request/Response Models
# =============================================================================
class EchoRequest(BaseModel):
    message: str

class EchoResponse(BaseModel):
    reply: str
    tee_address: Optional[str] = None

class StorageRequest(BaseModel):
    key: str
    value: Any

class ContractWriteRequest(BaseModel):
    """Request to update state hash on contract."""
    state_hash: str  # bytes32 as hex string


# =============================================================================
# Demo Endpoints
# =============================================================================

@router.post("/echo", response_model=EchoResponse)
def echo_example(req: EchoRequest):
    """Echo back a message with TEE address."""
    try:
        address = odyn.eth_address() if odyn else "unknown"
    except:
        address = "unavailable"
    
    return EchoResponse(
        reply=f"Echo: {req.message}",
        tee_address=address
    )


@router.get("/info")
def get_info():
    """Get app info and current state keys."""
    return {
        "app": "Nova App Template",
        "state_keys": list(app_state.get("data", {}).keys()) if app_state else []
    }


# =============================================================================
# NSM Random Demo
# =============================================================================

@router.get("/random")
def get_random():
    """
    Generate random bytes using NSM hardware RNG.
    
    In production (Nitro Enclave), this uses the hardware random number generator.
    In development, it falls back to software RNG.
    
    Returns:
        random_hex: 32 random bytes as hex string
        random_int: Random integer (0 to 2^256-1)
    """
    if not odyn:
        raise HTTPException(status_code=500, detail="Odyn not initialized")
    
    try:
        random_bytes = odyn.get_random_bytes()
        random_hex = random_bytes.hex()
        random_int = int.from_bytes(random_bytes, 'big')
        
        return {
            "random_hex": f"0x{random_hex}",
            "random_int": str(random_int),
            "bytes_length": len(random_bytes)
        }
    except Exception as e:
        logger.error(f"Failed to get random bytes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# S3 Storage Demo
# =============================================================================

@router.post("/storage")
def save_to_storage(req: StorageRequest):
    """
    Save key-value data to S3 storage.
    
    Data is stored under the app's S3 prefix (isolated per app).
    The value can be any JSON-serializable data.
    
    Example:
        POST /api/storage
        {"key": "user_prefs", "value": {"theme": "dark", "lang": "en"}}
    """
    if not odyn:
        raise HTTPException(status_code=500, detail="Odyn not initialized")
    
    try:
        # Serialize value to JSON bytes
        json_bytes = json.dumps(req.value).encode('utf-8')
        
        # Save to S3
        success = odyn.s3_put(req.key, json_bytes)
        
        # Also update in-memory state
        if app_state:
            app_state["data"][req.key] = req.value
        
        return {
            "success": success,
            "key": req.key,
            "message": f"Data saved to S3 storage"
        }
    except Exception as e:
        logger.error(f"Failed to save to storage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/storage/{key}")
def load_from_storage(key: str):
    """
    Load key-value data from S3 storage.
    
    Returns the stored JSON value for the given key.
    """
    if not odyn:
        raise HTTPException(status_code=500, detail="Odyn not initialized")
    
    try:
        # Try to load from S3
        data = odyn.s3_get(key)
        
        if data is None:
            raise HTTPException(status_code=404, detail=f"Key not found: {key}")
        
        # Parse JSON
        value = json.loads(data.decode('utf-8'))
        
        return {
            "key": key,
            "value": value
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load from storage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/storage")
def list_storage():
    """
    List all keys in S3 storage.
    """
    if not odyn:
        raise HTTPException(status_code=500, detail="Odyn not initialized")
    
    try:
        keys = odyn.s3_list()
        return {
            "keys": keys,
            "count": len(keys)
        }
    except Exception as e:
        logger.error(f"Failed to list storage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/storage/{key}")
def delete_from_storage(key: str):
    """
    Delete a key from S3 storage.
    """
    if not odyn:
        raise HTTPException(status_code=500, detail="Odyn not initialized")
    
    try:
        success = odyn.s3_delete(key)
        
        # Also remove from in-memory state
        if app_state and key in app_state.get("data", {}):
            del app_state["data"][key]
        
        return {
            "success": success,
            "key": key,
            "message": f"Key deleted from S3 storage"
        }
    except Exception as e:
        logger.error(f"Failed to delete from storage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Contract Interaction Demo
# =============================================================================

# Contract configuration (set via environment variables)
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "")
RPC_URL = os.getenv("RPC_URL", "https://sepolia.base.org")
CHAIN_ID = int(os.getenv("CHAIN_ID", "84532"))  # Base Sepolia


@router.get("/contract")
def read_contract():
    """
    Read state from the NovaAppBase contract.
    
    Returns:
        - stateHash: Current state hash stored on-chain
        - teeWallet: Registered TEE wallet address
        - lastUpdatedBlock: Block number of last update
    """
    if not CONTRACT_ADDRESS:
        return {
            "error": "Contract not configured",
            "hint": "Set CONTRACT_ADDRESS environment variable"
        }
    
    # Note: For full contract reads, you would use web3.py or similar
    # This is a demo showing the pattern
    return {
        "contract_address": CONTRACT_ADDRESS,
        "rpc_url": RPC_URL,
        "chain_id": CHAIN_ID,
        "tee_address": odyn.eth_address() if odyn else None,
        "note": "Full contract read requires web3.py integration"
    }


@router.post("/contract/update-state")
def update_contract_state(req: ContractWriteRequest):
    """
    Update state hash on the NovaAppBase contract.
    
    This signs a transaction with the TEE's key and returns the raw tx.
    The transaction can be submitted via any RPC endpoint.
    
    Note: For full implementation, add web3.py for nonce/gas estimation.
    """
    if not odyn:
        raise HTTPException(status_code=500, detail="Odyn not initialized")
    
    if not CONTRACT_ADDRESS:
        raise HTTPException(
            status_code=400, 
            detail="Contract not configured. Set CONTRACT_ADDRESS env var."
        )
    
    try:
        # Function selector for updateStateHash(bytes32)
        # keccak256("updateStateHash(bytes32)")[:4] = 0x9f0e2260
        function_selector = "0x9f0e2260"
        
        # Encode the state hash (padded to 32 bytes)
        state_hash = req.state_hash.replace("0x", "").zfill(64)
        call_data = f"{function_selector}{state_hash}"
        
        # Build EIP-1559 transaction
        tx = {
            "kind": "structured",
            "chain_id": hex(CHAIN_ID),
            "nonce": "0x0",  # Should be fetched from RPC in production
            "max_priority_fee_per_gas": "0x5F5E100",  # 0.1 gwei
            "max_fee_per_gas": "0xB2D05E00",  # 3 gwei
            "gas_limit": "0x30D40",  # 200,000 gas
            "to": CONTRACT_ADDRESS,
            "value": "0x0",
            "data": call_data
        }
        
        # Sign with TEE key
        signed = odyn.sign_tx(tx)
        
        return {
            "success": True,
            "raw_transaction": signed["raw_transaction"],
            "transaction_hash": signed["transaction_hash"],
            "from_address": signed["address"],
            "to_address": CONTRACT_ADDRESS,
            "note": "Submit raw_transaction to RPC endpoint to execute"
        }
    except Exception as e:
        logger.error(f"Failed to sign transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Add Your Own Endpoints Below
# =============================================================================

# @router.post("/your-endpoint")
# def your_endpoint(req: YourRequestModel):
#     """Your custom logic here."""
#     pass

