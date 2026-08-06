# Reusable Widget Documentation

API reference for `desktop/lib/ui/workspace/enterprise_form_kit.dart`.

## `EnterpriseSection`

```dart
EnterpriseSection({
  required String title,
  required List<Widget> children,
  String? subtitle,
  IconData? icon,
  bool initiallyExpanded = true,
  int errorCount = 0,
  bool readOnly = false,
})
```

Renders a card with an `ExpansionTile` header (title, optional subtitle/icon, "Read only" badge, error-count badge) and a stretched column of `children` when expanded. Force-expands when `errorCount > 0`.

## `EnterpriseValidationSummary`

```dart
EnterpriseValidationSummary({ String? message, Map<String, String> fieldErrors = const {} })
```

Renders nothing when both `message` and `fieldErrors` are empty. Otherwise shows an error-colored banner: a heading, the top-level `message` (if any), and one bullet per `fieldErrors` entry (`"label: message"`).

## `EnterpriseActionBar`

```dart
EnterpriseActionBar({
  required bool saving,
  required VoidCallback? onCancel,
  required VoidCallback? onSaveAndClose,
  VoidCallback? onSaveAndNew,
  bool readOnly = false,
  String cancelLabel = 'Cancel',
})
```

Cancel/Close button always shown. When `readOnly` is false: an optional "Save & New" button (only if `onSaveAndNew != null`) and a primary "Save & Close" button (spinner + "Saving..." while `saving`).

## `EnterpriseAuditSection`

```dart
EnterpriseAuditSection({ required Map<String, String?> entries })
```

Wraps `entries` into a responsive `Wrap` of label/value pairs (240px columns), showing `—` for blank values. Used for stand-alone read-only audit displays.

## `EnterpriseConfirmationDialog`

```dart
static Future<bool> confirmDiscard(BuildContext context)
```

Shows a "Discard unsaved changes?" `ConfirmationDialog` and resolves to whether the user confirmed discarding.

## `AddressRecord` / `EnterpriseAddressEditor`

```dart
class AddressRecord {
  String addressType, line1, line2, city, state, country, postalCode;
  bool isPrimary;
  factory AddressRecord.fromJson(Map<String, dynamic> json);
  Map<String, dynamic> toJson();
}

EnterpriseAddressEditor({
  required List<AddressRecord> addresses,
  required ValueChanged<List<AddressRecord>> onChanged,
  bool readOnly = false,
})
```

Renders one card per address (type dropdown from `kEnterpriseAddressTypes`, primary chip, delete button, line1/line2/city/state/country/postal code) plus an "Add address" action when not read-only. This is the canonical **Enterprise Address Framework** — the shape other modules should converge on instead of maintaining their own address drafts.

## `DocumentRecord` / `EnterpriseDocumentSection`

```dart
class DocumentRecord {
  String documentType, reference, notes;
  factory DocumentRecord.fromJson(Map<String, dynamic> json);
  Map<String, dynamic> toJson();
}

EnterpriseDocumentSection({
  required List<DocumentRecord> documents,
  required ValueChanged<List<DocumentRecord>> onChanged,
  bool readOnly = false,
})
```

Renders one card per document (type dropdown from `kEnterpriseDocumentTypes`, reference/number, notes, delete button) plus an "Add document" action. Metadata only — this sprint does not add file upload/storage; it establishes the reusable shape (**Enterprise Document Framework**) for a future storage integration.

## Extension points in `resource_management_page.dart`

- `FieldKind` enum (`text`, `date`, `addressList`, `documentList`) and the new `FieldSpec.kind`/`sectionIcon`/`alwaysReadOnly` properties let any `ResourceDefinition` opt into these composite widgets without touching `CrudWorkspaceDialog` itself.
- `_decodeRecords<R>` in `_CrudWorkspaceDialogState` is the shared JSON → record-list decoder used for both address and document lists.
