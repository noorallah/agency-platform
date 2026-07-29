"""Safe JSON serialization helpers for common framework values."""

import json
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


def json_dumps(value: object) -> str:
    """Serialize common framework values using deterministic compact JSON."""
    return json.dumps(
        value, default=_json_default, separators=(",", ":"), sort_keys=True
    )


def json_loads(value: str) -> object:
    """Deserialize JSON text."""
    return json.loads(value)


def _json_default(value: object) -> str:
    """Serialize standard non-JSON primitives used by application contracts."""
    if isinstance(value, UUID | datetime | date | Decimal):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
