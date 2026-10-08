"""Shared helpers for the kept API checks under docs/qa/checks.

Standard library only, so any Python runs them. Each check is one script that
exits non-zero with one line saying expected against got::

    from common import Check, state, client

    c = Check("tc_mast_017")
    admin = client("admin")                 # an account from the module's state
    status, body = admin.post("/api/v1/products/goods-types", {...})
    c.eq(status, 201, "a firm's own goods type is saved")
    c.done()

The module's state file (accounts, firm ids, anything the set-up made) is
``docs/qa/checks/.state/<module>.json``; it is not committed. ``setup.py`` in
the module's folder writes it, and a check reads it and makes its own records
under a fresh suffix, so every check can run alone and run twice.
"""

from __future__ import annotations

import http.client
import json
import os
import pathlib
import secrets
import string
import sys
import urllib.parse
import uuid
from typing import Any

BASE = os.environ.get("QA_BASE", "http://127.0.0.1:8000")
CHECKS = pathlib.Path(__file__).resolve().parent
PASSWORD = "Fixture@2026pw"


def fetch(
    method: str, path: str, data: bytes | None, headers: dict[str, str]
) -> tuple[int, bytes]:
    """Send one request on a connection the server may keep; return (status, body).

    Not ``urllib``: it asks for ``Connection: close`` on every request, and
    on the development PC the server cuts off any answer past about 320 KB
    sent to such a client, 19 seconds in (D-PERF-3). The desktop keeps its
    connections alive, and so does this.
    """
    base = urllib.parse.urlsplit(BASE)
    connect = (
        http.client.HTTPSConnection
        if base.scheme == "https"
        else http.client.HTTPConnection
    )
    connection = connect(base.hostname or "127.0.0.1", base.port, timeout=300)
    try:
        connection.request(method, f"{base.path}{path}", body=data, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def module_name() -> str:
    """Return the module a running check belongs to: its folder's name."""
    return pathlib.Path(sys.argv[0]).resolve().parent.name


def state_path(module: str | None = None) -> pathlib.Path:
    """Return where a module's set-up state is kept."""
    return CHECKS / ".state" / f"{module or module_name()}.json"


def state(module: str | None = None) -> dict[str, Any]:
    """Read the module's set-up state, or stop saying how to make it."""
    path = state_path(module)
    if not path.exists():
        raise SystemExit(f"SETUP MISSING: run setup.py of the module first ({path})")
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(values: dict[str, Any], module: str | None = None) -> None:
    """Merge values into the module's set-up state."""
    path = state_path(module)
    path.parent.mkdir(parents=True, exist_ok=True)
    held = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    held.update(values)
    path.write_text(json.dumps(held, indent=2), encoding="utf-8")


def suffix(length: int = 5) -> str:
    """Return a short upper-case tag no earlier run has used."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class Api:
    """Talk to the running backend as one user, optionally inside one firm."""

    def __init__(self, token: str | None = None, firm_id: str | None = None) -> None:
        self.token = token
        self.firm_id = firm_id

    def _send(
        self, method: str, path: str, data: bytes | None, content_type: str | None
    ) -> tuple[int, Any]:
        headers: dict[str, str] = {}
        if content_type:
            headers["Content-Type"] = content_type
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.firm_id:
            headers["X-Firm-ID"] = self.firm_id
        # A read that loses its connection is asked again; a write never is.
        tries = 3 if method == "GET" else 1
        for attempt in range(tries):
            try:
                status, raw = fetch(method, path, data, headers)
                break
            except ConnectionResetError:
                if attempt == tries - 1:
                    raise
        try:
            return status, json.loads(raw.decode("utf-8")) if raw else None
        except ValueError:
            return status, raw

    def call(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        """Send JSON; return (status, whole decoded answer)."""
        data = None if body is None else json.dumps(body).encode("utf-8")
        return self._send(method, path, data, "application/json")

    def get(self, path: str) -> tuple[int, Any]:
        """GET a path."""
        return self.call("GET", path)

    def post(self, path: str, body: Any = None) -> tuple[int, Any]:
        """POST JSON."""
        return self.call("POST", path, body if body is not None else {})

    def put(self, path: str, body: Any = None) -> tuple[int, Any]:
        """PUT JSON."""
        return self.call("PUT", path, body if body is not None else {})

    def delete(self, path: str) -> tuple[int, Any]:
        """DELETE a path."""
        return self.call("DELETE", path)

    def upload(
        self,
        path: str,
        filename: str,
        content: bytes,
        fields: dict[str, str] | None = None,
        file_field: str = "file",
        method: str = "POST",
    ) -> tuple[int, Any]:
        """Send one file as multipart form data, with optional form fields."""
        boundary = uuid.uuid4().hex
        parts: list[bytes] = []
        for name, value in (fields or {}).items():
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
                f"\r\n\r\n{value}\r\n".encode()
            )
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
            f'filename="{filename}"\r\nContent-Type: application/octet-stream'
            "\r\n\r\n".encode()
            + content
            + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        return self._send(
            method, path, b"".join(parts), f"multipart/form-data; boundary={boundary}"
        )

    def raw(self, path: str) -> tuple[int, bytes]:
        """GET a path and return the bytes untouched (a template download)."""
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.firm_id:
            headers["X-Firm-ID"] = self.firm_id
        return fetch("GET", path, None, headers)

    def inside(self, firm_id: str | None) -> Api:
        """Return the same user acting inside another firm (or none)."""
        return Api(self.token, firm_id)


def sign_in(email: str, password: str = PASSWORD, firm_id: str | None = None) -> Api:
    """Sign in once and return a client; a refusal stops the check.

    Never retried: repeated failures lock the account.
    """
    status, body = Api().post(
        "/api/v1/auth/login", {"email": email, "password": password}
    )
    if status != 200:
        raise SystemExit(f"SIGN-IN REFUSED for {email}: {status} {message(body)}")
    return Api(str(body["data"]["access_token"]), firm_id)


def client(account: str, module: str | None = None) -> Api:
    """Sign in as a named account of the module's state.

    The state holds ``accounts: {name: {"email": ..., "firm_id": ...}}``.
    """
    held = state(module)["accounts"][account]
    return sign_in(held["email"], held.get("password", PASSWORD), held.get("firm_id"))


def data(body: Any) -> Any:
    """Return the ``data`` of an answer, or the answer itself."""
    return body.get("data", body) if isinstance(body, dict) else body


def message(body: Any) -> str:
    """Return what the server said in a refusal, details included."""
    if not isinstance(body, dict):
        return str(body)[:300]
    error = body.get("error") or {}
    text = str(error.get("message") or body.get("message") or body.get("detail") or "")
    details = error.get("details")
    return f"{text} {json.dumps(details)[:400]}" if details else text


class Check:
    """Collect one check's comparisons and exit non-zero if any failed."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.failures: list[str] = []
        self.passed = 0

    def eq(self, got: Any, expected: Any, what: str) -> bool:
        """Compare two values."""
        if got == expected:
            self.passed += 1
            return True
        self.failures.append(f"{what}: expected {expected!r}, got {got!r}")
        return False

    def ok(self, condition: Any, what: str, got: Any = None) -> bool:
        """Assert a condition, saying what was seen when it does not hold."""
        if condition:
            self.passed += 1
            return True
        tail = "" if got is None else f" (got {str(got)[:300]!r})"
        self.failures.append(f"{what}{tail}")
        return False

    def refused(
        self, answer: tuple[int, Any], status: int, says: str, what: str
    ) -> bool:
        """Assert a refusal: its status and a phrase of its message."""
        got_status, body = answer
        text = message(body)
        if got_status == status and says.lower() in text.lower():
            self.passed += 1
            return True
        self.failures.append(
            f"{what}: expected {status} saying {says!r}, got {got_status} {text[:300]!r}"
        )
        return False

    def done(self) -> None:
        """Print the outcome and exit: 0 clean, 1 with one line per failure."""
        if self.failures:
            for failure in self.failures:
                print(f"FAIL {self.name}: {failure}")
            raise SystemExit(1)
        print(f"ok {self.name} ({self.passed} checks)")
        raise SystemExit(0)


def all_rows(api: "Api", path: str, size: int = 25) -> list[Any]:
    """Read every page of a list, a small page at a time.

    This development PC resets some answers larger than about 64 KB
    (D-PERF-3), so a helper never asks for a hundred rows in one answer.
    ``path`` carries its own filters and no ``page`` or ``page_size``.
    """
    rows: list[Any] = []
    joiner = "&" if "?" in path else "?"
    page = 1
    while True:
        status, body = api.get(f"{path}{joiner}page={page}&page_size={size}")
        got = data(body) if status == 200 else []
        if not isinstance(got, list) or not got:
            return rows
        rows.extend(got)
        pages = (body.get("pagination") or {}).get("total_pages", 1)
        if page >= int(pages or 1):
            return rows
        page += 1
