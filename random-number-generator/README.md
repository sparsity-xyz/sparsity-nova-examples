
# rng demo
This is a demo showing how a random number generator runs on the Sparsity Nova Platform.

## local testing

### deploy contract
```
cd contract
```

install requirements
```
npm install
```
start local node
```
npx hardhat node
```
deploy contract
```
npm run deploy:local
``` 
To set up a mock TEE wallet for local testing, we provide a mock TEE service to support local development.

```
REGISTRY_ADDRESS=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 npx hardhat run scripts/set-registry.js --network localhost

TEE_WALLET_ADDRESS=0x50a1c7EaA1CC0e0a8D3a02681C87b6A3C75f80d8 npx hardhat run scripts/register-tee-wallet.js --network localhost
```

### start backend
```
cd backend
```
start service
```
python main.py
```

### testing
```
cd contract
```
run test script to generate random number requests
```
npm run test:local
```
then the backend will detect the requests and fulfill the data,
you can also check the results by running
```
npm run check:local
```

## deploy on Sparsity Nova Platform
### contract
```
cd contract
```
set up environment variables
```
cp .env.example .env
```
deploy contract, When the contract is deployed, the on-chain contract address will be automatically injected into backend/config.py. 
```
npm run deploy:sepolia
```
verify contract
```
npx hardhat verify --network baseSepolia <YOUR_CONTRACT_ADDRESS> <REGISTRY_CONTRACT>
```

### go to Sparsity Nova Platform
```
https://nova.sparsity.ai/
```
create a new app and deploy

### get address inside service
after the app was registered onchain, fund the wallet inside TEE
```
curl <APP_ENDPOINT>
```
the output should be
```
{
    "service": "Random Number Generator",
    "version": "1.0.0",
    "status": "running",
    "is_operator": true,
    "contract_address": "0xB7f8BC63BbcaD18155201308C8f3540b07f84F5e",
    "operator": "0xAae4260D8b9AE1D2D6fBC07FCE0D9a46852c5984",
    "operator_balance": 0.998857,
    "processed_requests": 0
}
```
fund `operator`