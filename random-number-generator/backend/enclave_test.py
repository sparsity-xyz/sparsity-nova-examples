from web3 import Web3

from enclave import Enclave


def estimate_priority_from_fee_history(w3: Web3, blocks: int = 5, percentile: float = 50):
    try:
        hist = w3.eth.fee_history(blocks, 'pending', [percentile/100])
        reward = hist['reward'][-1][0]  # 单位 wei
        return int(reward)
    except Exception:
        return w3.to_wei(2, 'gwei')

def test_transaction():
    en = Enclave()
    address = Web3.to_checksum_address("0x358081769cdfc309e95de8942e388f095cd1bc7c")
    w3 = Web3()

    priority_from_hist = estimate_priority_from_fee_history(w3, blocks=5, percentile=50)
    base_fee = w3.eth.get_block('pending')['baseFeePerGas']
    max_fee = base_fee * 2 + priority_from_hist

    tx = {
        "chainId": w3.eth.chain_id,
        "nonce": w3.eth.get_transaction_count(address),
        "maxPriorityFeePerGas": priority_from_hist,
        "maxFeePerGas": max_fee,
        "gas": 300000,
        "to": Web3.to_checksum_address("0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"),
        "value": int(1e18),
        "data": "0x",
    }
    print(tx)
    res = en.sign_tx(tx)
    print(res)

    tx_hash = w3.eth.send_raw_transaction(res["raw_transaction"])
    print(tx_hash)


if __name__ == '__main__':
    test_transaction()
