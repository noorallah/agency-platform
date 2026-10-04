"""Generate docs/qa/*.md from INDEPENDENT_TEST_CASES.md, the module catalog and the role seed."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
SCRATCH = Path(sys.argv[2])
OUT = ROOT / "docs" / "qa"
SRC = (ROOT / "docs" / "INDEPENDENT_TEST_CASES.md").read_text(encoding="utf-8")
TABS = json.loads((SCRATCH / "tabs.json").read_text(encoding="utf-8"))
MATRIX = json.loads((SCRATCH / "matrix.json").read_text(encoding="utf-8"))
ROLES = json.loads((SCRATCH / "roles.json").read_text(encoding="utf-8"))["roles"]
TODAY = "2026-10-04"
RELEASE = "1.3.0"

# --------------------------------------------------------------------------
# The 1.3.0 menu. The desktop's own catalogue of the menu is the authority for
# where a screen is reached, so the paths printed below are derived from
# desktop/lib/phase2/menu_layout.dart rather than written by hand.
MENU_SRC = (ROOT / "desktop" / "lib" / "phase2" / "menu_layout.dart").read_text(encoding="utf-8")
SHORT_LISTS = {"Sell": {"salesReturns", "sales/credit-notes", "sales/customer-debit-notes"},
               "Buy": {"purchaseReturns", "purchases/debit-notes"}}
_ITEM = re.compile(r"MenuItemSpec\(\s*AppModule\.(\w+),\s*'([\w-]+)',\s*'([^']+)'\)|MenuItemSpec\.module\(\s*AppModule\.(\w+),\s*'([^']+)'\)")


def _items(chunk: str) -> list[tuple[str, str]]:
    found = []
    for m in _ITEM.finditer(chunk):
        if m.group(1):
            found.append((m.group(1) + "/" + m.group(2), m.group(3)))
        else:
            found.append((m.group(4), m.group(5)))
    return found


def load_menu() -> tuple[dict[str, tuple[str, int, str]], list[str]]:
    """Map a catalogue key (module/tab) to (menu path, order, top-level section)."""
    paths: dict[str, tuple[str, int, str]] = {}
    sections: list[str] = []
    order = 0
    start = MENU_SRC.index("static const List<MenuAreaSpec> areas")
    end = MENU_SRC.index("static const MenuAreaSpec settings")
    body = MENU_SRC[start:end]
    heads = [(m.start(), m.group(2)) for m in re.finditer(r"MenuAreaSpec\(\s*'(\w+)',\s*'([^']+)'", body)]
    for i, (pos, label) in enumerate(heads):
        chunk = body[pos:heads[i + 1][0] if i + 1 < len(heads) else len(body)]
        cut = chunk.index("], daily:") if "], daily:" in chunk else len(chunk)
        daily = set(re.findall(r"'([\w/-]+)'", chunk[cut:]))
        if label == "Reports":
            for key, item in _items(chunk[:cut]):
                order += 1
                paths[key] = (f"Reports > {item}", order, "Reports")
            sections.append("Reports")
            continue
        if label == "Home":
            continue
        sections.append(label)
        for gm in re.finditer(r"MenuGroupSpec\('([^']+)',\s*\[(.*?)\]\)", chunk[:cut], re.S):
            for key, item in _items(gm.group(2)):
                order += 1
                if key in SHORT_LISTS.get(label, ()):
                    where = f"{label} > Returns & notes > {item}"
                elif key in daily:
                    where = f"{label} > {item}"
                else:
                    where = f"{label} > All {label} screens > {gm.group(1)} > {item}"
                paths[key] = (where, order, label)
    sset = MENU_SRC[MENU_SRC.index("static const MenuAreaSpec settings"):MENU_SRC.index("/// Every area, the gear")]
    for gm in re.finditer(r"MenuGroupSpec\('([^']+)',\s*\[(.*?)\](?:,\s*part: MenuPart\.(\w+))?\)", sset, re.S):
        part = {"setUp": "Set up", "platform": "Platform"}.get(gm.group(3))
        head = f"Settings > {part} > {gm.group(1)}" if part else f"Settings > {gm.group(1)}"
        top = f"Settings > {part or gm.group(1)}"
        found = _items(gm.group(2))
        if found and top not in sections:
            sections.append(top)
        for key, item in found:
            order += 1
            paths[key] = (f"{head} > {item}", order, top)
    return paths, sections


MENU, MENU_SECTIONS = load_menu()

# --------------------------------------------------------------------------
# Preparations: what each developer fixture built, said so a person can build
# it by hand on an installed copy.
PREP = {
    "firm-admin": "A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).",
    "custom-role": "A firm administrator of QA01, and a custom role *Night Desk* holding exactly SALES_VIEW, CUSTOMER_VIEW, RECEIPT_VIEW and RECEIPT_CREATE.",
    "custom-template": "The *Night Desk* custom role, and a QA01 job template that bundles it.",
    "role-holder": "The *Night Desk* custom role, and a QA01 user holding that role and nothing else.",
    "platform-admin": "The platform administrator (`platform-admin@agency.local`), who belongs to no firm.",
    "platform-admin-member": "A platform administrator who is also a member of QA01 and QA02.",
    "two-firm-user": "An ordinary user who is a member of QA01 and QA02, with a role in each.",
    "unprovisioned-firm": "The platform administrator, and a new firm created with deployment mode **SCHEMA** whose storage has not been provisioned.",
    "unfinished-firm": "The platform administrator, and a new **SCHEMA** firm that has been provisioned and nothing else: no profile, books, tax, branch or members.",
    "ready-firm": "A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.",
    "shared-pair": "Two SHARED firms, QASH1 and QASH2, each with its own firm administrator.",
    "platform-operator": "A platform administrator with **PLATFORM** scope (not ALL_FIRMS) who is a member of QA01 and QA02 with no roles. Creating one needs the platform designation set on the account; ask the developer if the screen offers no way to do it.",
    "sales-executive": "A QA01 user hired with the *Field Sales* job template (role SALES_EXECUTIVE only).",
    "manual-hire": "A firm administrator of QA01, and a QA01 user given two roles picked by hand.",
    "two-tier-hire": "The platform administrator, a firm administrator of QA01, and a user holding one platform-wide role and one QA01 role.",
    "firm-template-hire": "A firm administrator of QA01, a QA01 job template of its own, and somebody hired into it.",
    "clone-source": "A firm administrator of QA01, and a QA01 salesperson to hire somebody like.",
    "template-offering": "The platform administrator and a firm administrator of QA01.",
    "shared-member": "The platform administrator, a firm administrator of QA01, a user who is a member of QA01 and QA02, and a user in QA02 only.",
    "shared-member-roles": "As *shared-member*, with the QA01/QA02 member holding a role in each tier.",
    "invoiced": "A firm administrator of QA01, and one sale taken to an approved invoice: order, dispatched delivery note, approved invoice.",
    "loyalty-viewer": "A QA01 user hired with the *Sales Manager* job template.",
    "cashier": "A QA01 user holding the CASHIER role only, and a customer to record a receipt against.",
    "accountant": "A QA01 user hired with the *Accounts* job template (role ACCOUNTANT only).",
    "outsider": "The platform administrator, a firm administrator of QA01, and a cashier who belongs to QA02 only.",
    "outsider-added": "As *outsider*, with the QA02 cashier already added to QA01 as *Counter Sales*.",
    "lock-target": "The platform administrator, a firm administrator of QA01, and an ordinary QA01 user to act on.",
    "isolation-pair": "The platform administrator, and one customer in each of two firms, QA01 and QA02.",
    "shared-isolation-pair": "The platform administrator, and one customer in each of two SHARED firms, QASH1 and QASH2.",
    "customer-master": "A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.",
    "invoiced-part-paid": "As *invoiced*, with the invoice of 590.00 and a receipt of 200.00 applied to it.",
    "vendor-master": "A firm administrator of QA01, and a vendor `QA-V` *Supply Check* with one contact, address, bank account, tax record, attachment and note; a vendor category `QA-CAT` and type `QA-TYP`.",
    "product-master": "A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.",
    "branch-master": "A firm administrator of QA02 with a default branch and warehouse, and two import files (one valid, one with a bad row).",
    "config-firm": "A finished firm, a vendor, and a product with its own PACK to KG conversion rule.",
    "buy-ready": "A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.",
    "po-approved": "As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.",
    "po-received": "As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.",
    "po-invoiced": "As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).",
    "stock-ready": "A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse.",
    "pharma-firm": "A firm on the **Pharmacy** profile, with a batch-tracked product in two batches with different expiry dates, and two orders for it.",
    "electronics-firm": "A firm on the **Electronics** profile, with a serial-tracked product that carries a warranty.",
    "selling-firm": "The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.",
    "selling-ordered": "As *selling-firm*, plus the order described in the preparation table, approved.",
    "selling-delivered": "As *selling-ordered*, plus the two delivery notes in the preparation table, dispatched.",
    "selling-invoiced": "As *selling-delivered*, plus the first note billed and approved, as in the preparation table.",
    "selling-paid": "As *selling-invoiced*, plus the two receipts and the second invoice in the preparation table.",
    "territory-firm": "A Wholesale firm with the territories, routes, rounds, salespeople and beat plans described in this section's preparation table.",
    "commission-firm": "As *territory-firm*, plus commission rules, targets and three collected sales, as in the preparation table.",
    "loyalty-points": "As *selling-invoiced*, plus 200 loyalty points credited to the first customer.",
    "compliance-firm": "The GST-registered firm described in this section's preparation table, with its three invoices.",
    "policy-firm": "As *selling-firm*, plus a **blocking** credit policy and the delivery-note stage switched off in the sales workflow settings.",
}

# Which source sections go to which file. (file, title, [section headings], [catalog tabs for screen checks])
FILES = [
    ("02_SIGN_IN_AND_ACCOUNTS", "Signing in, sessions and your own account",
     ["Signing in, sessions, and the life of an account", "Platform mode — the switcher and what a platform administrator starts on",
      "The user menu — who you are, and where you start", "User tiers — what a platform operator may and may not reach"],
     []),
    ("03_USERS_AND_ROLES", "Users, roles, job templates and hiring",
     ["A firm administrator creating users", "Hiring somebody who already has an account", "Hiring like an existing person",
      "User templates — hiring by naming the job", "Templates from the platform side — which firms a job is offered to",
      "Roles in two tiers — every firm, and one firm", "Roles — a firm's own roles and templates"],
     [("Administration", ["Users", "Roles", "Permissions", "User Templates", "User-Firm Assignments"])]),
    ("04_FIRMS_AND_CONFIGURATION", "Firms, set-up and configuration",
     ["Firms — creating one and finishing it", "Firm isolation — one firm never sees another's data",
      "Configuration — numbering, profiles, tax and units", "Custom fields — how a profile reaches a record"],
     [("Administration", ["Firms", "Numbering Series", "Business Profiles", "Feature Management", "Module Configuration",
                          "Attribute Definitions", "Mandatory Attributes", "Profile Assignment", "Tax Configuration", "Tax Rules",
                          "Rule Simulator", "Execution Log", "Settings", "Units of Measure", "UOM Groups", "Packaging Types",
                          "Packaging Levels", "Conversion Rules", "Industry Templates"])]),
    ("05_MASTERS", "Masters: customers, vendors, products, branches and warehouses",
     ["Customers", "Vendors, products, branches and warehouses"],
     [("Masters", ["Customers", "Statements", "Products", "Vendors", "Vendor Categories", "Vendor Types", "Branches",
                   "Warehouses", "Storage Areas", "Warehouse Types", "Branch Types", "Settings", "Financial Years", "Firm Settings"])]),
    ("06_PURCHASING", "Purchasing: order to payment",
     ["Buying — order to payment"],
     [("Purchases", None), ("Purchase Invoices", None), ("Purchase Returns", None), ("Goods Receipts", None)]),
    ("07_INVENTORY", "Inventory, batches and serial numbers",
     ["Stock"],
     [("Inventory", None)]),
    ("08_SELLING", "Selling: quotation to cash, returns and credit notes",
     ["Selling — quotation to cash"],
     [("Quotations", None), ("Sales Orders", None), ("Delivery Notes", None), ("Sales Invoices", None), ("Sales Returns", None),
      ("Sales", ["Proforma", "Credit Notes"])]),
    ("09_PRICING_AND_INCENTIVES", "Pricing, promotions, loyalty, commission and targets",
     ["Pricing, promotions and incentives"],
     [("Sales", ["Price Lists", "Promotions", "Commission", "Targets"]), ("Masters", ["Loyalty"])]),
    ("10_TERRITORY", "Territory, routes and beats",
     ["Territory, routes and beats"],
     [("Sales", ["Geography", "Route Types", "Beat Plans", "Call Lists", "Coverage", "Route Builder"]), ("Masters", ["Places"])]),
    ("11_COMPLIANCE", "Compliance: GST returns, e-invoices and TCS",
     ["Compliance — GST returns, e-invoices and TCS"],
     [("Sales", ["E-Invoice", "GST Returns", "TCS"])]),
    ("12_FINANCE_AND_REPORTS", "Finance, reports, audit and diagnostics",
     ["Finance, reports and the rest of the platform", "A cashier can see the till", "The audit trail"],
     [("Finance", None), ("Reports", None), ("Settings", None), ("Dashboard", None)]),
    ("13_CROSS_CUTTING", "Cross-cutting: permissions, concurrency and grants",
     ["Permissions — the server refuses, not only the button", "Concurrency — two people, one record",
      "The five modules a firm administrator could not open"],
     []),
]

# --------------------------------------------------------------------------
# Parse the source into sections.
sections: dict[str, str] = {}
parts = re.split(r"(?m)^## ", SRC)
for part in parts[1:]:
    head, _, body = part.partition("\n")
    sections[head.strip()] = body

used = {h for f in FILES for h in f[2]}
skip = {"How a case works", "Adding a case"}
missing = [h for h in sections if h not in used and h not in skip]
unknown = [h for f in FILES for h in f[2] if h not in sections]
assert not unknown, unknown
if missing:
    raise SystemExit(f"Sections with no module file: {missing}. Add them to FILES.")


def generic(text: str) -> str:
    """Replace developer fixture vocabulary with installed-copy vocabulary."""
    t = text
    t = t.replace("<SUFFIX>", "QA").replace("<suffix>", "qa")
    t = re.sub(r"\bTESTSH1\b", "QASH1", t)
    t = re.sub(r"\bTESTSH2\b", "QASH2", t)
    t = re.sub(r"\bTEST01\b", "QA01", t)
    t = re.sub(r"\bTEST02\b", "QA02", t)
    t = t.replace("the fixture's ", "the prepared ").replace("The fixture's ", "The prepared ")
    t = t.replace("this fixture's ", "this preparation's ").replace("the fixture ", "the preparation ")
    t = t.replace("fixtures.local", "qa.test").replace("Fixture@2026pw", "a password you choose")
    t = re.sub(r"\| Fixture \|", "| Preparation |", t)
    t = re.sub(r"(?<![\w`])fixture(s?)(?![\w`])", r"preparation\1", t)
    t = t.replace("the four demo firms, ", "").replace(", the demo firm, ELEC01, MEDI01", "")
    t = t.replace("the demo firms included, ", "")
    # WHOLE01 is a distinct demo firm, not a synonym for TEST01/QA01 -- mapping
    # it to QA01 made a list naming both ("TEST01, TEST02, WHOLE01, ...") print
    # QA01 twice (D-QA-9). Left as WHOLE01: 00_README's convention already
    # tells the reader to read a demo firm's name as "any other firm on this
    # installation", the same as ELEC01, MEDI01 and FOOD01 beside it.
    t = t.replace("this run's own", "yours")
    return t


NL = chr(10)
DEV_PARAGRAPH = re.compile(r"suffix|schema|run's own|this run|accumulates|seeder|demo firm|test_fixture|fixtures? (build|work|make)", re.I)


def strip_intro(body: str) -> str:
    """Remove developer-only paragraphs from the text before a section's first case."""
    head, sep, rest = body.partition(NL + "### ")
    paras = head.split(NL + NL)
    kept = [p for p in paras if p.lstrip().startswith("|") or not DEV_PARAGRAPH.search(p)]
    return (NL + NL).join(kept) + (sep + rest if sep else "")


