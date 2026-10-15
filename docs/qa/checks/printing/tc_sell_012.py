"""TC-SELL-012: print settings (two copies, own labels) and the printed bill."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _prt import *

c = Check("tc_sell_012")
a = admin()
v = admin("viewer")
sc = Scene(a, stock="50")
shown = must(a.get(PRINT_TEMPLATE), "template")
c.ok(isinstance(shown.get("copy_labels"), list), "the template answers a list of copy labels", shown.get("copy_labels"))
with counter(a):
    bill = sc.bill()
    c.eq(pdf_text(printed(a, bill["id"])).count("TAX INVOICE"), 3, "a firm that never saved prints three copies")
    labels = ["ORIGINAL FOR RECIPIENT", "DUPLICATE FOR TRANSPORTER"]
    status, body = v.put(PRINT_TEMPLATE, {"copy_labels": labels})
    c.eq(status, 403, "a Viewer cannot save print settings")
    with template(a, copy_labels=labels):
        c.eq(data(a.get(PRINT_TEMPLATE)[1])["copy_labels"], labels, "the two labels read back")
        raw = printed(a, bill["id"])
        text = pdf_text(raw)
        for word in ("CGST", "SGST", "HSN", "HSN / SAC", "AMOUNT CHARGEABLE, IN WORDS"):
            c.ok(word in text, f"the print carries {word}")
        c.eq(text.count("ORIGINAL FOR RECIPIENT"), 1, "one ORIGINAL copy")
        c.eq(text.count("DUPLICATE FOR TRANSPORTER"), 1, "one DUPLICATE copy")
        c.ok("TRIPLICATE" not in text, "no third copy")
        c.eq(len(kinds(raw)), 2, "two copies are two pages")
        c.ok("118.00" in text, "the total 118.00 is printed")
    c.eq(pdf_text(printed(a, bill["id"])).count("TAX INVOICE"), 3, "put back: three copies again")
c.done()
