"""Import the original or prototype Cartridges library on first run."""
import argparse
import json
import logging
import shlex
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory

from gi.repository import Gio

from cartridges import shared


def remote_fields(command):
    argv = shlex.split(command or "")
    if len(argv) == 2 and argv[0] == "gtk-launch":
        desktop = argv[1].removesuffix(".desktop")
        if "/" in desktop:
            return {}
        path = shared.host_data_dir / "applications" / (desktop + ".desktop")
        entry = Gio.DesktopAppInfo.new_from_filename(str(path)) if path.is_file() else None
        if entry:
            argv = shlex.split(entry.get_string("Exec") or "")
    if argv[:2] == ["env", "HESTIA_FORCE_NORMAL=1"]:
        argv = argv[2:]
    if not argv or Path(argv[0]).name != "home-lab-stream":
        return {}
    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument("--low-latency", action="store_true")
    parser.add_argument("--launcher-status", default="")
    parser.add_argument("--game", default="")
    parser.add_argument("--bitrate")
    parser.add_argument("app_id", nargs="?")
    parser.add_argument("title", nargs="?")
    parser.add_argument("app", nargs="?")
    opts, extra = parser.parse_known_args(argv[1:])
    if extra or not opts.app:
        return {}
    return {"remote_app": opts.app, "remote_selection": opts.game,
            "remote_status": opts.launcher_status}


def migrate_library():
    if shared.PROFILE != "home-lab" or shared.games_dir.exists():
        return
    original = Path.home() / ".var/app/page.kramo.Cartridges/data"
    for source in (original / "cartridges-home-lab", original / "cartridges"):
        if not (source / "games").is_dir():
            continue
        with TemporaryDirectory(dir=shared.data_dir) as temp:
            target = Path(temp) / "library"
            copytree(source, target)
            for file in (target / "games").glob("*.json"):
                try:
                    data = json.loads(file.read_text())
                    if isinstance(data.get("executable"), str) and not data.get("remote_app"):
                        data.update(remote_fields(data["executable"]))
                    file.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n")
                except (argparse.ArgumentError, ValueError, OSError, TypeError):
                    logging.warning("Could not migrate game %s", file.name)
            target.rename(shared.games_dir.parent)
        return
