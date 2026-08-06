# UX Standards

## Interaction principles

- **Minimal clicks.** Prefer inline expand/collapse and in-place edits over opening additional dialogs or navigating away.
- **Data-centric.** Every screen should maximize visible grid rows / form fields; chrome (toolbars, banners) should be as slim as reasonably possible.
- **Consistent verbs.** Buttons always read the same way for the same action across every module: **Save & Close**, **Save & New**, **Cancel**, **Close** (view mode), **Discard changes** (confirmation).

## Validation behavior

1. On save, invalid fields are highlighted inline (existing `TextFormField`/`FilterChip`/`SwitchListTile` validators).
2. Any section containing an invalid field is force-expanded (`EnterpriseSection.errorCount > 0`) so the user never has to hunt for it.
3. A top-of-form `EnterpriseValidationSummary` lists every error plus any server-side/API error message.
4. The form **never closes** on a failed save — entered data is preserved (`_controllers`/`_booleans`/`_selections`/`_addressLists`/`_documentLists` state persists across a failed `_save()`).

## Unsaved changes

- Every field mutation marks the dialog `_dirty` (via a `TextEditingController` listener for text fields, or directly in `setState` for booleans/selections/lists).
- Closing (via the header close icon, Cancel, or `Esc`) while dirty shows `EnterpriseConfirmationDialog.confirmDiscard()`. Users must explicitly confirm "Discard changes" or the dialog stays open.
- A successful save clears the dirty flag before closing (or, for **Save & New**, resets it after clearing the form).

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+S` | Save (Save & Close) |
| `Esc` | Close/Cancel (with unsaved-changes confirmation if dirty) |

These are wired once in `CrudWorkspaceDialog` via `CallbackShortcuts` and apply to every resource using the shared framework — no per-module wiring needed.

## Empty/loading/error states

- Options-driven fields (roles, firms) show a spinner while loading and a clear inline error if the options request fails — this pattern is unchanged and should be preserved by any future extension.
- Composite editors (`EnterpriseAddressEditor`, `EnterpriseDocumentSection`) show "No addresses/documents on file." in read-only mode when empty, instead of an empty blank area.
