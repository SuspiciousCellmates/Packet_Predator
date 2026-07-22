# Deterministic recordings

Deterministic replay answers a narrow development question: “What will the workbench show if these exact frames arrive in this exact order?” It is a packet-recording player, not a game simulator.

## Runtime model

Packet Predator starts with the inspect-only transport. Selecting a recording resolves every referenced example through the sibling Protocol Contract, validates every resulting frame, and loads those opaque bytes into the replay transport. Nothing is delivered until the operator presses **Step** or **Play**.

The replay transport understands only sequence number, scheduled offset, direction, complete frame bytes, representation, and provenance. It does not inspect fields or know what a Player, Task, outcome, or controller decision means. The workbench service decodes each delivered frame through the same wire adapter used for pasted input and attaches replay provenance to the process-local journal.

Playback is advanced by explicit browser/API polling against an injectable monotonic clock. There is no background actor thread. Tests control that clock directly and prove the boundaries at which each frame becomes due.

## Recording format

Files live in `recordings/` and contain:

- one schema and required Protocol Contract release;
- a stable recording identifier, title, and factual description;
- one logical or fixed-frame representation for the recording;
- a finite duration; and
- an ordered array of scheduled entries.

Each entry names a released conformance example, its scheduled millisecond offset, observed direction, optional scenario-local source and destination addresses, and a factual note. Endpoint changes are re-encoded and validated by the reference codec; the recording never patches raw bytes itself.

Unknown fields are rejected deliberately. This prevents an innocent-looking recording from acquiring conditions, branches, inferred replies, or executable behavior. Timing must be nondecreasing, every address must fit the shared envelope, every route must be valid for its referenced message, and the final entry must fit within the declared duration.

## Authoring rules

- Prefer a released example reference over copied frame hex.
- Describe only what the listed frame demonstrates; do not invent why the Game Controller chose it.
- Keep endpoint assignments internally understandable when combining otherwise independent conformance examples.
- Use repeated references deliberately when demonstrating retries or duplicate delivery.
- Never add randomness, branching, conditions, actor state, success criteria, assertions about game policy, or automatic responses.
- Run `./scripts/check`; malformed recording structure and invalid fixture references must fail.

An actual captured-session import/export format remains parked for later design. These hand-authored recordings are small, reviewable demonstrations for this milestone.
