"""Hestia transport for remote games. All child processes take argv arrays."""
import hashlib
import json
import logging
import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event
from time import monotonic
from urllib.parse import urlunsplit
from urllib.request import urlopen

from gi.repository import GLib

from cartridges import shared
from cartridges.remote_power import TuyaPower

STAGE_MESSAGES = {
    "Preparing session": "prepare",
    "Starting RTSP handshake": "connect",
    "Waiting for game window before showing stream": "wait-game",
    "Steam is processing the game shaders": "shaders",
    "Launcher sign-in required": "sign-in",
}
# Only explicit unsupported or unavailable replies allow a legacy fallback. Transport errors are
# ambiguous because a reservation may already have been created remotely.
SESSION_FALLBACK = {
    3: "hermes-game-session unsupported",
    127: "hermes-game-session unavailable",
}
SESSION_COMMAND = (
    'if [ -x "$HOME/.local/bin/hermes-game-session" ]; then '
    'exec "$HOME/.local/bin/hermes-game-session"; '
    f"else printf '%s\\n' '{SESSION_FALLBACK[127]}'; exit 127; fi"
)
SELECTION = re.compile(r"[a-z][a-z0-9-]*:[a-zA-Z0-9._-]+")
STATUS_CHANNEL = re.compile(r"[a-z][a-z0-9-]*")
SESSION_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")
CATALOG_GAME_ID = re.compile(r"[a-zA-Z0-9._:-]{1,128}")
SELECTION_COMMAND = (
    'set -eu; target="$HOME/.local/share/hermes-game-selection"; '
    'temp=$(mktemp "$target.XXXXXX"); trap \'rm -f "$temp"\' EXIT; '
    'cat > "$temp"; chmod 644 "$temp"; mv -T "$temp" "$target"'
)


@dataclass(frozen=True)
class StreamSettings:
    host: str
    client: str
    wake_command: str
    ssh_host: str
    readiness_check: str
    tuya_enabled: bool
    tuya_endpoint: str
    tuya_device: str
    tuya_switch: str
    resolution: str
    fps: int
    bitrate: int
    codec: str
    app: str
    title: str
    app_id: str
    selection: str
    status_channel: str
    relative_mouse: bool
    catalog_id: str = ""
    catalog_game_id: str = ""

    @classmethod
    def from_game(cls, game):
        string = shared.schema.get_string
        integer = shared.schema.get_int
        return cls(
            string("remote-host").strip(), string("remote-client").strip(),
            string("remote-wake-command").strip(), string("remote-ssh-host").strip(),
            string("remote-readiness-check").strip(), shared.schema.get_boolean("remote-tuya-enabled"),
            string("remote-tuya-endpoint").strip(), string("remote-tuya-device").strip(),
            string("remote-tuya-switch").strip(), string("remote-resolution"),
            integer("remote-fps"), integer("remote-bitrate"), string("remote-codec"),
            game.remote_app, game.name,
            "io.github.alexisrocca.CartuchosHomeLab.Game",
            game.remote_selection, game.remote_status, game.remote_relative_mouse,
            getattr(game, "remote_catalog_id", ""), getattr(game, "remote_catalog_game_id", ""),
        )


def catalog_key(destination, game_id):
    return hashlib.sha256(f"{destination}\0{game_id}".encode()).hexdigest()


def host_command(argv, environment=None):
    environment = environment or {}
    if Path("/.flatpak-info").is_file():
        return [
            "flatpak-spawn", "--host", "--watch-bus",
            *(f"--env={key}={value}" for key, value in environment.items()), *argv,
        ], None
    return argv, dict(os.environ, **environment)


