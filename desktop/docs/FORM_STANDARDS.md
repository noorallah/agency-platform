# Form Standards

## One shape for Create, Edit, and View

`CrudWorkspaceDialog` renders exactly the same section/field layout in all three `CrudDialogMode`s. Only field behavior changes:

| Mode | Behavior |
|---|---|
| `create` | All non-`editOnly` fields editable; `createOnly` fields (e.g. initial password) appear; footer shows Cancel, **Save & New**, **Save & Close**. |
| `edit` | All non-`createOnly` fields editable except `readOnlyWhenEditing` ones (e.g. email/username); footer shows Cancel, **Save & Close** only. |
| `view` | Every field renders read-only; footer shows only **Close**. |

## Section taxonomy (reference: User Management)

`General Information → Organization → Security → Contact Information → Address → Employment → Documents → Audit Information`

- **General Information** — identity basics: username/email, full name, mobile numbers, profile photo, active status.
- **Organization** — access scoping: firms, primary firm (roles moved to Security since they are an access-control concept).
- **Security** — password, force-password-change, roles, expiry, account-lock clearing.
- **Contact Information** — personal/office email, emergency contact details.
- **Address** — `EnterpriseAddressEditor` bound to a single composite field (see Reusable Widget docs).
- **Employment** — HR-style optional fields (employee code, joining/leaving date, department, designation, reporting manager, employment type, cost center).
- **Documents** — `EnterpriseDocumentSection` metadata list.
- **Audit Information** — read-only: created on, last modified on, last login, failed login attempts.

Future modules should reuse this taxonomy where applicable rather than inventing new section names for the same concepts.

## Field kinds

`FieldSpec.kind` (`FieldKind` enum) selects the control:

- `text` (default) — `TextFormField`, single or multi-line.
- `date` — text field with a calendar picker button; stores `yyyy-MM-dd`.
- `addressList` — renders `EnterpriseAddressEditor`; the field's value is a `List<Map>` (JSON-serializable `AddressRecord`s).
- `documentList` — renders `EnterpriseDocumentSection`; the field's value is a `List<Map>` (JSON-serializable `DocumentRecord`s).

`FieldSpec.alwaysReadOnly = true` renders a static label/value pair (used for Audit Information) regardless of dialog mode — it never becomes editable, even in create/edit.

## Save actions

- **Save & Close** (primary, `FilledButton`) — validates, calls `onSave`, and on success closes the dialog.
- **Save & New** (secondary, create mode only) — validates, calls `onSave`, and on success clears all fields back to their create-mode defaults **without** closing the dialog, so the user can immediately enter the next record. A success toast confirms the save.
- **Cancel / Close** — closes without saving; prompts for confirmation if the form is dirty.

## Validation & error handling

See `UX_STANDARDS.md` for the full behavior contract (form stays open on failure, sections auto-expand, summary banner, dirty tracking).
