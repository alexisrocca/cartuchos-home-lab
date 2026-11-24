## Why

Shared Hermes profiles currently read one mutable selection file. Overlapping starts and delayed cleanup can affect another launch.

## What Changes

- Reserve a catalog-backed launch through the existing SSH connection with an opaque server-issued ID.
- Make the shared launcher claim the reservation once and track the game within its Gamescope lifecycle.
- Release only the reservation belonging to the requesting client. Preserve the legacy path for older installations.
- Keep Hestia event transport and the idle power policy for subsequent changes.

## Capabilities

### New Capabilities

- `remote-game-session`: Own and release a shared remote game launch.

### Modified Capabilities

None.

## Impact

Cartuchos launcher, Hermes-side SSH helper and Gamescope wrapper. The same Hestia stream and existing SSH trust settings are used.
