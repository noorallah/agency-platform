/// Enterprise Design System — form/data-entry component kit.
///
/// This file contains the reusable "Enterprise*" widgets that every module's
/// data-entry surface should build on top of (see
/// `desktop/docs/DESKTOP_UI_FRAMEWORK.md`). These are intentionally generic:
/// they know nothing about Users, Customers, or any specific module — they
/// only encode the shared enterprise visual language (spacing, section
/// chrome, validation, and action patterns).
///
/// Reference implementation: [CrudWorkspaceDialog] in
/// `resource_management_page.dart`, and the User Management screen wired up
/// in `desktop_shell.dart`.
library;

import 'package:flutter/material.dart';

import 'workspace_components.dart';

/// A single collapsible group of related fields inside an enterprise form.
///
/// Replaces horizontal tab/segmented-button switching: every section is
/// always present in the scroll, and the user expands only the ones they
/// need. This keeps validation errors visible (an invalid field never hides
/// behind an unselected tab) and lets users scan the whole record at a
/// glance, matching the collapsible-section standard from
/// `DESKTOP_UI_FRAMEWORK.md`.
class EnterpriseSection extends StatelessWidget {
  const EnterpriseSection({
    super.key,
    required this.title,
    required this.children,
    this.subtitle,
    this.icon,
    this.initiallyExpanded = true,
    this.errorCount = 0,
    this.readOnly = false,
  });

  /// Section heading, e.g. "General Information", "Address".
  final String title;

  /// Optional short description shown under the title.
  final String? subtitle;

  /// Optional leading icon for quick visual scanning.
  final IconData? icon;

  /// Field widgets rendered inside the section body when expanded.
  final List<Widget> children;

  /// Whether the section starts expanded. Sections with errors are forced
  /// open regardless of this flag.
  final bool initiallyExpanded;

  /// Number of invalid fields currently inside this section, surfaced as a
  /// badge next to the title.
  final int errorCount;

  /// Marks a purely informational/audit section (adds a "Read only" tag).
  final bool readOnly;

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      clipBehavior: Clip.antiAlias,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: BorderSide(color: colors.outlineVariant),
      ),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          initiallyExpanded: initiallyExpanded || errorCount > 0,
          tilePadding: const EdgeInsets.symmetric(horizontal: 16),
          childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          leading: icon == null ? null : Icon(icon, size: 20),
          title: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Flexible(
                child: Text(title, style: Theme.of(context).textTheme.titleSmall),
              ),
              if (readOnly) ...[
                const SizedBox(width: 8),
                const StatusBadge(label: 'Read only'),
              ],
              if (errorCount > 0) ...[
                const SizedBox(width: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: colors.errorContainer,
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    errorCount == 1 ? '1 error' : '$errorCount errors',
                    style: TextStyle(
                      color: colors.onErrorContainer,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ],
          ),
          subtitle: subtitle == null ? null : Text(subtitle!),
          children: [
            Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
          ],
        ),
      ),
    );
  }
}

/// Summary banner listing every current validation failure, grouped so the
/// user can see everything wrong with the form without hunting through
/// collapsed sections. Placed once at the top of the enterprise form body.
class EnterpriseValidationSummary extends StatelessWidget {
  const EnterpriseValidationSummary({
    super.key,
    this.message,
    this.fieldErrors = const {},
  });

  /// Top-level/server error message (e.g. a save failure unrelated to a
  /// specific field).
  final String? message;

  /// Map of field label -> error message.
  final Map<String, String> fieldErrors;

  @override
  Widget build(BuildContext context) {
    if (message == null && fieldErrors.isEmpty) return const SizedBox.shrink();
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: colors.errorContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(children: [
            Icon(Icons.error_outline, color: colors.onErrorContainer, size: 18),
            const SizedBox(width: 8),
            Text(
              'Please review the following before saving',
              style: TextStyle(
                color: colors.onErrorContainer,
                fontWeight: FontWeight.w600,
              ),
            ),
          ]),
          if (message != null) ...[
            const SizedBox(height: 8),
            Text(message!, style: TextStyle(color: colors.onErrorContainer)),
          ],
          for (final MapEntry<String, String> entry in fieldErrors.entries) ...[
            const SizedBox(height: 4),
            Text(
              '•  ${entry.key}: ${entry.value}',
              style: TextStyle(color: colors.onErrorContainer),
            ),
          ],
        ],
      ),
    );
  }
}

