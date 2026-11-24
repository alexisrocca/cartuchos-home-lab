"""Read the Home Lab catalog via SSH and merge it into the local library."""

import base64
import json
import logging
import re
import select
import subprocess
from dataclasses import dataclass
from io import BytesIO
from time import monotonic, time

from gi.repository import Gio, GLib
from PIL import Image

from cartridges import shared
from cartridges.game import Game
from cartridges.remote_stream import catalog_key, host_command

SOURCE = "homelab"
MAX_CATALOG_SIZE = 2 * 1024 * 1024
MAX_GAMES = 500
MAX_LOCAL_ART = 8 * 1024 * 1024
MAX_COVER_SIZE = 256 * 1024
COVER_PREFIX = re.compile(r"data:image/(jpeg|png|webp);base64,")
IDENTIFIER = re.compile(r"[a-zA-Z0-9._:-]{1,128}")
SELECTION = re.compile(r"[a-z][a-z0-9-]*:[a-zA-Z0-9._-]+")
STATUS = re.compile(r"[a-z][a-z0-9-]*")


@dataclass(frozen=True)
class CatalogGame:
    id: str
    name: str
    app: str
    selection: str | None = None
    status_channel: str | None = None
    relative_mouse: bool | None = None
    cover: bytes | None = None


def read_cover(value):
    if not isinstance(value, str) or len(value) > (MAX_COVER_SIZE + 2) // 3 * 4 + 32:
        return None
    prefix = COVER_PREFIX.match(value)
    if prefix is None:
        return None
    try:
        payload = base64.b64decode(value[prefix.end():], validate=True)
        if len(payload) > MAX_COVER_SIZE:
            return None
        with Image.open(BytesIO(payload), formats=("JPEG", "PNG", "WEBP")) as image:
            if image.width * image.height > 4_000_000:
                return None
            image.thumbnail((600, 900))
            with BytesIO() as output:
                image.convert("RGB").save(output, format="TIFF", compression="tiff_adobe_deflate")
                return output.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def parse_catalog(payload):
    if len(payload) > MAX_CATALOG_SIZE:
        raise ValueError(_("The Home Lab catalog is too large."))
    try:
        catalog = json.loads(payload)
    except (ValueError, RecursionError) as error:
        raise ValueError(_("The Home Lab returned an invalid game catalog.")) from error

    if (not isinstance(catalog, dict) or type(catalog.get("version")) is not int
            or catalog["version"] != 1 or not isinstance(catalog.get("games"), list)):
        raise ValueError(_("The Home Lab returned an unsupported game catalog."))

    if len(catalog["games"]) > MAX_GAMES:
        raise ValueError(_("The Home Lab catalog is too large."))

    seen = set()
    items = []
    cover_budget = MAX_LOCAL_ART
    for entry in catalog["games"]:
        if not isinstance(entry, dict):
            raise ValueError(_("The Home Lab catalog contains an invalid game."))
        identifier, name, app = (entry.get(key) for key in ("id", "name", "app"))
        if (not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier)
                or identifier in seen
                or not all(isinstance(value, str) and 0 < len(value.strip()) <= 256
                           and value.isprintable() for value in (name, app))):
            raise ValueError(_("The Home Lab catalog contains an invalid game."))

        selection = entry.get("selection")
        status = entry.get("status_channel")
        mouse = entry.get("relative_mouse")
        for value, pattern in ((selection, SELECTION), (status, STATUS)):
            if value is not None and (not isinstance(value, str)
                                      or len(value) > 128
                                      or (value and not pattern.fullmatch(value))):
                raise ValueError(_("The Home Lab catalog contains invalid launch settings."))
        if mouse is not None and type(mouse) is not bool:
            raise ValueError(_("The Home Lab catalog contains invalid launch settings."))

        cover = read_cover(entry.get("cover")) if cover_budget else None
        if cover and len(cover) <= cover_budget:
            cover_budget -= len(cover)
        else:
            cover = None
        seen.add(identifier)
        items.append(CatalogGame(identifier, name.strip(), app.strip(), selection, status,
                                 mouse, cover))
    return items


def fetch_catalog(destination):
    # The remote command is constant. Catalog data never participates in the SSH command.
    command, env = host_command([
        "ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=4",
        "-o", "StrictHostKeyChecking=yes", "--", destination,
        '"$HOME/.local/bin/hermes-game-catalog"',
    ])
    deadline = monotonic() + 20
    payload = bytearray()
    try:
        with subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
            try:
                while select.select([process.stdout], [], [], max(0, deadline - monotonic()))[0]:
                    chunk = process.stdout.read1(MAX_CATALOG_SIZE + 1 - len(payload))
                    if not chunk:
                        if process.wait(timeout=max(0, deadline - monotonic())):
                            raise RuntimeError(_("Could not retrieve the Home Lab catalog over SSH."))
                        return parse_catalog(payload)
                    payload.extend(chunk)
                    if len(payload) > MAX_CATALOG_SIZE:
                        raise ValueError(_("The Home Lab catalog is too large."))
                    if monotonic() >= deadline:
                        break
                raise RuntimeError(_("Could not retrieve the Home Lab catalog over SSH."))
            finally:
                if process.poll() is None:
                    process.kill()
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(_("Could not retrieve the Home Lab catalog over SSH.")) from error


def merge_catalog(destination, items):
    """Apply a validated snapshot without deleting absent entries or replacing local art."""
    count = 0
    library = list(shared.store)
    for item in items:
        catalog_id = catalog_key(destination, item.id)
        game = next((existing for existing in library
                     if existing.remote_catalog_id == catalog_id and not existing.removed), None)
        if game is None:
            matches = [existing for existing in library
                       if not existing.remote_catalog_id and not existing.removed
                       and existing.remote_app == item.app
                       and existing.remote_selection == (item.selection or "")]
            if len(matches) == 1:
                game = matches[0]

        is_new = game is None
        details = {
            "remote_catalog_id": catalog_id,
            "remote_catalog_game_id": item.id,
            "remote_app": item.app,
            "remote_selection": item.selection,
            "remote_status": item.status_channel,
            "remote_relative_mouse": item.relative_mouse,
        }
        details = {key: value for key, value in details.items() if value is not None}
        if is_new:
            game = Game({
                "name": item.name, "game_id": f"{SOURCE}_{catalog_id}", "source": SOURCE,
                "executable": "", "added": int(time()), **details,
            })
            shared.store.add_game(game, {}, run_pipeline=False)
            library.append(game)
        changed = is_new or any(getattr(game, key) != value for key, value in details.items())
        if changed:
            game.update_values(details)
            game.save()
        if item.cover and game.get_cover_path() is None:
            try:
                shared.covers_dir.mkdir(parents=True, exist_ok=True)
                path = shared.covers_dir / f"{game.game_id}.tiff"
                Gio.File.new_for_path(str(path)).replace_contents(
                    item.cover, None, False, Gio.FileCreateFlags.NONE, None,
                )
                if game.game_cover:
                    game.game_cover.new_cover(path)
            except (OSError, GLib.Error) as error:
                logging.warning("Failed to store the Home Lab cover for %s: %s", game.game_id, error)
        if changed:
            game.update()
        count += 1
    return count
