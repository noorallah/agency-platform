part of 'customer_debit_note_page.dart';

/// The debit note screen in the phase 2 app: the documents' one-screen
/// layout (wireframe view 7) for more charged on a sale already invoiced --
/// the invoice being added to, **every** one of its lines with the extra
/// charged on each before tax, and the tax going on each at the rate its
/// invoice line charged, priced as it is typed by
/// `POST /customer-debit-notes/preview`.
/// The dialog's state and create are reused; it can now debit several lines
/// of one invoice on one note.
extension _Phase2CustomerDebitNote on _CustomerDebitNoteDialogState {
  static const List<DocumentColumn> _columns = [
    DocumentColumn('#', 28),
    DocumentColumn('Product', 0),
    DocumentColumn('Billed', 66, numeric: true),
    DocumentColumn('Rate', 84, numeric: true),
    DocumentColumn('Line value', 96, numeric: true),
    DocumentColumn('Charge', 96, numeric: true),
    DocumentColumn('GST', 52, numeric: true),
    DocumentColumn('Tax added', 88, numeric: true),
    DocumentColumn('Total', 100, numeric: true),
  ];

  static const List<(String, String)> _reasons = [
    ('PRICE_INCREASE', 'Price increase'),
    ('SHORT_BILLED', 'Short billed'),
    ('ADDITIONAL_CHARGES', 'Additional charges'),
    ('OTHER', 'Other'),
  ];