def convert_body(body: str) -> str:
    """Drop what only a developer can use: SQL, table checks, fixture commands, known-defect lists."""
    body = strip_intro(body)
    out: list[str] = []
    lines = body.split("\n")
    i = 0
    in_case_data = False
    skipping_known = False
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith("### Known defects"):
            skipping_known = True
        elif s.startswith("### ") or s.startswith("## "):
            skipping_known = False
        if skipping_known:
            i += 1
            continue
        if s.startswith("```sql") or s.startswith("```powershell"):
            # Skip a developer-only code block. A bare ``` fence (no language
            # tag) is kept -- those hold the handful of plain HTTP requests a
            # tester with a REST client can actually send, and blanket-
            # stripping every fence used to take those with the SQL, leaving
            # a "Steps (HTTP)" line with no request under it (D-QA-9).
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                i += 1
            i += 1
            continue
        m = re.match(r"^(\s*)- \*\*(Data|Leaves|Covers)(?: \(HTTP\))?:?\*\*", line)
        if m:
            in_case_data = True
            i += 1
            continue
        if in_case_data:
            if re.match(r"^- \*\*", line) or s.startswith("### ") or s == "---":
                in_case_data = False
            else:
                i += 1
                continue
        fm = re.match(r"^- \*\*Fixture:\*\* `([a-z0-9-]+)`(.*)$", line)
        if fm:
            name, rest = fm.group(1), fm.group(2)
            prep = PREP.get(name)
            if prep is None:
                raise SystemExit(f"No precondition for fixture {name!r}. Add it to PREP.")
            rest = re.sub(r"^\s*[—-]\s*", "", rest).strip()
            extra = f" ({generic(rest)})" if rest else ""
            out.append(f"- **Preconditions:** {prep}{extra}")
            i += 1
            continue
        if re.search(r"scripts\\|\.venv|test_fixture|information_schema|platform\.firms|`fx_|test_fixtures`|DATA_TRAIL|select id from|from platform[.]", line):
            i += 1
            continue
        out.append(generic(line))
        i += 1
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --------------------------------------------------------------------------
tab_index = {m["module"]: m for m in TABS}


