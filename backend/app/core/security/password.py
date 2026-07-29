"""Argon2 password hashing utilities."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


class PasswordSecurity:
    """Hash and verify passwords with Argon2's recommended defaults."""

    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        """Initialize the utility with an optionally injected Argon2 hasher."""
        self._hasher = hasher or PasswordHasher()

    def hash_password(self, password: str) -> str:
        """Return a one-way Argon2 hash for a plaintext password."""
        return self._hasher.hash(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Return whether a plaintext password matches its stored hash."""
        try:
            return self._hasher.verify(password_hash, password)
        except (InvalidHashError, VerificationError):
            return False
