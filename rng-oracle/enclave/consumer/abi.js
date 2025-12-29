// ABI for RandomNumberGenerator contract
const RNG_ABI = [
    // Request functions
    "function requestRandom(uint256 max) external returns (uint256)",
    "function requestRandomRange(uint256 min, uint256 max, uint256 count) external returns (uint256)",
    "function requestRandomWithCallback(uint256 max, address callbackContract) external returns (uint256)",
    "function requestRandomRangeWithCallback(uint256 min, uint256 max, uint256 count, address callbackContract) external returns (uint256)",

    // Query functions
    "function getRequest(uint256 requestId) external view returns (uint8 status, uint256[] memory randomNumbers, address requester, uint256 timestamp, uint256 fulfilledAt, address callbackContract, bool callbackExecuted, uint256 min, uint256 max, uint256 count)",
    "function getTotalRequests() external view returns (uint256)",
    "function isOperator(address addr) external view returns (bool)",
    "function getUserRequests(address user) external view returns (uint256[] memory)",

    // Events
    "event RandomNumberRequested(uint256 indexed requestId, address indexed requester, uint256 min, uint256 max, uint256 count, address callbackContract, uint256 timestamp)",
    "event RandomNumberFulfilled(uint256 indexed requestId, address indexed requester, uint256[] randomNumbers, uint256 timestamp)"
];

// ABI for RNGConsumer contract
const CONSUMER_ABI = [
    // Request functions
    "function requestRandomWithoutCallback(uint256 min, uint256 max, uint256 count) external returns (uint256)",
    "function requestRandomWithCallback(uint256 min, uint256 max, uint256 count) external returns (uint256)",

    // Query functions
    "function getResult(uint256 requestId) external view returns (bool fulfilled, uint256[] memory randomNumbers, uint256 fulfilledAt)",
    "function getAllRequestIds() external view returns (uint256[] memory)",
    "function getRequestCount() external view returns (uint256)",
    "function checkResultFromRNG(uint256 requestId) external view returns (uint8 status, uint256[] memory randomNumbers)",
    "function results(uint256) external view returns (uint256 requestId, uint256 fulfilledAt, bool fulfilled)",
    "function rngContract() external view returns (address)",

    // Events
    "event RandomRequested(uint256 indexed requestId, uint256 min, uint256 max, uint256 count, bool withCallback)",
    "event RandomReceived(uint256 indexed requestId, uint256[] randomNumbers, uint256 timestamp)"
];
