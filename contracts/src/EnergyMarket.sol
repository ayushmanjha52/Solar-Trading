// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {MeterRegistry} from "./MeterRegistry.sol";

/// @title EnergyMarket
/// @notice Settlement anchor for a peer-to-peer market on one LV feeder.
///
/// What this contract does, and deliberately nothing more:
///   1. commit: before a slot is delivered, the operator publishes
///      keccak256(abi.encode(slotStart, price, trades)). Without this step the
///      operator could run the auction, observe the outcome, and settle a
///      different one.
///   2. settle: after delivery, the operator submits the trades and every
///      meter's signed reading. The contract checks the trades reproduce the
///      commitment, the price sits strictly inside the tariff band, every
///      reading is signed by its meter's registered key, and every trading
///      household has a reading. It then computes the two-pass settlement
///      (market at the cleared price, imbalance at grid tariffs) and emits it.
///
/// Matching is NOT done here. An order-book walk on chain costs gas in
/// proportion to the number of participants; the chain's job is to make the
/// result checkable and tamper-evident, not to compute it.
///
/// @dev THE ORACLE PROBLEM IS RELOCATED, NOT SOLVED. This contract cannot
///      observe a kilowatt-hour. It verifies that a reading was signed by the
///      key that MeterRegistry associates with a meter id. If a meter's key is
///      extracted, or the meter is tampered with so that it signs false
///      measurements, this contract will accept the false reading. Trust has
///      moved from the operator into each meter's secure element and into
///      whoever controls the registry. In this project the meters are
///      simulated software processes, so that trust is assumed, not earned.
contract EnergyMarket {
    struct Trade {
        uint32 seller;
        uint32 buyer;
        uint64 injectedWh;
        uint64 deliveredWh;
    }

    struct Reading {
        uint32 meterId;
        uint64 importWh;
        uint64 exportWh;
        bytes signature; // EIP-712, 65 bytes r||s||v
    }

    bytes32 private constant DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 public constant READING_TYPEHASH =
        keccak256("MeterReading(uint32 meterId,uint64 slotStart,uint64 importWh,uint64 exportWh)");
    uint256 private constant SECP256K1_HALF_N =
        0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0;

    MeterRegistry public immutable registry;
    address public immutable operator;
    /// Tariffs in paise per kWh. Money below is milli-paise: price x Wh, exact.
    uint32 public immutable feedIn;
    uint32 public immutable retail;
    uint32 public immutable wheeling;
    bytes32 public immutable DOMAIN_SEPARATOR;

    /// A run is one continuous simulated timeline. Starting a new run is a
    /// public event; in production there is exactly one run.
    uint64 public currentRun;
    mapping(uint64 run => mapping(uint64 slotStart => bytes32)) public commitments;
    mapping(uint64 run => mapping(uint64 slotStart => bytes32)) public settlements;

    event RunStarted(uint64 indexed run);
    event Committed(uint64 indexed run, uint64 indexed slotStart, bytes32 commitment);
    event HouseholdSettled(
        uint64 indexed run, uint64 indexed slotStart, uint32 indexed meterId, int256 marketMp, int256 imbalanceMp
    );
    event Settled(
        uint64 indexed run, uint64 indexed slotStart, uint32 price, uint256 injectedWh, uint256 deliveredWh, bytes32 evidence
    );

    error NotOperator();
    error AlreadyCommitted();
    error NotCommitted();
    error AlreadySettled();
    error CommitmentMismatch();
    error PriceOutsideBand(uint32 price);
    error ReadingsNotSorted();
    error MeterIdTooLarge(uint32 meterId);
    error BadSignature(uint32 meterId);
    error MissingReading(uint32 meterId);
    error LossExceedsInjection();

    modifier onlyOperator() {
        if (msg.sender != operator) revert NotOperator();
        _;
    }

    constructor(MeterRegistry registry_, uint32 feedIn_, uint32 retail_, uint32 wheeling_) {
        require(uint256(feedIn_) + 1 < uint256(retail_) - wheeling_, "band is closed");
        registry = registry_;
        operator = msg.sender;
        feedIn = feedIn_;
        retail = retail_;
        wheeling = wheeling_;
        DOMAIN_SEPARATOR = keccak256(
            abi.encode(
                DOMAIN_TYPEHASH, keccak256("LocalEnergyMarket"), keccak256("1"), block.chainid, address(this)
            )
        );
    }

    function startRun() external onlyOperator returns (uint64) {
        currentRun += 1;
        emit RunStarted(currentRun);
        return currentRun;
    }

    /// @notice Publish the hash of a slot's cleared trades at gate closure.
    function commit(uint64 slotStart, bytes32 commitment) external onlyOperator {
        if (commitments[currentRun][slotStart] != bytes32(0)) revert AlreadyCommitted();
        commitments[currentRun][slotStart] = commitment;
        emit Committed(currentRun, slotStart, commitment);
    }

    /// @notice Band check, layer 3 of 3: strictly above feed-in, strictly below retail minus wheeling.
    function inBand(uint32 price) public view returns (bool) {
        return price > feedIn && uint256(price) + wheeling < retail;
    }

    function readingDigest(uint32 meterId, uint64 slotStart, uint64 importWh, uint64 exportWh)
        public
        view
        returns (bytes32)
    {
        bytes32 structHash = keccak256(abi.encode(READING_TYPEHASH, meterId, slotStart, importWh, exportWh));
        return keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR, structHash));
    }

    function recover(bytes32 digest, bytes calldata sig) public pure returns (address) {
        if (sig.length != 65) return address(0);
        bytes32 r = bytes32(sig[0:32]);
        bytes32 s = bytes32(sig[32:64]);
        uint8 v = uint8(sig[64]);
        if (v < 27) v += 27;
        // Reject malleable signatures (upper-half s) and invalid v.
        if (uint256(s) > SECP256K1_HALF_N || (v != 27 && v != 28)) return address(0);
        return ecrecover(digest, v, r, s);
    }

    /// @notice Settle a committed slot against every meter's signed reading.
    /// @param readings one per meter, sorted by strictly increasing meterId.
    function settle(uint64 slotStart, uint32 price, Trade[] calldata trades, Reading[] calldata readings)
        external
        onlyOperator
    {
        uint64 run = currentRun;
        _checkCommitment(run, slotStart, price, trades);
        Positions memory pos = _positions(trades, _verifyReadings(slotStart, readings));
        _settleHouseholds(run, slotStart, price, readings, pos);
        bytes32 evidence = keccak256(abi.encode(run, slotStart, price, trades, readings));
        settlements[run][slotStart] = evidence;
        emit Settled(run, slotStart, price, pos.injected, pos.delivered, evidence);
    }

    struct Positions {
        int256[256] exported; // contracted export per meter, Wh
        int256[256] imported; // contracted import per meter, Wh
        uint256 injected;
        uint256 delivered;
    }

    /// The trades must reproduce the commitment published at gate closure, and the price must sit in the band.
    function _checkCommitment(uint64 run, uint64 slotStart, uint32 price, Trade[] calldata trades) internal view {
        bytes32 committed = commitments[run][slotStart];
        if (committed == bytes32(0)) revert NotCommitted();
        if (settlements[run][slotStart] != bytes32(0)) revert AlreadySettled();
        if (keccak256(abi.encode(slotStart, price, trades)) != committed) revert CommitmentMismatch();
        if (trades.length > 0 && !inBand(price)) revert PriceOutsideBand(price);
    }

    /// Every reading must be signed by its meter's registered key. Returns a bitmap of meters seen.
    function _verifyReadings(uint64 slotStart, Reading[] calldata readings) internal view returns (uint256 seen) {
        uint32 last;
        for (uint256 i = 0; i < readings.length; i++) {
            Reading calldata rd = readings[i];
            if (rd.meterId > 255) revert MeterIdTooLarge(rd.meterId);
            if (i > 0 && rd.meterId <= last) revert ReadingsNotSorted();
            last = rd.meterId;
            address signer = recover(readingDigest(rd.meterId, slotStart, rd.importWh, rd.exportWh), rd.signature);
            if (signer == address(0) || signer != registry.signerOf(rd.meterId)) revert BadSignature(rd.meterId);
            seen |= uint256(1) << rd.meterId;
        }
    }

    /// Contracted export and import per meter. Every trading household must have reported.
    function _positions(Trade[] calldata trades, uint256 seen) internal pure returns (Positions memory pos) {
        for (uint256 i = 0; i < trades.length; i++) {
            Trade calldata t = trades[i];
            if (t.seller > 255 || (seen >> t.seller) & 1 == 0) revert MissingReading(t.seller);
            if (t.buyer > 255 || (seen >> t.buyer) & 1 == 0) revert MissingReading(t.buyer);
            if (t.deliveredWh > t.injectedWh) revert LossExceedsInjection();
            pos.exported[t.seller] += int256(uint256(t.injectedWh));
            pos.imported[t.buyer] += int256(uint256(t.deliveredWh));
            pos.injected += t.injectedWh;
            pos.delivered += t.deliveredWh;
        }
    }

    /// Pass 1 (market, at the cleared price) and pass 2 (imbalance, at grid tariffs), in milli-paise.
    function _settleHouseholds(
        uint64 run,
        uint64 slotStart,
        uint32 price,
        Reading[] calldata readings,
        Positions memory pos
    ) internal {
        int256 p = int256(uint256(price));
        int256 pw = int256(uint256(price) + wheeling);
        for (uint256 i = 0; i < readings.length; i++) {
            uint32 m = readings[i].meterId;
            int256 deviation = (int256(uint256(readings[i].exportWh)) - int256(uint256(readings[i].importWh)))
                - (pos.exported[m] - pos.imported[m]);
            int256 imbalance = deviation > 0 ? deviation * int256(uint256(feedIn)) : deviation * int256(uint256(retail));
            emit HouseholdSettled(run, slotStart, m, p * pos.exported[m] - pw * pos.imported[m], imbalance);
        }
    }
}
