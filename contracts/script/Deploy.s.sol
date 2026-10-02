// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {EnergyMarket} from "../src/EnergyMarket.sol";
import {MeterRegistry} from "../src/MeterRegistry.sol";

/// Deploys the registry and the settlement contract with the tariff band from
/// config/market.json, and records the addresses in deployments/<chainid>.json
/// for the Python engine to pick up.
///
///   local:  forge script script/Deploy.s.sol --rpc-url local --broadcast --private-key <anvil key 0>
///   amoy:   forge script script/Deploy.s.sol --rpc-url amoy --broadcast --private-key $OPERATOR_KEY --verify
///
/// The deployer becomes the operator and the registry owner. Meter keys are
/// registered afterwards by the engine, which knows them.
contract Deploy is Script {
    function run() external {
        string memory cfg = vm.readFile(string.concat(vm.projectRoot(), "/../config/market.json"));
        uint32 feedIn = uint32(vm.parseJsonUint(cfg, ".feed_in_tariff_paise_per_kwh"));
        uint32 retail = uint32(vm.parseJsonUint(cfg, ".retail_tariff_paise_per_kwh"));
        uint32 wheeling = uint32(vm.parseJsonUint(cfg, ".wheeling_charge_paise_per_kwh"));

        vm.startBroadcast();
        MeterRegistry registry = new MeterRegistry();
        EnergyMarket market = new EnergyMarket(registry, feedIn, retail, wheeling);
        vm.stopBroadcast();

        string memory key = "deployment";
        vm.serializeUint(key, "chainId", block.chainid);
        vm.serializeUint(key, "deployedAtBlock", block.number);
        vm.serializeAddress(key, "registry", address(registry));
        string memory json = vm.serializeAddress(key, "market", address(market));
        vm.writeJson(json, string.concat(vm.projectRoot(), "/deployments/", vm.toString(block.chainid), ".json"));

        console.log("MeterRegistry", address(registry));
        console.log("EnergyMarket ", address(market));
    }
}
