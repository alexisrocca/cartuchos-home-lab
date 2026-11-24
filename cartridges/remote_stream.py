"""Hestia transport for remote games. All child processes take argv arrays."""
import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
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
        )


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

    def run(self, emit):
        config = self.settings
        if not config.host or not config.client:
            raise RuntimeError("Configure the Hestia host and client in Preferences → Home Lab.")
        if not re.fullmatch(r"[\w.:-]+", config.host):
            raise RuntimeError("Enter a hostname or IP address without a URL or port.")
        if config.status_channel and not re.fullmatch(r"[a-z][a-z0-9-]*", config.status_channel):
            raise RuntimeError("Invalid launcher status channel.")
        self.wait_for_host(emit)
        if self.cancelled.is_set():
            return
        if config.selection:
            if not config.ssh_host or config.ssh_host.startswith("-"):
                raise RuntimeError("Set the SSH destination in Home Lab preferences.")
            if not re.fullmatch(r"[a-z][a-z0-9-]*:[a-zA-Z0-9._-]+", config.selection):
                raise RuntimeError("Game selection must use provider:identifier.")
            emit("select")
            self.execute([
                "ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=4",
                "-o", "StrictHostKeyChecking=yes", config.ssh_host,
                "bash -c " + shlex.quote(SELECTION_COMMAND),
            ], input_text=config.selection.replace(":", " ", 1) + "\n")
        if not self.cancelled.is_set():
            self.stream(emit)

    def stream(self, emit):
        config = self.settings
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
            if config.selection.startswith("steam:"):
                environment["HESTIA_GAME_TARGET"] = config.selection.partition(":")[2]
            if config.status_channel:
                environment["HESTIA_LAUNCHER_STATUS"] = config.status_channel
            args = [
                os.path.expanduser(config.client), f"--{config.resolution}",
                "--fps", str(config.fps), "--bitrate", str(config.bitrate),
                "--video-codec", config.codec, "--no-hdr", "--display-mode",
                "borderless", "--quit-after",
            ]
            if config.relative_mouse:
                args.append("--no-absolute-mouse")
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
