import random

import httpx


class Enclave:
    def __init__(self, endpoint="http://127.0.0.1:8000"):
        self.endpoint = endpoint

    def set_random_seed(self):
        res = httpx.get(f"{self.endpoint}/v1/random")
        seed = bytes.fromhex(res.json()["random_bytes"].removeprefix("0x"))
        random.seed(seed)

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
            random_num = min_val + random.randint(0, range_size)
            random_numbers.append(random_num)

        return random_numbers


if __name__ == '__main__':
    e = Enclave()
    e.set_random_seed()
    print(e.generate_random_numbers(10, 30, 3))
