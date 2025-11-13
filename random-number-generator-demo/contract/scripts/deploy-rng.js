const hre = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
  console.log("\n" + "=".repeat(70));
  console.log("🎲 Deploying Random Number Generator");
  console.log("=".repeat(70));

  // Get deployer account
  const [deployer] = await hre.ethers.getSigners();
  const balance = await hre.ethers.provider.getBalance(deployer.address);
  const network = await hre.ethers.provider.getNetwork();

  console.log("\n📊 Network Info:");
  console.log("   Network:", hre.network.name);
  console.log("   Chain ID:", network.chainId.toString());

  console.log("\n👤 Deployer:");
  console.log("   Address:", deployer.address);
  console.log("   Balance:", hre.ethers.formatEther(balance), "ETH");

  if (balance === 0n) {
    console.error("\n❌ Deployer has zero balance!");
    if (hre.network.name === "baseSepolia") {
      console.log("\n🪙  Get Base Sepolia ETH from:");
      console.log("   https://www.coinbase.com/faucets/base-ethereum-sepolia-faucet");
    }
    process.exit(1);
  }

  // Deploy contract
  console.log("\n📦 Deploying RandomNumberGenerator...");
  const RandomNumberGenerator = await hre.ethers.getContractFactory("RandomNumberGenerator");
  const rng = await RandomNumberGenerator.deploy();

  await rng.waitForDeployment();
  const rngAddress = await rng.getAddress();

  console.log("✅ RandomNumberGenerator deployed to:", rngAddress);
  console.log("👑 Owner:", await rng.owner());

  // Save deployment info
  const deploymentInfo = {
    network: hre.network.name,
    chainId: network.chainId.toString(),
    contractAddress: rngAddress,
    owner: deployer.address,
    deployedAt: new Date().toISOString(),
    blockNumber: await hre.ethers.provider.getBlockNumber(),
    explorerUrl: getExplorerUrl(hre.network.name, rngAddress)
  };

  const deploymentPath = path.join(__dirname, "../rng-deployment.json");
  fs.writeFileSync(deploymentPath, JSON.stringify(deploymentInfo, null, 2));
  console.log("\n💾 Deployment info saved to rng-deployment.json");

  // Export ABI
  const artifactPath = path.join(__dirname, "../artifacts/contracts/RandomNumberGenerator.sol/RandomNumberGenerator.json");
  const artifact = JSON.parse(fs.readFileSync(artifactPath, "utf8"));

  const rngBackendDir = path.join(__dirname, "../../backend");
  if (!fs.existsSync(rngBackendDir)) {
    fs.mkdirSync(rngBackendDir, { recursive: true });
  }

  const abiPath = path.join(rngBackendDir, "abi.json");
  fs.writeFileSync(abiPath, JSON.stringify(artifact.abi, null, 2));
  console.log("📋 ABI exported to rng-backend/rng-abi.json");

  // Update backend config
  updateBackendConfig(rngAddress, hre.network.name);

  // Wait for confirmation (testnet only)
  if (hre.network.name === "baseSepolia") {
    console.log("\n⏳ Waiting for 3 block confirmations...");
    await rng.deploymentTransaction().wait(3);
    console.log("✅ Contract confirmed!");
  }

  console.log("\n" + "=".repeat(70));
  console.log("🎉 Deployment Complete!");
  console.log("=".repeat(70));

  console.log("\n📌 Contract Address:", rngAddress);
  if (deploymentInfo.explorerUrl) {
    console.log("🔍 Explorer:", deploymentInfo.explorerUrl);
  }

  console.log("\n📌 Next Steps:");
  console.log("1. Register operator:");
  console.log(`   OPERATOR_ADDRESS=<operator_address> npx hardhat run scripts/register-operator.js --network ${hre.network.name}`);
  console.log("\n2. Start off-chain service:");
  console.log("   cd backend && python main.py");
  console.log("\n3. Test the RNG:");
  console.log(`   npx hardhat run scripts/test-rng.js --network ${hre.network.name}`);
  console.log("=".repeat(70));
}

function getExplorerUrl(network, address) {
  const explorers = {
    baseSepolia: "https://sepolia.basescan.org",
    base: "https://basescan.org",
    localhost: null,
    hardhat: null
  };

  const baseUrl = explorers[network];
  return baseUrl ? `${baseUrl}/address/${address}` : null;
}

function updateBackendConfig(contractAddress, network) {
  const configPath = path.join(__dirname, "../../backend/config.py");
  let config = fs.readFileSync(configPath, "utf8");

  // Update contract address
  config = config.replace(
    /CONTRACT_ADDRESS = "0x[a-fA-F0-9]{40}"/,
    `CONTRACT_ADDRESS = "${contractAddress}"`
  );

  // Update RPC URL based on network
  const rpcUrls = {
    localhost: "http://127.0.0.1:8545",
    hardhat: "http://127.0.0.1:8545",
    baseSepolia: process.env.BASE_SEPOLIA_RPC,
    base: "https://mainnet.base.org"
  };

  if (rpcUrls[network]) {
    config = config.replace(
      /RPC_URL = ".+"/,
      `RPC_URL = "${rpcUrls[network]}"`
    );
  }

  fs.writeFileSync(configPath, config);
  console.log("⚙️  Backend config.py updated");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error("\n❌ Deployment failed:");
    console.error(error);
    process.exit(1);
  });