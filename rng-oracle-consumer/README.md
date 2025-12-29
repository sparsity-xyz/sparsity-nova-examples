# Random Number Generator Consumer

A web-based consumer application for the Random Number Generator service on the Sparsity Nova Platform.

## Features

- **Web Interface**: Modern, responsive UI for requesting random numbers
- **Two Modes**:
  - **Without Callback**: Direct request and poll for results
  - **With Callback**: Deploy a consumer contract that receives random numbers automatically
- **Real-time Status**: Live polling and status updates
- **Request History**: Track all your random number requests

## Architecture

```
┌─────────────────────┐     ┌─────────────────────────────┐
│   Web Frontend      │────▶│  RandomNumberGenerator      │
│   (Browser + Wallet)│     │  Contract                   │
└─────────────────────┘     └─────────────────────────────┘
         │                              │
         │                              ▼
         │                  ┌─────────────────────────────┐
         │                  │  RNG Enclave (TEE)          │
         │                  │  - Listen for events        │
         │                  │  - Generate random numbers  │
         │                  │  - Fulfill requests         │
         │                  └─────────────────────────────┘
         │                              │
         ▼                              ▼
┌─────────────────────┐     ┌─────────────────────────────┐
│ RNGConsumer Contract│◀────│  Callback with results      │
│ (optional)          │     │                             │
└─────────────────────┘     └─────────────────────────────┘
```


## Quick Start

### 1. Deploy Consumer Contract (for callback mode)

```bash
cd contract
npm install
cp .env.example .env
# Edit .env with your settings
npm run deploy:sepolia
```

### 2. Start Frontend

Simply open `frontend/index.html` in a browser, or serve it:

```bash
cd frontend
python -m http.server 8080
# Visit http://localhost:8080
```

### 3. Connect Wallet

1. Open the web interface
2. Click "Connect Wallet" 
3. Make sure you're on Base Sepolia network
4. Start requesting random numbers!

## Usage

### Without Callback (Polling Mode)

1. Select "Without Callback" mode
2. Set min, max, and count values
3. Click "Request Random Numbers"
4. The UI will automatically poll for results

### With Callback (Contract Mode)

1. First deploy the RNGConsumer contract
2. Select "With Callback" mode
3. Enter your RNGConsumer contract address
4. Request random numbers
5. Results will be stored in your consumer contract

## Contract Addresses

| Contract | Base Sepolia |
|----------|--------------|
| RandomNumberGenerator | See .env |
| RNGConsumer (Example) | Deploy your own |

## Environment Variables

Create `.env` in the contract directory:

```
DEPLOYMENT_PRIVATE_KEY=your_private_key
BASE_SEPOLIA_RPC=https://sepolia.base.org
RNG_CONTRACT_ADDRESS=0x...  # RandomNumberGenerator address
```

## License

Apache-2.0