/// Standard footer action row for every enterprise create/edit form:
/// Cancel, Save & New (create mode only), Save & Close.
///
/// Keeping this identical across modules means users build one muscle memory
/// for finishing a record, per the Form Standards in
/// `DESKTOP_UI_FRAMEWORK.md`.
class EnterpriseActionBar extends StatelessWidget {
  const EnterpriseActionBar({
    super.key,
    required this.saving,
    required this.onCancel,
    required this.onSaveAndClose,
    this.onSaveAndNew,
    this.readOnly = false,
    this.cancelLabel = 'Cancel',
  });

  final bool saving;
  final bool readOnly;
  final VoidCallback? onCancel;
  final VoidCallback? onSaveAndClose;

  /// When non-null, shows a secondary "Save & New" button (typically only
  /// offered in create mode).
  final VoidCallback? onSaveAndNew;
  final String cancelLabel;

  @override
  Widget build(BuildContext context) => Material(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              OutlinedButton(
                onPressed: onCancel,
                child: Text(readOnly ? 'Close' : cancelLabel),
              ),
              if (!readOnly) ...[
                if (onSaveAndNew != null) ...[
                  const SizedBox(width: 12),
                  OutlinedButton.icon(
                    onPressed: onSaveAndNew,
                    icon: const Icon(Icons.add_circle_outline),
                    label: const Text('Save & New'),
                  ),
                ],
                const SizedBox(width: 12),
                FilledButton.icon(
                  onPressed: onSaveAndClose,
                  icon: saving
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.save_outlined),
                  label: Text(saving ? 'Saving...' : 'Save & Close'),
                ),
              ],
            ],
          ),
        ),
      );
}

/// Read-only key/value grid for audit trail data (created/modified by & on,
/// last login, etc.). Never editable regardless of form mode.
class EnterpriseAuditSection extends StatelessWidget {
  const EnterpriseAuditSection({super.key, required this.entries});

  final Map<String, String?> entries;

  @override
  Widget build(BuildContext context) {
    final TextTheme text = Theme.of(context).textTheme;
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Wrap(
      spacing: 24,
      runSpacing: 12,
      children: [
        for (final MapEntry<String, String?> entry in entries.entries)
          SizedBox(
            width: 240,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(entry.key,
                    style: text.labelMedium?.copyWith(color: colors.onSurfaceVariant)),
                const SizedBox(height: 2),
                Text(entry.value?.trim().isNotEmpty == true ? entry.value! : '—',
                    style: text.bodyMedium),
              ],
            ),
          ),
      ],
    );
  }
}

/// Confirmation dialog shown when a user tries to close a form with unsaved
/// changes. Thin, opinionated wrapper over [ConfirmationDialog].
class EnterpriseConfirmationDialog {
  const EnterpriseConfirmationDialog._();

  static Future<bool> confirmDiscard(BuildContext context) async {
    final bool? result = await showDialog<bool>(
      context: context,
      builder: (_) => ConfirmationDialog(
        title: 'Discard unsaved changes?',
        message: 'You have unsaved changes. Closing now will discard them.',
        confirmLabel: 'Discard changes',
        onCancel: () => Navigator.pop(context, false),
        onConfirm: () => Navigator.pop(context, true),
      ),
    );
    return result ?? false;
  }
}

/// A single postal address entry used by [EnterpriseAddressEditor].
///
/// This is the canonical, reusable address record shape for the Enterprise
/// Design System. Modules that currently hand-roll their own address drafts
/// (Customers, Vendors) are expected to migrate to this shape in a future
/// sprint rather than each maintaining their own model.
class AddressRecord {
  AddressRecord({
    required this.addressType,
    this.line1 = '',
    this.line2 = '',
    this.city = '',
    this.state = '',
    this.country = '',
    this.postalCode = '',
    this.isPrimary = false,
  });

  String addressType;
  String line1;
  String line2;
  String city;
  String state;
  String country;
  String postalCode;
  bool isPrimary;

