"""Encrypt a small secret at rest under a key held in the server's config.

Messaging credentials (an SMTP password, a WhatsApp access token, an SMS auth
key) have to be stored, because the server sends on the firm's behalf while
nobody is signed in -- and they must not be readable by whoever can read the
database or a backup of it (backlog 51, decision 2). The key lives in
``AGENCY_MESSAGING_KEY``, never in the database.

**Standard library only.** The release is compiled with Nuitka and every
dependency has to survive that; ``cryptography`` is a Rust extension and would
be the first native wheel added for one feature. The construction is the
textbook one built from HMAC-SHA256, which the standard library has:

* two keys derived from the configured secret (HKDF-style, one for the stream,
  one for the tag), so the configured value is never used directly;
* a random 16-byte nonce per encryption;
* the keystream is ``HMAC(stream_key, nonce || counter)`` -- HMAC is a PRF, so
  this is a stream cipher in counter mode;
* **encrypt-then-MAC**: the tag is ``HMAC(tag_key, version || nonce || ct)`` and
  is checked, in constant time, before anything is decrypted.

The stored form is ``v1.<urlsafe base64 of nonce || ciphertext || tag>``. The
version prefix is what lets a later release change the construction and still
read what this one wrote.
"""

import base64
import hashlib
import hmac
import secrets

_VERSION = b"v1"
_PREFIX = "v1."
_NONCE_BYTES = 16
_TAG_BYTES = 32
_BLOCK = hashlib.sha256().digest_size


class SecretBoxError(ValueError):
    """A stored secret could not be opened: wrong key, or altered."""


def _derive(secret: str, purpose: bytes) -> bytes:
    """Derive one purpose-bound 32-byte key from the configured secret."""
    extracted = hmac.new(
        b"agency-platform/secret-box", secret.encode("utf-8"), hashlib.sha256
    ).digest()
    return hmac.new(extracted, purpose + b"\x01", hashlib.sha256).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    """Return ``length`` bytes of keystream for one nonce."""
    blocks = []
    for counter in range((length + _BLOCK - 1) // _BLOCK):
        blocks.append(
            hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        )
    return b"".join(blocks)[:length]


def seal(plaintext: str, *, secret: str) -> str:
    """Encrypt and authenticate ``plaintext`` under ``secret``.

    Args:
        plaintext: The value to protect.
        secret: The configured key (``Settings.messaging_secret()``).

    Returns:
        The stored form, ``v1.<base64>``.

    """
    if not secret:
        raise SecretBoxError("No key is configured to encrypt with.")
    data = plaintext.encode("utf-8")
    nonce = secrets.token_bytes(_NONCE_BYTES)
    stream = _keystream(_derive(secret, b"stream"), nonce, len(data))
    ciphertext = bytes(a ^ b for a, b in zip(data, stream, strict=True))
    tag = hmac.new(
        _derive(secret, b"tag"), _VERSION + nonce + ciphertext, hashlib.sha256
    ).digest()
    return _PREFIX + base64.urlsafe_b64encode(nonce + ciphertext + tag).decode("ascii")


def open_sealed(stored: str, *, secret: str) -> str:
    """Check and decrypt a value :func:`seal` produced.

    Raises:
        SecretBoxError: If the key is wrong, the value was altered, or it is
            not in a form this release can read. The message never includes
            the value.

    """
    if not secret:
        raise SecretBoxError("No key is configured to decrypt with.")
    if not stored.startswith(_PREFIX):
        raise SecretBoxError("The stored secret is in an unknown format.")
    try:
        raw = base64.urlsafe_b64decode(stored[len(_PREFIX) :].encode("ascii"))
    except (ValueError, UnicodeEncodeError) as error:
        raise SecretBoxError("The stored secret is not readable.") from error
    if len(raw) < _NONCE_BYTES + _TAG_BYTES:
        raise SecretBoxError("The stored secret is not readable.")
    nonce = raw[:_NONCE_BYTES]
    ciphertext = raw[_NONCE_BYTES:-_TAG_BYTES]
    tag = raw[-_TAG_BYTES:]
    expected = hmac.new(
        _derive(secret, b"tag"), _VERSION + nonce + ciphertext, hashlib.sha256
    ).digest()
    if not hmac.compare_digest(tag, expected):
        raise SecretBoxError(
            "The stored secret does not open with this server's key; it was "
            "saved under another key or has been altered."
        )
    stream = _keystream(_derive(secret, b"stream"), nonce, len(ciphertext))
    data = bytes(a ^ b for a, b in zip(ciphertext, stream, strict=True))
    return data.decode("utf-8")
