// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import "@openzeppelin/contracts/access/Ownable.sol";

/// @title RNG Callback Interface
/// @notice Interface that consumer contracts must implement to receive random numbers
interface IRNGCallback {
    function onRandomNumberFulfilled(
        uint256 requestId,
        uint256[] calldata randomNumbers
    ) external;
}

/// @title RandomNumberGenerator Interface
interface IRandomNumberGenerator {
    function requestRandom(uint256 max) external returns (uint256);
    function requestRandomRange(
        uint256 min,
        uint256 max,
        uint256 count
    ) external returns (uint256);
    function requestRandomWithCallback(
        uint256 max,
        address callbackContract
    ) external returns (uint256);
    function requestRandomRangeWithCallback(
        uint256 min,
        uint256 max,
        uint256 count,
        address callbackContract
    ) external returns (uint256);
    function getRequest(
        uint256 requestId
    )
        external
        view
        returns (
            uint8 status,
            uint256[] memory randomNumbers,
            address requester,
            uint256 timestamp,
            uint256 fulfilledAt,
            address callbackContract,
            bool callbackExecuted,
            uint256 min,
            uint256 max,
            uint256 count
        );
}

/// @title RNG Consumer
/// @author Sparsity
/// @notice Example consumer contract that requests and receives random numbers via callback
/// @dev Implements IRNGCallback to receive random numbers from the RandomNumberGenerator
contract RNGConsumer is Ownable, IRNGCallback {
    // ========== State Variables ==========

    /// @notice Address of the RandomNumberGenerator contract
    IRandomNumberGenerator public rngContract;

    /// @notice Struct to store fulfilled random number results
    struct RandomResult {
        uint256 requestId;
        uint256[] randomNumbers;
        uint256 fulfilledAt;
        bool fulfilled;
    }

    /// @notice Mapping from requestId to RandomResult
    mapping(uint256 => RandomResult) public results;

    /// @notice Array of all request IDs made by this contract
    uint256[] public requestIds;

    /// @notice Mapping to track which requests were made by this contract
    mapping(uint256 => bool) public ourRequests;

    // ========== Events ==========

    event RandomRequested(
        uint256 indexed requestId,
        uint256 min,
        uint256 max,
        uint256 count,
        bool withCallback
    );

    event RandomReceived(
        uint256 indexed requestId,
        uint256[] randomNumbers,
        uint256 timestamp
    );

    event RNGContractUpdated(
        address indexed oldAddress,
        address indexed newAddress
    );

    // ========== Constructor ==========

    constructor(address _rngContract) Ownable(msg.sender) {
        require(_rngContract != address(0), "Invalid RNG contract address");
        rngContract = IRandomNumberGenerator(_rngContract);
    }

    // ========== External Functions ==========

    /// @notice Request random numbers without callback (polling mode)
    /// @param min Minimum value (inclusive)
    /// @param max Maximum value (exclusive)
    /// @param count Number of random numbers to generate
    /// @return requestId The request ID
    function requestRandomWithoutCallback(
        uint256 min,
        uint256 max,
        uint256 count
    ) external returns (uint256) {
        uint256 requestId = rngContract.requestRandomRange(min, max, count);

        requestIds.push(requestId);
        ourRequests[requestId] = true;
        results[requestId] = RandomResult({
            requestId: requestId,
            randomNumbers: new uint256[](0),
            fulfilledAt: 0,
            fulfilled: false
        });

        emit RandomRequested(requestId, min, max, count, false);
        return requestId;
    }

    /// @notice Request random numbers with callback
    /// @param min Minimum value (inclusive)
    /// @param max Maximum value (exclusive)
    /// @param count Number of random numbers to generate
    /// @return requestId The request ID
    function requestRandomWithCallback(
        uint256 min,
        uint256 max,
        uint256 count
    ) external returns (uint256) {
        uint256 requestId = rngContract.requestRandomRangeWithCallback(
            min,
            max,
            count,
            address(this)
        );

        requestIds.push(requestId);
        ourRequests[requestId] = true;
        results[requestId] = RandomResult({
            requestId: requestId,
            randomNumbers: new uint256[](0),
            fulfilledAt: 0,
            fulfilled: false
        });

        emit RandomRequested(requestId, min, max, count, true);
        return requestId;
    }

    /// @notice Callback function called by RandomNumberGenerator when random numbers are ready
    /// @param requestId The request ID
    /// @param randomNumbers Array of random numbers
    function onRandomNumberFulfilled(
        uint256 requestId,
        uint256[] calldata randomNumbers
    ) external override {
        require(
            msg.sender == address(rngContract),
            "Only RNG contract can call"
        );
        require(ourRequests[requestId], "Not our request");

        results[requestId] = RandomResult({
            requestId: requestId,
            randomNumbers: randomNumbers,
            fulfilledAt: block.timestamp,
            fulfilled: true
        });

        emit RandomReceived(requestId, randomNumbers, block.timestamp);
    }

    // ========== View Functions ==========

    /// @notice Get the result for a specific request
    /// @param requestId The request ID
    /// @return fulfilled Whether the request has been fulfilled
    /// @return randomNumbers The random numbers (empty if not fulfilled)
    /// @return fulfilledAt Timestamp when fulfilled (0 if not fulfilled)
    function getResult(
        uint256 requestId
    )
        external
        view
        returns (
            bool fulfilled,
            uint256[] memory randomNumbers,
            uint256 fulfilledAt
        )
    {
        RandomResult memory result = results[requestId];
        return (result.fulfilled, result.randomNumbers, result.fulfilledAt);
    }

    /// @notice Get all request IDs made by this contract
    /// @return Array of request IDs
    function getAllRequestIds() external view returns (uint256[] memory) {
        return requestIds;
    }

    /// @notice Get the total number of requests made
    /// @return Total request count
    function getRequestCount() external view returns (uint256) {
        return requestIds.length;
    }

    /// @notice Check result directly from RNG contract (for polling mode)
    /// @param requestId The request ID
    /// @return status Request status (0=Pending, 1=Fulfilled, 2=Cancelled)
    /// @return randomNumbers The random numbers
    function checkResultFromRNG(
        uint256 requestId
    ) external view returns (uint8 status, uint256[] memory randomNumbers) {
        (status, randomNumbers, , , , , , , , ) = rngContract.getRequest(
            requestId
        );
        return (status, randomNumbers);
    }

    // ========== Admin Functions ==========

    /// @notice Update the RNG contract address
    /// @param _newRngContract New RNG contract address
    function setRNGContract(address _newRngContract) external onlyOwner {
        require(_newRngContract != address(0), "Invalid address");
        address oldAddress = address(rngContract);
        rngContract = IRandomNumberGenerator(_newRngContract);
        emit RNGContractUpdated(oldAddress, _newRngContract);
    }
}
