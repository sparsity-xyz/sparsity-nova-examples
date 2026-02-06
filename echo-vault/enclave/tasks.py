import json
import logging
import threading
import time
from typing import List, Dict, Any, Optional
from odyn import Odyn
from chain import Chain

logger = logging.getLogger(__name__)

class HistoryLimitExceeded(Exception):
    """Raised when the requested block is beyond the light client's historical buffer."""
    pass

class EchoTask:
    """Background task to poll for transfers and echo them back."""
    
    def __init__(self, odyn: Odyn, chain: Chain):
        self.odyn = odyn
        self.chain = chain
        self.address = odyn.eth_address()
        self.history: List[Dict[str, Any]] = []
        self.is_running = False
        self.last_block = 0
        self.persisted_block = 0
        self.processed_count = 0
        self.pending_hashes: List[str] = [] # Hashes currently in 'received' or 'failed' state
        
        # State management to reduce S3 frequency
        self._dirty = False
        self._last_save_at = 0
        self._save_interval = 60  # Save every 60 seconds if dirty
        self._block_checkpoint_interval = 200 # Only save last_block every 200 blocks if no txs

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        
        # 1. Load state from S3
        if not self._load_state():
            # Initial startup or migration
            saved_block = self.odyn.s3_get("last_block")
            if saved_block:
                self.last_block = int(saved_block.decode())
                self.persisted_block = self.last_block
                logger.info(f"Resuming from block {self.last_block} (legacy)")
            else:
                self.last_block = self.chain.get_latest_block()
                self.persisted_block = self.last_block
                logger.info(f"Starting from current block {self.last_block}")

            # 2. Recover history and pending hashes from S3 (Legacy migration)
            self._recover_state_from_s3_legacy()
            self._save_state() # Consolidate into state.json immediately

        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def _load_state(self) -> bool:
        """Load unified state from S3."""
        try:
            data = self.odyn.s3_get("state.json")
            if not data:
                return False
            
            state = json.loads(data.decode())
            self.last_block = state.get("last_block", 0)
            self.persisted_block = self.last_block
            self.processed_count = state.get("processed_count", 0)
            self.history = state.get("history", [])
            self.pending_hashes = state.get("pending_hashes", [])
            logger.info(f"Loaded state from S3: block={self.last_block}, history={len(self.history)}, pending={len(self.pending_hashes)}")
            return True
        except Exception as e:
            logger.error(f"Failed to load state.json: {e}")
            return False

    def _save_state(self, force: bool = False):
        """Save unified state to S3."""
        if not force and not self._dirty:
            return

        try:
            state = {
                "last_block": self.last_block,
                "processed_count": self.processed_count,
                "history": self.history,
                "pending_hashes": self.pending_hashes,
                "updated_at": int(time.time())
            }
            data = json.dumps(state).encode()
            if self.odyn.s3_put("state.json", data):
                self._dirty = False
                self._last_save_at = time.time()
                self.persisted_block = self.last_block
                logger.info(f"State persisted to S3 (block={self.last_block}, history={len(self.history)})")
        except Exception as e:
            logger.error(f"Failed to save state to S3: {e}")

    def _persist_if_dirty(self):
        """Persist state if dirty and enough time has passed."""
        if self._dirty and (time.time() - self._last_save_at > self._save_interval):
            self._save_state()

    def _mark_dirty(self):
        """Mark state as needing persistence."""
        self._dirty = True

    def _recover_state_from_s3_legacy(self):
        """Rebuild history and pending list by scanning S3 for transaction records (Legacy)."""
        try:
            logger.info("Recovering legacy state from echoes/ S3 prefix...")
            res = self.odyn.s3_list(prefix="echoes/")
            keys = res.get("keys", [])
            
            temp_history = []
            new_pending = []
            success_count = 0
            
            for key in keys:
                data = self.odyn.s3_get(key)
                if data:
                    try:
                        tx_data = json.loads(data.decode())
                        temp_history.append(tx_data)
                        if tx_data.get("status") in ["received", "failed"]:
                            new_pending.append(tx_data["incoming_hash"])
                        if tx_data.get("status") == "success":
                            success_count += 1
                    except Exception as e:
                        logger.error(f"Failed to parse transaction data for {key}: {e}")

            # Sort history by timestamp descending
            temp_history.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            self.history = temp_history[:100]
            self.pending_hashes = new_pending
            self.processed_count = success_count
            logger.info(f"Recovered {len(self.history)} history items and {len(self.pending_hashes)} pending transactions")
            
        except Exception as e:
            logger.error(f"Failed to recover legacy state: {e}")

    def _clear_pending(self) -> bool:
        """Attempt to clear all pending echoes. Returns True if all cleared."""
        if not self.pending_hashes:
            return True
            
        logger.info(f"Attempting to clear {len(self.pending_hashes)} pending echoes")
        
        try:
            current_nonce = self.chain.get_nonce(self.address)
        except Exception as e:
            logger.error(f"Failed to get nonce: {e}")
            return False

        for tx_hash in list(self.pending_hashes):
            tx_data = next((h for h in self.history if h["incoming_hash"] == tx_hash), None)
            if not tx_data:
                logger.warning(f"Pending hash {tx_hash} not found in memory, skipping")
                self.pending_hashes.remove(tx_hash)
                self._mark_dirty()
                continue

            tx_data.update({
                "status": "processing",
                "echo_value": "Preparing echo transaction...",
                "timestamp": int(time.time())
            })
            self._mark_dirty()

            success = self._echo_transfer(tx_data, current_nonce)
            if success:
                if tx_hash in self.pending_hashes:
                    self.pending_hashes.remove(tx_hash)
                if tx_data.get("status") == "success":
                    current_nonce += 1
                self._mark_dirty()
            else:
                return False
        return True

    def _run(self):
        while self.is_running:
            try:
                # 1. Advance blocks and identify new transfers
                current_block = self.chain.get_latest_block()
                
                if current_block > self.last_block:
                    for b in range(self.last_block + 1, current_block + 1):
                        try:
                            found_count = self._process_block(b)
                            self.last_block = b
                            if found_count > 0:
                                # Found transactions, mark dirty to save state soon
                                self._mark_dirty()
                            elif (self.last_block - self.persisted_block) >= self._block_checkpoint_interval:
                                # No transactions, but we've moved far enough to warrant a checkpoint
                                self._mark_dirty()
                            
                            # Keep catch-up logging minimal
                            if b % 100 == 0:
                                logger.info(f"Scanning: {b}/{current_block}")
                        except HistoryLimitExceeded:
                            logger.warning(f"Block {b} is old. Jumping to {current_block}.")
                            self.last_block = current_block
                            self._mark_dirty()
                            break
                
                # 2. Try to clear pending echoes
                if self.pending_hashes:
                    if not self._clear_pending():
                        logger.warning("Some echoes failed, will retry in 10s")
                        self._persist_if_dirty()
                        time.sleep(10)
                        continue

                # 3. Periodic persistence
                self._persist_if_dirty()
                
                time.sleep(2) # Poll every 2 seconds
            except Exception as e:
                logger.error(f"Error in background task: {e}")
                self._persist_if_dirty()
                time.sleep(2)

    def _process_block(self, block_number: int) -> int:
        """Identifies transfers in a block. Returns count of new transfers found."""
        try:
            txs = self.chain.get_block_transactions(block_number)
        except Exception as e:
            err_msg = str(e)
            if "outside eip-2935 ring buffer range" in err_msg.lower():
                raise HistoryLimitExceeded(err_msg)
            logger.error(f"Failed to fetch block {block_number}: {e}")
            return 0
            
        found_count = 0
        for tx in txs:
            if tx.get('to') and tx['to'].lower() == self.address.lower() and tx['value'] > 0:
                if tx.get('from') and tx['from'].lower() == self.address.lower():
                    continue
                
                raw_hash = tx['hash']
                tx_hash = raw_hash.hex() if hasattr(raw_hash, 'hex') else str(raw_hash)
                if not tx_hash.startswith("0x"):
                    tx_hash = f"0x{tx_hash}"
                
                if any(h['incoming_hash'] == tx_hash for h in self.history):
                    continue
                    
                tx_data = {
                    "incoming_hash": tx_hash,
                    "from": str(tx['from']),
                    "value": str(tx['value']),
                    "block_number": block_number,
                    "timestamp": int(time.time()),
                    "status": "received",
                    "echo_hash": None,
                    "echo_value": "Transfer detected",
                    "gas_fee": None
                }
                
                self.pending_hashes.append(tx_hash)
                self.history.insert(0, tx_data)
                if len(self.history) > 100:
                    self.history.pop()
                
                found_count += 1
                logger.info(f"New transfer detected: {tx_hash} ({tx['value']} wei)")

        return found_count

    def _echo_transfer(self, incoming_tx: Dict[str, Any], nonce: int) -> bool:
        """Performs the actual echo. Returns True if handled."""
        try:
            from_address = str(incoming_tx['from'])
            received_value = int(incoming_tx['value'])
            tx_hash = incoming_tx['incoming_hash']
            
            logger.info(f"Echoing transfer: {received_value} wei from {from_address}")

            current_balance = self.chain.get_balance(self.address)
            priority_fee, max_fee = self.chain.estimate_fees()
            gas_limit = 21000 
            
            estimated_gas_cost = gas_limit * max_fee
            safe_gas_cost = int(estimated_gas_cost * 1.1)
            
            if received_value <= safe_gas_cost:
                logger.warning(f"Received value {received_value} <= safe gas cost {safe_gas_cost}, skipping")
                incoming_tx.update({
                    "status": "skipped",
                    "echo_value": "Value less than gas cost",
                    "gas_fee": str(safe_gas_cost),
                    "timestamp": int(time.time())
                })
                self._mark_dirty()
                return True

            if current_balance < safe_gas_cost:
                logger.warning(f"Insufficient balance for gas: {current_balance} < {safe_gas_cost}")
                return False

            available_funds = min(received_value, current_balance)
            echo_value = available_funds - safe_gas_cost
            
            tx_params = {
                "kind": "structured",
                "chain_id": hex(self.chain.w3.eth.chain_id),
                "nonce": hex(nonce),
                "max_priority_fee_per_gas": hex(priority_fee),
                "max_fee_per_gas": hex(max_fee),
                "gas_limit": hex(gas_limit),
                "to": from_address,
                "value": hex(echo_value),
                "data": "0x"
            }
            
            signed_tx = self.odyn.sign_tx(tx_params)
            echo_hash = self.chain.send_raw_transaction(signed_tx["raw_transaction"])
            logger.info(f"Echoed! Hash: {echo_hash}")

            incoming_tx.update({
                "status": "success",
                "echo_hash": echo_hash,
                "echo_value": str(echo_value),
                "gas_fee": str(safe_gas_cost),
                "timestamp": int(time.time())
            })
            self.processed_count += 1
            self._mark_dirty()
            return True
            
        except Exception as e:
            error_msg = str(e)
            if "already known" in error_msg.lower():
                incoming_tx.update({
                    "status": "success",
                    "echo_value": "Already submitted",
                    "timestamp": int(time.time())
                })
                self._mark_dirty()
                return True
                
            logger.error(f"Failed to echo transfer: {error_msg}")
            incoming_tx.update({
                "status": "failed",
                "echo_value": error_msg,
                "timestamp": int(time.time())
            })
            self._mark_dirty()
            return False
