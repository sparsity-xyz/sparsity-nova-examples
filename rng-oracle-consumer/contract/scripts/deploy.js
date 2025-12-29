const hre = require("hardhat");
require("dotenv").config();

async function main() {
    const rngContractAddress = process.env.RNG_CONTRACT_ADDRESS;

    if (!rngContractAddress) {
        throw new Error("RNG_CONTRACT_ADDRESS not set in .env");
    }

    console.log("Deploying RNGConsumer...");
    console.log("RNG Contract Address:", rngContractAddress);

    const RNGConsumer = await hre.ethers.getContractFactory("RNGConsumer");
    const consumer = await RNGConsumer.deploy(rngContractAddress);

    await consumer.waitForDeployment();
    const consumerAddress = await consumer.getAddress();

    console.log("\n✅ RNGConsumer deployed to:", consumerAddress);
    console.log("\nVerify with:");
    console.log(`npx hardhat verify --network baseSepolia ${consumerAddress} ${rngContractAddress}`);

    // Save deployment info
    const fs = require("fs");
    const deploymentInfo = {
        network: hre.network.name,
        consumerAddress: consumerAddress,
        rngContractAddress: rngContractAddress,
        deployedAt: new Date().toISOString()
    };

    fs.writeFileSync(
        "deployment.json",
        JSON.stringify(deploymentInfo, null, 2)
    );
    console.log("\nDeployment info saved to deployment.json");
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
