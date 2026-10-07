part of 'customer_management_page.dart';

/// The customer form in the phase 2 app: a full-page tab (design 4.8 and
/// section 9, item 1) rather than a dialog of seven tabs. Every part of the
/// record is one scroll -- who they are, money, addresses, contacts, custom
/// fields, rounds -- with a strip of section links at the top, and a side
/// panel with what the firm needs to know at a glance: what they owe against
/// their limit and who last touched the record. The pattern is Business
/// Central's card page and Zoho's customer page. The dialog's fields,
/// validation, payload and save are reused unchanged.
extension _Phase2CustomerForm on _CustomerWorkspaceDialogState {
  static const List<String> _sections = [
    'General',
    'Money',
    'Addresses',
    'Contacts',
    'Custom fields',
    'Rounds',
    'Licences',
    'Opening bills',
    'Bank accounts',
    'Files',
  ];

  Widget _phase2Page(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final Customer? customer = widget.customer;
    final String code = _fields['code']!.text.trim();
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.escape): () =>
            unawaited(_close()),
        const SingleActivator(LogicalKeyboardKey.keyS, control: true): () =>
            unawaited(_save()),
      },
      // A scope, not a plain Focus: after a click outside a text box the
      // focus falls to the nearest scope, which was above these
      // shortcuts, so Esc and Ctrl+S did nothing (SC-SO-029).
      child: FocusScope(
        autofocus: true,
        child: Material(
          color: scheme.surface,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DocumentPageBand(
                title: widget.mode == CustomerDialogMode.create
                    ? 'New customer'
                    : customer!.displayName.isEmpty
                        ? customer.name
                        : customer.displayName,
                chips: [
                  if (code.isNotEmpty) code,
                  _statusWords(_status),
                  if (customer?.isDeleted ?? false) 'Deleted',
                ],
                hint: _readOnly ? '' : 'Ctrl+S save  ·  Esc close',
                actions: [
                  TextButton(
                    onPressed: _saving ? null : () => unawaited(_close()),
                    child: Text(_readOnly ? 'Close' : 'Cancel'),
                  ),
                  if (!_readOnly)
                    FilledButton(
                      key: const ValueKey('customer-save'),
                      onPressed: _saving ? null : () => unawaited(_save()),
                      child: Text(_saving ? 'Saving…' : 'Save customer'),
                    ),
                ],
              ),
              if (widget.customer?.status == 'PENDING')
                Container(
                  key: const ValueKey('customer-pending-banner'),
                  margin: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: scheme.secondaryContainer,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.hourglass_top_outlined,
                          size: 18, color: scheme.onSecondaryContainer),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Waiting for office approval — orders allowed, '
                          'billing blocked',
                          style: theme.textTheme.bodyMedium?.copyWith(
                              color: scheme.onSecondaryContainer),
                        ),
                      ),
                      if (widget.onApprove != null) ...[
                        const SizedBox(width: 8),
                        FilledButton(
                          key: const ValueKey('customer-approve'),
                          onPressed:
                              _saving ? null : () => unawaited(_approve()),
                          child: const Text('Approve'),
                        ),
                      ],
                    ],
                  ),
                ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                  child: MaterialBanner(
                    contentTextStyle: theme.textTheme.bodyMedium,
                    content: Text(_error!),
                    actions: [
                      TextButton(
                        onPressed: () => _setState(() => _error = null),
                        child: const Text('Dismiss'),
                      ),
                    ],
                  ),
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
                        _sidePanel(context),
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
        'ON_HOLD' => 'On hold',
        'PENDING' => 'Pending approval',
        _ => status,
      };

  bool _shows(String section) => switch (section) {
        'Custom fields' => _customFields != null,
        'Licences' => widget.loadLicences != null,
        'Opening bills' => widget.loadOpeningBills != null,
        // A new customer is told to save first; an existing one sees them
        // only when the caller supplied a loader.
        'Bank accounts' =>
          widget.loadBankAccounts != null || widget.customer == null,
        'Files' => widget.loadFiles != null || widget.customer == null,
        _ => true,
      };

  Widget _sectionStrip(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
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
            for (final String section in _sections)
              if (_shows(section))
                TextButton(
                  key: ValueKey<String>('customer-section-$section'),
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

  Widget _heading(BuildContext context, String section, {String note = ''}) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      key: _sectionKeys[section],
      padding: const EdgeInsets.fromLTRB(0, 20, 0, 8),
      child: Row(children: [
        Text(
          section.toUpperCase(),
          style: theme.textTheme.labelMedium?.copyWith(
            fontWeight: FontWeight.w700,
            letterSpacing: .6,
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        if (note.isNotEmpty) ...[
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
        ],
      ]),
    );
  }

  /// The dialog's own fields, drawn dense, as the document screens are.
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
      child: _scroll(context),
    );
  }

  Widget _scroll(BuildContext context) => SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _heading(context, 'General'),
            _generalTab(),
            _heading(
              context,
              'Money',
              note: 'group, credit, standing discount and terms',
            ),
            _financialTab(),
            // The address and contact sections carry their own heading with
            // the Add button beside it.
            KeyedSubtree(
              key: _sectionKeys['Addresses'],
              child: Padding(
                padding: const EdgeInsets.only(top: 20),
                child: _addressTab(),
              ),
            ),
            KeyedSubtree(
              key: _sectionKeys['Contacts'],
              child: Padding(
                padding: const EdgeInsets.only(top: 20),
                child: _contactTab(),
              ),
            ),
            if (_customFields != null) ...[
              _heading(context, 'Custom fields'),
              CustomFieldsSection(
                controller: _customFields,
                noun: 'customers',
                readOnly: _readOnly,
                onChanged: () => _setState(() => _dirty = true),
              ),
            ],
            _heading(context, 'Rounds', note: 'the routes that call this shop'),
            _routesTab(),
            if (widget.loadLicences != null) ...[
              KeyedSubtree(
                key: _sectionKeys['Licences'],
                child: Padding(
                  padding: const EdgeInsets.only(top: 20),
                  child: _licencesTab(),
                ),
              ),
            ],
            if (widget.loadOpeningBills != null) ...[
              _heading(
                context,
                'Opening bills',
                note: 'what they owed on the firm\'s first day here, bill by '
                    'bill',
              ),
              _openingBillsTab(),
            ],
            if (widget.loadBankAccounts != null || widget.customer == null) ...[
              _heading(
                context,
                'Bank accounts',
                note: 'where they pay from and where refunds go',
              ),
              if (widget.loadBankAccounts == null)
                const CustomerRecordsAfterSave(what: 'Bank accounts')
              else
                CustomerBankAccountsSection(
                  load: widget.loadBankAccounts!,
                  onSave: widget.onSaveBankAccounts,
                ),
            ],
            if (widget.loadFiles != null || widget.customer == null) ...[
              _heading(
                context,
                'Files',
                note: 'agreements, licences and photos kept with the customer',
              ),
              if (widget.loadFiles == null)
                const CustomerRecordsAfterSave(what: 'Files')
              else
                CustomerFilesSection(
                  load: widget.loadFiles!,
                  onAdd: widget.onAddFiles,
                  onRemove: widget.onRemoveFile,
                  pickFiles: widget.pickFiles,
                ),
            ],
          ],
        ),
      );

  Widget _sidePanel(BuildContext context) {
    final Customer? customer = widget.customer;
    if (customer == null) {
      return const DocumentSidePanel(children: [
        DocumentSideHeading('New customer'),
        DocumentSideNote(
          'a name is all it needs to be saved; the rest can be '
          'added now or later',
        ),
        DocumentSideNote(
          'a GSTIN decides whether their bills charge IGST or CGST and SGST, '
          'with the state of the billing address',
        ),
      ]);
    }
    final double balance = double.tryParse(customer.currentOutstanding) ?? 0;
    final double limit = double.tryParse(customer.creditLimit) ?? 0;
    return DocumentSidePanel(children: [
      ...documentCustomerLines(context, customer),
      if (limit > 0)
        DocumentSidePair(
          'Credit left',
          indianAmount(limit - balance, full: true),
          bold: true,
          tone:
              limit - balance < 0 ? Theme.of(context).colorScheme.error : null,
        ),
      DocumentSidePair(
        'Pays in',
        customer.paymentTermsDays == 0
            ? 'on delivery'
            : '${customer.paymentTermsDays} days',
      ),
      if (customer.gstNumber.isNotEmpty)
        DocumentSidePair('GSTIN', customer.gstNumber)
      else
        const DocumentSidePair('GSTIN', 'unregistered'),
      const DocumentSideHeading('Record'),
      DocumentSidePair('Created', _auditDay(customer.createdAt)),
      DocumentSidePair('Last changed', _auditDay(customer.updatedAt)),
    ]);
  }

  String _auditDay(String value) {
    final DateTime? day = DateTime.tryParse(value)?.toLocal();
    return day == null ? (value.isEmpty ? '—' : value) : documentDate(day);
  }
}
