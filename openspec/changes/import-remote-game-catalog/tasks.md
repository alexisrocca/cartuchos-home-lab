## 1. Catalog contract

- [x] 1.1 Define the versioned SSH catalog format and compatibility boundaries.

## 2. Server and client

- [x] 2.1 Implement and verify the read-only Home Lab exporter.
- [x] 2.2 Implement and verify native Cartuchos import, stable refresh and offline behavior.

## 3. Integration

- [x] 3.1 Validate OpenSpec and exercise the exporter and importer together.
- [x] 3.2 Verify existing games, artwork, and normal launch configuration are preserved.

## Follow-up changes

1. Move launch selection and process tracking into server-owned sessions with unique IDs.
2. Expose structured Hestia lifecycle events and replace log-text interpretation.
3. Verify cleanup and idle power policy after the last graphical session.
