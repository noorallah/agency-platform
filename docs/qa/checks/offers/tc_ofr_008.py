"""TC-OFR-008: a part share of "11 + 1" (step 4 of the worked example)."""

from _offer import (
    Check,
    D,
    Scene,
    admin,
    cand,
    data,
    doc_line,
    message,
    mode,
    offer_rows,
    taxable,
)

c = Check("tc_ofr_008")
api = admin()
with mode(api, "COMBINE"):
    s = Scene(api).tea()
    pv = s.preview([s.line("6")])
    share = (cand(pv, s.code("TEA11")) or {}).get("part_share") or {}
    c.eq(
        (D(share.get("charged_quantity")), D(share.get("free_quantity"))),
        (D("5.5"), D("0.5")),
        "(1) 6 on TEA-11 is offered as 5.5 charged + 0.5 free",
    )
    pv = s.preview([s.line("4")])
    share = (cand(pv, s.code("TEA11")) or {}).get("part_share") or {}
    c.eq(
        (D(share.get("charged_quantity")), D(share.get("free_quantity"))),
        (D("3.6667"), D("0.3333")),
        "(1) 4 is 3.6667 + 0.3333",
    )
    pick = {"part_share": s.key("TEA11")}
    status, body = s.save([s.line("5.5", offer_choice=pick)])
    c.eq(
        status,
        201,
        f"(2) 5.5 with TEA-11 as a part share is saved ({message(body)[:160]})",
    )
    if status == 201:
        line = doc_line(data(body))
        c.eq(
            (
                D(line["quantity"]),
                D(line["free_quantity"]),
                D(line["discount_amount"]),
                taxable(line),
                D(line["tax_amount"]),
                D(line["net_amount"]),
            ),
            (D("5.5"), D("0.5"), D("27.5"), D("522.5"), D("62.70"), D("585.20")),
            "(2) 5.5 + 0.5 free, TEA-5 27.50, taxable 522.50, GST 62.70, amount 585.20",
        )
        c.eq(
            sorted(offer_rows(line, "APPLIED")),
            sorted(
                [
                    ("TEA11", "APPLIED", True, D(0), D("0.5"), True),
                    ("TEA5", "APPLIED", False, D("27.5"), D(0), False),
                ]
            ),
            "(2) rows: TEA-11 0.5 free as a part share, chosen; TEA-5 27.50, the"
            " server's (design 3.2: chosen is whether a person put it there)",
        )
    # (3) refusals.
    c.refused(
        s.save([s.line("5", offer_choice=pick)]),
        422,
        "counted in whole numbers",
        "(3) 5 charged is 5 + 0.4545, not whole pieces: refused",
    )
    c.refused(
        s.save([s.line("5.5", free_quantity="0.5", offer_choice=pick)]),
        422,
        "cannot be billed as a part share",
        "(3) a part share beside a typed free quantity is refused",
    )
    c.refused(
        s.save([s.line("9", offer_choice={"part_share": s.key("TEA5")})]),
        422,
        "cannot be billed as a part share",
        "(3) a part share of a discount offer is refused",
    )
    other = Scene(api).tea(part_share=False)
    c.ok(
        (cand(other.preview([other.line("6")]), other.code("TEA11")) or {}).get(
            "part_share"
        )
        is None,
        "(4) an offer that does not allow it lists no part share",
    )
    c.refused(
        other.save(
            [other.line("5.5", offer_choice={"part_share": other.key("TEA11")})]
        ),
        422,
        "cannot be billed as a part share",
        "(4) and a part share of it is refused",
    )
c.done()
