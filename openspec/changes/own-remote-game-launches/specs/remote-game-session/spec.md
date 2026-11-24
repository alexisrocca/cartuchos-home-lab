## ADDED Requirements

### Requirement: Exclusive reservation

The server SHALL resolve the requested game from the configured catalog and issue an opaque session ID. The shared launcher SHALL claim a live reservation at most once.

#### Scenario: Two clients request the shared launcher

- **WHEN** a valid reservation is active and another managed launch is requested
- **THEN** the server rejects the second request without modifying the first reservation

### Requirement: Owned cleanup

A cleanup request SHALL affect only the matching session. Cleanup and abandoned reservation expiry SHALL preserve any newer reservation.

#### Scenario: Delayed cleanup arrives

- **WHEN** a client attempts to release an earlier session after a new reservation exists
- **THEN** the new reservation and its launcher remain intact

### Requirement: Legacy compatibility

Cartuchos SHALL preserve legacy launches when the server explicitly lacks the session helper.

#### Scenario: A managed request fails

- **WHEN** the server rejects a reservation or the request outcome is ambiguous
- **THEN** Cartuchos reports the error and does not attempt a legacy selection write
