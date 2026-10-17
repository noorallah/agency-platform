"""Tiny HTTP helper for the RCM GTA check (standalone; reads no secret from a doc)."""

from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.request
from typing import Any

BASE = "http://localhost:8000"
PASSWORD_FILE = pathlib.Path(r"D:\ws\agencyApp\unattended\loop_admin.txt")


class Api:
    """Talk JSON to the backend; ``call`` returns (status, parsed body)."""

    def __init__(self, token: str | None = None, firm: str | None = None) -> None:
        self.token, self.firm = token, firm

    def call(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        """Send one request."""
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self.firm:
            h["X-Firm-ID"] = self.firm
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                raw = r.read().decode()
                return r.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, {"raw": raw}

    def ok(self, method: str, path: str, body: Any = None) -> Any:
        """Return ``data`` or raise with the refusal."""
        s, b = self.call(method, path, body)
        if s >= 300:
            raise RuntimeError(f"{method} {path} -> {s}: {json.dumps(b)[:600]}")
        return b.get("data", b) if isinstance(b, dict) else b


def sign_in() -> Api:
    """Sign in once (no retry: repeated failures lock the account)."""
    lines = PASSWORD_FILE.read_text(encoding="utf-8-sig").splitlines()
    email = "loop-admin@example.com"
    pw = next(x.split("=", 1)[1].strip() for x in lines if x.lower().startswith("password="))
    a = Api()
    d = a.ok("POST", "/api/v1/auth/login", {"email": email, "password": pw})
    return Api(d["access_token"])
