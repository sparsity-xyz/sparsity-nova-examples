"""
Nova KMS Client - Example Application
"""
import asyncio
import base64
import logging
import os
import time
import random
from collections import deque
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

import httpx
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import config
from odyn import Odyn
from kms_registry import KMSRegistryClient
from nova_registry import NovaRegistry

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("nova-kms-client")

# In-memory log storage (last 100 entries)
MAX_LOGS = 100
request_logs = deque(maxlen=MAX_LOGS)

class LogEntry(BaseModel):
    timestamp_ms: int
    kms_node_url: str
    action: str
    status: str
    details: Optional[Dict] = None
    error: Optional[str] = None

class KMSClient:
    def __init__(self):
        self.odyn = Odyn()
        self.kms_registry: Optional[KMSRegistryClient] = None
        self.nova_registry: Optional[NovaRegistry] = None
        
        # Helper to get chain helpers initialized
        try:
            if config.KMS_REGISTRY_ADDRESS:
                self.kms_registry = KMSRegistryClient(address=config.KMS_REGISTRY_ADDRESS)
            else:
                logger.warning("KMS_REGISTRY_ADDRESS not set. KMS discovery disabled.")

            if config.NOVA_APP_REGISTRY_ADDRESS:
                self.nova_registry = NovaRegistry(address=config.NOVA_APP_REGISTRY_ADDRESS)
            else:
                logger.warning("NOVA_APP_REGISTRY_ADDRESS not set. Service discovery disabled.")
                
        except Exception as e:
             logger.error(f"Failed to initialize registries: {e}")

    async def get_kms_nodes(self) -> List[str]:
        """
        Discover KMS nodes via KMSRegistry -> NovaRegistry.
        Returns a list of URLs.
        """
        if not self.kms_registry or not self.nova_registry:
            # Fallback for local testing without chain config
            fallback = os.getenv("KMS_NODES_FALLBACK", "").split(",")
            if fallback and fallback[0]:
                return fallback
            return []

        try:
            operators = await asyncio.to_thread(self.kms_registry.get_operators)
            urls = []
            for op in operators:
                try:
                    instance = await asyncio.to_thread(self.nova_registry.get_instance_by_wallet, op)
                    if instance.instance_url:
                         # Ensure URL scheme
                        url = instance.instance_url
                        if not url.startswith("http"):
                             url = f"http://{url}"
                        urls.append(url)
                except Exception as e:
                    logger.warning(f"Failed to resolve operator {op}: {e}")
            return urls
        except Exception as e:
            logger.error(f"Error discovering KMS nodes: {e}")
            return []

    async def _signed_request(self, client: httpx.AsyncClient, method: str, url: str, json: Optional[dict] = None) -> httpx.Response:
        """
        Perform a request with full PoP authentication flow:
        1. GET /nonce from KMS node
        2. Sign (nonce + wallet + timestamp) using Odyn
        3. Send request with X-App-* headers
        """
        # 1. Get Nonce
        # Need base URL + /nonce. Assuming url passed is the full target endpoint.
        base_url = "/".join(url.split("/")[:3]) # http://host:port
        nonce_resp = await client.get(f"{base_url}/nonce")
        nonce_resp.raise_for_status()
        nonce_b64 = nonce_resp.json()["nonce"]
        
        # 2. Prepare PoP
        ts = str(int(time.time()))
        wallet = self.odyn.eth_address()
        
        # Message format: NovaKMS:AppAuth:<Nonce>:<KMS_Wallet>:<Timestamp>
        # Note: KMS_Wallet is the wallet of the KMS node we are calling.
        # We need to fetch the KMS node's wallet from /status or assume valid based on registry.
        # However, looking at auth.py in nova-kms, the message format is:
        # NovaKMS:AppAuth:<Nonce>:<KMS_Wallet>:<Timestamp>
        # The verify logic checks if `_node_wallet` (KMS's own wallet) matches the one in message?
        # Actually auth.py says:
        # message = f"NovaKMS:AppAuth:{nonce_b64}:{_node_wallet}:{ts}"
        # So the message MUST include the KMS node's wallet address.
        
        # We need to get the KMS node's wallet address first.
        status_resp = await client.get(f"{base_url}/status")
        status_resp.raise_for_status()
        kms_wallet = status_resp.json()["node"]["tee_wallet"]

        message = f"NovaKMS:AppAuth:{nonce_b64}:{kms_wallet}:{ts}"
        
        # 3. Sign
        # If running IN_ENCLAVE, use Odyn to sign.
        # If running locally (SIMULATION), we might need a fake signer or reliance on headers shim if enabled on server.
        # The user requested "real PoP authentication using odyn.py". 
        # odyn.py automatically handles local vs remote signing based on env.
        
        # odyn.sign_message returns {'signature': '0x...', 'recid': ...}
        sig_res = self.odyn.sign_message(message)
        signature = sig_res["signature"]

        headers = {
            "X-App-Signature": signature,
            "X-App-Nonce": nonce_b64,
            "X-App-Timestamp": ts,
            "X-App-Wallet": wallet, # Optional hint
            "Content-Type": "application/json"
        }
        
        # 4. Execute Request
        if method == "POST":
            return await client.post(url, json=json, headers=headers)
        elif method == "PUT":
            return await client.put(url, json=json, headers=headers)
        elif method == "GET":
            return await client.get(url, headers=headers)
        elif method == "DELETE":
             # httpx.delete doesn't accept json body in some versions, use client.request
             return await client.request("DELETE", url, json=json, headers=headers)
        else:
             raise ValueError(f"Unsupported method {method}")


    async def run_test_cycle(self):
        """
        Execute one test cycle:
        1. Discover nodes
        2. Pick one
        3. Derive key
        4. Write data
        5. Read data
        """
        try:
            nodes = await self.get_kms_nodes()
            if not nodes:
                self._log("Discovery", "Failed", error="No KMS nodes found")
                return

            node_url = random.choice(nodes)
            self._log("Discovery", "Success", details={"node": node_url})
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test 1: Derive Key
                try:
                    # KMS needs a path
                    path = "test/key/1"
                    resp = await self._signed_request(
                        client, 
                        "POST", 
                        f"{node_url}/kms/derive", 
                        json={"path": path}
                    )
                    resp.raise_for_status()
                    self._log("Derive Key", "Success", node_url, details=resp.json())
                except Exception as e:
                    self._log("Derive Key", "Failed", node_url, error=str(e))

                # Test 2: Data Put (Write)
                key = "test_data_key"
                value = base64.b64encode(b"Hello Nova KMS").decode()
                try:
                    resp = await self._signed_request(
                        client,
                        "PUT",
                        f"{node_url}/kms/data",
                        json={"key": key, "value": value, "ttl_ms": 60000}
                    )
                    resp.raise_for_status()
                    self._log("Write Data", "Success", node_url, details=resp.json())
                except Exception as e:
                    self._log("Write Data", "Failed", node_url, error=str(e))

                # Test 3: Data Get (Read)
                try:
                    resp = await self._signed_request(
                        client,
                        "GET",
                        f"{node_url}/kms/data/{key}"
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    # Decode value for display
                    decoded_value = base64.b64decode(data["value"]).decode()
                    self._log("Read Data", "Success", node_url, details={"key": key, "value": decoded_value})
                except Exception as e:
                    self._log("Read Data", "Failed", node_url, error=str(e))

        except Exception as e:
            logger.error(f"Test cycle failed: {e}")
            self._log("Loop", "Failed", error=str(e))

    def _log(self, action: str, status: str, kms_node_url: str = "N/A", details: Optional[Dict] = None, error: Optional[str] = None):
        entry = LogEntry(
            timestamp_ms=int(time.time() * 1000),
            kms_node_url=kms_node_url,
            action=action,
            status=status,
            details=details,
            error=error
        )
        request_logs.appendleft(entry.dict()) # Newest first
        logger.info(f"[{status}] {action} (Node: {kms_node_url}): {error if error else ''}")


# Initialize Client
kms_client = KMSClient()

# Initialize Scheduler
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Nova KMS Client...")
    
    # 1. Wait for Helios (if configured)
    from chain import wait_for_helios
    try:
        # Run in thread pool to avoid blocking async loop
        logger.info("Waiting for Helios sync...")
        await asyncio.to_thread(wait_for_helios, timeout=120)
        logger.info("Helios synced.")
    except Exception as e:
         logger.warning(f"Helios sync warning: {e}")

    # Verify Odyn connection
    try:
        addr = kms_client.odyn.eth_address()
        logger.info(f"Client TEE Identity: {addr}")
    except Exception as e:
        logger.error(f"Failed to connect to Odyn: {e}")
    
    scheduler.add_job(kms_client.run_test_cycle, 'interval', seconds=config.TEST_CYCLE_INTERVAL_SECONDS)
    scheduler.start()
    
    # Trigger one run immediately
    asyncio.create_task(kms_client.run_test_cycle())
    
    yield
    
    # Shutdown
    scheduler.shutdown()
    logger.info("Shutting down...")

app = FastAPI(title="Nova KMS Client", lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/logs")
def get_logs():
    return list(request_logs)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