def menu_path(module: dict, tab: dict | None) -> str | None:
    """Where the 1.3.0 menu reaches a screen; None for one the menu deliberately does not offer."""
    key = module["moduleId"] if tab is None else f"{module['moduleId']}/{tab['id']}"
    hit = MENU.get(key)
    return hit[0] if hit else None


def screen_checks(prefix: str, spec) -> str:
    rows = []
    n = 0
    for module, tabs in spec:
        m = tab_index[module]
        wanted = [t for t in m["tabs"]] if tabs is None else [t for t in m["tabs"] if t["label"] in tabs]
        targets = [(menu_path(m, t), t["codes"], t["platformOnly"]) for t in wanted]
        if not m["tabs"] and tabs is None:
            targets = [(menu_path(m, None), m["codes"], m["platformOnly"])]
        targets = [x for x in targets if x[0]]
        for where, codes, plat in targets:
            n += 1
            who = "the platform administrator only" if (plat or m["platformOnly"]) else "any role holding " + " or ".join(f"`{c}`" for c in codes)
            rows.append(f"| {prefix}-S{n:02d} | **{where}** | Offered to {who}. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |")
    if not rows:
        return ""
    head = ("## Screen checks\n\nOne standard check for every screen in this area. Run it once per screen as the firm administrator, "
            "then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, "
            "the check only asks that the screen behaves consistently with it.\n\n"
            "| ID | Screen | Expected | Result | Notes |\n| --- | --- | --- | --- | --- |\n")
    return head + "\n".join(rows) + "\n"


