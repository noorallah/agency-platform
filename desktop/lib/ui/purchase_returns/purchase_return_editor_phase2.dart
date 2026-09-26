part of 'purchase_return_editor_dialog.dart';

/// The purchase return screen in the phase 2 app: the documents' one-screen
/// layout (wireframe view 7) for goods going back -- the receipt they came
/// in on, its lines as a table with what can still go back and how much is,
/// the batch it leaves from, the value and tax of the debit, and a side
/// panel for the line's condition, reason and remarks -- priced as it is
/// typed by `POST /purchase-returns/preview`. The dialog's state,
/// validation and save are reused unchanged.
extension _Phase2PurchaseReturnEditor on _PurchaseReturnEditorDialogState {
  static const List<DocumentColumn> _columns = [
    DocumentColumn('#', 28),
    DocumentColumn('Product', 0),
    DocumentColumn('Received', 72, numeric: true),
    DocumentColumn('Returned', 72, numeric: true),
    DocumentColumn('Can go', 62, numeric: true),
    DocumentColumn('Returning', 80, numeric: true),
    DocumentColumn('Rejected', 72, numeric: true),
    DocumentColumn('Batch', 120),
    DocumentColumn('Taxable', 96, numeric: true),
    DocumentColumn('GST', 48, numeric: true),
    DocumentColumn('Amount', 104, numeric: true),
  ];

