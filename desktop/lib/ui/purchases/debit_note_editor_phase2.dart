part of 'debit_note_page.dart';

/// The debit note screen in the phase 2 app: the documents' one-screen layout
/// for money claimed from a supplier without goods going back -- the vendor,
/// the one bill being claimed on, **every** line of that bill with the claim
/// typed on each before tax, and the tax coming off each at the rate its bill
/// line charged, priced as it is typed by `POST /debit-notes/preview`.
extension _Phase2DebitNote on _DebitNoteDialogState {
  static const List<DocumentColumn> _columns = [
    DocumentColumn('#', 28),
    DocumentColumn('Product', 0),
    DocumentColumn('Billed', 66, numeric: true),
    DocumentColumn('Claimable', 96, numeric: true),
    DocumentColumn('Qty short', 72, numeric: true),
    DocumentColumn('Claim', 96, numeric: true),
    DocumentColumn('GST', 52, numeric: true),
    DocumentColumn('Tax', 88, numeric: true),
    DocumentColumn('Total', 100, numeric: true),
  ];

  static const List<(String, String)> _reasons = [
    ('PRICE_DIFFERENCE', 'Price difference'),
    ('SHORT_SUPPLY', 'Short supply'),
    ('DISCOUNT', 'Discount after billing'),
    ('OTHER', 'Other'),
  ];

  Json? get _selectedBill {
    for (final Json bill in _bills) {
      if (stringValue(bill['id']) == _billId) return bill;
    }
    return null;
  }

  String _billLabel(Json bill) {
    final String supplier = stringValue(bill['supplier_invoice_number']);
    return [
      stringValue(bill['invoice_number']),
      if (supplier.isNotEmpty) 'supplier $supplier',
      stringValue(bill['invoice_date']),
    ].where((part) => part.isNotEmpty).join('  ·  ');
  }

