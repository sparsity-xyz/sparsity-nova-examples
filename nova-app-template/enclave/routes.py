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
    - POST /api/contract/update-state → Write to contract (updateStateHash)
    - POST /api/oracle/update-now     → Fetch ETH/USD and update on-chain price
    - GET  /api/events/oracle         → Fetch oracle-related on-chain events
"""

import json
import logging
import base64
from datetime import datetime
from typing import Optional, Dict, Any, TYPE_CHECKING

import requests
from eth_hash.auto import keccak
from fastapi import APIRouter, HTTPException, Body, Response
from pydantic import BaseModel

from chain import compute_state_hash, sign_update_state_hash
from chain import sign_update_eth_price
from config import CONTRACT_ADDRESS, RPC_URL, CHAIN_ID, BROADCAST_TX, ANCHOR_ON_WRITE

# Type hint for Odyn (actual import would cause circular dependency)
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
public_router = APIRouter(tags=["public"])


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
    content_type: Optional[str] = None

class ContractWriteRequest(BaseModel):
    """Request to update state hash on contract."""
    state_hash: str  # bytes32 as hex string

class SignMessageRequest(BaseModel):
    """Request to sign a message."""
    message: str
    include_attestation: bool = False

class EncryptRequest(BaseModel):
    """Request to encrypt data for client."""
    plaintext: str
    client_public_key: str  # Hex-encoded DER public key

class DecryptRequest(BaseModel):
    """Request to decrypt data from client."""
    nonce: str
    client_public_key: str
    encrypted_data: str

class EncryptedPayload(BaseModel):
    nonce: str
    public_key: str
    data: str


# =============================================================================
# TEE Identity & Cryptography Endpoints
# =============================================================================

@router.get("/attestation")
def get_attestation(nonce: str = ""):
    """
    Get a Nitro attestation document.
    
    The attestation proves this code is running in a genuine
    AWS Nitro Enclave with specific PCR measurements.
    
    Returns: CBOR-encoded attestation document (base64)
    """
    if not odyn:
        raise HTTPException(status_code=500, detail="Odyn not initialized")
    
    try:
        attestation = odyn.get_attestation(nonce)
        return {"attestation": base64.b64encode(attestation).decode()}
    except Exception as e:
        logger.error(f"Failed to get attestation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@public_router.post("/.well-known/attestation")
def well_known_attestation(body: Dict[str, Any] = Body(default_factory=dict)):
    """
    Public RA-TLS endpoint for frontend attestation fetch.

    Returns raw CBOR attestation document.
    """
    if not odyn:
        raise HTTPException(status_code=500, detail="Odyn not initialized")

    try:
        nonce = body.get("nonce", "") if isinstance(body, dict) else ""
        attestation = odyn.get_attestation(nonce)
        return Response(content=attestation, media_type="application/cbor")
    except Exception as e:
        logger.error(f"Failed to get attestation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sign")
def sign_message(req: SignMessageRequest):
    """
    Sign a message using EIP-191 personal message prefix.
    
    The signature proves the message was signed by the TEE's
    hardware-seeded private key.
    """
    if not odyn:
        raise HTTPException(status_code=500, detail="Odyn not initialized")
    
    try:
        result = odyn.sign_message(req.message, req.include_attestation)
        return result
    except Exception as e:
        logger.error(f"Failed to sign message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/encryption/public_key")
def get_encryption_public_key():
    """
    Get the enclave's P-384 public key for ECDH-based encryption.
    
    Use this to establish an encrypted channel with the TEE.
    """
    if not odyn:
        raise HTTPException(status_code=500, detail="Odyn not initialized")
    
    try:
        return odyn.get_encryption_public_key()
    except Exception as e:
        logger.error(f"Failed to get encryption public key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/encrypt")
def encrypt_data(req: EncryptRequest):
    """
    Encrypt data to send to a client using ECDH + AES-256-GCM.
    """
    if not odyn:
        raise HTTPException(status_code=500, detail="Odyn not initialized")
    
    try:
        return odyn.encrypt(req.plaintext, req.client_public_key)
    except Exception as e:
        logger.error(f"Failed to encrypt: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decrypt")
def decrypt_data(req: DecryptRequest):
    """
    Decrypt data sent from a client using ECDH + AES-256-GCM.
    """
    if not odyn:
        raise HTTPException(status_code=500, detail="Odyn not initialized")
    
    try:
        plaintext = odyn.decrypt(req.nonce, req.client_public_key, req.encrypted_data)
        return {"plaintext": plaintext}
    except Exception as e:
        logger.error(f"Failed to decrypt: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Demo Endpoints
# =============================================================================

@router.post("/echo")
def echo_example(payload: Dict[str, Any] = Body(...)):
    """Echo back a message with TEE address (supports encrypted payloads)."""
    if not odyn:
        raise HTTPException(status_code=500, detail="Odyn not initialized")

    try:
        address = odyn.eth_address()
    except Exception:
        address = "unavailable"

    # Encrypted flow: {nonce, public_key, data}
    if {"nonce", "public_key", "data"}.issubset(payload.keys()):
        enc = EncryptedPayload(**payload)
        try:
            plaintext = odyn.decrypt(enc.nonce, enc.public_key, enc.data)
            req = EchoRequest(**json.loads(plaintext))
            response = {"reply": f"Echo: {req.message}", "tee_address": address}
            encrypted = odyn.encrypt(json.dumps(response), enc.public_key)
            return {
                "data": {
                    "encrypted_data": encrypted.get("encrypted_data"),
                    "nonce": encrypted.get("nonce"),
                    "public_key": encrypted.get("enclave_public_key"),
                }
            }
        except requests.exceptions.HTTPError as e:
            detail = None
            try:
                detail = e.response.text if e.response is not None else None
            except Exception:
                detail = None
            raise HTTPException(
                status_code=400,
                detail=f"Odyn encryption/decryption failed: {detail or str(e)}",
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Encrypted request failed: {str(e)}")

    # Plaintext flow
    req = EchoRequest(**payload)
    return EchoResponse(reply=f"Echo: {req.message}", tee_address=address)


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
        success = odyn.s3_put(req.key, json_bytes, content_type=req.content_type)
        
        # Also update in-memory state
        if app_state:
            app_state["data"][req.key] = req.value
        
        result: Dict[str, Any] = {
            "success": success,
            "key": req.key,
            "message": "Data saved to S3 storage"
        }

        # Anchor updated state hash on-chain (optional)
        if success and app_state and ANCHOR_ON_WRITE and CONTRACT_ADDRESS:
            state_hash = compute_state_hash(app_state["data"])
            app_state["data"]["last_state_hash"] = state_hash
            try:
                anchor = sign_update_state_hash(
                    odyn=odyn,
                    contract_address=CONTRACT_ADDRESS,
                    chain_id=CHAIN_ID,
                    rpc_url=RPC_URL,
                    state_hash=state_hash,
                    broadcast=BROADCAST_TX,
                )
                result["state_hash"] = state_hash
                result["anchor_tx"] = anchor
            except Exception as e:
                result["anchor_error"] = str(e)

        return result
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
        res = odyn.s3_list()
        keys = res.get("keys", []) if isinstance(res, dict) else res
        return {
            "keys": keys,
            "count": len(keys),
            "continuation_token": res.get("continuation_token") if isinstance(res, dict) else None,
            "is_truncated": res.get("is_truncated") if isinstance(res, dict) else False
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

# Contract configuration
# This template uses static constants in config.py (per-request: no env var reads).


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
            "hint": "Set CONTRACT_ADDRESS in enclave/config.py"
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
            detail="Contract not configured. Set CONTRACT_ADDRESS in enclave/config.py."
        )
    
    try:
        signed = sign_update_state_hash(
            odyn=odyn,
            contract_address=CONTRACT_ADDRESS,
            chain_id=CHAIN_ID,
            rpc_url=RPC_URL,
            state_hash=req.state_hash,
            broadcast=BROADCAST_TX,
        )
        return {
            "success": True,
            "raw_transaction": signed["raw_transaction"],
            "transaction_hash": signed["transaction_hash"],
            "from_address": signed["address"],
            "to_address": CONTRACT_ADDRESS,
            "broadcasted": signed.get("broadcasted"),
            "rpc_tx_hash": signed.get("rpc_tx_hash"),
            "note": "Submit raw_transaction to RPC endpoint to execute" if not BROADCAST_TX else "Broadcast attempted"
        }
    except Exception as e:
        logger.error(f"Failed to sign transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Oracle Demo (Internet to Chain)
# =============================================================================

@router.get("/oracle/price")
def get_oracle_price_tx():
    """
    Oracle Demo (legacy): Fetch internet data and sign an on-chain update.

    Prefer POST /oracle/update-now for a real on-chain update flow.
    """
    return update_oracle_price_now()


@router.post("/oracle/update-now")
def update_oracle_price_now():
    """Fetch ETH/USD and update the on-chain app contract via updateEthPrice.

    - If BROADCAST_TX is True, the enclave will attempt to send the tx via RPC.
    - Otherwise returns a raw signed tx for the caller to broadcast.
    """
    if not odyn:
        raise HTTPException(status_code=500, detail="Odyn not initialized")

    if not CONTRACT_ADDRESS:
        raise HTTPException(status_code=400, detail="Contract not configured. Set CONTRACT_ADDRESS in enclave/config.py.")

    try:
        res = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd",
            timeout=10,
        )
        res.raise_for_status()
        price_usd = int(res.json()["ethereum"]["usd"])

        updated_at = int(datetime.utcnow().timestamp())

        signed = sign_update_eth_price(
            odyn=odyn,
            contract_address=CONTRACT_ADDRESS,
            chain_id=CHAIN_ID,
            rpc_url=RPC_URL,
            request_id=0,
            price_usd=price_usd,
            updated_at=updated_at,
            broadcast=BROADCAST_TX,
        )

        if app_state is not None:
            oracle_state = app_state.setdefault("data", {}).setdefault("oracle", {})
            oracle_state["last_price_usd"] = price_usd
            oracle_state["last_updated_at"] = updated_at
            oracle_state["last_reason"] = "api"
            oracle_state["last_tx"] = signed

        return {
            "success": True,
            "contract_address": CONTRACT_ADDRESS,
            "price_usd": price_usd,
            "updated_at": updated_at,
            "tx": signed,
            "broadcast": BROADCAST_TX,
        }
    except Exception as e:
        logger.error(f"Oracle update-now failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _rpc_call(method: str, params: list) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    res = requests.post(RPC_URL, json=payload, timeout=15)
    res.raise_for_status()
    data = res.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data["result"]


@router.get("/events/oracle")
def get_oracle_events(lookback: int = 1000):
    """Return oracle-related contract events for the last N blocks."""
    if not CONTRACT_ADDRESS:
        raise HTTPException(status_code=400, detail="Contract not configured. Set CONTRACT_ADDRESS in enclave/config.py.")

    current_block_hex = _rpc_call("eth_blockNumber", [])
    current_block = int(current_block_hex, 16)
    from_block = max(current_block - max(0, int(lookback)), 0)

    # Topics
    req_topic0 = "0x" + keccak(b"EthPriceUpdateRequested(uint256,address)").hex()
    upd_topic0 = "0x" + keccak(b"EthPriceUpdated(uint256,uint256,uint256,uint256)").hex()

    req_logs = _rpc_call(
        "eth_getLogs",
        [{
            "fromBlock": hex(from_block),
            "toBlock": hex(current_block),
            "address": CONTRACT_ADDRESS,
            "topics": [req_topic0],
        }],
    )

    upd_logs = _rpc_call(
        "eth_getLogs",
        [{
            "fromBlock": hex(from_block),
            "toBlock": hex(current_block),
            "address": CONTRACT_ADDRESS,
            "topics": [upd_topic0],
        }],
    )

    handled = {}
    if app_state is not None:
        handled = app_state.get("data", {}).get("oracle", {}).get("handled_requests", {}) or {}

    def _parse_uint256(hex32: str) -> int:
        return int(hex32, 16)

    requests_out = []
    for log in req_logs or []:
        topics = log.get("topics", [])
        request_id = _parse_uint256(topics[1]) if len(topics) > 1 else 0
        requester = "0x" + topics[2][-40:] if len(topics) > 2 else None
        requests_out.append({
            "type": "EthPriceUpdateRequested",
            "request_id": request_id,
            "requester": requester,
            "block_number": int(log.get("blockNumber", "0x0"), 16),
            "tx_hash": log.get("transactionHash"),
            "log_index": int(log.get("logIndex", "0x0"), 16),
            "handled": str(request_id) in handled,
        })

    updates_out = []
    for log in upd_logs or []:
        topics = log.get("topics", [])
        request_id = _parse_uint256(topics[1]) if len(topics) > 1 else 0
        data_hex = (log.get("data") or "0x").replace("0x", "")
        # data: priceUsd, updatedAt, blockNumber
        price_usd = int(data_hex[0:64] or "0", 16) if len(data_hex) >= 64 else 0
        updated_at = int(data_hex[64:128] or "0", 16) if len(data_hex) >= 128 else 0
        block_number_emitted = int(data_hex[128:192] or "0", 16) if len(data_hex) >= 192 else 0
        updates_out.append({
            "type": "EthPriceUpdated",
            "request_id": request_id,
            "price_usd": price_usd,
            "updated_at": updated_at,
            "block_number_emitted": block_number_emitted,
            "block_number": int(log.get("blockNumber", "0x0"), 16),
            "tx_hash": log.get("transactionHash"),
            "log_index": int(log.get("logIndex", "0x0"), 16),
        })

    events = sorted(requests_out + updates_out, key=lambda e: (e.get("block_number", 0), e.get("log_index", 0)))

    return {
        "contract_address": CONTRACT_ADDRESS,
        "from_block": from_block,
        "to_block": current_block,
        "events": events,
        "handled_requests": handled,
    }


# =============================================================================
# Add Your Own Endpoints Below
# =============================================================================

# @router.post("/your-endpoint")
# def your_endpoint(req: YourRequestModel):
#     """Your custom logic here."""
#     pass