  factory AddressRecord.fromJson(Map<String, dynamic> json) => AddressRecord(
        addressType: json['address_type']?.toString() ?? 'Other',
        line1: json['line1']?.toString() ?? '',
        line2: json['line2']?.toString() ?? '',
        city: json['city']?.toString() ?? '',
        state: json['state']?.toString() ?? '',
        country: json['country']?.toString() ?? '',
        postalCode: json['postal_code']?.toString() ?? '',
        isPrimary: json['is_primary'] as bool? ?? false,
      );

  Map<String, dynamic> toJson() => {
        'address_type': addressType,
        'line1': line1,
        'line2': line2,
        'city': city,
        'state': state,
        'country': country,
        'postal_code': postalCode,
        'is_primary': isPrimary,
      };
}

/// Standard address types offered by [EnterpriseAddressEditor].
const List<String> kEnterpriseAddressTypes = [
  'Permanent',
  'Current',
  'Office',
  'Temporary',
  'Other',
];

/// Reusable multi-address editor: the Enterprise Address Framework.
///
/// Renders a list of [AddressRecord] cards (add/edit/remove), each with a
/// type selector and the standard postal fields. Used today by User
/// Management; intended to become the shared address widget for every other
/// module once migrated.
class EnterpriseAddressEditor extends StatelessWidget {
  const EnterpriseAddressEditor({
    super.key,
    required this.addresses,
    required this.onChanged,
    this.readOnly = false,
  });

  final List<AddressRecord> addresses;
  final ValueChanged<List<AddressRecord>> onChanged;
  final bool readOnly;

  void _update(int index, AddressRecord Function(AddressRecord) mutate) {
    final List<AddressRecord> next = [...addresses];
    next[index] = mutate(next[index]);
    onChanged(next);
  }

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (int index = 0; index < addresses.length; index++)
            _addressCard(context, index, addresses[index]),
          if (!readOnly)
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: () => onChanged([
                  ...addresses,
                  AddressRecord(addressType: kEnterpriseAddressTypes.first),
                ]),
                icon: const Icon(Icons.add),
                label: const Text('Add address'),
              ),
            ),
          if (addresses.isEmpty && readOnly)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Text('No addresses on file.'),
            ),
        ],
      );

  Widget _addressCard(BuildContext context, int index, AddressRecord address) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        border: Border.all(color: colors.outlineVariant),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            Expanded(
              child: DropdownButtonFormField<String>(
                initialValue: kEnterpriseAddressTypes.contains(address.addressType)
                    ? address.addressType
                    : kEnterpriseAddressTypes.last,
                decoration: const InputDecoration(labelText: 'Address type'),
                items: [
                  for (final String type in kEnterpriseAddressTypes)
                    DropdownMenuItem(value: type, child: Text(type)),
                ],
                onChanged: readOnly
                    ? null
                    : (value) => _update(
                        index, (a) => a..addressType = value ?? a.addressType),
              ),
            ),
            const SizedBox(width: 12),
            FilterChip(
              label: const Text('Primary'),
              selected: address.isPrimary,
              onSelected: readOnly
                  ? null
                  : (selected) => _update(index, (a) => a..isPrimary = selected),
            ),
            if (!readOnly) ...[
              const SizedBox(width: 4),
              IconButton(
                tooltip: 'Remove address',
                icon: const Icon(Icons.delete_outline),
                onPressed: () => onChanged([...addresses]..removeAt(index)),
              ),
            ],
          ]),
          const SizedBox(height: 8),
          TextFormField(
            initialValue: address.line1,
            readOnly: readOnly,
            decoration: const InputDecoration(labelText: 'Address line 1'),
            onChanged: (value) => _update(index, (a) => a..line1 = value),
          ),
          const SizedBox(height: 8),
          TextFormField(
            initialValue: address.line2,
            readOnly: readOnly,
            decoration: const InputDecoration(labelText: 'Address line 2'),
            onChanged: (value) => _update(index, (a) => a..line2 = value),
          ),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(
              child: TextFormField(
                initialValue: address.city,
                readOnly: readOnly,
                decoration: const InputDecoration(labelText: 'City'),
                onChanged: (value) => _update(index, (a) => a..city = value),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextFormField(
                initialValue: address.state,
                readOnly: readOnly,
                decoration: const InputDecoration(labelText: 'State'),
                onChanged: (value) => _update(index, (a) => a..state = value),
              ),
            ),
          ]),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(
              child: TextFormField(
                initialValue: address.country,
                readOnly: readOnly,
                decoration: const InputDecoration(labelText: 'Country'),
                onChanged: (value) => _update(index, (a) => a..country = value),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextFormField(
                initialValue: address.postalCode,
                readOnly: readOnly,
                decoration: const InputDecoration(labelText: 'Postal code'),
                onChanged: (value) => _update(index, (a) => a..postalCode = value),
              ),
            ),
          ]),
        ],
      ),
    );
  }
}

