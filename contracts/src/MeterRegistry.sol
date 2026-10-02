// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @title MeterRegistry
/// @notice Maps each meter id to the address of the key that signs its readings.
/// @dev The registry is where trust in the physical world enters the system. A
///      contract cannot observe a kilowatt-hour; it can only check that a
///      reading was signed by the key registered here. Whoever controls
///      registration controls which keys count, so in production registration
///      belongs to the DISCOM's meter provisioning process, and each key lives
///      inside the meter's secure element and never leaves it.
contract MeterRegistry {
    address public immutable owner;
    mapping(uint32 => address) public signerOf;
    uint32 public meterCount;

    event MeterRegistered(uint32 indexed meterId, address signer);

    error NotOwner();
    error AlreadyRegistered(uint32 meterId);
    error ZeroSigner();

    constructor() {
        owner = msg.sender;
    }

    /// @notice Register a meter's signing key. Keys cannot be replaced: a
    ///         changed key would let the operator rewrite whose readings count.
    function register(uint32 meterId, address signer) external {
        if (msg.sender != owner) revert NotOwner();
        if (signer == address(0)) revert ZeroSigner();
        if (signerOf[meterId] != address(0)) revert AlreadyRegistered(meterId);
        signerOf[meterId] = signer;
        meterCount += 1;
        emit MeterRegistered(meterId, signer);
    }

    function registerMany(uint32[] calldata meterIds, address[] calldata signers) external {
        if (msg.sender != owner) revert NotOwner();
        require(meterIds.length == signers.length, "length mismatch");
        for (uint256 i = 0; i < meterIds.length; i++) {
            if (signers[i] == address(0)) revert ZeroSigner();
            if (signerOf[meterIds[i]] != address(0)) revert AlreadyRegistered(meterIds[i]);
            signerOf[meterIds[i]] = signers[i];
            emit MeterRegistered(meterIds[i], signers[i]);
        }
        meterCount += uint32(meterIds.length);
    }
}
