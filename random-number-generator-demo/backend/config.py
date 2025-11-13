import json
import os
from pathlib import Path
from eth_account import Account


class Config:
    RPC_URL = "https://sepolia.base.org"
    CONTRACT_ADDRESS = "0x41C16DF1E1D5cB71Fa5aaDBC6cE8dd0bDee22cCf"

    POLL_INTERVAL = 10  # 秒
    FROM_BLOCK = "latest"

    DEPOSIT_AMOUNT = 0.1 # ether

    pk = os.getenv("PRIVATE_KEY", "")
    if pk == "":
        OPERATOR = Account.create()
    else:
        OPERATOR = Account.from_key(pk)

    OPERATOR_PRIVATE_KEY = OPERATOR.key.hex()
    OPERATOR_ADDRESS = OPERATOR.address

    @staticmethod
    def load_abi():
        abi_path = Path(__file__).parent / "abi.json"
        with open(abi_path, "r") as f:
            return json.load(f)

    CONTRACT_ABI = load_abi.__func__()

    LOG_LEVEL = "INFO"


if __name__ == '__main__':
    print(Config)
