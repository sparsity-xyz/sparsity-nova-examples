#!/usr/bin/env python3
"""
BTC Price Oracle - Uses EIP-4337 Account Abstraction for gas sponsorship.
"""

import json
import time
import threading
import logging
import requests
from flask import Flask, jsonify
from eth_utils import to_checksum_address
from eth_abi import encode
from web3 import Web3

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

ODYN_API = "http://127.0.0.1:9000"

config = {}
w3 = None

CONTRACT_ABI = [
    {"inputs": [{"name": "_price", "type": "uint256"}], "name": "setPrice", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [], "name": "getPrice", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "btcPrice", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
]

FACTORY_ABI = [
    {"inputs": [{"name": "agentId", "type": "uint256"}, {"name": "operator", "type": "address"}], "name": "getWalletAddress", "outputs": [{"name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
]

def load_config():
    global config, w3
    with open("/app/config.json", "r") as f:
        config = json.load(f)
    w3 = Web3(Web3.HTTPProvider(config["rpc_url"]))

def get_enclave_address():
    response = requests.get(f"{ODYN_API}/v1/eth/address")
    response.raise_for_status()
    return response.json()["address"]

def get_wallet_address(operator_address):
    """Get 4337 wallet address from factory."""
    factory = w3.eth.contract(
        address=to_checksum_address(config["wallet_factory"]),
        abi=FACTORY_ABI
    )
    # Using agentId=0 for now - in production this would come from registration
    return factory.functions.getWalletAddress(0, to_checksum_address(operator_address)).call()

def fetch_btc_price():
    response = requests.get(config["coingecko_url"])
    response.raise_for_status()
    data = response.json()
    return int(data["bitcoin"]["usd"] * 100)

def get_contract_price():
    if not config.get("contract_address"):
        return None
    contract = w3.eth.contract(
        address=to_checksum_address(config["contract_address"]),
        abi=CONTRACT_ABI
    )
    return contract.functions.getPrice().call()

def pack_user_op(user_op):
    """Pack UserOperation for hashing (EIP-4337 v0.7 format)."""
    init_code = bytes.fromhex(user_op.get("factory", "")[2:] + user_op.get("factoryData", "")[2:]) if user_op.get("factory") else b""
    account_gas_limits = (int(user_op["verificationGasLimit"], 16) << 128) | int(user_op["callGasLimit"], 16)
    gas_fees = (int(user_op["maxPriorityFeePerGas"], 16) << 128) | int(user_op["maxFeePerGas"], 16)
    paymaster_and_data = bytes.fromhex(
        user_op.get("paymaster", "")[2:] +
        format(int(user_op.get("paymasterVerificationGasLimit", "0x0"), 16), '032x') +
        format(int(user_op.get("paymasterPostOpGasLimit", "0x0"), 16), '032x') +
        user_op.get("paymasterData", "")[2:]
    ) if user_op.get("paymaster") else b""

    packed = encode(
        ['address', 'uint256', 'bytes32', 'bytes32', 'bytes32', 'uint256', 'bytes32', 'bytes32'],
        [
            to_checksum_address(user_op["sender"]),
            int(user_op["nonce"], 16),
            Web3.keccak(init_code),
            Web3.keccak(bytes.fromhex(user_op["callData"][2:])),
            account_gas_limits.to_bytes(32, 'big'),
            int(user_op["preVerificationGas"], 16),
            gas_fees.to_bytes(32, 'big'),
            Web3.keccak(paymaster_and_data)
        ]
    )
    return packed

def get_user_op_hash(user_op):
    """Calculate UserOperation hash."""
    packed = pack_user_op(user_op)
    entry_point = to_checksum_address(config["entry_point"])
    chain_id = config["chain_id"]

    op_hash = Web3.keccak(packed)
    final_hash = Web3.keccak(encode(['bytes32', 'address', 'uint256'], [op_hash, entry_point, chain_id]))
    return final_hash.hex()

def get_private_key():
    """Get private key from enclave."""
    response = requests.get(f"{ODYN_API}/v1/eth/private_key")
    response.raise_for_status()
    return response.json()["private_key"]

def sign_hash(hash_hex):
    """Sign a hash using local key from enclave (as Ethereum signed message)."""
    from eth_account import Account
    from eth_account.messages import encode_defunct

    private_key = get_private_key()
    hash_bytes = bytes.fromhex(hash_hex[2:] if hash_hex.startswith("0x") else hash_hex)

    # Sign as Ethereum message (wallet uses toEthSignedMessageHash)
    message = encode_defunct(primitive=hash_bytes)
    signed = Account.sign_message(message, private_key)

    # Return signature in format: r + s + v
    sig_hex = signed.signature.hex()
    return sig_hex if sig_hex.startswith("0x") else "0x" + sig_hex

def send_user_op(user_op):
    """Send UserOperation to bundler."""
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_sendUserOperation",
        "params": [user_op, config["entry_point"]],
        "id": 1
    }
    logger.info(f"Sending UserOp: {json.dumps(user_op, indent=2)}")
    response = requests.post(config["bundler_url"], json=payload)
    if response.status_code != 200:
        raise Exception(f"Bundler HTTP {response.status_code}: {response.text}")
    result = response.json()
    if "error" in result:
        raise Exception(f"Bundler error: {result['error']}")
    return result["result"]

def update_price_on_chain():
    """Update price using 4337 UserOperation."""
    if not config.get("contract_address"):
        return {"error": "Contract address not configured"}

    price = fetch_btc_price()

    # Get addresses
    operator = to_checksum_address(get_enclave_address())
    sender = to_checksum_address(get_wallet_address(operator))

    # Check if wallet needs to be created (no code at address)
    wallet_code = w3.eth.get_code(sender)
    needs_init = len(wallet_code) == 0

    # Build call data for setPrice
    contract = w3.eth.contract(
        address=to_checksum_address(config["contract_address"]),
        abi=CONTRACT_ABI
    )
    call_data = contract.encodeABI(fn_name="setPrice", args=[price])

    # Wrap in execute call for the wallet
    execute_data = "0xb61d27f6" + encode(
        ['address', 'uint256', 'bytes'],
        [to_checksum_address(config["contract_address"]), 0, bytes.fromhex(call_data[2:])]
    ).hex()

    # Get nonce from entry point
    entry_point = w3.eth.contract(
        address=to_checksum_address(config["entry_point"]),
        abi=[{"inputs": [{"name": "sender", "type": "address"}, {"name": "key", "type": "uint192"}], "name": "getNonce", "outputs": [{"name": "nonce", "type": "uint256"}], "stateMutability": "view", "type": "function"}]
    )
    nonce = entry_point.functions.getNonce(sender, 0).call()

    # Get gas prices
    base_fee = w3.eth.get_block('latest')['baseFeePerGas']
    max_priority = w3.to_wei(1, 'gwei')
    max_fee = base_fee * 2 + max_priority

    # Set gas limits based on whether wallet exists
    if needs_init:
        verification_gas = 800000
        call_gas = 300000
    else:
        verification_gas = 50000
        call_gas = 80000

    # Build UserOperation
    user_op = {
        "sender": sender,
        "nonce": hex(nonce),
        "callData": execute_data,
        "callGasLimit": hex(call_gas),
        "verificationGasLimit": hex(verification_gas),
        "preVerificationGas": hex(50000),
        "maxFeePerGas": hex(max_fee),
        "maxPriorityFeePerGas": hex(max_priority),
        "paymaster": config["paymaster"],
        "paymasterVerificationGasLimit": hex(50000),
        "paymasterPostOpGasLimit": hex(50000),
        "paymasterData": "0x",
        "signature": "0x"
    }

    # Add factory/factoryData if wallet needs to be created
    if needs_init:
        # createAccount(uint256 agentId, address operator)
        factory_data = "0x114c63b1" + encode(
            ['uint256', 'address'],
            [0, operator]  # agentId=0 for testing
        ).hex()
        user_op["factory"] = config["wallet_factory"]
        user_op["factoryData"] = factory_data

    # Sign UserOp
    op_hash = get_user_op_hash(user_op)
    signature = sign_hash(op_hash)
    user_op["signature"] = signature

    # Send to bundler
    op_hash_result = send_user_op(user_op)

    return {
        "success": True,
        "price_cents": price,
        "price_usd": price / 100,
        "user_op_hash": op_hash_result,
        "wallet": sender
    }

def scheduled_update():
    while True:
        time.sleep(config.get("update_interval_seconds", 300))
        try:
            if config.get("contract_address"):
                result = update_price_on_chain()
                logger.info(f"Scheduled update: {result}")
        except Exception as e:
            logger.error(f"Scheduled update error: {e}")

@app.route('/')
def index():
    try:
        operator = get_enclave_address()
        wallet = get_wallet_address(operator)
        return jsonify({
            "status": "ok",
            "message": "BTC Price Oracle (4337)",
            "operator_address": operator,
            "wallet_address": wallet,
            "contract_address": config.get("contract_address", "not configured"),
            "paymaster": config.get("paymaster"),
            "endpoints": {
                "/price": "Get current BTC price from CoinGecko",
                "/update": "Trigger price update via UserOp",
                "/contract-price": "Read current price from contract"
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/price')
def price():
    try:
        price_cents = fetch_btc_price()
        return jsonify({"source": "coingecko", "price_cents": price_cents, "price_usd": price_cents / 100})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/update')
def update():
    try:
        result = update_price_on_chain()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/contract-price')
def contract_price():
    try:
        price = get_contract_price()
        if price is None:
            return jsonify({"error": "Contract address not configured"}), 400
        return jsonify({"source": "contract", "price_cents": price, "price_usd": price / 100})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    logger.info("Loading configuration...")
    load_config()
    logger.info("Starting BTC Price Oracle (4337)...")

    if config.get("contract_address"):
        update_thread = threading.Thread(target=scheduled_update, daemon=True)
        update_thread.start()
        logger.info(f"Scheduled updates every {config.get('update_interval_seconds', 300)} seconds")

    app.run(host='0.0.0.0', port=8000)
