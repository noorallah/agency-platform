# Tag history

Every tag in this repository: when it was created, the commit it marks, and
why. A tag is a fixed point to return to; this file is what says which point
is which. Add a line here in the same work that creates a tag.

List them from git with `git tag -n1 --sort=creatordate`; each tag's own
message carries the same reason in short.

| Tag | Created | Commit | Why it was created | What followed |
| --- | --- | --- | --- | --- |
| `v1.0.1` | 2026-09-26 | `70b46c11` | Release 1.0.1: the build installed on the laptop | QA fixes on the installed build |
| `ui-phase-1` | 2026-09-26 | `90069ef9` | UI phase 1 frozen: 1.0.1 plus the D-QA fixes, with main's CI green. Phase 1 UI is not shared with customers | The phase 2 UI, built on main; functionality is tested with it |
| `v1.3.0` | 2026-10-04 | `71aeeab4` | Release 1.3.0, the milestone of the first end-to-end test. 1.2.0 was never shipped | Purchasing and sales rounds, goods types (backlog 89), the pricing and money display fixes |
| `before-customer-requirements-2026-10-12` | 2026-10-12 | `4b0af34d` | The baseline before the first customer's requirements are built. Main at #1424, the state shown at the customer demonstration, with the money display defects D-UI-91 to 98 fixed. Created so that state can be returned to, and so every change that follows is measured from it | The changes from the requirements review of 2026-10-12 (`dist/customer/CUSTOMER_REQUIREMENTS_QUESTIONS_answers_2026-10-11.xlsx`) |

## Naming

- `vX.Y.Z` marks a release that was built and handed over.
- A dated name in words (`before-...-YYYY-MM-DD`, `ui-phase-1`) marks a
  baseline or a freeze that is not a release.

## Returning to a tag

To look at the code as it was, without changing main:

```powershell
git switch --detach before-customer-requirements-2026-10-12
git switch main                      # to come back
```

To see everything that changed since a tag:

```powershell
git log --oneline before-customer-requirements-2026-10-12..main
```
