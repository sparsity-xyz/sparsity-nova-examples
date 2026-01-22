// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.20;

/**
 * @title NovaAppBase
 * @dev Base contract for Nova TEE applications with on-chain state verification.
 *
 * This contract stores the hash of the encrypted application state,
 * allowing external verification that the TEE's state matches on-chain expectations.
 */
contract NovaAppBase {
    /// @notice The keccak256 hash of the current encrypted state blob
    bytes32 public stateHash;

    /// @notice Block number when state was last updated
    uint256 public lastUpdatedBlock;

    /// @notice The TEE wallet address (from Odyn /v1/eth/address)
    address public teeWalletAddress;

    /// @notice Contract owner for administrative functions
    address public owner;

    /// @notice Emitted when state hash is updated
    event StateUpdated(bytes32 indexed newHash, uint256 blockNumber);

    /// @notice Emitted when TEE wallet is registered
    event TeeWalletRegistered(address indexed wallet);

    /// @notice Emitted when ownership is transferred
    event OwnershipTransferred(
        address indexed previousOwner,
        address indexed newOwner
    );

    modifier onlyOwner() {
        require(msg.sender == owner, "NovaAppBase: caller is not the owner");
        _;
    }

    modifier onlyTee() {
        require(
            msg.sender == teeWalletAddress,
            "NovaAppBase: caller is not the TEE"
        );
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    /**
     * @notice Register the TEE wallet address
     * @param _teeWallet The Ethereum address from the TEE's Odyn API
     * @dev Can only be called once by the owner
     */
    function registerTeeWallet(address _teeWallet) external onlyOwner {
        require(
            teeWalletAddress == address(0),
            "NovaAppBase: TEE wallet already registered"
        );
        require(_teeWallet != address(0), "NovaAppBase: invalid TEE wallet");

        teeWalletAddress = _teeWallet;
        emit TeeWalletRegistered(_teeWallet);
    }

    /**
     * @notice Update the state hash (called by TEE after state save)
     * @param _newHash The keccak256 hash returned by Odyn's /v1/state/save
     */
    function updateStateHash(bytes32 _newHash) external onlyTee {
        require(_newHash != bytes32(0), "NovaAppBase: invalid hash");

        stateHash = _newHash;
        lastUpdatedBlock = block.number;

        emit StateUpdated(_newHash, block.number);
    }

    /**
     * @notice Verify that a given hash matches the current state
     * @param _hash Hash to verify
     * @return True if hash matches current state
     */
    function verifyStateHash(bytes32 _hash) external view returns (bool) {
        return stateHash == _hash;
    }

    /**
     * @notice Transfer ownership to a new address
     * @param newOwner The new owner address
     */
    function transferOwnership(address newOwner) external onlyOwner {
        require(
            newOwner != address(0),
            "NovaAppBase: new owner is zero address"
        );
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }
}
