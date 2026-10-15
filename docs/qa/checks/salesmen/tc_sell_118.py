"""TC-SELL-118: two salesmen cannot share a name, whatever the case."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *

c = Check("tc_sell_118")
a = admin()
tag = suffix(5)
base = f"Phone order {tag}"
must(a.post(SM, {"name": base}), "first entry")


def count() -> int:
    """Return how many entries carry this run's tag."""
    return len(all_rows(a, f"{SM}?search={tag}"))


c.eq(count(), 1, "one entry to start")
status, body = a.post(SM, {"name": base.lower()})
c.ok(status in (409, 422) and "already" in message(body).lower(),
     "the same name in another case is refused in words", f"{status} {message(body)[:150]}")
c.eq(count(), 1, "nothing was added by the refused save")
second = must(a.post(SM, {"name": f"Phone Order 2 {tag}"}), "second entry")
status, body = a.put(f"{SM}/{second['id']}", {"name": base.upper()})
c.ok(status in (409, 422) and "already" in message(body).lower(),
     "editing to the first name in capitals is refused the same way", f"{status} {message(body)[:150]}")
c.eq(count(), 2, "two entries remain")
c.done()