HEADER_NOTE = """Part of the QA test suite in `docs/qa/` for **release {release}**, the first
end-to-end test pass (it includes 1.2.0). Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Every menu
path is the 1.3.0 menu: `Sell > Quotations` is the Sell drop-down on the menu
bar, `Sell > All Sell screens > Documents > Proforma` is a screen that is not
daily work, and `Settings > Set up > Pricing > Price Lists` is the gear at the
right of the bar. Generated on {today} from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
running server) and the application's own screen catalogue; regenerate
rather than hand-edit when those change.

Each case keeps its original id (TC-…), so a failure can be traced to the
developer case it came from. Steps marked **(HTTP)** are optional API checks
for a tester with a REST client such as Postman; skip them otherwise."""

index_rows = []
for fname, title, heads, spec in FILES:
    chunks = [f"# {title}\n", HEADER_NOTE.format(today=TODAY, release=RELEASE), ""]
    ncases = 0
    for h in heads:
        body = convert_body(sections[h])
        ncases += len(re.findall(r"(?m)^### TC-", body))
        chunks.append(f"## {generic(h)}\n\n{body}\n")
    sc = screen_checks(fname[:2], spec)
    nscreens = sc.count(f"| {fname[:2]}-S")
    if sc:
        chunks.append(sc)
    chunks.append("## Results summary\n\n| | |\n| --- | --- |\n| Tester | |\n| Date | |\n| Installed version | |\n| Cases passed / failed / blocked | |\n| Worst problem found | |\n")
    (OUT / f"{fname}.md").write_text("\n".join(chunks), encoding="utf-8")
    index_rows.append((fname, title, ncases, nscreens))
    print(fname, ncases, "cases", nscreens, "screen checks")

