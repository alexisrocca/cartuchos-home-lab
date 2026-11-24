# Cartuchos Home Lab

Fork of Cartridges 2.13.1 with native Hestia integration. Linux distributions
can install the self-contained app bundle from GitHub Releases using
`flatpak install --user Cartuchos-Home-Lab-x86_64.flatpak`. Install the GNOME
49 runtime from Flathub if prompted. Hestia runs on the host and should already
be paired with the streaming server.

Open **Preferences → Home Lab** and enter the server address and the local
Hestia executable. That page also controls resolution, frame rate, bitrate,
codec, fullscreen, the optional wake command, and the optional SSH settings.
F11 toggles fullscreen.

Edit a game and enter its Hestia application name as advertised by the server.
Ordinary local games continue to use the executable field. Shared Hermes
profiles can specify a game selection in `provider:identifier` form, the SSH
destination, and an optional readiness executable. The wake command accepts
an executable plus arguments, with shell-style quoting and no shell expansion.
For the existing Home Lab, the Tuya extension can supply that optional wake
command and the Gamescope setup can supply a readiness executable. Neither is
required for regular Hestia applications on an already running server.

On first launch the fork copies the prototype or original Flatpak library if
available and converts supported legacy launcher entries to remote games.
Review the per-game relative mouse setting if a game needs it.

To build locally, use the GNOME 49 SDK and
`flatpak-builder --user --repo=repo build-home-lab build-aux/flatpak/io.github.alexisrocca.CartuchosHomeLab.json`.
Create the downloadable bundle with
`flatpak build-bundle repo Cartuchos-Home-Lab-x86_64.flatpak io.github.alexisrocca.CartuchosHomeLab master`.
