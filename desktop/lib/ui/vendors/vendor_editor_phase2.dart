part of 'vendor_management_page.dart';

/// The vendor record in the phase 2 app: a full-page tab, as the customer
/// record is (approved by the owner 2026-09-26). Every section is one scroll
/// -- General, Contacts, Addresses, Banking, Tax, Notes, Custom fields --
/// reached from a strip of links, and a side panel with what purchasing and
/// accounts need at a glance: GST standing, who to call, where to pay. The
/// dialog's fields and payload are reused unchanged; the list saves what it
/// is handed back, as before.
extension _Phase2VendorForm on _VendorEditorDialogState {
  static const List<String> _sectionNames = [
    'General',
    'Contacts',
    'Addresses',
    'Banking',
    'Tax',
    'Notes',
    'Custom fields',
  ];

  void _submit() {
    final String? customField = _customFields.validate();
    if (customField != null) {
      NotificationService.show(context, customField,
          kind: AppNotificationKind.warning);
      return;
    }
    Navigator.pop(context, _payload());
  }

  Widget _phase2Page(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final Vendor? vendor = widget.vendor;
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.escape): () =>
            Navigator.pop(context),
        const SingleActivator(LogicalKeyboardKey.keyS, control: true): _submit,
      },
      child: Focus(
        autofocus: true,
        child: Material(
          color: scheme.surface,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DocumentPageBand(
                title: vendor == null
                    ? 'New vendor'
                    : vendor.displayName.isEmpty
                        ? vendor.name
                        : vendor.displayName,
                chips: [
                  if (_code.text.trim().isNotEmpty) _code.text.trim(),
                  _statusWords(_status),
                ],
                hint: 'Ctrl+S save  ·  Esc close',
                actions: [
                  TextButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('Cancel'),
                  ),
                  FilledButton(
                    key: const ValueKey('vendor-save'),
                    onPressed: _submit,
                    child: const Text('Save vendor'),
                  ),
                ],
              ),
              Expanded(
                child: LayoutBuilder(
                  builder: (context, constraints) => Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            _sectionStrip(context),
                            Expanded(child: _body(context)),
                          ],
                        ),
                      ),
                      if (constraints.maxWidth >= DocumentSidePanel.showFrom)
                        _sidePanel(),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _statusWords(String status) => switch (status) {
        'ACTIVE' => 'Active',
        'INACTIVE' => 'Inactive',
        'DRAFT' => 'Draft',
        'ARCHIVED' => 'Archived',
        _ => status,
      };

  Widget _sectionStrip(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLowest,
        border: Border(bottom: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(children: [
            for (final String section in _sectionNames)
              TextButton(
                key: ValueKey<String>('vendor-section-$section'),
                onPressed: () {
                  final BuildContext? target =
                      _sectionKeys[section]?.currentContext;
                  if (target != null) {
                    unawaited(Scrollable.ensureVisible(
                      target,
                      duration: const Duration(milliseconds: 200),
                    ));
                  }
                },
                child: Text(section),
              ),
          ]),
        ),
      ),
    );
  }

  Widget _heading(BuildContext context, String section, String note) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      key: _sectionKeys[section],
      padding: const EdgeInsets.fromLTRB(0, 20, 0, 4),
      child: Row(children: [
        Text(
          section.toUpperCase(),
          style: theme.textTheme.labelMedium?.copyWith(
            fontWeight: FontWeight.w700,
            letterSpacing: .6,
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(width: 10),
        Flexible(
          child: Text(
            note,
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ),
      ]),
    );
  }

  /// The dialog's own sections, drawn dense, one after another.
  Widget _body(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Theme(
      data: theme.copyWith(
        inputDecorationTheme: theme.inputDecorationTheme.copyWith(
          isDense: true,
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
        ),
      ),
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _heading(context, 'General', 'who they are and how to reach them'),
            _generalTab(),
            _heading(context, 'Contacts', 'who to call there'),
            _contactsTab(),
            _heading(context, 'Addresses', 'where they are'),
            _addressTab(),
            _heading(context, 'Banking', 'where they are paid'),
            _bankTab(),
            _heading(context, 'Tax', 'registrations and licences'),
            _taxTab(),
            _heading(context, 'Notes', ''),
            _notesTab(),
            _heading(context, 'Custom fields', ''),
            CustomFieldsSection(controller: _customFields, noun: 'vendors'),
          ],
        ),
      ),
    );
  }

  Widget _sidePanel() {
    final Vendor? vendor = widget.vendor;
    String first<T>(
        List<T> rows, bool Function(T) primary, String Function(T) text) {
      for (final T row in rows) {
        if (primary(row)) return text(row);
      }
      return rows.isEmpty ? '' : text(rows.first);
    }

    final String contact = first<_EditableContact>(
      _contacts,
      (row) => row.isPrimary,
      (row) => [row.name.text.trim(), row.mobile.text.trim()]
          .where((part) => part.isNotEmpty)
          .join(' · '),
    );
    final String bank = first<_EditableBank>(
      _banks,
      (row) => row.isPrimary,
      (row) => [row.bankName.text.trim(), row.ifsc.text.trim()]
          .where((part) => part.isNotEmpty)
          .join(' · '),
    );
    return DocumentSidePanel(children: [
      const DocumentSideHeading('At a glance'),
      DocumentSidePair(
        'GST',
        _gstin.text.trim().isNotEmpty
            ? _gstin.text.trim()
            : _gstRegistration
                ? 'registered, no GSTIN yet'
                : 'unregistered',
      ),
      const DocumentSideNote(
        'the GSTIN\'s state decides whether their bills charge IGST or CGST '
        'and SGST',
      ),
      DocumentSidePair('Contact', contact.isEmpty ? '—' : contact),
      DocumentSidePair('Pay to', bank.isEmpty ? '—' : bank),
      if (vendor != null) ...[
        const DocumentSideHeading('Record'),
        DocumentSidePair('Created', _day(vendor.createdAt)),
        DocumentSidePair('Last changed', _day(vendor.updatedAt)),
      ] else
        const DocumentSideNote(
          'a code and a name are all it needs to be saved; the rest can be '
          'added now or later',
        ),
    ]);
  }

  String _day(String value) {
    final DateTime? day = DateTime.tryParse(value)?.toLocal();
    return day == null ? (value.isEmpty ? '—' : value) : documentDate(day);
  }
}
