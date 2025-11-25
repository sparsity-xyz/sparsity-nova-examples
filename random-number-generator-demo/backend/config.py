import json
from pathlib import Path


class Config:
    RPC_URL = "http://127.0.0.1:8545"
    CONTRACT_ADDRESS = "0x5FbDB2315678afecb367f032d93F642f64180aa3"

    ENLAVER_ENDPOINT= "http://127.0.0.1:18000"

    POLL_INTERVAL = 10  # second
    FROM_BLOCK = "latest"

    DEPOSIT_AMOUNT = 0.1 # ether

    @staticmethod
    def load_abi():
        abi_path = Path(__file__).parent / "abi.json"
        with open(abi_path, "r") as f:
            return json.load(f)

    CONTRACT_ABI = load_abi.__func__()

    LOG_LEVEL = "INFO"


if __name__ == '__main__':
    print(Config)
