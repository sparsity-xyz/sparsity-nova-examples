
# install
```
npm install
```

# local network
## local node
```
npx hardhat node
```

## deploy on local node
```
npm run deploy:local
```

## env
```
cp .env.example .env

```

## set registry
for local testing, we assume a EOA as the registry contract
```
REGISTRY_ADDRESS=<registry_address> npx hardhat run scripts/set-registry.js --network localhost
```

## set tee wallet
get operator address from backend
```
TEE_WALLET_ADDRESS=<tee_wallet_address> npx hardhat run scripts/register-tee-wallet.js --network localhost
```

## generate requests
```
npm run test:local
```

## fulfill requests
fill the OPERATOR_PRIVATE_KEY in .env
```
REQUEST_ID=<request_id> npm run fulfill:local
```

## check
```
npm run check:local
```

# base sepolia
## env
```
cp .env.example .env
# fill the missing part in .env
# REGISTRY_CONTRACT and DEPLOYMENT_PRIVATE_KEY
```
## deploy on base sepolia
```
npm run deploy:sepolia
```

## verify contract
```
npx hardhat verify --network baseSepolia <YOUR_CONTRACT_ADDRESS> <REGISTRY_CONTRACT>
```
