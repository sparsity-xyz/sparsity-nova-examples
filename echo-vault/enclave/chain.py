import logging
from typing import Optional

from nova_python_sdk.rpc import ChainRpc


class Chain(ChainRpc):
    """Echo Vault chain helper using the canonical Nova RPC SDK."""

    DEFAULT_MOCK_RPC = "http://capsule-runtime.sparsity.cloud:18545"
    DEFAULT_HELIOS_RPC = "http://127.0.0.1:18545"

    def __init__(self, rpc_url: Optional[str] = None):
        super().__init__(
            enclave_rpc_url=self.DEFAULT_HELIOS_RPC,
            dev_rpc_url=self.DEFAULT_MOCK_RPC,
            rpc_url=rpc_url,
            override_env_vars=("ECHO_VAULT_RPC_URL", "BASE_SEPOLIA_RPC_URL", "BUSINESS_CHAIN_RPC_URL"),
            logger_name=__name__,
        )
        self.logger = logging.getLogger(__name__)

    def get_block_transactions(self, block_number: int):
        block = self.w3.eth.get_block(block_number, full_transactions=True)
        return block.get("transactions", [])
