// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

/// @notice Experiment only: an authorized operator anchors encrypted backup manifests.
/// Does not verify Nitro attestation, S3 availability, or application correctness.
contract BackupAnchor {
    address public immutable owner;
    bytes32 public immutable dataset;
    uint64 private epoch;
    uint64 private sequence;
    bytes32 private manifestHash;
    bytes32 private logHead;
    event Checkpoint(uint64 indexed epoch, uint64 indexed sequence,
                     bytes32 indexed manifestHash, bytes32 previousHash, bytes32 logHead);
    constructor(bytes32 dataset_) { owner = msg.sender; dataset = dataset_; }
    function latest() external view returns (uint64, uint64, bytes32, bytes32) {
        return (epoch, sequence, manifestHash, logHead);
    }
    function commit(uint64 nextEpoch, uint64 nextSequence, bytes32 nextHash,
                    bytes32 nextLogHead, bytes32 expectedPrevious) external {
        require(msg.sender == owner, "writer");
        require(nextEpoch == epoch + 1, "epoch");
        require(nextSequence >= sequence, "sequence");
        require(nextHash != bytes32(0), "empty");
        require(expectedPrevious == manifestHash, "previous");
        bytes32 previous = manifestHash;
        epoch = nextEpoch; sequence = nextSequence;
        manifestHash = nextHash; logHead = nextLogHead;
        emit Checkpoint(epoch, sequence, manifestHash, previous, logHead);
    }
}
