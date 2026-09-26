part of 'credit_note_page.dart';

/// The credit note screen in the phase 2 app: the documents' one-screen
/// layout (wireframe view 7) for money going back without goods -- the
/// invoice being corrected, **every** one of its lines with the amount
/// credited on each before tax, and the tax coming off each at the rate its
/// invoice line charged, priced as it is typed by `POST /credit-notes/preview`.
/// The dialog's state and create are reused; it can now credit several lines
/// of one invoice on one note.
extension _Phase2CreditNote on _CreditNoteDialogState {
  static const List<DocumentColumn> _columns = [
    DocumentColumn('#', 28),
    DocumentColumn('Product', 0),
    DocumentColumn('Billed', 66, numeric: true),
    DocumentColumn('Rate', 84, numeric: true),
    DocumentColumn('Line value', 96, numeric: true),
    DocumentColumn('Credit', 96, numeric: true),
    DocumentColumn('GST', 52, numeric: true),
    DocumentColumn('Tax back', 88, numeric: true),
    DocumentColumn('Total', 100, numeric: true),
  ];

  static const List<(String, String)> _reasons = [
    ('RATE_DIFFERENCE', 'Rate difference'),
    ('POST_SALE_DISCOUNT', 'Discount after the sale'),
    ('DEFICIENCY_IN_SERVICE', 'Deficiency'),
    ('OTHER', 'Other'),
  ];

  Widget _phase2Page(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_invoices.isEmpty) {
      return StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'No approved invoice to credit',
        message: _error ??
            'A credit note always names the supply it corrects, because '
                'only that line knows the rate its tax was charged at.',
      );
    }
    final String number = _preview?.creditNoteNumber ?? '';
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.escape): () {
          if (!_saving) Navigator.of(context).pop(false);
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
                title: 'New credit note',
                chips: [
                  if (number.isNotEmpty) '$number (new)',
                  if (_selected != null) 'against ${_selected!.number}',
                  'Draft',
                ],
                hint: 'Enter next field  ·  Ctrl+S save',
                actions: [
                  TextButton(
                    onPressed:
                        _saving ? null : () => Navigator.of(context).pop(false),
                    child: const Text('Cancel'),
                  ),
                  FilledButton(
                    key: const ValueKey('credit-note-save'),
                    onPressed: _saving ? null : () => unawaited(_phase2Save()),
                    child: Text(_saving ? 'Saving…' : 'Raise credit note'),
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
    final List<ReturnableLine> crediting = [
      for (final ReturnableLine line in invoice.lines)
        if (_number(_amounts[line.id] ?? '') > 0) line,
    ];
    if (crediting.isEmpty) return null;
    return <String, dynamic>{
      'sales_invoice_id': invoice.id,
      'credit_note_date': _CreditNoteDialogState._today(),
      'reason': _reason,
      if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
      'lines': [
        for (int i = 0; i < crediting.length; i++)
          <String, dynamic>{
            'sales_invoice_line_id': crediting[i].id,
            'line_number': i + 1,
            // The tax comes off at the rate the invoice line charged, which
            // is why nothing here names one.
            'taxable_amount': _amounts[crediting[i].id]!.trim(),
          },
      ],
    };
  }

  Future<void> _phase2Save() async {
    final Json? payload = _phase2Payload();
    if (payload == null) {
      _setState(() => _error = 'Enter what is being credited, before tax, on '
          'at least one line.');
      return;
    }
    _setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.createCreditNote(payload);
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
        label: 'Invoice being corrected (approved)',
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
          key: const ValueKey('credit-note-invoice'),
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
          key: const ValueKey('credit-note-reason'),
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

  CreditNoteLineRecord? _pricedLine(String lineId) {
    for (final CreditNoteLineRecord line
        in _preview?.lines ?? const <CreditNoteLineRecord>[]) {
      if (line.salesInvoiceLineId == lineId) return line;
    }
    return null;
  }

  Widget _noteRow(BuildContext context, int index) {
    final ThemeData theme = Theme.of(context);
    final ReturnableLine line = _selected!.lines[index];
    final CreditNoteLineRecord? priced = _pricedLine(line.id);
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final TextStyle? quiet =
        text?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final double credit = _number(_amounts[line.id] ?? '');
    final double value = _number(line.quantity) * _number(line.unitPrice);
    final double tax = priced == null ? 0 : _number(priced.taxAmount);
    return DocumentLineRow(
      key: ValueKey<String>('credit-note-line-$index'),
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
          key: ValueKey<String>('credit-note-amount-$_invoiceId-$index'),
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
          priced == null || credit <= 0
              ? ''
              : '${documentQuantity(priced.taxRatePercent)}%',
          style: text,
        ),
        Text(credit <= 0 ? '' : indianAmount(tax, full: true), style: text),
        Text(
          credit <= 0 ? '' : indianAmount(credit + tax, full: true),
          style: text?.copyWith(fontWeight: FontWeight.w600),
        ),
      ],
    );
  }

  Widget _noteTotals() {
    final CreditNoteRecord? priced = _preview;
    double typed = 0;
    for (final String amount in _amounts.values) {
      typed += _number(amount);
    }
    return DocumentTotalsBar(
      total: priced == null ? null : _number(priced.totalAmount),
      note: typed <= 0
          ? 'Type the credit, before tax, on the lines it applies to.'
          : 'The tax follows as the lines are priced.',
      figures: [
        (
          'Credit before tax',
          priced == null ? typed : _number(priced.taxableAmount)
        ),
        ('Tax back', priced == null ? 0 : _number(priced.taxAmount)),
        (
          'Credit to customer',
          priced == null ? typed : _number(priced.totalAmount)
        ),
      ],
    );
  }

  Widget _noteSidePanel(BuildContext context) {
    final ReturnableDocument? invoice = _selected;
    if (invoice == null || invoice.lines.isEmpty) {
      return const DocumentSidePanel(children: [
        DocumentSideHeading('Credit note'),
        DocumentSideNote('choose the invoice being corrected'),
      ]);
    }
    final ReturnableLine line =
        invoice.lines[_current.clamp(0, invoice.lines.length - 1)];
    final CreditNoteLineRecord? priced = _pricedLine(line.id);
    final double credit = _number(_amounts[line.id] ?? '');
    final double tax = priced == null ? 0 : _number(priced.taxAmount);
    return DocumentSidePanel(children: [
      DocumentSideHeading(
        'Line ${line.lineNumber} · '
        '${line.description.isEmpty ? '' : line.description}',
      ),
      DocumentSidePair('Billed', documentQuantity(line.quantity)),
      DocumentSidePair('At', documentMoney(line.unitPrice)),
      DocumentSidePair('Crediting', indianAmount(credit, full: true),
          bold: true),
      if (priced != null && credit > 0) ...[
        DocumentSidePair(
          'Tax back at ${documentQuantity(priced.taxRatePercent)}%',
          indianAmount(tax, full: true),
        ),
        const DocumentSideNote(
          'the rate this invoice line charged, not today\'s rate',
        ),
      ],
      const DocumentSideHeading('When to use one'),
      const DocumentSideNote(
        'when the money changes and the goods do not -- a rate agreed after '
        'invoicing, or a discount given later; goods coming back are a sales '
        'return, which moves stock as well',
      ),
      const DocumentSideNote(
        'a line cannot be credited past what it was charged, counting other '
        'credit notes against it',
      ),
    ]);
  }
}