# --------------------------------------------------------------------------
# Roles and access.
TEMPLATES = [
    ("Firm Administrator", ["FIRM_ADMIN"]), ("Firm Manager", ["FIRM_MANAGER"]), ("Counter Sales", ["CASHIER", "BILLING_EXECUTIVE"]),
    ("Field Sales", ["SALES_EXECUTIVE"]), ("Sales Manager", ["SALES_MANAGER"]), ("Warehouse", ["INVENTORY_MANAGER"]),
    ("Purchasing", ["PURCHASE_EXECUTIVE"]), ("Purchase Manager", ["PURCHASE_MANAGER"]), ("Accounts", ["ACCOUNTANT"]),
    ("Customer Support", ["CUSTOMER_SUPPORT"]), ("Read Only", ["VIEWER"]),
]
VERB = {"CREATE": "create", "UPDATE": "edit", "DELETE": "delete", "RESTORE": "restore", "APPROVE": "approve",
        "CANCEL": "cancel", "IMPORT": "import", "EXPORT": "export", "MANAGE": "manage", "POST": "post", "REVERSE": "reverse"}


def role_rows(offered: dict) -> tuple[list[tuple[int, str, dict, dict | None]], set[str]]:
    """The menu rows a job is offered, in menu order, and the sections they fall in."""
    rows = []
    for m in TABS:
        if m["module"] not in offered:
            continue
        tabs = [t for t in m["tabs"] if t["label"] in offered[m["module"]]]
        if not tabs:
            hit = MENU.get(m["moduleId"])
            if hit:
                rows.append((hit[1], hit[0], m, None))
        for t in tabs:
            hit = MENU.get(f"{m['moduleId']}/{t['id']}")
            if hit:
                rows.append((hit[1], hit[0], m, t))
    rows.sort(key=lambda r: r[0])
    seen = {MENU[(m["moduleId"] if t is None else f"{m['moduleId']}/{t['id']}")][2] for _, _, m, t in rows}
    return rows, seen


