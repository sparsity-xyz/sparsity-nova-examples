import random

import httpx
from web3 import Web3


class Enclave:
    def __init__(self, endpoint="http://127.0.0.1:18000"):
        self.endpoint = endpoint

    def eth_address(self):
        res = httpx.get(f"{self.endpoint}/v1/eth/address")
        return res.json()["address"]

    def set_random_seed(self):
        res = httpx.get(f"{self.endpoint}/v1/random")
        seed = bytes.fromhex(res.json()["random_bytes"].removeprefix("0x"))
        random.seed(seed)

    def sign_tx(self, transaction_dict):
        """
        chain_id: String,
        nonce: String,
        max_priority_fee_per_gas: String,
        max_fee_per_gas: String,
        gas_limit: String,
        to: Option<String>,
        #[serde(default = "zero_hex_string")]
        value: String,
        #[serde(default = "empty_hex_string")]
        data: String,
        #[serde(default)]
        access_list: Vec<AccessListInput>,
        """
        res = httpx.post(f"{self.endpoint}/v1/eth/sign-tx", json={
            "payload": self.tx_to_payload(transaction_dict),
            "include_attestation": False
        })
        return res.json()

    @staticmethod
    def tx_to_payload(tx):
        return {
            "kind": "structured",
            "chain_id": hex(tx["chainId"]),
            "nonce": hex(tx["nonce"]),
            "max_priority_fee_per_gas": hex(tx["maxPriorityFeePerGas"]),
            "max_fee_per_gas": hex(tx["maxFeePerGas"]),
            "gas_limit": hex(tx["gas"]),
            "to": Web3.to_checksum_address(tx["to"]),
            "value": hex(tx.get("value", 0)),
            "data": tx["data"],
        }

    @staticmethod
    def generate_random_numbers(min_val: int, max_val: int, count: int):
        """
        Generate cryptographically secure random numbers

        Args:
            min_val: Minimum value (inclusive)
            max_val: Maximum value (exclusive)
            count: Number of random numbers

        Returns:
            List of random numbers
        """
        random_numbers = []
        range_size = max_val - min_val

        for _ in range(count):
            # Use secrets module to generate cryptographically secure random numbers
            # [min, max)
            random_num = min_val + random.randint(0, range_size - 1)
            random_numbers.append(random_num)

        return random_numbers


if __name__ == '__main__':
    e = Enclave()
    e.set_random_seed()
    print(e.generate_random_numbers(10, 30, 3))
