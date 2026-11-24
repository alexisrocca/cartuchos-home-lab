## Why

Cartuchos requires manual game names and launcher arguments. Remote discovery should reuse the established Home Lab connection and keep the library available while the server is off.

## What Changes

- Add a versioned, read-only catalog over the configured SSH destination.
- Import remote launch metadata and available artwork into the Cartuchos library.
- Refresh entries using stable remote identifiers and keep the last successful library offline.
- Plan session IDs, structured Hestia events and idle cleanup as follow-up OpenSpec changes.

## Capabilities

### New Capabilities

- `remote-game-catalog`: Discover and import games available on the configured Hestia server.

### Modified Capabilities

None.

## Impact

Cartuchos library and import UI, Home Lab catalog exporter, and the existing SSH trust configuration. Streaming, privilege settings and power controls retain their existing entry points.
