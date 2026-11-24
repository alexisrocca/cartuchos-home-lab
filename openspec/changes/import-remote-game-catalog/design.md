## Context

Cartuchos already invokes Hestia directly and supports an SSH destination for shared Hermes profiles. The server stores installed game metadata independently of the graphical session.

## Goals / Non-Goals

- Discover usable games and enough metadata to launch them through the current Cartuchos flow.
- Keep the library useful when the server is offline and preserve personalized local records.
- Session lifecycle, structured streaming events and power-policy changes are later stages.

## Decisions

- Run a read-only exporter on demand through the existing SSH connection. Avoid an additional listener.
- Return a version 1 JSON envelope with stable IDs, Hermes application names and optional selection, launcher status, relative-mouse and artwork fields.
- Match imports by remote identity. Existing local entries retain user-owned data. Missing or unverifiable artwork is optional.

## Risks / Trade-offs

- A catalog can only advertise launch mappings the exporter can determine reliably. Unknown platforms or custom profiles may require manual metadata.
- The client must reject incompatible versions and leave the library intact on connection or validation failure.

## Follow-up architecture

| Stage | Proposed interface | Verification before adoption |
| --- | --- | --- |
| Server-owned launch session | A request contains a catalog ID and returns an opaque session ID. Server tracks the game within that session and keeps cleanup idempotent. | Launch and exit a Steam game and a launcher-backed game. Confirm the launcher staying open cannot keep the stream alive and cancellation only affects its own session. |
| Structured Hestia events | Versioned events carry session ID, phase, and actionable error details from first connection through first frame and termination. | Exercise connection failure, shaders, sign-in, first video and exit. Keep the existing transport available until both sides agree on the protocol. |
| Idle cleanup | Reference-count graphical leases and restore the configured idle profile when the last one ends. | Confirm Gamescope and the performance profile are released on normal exit and unexpected disconnect; confirm unrelated workloads continue. Power-off remains separately configurable. |