  Widget _phase2Page(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_vendors.isEmpty) {
      return StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'No supplier to claim on',
        message: _error ??
            'A debit note always names the bill it corrects, because only '
                'that line knows the rate its tax was charged at.',
      );
    }
    final String number = _preview?.debitNoteNumber ?? '';
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.escape): () {
          if (!_saving) Navigator.of(context).pop(false);
        },
        const SingleActivator(LogicalKeyboardKey.keyS, control: true): () {
          if (!_saving) unawaited(_save());
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
                title: _editing
                    ? 'Edit ${widget.existing!.debitNoteNumber}'
                    : 'New debit note',
                chips: [
                  if (number.isNotEmpty) '$number (new)',
                  if (_selectedBill != null)
                    'against ${stringValue(_selectedBill!['invoice_number'])}',
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
                    key: const ValueKey('debit-note-save'),
                    onPressed: _saving ? null : () => unawaited(_save()),
                    child: Text(_saving
                        ? 'Saving…'
                        : _editing
                            ? 'Save changes'
                            : 'Raise debit note'),
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
                            Expanded(child: _noteBody()),
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

  /// The lines, or the word on what to do first.
  Widget _noteBody() {
    if (_loadingBills || _loadingLines) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_vendorId.isEmpty) {
      return const Center(child: Text('Choose the supplier.'));
    }
    if (_bills.isEmpty) {
      return const Center(
        child: Text('This supplier has no approved bill to claim on.'),
      );
    }
    if (_billId.isEmpty) {
      return const Center(child: Text('Choose the bill being corrected.'));
    }
    return DocumentLineTable(
      columns: _columns,
      rows: [
        for (int i = 0; i < _lines.length; i++) _noteRow(context, i),
      ],
    );
  }

  InputDecorationTheme _menuTheme(ColorScheme scheme) => InputDecorationTheme(
        isDense: true,
        filled: true,
        fillColor: scheme.surfaceContainerLowest,
        contentPadding: const EdgeInsets.symmetric(horizontal: 8),
        constraints: const BoxConstraints(maxHeight: 36),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(5)),
      );

  Widget _noteHeader(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return DocumentHeader(children: [
      DocumentField(
        label: 'Supplier',
        width: 240,
        child: DropdownMenu<String>(
          key: const ValueKey('debit-note-vendor'),
          initialSelection: _vendorId.isEmpty ? null : _vendorId,
          width: 240,
          enabled: !_saving && !_editing,
          enableFilter: true,
          requestFocusOnTap: true,
          menuHeight: 320,
          inputDecorationTheme: _menuTheme(scheme),
          dropdownMenuEntries: [
            for (final Vendor vendor in _vendors)
              DropdownMenuEntry<String>(
                value: vendor.id,
                label: vendor.displayName.isNotEmpty
                    ? vendor.displayName
                    : vendor.name,
              ),
          ],
          onSelected: (value) {
            if (value == null || value == _vendorId) return;
            unawaited(_loadBills(value));
          },
        ),
      ),
      DocumentField(
        label: 'Bill being corrected (approved)',
        width: 340,
        child: DropdownMenu<String>(
          // A new key per supplier, so the previous supplier's bill is not
          // left showing in the box.
          key: ValueKey('debit-note-bill-$_vendorId'),
          initialSelection: _billId.isEmpty ? null : _billId,
          width: 340,
          enabled: !_saving && !_editing && _bills.isNotEmpty,
          enableFilter: true,
          requestFocusOnTap: true,
          menuHeight: 320,
          inputDecorationTheme: _menuTheme(scheme),
          dropdownMenuEntries: [
            for (final Json bill in _bills)
              DropdownMenuEntry<String>(
                value: stringValue(bill['id']),
                label: _billLabel(bill),
              ),
          ],
          onSelected: (value) {
            if (value == null || value == _billId) return;
            unawaited(_loadLines(value));
          },
        ),
      ),
      DocumentField(
        label: 'Dated',
        auto: true,
        width: 130,
        child: InputDecorator(
          decoration: documentBoxDecoration(context),
          child: Text(_editing
              ? widget.existing!.debitNoteDate
              : documentDate(DateTime.now())),
        ),
      ),
      DocumentField(
        label: 'Reason',
        width: 180,
        child: DropdownButtonFormField<String>(
          key: const ValueKey('debit-note-reason'),
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
              : (value) {
                  _setState(() => _reason = value ?? _reason);
                  _schedulePreview();
                },
        ),
      ),
      DocumentField(
        label: 'Reference',
        width: 160,
        child: TextFormField(
          controller: _reference,
          readOnly: _saving,
          decoration: documentBoxDecoration(context),
        ),
      ),
      DocumentField(
        label: "Supplier's credit note no.",
        width: 170,
        child: TextFormField(
          key: const ValueKey('debit-note-supplier-credit-note'),
          controller: _supplierNote,
          readOnly: _saving,
          decoration: documentBoxDecoration(context),
        ),
      ),
      DocumentField(
        label: 'Its date',
        width: 150,
        child: _supplierNoteDateBox(context),
      ),
      DocumentField(
        label: 'Remarks',
        width: 240,
        child: TextFormField(
          controller: _remarks,
          readOnly: _saving,
          decoration: documentBoxDecoration(context),
        ),
      ),
    ]);
  }

  /// The supplier's credit note date: picked, and clearable.
  Widget _supplierNoteDateBox(BuildContext context) {
    final DateTime? day = DateTime.tryParse(_supplierNoteDate);
    return InkWell(
      key: const ValueKey('debit-note-supplier-credit-note-date'),
      onTap: _saving
          ? null
          : () async {
              final DateTime? picked = await showDatePicker(
                context: context,
                initialDate: day ?? DateTime.now(),
                firstDate: DateTime(2000),
                lastDate: DateTime(2100),
              );
              if (picked != null) {
                _setState(() => _supplierNoteDate =
                    picked.toIso8601String().split('T').first);
              }
            },
      child: InputDecorator(
        decoration: documentBoxDecoration(context).copyWith(
          suffixIcon: day != null && !_saving
              ? IconButton(
                  tooltip: 'Clear',
                  iconSize: 14,
                  visualDensity: VisualDensity.compact,
                  onPressed: () => _setState(() => _supplierNoteDate = ''),
                  icon: const Icon(Icons.close),
                )
              : const Icon(Icons.event, size: 16),
          suffixIconConstraints:
              const BoxConstraints(minWidth: 28, minHeight: 20),
        ),
        child: Text(day == null ? '—' : documentDate(day)),
      ),
    );
  }

  DebitNoteLineRecord? _pricedLine(String lineId) {
    for (final DebitNoteLineRecord line
        in _preview?.lines ?? const <DebitNoteLineRecord>[]) {
      if (line.purchaseInvoiceLineId == lineId) return line;
    }
    return null;
  }

  Widget _noteRow(BuildContext context, int index) {
    final ThemeData theme = Theme.of(context);
    final DebitNoteClaimableLine line = _lines[index];
    final String lineId = line.purchaseInvoiceLineId;
    final DebitNoteLineRecord? priced = _pricedLine(lineId);
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final TextStyle? quiet =
        text?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final double claim = _number(_amounts[lineId] ?? '');
    final double tax = priced == null ? 0 : _number(priced.taxAmount);
    final bool over = claim > _number(line.claimable) + 0.00005;
    return DocumentLineRow(
      key: ValueKey<String>('debit-note-line-$index'),
      columns: _columns,
      current: index == _current,
      onTap: () => _setState(() => _current = index),
      cells: [
        Text('${line.lineNumber}', style: text),
        Padding(
          padding: const EdgeInsets.only(right: 8),
          child: Text(
            line.productName.isEmpty
                ? 'Line ${line.lineNumber}'
                : line.productName,
            overflow: TextOverflow.ellipsis,
            style: text,
          ),
        ),
        Text(documentQuantity(line.quantity), style: quiet),
        Text(indianAmount(_number(line.claimable), full: true), style: quiet),
        TextFormField(
          key: ValueKey<String>('debit-note-quantity-$_billId-$index'),
          initialValue: _quantities[lineId] ?? '',
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
              _quantities[lineId] = next;
            });
            _schedulePreview();
          },
        ),
        TextFormField(
          key: ValueKey<String>('debit-note-amount-$_billId-$index'),
          initialValue: _amounts[lineId] ?? '',
          readOnly: _saving,
          textAlign: TextAlign.right,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          inputFormatters: [
            FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
          ],
          style: over ? text?.copyWith(color: theme.colorScheme.error) : text,
          decoration: documentCellDecoration(context, hint: '0'),
          onTap: () => _setState(() => _current = index),
          onChanged: (next) {
            _setState(() {
              _current = index;
              _amounts[lineId] = next;
            });
            _schedulePreview();
          },
        ),
        Text(
          priced == null || claim <= 0
              ? ''
              : '${documentQuantity(priced.taxRatePercent)}%',
          style: text,
        ),
        Text(claim <= 0 ? '' : indianAmount(tax, full: true), style: text),
        Text(
          claim <= 0 ? '' : indianAmount(claim + tax, full: true),
          style: text?.copyWith(fontWeight: FontWeight.w600),
        ),
      ],
    );
  }

  Widget _noteTotals() {
    final DebitNoteRecord? priced = _preview;
    double typed = 0;
    for (final String amount in _amounts.values) {
      typed += _number(amount);
    }
    return DocumentTotalsBar(
      total: priced == null ? null : _number(priced.totalAmount),
      note: typed <= 0
          ? 'Type the claim, before tax, on the lines it applies to.'
          : 'The tax follows as the lines are priced.',
      figures: [
        (
          'Claim before tax',
          priced == null ? typed : _number(priced.taxableAmount)
        ),
        ('Tax', priced == null ? 0 : _number(priced.taxAmount)),
        (
          'Claim on supplier',
          priced == null ? typed : _number(priced.totalAmount)
        ),
      ],
    );
  }

  Widget _noteSidePanel(BuildContext context) {
    if (_lines.isEmpty) {
      return const DocumentSidePanel(children: [
        DocumentSideHeading('Debit note'),
        DocumentSideNote('choose the supplier, then the bill being corrected'),
      ]);
    }
    final DebitNoteClaimableLine line =
        _lines[_current.clamp(0, _lines.length - 1)];
    final DebitNoteLineRecord? priced = _pricedLine(line.purchaseInvoiceLineId);
    final double claim = _number(_amounts[line.purchaseInvoiceLineId] ?? '');
    final double tax = priced == null ? 0 : _number(priced.taxAmount);
    return DocumentSidePanel(children: [
      DocumentSideHeading('Line ${line.lineNumber} · ${line.productName}'),
      DocumentSidePair('Billed', documentQuantity(line.quantity)),
      DocumentSidePair('At', documentMoney(line.unitPrice)),
      DocumentSidePair(
          'Already claimed', indianAmount(_number(line.alreadyClaimed))),
      DocumentSidePair(
          'Already returned', indianAmount(_number(line.alreadyReturned))),
      DocumentSidePair('Left to claim', indianAmount(_number(line.claimable)),
          bold: true),
      DocumentSidePair('Claiming', indianAmount(claim, full: true), bold: true),
      if (priced != null && claim > 0) ...[
        DocumentSidePair(
          'Tax at ${documentQuantity(priced.taxRatePercent)}%',
          indianAmount(tax, full: true),
        ),
        const DocumentSideNote(
          'the rate this bill line charged, not today\'s rate',
        ),
      ],
      const DocumentSideHeading('When to use one'),
      const DocumentSideNote(
        'when the money changes and the goods do not -- a price difference '
        'found after the bill, or a short supply; goods going back are a '
        'purchase return, which moves stock as well',
      ),
      const DocumentSideNote(
        'a line cannot be claimed past what is left on it, counting other '
        'debit notes and returns against it',
      ),
      const DocumentSideNote(
        "when the supplier sent their own credit note -- a rate difference "
        'or a discount after billing -- record its number and date here; it '
        'is the same claim seen from their side',
      ),
    ]);
  }
}