def actions_for(codes: set[str], tab_codes: list[str]) -> str:
    """The job's codes in this screen's area, other than viewing it."""
    prefixes = {c.rsplit("_", 1)[0] for c in tab_codes if c.endswith("_VIEW")}
    acts = {c for c in codes for p in prefixes if c.startswith(p + "_") and not c.endswith("_VIEW")}
    acts |= {c for c in tab_codes if c in codes and not c.endswith("_VIEW")}
    return ", ".join(f"`{a}`" for a in sorted(acts)) if acts else "none beyond viewing"


role_md = ["# Roles and access\n", """Part of the QA test suite in `docs/qa/` for **release {release}**. What each job
template may reach, computed on {today} from the application's own rules: the role seed
(`backend/app/identity/system_seed.py`) and the desktop's screen catalogue and
visibility filter. Regenerate rather than hand-edit.

**How to test a job.** Hire one user per job with *Settings > Platform >
People > Users > + New*, naming the job in **Job template**. Sign in as each and check three
things, recording one result per job:

1. **The menu offers exactly the screens listed** for that job, no more and
   no fewer (the paths are the 1.3.0 menu: a screen under *All Sell screens* is
   one click further than the daily list). A business profile can hide a whole module (for example batches
   on a profile that does not track them); note any such difference.
2. **Actions.** On each screen, write buttons appear only where the job holds
   a matching code. A screen marked *none beyond viewing* offers no New, Edit,
   Delete, Approve or Cancel, or offers them disabled with a reason.
3. **The server agrees.** Where a button is offered but the job lacks the code,
   the action is refused with *You do not have permission to perform this
   action.* A hidden button is not a control; a refused request is.

The *Codes held in this area* column lists the job's permission codes that
share the screen's area, other than viewing it. A code names one action, and
the area is broad: `SALES_INVOICE_CREATE` on the Quotations row means the job
may raise invoices, not quotations. Check each button against the code that
names it.""".format(today=TODAY, release=RELEASE), ""]
role_md.append("## Summary\n\n| Job template | Roles | Screens offered |\n| --- | --- | --- |")
for label, roles in TEMPLATES:
    offered = {}
    for r in roles:
        for mod, tabs in MATRIX[r].items():
            offered.setdefault(mod, set()).update(tabs)
    n = len(role_rows(offered)[0])
    role_md.append(f"| {label} | {', '.join(roles)} | {n} |")