/// Metadata for a single supporting document, used by
/// [EnterpriseDocumentSection]. Stores a reference/label only — actual file
/// upload/storage is out of scope for this sprint (no shared attachment
/// backend exists yet); this establishes the canonical shape other modules
/// should converge on.
class DocumentRecord {
  DocumentRecord({
    required this.documentType,
    this.reference = '',
    this.notes = '',
  });

  String documentType;
  String reference;
  String notes;

  factory DocumentRecord.fromJson(Map<String, dynamic> json) => DocumentRecord(
        documentType: json['document_type']?.toString() ?? 'Other',
        reference: json['reference']?.toString() ?? '',
        notes: json['notes']?.toString() ?? '',
      );

  Map<String, dynamic> toJson() => {
        'document_type': documentType,
        'reference': reference,
        'notes': notes,
      };
}

/// Standard document types offered by [EnterpriseDocumentSection].
const List<String> kEnterpriseDocumentTypes = [
  'Government ID',
  'Passport',
  'Driving License',
  'Employee ID',
  'Other',
];

/// Reusable document metadata list editor: the Enterprise Document
/// Framework reference implementation. Mirrors the read-only
/// [AttachmentPanel] visual language but supports add/edit of metadata rows.
class EnterpriseDocumentSection extends StatelessWidget {
  const EnterpriseDocumentSection({
    super.key,
    required this.documents,
    required this.onChanged,
    this.readOnly = false,
  });

  final List<DocumentRecord> documents;
  final ValueChanged<List<DocumentRecord>> onChanged;
  final bool readOnly;

  void _update(int index, DocumentRecord Function(DocumentRecord) mutate) {
    final List<DocumentRecord> next = [...documents];
    next[index] = mutate(next[index]);
    onChanged(next);
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (int index = 0; index < documents.length; index++)
          Container(
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              border: Border.all(color: colors.outlineVariant),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(Icons.description_outlined, color: colors.onSurfaceVariant),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    DropdownButtonFormField<String>(
                      initialValue:
                          kEnterpriseDocumentTypes.contains(documents[index].documentType)
                              ? documents[index].documentType
                              : kEnterpriseDocumentTypes.last,
                      decoration: const InputDecoration(labelText: 'Document type'),
                      items: [
                        for (final String type in kEnterpriseDocumentTypes)
                          DropdownMenuItem(value: type, child: Text(type)),
                      ],
                      onChanged: readOnly
                          ? null
                          : (value) => _update(index,
                              (d) => d..documentType = value ?? d.documentType),
                    ),
                    const SizedBox(height: 8),
                    TextFormField(
                      initialValue: documents[index].reference,
                      readOnly: readOnly,
                      decoration: const InputDecoration(
                          labelText: 'Reference / number',
                          helperText: 'Document number or file reference'),
                      onChanged: (value) =>
                          _update(index, (d) => d..reference = value),
                    ),
                    const SizedBox(height: 8),
                    TextFormField(
                      initialValue: documents[index].notes,
                      readOnly: readOnly,
                      decoration: const InputDecoration(labelText: 'Notes'),
                      onChanged: (value) => _update(index, (d) => d..notes = value),
                    ),
                  ],
                ),
              ),
              if (!readOnly)
                IconButton(
                  tooltip: 'Remove document',
                  icon: const Icon(Icons.delete_outline),
                  onPressed: () => onChanged([...documents]..removeAt(index)),
                ),
            ]),
          ),
        if (!readOnly)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => onChanged([
                ...documents,
                DocumentRecord(documentType: kEnterpriseDocumentTypes.first),
              ]),
              icon: const Icon(Icons.add),
              label: const Text('Add document'),
            ),
          ),
        if (documents.isEmpty && readOnly)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: Text('No documents on file.'),
          ),
      ],
    );
  }
}
