// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.20;

import {Script, console} from "forge-std/Script.sol";
import {NovaAppBase} from "../src/NovaAppBase.sol";

contract DeployScript is Script {
    function run() public {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");

        vm.startBroadcast(deployerPrivateKey);

        NovaAppBase app = new NovaAppBase();
        console.log("NovaAppBase deployed at:", address(app));

        vm.stopBroadcast();
    }
}
