import asyncio
import logging
from typing import List, Optional

import uvicorn
from web3 import Web3
from web3.contract import Contract
from eth_account.signers.local import LocalAccount
from fastapi import FastAPI, HTTPException
from fastapi.requests import Request

from config import Config
from enclave import Enclave


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)


class RandomNumberGenerator:
    def __init__(self):
        # Web3 connection
        self.w3 = Web3(Web3.HTTPProvider(Config.RPC_URL))

        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to {Config.RPC_URL}")

        self.chain_id = self.w3.eth.chain_id
        logging.info(f"✅ Connected to chain ID: {self.chain_id}")

        # Contract
        self.contract_address = Web3.to_checksum_address(Config.CONTRACT_ADDRESS)
        self.contract: Contract = self.w3.eth.contract(
            address=self.contract_address,
            abi=Config.CONTRACT_ABI,
        )

        # Operator account
        self.operator: LocalAccount = Config.OPERATOR
        logging.info(f"🔑 Operator: {self.operator.address}")

        # Check balance
        balance = self.w3.eth.get_balance(self.operator.address)
        logging.info(f"💰 Operator balance: {Web3.from_wei(balance, 'ether')} ETH")

        if balance == 0:
            logging.warning("⚠️  Operator has zero balance!")

        # Verify operator permission
        self.is_operator = self.contract.functions.isOperator(self.operator.address).call()
        if not self.is_operator:
            logging.info("✅ Operator authorized")

        # Processed requests (prevent duplicates)
        self.processed_requests = set()

        self.app = FastAPI(
            title="Random Number Generator Service",
            description="Off-chain service for generating and fulfilling random numbers",
            version="1.0.0"
        )
        self.init_router()
        self.enclaver = Enclave()

    def init_router(self):
        self.app.add_api_route("/", self.status, methods=["GET"])
        self.app.add_api_route("/request/{request_id}", self.request_info, methods=["GET"])

        self.app.add_event_handler("startup", self.run)

    async def status(self, req: Request):
        return {
            "service": "Random Number Generator",
            "version": "1.0.0",
            "status": "running",
            "is_operator": self.is_operator,
            "contract_address": self.contract_address,
            "operator": self.operator.address,
            "operator_balance": round(self.w3.eth.get_balance(self.operator.address) / 1e18, 6),
            "processed_requests": len(self.processed_requests),
            "explorer": f"https://sepolia.basescan.org/address/{self.contract_address}"
        }

    async def request_info(self, request_id):
        return self.get_request_info(int(request_id))

    def get_request_info(self, request_id: int) -> dict:
        """Get request information from contract"""
        try:
            request = self.contract.functions.getRequest(request_id).call()

            status_names = ["Pending", "Fulfilled", "Cancelled"]

            return {
                "request_id": request_id,
                "status": status_names[request[0]],
                "random_numbers": request[1],
                "requester": request[2],
                "timestamp": request[3],
                "fulfilled_at": request[4],
                "callback_contract": request[5] if request[5] != '0x0000000000000000000000000000000000000000' else None,
                "callback_executed": request[6],
                "min_val": request[7],
                "max_val": request[8],
                "count": request[9]
            }
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Request not found: {e}")

    async def fulfill_random_number(
            self,
            request_id: int,
            random_numbers: List[int]
    ) -> Optional[str]:
        """
        Fulfill random number to contract

        Args:
            request_id: Request ID
            random_numbers: List of random numbers

        Returns:
            Transaction hash
        """
        try:
            # Get nonce
            nonce = self.w3.eth.get_transaction_count(self.operator.address)

            # Build transaction function
            function = self.contract.functions.fulfillRandomNumber(
                request_id,
                random_numbers
            )

            # Estimate gas
            try:
                gas_estimate = function.estimate_gas({"from": self.operator.address})
                gas_limit = int(gas_estimate * 1.2)  # Add 20% buffer
            except Exception as e:
                logging.warning(f"⚠️  Gas estimation failed: {e}, using default")
                gas_limit = 300000

            # Get gas price
            gas_price = self.w3.eth.gas_price

            # Build transaction
            transaction = function.build_transaction({
                "from": self.operator.address,
                "nonce": nonce,
                "gas": gas_limit,
                "gasPrice": gas_price,
                "chainId": self.chain_id,
            })

            # Sign transaction
            signed_txn = self.w3.eth.account.sign_transaction(
                transaction,
                private_key=self.operator.key
            )

            # Send transaction
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            tx_hash_hex = tx_hash.hex()

            logging.info(f"📤 Fulfilling request {request_id}, tx: {tx_hash_hex}")

            # Wait for confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt.status == 1:
                logging.info(f"✅ Request {request_id} fulfilled successfully!")
                logging.info(f"   Gas used: {receipt.gasUsed}")
            else:
                logging.error(f"❌ Transaction failed for request {request_id}")

            return tx_hash_hex

        except Exception as e:
            logging.error(f"❌ Error fulfilling request {request_id}: {e}")
            raise

    async def handle_random_requested_event(self, event: dict):
        """
        Handle RandomNumberRequested event

        Args:
            event: Event data
        """
        args = event['args']
        request_id = args['requestId']
        requester = args['requester']
        min_val = args['min']
        max_val = args['max']
        count = args['count']
        callback_contract = args['callbackContract']
        timestamp = args['timestamp']

        logging.info("=" * 70)
        logging.info(f"📥 New Random Request Detected!")
        logging.info(f"   Request ID:       {request_id}")
        logging.info(f"   Requester:        {requester}")
        logging.info(f"   Range:            [{min_val}, {max_val})")
        logging.info(f"   Count:            {count}")
        logging.info(
            f"   Callback:         {callback_contract if callback_contract != '0x0000000000000000000000000000000000000000' else 'None'}")
        logging.info(f"   Timestamp:        {timestamp}")

        # Check if already processed
        if request_id in self.processed_requests:
            logging.warning(f"⚠️  Request {request_id} already processed, skipping")
            return

        # Check request status
        try:
            request = self.contract.functions.getRequest(request_id).call()
            status = request[0]  # RequestStatus

            if status != 0:  # 0 = Pending
                logging.warning(f"⚠️  Request {request_id} is not pending (status={status}), skipping")
                return
        except Exception as e:
            logging.error(f"❌ Error checking request status: {e}")
            return

        # set seed first
        self.enclaver.set_random_seed()
        # Generate random numbers
        random_numbers = self.enclaver.generate_random_numbers(min_val, max_val, count)

        # Fulfill to contract
        try:
            tx_hash = await self.fulfill_random_number(request_id, random_numbers)

            # Mark as processed
            self.processed_requests.add(request_id)

            logging.info(f"   Random Numbers:   {random_numbers}")
            logging.info(f"   Tx Hash:          {tx_hash}")

        except Exception as e:
            logging.error(f"❌ Failed to fulfill request {request_id}: {e}")

        logging.info("=" * 70)

    async def listen_for_events(self, poll_interval: int = 2):
        """
        Listen for RandomNumberRequested events

        Args:
            poll_interval: Polling interval (seconds)
        """
        logging.info("👂 Starting to listen for RandomNumberRequested events...")
        logging.info(f"   Contract: {self.contract_address}")
        logging.info(f"   Poll Interval: {poll_interval}s")

        # Create event filter (from specified block)
        event_filter = self.contract.events.RandomNumberRequested.create_filter(
            from_block=Config.FROM_BLOCK
        )

        logging.info("✅ Event filter created, listening for events...\n")

        while True:
            try:
                if not self.is_operator:
                    self.is_operator = self.contract.functions.isOperator(self.operator.address).call()
                    logging.info("Wait for register operator...")
                else:
                    # Get new events
                    events = event_filter.get_new_entries()

                    for event in events:
                        await self.handle_random_requested_event(event)

                # Wait before checking again
                await asyncio.sleep(poll_interval)

            except Exception as e:
                logging.error(f"❌ Error in event loop: {e}")
                await asyncio.sleep(poll_interval * 2)

    async def run(self):
        """Run service"""
        logging.info("\n" + "=" * 70)
        logging.info("🚀 RNG Off-Chain Service Starting...")
        logging.info("=" * 70)
        logging.info(f"Contract:  {self.contract_address}")
        logging.info(f"Operator:  {self.operator.address}")
        logging.info(f"Chain ID:  {self.chain_id}")
        logging.info("=" * 70 + "\n")

        # Start listening for events
        asyncio.create_task(self.listen_for_events())


def main():
    # Create RNG service
    try:
        rng_service = RandomNumberGenerator()

        # Run service
        uvicorn.run(
            rng_service.app,
            log_level="info",
            workers=1
        )

    except KeyboardInterrupt:
        logging.info("\n👋 Shutting down gracefully...")
    except Exception as e:
        logging.error(f"❌ Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()
