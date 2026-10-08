"""Probe: platform-admin reads of the firm-stored catalogue with no X-Firm-ID."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import Check, client

c = Check("q_platform_without_firm")
platform = client("platform")
BF = "/api/v1/business-framework"
for path in ("/attribute-definitions?page_size=5", "/active-modules", "/features?page_size=5"):
    s, body = platform.get(BF + path)
    c.ok(s != 503, f"GET {BF}{path} with no X-Firm-ID does not answer 503 database_error", s)
c.done()