  Widget _phase2Page(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final String number =
        stringValue(_preview?.purchaseReturn['return_number']);
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.escape): () {
          if (!_saving) Navigator.pop(context);
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
                title: 'New purchase return',
                chips: [
                  if (number.isNotEmpty) '$number (new)',
                  if (_receipt != null) 'against ${_receipt!.grnNumber}',
                  'Draft',
                ],
                hint: 'Enter next field  ·  Ctrl+S save',
                actions: [
                  TextButton(
                    onPressed: _saving ? null : () => Navigator.pop(context),
                    child: const Text('Cancel'),
                  ),
                  FilledButton(
                    key: const ValueKey('purchase-return-save'),
                    onPressed: _saving ? null : () => unawaited(_save()),
                    child: const Text('Save return'),
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
              if (_saving || _loadingLines)
                const LinearProgressIndicator(minHeight: 2),
              Expanded(
                child: LayoutBuilder(
                  builder: (context, constraints) => Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            _returnHeader(context),
                            Expanded(child: _returnLines(context)),
                            _returnTotals(),
                          ],
                        ),
                      ),
                      if (constraints.maxWidth >= DocumentSidePanel.showFrom)
                        _returnSidePanel(context),
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

  Product? _product(String id) {
    for (final Product item in widget.products) {
      if (item.id == id) return item;
    }
    return null;
  }

  double _number(String value) => double.tryParse(value.trim()) ?? 0;

  String _dayOf(String value) {
    final DateTime? day = DateTime.tryParse(value);
    return day == null ? value : documentDate(day);
  }

  Widget _box(
    BuildContext context, {
    required String label,
    required String value,
    required ValueChanged<String> onChanged,
    double width = 180,
  }) =>
      DocumentField(
        label: label,
        width: width,
        child: TextFormField(
          initialValue: value,
          readOnly: _saving,
          decoration: documentBoxDecoration(context),
          onChanged: (next) => _setState(() => onChanged(next)),
        ),
      );

  Widget _returnHeader(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final GoodsReceiptRecord? receipt = _receipt;
    final DateTime? day = DateTime.tryParse(_returnDate);
    return DocumentHeader(children: [
      DocumentField(
        label: 'Goods receipt going back (completed only)',
        width: 400,
        below: receipt == null
            ? null
            : Text(
                [
                  'received ${_dayOf(receipt.receiptDate)}',
                  if (receipt.purchaseOrderNumber.isNotEmpty)
                    'order ${receipt.purchaseOrderNumber}',
                ].join('  ·  '),
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall?.copyWith(
                  fontSize: 11,
                  color: scheme.onSurfaceVariant,
                ),
              ),
        child: DropdownMenu<String>(
          key: const ValueKey('purchase-return-receipt'),
          initialSelection: receipt?.id,
          width: 400,
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
            for (final GoodsReceiptRecord item in widget.receipts)
              DropdownMenuEntry<String>(
                value: item.id,
                label: '${item.grnNumber}  ${_dayOf(item.receiptDate)}',
              ),
          ],
          onSelected: (value) async {
            for (final GoodsReceiptRecord item in widget.receipts) {
              if (item.id == value && item.id != _receipt?.id) {
                _current = 0;
                _preview = null;
                await _selectReceipt(item);
                _schedulePreview();
              }
            }
          },
        ),
      ),
      DocumentField(
        label: 'Return date',
        auto: true,
        width: 140,
        child: InkWell(
          key: const ValueKey('purchase-return-date'),
          onTap: _saving
              ? null
              : () async {
                  final DateTime? picked = await showDatePicker(
                    context: context,
                    initialDate: day ?? DateTime.now(),
                    firstDate: DateTime(2000),
                    lastDate: DateTime(2100),
                  );
                  if (picked == null) return;
                  _setState(() =>
                      _returnDate = picked.toIso8601String().split('T').first);
                  _schedulePreview();
                },
          child: InputDecorator(
            decoration: documentBoxDecoration(context).copyWith(
              suffixIcon: const Icon(Icons.event, size: 16),
              suffixIconConstraints:
                  const BoxConstraints(minWidth: 28, minHeight: 20),
            ),
            child: Text(day == null ? '—' : documentDate(day)),
          ),
        ),
      ),
      _box(
        context,
        label: "Supplier's return number",
        value: _supplierReturnNumber,
        width: 180,
        onChanged: (value) => _supplierReturnNumber = value,
      ),
      DocumentField(
        label: 'Tax',
        auto: true,
        width: 150,
        child: InputDecorator(
          decoration: documentBoxDecoration(context),
          child: Text(
            _preview == null
                ? '—'
                : _preview!.interstate
                    ? 'IGST · other state'
                    : 'CGST + SGST',
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ),
      _box(
        context,
        label: 'Why it is going back',
        value: _returnReason,
        width: 240,
        onChanged: (value) => _returnReason = value,
      ),
      _box(
        context,
        label: 'Remarks',
        value: _remarks,
        width: 240,
        onChanged: (value) => _remarks = value,
      ),
    ]);
  }

  Widget _returnLines(BuildContext context) {
    if (_receipt == null) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'No goods receipt chosen',
        message: 'A return sends back what a receipt brought in. Choose the '
            'receipt above and its lines appear here, at what can still go '
            'back.',
      );
    }
    return DocumentLineTable(
      columns: _columns,
      rows: [for (int i = 0; i < _lines.length; i++) _returnRow(context, i)],
    );
  }

  Map<String, dynamic>? _pricedLine(int index) {
    final PurchaseReturnDraftLine line = _lines[index];
    for (final dynamic raw
        in _preview?.purchaseReturn['lines'] as List? ?? const []) {
      if (raw is Map &&
          stringValue(raw['source_document_line_id']) ==
              line.sourceDocumentLineId) {
        return Map<String, dynamic>.from(raw);
      }
    }
    return null;
  }

  DocumentPreviewLine? _companion(int index) {
    final Map<String, dynamic>? priced = _pricedLine(index);
    if (priced == null) return null;
    final int number = (priced['line_number'] as num?)?.toInt() ?? 0;
    for (final DocumentPreviewLine line
        in _preview?.lines ?? const <DocumentPreviewLine>[]) {
      if (line.lineNumber == number) return line;
    }
    return null;
  }

  double _typedTaxable(PurchaseReturnDraftLine line) =>
      _number(line.returnQuantity) * _number(line.unitPrice);

  Widget _cellBox(
    BuildContext context, {
    required int index,
    required String name,
    required String value,
    required ValueChanged<String> onChanged,
    bool over = false,
  }) =>
      TextFormField(
        key: ValueKey<String>('purchase-return-$name-${_receipt?.id}-$index'),
        initialValue: value.trim().isEmpty ? value : documentQuantity(value),
        readOnly: _saving,
        textAlign: TextAlign.right,
        keyboardType: TextInputType.number,
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              fontSize: 13,
              color: over ? Theme.of(context).colorScheme.error : null,
            ),
        decoration: documentCellDecoration(context),
        onTap: () => _setState(() => _current = index),
        onChanged: (next) {
          _setState(() {
            _current = index;
            onChanged(next);
          });
          _schedulePreview();
        },
      );

