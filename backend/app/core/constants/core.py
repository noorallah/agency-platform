"""Central constants used across the reusable framework."""

from datetime import UTC

API_VERSION = "v1"
DEFAULT_PAGE_NUMBER = 1
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
ISO_DATE_FORMAT = "%Y-%m-%d"
ISO_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
UTC_TIMEZONE = UTC
HEADER_CORRELATION_ID = "X-Correlation-ID"
HEADER_REQUEST_ID = "X-Request-ID"
HEADER_PROCESS_TIME = "X-Process-Time-Ms"
HEADER_CONTENT_TYPE_OPTIONS = "X-Content-Type-Options"
HEADER_FRAME_OPTIONS = "X-Frame-Options"
HEADER_REFERRER_POLICY = "Referrer-Policy"
HEADER_PERMISSIONS_POLICY = "Permissions-Policy"
