"""
Verification script for nova-kms-client.
Simulates a running KMS environment and checks if the client can successfully interact with it.
"""
import sys
import os
import asyncio
import time
from unittest.mock import MagicMock, patch

# Add enclave directory to path
enclave_path = os.path.join(os.getcwd(), "enclave")
sys.path.append(enclave_path)

# Mock environment variables BEFORE importing config (for IN_ENCLAVE/SIMULATION_MODE)
os.environ["KMS_NODES_FALLBACK"] = "http://mock-kms:8000"
os.environ["IN_ENCLAVE"] = "false"
os.environ["SIMULATION_MODE"] = "true"

# Mock Key components BEFORE importing config
sys.modules["chain"] = MagicMock()
sys.modules["chain"].wait_for_helios = MagicMock()
sys.modules["chain"].function_selector = MagicMock()
sys.modules["chain"].encode_uint256 = MagicMock()
sys.modules["chain"].encode_address = MagicMock()
sys.modules["chain"].get_chain = MagicMock()

# Mock Web3
sys.modules["web3"] = MagicMock()
sys.modules["web3.exceptions"] = MagicMock()

# Import config first to ensure mocks are in place, then app
import config
# Patch fixed parameters for test
config.NOVA_APP_REGISTRY_ADDRESS = "0xMockNovaRegistry"
config.KMS_REGISTRY_ADDRESS = "0xMockKMSRegistry"

import app
from app import KMSClient, request_logs

async def run_verification():
    print("Starting verification...")
    
    # 1. Mock HTTPX Client
    mock_response_derive = MagicMock()
    mock_response_derive.status_code = 200
    mock_response_derive.json.return_value = {"key": "dGVzdF9rZXk="} # test_key base64

    mock_response_put = MagicMock()
    mock_response_put.status_code = 200
    mock_response_put.json.return_value = {"status": "ok"}

    mock_response_get = MagicMock()
    mock_response_get.status_code = 200
    mock_response_get.json.return_value = {"value": "SGVsbG8gTm92YSBLTVM="} # Hello Nova KMS base64

    mock_response_nonce = MagicMock()
    mock_response_nonce.status_code = 200
    mock_response_nonce.json.return_value = {"nonce": "MDAwMA=="} # 0000 base64
    
    mock_response_status = MagicMock()
    mock_response_status.status_code = 200
    mock_response_status.json.return_value = {"node": {"tee_wallet": "0xKMSWallet"}}

    async def mock_request(*args, **kwargs):
        method = "UNKNOWN"
        url = "UNKNOWN"
        
        # Heuristic to find method and url
        if len(args) >= 3:
             method = args[1]
             url = args[2]
        elif len(args) >= 2:
            if args[0] in ["GET", "POST", "PUT", "DELETE"]:
                method = args[0]
                url = args[1]
        
        if "method" in kwargs: method = kwargs["method"]
        if "url" in kwargs: url = kwargs["url"]

        if "nonce" in str(url):
            return mock_response_nonce
        if "status" in str(url):
            return mock_response_status
        if "derive" in str(url):
            return mock_response_derive
        if "data" in str(url) and method == "PUT":
            return mock_response_put
        if "data" in str(url) and method == "GET":
            return mock_response_get
        return MagicMock(status_code=404)

    # Patch httpx.AsyncClient.request
    with patch("httpx.AsyncClient.request", side_effect=mock_request) as mock_req:
                    
        # Run one cycle
        client = KMSClient()
        
        # Force nodes (skip discovery for this unit test)
        with patch.object(client, 'get_kms_nodes', return_value=["http://mock-kms:8000"]):
            await client.run_test_cycle()

    # Check logs
    print("\nVerification Results:")
    found_success = False
    for log in request_logs:
        print(f"[{log['status']}] {log['action']} - {log['error'] if log['error'] else 'OK'}")
        if log['status'] == 'Success':
            found_success = True
    
    if found_success:
        print("\nSUCCESS: Client successfully executed test cycle.")
        sys.exit(0)
    else:
        print("\nFAILURE: No successful operations found in logs.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_verification())
