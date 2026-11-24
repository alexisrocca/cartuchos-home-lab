## Context

The Home Lab catalog already advertises games and maps them to a published Hermes profile. SSH is available without adding a network listener.

## Decisions

- Reserve by catalog identity, resolve server-side, and serialize access to the shared profile.
- Keep private server-side state under a lock. An opaque ID identifies the reservation; reject conflicting launches and mismatched cleanup.
- A launcher claims once across its existing Gamescope process lifecycle. An abandoned reservation expires. Release must be safe to retry after network failure.
- Enable managed launches only for catalog profiles whose wrapper can access the reservation under the same user. Other profiles retain their existing launch path until their execution context can participate safely.
- A positive capability check or unambiguous feature absence determines legacy compatibility. A contention error, transport failure or ambiguous response does not trigger the legacy write.
- The Hermes shared-profile launch command currently carries no caller session ID. The reservation protects cooperating clients; end-to-end stream ownership with unrelated Hestia clients requires a later protocol change.

## Rollout

Exercise reservation, contention, claim, stale cleanup and legacy behavior under an isolated home. Validate on the live host without modifying the running launcher. Deploy the server helper and wrapper together before enabling clients against the production host.
