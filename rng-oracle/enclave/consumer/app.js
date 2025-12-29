/**
 * RNG Consumer - Web Application
 * Interacts with RandomNumberGenerator contract on Base Sepolia
 */

// ========== State ==========
let provider = null;
let signer = null;
let rngContract = null;
let consumerContract = null;
let userAddress = null;
let currentMode = 'without-callback';
let requests = []; // Local storage of requests
let pollingIntervals = {}; // Track polling intervals

// ========== DOM Elements ==========
const connectBtn = document.getElementById('connectBtn');
const walletInfo = document.getElementById('walletInfo');
const walletAddress = document.getElementById('walletAddress');
const networkBadge = document.getElementById('networkBadge');
const rngAddressInput = document.getElementById('rngAddress');
const consumerAddressInput = document.getElementById('consumerAddress');
const consumerAddressGroup = document.getElementById('consumerAddressGroup');
const minValInput = document.getElementById('minVal');
const maxValInput = document.getElementById('maxVal');
const countInput = document.getElementById('count');
const requestBtn = document.getElementById('requestBtn');
const requestStatus = document.getElementById('requestStatus');
const noRequests = document.getElementById('noRequests');
const requestsList = document.getElementById('requestsList');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingText = document.getElementById('loadingText');
const modeBtns = document.querySelectorAll('.mode-btn');

// ========== Constants ==========
const BASE_SEPOLIA_CHAIN_ID = 84532;
const POLL_INTERVAL = 3000; // 3 seconds

// ========== Initialization ==========
document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    loadSavedState();
    checkWalletConnection();
});

function initEventListeners() {
    connectBtn.addEventListener('click', connectWallet);
    requestBtn.addEventListener('click', requestRandomNumbers);

    // Mode selector
    modeBtns.forEach(btn => {
        btn.addEventListener('click', () => selectMode(btn.dataset.mode));
    });

    // Contract address inputs
    rngAddressInput.addEventListener('change', updateRNGContract);
    consumerAddressInput.addEventListener('change', updateConsumerContract);
}

function loadSavedState() {
    // Load saved addresses from localStorage
    const savedRNGAddress = localStorage.getItem('rngAddress');
    const savedConsumerAddress = localStorage.getItem('consumerAddress');
    const savedRequests = localStorage.getItem('requests');

    if (savedRNGAddress) rngAddressInput.value = savedRNGAddress;
    if (savedConsumerAddress) consumerAddressInput.value = savedConsumerAddress;
    if (savedRequests) {
        requests = JSON.parse(savedRequests);
        renderRequests();
    }
}

function saveState() {
    localStorage.setItem('rngAddress', rngAddressInput.value);
    localStorage.setItem('consumerAddress', consumerAddressInput.value);
    localStorage.setItem('requests', JSON.stringify(requests));
}

// ========== Wallet Connection ==========
async function checkWalletConnection() {
    if (typeof window.ethereum !== 'undefined') {
        provider = new ethers.providers.Web3Provider(window.ethereum);

        // Check if already connected
        const accounts = await provider.listAccounts();
        if (accounts.length > 0) {
            await setupWallet(accounts[0]);
        }

        // Listen for account changes
        window.ethereum.on('accountsChanged', handleAccountsChanged);
        window.ethereum.on('chainChanged', () => window.location.reload());
    }
}

async function connectWallet() {
    if (typeof window.ethereum === 'undefined') {
        showStatus('Please install MetaMask or another Web3 wallet!', 'error');
        return;
    }

    try {
        showLoading('Connecting wallet...');
        provider = new ethers.providers.Web3Provider(window.ethereum);

        // Request account access
        const accounts = await provider.send('eth_requestAccounts', []);
        await setupWallet(accounts[0]);

        hideLoading();
    } catch (error) {
        hideLoading();
        console.error('Connection error:', error);
        showStatus('Failed to connect wallet: ' + error.message, 'error');
    }
}

async function setupWallet(address) {
    userAddress = address;
    signer = provider.getSigner();

    // Check network
    const network = await provider.getNetwork();
    if (network.chainId !== BASE_SEPOLIA_CHAIN_ID) {
        showStatus('Please switch to Base Sepolia network', 'error');
        try {
            await window.ethereum.request({
                method: 'wallet_switchEthereumChain',
                params: [{ chainId: '0x' + BASE_SEPOLIA_CHAIN_ID.toString(16) }],
            });
        } catch (error) {
            console.error('Failed to switch network:', error);
        }
    }

    // Update UI
    connectBtn.classList.add('hidden');
    walletInfo.classList.remove('hidden');
    walletAddress.textContent = shortenAddress(address);
    networkBadge.textContent = 'Base Sepolia';

    // Setup contracts
    await updateRNGContract();
    await updateConsumerContract();

    // Enable request button
    updateRequestButtonState();

    // Resume polling for pending requests
    resumePolling();
}

