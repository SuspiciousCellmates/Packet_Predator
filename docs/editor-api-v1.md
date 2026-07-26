# Packet Predator editor and validation API v1

**Status:** Implemented browser/editor contract

**Date:** 2026-07-26

This HTTP interface supports Packet Predator's structured editor and an
explicit laptop validation client. It is a developer workbench interface, not
a Game Controller, Game Master, or general remote-administration API.

## Identity

`GET /api/status` and `GET /api/workbench/state` expose:

- `workbench_interface_version`;
- `application_version`;
- `process_instance_id`;
- `build_id`; and
- loaded Protocol Contract version.

`process_instance_id` changes on every service process start. A client must
not carry a model revision or transmit result assumption across a changed
process identity.

`build_id` identifies the deployed checkout when the launch environment can
provide it. `unknown` must remain visible when it cannot be proven.

## Message metadata

```text
GET /api/v1/editor/messages
GET /api/v1/editor/messages/{message_name}
```

The response is derived from the released registry and contains message name,
numeric type, valid producers/consumers, delivery/revision metadata, payload
size bounds, ordered fields, primitive type, declared validation constraints,
and applicable enum/flag labels.

Packet Predator does not maintain a second field catalogue. Unknown message
names return a stable error.

## Compose

```text
POST /api/v1/editor/compose
```

Request:

```json
{
  "definition": "NODE_HELLO",
  "source": 1,
  "destination": 0,
  "values": {
    "permanent_device_serial": 16909060,
    "boot_generation": 1,
    "component_class": 1,
    "synchronization_reason": 5,
    "hardware_model": 4097,
    "firmware_build_identifier": 16777217,
    "capability_fingerprint": 1662968791,
    "highest_supported_core_revision": 1,
    "highest_supported_component_profile_revision": 1,
    "last_applied_state_revision": 0
  },
  "representation": "fixed"
}
```

The server:

1. rejects unknown and extra payload fields;
2. converts API hexadecimal strings only for fields declared as bytes;
3. calls the released reference codec;
4. decodes the result again through the ordinary inspection boundary; and
5. returns canonical logical/fixed hexadecimal plus that inspection.

The API never accepts a client-supplied message layout or enum catalogue.
Integer fields accept JSON integers or unsigned decimal strings. Decimal
strings allow the browser to preserve the complete protocol `u64` range
without JavaScript-number rounding.

## Draft byte inspection

```text
POST /api/v1/editor/inspect
```

This route applies the same strict reference-codec decode to draft bytes
without adding an observation to the workbench journal. The ordinary
`/api/v1/inspect` route retains its existing behavior for deliberate pasted
observations.

## Draft provenance

The browser's single draft has a stable draft ID and copies:

- base fixture or observation identity;
- base logical/fixed bytes;
- source capture provenance;
- changed fields and bytes; and
- optional Hardware Validation Console run ID.

Editing an observation creates a draft. It does not alter the journal entry.
Switching selection with unsaved changes requires explicit discard or save.

Draft provenance is local metadata and is never added to the RF frame.

## Deliberate transmit

`POST /api/carrier/transmit` retains profile permission, codec validation, and
one-shot confirmation. A validation client additionally supplies
`request_id`, a 1–128 character supported identifier.

An editor transmission also supplies local `provenance`: draft ID, base
identity, changed field names, changed byte offsets, and an optional Console
run ID. The cached result returns this metadata unchanged. It is not encoded
into the over-air frame.

For one Packet Predator process:

- repeating the same request ID, frame, and mode returns the stored result with
  `replayed_result: true` and does not touch the radio;
- reusing an ID with different input is rejected;
- a simultaneous duplicate is rejected as in progress; and
- a request without an ID remains supported for the existing manual browser
  but cannot be recovered by a client.

The response carries the process identity and request ID. The service keeps a
bounded process-local result cache. If the process restarts before a client
recovers a result, the outcome is unknown and the client must not retry
automatically.

## Model stream

The validation client:

1. reads `/api/workbench/state`;
2. records process identity, revision, latest `journal_sequence`, and receiver
   state;
3. subscribes to `/api/workbench/events?after=REVISION`;
4. refetches the canonical snapshot when notified; and
5. archives relevant observations outside Packet Predator's bounded model.

Server-sent events are change notifications, not a second observation store.
The client uses `journal_sequence` for order within one process and does not
infer cross-host causality from timestamps.