  /// The batch the goods leave from: the register's batches for the
  /// product, so a number nobody received cannot be chosen.
  Widget _batchCell(
    BuildContext context,
    int index,
    PurchaseReturnDraftLine line,
    TextStyle? text,
  ) {
    final List<BatchRecord> batches = _batchesByProduct[line.productId] ?? [];
    if (batches.isEmpty) {
      return Text(
        line.receiptBatchNumber.isEmpty ? '—' : line.receiptBatchNumber,
        overflow: TextOverflow.ellipsis,
        style: text?.copyWith(
          color: Theme.of(context).colorScheme.onSurfaceVariant,
        ),
      );
    }
    return DropdownButton<String>(
      key: ValueKey<String>('purchase-return-batch-${_receipt?.id}-$index'),
      value: batches.any((batch) => batch.batchNumber == line.batchNumber)
          ? line.batchNumber
          : null,
      isExpanded: true,
      isDense: true,
      underline: const SizedBox.shrink(),
      style: text,
      hint: Text('choose', style: text),
      items: [
        for (final BatchRecord batch in batches)
          DropdownMenuItem<String>(
            value: batch.batchNumber,
            child: Text(batch.batchNumber, overflow: TextOverflow.ellipsis),
          ),
      ],
      onChanged: _saving
          ? null
          : (value) => _setState(() {
                _current = index;
                line.batchNumber = value ?? '';
              }),
    );
  }

  Widget _returnRow(BuildContext context, int index) {
    final ThemeData theme = Theme.of(context);
    final PurchaseReturnDraftLine line = _lines[index];
    final Product? product = _product(line.productId);
    final Map<String, dynamic>? priced = _pricedLine(index);
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final TextStyle? quiet =
        text?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final double returning = _number(line.returnQuantity);
    final double taxable = priced == null
        ? _typedTaxable(line)
        : _number(stringValue(priced['gross_amount'])) -
            _number(stringValue(priced['discount_amount']));
    final double tax =
        priced == null ? 0 : _number(stringValue(priced['tax_amount']));
    final double rate = taxable > 0 ? tax / taxable * 100 : 0;
    return DocumentLineRow(
      key: ValueKey<String>('purchase-return-line-$index'),
      columns: _columns,
      current: index == _current,
      onTap: () => _setState(() => _current = index),
      cells: [
        Text('${line.lineNumber}', style: text),
        Padding(
          padding: const EdgeInsets.only(right: 8),
          child: Text(
            product == null
                ? (line.description.isEmpty ? line.productId : line.description)
                : '${product.name}  ${product.code}',
            overflow: TextOverflow.ellipsis,
            style: text,
          ),
        ),
        Text(documentQuantity(line.receivedQuantity), style: quiet),
        Text(documentQuantity(line.alreadyReturned), style: quiet),
        Text(
          documentQuantity(
            _PurchaseReturnEditorDialogState._trim(line.outstanding),
          ),
          style: text?.copyWith(fontWeight: FontWeight.w600),
        ),
        _cellBox(
          context,
          index: index,
          name: 'returning',
          value: line.returnQuantity,
          over: returning > line.outstanding,
          onChanged: (value) => line.returnQuantity = value,
        ),
        _cellBox(
          context,
          index: index,
          name: 'rejected',
          value: line.rejectedQuantity,
          over: _number(line.rejectedQuantity) > returning,
          onChanged: (value) => line.rejectedQuantity = value,
        ),
        _batchCell(context, index, line, text),
        Text(indianAmount(taxable, full: true), style: text),
        Text(
          priced == null || returning <= 0
              ? ''
              : '${documentQuantity(rate.toStringAsFixed(1))}%',
          style: text,
        ),
        Text(
          indianAmount(taxable + tax, full: true),
          style: text?.copyWith(fontWeight: FontWeight.w600),
        ),
      ],
    );
  }

  Widget _returnTotals() {
    final Map<String, dynamic>? document = _preview?.purchaseReturn;
    double typed = 0;
    for (final PurchaseReturnDraftLine line in _lines) {
      typed += _typedTaxable(line);
    }
    final double taxable =
        document == null ? typed : _number(stringValue(document['subtotal']));
    final double tax =
        document == null ? 0 : _number(stringValue(document['tax_total']));
    final double total = document == null
        ? taxable
        : _number(stringValue(document['grand_total']));
    final bool? interstate = _preview?.interstate;
    return DocumentTotalsBar(
      total: document == null ? null : total,
      note: _receipt == null
          ? 'Choose the receipt the goods came in on.'
          : 'Totals follow as the lines are priced.',
      figures: [
        ('Taxable', taxable),
        if (interstate == null)
          ('GST', tax)
        else if (interstate)
          ('IGST', tax)
        else ...[
          ('CGST', tax / 2),
          ('SGST', tax / 2),
        ],
        ('Debit to supplier', total),
      ],
    );
  }

