import json
import logging
import threading
import time
from typing import List, Dict, Any, Optional
from odyn import Odyn
from chain import Chain

logger = logging.getLogger(__name__)

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
        self.pending_echoes: List[Dict[str, Any]] = []

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        
        # Load last block from S3
        saved_block = self.odyn.s3_get("last_block")
        if saved_block:
            self.last_block = int(saved_block.decode())
            self.persisted_block = self.last_block
            logger.info(f"Resuming from block {self.last_block}")
        else:
            self.last_block = self.chain.get_latest_block()
            logger.info(f"Starting from current block {self.last_block}")

        # Load pending echoes from S3
        saved_pending = self.odyn.s3_get("pending_echoes")
        if saved_pending:
            try:
                self.pending_echoes = json.loads(saved_pending.decode())
                logger.info(f"Loaded {len(self.pending_echoes)} pending echoes from S3")
            except Exception as e:
                logger.error(f"Failed to parse pending echoes: {e}")

        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def _save_pending(self):
        """Persist pending echoes list to S3."""
        try:
            data = json.dumps(self.pending_echoes).encode()
            self.odyn.s3_put("pending_echoes", data)
        except Exception as e:
            logger.error(f"Failed to save pending echoes to S3: {e}")

    def _clear_pending(self) -> bool:
        """Attempt to clear all pending echoes. Returns True if all cleared."""
        if not self.pending_echoes:
            return True
            
        logger.info(f"Attempting to clear {len(self.pending_echoes)} pending echoes")
        
        # We process a copy so we can modify the original list
        for tx in list(self.pending_echoes):
            success = self._echo_transfer(tx)
            if success:
                # Remove from list and update S3 immediately
                # Note: We match by hash to be safe
                self.pending_echoes = [p for p in self.pending_echoes if p['incoming_hash'] != tx['incoming_hash']]
                self._save_pending()
            else:
                # Failed or skipped (if skip didn't count as success)
                # For this app, we'll treat "skipped due to value" as success so it doesn't block forever
                return False
        return True

    def _run(self):
        while self.is_running:
            try:
                # 1. Always try to clear pending echoes first (from previous runs or current scan)
                if not self._clear_pending():
                    logger.warning("Pending echoes still remaining, will retry in 10s")
                    time.sleep(10)
                    continue

                # 2. Advance blocks
                current_block = self.chain.get_latest_block()
                
                if current_block > self.last_block:
                    for b in range(self.last_block + 1, current_block + 1):
                        # 3. Identify and stage transfers for block b
                        if self._process_block(b):
                            # Advance block only if all transfers in it were handled
                            self.last_block = b
                            if self.odyn.s3_put("last_block", str(b).encode()):
                                self.persisted_block = b
                        else:
                            # Something in this block failed to echo, stop advancement
                            logger.warning(f"Failed to fully process block {b}, stopping advancement")
                            break 
                
                time.sleep(10) # Poll every 10 seconds
            except Exception as e:
                logger.error(f"Error in background task: {e}")
                time.sleep(10)

    def _process_block(self, block_number: int) -> bool:
        """Identifies transfers in a block and adds them to the pending queue."""
        logger.info(f"Scanning block {block_number}")
        txs = self.chain.get_block_transactions(block_number)
        
        found_any = False
        for tx in txs:
            # Check if transaction is to the enclave address and has value
            if tx.get('to') and tx['to'].lower() == self.address.lower() and tx['value'] > 0:
                # Skip if the sender is the enclave itself to avoid loops
                if tx.get('from') and tx['from'].lower() == self.address.lower():
                    logger.info("Skipping self-transfer")
                    continue
                
                # Prepare pending item
                raw_hash = tx['hash']
                tx_hash = raw_hash.hex() if hasattr(raw_hash, 'hex') else str(raw_hash)
                
                # Check if already in pending (unlikely in one block, but safe)
                if any(p['incoming_hash'] == tx_hash for p in self.pending_echoes):
                    continue
                    
                pending_item = {
                    "incoming_hash": tx_hash,
                    "from": str(tx['from']),
                    "value": int(tx['value']),
                    "block_number": block_number
                }
                self.pending_echoes.append(pending_item)
                found_any = True

        if found_any:
            self._save_pending()
            
        # Try to clear immediately
        return self._clear_pending()

    def _echo_transfer(self, incoming_tx: Dict[str, Any]) -> bool:
        """Performs the actual echo. Returns True if handled (success or non-retryable skip)."""
        try:
            # Standardize inputs
            from_address = str(incoming_tx['from'])
            received_value = int(incoming_tx['value'])
            tx_hash = incoming_tx['incoming_hash']
            
            logger.info(f"Echoing transfer: {received_value} wei from {from_address} (hash: {tx_hash})")

            # Estimate fees
            priority_fee, max_fee = self.chain.estimate_fees()
            gas_limit = 21000 # Standard transfer
            gas_cost = gas_limit * max_fee
            
            if received_value <= gas_cost:
                logger.warning(f"Received value {received_value} is less than gas cost {gas_cost}, skipping echo")
                # Record as success because we handled it (no point retrying)
                self._record_history(incoming_tx, None, "skipped", "Value less than gas cost")
                return True

            echo_value = received_value - gas_cost
            nonce = self.chain.get_nonce(self.address)
            
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

            # Sign via Odyn
            signed_tx = self.odyn.sign_tx(tx_params)
            
            # Broadcast
            echo_hash = self.chain.send_raw_transaction(signed_tx["raw_transaction"])
            logger.info(f"Echoed transfer! Hash: {echo_hash}")

            # Update history
            self._record_history(incoming_tx, echo_hash, "success", f"Echoed {echo_value} wei")
            self.processed_count += 1
            return True
            
        except Exception as e:
            logger.error(f"Failed to echo transfer: {e}")
            # Do NOT record in history here, as we want to retry it in the pending queue
            # (Unless it's a known non-retryable error, but let's be safe and always retry)
            return False

    def _record_history(self, incoming_tx: Dict[str, Any], echo_hash: Optional[str], status: str, detail: str = ""):
        """Internal helper to log events to the memory history."""
        event = {
            "incoming_hash": incoming_tx["incoming_hash"],
            "from": incoming_tx["from"],
            "value": str(incoming_tx["value"]),
            "echo_hash": echo_hash,
            "echo_value": detail, # Storing detail string or value
            "timestamp": int(time.time()),
            "status": status
        }
        self.history.insert(0, event)
        if len(self.history) > 100:
            self.history.pop()
