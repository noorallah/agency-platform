part of 'purchase_invoice_editor_dialog.dart';

/// The supplier bill screen in the phase 2 app: the documents' one-screen
/// layout (wireframe view 7) for a bill -- the receipt it charges for and the
/// supplier's own number and date, the receipt's lines as a table, the
/// totals to check against the paper, and a side panel for the line being
/// typed -- priced as it is typed by `POST /purchase-invoices/preview`. The
/// dialog's state, validation and save are reused unchanged.
extension _Phase2PurchaseInvoiceEditor on _PurchaseInvoiceEditorDialogState {
  static const List<DocumentColumn> _columns = [
    DocumentColumn('#', 28),
    DocumentColumn('Product', 0),
    DocumentColumn('HSN', 66),
    DocumentColumn('Received', 72, numeric: true),
    DocumentColumn('Billed', 64, numeric: true),
    DocumentColumn('Due', 60, numeric: true),
    DocumentColumn('Billing', 76, numeric: true),
    DocumentColumn('Rate', 90, numeric: true),
    DocumentColumn('Taxable', 96, numeric: true),
    DocumentColumn('GST', 48, numeric: true),
    DocumentColumn('Amount', 104, numeric: true),
  ];

  Widget _phase2Page(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final String number = stringValue(_preview?.invoice['invoice_number']);
    final String duplicate =
        stringValue(_preview?.invoice['duplicate_warning']);
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
                title: 'New purchase invoice',
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
                    key: const ValueKey('purchase-invoice-save'),
                    onPressed: _saving ? null : () => unawaited(_save()),
                    child: const Text('Save bill'),
                  ),
                ],
              ),
              for (final String message in [
                if (_error != null) _error!,
                if (duplicate.isNotEmpty &&
                    _supplierInvoiceNumber.trim().isNotEmpty)
                  '$duplicate Check it is not the same bill entered twice.',
              ])
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                  child: MaterialBanner(
                    contentTextStyle: theme.textTheme.bodyMedium,
                    content: Text(message),
                    actions: [
                      if (message == _error)
                        TextButton(
                          onPressed: () => _setState(() => _error = null),
                          child: const Text('Dismiss'),
                        )
                      else
                        const SizedBox.shrink(),
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
                            _billHeader(context),
                            Expanded(child: _billLines(context)),
                            _billTotals(),
                          ],
                        ),
                      ),
                      if (constraints.maxWidth >= DocumentSidePanel.showFrom)
                        _billSidePanel(context),
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

  Widget _dateBox(
    BuildContext context, {
    required Key key,
    required String value,
    required ValueChanged<String> onPicked,
  }) {
    final DateTime? day = DateTime.tryParse(value);
    return InkWell(
      key: key,
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
                onPicked(picked.toIso8601String().split('T').first);
              }
            },
      child: InputDecorator(
        decoration: documentBoxDecoration(context).copyWith(
          suffixIcon: const Icon(Icons.event, size: 16),
          suffixIconConstraints:
              const BoxConstraints(minWidth: 28, minHeight: 20),
        ),
        child: Text(day == null ? '—' : documentDate(day)),
      ),
    );
  }

  Widget _billHeader(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final GoodsReceiptRecord? receipt = _receipt;
    return DocumentHeader(children: [
      DocumentField(
        label: 'Goods receipt being billed (completed only)',
        width: 400,
        below: receipt == null
            ? null
            : Text(
                [
                  'received ${_dayOf(receipt.receiptDate)}',
                  if (receipt.purchaseOrderNumber.isNotEmpty)
                    'order ${receipt.purchaseOrderNumber}',
                  if (receipt.invoiceReference.isNotEmpty)
                    'bill noted on receipt ${receipt.invoiceReference}',
                ].join('  ·  '),
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall?.copyWith(
                  fontSize: 11,
                  color: scheme.onSurfaceVariant,
                ),
              ),
        child: DropdownMenu<String>(
          key: const ValueKey('purchase-invoice-receipt'),
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
                // The paper usually carries the number the storeman noted.
                if (_supplierInvoiceNumber.trim().isEmpty &&
                    item.invoiceReference.isNotEmpty) {
                  _supplierInvoiceNumber = item.invoiceReference;
                  _supplierNumberEpoch++;
                }
                await _selectReceipt(item);
                _schedulePreview();
              }
            }
          },
        ),
      ),
      DocumentField(
        label: "Supplier's invoice number",
        width: 190,
        child: TextFormField(
          key: ValueKey<String>(
            'purchase-invoice-supplier-number-$_supplierNumberEpoch',
          ),
          initialValue: _supplierInvoiceNumber,
          readOnly: _saving,
          decoration: documentBoxDecoration(context, hint: 'as printed'),
          onChanged: (value) {
            _setState(() => _supplierInvoiceNumber = value);
            _schedulePreview();
          },
        ),
      ),
      DocumentField(
        label: "Supplier's invoice date",
        width: 150,
        child: _dateBox(
          context,
          key: const ValueKey('purchase-invoice-supplier-date'),
          value: _supplierInvoiceDate,
          onPicked: (day) => _setState(() => _supplierInvoiceDate = day),
        ),
      ),
      DocumentField(
        label: 'Entered on',
        auto: true,
        width: 140,
        child: _dateBox(
          context,
          key: const ValueKey('purchase-invoice-date'),
          value: _invoiceDate,
          onPicked: (day) {
            _setState(() => _invoiceDate = day);
            _schedulePreview();
          },
        ),
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
      DocumentField(
        label: 'Remarks',
        width: 240,
        child: TextFormField(
          initialValue: _remarks,
          readOnly: _saving,
          decoration: documentBoxDecoration(context),
          onChanged: (value) => _remarks = value,
        ),
      ),
    ]);
  }

  Widget _billLines(BuildContext context) {
    if (_receipt == null) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'No goods receipt chosen',
        message: 'A bill charges for what a receipt brought in. Choose the '
            'receipt above and its lines appear here, at what is still to be '
            'billed.',
      );
    }
    return DocumentLineTable(
      columns: _columns,
      rows: [for (int i = 0; i < _lines.length; i++) _billRow(context, i)],
    );
  }

  Map<String, dynamic>? _pricedLine(int index) {
    final PurchaseInvoiceDraftLine line = _lines[index];
    for (final dynamic raw in _preview?.invoice['lines'] as List? ?? const []) {
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

  /// The line's value before tax, as typed: what shows until the server's
  /// figure arrives, and for a line not being billed.
  double _typedTaxable(PurchaseInvoiceDraftLine line) =>
      _number(line.invoiceQuantity) *
      _number(line.unitPrice.trim().isEmpty
          ? line.receiptUnitPrice
          : line.unitPrice);

  Widget _cellBox(
    BuildContext context, {
    required int index,
    required String name,
    required String value,
    required ValueChanged<String> onChanged,
    bool over = false,
    String? hint,
  }) =>
      TextFormField(
        key: ValueKey<String>('purchase-invoice-$name-${_receipt?.id}-$index'),
        initialValue: value.trim().isEmpty ? value : documentQuantity(value),
        readOnly: _saving,
        textAlign: TextAlign.right,
        keyboardType: TextInputType.number,
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              fontSize: 13,
              color: over ? Theme.of(context).colorScheme.error : null,
            ),
        decoration: documentCellDecoration(context, hint: hint),
        onTap: () => _setState(() => _current = index),
        onChanged: (next) {
          _setState(() {
            _current = index;
            onChanged(next);
          });
          _schedulePreview();
        },
      );

  Widget _billRow(BuildContext context, int index) {
    final ThemeData theme = Theme.of(context);
    final PurchaseInvoiceDraftLine line = _lines[index];
    final Product? product = _product(line.productId);
    final Map<String, dynamic>? priced = _pricedLine(index);
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final TextStyle? quiet =
        text?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final double billing = _number(line.invoiceQuantity);
    final double taxable = priced == null
        ? _typedTaxable(line)
        : _number(stringValue(priced['gross_amount'])) -
            _number(stringValue(priced['discount_amount']));
    final double tax =
        priced == null ? 0 : _number(stringValue(priced['tax_amount']));
    final double rate = taxable > 0 ? tax / taxable * 100 : 0;
    return DocumentLineRow(
      key: ValueKey<String>('purchase-invoice-line-$index'),
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
        Text(product?.hsnSac ?? '', style: text),
        Text(documentQuantity(line.receivedQuantity), style: quiet),
        Text(documentQuantity(line.alreadyInvoiced), style: quiet),
        Text(
          documentQuantity(
            _PurchaseInvoiceEditorDialogState._trim(line.outstanding),
          ),
          style: text?.copyWith(fontWeight: FontWeight.w600),
        ),
        _cellBox(
          context,
          index: index,
          name: 'billing',
          value: line.invoiceQuantity,
          over: billing > line.outstanding,
          onChanged: (value) => line.invoiceQuantity = value,
        ),
        _cellBox(
          context,
          index: index,
          name: 'rate',
          value: line.unitPrice,
          // Blank takes the receipt's price; say which.
          hint: documentMoney(line.receiptUnitPrice),
          onChanged: (value) => line.unitPrice = value,
        ),
        Text(indianAmount(taxable, full: true), style: text),
        Text(
          priced == null || billing <= 0
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

  Widget _billTotals() {
    final Map<String, dynamic>? invoice = _preview?.invoice;
    double typed = 0;
    for (final PurchaseInvoiceDraftLine line in _lines) {
      typed += _typedTaxable(line);
    }
    final double taxable =
        invoice == null ? typed : _number(stringValue(invoice['subtotal']));
    final double tax =
        invoice == null ? 0 : _number(stringValue(invoice['tax_total']));
    final double total = invoice == null
        ? taxable
        : _number(stringValue(invoice['grand_total']));
    final bool? interstate = _preview?.interstate;
    return DocumentTotalsBar(
      total: invoice == null ? null : total,
      note: _receipt == null
          ? 'Choose the receipt being billed.'
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
        ('Total', total),
      ],
    );
  }

  Widget _billSidePanel(BuildContext context) {
    if (_lines.isEmpty) {
      return const DocumentSidePanel(children: [
        DocumentSideHeading('Billing'),
        DocumentSideNote(
          'Choose the receipt the bill is for. Each line starts at what is '
          'still to be billed, at the receipt price; type a rate only where '
          "the supplier's differs, and check the total against the paper.",
        ),
      ]);
    }
    final int index = _current.clamp(0, _lines.length - 1);
    final PurchaseInvoiceDraftLine line = _lines[index];
    final Product? product = _product(line.productId);
    final Map<String, dynamic>? priced = _pricedLine(index);
    final DocumentPreviewLine? companion = _companion(index);
    final double billing = _number(line.invoiceQuantity);
    final double left = line.outstanding - billing;
    final double taxable = priced == null
        ? _typedTaxable(line)
        : _number(stringValue(priced['gross_amount'])) -
            _number(stringValue(priced['discount_amount']));
    final double tax =
        priced == null ? 0 : _number(stringValue(priced['tax_amount']));
    final bool typedRate = line.unitPrice.trim().isNotEmpty;
    String quantity(double value) =>
        documentQuantity(_PurchaseInvoiceEditorDialogState._trim(value));
    return DocumentSidePanel(children: [
      DocumentSideHeading(
        'Line ${line.lineNumber} · ${product?.name ?? line.description}',
      ),
      DocumentSidePair('Received', documentQuantity(line.receivedQuantity)),
      DocumentSidePair('Billed before', documentQuantity(line.alreadyInvoiced)),
      DocumentSidePair('Billing now', quantity(billing)),
      DocumentSidePair(
        left < 0 ? 'More than received by' : 'Left to bill',
        quantity(left.abs()),
        bold: true,
        tone: left < 0 ? Theme.of(context).colorScheme.error : null,
      ),
      DocumentSidePair(
        'Rate',
        documentMoney(typedRate ? line.unitPrice : line.receiptUnitPrice),
      ),
      DocumentSideNote(
        typedRate ? "as on the supplier's bill" : 'the receipt price',
      ),
      if (companion != null && companion.lastPrice.isNotEmpty) ...[
        DocumentSidePair(
          'Last bill from them',
          documentMoney(companion.lastPrice),
        ),
        DocumentSideNote(
          '${companion.lastInvoiceNumber} on '
          '${_dayOf(companion.lastInvoiceDate)}',
        ),
      ],
      ...documentTaxLines(
        taxable: taxable,
        tax: tax,
        interstate: _preview?.interstate,
      ),
      DocumentField(
        label: 'Line remarks',
        width: 258,
        child: TextFormField(
          key: ValueKey<String>(
            'purchase-invoice-remarks-${_receipt?.id}-$index',
          ),
          initialValue: line.remarks,
          readOnly: _saving,
          decoration: documentBoxDecoration(context),
          onChanged: (value) => line.remarks = value,
        ),
      ),
      const DocumentSideHeading('Stock'),
      DocumentSidePair(
        'Where it was received',
        companion == null ? '—' : documentQuantity(companion.availableQuantity),
      ),
      const DocumentSideNote(
        'the receipt already put it into stock; the bill records what is '
        'owed for it',
      ),
    ]);
  }
}