  Widget _returnSidePanel(BuildContext context) {
    if (_lines.isEmpty) {
      return const DocumentSidePanel(children: [
        DocumentSideHeading('Returning'),
        DocumentSideNote(
          'Choose the receipt the goods came in on. Each line starts at what '
          'can still go back; change what differs, leave a line at zero if it '
          'stays, and say which batch it leaves from.',
        ),
      ]);
    }
    final int index = _current.clamp(0, _lines.length - 1);
    final PurchaseReturnDraftLine line = _lines[index];
    final Product? product = _product(line.productId);
    final Map<String, dynamic>? priced = _pricedLine(index);
    final DocumentPreviewLine? companion = _companion(index);
    final double returning = _number(line.returnQuantity);
    final double left = line.outstanding - returning;
    final double taxable = priced == null
        ? _typedTaxable(line)
        : _number(stringValue(priced['gross_amount'])) -
            _number(stringValue(priced['discount_amount']));
    final double tax =
        priced == null ? 0 : _number(stringValue(priced['tax_amount']));
    String quantity(double value) =>
        documentQuantity(_PurchaseReturnEditorDialogState._trim(value));
    return DocumentSidePanel(children: [
      DocumentSideHeading(
        'Line ${line.lineNumber} · ${product?.name ?? line.description}',
      ),
      DocumentSidePair('Received', documentQuantity(line.receivedQuantity)),
      DocumentSidePair(
          'Returned before', documentQuantity(line.alreadyReturned)),
      DocumentSidePair('Returning now', quantity(returning)),
      DocumentSidePair(
        left < 0 ? 'More than received by' : 'Could still go back',
        quantity(left.abs()),
        bold: true,
        tone: left < 0 ? Theme.of(context).colorScheme.error : null,
      ),
      DocumentSidePair('Rate', documentMoney(line.unitPrice)),
      const DocumentSideNote('the receipt price'),
      ...documentTaxLines(
        taxable: taxable,
        tax: tax,
        interstate: _preview?.interstate,
      ),
      if (line.receiptBatchNumber.isNotEmpty)
        DocumentSideNote('the receipt said batch ${line.receiptBatchNumber}'),
      const DocumentSideHeading('Condition'),
      Wrap(spacing: 8, children: [
        FilterChip(
          key: ValueKey<String>('purchase-return-damaged-$index'),
          label: const Text('Damaged'),
          selected: line.isDamaged,
          onSelected: _saving
              ? null
              : (value) => _setState(() => line.isDamaged = value),
        ),
        FilterChip(
          key: ValueKey<String>('purchase-return-scrap-$index'),
          label: const Text('Scrap'),
          selected: line.isScrap,
          onSelected:
              _saving ? null : (value) => _setState(() => line.isScrap = value),
        ),
      ]),
      const SizedBox(height: 8),
      DocumentField(
        label: 'Reason code',
        width: 258,
        child: TextFormField(
          key:
              ValueKey<String>('purchase-return-reason-${_receipt?.id}-$index'),
          initialValue: line.reasonCode,
          readOnly: _saving,
          decoration: documentBoxDecoration(context),
          onChanged: (value) => line.reasonCode = value,
        ),
      ),
      DocumentField(
        label: 'Line remarks',
        width: 258,
        child: TextFormField(
          key: ValueKey<String>(
              'purchase-return-remarks-${_receipt?.id}-$index'),
          initialValue: line.remarks,
          readOnly: _saving,
          decoration: documentBoxDecoration(context),
          onChanged: (value) => line.remarks = value,
        ),
      ),
      const DocumentSideHeading('Stock'),
      DocumentSidePair(
        'Where it goes back from',
        companion == null ? '—' : documentQuantity(companion.availableQuantity),
      ),
      const DocumentSideNote(
        'completing the return takes it out of stock and debits the supplier',
      ),
    ]);
  }
}
