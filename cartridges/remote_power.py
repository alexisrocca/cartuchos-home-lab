"""Tuya power-on provider with credentials stored in the desktop keyring."""
import hashlib
import hmac
import json
import re
from time import time_ns
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

import gi

gi.require_version("Secret", "1")
from gi.repository import Secret

SCHEMA = Secret.Schema.new(
    "io.github.alexisrocca.CartuchosHomeLab.Tuya",
    Secret.SchemaFlags.NONE,
    {"endpoint": Secret.SchemaAttributeType.STRING, "device": Secret.SchemaAttributeType.STRING},
)


def save_credentials(endpoint, device, client_id, secret):
    if not Secret.password_store_sync(
        SCHEMA, {"endpoint": endpoint, "device": device}, Secret.COLLECTION_DEFAULT,
        "Cartuchos Home Lab — Tuya", json.dumps([client_id, secret]), None,
    ):
        raise RuntimeError(_("Could not save the Tuya credentials."))


class TuyaPower:
    def __init__(self, endpoint, device, switch):
        url = urlsplit(endpoint)
        if (url.scheme != "https" or not url.hostname or not url.hostname.endswith((".tuya.com", ".tuyaus.com", ".tuyaeu.com", ".tuyacn.com", ".tuyain.com"))
                or url.username or url.password or url.path not in ("", "/")
                or url.query or url.fragment):
            raise RuntimeError(_("Enter a Tuya HTTPS API endpoint."))
        if not all(re.fullmatch(r"[a-zA-Z0-9_-]+", value) for value in (device, switch)):
            raise RuntimeError(_("Enter a Tuya device ID and switch code."))
        self.endpoint = endpoint.rstrip("/")
        self.device = f"/v1.0/iot-03/devices/{device}"
        self.switch = switch
        credentials = Secret.password_lookup_sync(
            SCHEMA, {"endpoint": endpoint, "device": device}, None,
        )
        if not credentials:
            raise RuntimeError(_("Save your Tuya credentials in Home Lab preferences."))
        self.client_id, self.secret = json.loads(credentials)
        self.token = ""

    def request(self, method, path, payload=None):
        body = b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode()
        now = str(time_ns() // 1_000_000)
        nonce = uuid4().hex
        digest = hashlib.sha256(body).hexdigest()
        message = f"{self.client_id}{self.token}{now}{nonce}{method}\n{digest}\n\n{path}"
        signature = hmac.new(self.secret.encode(), message.encode(), hashlib.sha256)
        headers = {"client_id": self.client_id, "t": now, "nonce": nonce,
                   "sign_method": "HMAC-SHA256", "sign": signature.hexdigest().upper()}
        if self.token:
            headers["access_token"] = self.token
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.endpoint + path, body if payload is not None else None,
                          headers, method=method)
        try:
            with urlopen(request, timeout=8) as response:
                result = json.load(response)
        except HTTPError as error:
            raise RuntimeError(_("Tuya returned HTTP {}.").format(error.code)) from error
        if not result.get("success"):
            raise RuntimeError(_("Tuya rejected the request (code {}).").format(result.get("code", "?")))
        return result["result"]

    def wake(self, emit, cancelled):
        emit("power-check")
        self.token = self.request("GET", "/v1.0/token?grant_type=1")["access_token"]
        for entry in self.request("GET", self.device + "/status"):
            if entry.get("code") != self.switch or not isinstance(entry.get("value"), bool):
                continue
            if not entry["value"] and not cancelled.is_set():
                emit("power-on")
                payload = {"commands": [{"code": self.switch, "value": True}]}
                if self.request("POST", self.device + "/commands", payload) is not True:
                    raise RuntimeError(_("Tuya did not confirm the power-on command."))
            return
        raise RuntimeError(_("Tuya did not report the configured switch."))