function handleAccountsChanged(accounts) {
    if (accounts.length === 0) {
        // Disconnected
        userAddress = null;
        signer = null;
        connectBtn.classList.remove('hidden');
        walletInfo.classList.add('hidden');
        requestBtn.disabled = true;
    } else {
        setupWallet(accounts[0]);
    }
}

// ========== Contract Setup ==========
async function updateRNGContract() {
    const address = rngAddressInput.value.trim();
    if (!address || !ethers.utils.isAddress(address)) {
        rngContract = null;
        updateRequestButtonState();
        return;
    }

    try {
        rngContract = new ethers.Contract(address, RNG_ABI, signer || provider);
        saveState();
        updateRequestButtonState();
    } catch (error) {
        console.error('Invalid RNG contract:', error);
        rngContract = null;
    }
}

async function updateConsumerContract() {
    const address = consumerAddressInput.value.trim();
    if (!address || !ethers.utils.isAddress(address)) {
        consumerContract = null;
        return;
    }

    try {
        consumerContract = new ethers.Contract(address, CONSUMER_ABI, signer || provider);
        saveState();
    } catch (error) {
        console.error('Invalid Consumer contract:', error);
        consumerContract = null;
    }
}

// ========== Mode Selection ==========
function selectMode(mode) {
    currentMode = mode;

    // Update button states
    modeBtns.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });

    // Show/hide consumer address input
    if (mode === 'with-callback') {
        consumerAddressGroup.classList.remove('hidden');
    } else {
        consumerAddressGroup.classList.add('hidden');
    }

    updateRequestButtonState();
}

function updateRequestButtonState() {
    const hasRNG = rngContract !== null;
    const hasWallet = signer !== null;
    const hasConsumer = currentMode === 'without-callback' || consumerContract !== null;

    requestBtn.disabled = !(hasRNG && hasWallet && hasConsumer);
}

// ========== Request Random Numbers ==========
async function requestRandomNumbers() {
    const min = parseInt(minValInput.value);
    const max = parseInt(maxValInput.value);
    const count = parseInt(countInput.value);

    // Validation
    if (isNaN(min) || isNaN(max) || isNaN(count)) {
        showStatus('Please enter valid numbers', 'error');
        return;
    }

    if (max <= min) {
        showStatus('Max must be greater than min', 'error');
        return;
    }

    if (count < 1 || count > 100) {
        showStatus('Count must be between 1 and 100', 'error');
        return;
    }

    try {
        showLoading('Sending transaction...');

        let tx;
        let requestId;

        if (currentMode === 'without-callback') {
            // Direct request to RNG contract
            tx = await rngContract.requestRandomRange(min, max, count);
        } else {
            // Request through consumer contract with callback
            if (!consumerContract) {
                throw new Error('Consumer contract not set');
            }
            tx = await consumerContract.requestRandomWithCallback(min, max, count);
        }

        showLoading('Waiting for confirmation...');
        const receipt = await tx.wait();

        // Extract requestId from events
        const event = receipt.events?.find(e =>
            e.event === 'RandomNumberRequested' || e.event === 'RandomRequested'
        );

        if (event) {
            requestId = event.args.requestId.toNumber();
        } else {
            // Try to get from logs
            const iface = new ethers.utils.Interface(RNG_ABI);
            for (const log of receipt.logs) {
                try {
                    const parsed = iface.parseLog(log);
                    if (parsed.name === 'RandomNumberRequested') {
                        requestId = parsed.args.requestId.toNumber();
                        break;
                    }
                } catch (e) {
                    // Not our event, continue
                }
            }
        }

        if (!requestId) {
            // Fallback: estimate based on transaction
            requestId = Date.now();
        }

        // Add to local requests
        const newRequest = {
            id: requestId,
            min,
            max,
            count,
            mode: currentMode,
            status: 'pending',
            randomNumbers: [],
            timestamp: Date.now(),
            txHash: receipt.transactionHash
        };

        requests.unshift(newRequest);
        saveState();
        renderRequests();

        // Start polling for result
        startPolling(requestId);

        hideLoading();
        showStatus(`Request #${requestId} submitted! Waiting for random numbers...`, 'success');

    } catch (error) {
        hideLoading();
        console.error('Request error:', error);
        showStatus('Transaction failed: ' + (error.reason || error.message), 'error');
    }
}

