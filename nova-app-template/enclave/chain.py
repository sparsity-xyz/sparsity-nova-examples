"""
Chain utilities for Nova app template.

- Computes state hash (keccak256 of canonical JSON)
- Builds and signs updateStateHash transactions
- Optionally broadcasts transactions via JSON-RPC
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import requests
from eth_hash.auto import keccak

logger = logging.getLogger("nova-app.chain")

UPDATE_STATE_SELECTOR = "0x9f0e2260"  # keccak256("updateStateHash(bytes32)")[:4]


def function_selector(signature: str) -> str:
    """Return 4-byte function selector (0x-prefixed, 8 hex chars)."""
    return "0x" + keccak(signature.encode("utf-8")).hex()[:8]


def compute_state_hash(data: dict) -> str:
    """Compute keccak256 hash of state data for on-chain anchoring."""
    json_bytes = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "0x" + keccak(json_bytes).hex()


def _rpc_call(rpc_url: str, method: str, params: list) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    res = requests.post(rpc_url, json=payload, timeout=15)
    res.raise_for_status()
    data = res.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data["result"]


def _hex_to_int(value: str) -> int:
    return int(value, 16)


def _int_to_hex(value: int) -> str:
    return hex(max(0, value))


def get_nonce(rpc_url: str, address: str) -> str:
    return _rpc_call(rpc_url, "eth_getTransactionCount", [address, "pending"])


def get_fee_params(rpc_url: str) -> Dict[str, str]:
    """Return EIP-1559 fee params (hex strings)."""
    try:
        max_priority = _rpc_call(rpc_url, "eth_maxPriorityFeePerGas", [])
    except Exception:
        max_priority = "0x5F5E100"  # 0.1 gwei fallback

    try:
        gas_price = _rpc_call(rpc_url, "eth_gasPrice", [])
    except Exception:
        gas_price = "0xB2D05E00"  # 3 gwei fallback

    max_priority_int = _hex_to_int(max_priority)
    gas_price_int = _hex_to_int(gas_price)

    # Conservative max fee: 2x gas price or gas price + priority, whichever is higher
    max_fee_int = max(gas_price_int * 2, gas_price_int + max_priority_int)

    return {
        "max_priority_fee_per_gas": _int_to_hex(max_priority_int),
        "max_fee_per_gas": _int_to_hex(max_fee_int),
    }


def estimate_gas(rpc_url: str, tx: Dict[str, str]) -> str:
    try:
        return _rpc_call(rpc_url, "eth_estimateGas", [tx])
    except Exception as e:
        logger.warning(f"Gas estimate failed, using fallback: {e}")
        return "0x30D40"  # 200,000


def encode_update_state_hash(state_hash: str) -> str:
    clean = state_hash.replace("0x", "").zfill(64)
    return f"{UPDATE_STATE_SELECTOR}{clean}"


def _encode_uint256(value: int) -> str:
    if value < 0:
        raise ValueError("uint256 cannot be negative")
    return hex(value).replace("0x", "").zfill(64)


UPDATE_ETH_PRICE_SELECTOR = function_selector("updateEthPrice(uint256,uint256,uint256)")


def encode_update_eth_price(*, request_id: int, price_usd: int, updated_at: int) -> str:
    """ABI-encode updateEthPrice(uint256,uint256,uint256) call data (uint256-only)."""
    return (
        f"{UPDATE_ETH_PRICE_SELECTOR}"
        f"{_encode_uint256(request_id)}"
        f"{_encode_uint256(price_usd)}"
        f"{_encode_uint256(updated_at)}"
    )


def sign_update_eth_price(
    *,
    odyn: Any,
    contract_address: str,
    chain_id: int,
    rpc_url: str,
    request_id: int,
    price_usd: int,
    updated_at: int,
    broadcast: bool = False,
) -> Dict[str, Any]:
    """Build, sign and optionally broadcast updateEthPrice transaction."""
    if not contract_address:
        raise ValueError("Contract address is required")

    tee_address = odyn.eth_address()
    nonce = get_nonce(rpc_url, tee_address)
    fee_params = get_fee_params(rpc_url)

    data = encode_update_eth_price(request_id=request_id, price_usd=price_usd, updated_at=updated_at)

    tx_for_estimate = {
        "from": tee_address,
        "to": contract_address,
        "data": data,
        "value": "0x0",
    }
    gas_limit = estimate_gas(rpc_url, tx_for_estimate)

    tx = {
        "kind": "structured",
        "chain_id": hex(chain_id),
        "nonce": nonce,
        "max_priority_fee_per_gas": fee_params["max_priority_fee_per_gas"],
        "max_fee_per_gas": fee_params["max_fee_per_gas"],
        "gas_limit": gas_limit,
        "to": contract_address,
        "value": "0x0",
        "data": data,
    }

    signed = odyn.sign_tx(tx)
    result: Dict[str, Any] = {
        "raw_transaction": signed.get("raw_transaction"),
        "transaction_hash": signed.get("transaction_hash"),
        "address": signed.get("address"),
    }

    if broadcast:
        try:
            rpc_tx_hash = _rpc_call(rpc_url, "eth_sendRawTransaction", [result["raw_transaction"]])
            result["broadcasted"] = True
            result["rpc_tx_hash"] = rpc_tx_hash
        except Exception as e:
            result["broadcasted"] = False
            result["broadcast_error"] = str(e)

    return result


def sign_update_state_hash(
    *,
    odyn: Any,
    contract_address: str,
    chain_id: int,
    rpc_url: str,
    state_hash: str,
    broadcast: bool = False,
) -> Dict[str, Any]:
    """Build, sign and optionally broadcast updateStateHash transaction."""
    if not contract_address:
        raise ValueError("Contract address is required")

    tee_address = odyn.eth_address()
    nonce = get_nonce(rpc_url, tee_address)
    fee_params = get_fee_params(rpc_url)

    data = encode_update_state_hash(state_hash)

    tx_for_estimate = {
        "from": tee_address,
        "to": contract_address,
        "data": data,
        "value": "0x0",
    }
    gas_limit = estimate_gas(rpc_url, tx_for_estimate)

    tx = {
        "kind": "structured",
        "chain_id": hex(chain_id),
        "nonce": nonce,
        "max_priority_fee_per_gas": fee_params["max_priority_fee_per_gas"],
        "max_fee_per_gas": fee_params["max_fee_per_gas"],
        "gas_limit": gas_limit,
        "to": contract_address,
        "value": "0x0",
        "data": data,
    }

    signed = odyn.sign_tx(tx)
    result: Dict[str, Any] = {
        "raw_transaction": signed.get("raw_transaction"),
        "transaction_hash": signed.get("transaction_hash"),
        "address": signed.get("address"),
    }

    if broadcast:
        try:
            rpc_tx_hash = _rpc_call(rpc_url, "eth_sendRawTransaction", [result["raw_transaction"]])
            result["broadcasted"] = True
            result["rpc_tx_hash"] = rpc_tx_hash
        except Exception as e:
            result["broadcasted"] = False
            result["broadcast_error"] = str(e)

    return result