role_md.append("")
for idx, (label, roles) in enumerate(TEMPLATES, 1):
    codes = set()
    offered: dict[str, set[str]] = {}
    for r in roles:
        codes |= set(ROLES[r])
        for mod, tabs in MATRIX[r].items():
            offered.setdefault(mod, set()).update(tabs)
    role_md.append(f"## R{idx:02d}. {label}\n\nRoles: {', '.join(f'`{r}`' for r in roles)}. {len(codes)} permission codes.\n")
    role_md.append("| Where in the menu | Codes held in this area | Result | Notes |\n| --- | --- | --- | --- |")
    rows, seen = role_rows(offered)
    for _, where, m, t in rows:
        role_md.append(f"| {where} | {actions_for(codes, m['codes'] if t is None else t['codes'])} | Not run | |")
    not_offered = [x for x in MENU_SECTIONS if x not in seen]
    role_md.append(f"\n**Nothing offered under:** {', '.join(not_offered) if not_offered else 'nothing'}. Check each is absent from the menu, and from the gear's Settings page (the dialogs under Settings, such as Credit Control or Sales Stages, are offered by the codes `docs/CONFIGURATION_SETTINGS_GUIDE.md` names and are not rows here). A firm role is never offered the Platform part except the People screens its codes allow.\n")
role_md.append("""## The platform administrator

`platform-admin@agency.local` starts on **Platform** every time, with the menu
bar reduced to Home and the gear. The gear's **Platform** part holds People
(Users, Roles, Permissions, User Templates, User-Firm Assignments), Firms
(Firms, Business Profiles), Agency (Branding) and System (Audit Logs,
Diagnostics, Licensing, Backups, Platform Dashboard); Business profile (Feature
Management, Module Configuration, Attribute Definitions, Mandatory Attributes,
Profile Assignment, Industry Templates) is under Settings. Choosing a firm in
the switcher opens that firm's menus. Test cases for this account are in
`02_SIGN_IN_AND_ACCOUNTS.md` and `04_FIRMS_AND_CONFIGURATION.md`.
""")
(OUT / "01_ROLES_AND_ACCESS.md").write_text("\n".join(role_md), encoding="utf-8")
json.dump(index_rows, open(SCRATCH / "qa_index.json", "w"))
print("roles file written")
