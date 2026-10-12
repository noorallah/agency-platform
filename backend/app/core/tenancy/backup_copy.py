"""Keep a password-protected copy of each backup in a second folder.

A backup on the disk it protects does not survive that disk (backlog 112).
With ``AGENCY_BACKUP_SECOND_DIRECTORY`` set -- a folder a cloud client keeps in
step, or one on another drive -- every finished backup under the backup root
also lands there as **one file**, ``agency-backup-<kind>-<stamp>.agbk``, which
does not open without ``AGENCY_BACKUP_SECOND_PASSWORD``. The copies of the
newest ``AGENCY_BACKUP_SECOND_KEEP_DAYS`` days are kept (10 unless said) and
the older ones removed.

:func:`copy_backups_to_second_folder` copies **what is missing** rather than
"the backup just taken": the nightly task and ``Back up now`` both end by
calling it, so a pre-upgrade backup is picked up by the next run, and so is a
night when the other drive was unplugged. It only ever deletes files carrying
its own name and suffix; a second folder is usually somebody's cloud folder
and holds other things.

**Standard library only**, for the reason ``app/core/security/secret_box.py``
gives: the release is compiled and every dependency has to survive that. No
library in the standard set writes an encrypted zip, so the file is our own:

* the backup's folder as an uncompressed tar (the dumps are already
  compressed), never written to disk unencrypted -- it streams through the
  cipher into ``<name>.part`` and is renamed only once read back;
* two keys from the password by PBKDF2-HMAC-SHA256 over a random salt;
* the keystream for each 1 MiB chunk is ``SHAKE-256(stream key || nonce ||
  chunk number)``, so this is a stream cipher in counter mode;
* **encrypt-then-MAC**: ``HMAC-SHA256(tag key, header || ciphertext)`` closes
  the file and is checked, in constant time, before anything is decrypted. A
  wrong password and an altered file fail the same check.

``agency-server backup-open`` is the way back: it turns one ``.agbk`` into the
folder of dumps the restore steps in ``docs/INSTALL_GUIDE.md`` section 6 start
from.
"""

import hashlib
import hmac
import os
import secrets
import tarfile
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from app.core.config.settings import Settings
from app.core.tenancy.backup import (
    BackupError,
    BackupFolder,
    list_backups,
)

COPY_PREFIX = "agency-backup-"
COPY_SUFFIX = ".agbk"
PART_SUFFIX = ".part"
#: The shortest password a copy is written under.
MIN_PASSWORD_LENGTH = 8

_MAGIC = b"AGBK1\n"
_SALT_BYTES = 16
_NONCE_BYTES = 16
_TAG_BYTES = 32
_HEADER_BYTES = len(_MAGIC) + _SALT_BYTES + _NONCE_BYTES
_CHUNK = 1024 * 1024
_STAMP_LENGTH = len("20261013-020000")
#: PBKDF2 rounds. A module constant so a test can lower it.
KEY_ROUNDS = 600_000

# One pass over the second folder at a time, whoever asked.
_COPY_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class SecondCopy:
    """One protected copy found in the second folder."""

    name: str
    path: Path
    size_bytes: int
    day: str  # yyyyMMdd, from the stamp in the name


