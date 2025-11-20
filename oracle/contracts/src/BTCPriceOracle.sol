// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract BTCPriceOracle {
    uint256 public btcPrice;
    address public oracle;
    address public owner;
    uint256 public lastUpdated;

    event PriceUpdated(uint256 newPrice, uint256 timestamp);
    event OracleUpdated(address newOracle);

    modifier onlyOracle() {
        require(msg.sender == oracle, "Only oracle can call");
        _;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call");
        _;
    }

    constructor(address _oracle) {
        owner = msg.sender;
        oracle = _oracle;
    }

    function setPrice(uint256 _price) external onlyOracle {
        btcPrice = _price;
        lastUpdated = block.timestamp;
        emit PriceUpdated(_price, block.timestamp);
    }

    function getPrice() external view returns (uint256) {
        return btcPrice;
    }

    function setOracle(address _oracle) external onlyOwner {
        oracle = _oracle;
        emit OracleUpdated(_oracle);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        owner = newOwner;
    }
}