  Widget _phase2Page(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_invoices.isEmpty) {
      return StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'No approved invoice to debit',
        message: _error ??
            'A debit note always names the supply it adds to, because '
                'only that line knows the rate its tax was charged at.',
      );
    }
    final String number = _preview?.debitNoteNumber ?? '';
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.escape): () {
          if (!_saving) leaveDocument(context, result: false);
        },
        const SingleActivator(LogicalKeyboardKey.keyS, control: true): () {
          if (!_saving) unawaited(_phase2Save());
        },
      },
      child: Focus(
        autofocus: true,
        child: Material(
          color: scheme.surface,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DocumentPageBand(
                title: 'New debit note',
                chips: [
                  if (number.isNotEmpty) '$number (new)',
                  if (_selected != null) 'against ${_selected!.number}',
                  'Draft',
                ],
                hint: 'Enter next field  ·  Ctrl+S save',
                actions: [
                  TextButton(
                    onPressed:
                        _saving ? null : () => leaveDocument(context, result: false),
                    child: const Text('Cancel'),
                  ),
                  FilledButton(
                    key: const ValueKey('customer-debit-note-save'),
                    onPressed: _saving ? null : () => unawaited(_phase2Save()),
                    child: Text(_saving ? 'Saving…' : 'Raise debit note'),
                  ),
                ],
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
                            _noteHeader(context),
                            Expanded(
                              child: DocumentLineTable(
                                columns: _columns,
                                rows: [
                                  for (int i = 0;
                                      i < (_selected?.lines.length ?? 0);
                                      i++)
                                    _noteRow(context, i),
                                ],
                              ),
                            ),
                            _noteTotals(),
                          ],
                        ),
                      ),
                      if (constraints.maxWidth >= DocumentSidePanel.showFrom)
                        _noteSidePanel(context),
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

  double _number(String value) => double.tryParse(value.trim()) ?? 0;

  /// The note as the server is sent it: every line with an amount on it.
  Json? _phase2Payload() {
    final ReturnableDocument? invoice = _selected;
    if (invoice == null) return null;
    final List<ReturnableLine> charging = [
      for (final ReturnableLine line in invoice.lines)
        if (_number(_amounts[line.id] ?? '') > 0) line,
    ];
    if (charging.isEmpty) return null;
    return <String, dynamic>{
      'sales_invoice_id': invoice.id,
      'debit_note_date': _CustomerDebitNoteDialogState._today(),
      'reason': _reason,
      if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
      'lines': [
        for (int i = 0; i < charging.length; i++)
          <String, dynamic>{
            'sales_invoice_line_id': charging[i].id,
            'line_number': i + 1,
            // The tax comes off at the rate the invoice line charged, which
            // is why nothing here names one.
            'taxable_amount': _amounts[charging[i].id]!.trim(),
          },
      ],
    };
  }

  Future<void> _phase2Save() async {
    final Json? payload = _phase2Payload();
    if (payload == null) {
      _setState(() => _error = 'Enter what is being charged, before tax, on '
          'at least one line.');
      return;
    }
    _setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.createCustomerDebitNote(payload);
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      _setState(() {
        _error = refusalMessage(error);
        _saving = false;
      });
    }
  }

  Widget _noteHeader(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final ReturnableDocument? invoice = _selected;
    return DocumentHeader(children: [
      DocumentField(
        label: 'Invoice being added to (approved)',
        width: 420,
        below: invoice == null
            ? null
            : Text(
                [
                  if (invoice.customerName.isNotEmpty) invoice.customerName,
                  if (DateTime.tryParse(invoice.documentDate) != null)
                    'billed '
                        '${documentDate(DateTime.parse(invoice.documentDate))}',
                ].join('  ·  '),
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall?.copyWith(
                  fontSize: 11,
                  color: scheme.onSurfaceVariant,
                ),
              ),
        child: DropdownMenu<String>(
          key: const ValueKey('customer-debit-note-invoice'),
          initialSelection: _invoiceId,
          width: 420,
          enabled: !_saving,
          enableFilter: true,
          requestFocusOnTap: true,
          menuHeight: 320,
          inputDecorationTheme: InputDecorationTheme(
            isDense: true,
            filled: true,
            fillColor: scheme.surfaceContainerLowest,
            contentPadding: const EdgeInsets.symmetric(horizontal: 8),
            constraints: const BoxConstraints(maxHeight: 36),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(5)),
          ),
          dropdownMenuEntries: [
            for (final ReturnableDocument row in _invoices)
              DropdownMenuEntry<String>(value: row.id, label: row.label),
          ],
          onSelected: (value) {
            if (value == null || value == _invoiceId) return;
            _setState(() {
              _invoiceId = value;
              _amounts.clear();
              _current = 0;
              _preview = null;
            });
          },
        ),
      ),
      DocumentField(
        label: 'Dated',
        auto: true,
        width: 130,
        child: InputDecorator(
          decoration: documentBoxDecoration(context),
          child: Text(documentDate(DateTime.now())),
        ),
      ),
      DocumentField(
        label: 'Reason',
        width: 200,
        child: DropdownButtonFormField<String>(
          key: const ValueKey('customer-debit-note-reason'),
          isExpanded: true,
          isDense: true,
          initialValue: _reason,
          decoration: documentBoxDecoration(context),
          items: [
            for (final (String code, String label) in _reasons)
              DropdownMenuItem<String>(
                value: code,
                child: Text(label, overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: _saving
              ? null
              : (value) => _setState(() => _reason = value ?? _reason),
        ),
      ),
      DocumentField(
        label: 'Remarks',
        width: 260,
        child: TextFormField(
          controller: _remarks,
          readOnly: _saving,
          decoration: documentBoxDecoration(context),
        ),
      ),
    ]);
  }

  CustomerDebitNoteLineRecord? _pricedLine(String lineId) {
    for (final CustomerDebitNoteLineRecord line
        in _preview?.lines ?? const <CustomerDebitNoteLineRecord>[]) {
      if (line.salesInvoiceLineId == lineId) return line;
    }
    return null;
  }

  Widget _noteRow(BuildContext context, int index) {
    final ThemeData theme = Theme.of(context);
    final ReturnableLine line = _selected!.lines[index];
    final CustomerDebitNoteLineRecord? priced = _pricedLine(line.id);
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final TextStyle? quiet =
        text?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final double charge = _number(_amounts[line.id] ?? '');
    final double value = _number(line.quantity) * _number(line.unitPrice);
    final double tax = priced == null ? 0 : _number(priced.taxAmount);
    return DocumentLineRow(
      key: ValueKey<String>('customer-debit-note-line-$index'),
      columns: _columns,
      current: index == _current,
      onTap: () => _setState(() => _current = index),
      cells: [
        Text('${line.lineNumber}', style: text),
        Padding(
          padding: const EdgeInsets.only(right: 8),
          child: Text(
            line.description.isEmpty
                ? 'Line ${line.lineNumber}'
                : line.description,
            overflow: TextOverflow.ellipsis,
            style: text,
          ),
        ),
        Text(documentQuantity(line.quantity), style: quiet),
        Text(documentMoney(line.unitPrice), style: quiet),
        Text(indianAmount(value, full: true), style: quiet),
        TextFormField(
          key: ValueKey<String>('customer-debit-note-amount-$_invoiceId-$index'),
          initialValue: _amounts[line.id] ?? '',
          readOnly: _saving,
          textAlign: TextAlign.right,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          inputFormatters: [
            FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
          ],
          style: text,
          decoration: documentCellDecoration(context, hint: '0'),
          onTap: () => _setState(() => _current = index),
          onChanged: (next) {
            _setState(() {
              _current = index;
              _amounts[line.id] = next;
            });
            _schedulePreview();
          },
        ),
        Text(
          priced == null || charge <= 0
              ? ''
              : '${documentQuantity(priced.taxRatePercent)}%',
          style: text,
        ),
        Text(charge <= 0 ? '' : indianAmount(tax, full: true), style: text),
        Text(
          charge <= 0 ? '' : indianAmount(charge + tax, full: true),
          style: text?.copyWith(fontWeight: FontWeight.w600),
        ),
      ],
    );
  }

  Widget _noteTotals() {
    final CustomerDebitNoteRecord? priced = _preview;
    double typed = 0;
    for (final String amount in _amounts.values) {
      typed += _number(amount);
    }
    return DocumentTotalsBar(
      total: priced == null ? null : _number(priced.totalAmount),
      note: typed <= 0
          ? 'Type the extra charge, before tax, on the lines it applies to.'
          : 'The tax follows as the lines are priced.',
      figures: [
        (
          'Charge before tax',
          priced == null ? typed : _number(priced.taxableAmount)
        ),
        ('Tax added', priced == null ? 0 : _number(priced.taxAmount)),
        (
          'Debit to customer',
          priced == null ? typed : _number(priced.totalAmount)
        ),
      ],
    );
  }

  Widget _noteSidePanel(BuildContext context) {
    final ReturnableDocument? invoice = _selected;
    if (invoice == null || invoice.lines.isEmpty) {
      return const DocumentSidePanel(children: [
        DocumentSideHeading('Debit note'),
        DocumentSideNote('choose the invoice being added to'),
      ]);
    }
    final ReturnableLine line =
        invoice.lines[_current.clamp(0, invoice.lines.length - 1)];
    final CustomerDebitNoteLineRecord? priced = _pricedLine(line.id);
    final double charge = _number(_amounts[line.id] ?? '');
    final double tax = priced == null ? 0 : _number(priced.taxAmount);
    return DocumentSidePanel(children: [
      DocumentSideHeading(
        'Line ${line.lineNumber} · '
        '${line.description.isEmpty ? '' : line.description}',
      ),
      DocumentSidePair('Billed', documentQuantity(line.quantity)),
      DocumentSidePair('At', documentMoney(line.unitPrice)),
      DocumentSidePair('Charging', indianAmount(charge, full: true),
          bold: true),
      if (priced != null && charge > 0) ...[
        DocumentSidePair(
          'Tax added at ${documentQuantity(priced.taxRatePercent)}%',
          indianAmount(tax, full: true),
        ),
        const DocumentSideNote(
          'the rate this invoice line charged, not today\'s rate',
        ),
      ],
      const DocumentSideHeading('When to use one'),
      const DocumentSideNote(
        'when a customer owes more on a sale already invoiced -- a price '
        'raised after billing, a line under-billed, a charge added later',
      ),
      const DocumentSideNote(
        'no cap: a line takes any positive amount; its original value is '
        'shown for reference only',
      ),
    ]);
  }
}
