// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {EnergyMarket} from "../src/EnergyMarket.sol";
import {MeterRegistry} from "../src/MeterRegistry.sol";

contract EnergyMarketTest is Test {
    MeterRegistry registry;
    EnergyMarket market;

    uint32 constant FEED_IN = 300;
    uint32 constant RETAIL = 850;
    uint64 constant SLOT = 1352683800; // 2012-11-12 11:30 AEST

    uint256[4] keys = [uint256(0xA11CE), 0xB0B, 0xC0FFEE, 0xD00D];

    function setUp() public {
        registry = new MeterRegistry();
        market = new EnergyMarket(registry, FEED_IN, RETAIL, 0);
        for (uint32 i = 0; i < 4; i++) {
            registry.register(i + 1, vm.addr(keys[i]));
        }
        market.startRun();
    }

    // --- helpers ---------------------------------------------------------------

    function _reading(uint32 meterId, uint64 importWh, uint64 exportWh)
        internal
        view
        returns (EnergyMarket.Reading memory)
    {
        bytes32 digest = market.readingDigest(meterId, SLOT, importWh, exportWh);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(keys[meterId - 1], digest);
        return EnergyMarket.Reading(meterId, importWh, exportWh, abi.encodePacked(r, s, v));
    }

    function _trades() internal pure returns (EnergyMarket.Trade[] memory t) {
        t = new EnergyMarket.Trade[](2);
        t[0] = EnergyMarket.Trade(1, 2, 500, 497);
        t[1] = EnergyMarket.Trade(3, 4, 300, 299);
    }

    function _readings() internal view returns (EnergyMarket.Reading[] memory rs) {
        rs = new EnergyMarket.Reading[](4);
        rs[0] = _reading(1, 0, 520); // seller, delivered a little more than contracted
        rs[1] = _reading(2, 497, 0); // buyer, used exactly what was delivered
        rs[2] = _reading(3, 0, 120); // seller, short by 180 Wh
        rs[3] = _reading(4, 400, 0); // buyer, used more
    }

    function _commit(uint32 price, EnergyMarket.Trade[] memory t) internal {
        market.commit(SLOT, keccak256(abi.encode(SLOT, price, t)));
    }

    // --- happy path ------------------------------------------------------------

    function test_commitThenSettle() public {
        EnergyMarket.Trade[] memory t = _trades();
        _commit(575, t);
        vm.recordLogs();
        market.settle(SLOT, 575, t, _readings());
        assertTrue(market.settlements(1, SLOT) != bytes32(0));
        assertEq(vm.getRecordedLogs().length, 5); // 4 households + Settled
    }

    function test_settlementAmountsAreTheTwoPassRule() public {
        EnergyMarket.Trade[] memory t = _trades();
        _commit(575, t);
        // Meter 3 sold 300 Wh but exported 120: market +575*300, imbalance -180 Wh at retail.
        vm.expectEmit(true, true, true, true);
        emit EnergyMarket.HouseholdSettled(1, SLOT, 3, int256(575 * 300), -int256(180) * 850);
        // Meter 4 was delivered 299 Wh and imported 400: pays 575*299, the extra 101 Wh at retail.
        vm.expectEmit(true, true, true, true);
        emit EnergyMarket.HouseholdSettled(1, SLOT, 4, -int256(575 * 299), -int256(101) * 850);
        market.settle(SLOT, 575, t, _readings());
    }

    // --- byte-for-byte agreement with the Python engine (sim/crypto.py) ----------

    function test_commitmentMatchesPython() public pure {
        EnergyMarket.Trade[] memory t = new EnergyMarket.Trade[](2);
        t[0] = EnergyMarket.Trade(12, 10, 81, 81);
        t[1] = EnergyMarket.Trade(2, 1, 412, 411);
        // crypto.commitment(1352683800, 575, trades) computed in Python with eth_abi.
        assertEq(
            keccak256(abi.encode(SLOT, uint32(575), t)),
            0x73b3b5baf875a6dd6374b89aa1f6f76a1bfd1976b3860cbf83dde4335192200b
        );
    }

    function test_pythonMeterSignatureRecovers() public view {
        // crypto.Meter(7, seed=20121112, chain 31337, this test's market address).sign(SLOT, 106, 0)
        assertEq(address(market), 0x2e234DAe75C793f67A35089C9d99245E1C58470b);
        bytes memory sig =
            hex"bbfb835f542f7a0680e4d46d6e24f136b5e803b541c2fb0c6a5d4803ee4d0efc6fe6fd7a3d4cd6b0a9e2d6de03f15ce192f6e4a6c19c36272b02ac3d1066e5991c";
        address signer = this.recoverExternal(market.readingDigest(7, SLOT, 106, 0), sig);
        assertEq(signer, 0xd1eFBE398536F0c2c1FB295DB831CcAe9A525d5c);
    }

    function recoverExternal(bytes32 digest, bytes calldata sig) external view returns (address) {
        return market.recover(digest, sig);
    }

    function test_emptySlotSettlesWithoutBandCheck() public {
        EnergyMarket.Trade[] memory none = new EnergyMarket.Trade[](0);
        _commit(0, none);
        market.settle(SLOT, 0, none, _readings());
    }

    // --- the operator cannot restate -------------------------------------------

    function test_restatedTradesFailTheCommitment() public {
        EnergyMarket.Trade[] memory t = _trades();
        _commit(575, t);
        t[0].deliveredWh = 499; // claim fewer losses after the fact
        EnergyMarket.Reading[] memory signed = _readings();
        vm.expectRevert(EnergyMarket.CommitmentMismatch.selector);
        market.settle(SLOT, 575, t, signed);
    }

    function test_restatedPriceFailsTheCommitment() public {
        EnergyMarket.Trade[] memory t = _trades();
        _commit(575, t);
        EnergyMarket.Reading[] memory signed = _readings();
        vm.expectRevert(EnergyMarket.CommitmentMismatch.selector);
        market.settle(SLOT, 600, t, signed);
    }

    function test_cannotSettleWithoutCommitment() public {
        EnergyMarket.Reading[] memory signed = _readings();
        vm.expectRevert(EnergyMarket.NotCommitted.selector);
        market.settle(SLOT, 575, _trades(), signed);
    }

    function test_cannotCommitTwice() public {
        _commit(575, _trades());
        vm.expectRevert(EnergyMarket.AlreadyCommitted.selector);
        _commit(600, _trades());
    }

    function test_cannotSettleTwice() public {
        EnergyMarket.Trade[] memory t = _trades();
        _commit(575, t);
        market.settle(SLOT, 575, t, _readings());
        EnergyMarket.Reading[] memory signed = _readings();
        vm.expectRevert(EnergyMarket.AlreadySettled.selector);
        market.settle(SLOT, 575, t, signed);
    }

    // --- the band, layer 3 -----------------------------------------------------

    function test_priceOnTheBandEdgeIsRefused() public {
        EnergyMarket.Trade[] memory t = _trades();
        _commit(850, t);
        EnergyMarket.Reading[] memory signed = _readings();
        vm.expectRevert(abi.encodeWithSelector(EnergyMarket.PriceOutsideBand.selector, uint32(850)));
        market.settle(SLOT, 850, t, signed);
    }

    function testFuzz_inBandMatchesTheRule(uint32 price) public view {
        assertEq(market.inBand(price), price > FEED_IN && price < RETAIL);
    }

    // --- signatures and readings -----------------------------------------------

    function test_readingSignedByTheWrongKeyIsRefused() public {
        EnergyMarket.Trade[] memory t = _trades();
        _commit(575, t);
        EnergyMarket.Reading[] memory rs = _readings();
        bytes32 digest = market.readingDigest(3, SLOT, 0, 120);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(keys[3], digest); // meter 4's key signs meter 3's reading
        rs[2].signature = abi.encodePacked(r, s, v);
        vm.expectRevert(abi.encodeWithSelector(EnergyMarket.BadSignature.selector, uint32(3)));
        market.settle(SLOT, 575, t, rs);
    }

    function test_alteredReadingIsRefused() public {
        EnergyMarket.Trade[] memory t = _trades();
        _commit(575, t);
        EnergyMarket.Reading[] memory rs = _readings();
        rs[2].exportWh = 300; // the short seller claims full delivery with the old signature
        vm.expectRevert(abi.encodeWithSelector(EnergyMarket.BadSignature.selector, uint32(3)));
        market.settle(SLOT, 575, t, rs);
    }

    function test_traderWithoutAReadingIsRefused() public {
        EnergyMarket.Trade[] memory t = _trades();
        _commit(575, t);
        EnergyMarket.Reading[] memory full = _readings();
        EnergyMarket.Reading[] memory rs = new EnergyMarket.Reading[](3);
        (rs[0], rs[1], rs[2]) = (full[0], full[1], full[2]);
        vm.expectRevert(abi.encodeWithSelector(EnergyMarket.MissingReading.selector, uint32(4)));
        market.settle(SLOT, 575, t, rs);
    }

    function test_duplicateReadingsAreRefused() public {
        EnergyMarket.Trade[] memory t = _trades();
        _commit(575, t);
        EnergyMarket.Reading[] memory rs = _readings();
        rs[1] = rs[0];
        vm.expectRevert(EnergyMarket.ReadingsNotSorted.selector);
        market.settle(SLOT, 575, t, rs);
    }

    function test_onlyTheOperatorCommitsAndSettles() public {
        vm.prank(address(0xBAD));
        vm.expectRevert(EnergyMarket.NotOperator.selector);
        market.commit(SLOT, bytes32(uint256(1)));
    }

    function test_keysCannotBeReplaced() public {
        vm.expectRevert(abi.encodeWithSelector(MeterRegistry.AlreadyRegistered.selector, uint32(1)));
        registry.register(1, address(0xBAD));
    }

    function test_newRunIsPublicAndSeparatesCommitments() public {
        _commit(575, _trades());
        vm.expectEmit(true, false, false, false);
        emit EnergyMarket.RunStarted(2);
        market.startRun();
        _commit(575, _trades()); // same slot, new run
        assertTrue(market.commitments(1, SLOT) != bytes32(0));
        assertTrue(market.commitments(2, SLOT) != bytes32(0));
    }
}
