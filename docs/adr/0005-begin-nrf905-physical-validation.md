# ADR 0005: Begin nRF905 physical adapter validation

- Status: Accepted
- Date: 2026-07-23
- Supersedes: the active milestone boundary in ADR 0004 after human review of deterministic replay

## Context

The deterministic recording player now moves known frames through the supported receive boundary with exact, clock-controlled tests. The user reviewed that checkpoint and selected the nRF905 as the first physical adapter. The available bench consists of two Raspberry Pi 5 computers and two nRF905 modules, which is enough to test each radio as both transmitter and receiver.

The historical `driver/nrf905.py` cannot be reused. It is frozen v0 evidence, couples hardware and virtual routing, uses an incompatible radio profile, and is not part of the supported layered runtime. The nRF905 remains an experimental first adapter rather than a platform commitment.

## Decision

Begin milestone `nrf905-physical-adapter-validation` with these boundaries:

- add a new isolated adapter under `packet_predator/adapters/`; do not modify or import the archived driver;
- keep SPI device, GPIO lines, RF band/channel, hardware address, CRC, crystal, and transmit permission in an explicit deployment profile;
- retain inspect-only startup unless an operator deliberately supplies an adapter profile;
- carry only complete 32-byte Protocol Contract frames through nRF905, with the shared reference codec remaining the only application-wire authority;
- provide a register write/readback probe before permitting an over-air test;
- require an explicit profile permission and a per-request confirmation before transmission;
- validate exact bytes in both directions between the two Raspberry Pis using released contract examples; and
- record capture/transmit provenance in the existing process-local journal without adding node emulation, responses, game state, or policy.

The browser may be exposed to a trusted local network for this development bench. It has no authentication and is not suitable for an untrusted network. Localhost plus SSH port forwarding remains the safer default.

## Validation sequence

1. On each Pi, validate the profile and open SPI/GPIO.
2. Put the radio in a programming-safe mode, write its ten configuration bytes, and require exact readback.
3. Start receive mode on Pi B and send one released controller-originated fixture from Pi A.
4. Require Pi B to receive the exact expected 32 bytes and decode them with Protocol Contract `1.0.1`.
5. Reverse the roles with one released node-originated fixture.

The software and fake-backend tests can be completed without the physical bench. This milestone is not closed until both over-air directions are run on the user's hardware and the evidence is reviewed.

## Consequences

Packet Predator gains real capture and explicit manual transmission through one adapter without becoming a Game Controller or simulated participant. Hardware failures can be localized to profile validation, Linux device access, nRF905 register communication, transmit completion, or received-byte comparison. A later adapter can implement the same opaque-frame boundary without inheriting nRF905 configuration.

## Physical validation outcome

On 2026-07-24, the two available Raspberry Pi 5 and original Packet Predator nRF905 HAT benches passed the required exchange in both directions:

- Pi A transmitted the exact fixed `v1-controller-beacon` fixture, reported completion after 6.999 ms, and Pi B received the same 32 bytes and decoded `CONTROLLER_BEACON`.
- Pi B transmitted the exact fixed `v1-node-status` fixture, reported completion after 7.003 ms, and Pi A received the same 32 bytes and decoded `NODE_STATUS`.

The recovered HAT profile uses SPI0 CE0, `PWR_UP` GPIO21, `TRX_CE` GPIO7, `TX_EN` GPIO23, `CD` GPIO18, `AM` GPIO22, and `DR` GPIO17. The first passing run reproduced the archived 125 kHz SPI baseline; a subsequent complete bidirectional run also passed at 1 MHz, which is now the shipped example setting. Raspberry Pi 5 requires `dtoverlay=spi0-1cs` to release GPIO7 from the unused SPI0 CE1 function. These deployment details do not alter the v1 wire contract.

The complete configuration, failure diagnosis, exact frames, results, and limits of the evidence are recorded in [nRF905 physical validation result — 2026-07-24](../nrf905-validation-2026-07-24.md).