@dataclass(frozen=True, slots=True)
class SecondCopyResult:
    """One pass of :func:`copy_backups_to_second_folder`."""

    folder: Path
    written: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Say the pass in one sentence, for the log and the screen."""
        parts = [f"{len(self.written)} copied to {self.folder}"]
        if self.removed:
            parts.append(f"{len(self.removed)} old removed")
        if self.failed:
            parts.append(f"{len(self.failed)} FAILED ({'; '.join(self.failed)})")
        if self.unreadable:
            parts.append(
                f"{len(self.unreadable)} not readable by this account "
                f"({', '.join(self.unreadable)})"
            )
        return "Second copy: " + ", ".join(parts) + "."


def _keys(password: str, salt: bytes) -> tuple[bytes, bytes]:
    """Derive the stream key and the tag key from the password."""
    master = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, KEY_ROUNDS, dklen=64
    )
    return master[:32], master[32:]


def _mask(data: bytes, key: bytes, nonce: bytes, chunk_number: int) -> bytes:
    """XOR one chunk with its keystream; the same call encrypts and decrypts."""
    stream = hashlib.shake_256(key + nonce + chunk_number.to_bytes(8, "big")).digest(
        len(data)
    )
    masked = int.from_bytes(data, "big") ^ int.from_bytes(stream, "big")
    return masked.to_bytes(len(data), "big")


class _SealingWriter:
    """A write-only file that encrypts what it is given and tags the whole."""

    def __init__(self, raw: BinaryIO, password: str) -> None:
        """Write the header and hold the keys."""
        salt = secrets.token_bytes(_SALT_BYTES)
        self._nonce = secrets.token_bytes(_NONCE_BYTES)
        self._stream_key, tag_key = _keys(password, salt)
        self._raw = raw
        self._mac = hmac.new(tag_key, digestmod=hashlib.sha256)
        self._pending = bytearray()
        self._chunk_number = 0
        header = _MAGIC + salt + self._nonce
        self._mac.update(header)
        raw.write(header)

    def write(self, data: bytes) -> int:
        """Take plaintext; encrypt and write every whole chunk gathered."""
        self._pending += data
        while len(self._pending) >= _CHUNK:
            self._emit(bytes(self._pending[:_CHUNK]))
            del self._pending[:_CHUNK]
        return len(data)

    def _emit(self, chunk: bytes) -> None:
        """Encrypt one chunk, feed the tag and write it."""
        sealed = _mask(chunk, self._stream_key, self._nonce, self._chunk_number)
        self._chunk_number += 1
        self._mac.update(sealed)
        self._raw.write(sealed)

    def finish(self) -> None:
        """Write what is left and close the file with its tag."""
        if self._pending:
            self._emit(bytes(self._pending))
            self._pending.clear()
        self._raw.write(self._mac.digest())


class _OpeningReader:
    """A read-only file that decrypts a copy whose tag was already checked."""

    def __init__(
        self, raw: BinaryIO, *, stream_key: bytes, nonce: bytes, length: int
    ) -> None:
        """Hold the keys; ``length`` is the ciphertext still to read."""
        self._raw = raw
        self._stream_key = stream_key
        self._nonce = nonce
        self._left = length
        self._chunk_number = 0
        self._ready = bytearray()

    def read(self, size: int = -1) -> bytes:
        """Return up to ``size`` plaintext bytes; all of it when negative."""
        while (size < 0 or len(self._ready) < size) and self._left > 0:
            sealed = self._raw.read(min(_CHUNK, self._left))
            if not sealed:
                break
            self._left -= len(sealed)
            self._ready += _mask(
                sealed, self._stream_key, self._nonce, self._chunk_number
            )
            self._chunk_number += 1
        take = len(self._ready) if size < 0 else min(size, len(self._ready))
        data = bytes(self._ready[:take])
        del self._ready[:take]
        return data


def seal_folder(folder: Path, destination: Path, *, password: str) -> None:
    """Write ``folder`` as one protected file at ``destination``.

    Only the files directly inside the folder go in, under their own names:
    a backup is a flat folder of dumps, a manifest and a marker.
    """
    with destination.open("wb") as raw:
        writer = _SealingWriter(raw, password)
        # The writer is file-like enough for a streamed tar, which only writes.
        with tarfile.open(fileobj=writer, mode="w|") as archive:  # type: ignore[call-overload]
            for child in sorted(folder.iterdir()):
                if child.is_file():
                    archive.add(child, arcname=child.name, recursive=False)
        writer.finish()


def _checked(raw: BinaryIO, size: int, password: str) -> tuple[bytes, bytes]:
    """Check a copy's tag; return its stream key and nonce, or raise."""
    refusal = BackupError(
        "The copy does not open: the password is wrong, or the file has been "
        "altered or is not whole."
    )
    if size < _HEADER_BYTES + _TAG_BYTES:
        raise refusal
    header = raw.read(_HEADER_BYTES)
    if not header.startswith(_MAGIC):
        raise BackupError("This is not a protected backup copy written by this server.")
    salt = header[len(_MAGIC) : len(_MAGIC) + _SALT_BYTES]
    nonce = header[len(_MAGIC) + _SALT_BYTES :]
    stream_key, tag_key = _keys(password, salt)
    mac = hmac.new(tag_key, header, hashlib.sha256)
    left = size - _HEADER_BYTES - _TAG_BYTES
    while left > 0:
        sealed = raw.read(min(_CHUNK, left))
        if not sealed:
            raise refusal
        left -= len(sealed)
        mac.update(sealed)
    if not hmac.compare_digest(raw.read(_TAG_BYTES), mac.digest()):
        raise refusal
    return stream_key, nonce


