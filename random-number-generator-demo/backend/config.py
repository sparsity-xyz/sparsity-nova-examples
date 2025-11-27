import json
import os
from pathlib import Path


class Config:
    RPC_URL = "https://base-sepolia-public.nodies.app"
    CONTRACT_ADDRESS = "0x7eAA444e7257Aa4A5Ed74793991AAa0767939075"

    MOCK_ENLAVER_ENDPOINT = "http://54.215.216.173:18000"
    ENLAVER_ENDPOINT = "http://127.0.0.1:18000" \
        if os.getenv("IN_DOCKER", "False").lower() == "true" \
        else MOCK_ENLAVER_ENDPOINT

    POLL_INTERVAL = 10  # second
    FROM_BLOCK = "latest"

    @staticmethod
    def load_abi():
        abi_path = Path(__file__).parent / "abi.json"
        with open(abi_path, "r") as f:
            return json.load(f)

    CONTRACT_ABI = load_abi.__func__()

    LOG_LEVEL = "INFO"


if __name__ == '__main__':
    print(Config)
