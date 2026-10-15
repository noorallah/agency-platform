"""Probe: the layout and the other print settings are saved, read back, bounded and put back."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _prt import *

c = Check("p_prt_layout_readback")
a = admin()
held = must(a.get(PRINT_TEMPLATE), "template")
base = {k: x for k, x in held.items() if k not in ("id", "document_type", "is_customised")}
if not held.get("is_customised") and not base.get("copy_labels"):
    base["copy_labels"] = list(DEFAULT_COPIES)
try:
    for layout in ("TRADE", "STANDARD"):
        must(a.put(PRINT_TEMPLATE, {**base, "bill_layout": layout}), f"save {layout}")
        c.eq(data(a.get(PRINT_TEMPLATE)[1])["bill_layout"], layout, f"{layout} reads back")
    c.eq(a.put(PRINT_TEMPLATE, {**base, "bill_layout": "FANCY"})[0], 422, "an unknown layout is refused")
    c.eq(data(a.get(PRINT_TEMPLATE)[1])["bill_layout"], "STANDARD", "a refused save changed nothing")
    c.eq(a.put(PRINT_TEMPLATE, {**base, "page_size": "A3"})[0], 422, "an unknown paper is refused")
    c.eq(a.put(PRINT_TEMPLATE, {**base, "margin_mm": "4"})[0], 422, "a margin under 5 mm is refused")
    c.eq(a.put(PRINT_TEMPLATE, {**base, "copy_labels": ["1", "2", "3", "4", "5"]})[0], 422, "five copies are refused")
    c.eq(a.put(PRINT_TEMPLATE, {**base, "accent_color": "red"})[0], 422, "a colour that is not #RRGGBB is refused")
    must(a.put(PRINT_TEMPLATE, {**base, "upi_id": "  shop@okaxis  "}), "upi trimmed")
    c.eq(data(a.get(PRINT_TEMPLATE)[1])["upi_id"], "shop@okaxis", "a UPI ID is trimmed")
    must(a.put(PRINT_TEMPLATE, {**base, "upi_id": "   "}), "upi blank")
    c.eq(data(a.get(PRINT_TEMPLATE)[1])["upi_id"], None, "a blank UPI ID clears it")
    must(a.put(PRINT_TEMPLATE, {**base, "page_size": "HALF", "bill_layout": "TRADE"}), "half with trade")
    got = data(a.get(PRINT_TEMPLATE)[1])
    c.eq((got["page_size"], got["bill_layout"]), ("HALF", "TRADE"), "half page with the Trade layout saved is stored as sent")
    c.eq(a.put("/api/v1/document-framework/print-templates/NOT_A_DOCUMENT", base)[0] in (404, 422), True, "an unknown document type is refused")
finally:
    must(a.put(PRINT_TEMPLATE, base), "template put back")
c.eq(data(a.get(PRINT_TEMPLATE)[1])["page_size"], base["page_size"], "put back: the paper is as found")
c.done()
