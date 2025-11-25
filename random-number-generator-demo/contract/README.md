
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
# fill the OPERATOR_PRIVATE_KEY in .env
```

## register operator
```
OPERATOR_ADDRESS=<operator_address> npx hardhat run scripts/register-operator.js --network localhost
```

## generate requests
```
npm run test:local
```

## fulfill requests
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
npx hardhat verify --network baseSepolia <YOUR_CONTRACT_ADDRESS>
```

## register operator
```
OPERATOR_ADDRESS=<operator_address> npx hardhat run scripts/register-operator.js --network baseSepolia
```

## call registry contract to register TEE operator