// ========== Polling for Results ==========
function startPolling(requestId) {
    if (pollingIntervals[requestId]) return;

    pollingIntervals[requestId] = setInterval(async () => {
        await checkRequestStatus(requestId);
    }, POLL_INTERVAL);

    // Also check immediately
    checkRequestStatus(requestId);
}

function stopPolling(requestId) {
    if (pollingIntervals[requestId]) {
        clearInterval(pollingIntervals[requestId]);
        delete pollingIntervals[requestId];
    }
}

async function checkRequestStatus(requestId) {
    if (!rngContract) return;

    try {
        const result = await rngContract.getRequest(requestId);
        const status = result.status; // 0=Pending, 1=Fulfilled, 2=Cancelled

        if (status === 1) { // Fulfilled
            const randomNumbers = result.randomNumbers.map(n => n.toNumber());

            // Update local request
            const request = requests.find(r => r.id === requestId);
            if (request) {
                request.status = 'fulfilled';
                request.randomNumbers = randomNumbers;
                request.fulfilledAt = result.fulfilledAt.toNumber() * 1000;
                saveState();
                renderRequests();
            }

            // Stop polling
            stopPolling(requestId);

            showStatus(`Request #${requestId} fulfilled! Random numbers: [${randomNumbers.join(', ')}]`, 'success');
        } else if (status === 2) { // Cancelled
            const request = requests.find(r => r.id === requestId);
            if (request) {
                request.status = 'cancelled';
                saveState();
                renderRequests();
            }
            stopPolling(requestId);
        }
    } catch (error) {
        console.error('Error checking request status:', error);
    }
}

function resumePolling() {
    // Resume polling for all pending requests
    requests.filter(r => r.status === 'pending').forEach(r => {
        startPolling(r.id);
    });
}

// ========== Render UI ==========
function renderRequests() {
    if (requests.length === 0) {
        noRequests.classList.remove('hidden');
        requestsList.innerHTML = '';
        return;
    }

    noRequests.classList.add('hidden');

    requestsList.innerHTML = requests.map(req => `
        <div class="request-item" data-id="${req.id}">
            <div class="request-id">
                <span class="request-id-label">Request</span>
                <span class="request-id-value">#${req.id}</span>
            </div>
            <div class="request-details">
                <div class="request-params">
                    Range: [${req.min}, ${req.max}) • Count: ${req.count} • Mode: ${req.mode === 'with-callback' ? '📞 Callback' : '📊 Polling'}
                </div>
                <div class="request-numbers">
                    ${req.status === 'fulfilled'
            ? '🎲 ' + req.randomNumbers.join(', ')
            : req.status === 'cancelled'
                ? '❌ Cancelled'
                : '⏳ Waiting for random numbers...'}
                </div>
            </div>
            <div class="request-status">
                <span class="status-badge ${getStatusClass(req.status)}">
                    ${getStatusText(req.status)}
                </span>
            </div>
        </div>
    `).join('');
}

function getStatusClass(status) {
    switch (status) {
        case 'pending': return 'status-polling';
        case 'fulfilled': return 'status-fulfilled';
        case 'cancelled': return 'status-pending';
        default: return '';
    }
}

function getStatusText(status) {
    switch (status) {
        case 'pending': return '⏳ Polling...';
        case 'fulfilled': return '✅ Fulfilled';
        case 'cancelled': return '❌ Cancelled';
        default: return status;
    }
}

// ========== Utilities ==========
function shortenAddress(address) {
    return address.slice(0, 6) + '...' + address.slice(-4);
}

function showStatus(message, type = 'info') {
    requestStatus.textContent = message;
    requestStatus.className = `status-message ${type}`;
    requestStatus.classList.remove('hidden');

    // Auto-hide after 10 seconds
    setTimeout(() => {
        requestStatus.classList.add('hidden');
    }, 10000);
}

function showLoading(text = 'Processing...') {
    loadingText.textContent = text;
    loadingOverlay.classList.remove('hidden');
}

function hideLoading() {
    loadingOverlay.classList.add('hidden');
}

// ========== Error Handling ==========
window.onerror = function (message, source, lineno, colno, error) {
    console.error('Global error:', { message, source, lineno, colno, error });
    hideLoading();
};
