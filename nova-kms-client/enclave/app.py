"""
Nova KMS Client - Example Application
"""
import asyncio
import base64
import logging
import time
import random
from collections import deque
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

import httpx
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

import config
from odyn import Odyn
from kms_registry import KMSRegistryClient
from nova_registry import NovaRegistry

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("nova-kms-client")

# In-memory log storage (keep last N entries)
MAX_LOGS = 20
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
        self._kms_wallet_cache: Dict[str, str] = {}  # base_url -> kms_wallet

        def _is_zero_address(addr: Optional[str]) -> bool:
            if not addr:
                return True
            a = addr.strip().lower()
            return a == "0x" + "0" * 40

        if _is_zero_address(getattr(config, "KMS_REGISTRY_ADDRESS", "")):
            raise RuntimeError(
                "KMS_REGISTRY_ADDRESS must be configured in enclave/config.py (registry-only client)."
            )
        if _is_zero_address(getattr(config, "NOVA_APP_REGISTRY_ADDRESS", "")):
            raise RuntimeError(
                "NOVA_APP_REGISTRY_ADDRESS must be configured in enclave/config.py (registry-only client)."
            )
        
        # Initialize on-chain registry clients
        try:
            self.kms_registry = KMSRegistryClient(address=config.KMS_REGISTRY_ADDRESS)
            self.nova_registry = NovaRegistry(address=config.NOVA_APP_REGISTRY_ADDRESS)
                
        except Exception as e:
             logger.error(f"Failed to initialize registries: {e}")
             raise

    async def get_operators(self) -> List[str]:
        if not self.kms_registry:
            return []
        return await asyncio.to_thread(self.kms_registry.get_operators)

    async def get_instance(self, operator_wallet: str):
        if not self.nova_registry:
            return None
        return await asyncio.to_thread(self.nova_registry.get_instance_by_wallet, operator_wallet)

    @staticmethod
    def _ensure_http(url: str) -> str:
        if not url:
            return url
        u = url.strip()
        if u.startswith("http://") or u.startswith("https://"):
            return u
        return f"http://{u}"

    async def _probe_health(self, client: httpx.AsyncClient, base_url: str) -> dict:
        start = time.time()
        try:
            r = await client.get(f"{base_url.rstrip('/')}/health")
            return {
                "connected": r.status_code == 200,
                "http_status": r.status_code,
                "probe_ms": int((time.time() - start) * 1000),
            }
        except Exception as exc:
            return {
                "connected": False,
                "http_status": None,
                "probe_ms": int((time.time() - start) * 1000),
                "error": str(exc),
            }

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
        
        # Fetch KMS wallet (cached per node)
        kms_wallet = self._kms_wallet_cache.get(base_url)
        if not kms_wallet:
            status_resp = await client.get(f"{base_url}/status")
            status_resp.raise_for_status()
            kms_wallet = status_resp.json()["node"]["tee_wallet"]
            self._kms_wallet_cache[base_url] = kms_wallet

        # Message format: NovaKMS:AppAuth:<Nonce>:<KMS_Wallet>:<Timestamp>
        message = f"NovaKMS:AppAuth:{nonce_b64}:{kms_wallet}:{ts}"
        
        # Sign with Odyn (auto-selects local vs enclave signing)
        sig_res = self.odyn.sign_message(message)
        signature = sig_res["signature"]

        headers = {
            "X-App-Signature": signature,
            "X-App-Nonce": nonce_b64,
            "X-App-Timestamp": ts,
            "X-App-Wallet": wallet, # Optional hint
            # In nova-kms dev/sim mode, identity is taken from header shims.
            # Sending this alongside PoP keeps the client compatible with both
            # dev/sim and production behavior.
            "x-tee-wallet": wallet,
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
        """Scan all operators and verify consistency + sync.

        Cycle:
          1) Fetch operators from KMSRegistry
          2) Fetch each operator's instance from NovaAppRegistry
          3) For ACTIVE instances, probe /health
          4) For reachable instances, request a fixed /kms/derive and compare results
          5) Randomly choose one reachable instance, write /kms/data with timestamp
          6) Read that key from all reachable instances and report consistency
        """
        from nova_registry import InstanceStatus

        fixed_path = "nova-kms-client/fixed-derive"
        data_key = "nova-kms-client/timestamp"
        ts_value = str(int(time.time()))
        ts_b64 = base64.b64encode(ts_value.encode("utf-8")).decode("utf-8")

        try:
            operators = await self.get_operators()
            if not operators:
                self._log("Scan", "Failed", error="No operators found in KMS registry")
                return

            results: List[dict] = []
            reachable: List[dict] = []
            expected_key: Optional[str] = None

            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1) Resolve instances
                for op in operators:
                    row: dict = {
                        "operator": op,
                        "instance": None,
                        "connection": {"connected": False},
                        "derive": None,
                        "data": None,
                    }
                    try:
                        inst = await self.get_instance(op)
                        if inst is None:
                            row["instance"] = {"error": "instance lookup unavailable"}
                            results.append(row)
                            continue

                        inst_url = self._ensure_http(getattr(inst, "instance_url", ""))
                        inst_status = getattr(inst, "status", None)
                        row["instance"] = {
                            "instance_id": getattr(inst, "instance_id", None),
                            "app_id": getattr(inst, "app_id", None),
                            "version_id": getattr(inst, "version_id", None),
                            "operator": getattr(inst, "operator", None),
                            "instance_url": inst_url,
                            "tee_wallet": getattr(inst, "tee_wallet_address", None),
                            "zk_verified": getattr(inst, "zk_verified", None),
                            "status": {
                                "value": getattr(inst_status, "value", inst_status),
                                "name": getattr(inst_status, "name", str(inst_status)),
                            },
                        }

                        # 2) Only probe/operate on ACTIVE instances
                        if inst_status != InstanceStatus.ACTIVE or not inst_url:
                            results.append(row)
                            continue

                        probe = await self._probe_health(client, inst_url)
                        row["connection"] = probe
                        if not probe.get("connected"):
                            results.append(row)
                            continue

                        # 3) Derive fixed key and compare across nodes
                        try:
                            resp = await self._signed_request(
                                client,
                                "POST",
                                f"{inst_url.rstrip('/')}/kms/derive",
                                json={"path": fixed_path},
                            )
                            resp.raise_for_status()
                            body = resp.json()
                            key_b64 = body.get("key")
                            if expected_key is None and key_b64:
                                expected_key = key_b64
                            row["derive"] = {
                                "path": fixed_path,
                                "key": key_b64,
                                "matches_cluster": (expected_key == key_b64) if expected_key else None,
                                "http_status": resp.status_code,
                            }
                        except Exception as exc:
                            row["derive"] = {"error": str(exc)}

                        reachable.append({"operator": op, "url": inst_url})
                        results.append(row)
                    except Exception as exc:
                        row["instance"] = {"error": str(exc)}
                        results.append(row)

                # 4) Write timestamp KV to one reachable node
                write_result: dict = {"performed": False}
                if reachable:
                    target = random.choice(reachable)
                    write_result = {
                        "performed": True,
                        "node_url": target["url"],
                        "key": data_key,
                        "timestamp": ts_value,
                    }
                    try:
                        resp = await self._signed_request(
                            client,
                            "PUT",
                            f"{target['url'].rstrip('/')}/kms/data",
                            json={"key": data_key, "value": ts_b64, "ttl_ms": 0},
                        )
                        resp.raise_for_status()
                        write_result["http_status"] = resp.status_code
                    except Exception as exc:
                        write_result["error"] = str(exc)

                # 5) Read from all reachable nodes (retry on 404 to allow sync)
                for row in results:
                    inst = row.get("instance") or {}
                    url = inst.get("instance_url")
                    if not url or not row.get("connection", {}).get("connected"):
                        continue
                    read_info: dict = {"key": data_key}
                    try:
                        last_exc: Optional[Exception] = None
                        for _ in range(3):
                            try:
                                r = await self._signed_request(
                                    client,
                                    "GET",
                                    f"{url.rstrip('/')}/kms/data/{data_key}",
                                )
                                if r.status_code == 404:
                                    await asyncio.sleep(1)
                                    continue
                                r.raise_for_status()
                                payload = r.json()
                                val_b64 = payload.get("value")
                                val = base64.b64decode(val_b64).decode("utf-8") if val_b64 else None
                                read_info.update({
                                    "http_status": r.status_code,
                                    "value": val,
                                    "matches_written": (val == ts_value) if write_result.get("performed") else None,
                                })
                                last_exc = None
                                break
                            except Exception as exc:
                                last_exc = exc
                                await asyncio.sleep(1)
                        if last_exc is not None:
                            raise last_exc
                    except Exception as exc:
                        read_info["error"] = str(exc)
                    row["data"] = read_info

            # 6) Summarize
            mismatched_keys = [
                r for r in results
                if r.get("derive")
                and isinstance(r["derive"], dict)
                and r["derive"].get("matches_cluster") is False
            ]
            reads_missing = [
                r for r in results
                if r.get("connection", {}).get("connected")
                and (not r.get("data") or r["data"].get("matches_written") is False)
            ]
            overall = "Success" if (not mismatched_keys and not reads_missing) else "Partial"

            self._log(
                "ScanSummary",
                overall,
                details={
                    "operator_count": len(operators),
                    "reachable_count": len(reachable),
                    "fixed_derive_path": fixed_path,
                    "expected_derived_key": expected_key,
                    "write": write_result,
                    "results": results,
                },
            )
        except Exception as exc:
            logger.error(f"Scan cycle failed: {exc}")
            self._log("ScanSummary", "Failed", error=str(exc))

    def _log(self, action: str, status: str, kms_node_url: str = "N/A", details: Optional[Dict] = None, error: Optional[str] = None):
        entry = LogEntry(
            timestamp_ms=int(time.time() * 1000),
            kms_node_url=kms_node_url,
            action=action,
            status=status,
            details=details,
            error=error
        )
        request_logs.appendleft(entry.model_dump()) # Newest first
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


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/logs")
def get_logs():
    return list(request_logs)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