class RemoteStream:
    def __init__(self, settings):
        self.settings = settings
        self.cancelled = Event()

    def cancel(self):
        self.cancelled.set()

    def ready(self):
        host = self.settings.host
        authority = f"[{host}]" if ":" in host else host
        url = urlunsplit(("http", f"{authority}:47989", "/serverinfo", "", ""))
        try:
            with urlopen(url, timeout=2) as response:
                return b"<currentgame>" in response.read(16384)
        except OSError:
            return False

    def execute(self, argv, *, input_text=None, timeout=10):
        command, environment = host_command(argv)
        try:
            return subprocess.run(command, env=environment, input=input_text,
                                  capture_output=True, text=True, timeout=timeout, check=True)
        except subprocess.CalledProcessError as error:
            raise RuntimeError(error.stderr.strip() or f"Command failed: {argv[0]}") from error

    def wait_for_host(self, emit):
        if self.ready() or self.cancelled.is_set():
            return
        config = self.settings
        if config.tuya_enabled:
            try:
                TuyaPower(config.tuya_endpoint, config.tuya_device, config.tuya_switch).wake(
                    emit, self.cancelled
                )
            except (GLib.Error, KeyError, ValueError) as error:
                raise RuntimeError(_("Could not read Tuya power status.")) from error
        elif config.wake_command:
            try:
                command = shlex.split(config.wake_command)
            except ValueError as error:
                raise RuntimeError(_("The wake command has invalid quoting.")) from error
            if not command:
                raise RuntimeError(_("The wake command is empty."))
            command[0] = os.path.expanduser(command[0])
            emit("power-on")
            self.execute(command, timeout=30)
        else:
            raise RuntimeError(_("Hestia host is offline. Check the server or configure wake-up."))
        emit("boot")
        deadline = monotonic() + 150
        while not self.cancelled.wait(1):
            if self.ready():
                return
            if monotonic() >= deadline:
                raise RuntimeError("The Hestia host did not become available in time.")

    def ssh_command(self, command):
        return [
            "ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=4",
            "-o", "StrictHostKeyChecking=yes", "--", self.settings.ssh_host,
            "bash -c " + shlex.quote(command),
        ]

    def session_request(self, action, **fields):
        command, environment = host_command(self.ssh_command(SESSION_COMMAND))
        request = json.dumps({"version": 1, "action": action, **fields}) + "\n"
        try:
            result = subprocess.run(command, env=environment, input=request, capture_output=True,
                                    encoding="utf-8", errors="replace", timeout=10)
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError(_("Could not contact Hermes to manage the game session.")) from error
        if (action == "reserve" and result.stdout.strip()
                == SESSION_FALLBACK.get(result.returncode)):
            return None
        if result.returncode:
            raise RuntimeError(result.stderr.strip()[:512]
                               or _("Hermes rejected the game session request."))
        try:
            response = json.loads(result.stdout)
        except (ValueError, RecursionError) as error:
            raise RuntimeError(_("Hermes returned an invalid game session response.")) from error
        if (not isinstance(response, dict) or type(response.get("version")) is not int
                or response["version"] != 1):
            raise RuntimeError(_("Hermes returned an invalid game session response."))
        return response

    def session_settings(self, response):
        app = response.get("app")
        selection = response.get("selection", "")
        status = response.get("status_channel", "")
        mouse = response.get("relative_mouse", self.settings.relative_mouse)
        if (not isinstance(app, str) or not app.strip() or len(app) > 256 or not app.isprintable()
                or not isinstance(selection, str) or (selection and not SELECTION.fullmatch(selection))
                or not isinstance(status, str) or (status and not STATUS_CHANNEL.fullmatch(status))
                or type(mouse) is not bool):
            raise RuntimeError(_("Hermes returned invalid game launch settings."))
        return replace(self.settings, app=app, selection=selection, status_channel=status,
                       relative_mouse=mouse)

    def release_session(self, session_id):
        try:
            response = self.session_request("release", session_id=session_id)
            if response.get("released") is not True:
                raise RuntimeError(_("Hermes did not acknowledge releasing the game session."))
        except RuntimeError as error:
            logging.warning("Could not release the Hermes game session: %s", error)

    def run(self, emit):
        config = self.settings
        catalog_game_id = config.catalog_game_id
        # Older imports stored a destination-scoped key but kept the Steam ID
        # in the selection field. The matching key proves it is that entry.
        if not catalog_game_id and config.catalog_id and config.selection.startswith("steam:"):
            catalog_game_id = config.selection
        if not config.host or not config.client:
            raise RuntimeError("Configure the Hestia host and client in Preferences → Home Lab.")
        if not re.fullmatch(r"[\w.:-]+", config.host):
            raise RuntimeError("Enter a hostname or IP address without a URL or port.")
        if config.status_channel and not STATUS_CHANNEL.fullmatch(config.status_channel):
            raise RuntimeError("Invalid launcher status channel.")
        if (catalog_game_id or config.selection) and not re.fullmatch(
            r"[a-zA-Z0-9_][a-zA-Z0-9_.@:-]{0,253}", config.ssh_host
        ):
            raise RuntimeError("Set the SSH destination in Home Lab preferences.")
        if catalog_game_id and (
            not CATALOG_GAME_ID.fullmatch(catalog_game_id)
            or config.catalog_id != catalog_key(config.ssh_host, catalog_game_id)
        ):
            raise RuntimeError(_("Import the game again from the configured Home Lab."))
        self.wait_for_host(emit)
        if self.cancelled.is_set():
            return

        if catalog_game_id:
            emit("select")
            response = self.session_request("reserve", catalog_id=catalog_game_id)
            if response is not None:
                session_id = response.get("session_id")
                if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id):
                    raise RuntimeError(_("Hermes returned an invalid game session ID."))
                try:
                    if not self.cancelled.is_set():
                        self.stream(emit, self.session_settings(response))
                finally:
                    self.release_session(session_id)
                return

        if config.selection and not self.cancelled.is_set():
            if not SELECTION.fullmatch(config.selection):
                raise RuntimeError("Game selection must use provider:identifier.")
            if not catalog_game_id:
                emit("select")
            self.execute(self.ssh_command(SELECTION_COMMAND),
                         input_text=config.selection.replace(":", " ", 1) + "\n")
        if not self.cancelled.is_set():
            self.stream(emit, config)

    def stream(self, emit, config):
        runtime = shared.data_dir / "hestia-sessions"
        runtime.mkdir(mode=0o700, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime) as temp:
            marker = Path(temp) / "first-frame"
            environment = {
                "HESTIA_DIRECT_STREAM": "1", "HESTIA_FORCE_NORMAL": "1",
                "HESTIA_APP_ID": config.app_id, "HESTIA_WINDOW_TITLE": config.title,
                "HESTIA_LOADING_MARKER": str(marker),
            }
            if config.ssh_host:
                environment["HESTIA_SSH_HOST"] = config.ssh_host
            if config.readiness_check and (config.selection or config.status_channel):
                environment["HESTIA_GAME_READY_CHECK"] = os.path.expanduser(config.readiness_check)
            is_steam = config.selection.startswith("steam:")
            if is_steam:
                environment["HESTIA_GAME_TARGET"] = config.selection.partition(":")[2]
            if config.status_channel:
                environment["HESTIA_LAUNCHER_STATUS"] = config.status_channel
            args = [
                os.path.expanduser(config.client), f"--{config.resolution}",
                "--fps", str(config.fps), "--bitrate", str(config.bitrate),
                "--video-codec", config.codec, "--no-hdr", "--display-mode",
                "windowed" if is_steam else "borderless", "--quit-after",
            ]
            if config.relative_mouse:
                args.append("--no-absolute-mouse")
            elif is_steam:
                args.append("--absolute-mouse")
            args.extend(["stream", config.host, config.app])
            command, env = host_command(args, environment)
            emit("prepare")
            self.monitor(command, env, marker, emit)

    def monitor(self, command, environment, marker, emit):
        log_path = marker.with_name("hestia.log")
        with log_path.open("w") as writer, log_path.open(errors="replace") as reader:
            with subprocess.Popen(command, env=environment, stdout=writer, stderr=writer) as child:
                deadline = monotonic() + 180
                last_stage = None
                last_line = ""
                try:
                    while not self.cancelled.wait(0.1):
                        for line in reader:
                            last_line = line.strip() or last_line
                            for message, stage in STAGE_MESSAGES.items():
                                if message in line and stage != last_stage:
                                    emit(stage)
                                    last_stage = stage
                        if marker.is_file():
                            emit("video")
                            child.wait()
                            return
                        if child.poll() is not None or monotonic() >= deadline:
                            raise RuntimeError(last_line or "Hestia did not deliver a video frame.")
                finally:
                    if child.poll() is None:
                        child.terminate()
                        try:
                            child.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            child.kill()
                            child.wait()
