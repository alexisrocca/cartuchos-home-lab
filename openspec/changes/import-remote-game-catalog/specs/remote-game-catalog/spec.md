## ADDED Requirements

### Requirement: Catalog discovery

Cartuchos SHALL request the remote game catalog over the configured SSH destination. The exporter SHALL return a versioned catalog with a stable identifier, display name and Hermes application name for each available game.

#### Scenario: User imports from an available server

- **WHEN** the user requests a Home Lab import and the server returns a valid catalog
- **THEN** Cartuchos adds or refreshes the entries with their launch metadata and available artwork

### Requirement: Local durability

Cartuchos SHALL cache successful imports locally and preserve user-owned library data during a refresh.

#### Scenario: User refreshes a previously imported game

- **WHEN** the same remote game identifier is returned again
- **THEN** Cartuchos updates its remote launch metadata without creating a duplicate or overriding customized cover art

#### Scenario: Catalog is offline or incompatible

- **WHEN** the connection fails or the catalog format cannot be used
- **THEN** Cartuchos displays an error and retains the existing library