def verify_copy(path: Path, *, password: str) -> None:
    """Read a copy back and check it against its tag. Raises :class:`BackupError`."""
    with path.open("rb") as raw:
        _checked(raw, path.stat().st_size, password)


def open_copy(path: Path, into: Path, *, password: str) -> list[str]:
    """Unpack a protected copy into ``into``; return the file names written.

    Nothing is written unless the whole file passes its check first, so a
    wrong password leaves ``into`` as it was.
    """
    if not path.is_file():
        raise BackupError(f"{path} is not a file.")
    size = path.stat().st_size
    with path.open("rb") as raw:
        stream_key, nonce = _checked(raw, size, password)
        raw.seek(_HEADER_BYTES)
        reader = _OpeningReader(
            raw,
            stream_key=stream_key,
            nonce=nonce,
            length=size - _HEADER_BYTES - _TAG_BYTES,
        )
        into.mkdir(parents=True, exist_ok=True)
        names: list[str] = []
        with tarfile.open(fileobj=reader, mode="r|") as archive:  # type: ignore[call-overload]
            for member in archive:
                # Flat by construction; anything else is not one of ours.
                if not member.isfile() or Path(member.name).name != member.name:
                    raise BackupError(
                        f"The copy holds an entry that is not a backup file: "
                        f"{member.name}"
                    )
                archive.extract(member, into, filter="data")
                names.append(member.name)
    return names


def copy_name(backup: BackupFolder) -> str:
    """Return the file name a backup's copy carries in the second folder."""
    if backup.kind == "pre-upgrade":
        return f"{COPY_PREFIX}{backup.name}{COPY_SUFFIX}"
    return f"{COPY_PREFIX}{backup.kind}-{backup.name}{COPY_SUFFIX}"


def _day_of(file_name: str) -> str | None:
    """Return the yyyyMMdd day in a copy's name, or None if it is not ours."""
    if not (file_name.startswith(COPY_PREFIX) and file_name.endswith(COPY_SUFFIX)):
        return None
    stamp = file_name[: -len(COPY_SUFFIX)][-_STAMP_LENGTH:]
    try:
        datetime.strptime(stamp, "%Y%m%d-%H%M%S")  # noqa: DTZ007 - a name, not a time
    except ValueError:
        return None
    return stamp[:8]


def second_folder(settings: Settings) -> Path | None:
    """Return the second folder, or None when no second copy is asked for."""
    return settings.backup_second_directory


def _password(settings: Settings) -> str:
    """Return the password copies are written under, or say what is missing."""
    secret = settings.backup_second_password
    value = "" if secret is None else secret.get_secret_value()
    if len(value) < MIN_PASSWORD_LENGTH:
        raise BackupError(
            "A second backup folder is set but no copy was written: "
            "AGENCY_BACKUP_SECOND_PASSWORD must be set, with at least "
            f"{MIN_PASSWORD_LENGTH} characters. A copy is never written "
            "without a password."
        )
    return value


