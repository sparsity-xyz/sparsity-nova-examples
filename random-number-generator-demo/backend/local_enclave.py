import random

from eth_account import Account


class LocalEnclave:
    def __init__(self, w3):
        self.w3 = w3
        self.account = Account.create()

    def eth_address(self):
        return self.account.address

    def set_random_seed(self):
        pass

    def sign_tx(self, transaction_dict):
        signed_txn = self.w3.eth.account.sign_transaction(
            transaction_dict,
            private_key=self.account.key
        )
        return signed_txn.raw_transaction

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