def list_second_copies(folder: Path) -> list[SecondCopy]:
    """Return the protected copies in ``folder``, newest first.

    Raises:
        BackupError: If the folder cannot be read.

    """
    try:
        children = [child for child in folder.iterdir() if child.is_file()]
    except OSError as error:
        raise BackupError(
            f"The second backup folder {folder} cannot be read: "
            f"{error.strerror or error}"
        ) from error
    copies: list[SecondCopy] = []
    for child in children:
        day = _day_of(child.name)
        if day is not None:
            copies.append(
                SecondCopy(
                    name=child.name,
                    path=child,
                    size_bytes=child.stat().st_size,
                    day=day,
                )
            )
    return sorted(
        copies, key=lambda copy: copy.name[-_STAMP_LENGTH - 5 :], reverse=True
    )


def _same_or_inside(folder: Path, root: Path) -> bool:
    """Return whether ``folder`` is ``root`` or somewhere under it."""
    resolved, base = folder.resolve(), root.resolve()
    return resolved == base or base in resolved.parents


def copy_backups_to_second_folder(
    settings: Settings, *, report: Callable[[str], None] | None = None
) -> SecondCopyResult | None:
    """Bring the second folder up to date; None when none is set.

    Writes the copy of every finished backup of the newest kept days that
    the folder does not hold yet, then removes the copies of older days. A
    copy that fails is reported and the rest are still written.

    Raises:
        BackupError: If the folder is set but cannot be used at all -- no
            password, the folder is the backup folder itself, it cannot be
            created or read, or another pass is running.

    """
    folder = second_folder(settings)
    if folder is None:
        return None
    say = report if report is not None else (lambda _line: None)
    password = _password(settings)
    if _same_or_inside(folder, Path(settings.backup_directory)):
        raise BackupError(
            f"The second backup folder {folder} is inside the backup folder "
            "itself, so it would be no second place. Name a folder on another "
            "drive or one a cloud client keeps in step."
        )
    if not _COPY_LOCK.acquire(blocking=False):
        raise BackupError("The second copy is already being written.")
    try:
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise BackupError(
                f"The second backup folder {folder} could not be created: "
                f"{error.strerror or error}"
            ) from error
        for stale in folder.glob(f"{COPY_PREFIX}*{COPY_SUFFIX}{PART_SUFFIX}"):
            stale.unlink(missing_ok=True)
        held = {copy.name: copy for copy in list_second_copies(folder)}
        wanted: dict[str, BackupFolder] = {}
        unreadable: list[str] = []
        for backup in list_backups(settings):
            if backup.complete is None:
                unreadable.append(backup.name)
            elif backup.complete and _day_of(copy_name(backup)) is not None:
                wanted[copy_name(backup)] = backup
        days = sorted(
            {day for name in [*held, *wanted] if (day := _day_of(name)) is not None},
            reverse=True,
        )
        kept_days = set(days[: settings.backup_second_keep_days])
        result = SecondCopyResult(folder=folder, unreadable=unreadable)
        for name in sorted(wanted):
            if name in held or _day_of(name) not in kept_days:
                continue
            try:
                _write_copy(wanted[name].path, folder / name, password)
            except (OSError, BackupError) as error:
                detail = getattr(error, "strerror", None) or str(error)
                result.failed.append(f"{name}: {detail}")
                say(f"  second copy of {wanted[name].name} FAILED: {detail}")
                continue
            result.written.append(name)
            say(f"  second copy written: {folder / name}")
        for name, copy in sorted(held.items()):
            if copy.day not in kept_days:
                copy.path.unlink(missing_ok=True)
                result.removed.append(name)
                say(f"  removed the old second copy {name}")
        return result
    finally:
        _COPY_LOCK.release()


def _write_copy(source: Path, destination: Path, password: str) -> None:
    """Write one copy beside its final name, read it back, then name it."""
    part = destination.with_name(destination.name + PART_SUFFIX)
    try:
        seal_folder(source, part, password=password)
        verify_copy(part, password=password)
        os.replace(part, destination)
    finally:
        part.unlink(missing_ok=True)
