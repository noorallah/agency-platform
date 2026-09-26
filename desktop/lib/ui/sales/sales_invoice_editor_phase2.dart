part of 'sales_invoice_editor_dialog.dart';

/// The sales invoice screen in the phase 2 app: the quotation's approved
/// one-screen layout (wireframe view 7) for a bill -- priced as it is typed
/// by `POST /sales-invoices/preview`. Both of the dialog's ways of billing
/// keep their rules: billing a dispatched note or an order (its lines, its
/// prices, only the quantity typed) and, for a firm that bills directly,
/// naming products. Serial numbers are picked in the side panel for the
/// line being typed, rather than under every row.
extension _Phase2SalesInvoiceEditor on _SalesInvoiceEditorDialogState {
  static const List<DocumentColumn> _documentColumns = [
    DocumentColumn('#', 28),
    DocumentColumn('Item', 0),
    DocumentColumn('Left to bill', 84, numeric: true),
    DocumentColumn('Bill qty', 78, numeric: true),
    DocumentColumn('Rate', 84, numeric: true),
    DocumentColumn('Disc %', 60, numeric: true),
    DocumentColumn('Taxable', 96, numeric: true),
    DocumentColumn('GST', 48, numeric: true),
    DocumentColumn('Amount', 104, numeric: true),
  ];

  static const List<DocumentColumn> _directColumns = [
    DocumentColumn('#', 28),
    DocumentColumn('Product (code, name or barcode)', 0),
    DocumentColumn('HSN', 66),
    DocumentColumn('Qty', 66, numeric: true),
    DocumentColumn('Unit', 50),
    DocumentColumn('Rate', 84, numeric: true),
    DocumentColumn('Disc %', 60, numeric: true),
    DocumentColumn('Taxable', 96, numeric: true),
    DocumentColumn('GST', 48, numeric: true),
    DocumentColumn('Amount', 104, numeric: true),
    DocumentColumn('', 28),
  ];

  Widget _phase2Page(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (!_direct && _billable.isEmpty && !_editing) {
      return const WorkspaceEmptyState(
        title: 'Nothing is waiting to be billed',
        message: 'Dispatch a delivery note and it appears here. A note that '
            'has already been invoiced in full does not.',
      );
    }
    final String number = stringValue(_preview?.invoice['invoice_number']);
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.keyS, control: true): () {
          if (!_saving) unawaited(_save());
        },
        const SingleActivator(LogicalKeyboardKey.enter, control: true): () {
          if (!_direct) return;
          _setState(() => _directLines.add(_DirectLine()));
          _current = _directLines.length - 1;
        },
      },
      child: Material(
        color: scheme.surface,
        child: Form(
          key: _form,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DocumentPageBand(
                title: _editing ? 'Sales invoice' : 'New sales invoice',
                chips: [
                  if (number.isNotEmpty) _editing ? number : '$number (new)',
                  'Draft',
                ],
                hint: _direct
                    ? 'Enter next field  ·  Ctrl+Enter new line  ·  Ctrl+S save'
                    : 'Enter next field  ·  Ctrl+S save',
                actions: [
                  TextButton(
                    onPressed:
                        _saving ? null : () => Navigator.of(context).pop(false),
                    child: const Text('Cancel'),
                  ),
                  FilledButton(
                    key: const ValueKey('sales-invoice-save'),
                    onPressed: _saving ? null : () => unawaited(_save()),
                    child: Text(_editing ? 'Save invoice' : 'Save draft'),
                  ),
                ],
              ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                  child: MaterialBanner(
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
                            _invoiceHeader(context),
                            Expanded(
                              child: _direct
                                  ? DocumentLineTable(
                                      columns: _directColumns,
                                      rows: [
                                        for (int i = 0;
                                            i < _directLines.length;
                                            i++)
                                          _directRow(context, i),
                                      ],
                                      addLabel: '${_directLines.length + 1}'
                                          '     + add a product (Ctrl+Enter)',
                                      onAdd: () {
                                        _setState(() =>
                                            _directLines.add(_DirectLine()));
                                        _current = _directLines.length - 1;
                                      },
                                    )
                                  : DocumentLineTable(
                                      columns: _documentColumns,
                                      rows: [
                                        for (int i = 0;
                                            i < (_document?.lines.length ?? 0);
                                            i++)
                                          _documentRow(context, i),
                                      ],
                                    ),
                            ),
                            _invoiceTerms(context),
                            _invoiceTotals(),
                          ],
                        ),
                      ),
                      if (constraints.maxWidth >= DocumentSidePanel.showFrom)
                        _invoiceSidePanel(context),
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

  Customer? get _customer {
    final String? id = _direct ? _customerId : _document?.customerId;
    for (final Customer item in _customers) {
      if (item.id == id) return item;
    }
    return null;
  }

  Product? _product(String? id) {
    for (final Product item in _products) {
      if (item.id == id) return item;
    }
    return null;
  }

  Widget _invoiceHeader(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final Customer? customer = _customer;
    final String place =
        customer == null ? '' : documentCustomerPlace(customer);
    final Map<String, dynamic>? invoice = _preview?.invoice;
    final String placeOfSupply = stringValue(invoice?['place_of_supply']);
    return DocumentHeader(children: [
      if (_direct)
        DocumentField(
          label: 'Customer (type code, name or phone)',
          width: 420,
          below: customer == null ? null : DocumentCustomerLine(customer),
          child: DropdownMenu<String>(
            key: const ValueKey('sales-invoice-customer'),
            initialSelection: _customerId,
            width: 420,
            enableFilter: true,
            requestFocusOnTap: true,
            menuHeight: 320,
            inputDecorationTheme: InputDecorationTheme(
              isDense: true,
              filled: true,
              fillColor: scheme.surfaceContainerLowest,
              contentPadding: const EdgeInsets.symmetric(horizontal: 8),
              constraints: const BoxConstraints(maxHeight: 36),
              border:
                  OutlineInputBorder(borderRadius: BorderRadius.circular(5)),
            ),
            dropdownMenuEntries: [
              for (final Customer item in _customers)
                DropdownMenuEntry<String>(
                  value: item.id,
                  label: '${item.displayName} — ${item.code}'
                      '${item.phone.isEmpty ? '' : '  ${item.phone}'}',
                ),
            ],
            onSelected: (value) {
              _setState(() => _customerId = value);
              _schedulePreview();
            },
          ),
        )
      else
        DocumentField(
          label: 'Bill this delivery note',
          width: 420,
          below: _document == null
              ? null
              : Text(
                  _document!.customerName,
                  style: Theme.of(context)
                      .textTheme
                      .bodySmall
                      ?.copyWith(fontSize: 11, fontWeight: FontWeight.w600),
                ),
          child: DropdownButtonFormField<String>(
            key: const ValueKey('sales-invoice-source'),
            initialValue: _document?.sourceDocumentId,
            isExpanded: true,
            isDense: true,
            decoration: documentBoxDecoration(context,
                hint: 'Only notes with something left to bill'),
            items: [
              for (final BillableDocument item in _pickable)
                DropdownMenuItem(
                  value: item.sourceDocumentId,
                  child: Text(item.label, overflow: TextOverflow.ellipsis),
                ),
            ],
            validator: (value) =>
                value == null ? 'Choose a delivery note.' : null,
            // Fixed while editing: changing which document a draft bills is
            // raising a different invoice, not correcting this one.
            onChanged: _editing
                ? null
                : (value) {
                    _setState(() {
                      final Iterable<BillableDocument> found = _billable
                          .where((item) => item.sourceDocumentId == value);
                      if (found.isNotEmpty) _choose(found.first);
                      _current = 0;
                    });
                    _schedulePreview();
                  },
          ),
        ),
      DocumentField(
        label: 'Invoice date',
        auto: true,
        width: 130,
        child: InputDecorator(
          decoration: documentBoxDecoration(context),
          child: Text(documentDate(widget.today)),
        ),
      ),
      DocumentField(
        label: 'Place of supply',
        auto: true,
        width: 200,
        child: InputDecorator(
          decoration: documentBoxDecoration(context),
          child: Text(
            _preview == null
                ? (place.isEmpty ? '—' : place)
                : '${placeOfSupply.isNotEmpty ? placeOfSupply : place.isEmpty ? 'Customer' : place}'
                    ' · ${_preview!.interstate ? 'IGST' : 'CGST + SGST'}',
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ),
      DocumentField(
        label: "Customer's reference",
        width: 200,
        child: TextFormField(
          controller: _reference,
          decoration: documentBoxDecoration(context, hint: 'their PO number'),
        ),
      ),
    ]);
  }

  Map<String, dynamic>? _pricedBySource(String sourceLineId) {
    for (final dynamic raw in _preview?.invoice['lines'] as List? ?? const []) {
      if (raw is Map &&
          stringValue(raw['source_document_line_id']) == sourceLineId) {
        return Map<String, dynamic>.from(raw);
      }
    }
    return null;
  }

  Map<String, dynamic>? _pricedByNumber(int number, String? productId) {
    for (final dynamic raw in _preview?.invoice['lines'] as List? ?? const []) {
      if (raw is Map &&
          (raw['line_number'] as num?)?.toInt() == number &&
          stringValue(raw['product_id']) == (productId ?? '')) {
        return Map<String, dynamic>.from(raw);
      }
    }
    return null;
  }

  DocumentPreviewLine? _companionFor(int? number, String? productId) {
    for (final DocumentPreviewLine line
        in _preview?.lines ?? const <DocumentPreviewLine>[]) {
      if (line.productId != productId) continue;
      if (number == null || line.lineNumber == number) return line;
    }
    return null;
  }

  /// Where a direct line stands in what is sent: the payload skips lines
  /// with nothing to bill, so its number is its place among the rest.
  int? _sentNumber(int index) {
    int number = 0;
    for (int i = 0; i <= index && i < _directLines.length; i++) {
      final _DirectLine line = _directLines[i];
      final bool sent = (line.productId ?? '').isNotEmpty &&
          (double.tryParse(line.quantity.text.trim()) ?? 0) > 0;
      if (sent) number++;
      if (i == index) return sent ? number : null;
    }
    return null;
  }

  Widget _cellBox(
    BuildContext context,
    TextEditingController? controller, {
    String? Function(String?)? validator,
    String? hint,
  }) =>
      TextFormField(
        controller: controller,
        textAlign: TextAlign.right,
        keyboardType: TextInputType.number,
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontSize: 13),
        decoration: documentCellDecoration(context, hint: hint),
        validator: validator,
        onChanged: (_) {
          _setState(() {});
          _schedulePreview();
        },
      );

  List<Widget> _figures(
    BuildContext context,
    Map<String, dynamic>? priced,
    double estimate,
  ) {
    final TextStyle? text =
        Theme.of(context).textTheme.bodyMedium?.copyWith(fontSize: 13);
    final double taxable =
        double.tryParse(stringValue(priced?['net_amount'])) ?? estimate;
    final double tax = double.tryParse(stringValue(priced?['tax_amount'])) ?? 0;
    final double rate = taxable > 0 ? tax / taxable * 100 : 0;
    return [
      Text(indianAmount(taxable, full: true), style: text),
      Text(
        priced == null ? '' : '${documentQuantity(rate.toStringAsFixed(1))}%',
        style: text,
      ),
      Text(
        indianAmount(taxable + tax, full: true),
        style: text?.copyWith(fontWeight: FontWeight.w600),
      ),
    ];
  }

  Widget _documentRow(BuildContext context, int index) {
    final ThemeData theme = Theme.of(context);
    final BillableLine line = _document!.lines[index];
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final Map<String, dynamic>? priced =
        _pricedBySource(line.sourceDocumentLineId);
    final double estimate = _quantityOf(line) *
        (double.tryParse(line.unitPrice) ?? 0) *
        (1 - (double.tryParse(line.discountPercent) ?? 0) / 100);
    final DocumentPreviewLine? companion = _companionFor(
      (priced?['line_number'] as num?)?.toInt(),
      line.productId,
    );
    final String already = line.alreadyInvoicedQuantity;
    return DocumentLineRow(
      key: ValueKey<String>('sales-invoice-line-$index'),
      columns: _documentColumns,
      current: index == _current,
      onTap: () => _setState(() => _current = index),
      cells: [
        Text('${line.lineNumber}', style: text),
        Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              line.description.isEmpty
                  ? 'Line ${line.lineNumber}'
                  : line.description,
              overflow: TextOverflow.ellipsis,
              style: text,
            ),
            Text(
              'dispatched ${documentQuantity(line.sourceQuantity)}'
              '${already.isEmpty || already == '0' ? '' : ', already billed ${documentQuantity(already)}'}'
              '${companion == null ? '' : '  ·  stock ${documentQuantity(companion.availableQuantity)}'}',
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodySmall?.copyWith(
                fontSize: 11,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
        Text(documentQuantity(line.remainingQuantity), style: text),
        _cellBox(
          context,
          _quantities[line.sourceDocumentLineId],
          validator: (value) => _billableQuantity(value, line),
        ),
        // The note's own price and discount: a bill continues the document
        // it bills rather than repricing it.
        Text(documentMoney(line.unitPrice), style: text),
        Text(
          (double.tryParse(line.discountPercent) ?? 0) > 0
              ? '${trimDiscountRate(line.discountPercent)}%'
              : '',
          style: text,
        ),
        ..._figures(context, priced, estimate),
      ],
    );
  }

  Widget _directRow(BuildContext context, int index) {
    final ThemeData theme = Theme.of(context);
    final _DirectLine line = _directLines[index];
    final Product? product = _product(line.productId);
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final int? number = _sentNumber(index);
    final Map<String, dynamic>? priced =
        number == null ? null : _pricedByNumber(number, line.productId);
    final DocumentPreviewLine? companion =
        number == null ? null : _companionFor(number, line.productId);
    final double estimate = (double.tryParse(line.quantity.text.trim()) ?? 0) *
        (double.tryParse(line.price.text.trim()) ?? 0) *
        (1 - (double.tryParse(line.discount.text.trim()) ?? 0) / 100);
    return DocumentLineRow(
      key: ValueKey<String>('sales-invoice-direct-$index'),
      columns: _directColumns,
      current: index == _current,
      onTap: () => _setState(() => _current = index),
      cells: [
        Text('${index + 1}', style: text),
        Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            DropdownMenu<String>(
              key: ValueKey<String>('sales-invoice-direct-product-$index'),
              initialSelection: line.productId,
              expandedInsets: EdgeInsets.zero,
              enableFilter: true,
              requestFocusOnTap: true,
              menuHeight: 320,
              textStyle: text,
              inputDecorationTheme: const InputDecorationTheme(
                isDense: true,
                border: InputBorder.none,
                contentPadding: EdgeInsets.zero,
                constraints: BoxConstraints(maxHeight: 26),
              ),
              dropdownMenuEntries: [
                for (final Product item in _products)
                  DropdownMenuEntry<String>(
                    value: item.id,
                    label: '${item.name}  ${item.code}'
                        '${item.barcode.isEmpty ? '' : '  ${item.barcode}'}',
                  ),
              ],
              onSelected: (value) {
                _setState(() {
                  line.productId = value;
                  // Units of the last product are not units of this one.
                  line.serialIds.clear();
                  // The product's selling price, where nobody typed one.
                  if (line.price.text.trim().isEmpty) {
                    final Product? chosen = _product(value);
                    final double price =
                        double.tryParse(chosen?.sellingPrice ?? '') ?? 0;
                    if (price > 0) line.price.text = chosen!.sellingPrice;
                  }
                  _current = index;
                });
                if (value != null && _isSerialised(value)) {
                  _loadSerials(value, _directWarehouse);
                }
                _schedulePreview();
              },
            ),
            if (companion != null)
              Text(
                'Stock ${documentQuantity(companion.availableQuantity)}'
                '${companion.lastPrice.isEmpty ? '' : '  ·  last to them '
                    '${documentMoney(companion.lastPrice)}'}',
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall?.copyWith(
                  fontSize: 11,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
          ],
        ),
        Text(product?.hsnSac ?? '', style: text),
        _cellBox(context, line.quantity),
        Text(product?.unit ?? '', style: text),
        _cellBox(context, line.price),
        _cellBox(
          context,
          line.discount,
          validator: _percentage,
          // Never prefilled: blank takes the customer's own rate.
          hint: priced == null
              ? null
              : trimDiscountRate(stringValue(priced['discount_percent'])),
        ),
        ..._figures(context, priced, estimate),
        IconButton(
          tooltip: 'Remove line',
          iconSize: 16,
          visualDensity: VisualDensity.compact,
          onPressed: _directLines.length == 1
              ? null
              : () {
                  _setState(() {
                    _directLines.removeAt(index);
                    if (_current >= _directLines.length) {
                      _current = _directLines.length - 1;
                    }
                  });
                  _schedulePreview();
                },
          icon: const Icon(Icons.close),
        ),
      ],
    );
  }

  Widget _invoiceTerms(BuildContext context) => DocumentTerms(children: [
        DocumentField(
          label: 'Discount on the whole bill %',
          width: 190,
          child: TextFormField(
            controller: _billDiscount,
            keyboardType: TextInputType.number,
            decoration: documentBoxDecoration(context),
            validator: _percentage,
            onChanged: (_) {
              _setState(() {});
              _schedulePreview();
            },
          ),
        ),
        if (_direct)
          DocumentField(
            label: 'Delivery charge',
            width: 130,
            child: TextFormField(
              controller: _freight,
              keyboardType: TextInputType.number,
              decoration: documentBoxDecoration(context),
              onChanged: (_) {
                _setState(() {});
                _schedulePreview();
              },
            ),
          ),
        if (_direct)
          SizedBox(
            width: 420,
            child: Padding(
              padding: const EdgeInsets.only(top: 18),
              child: DocumentSideNote(
                'This firm bills directly: saving raises the order and the '
                'delivery note behind this bill, so the goods leave the '
                'warehouse and their cost is recorded with them.',
              ),
            ),
          ),
      ]);

  Widget _invoiceTotals() {
    final Map<String, dynamic>? invoice = _preview?.invoice;
    final double subtotal =
        double.tryParse(stringValue(invoice?['subtotal'])) ?? _beforeTax;
    final double tax = double.tryParse(stringValue(invoice?['tax_total'])) ?? 0;
    final double total =
        double.tryParse(stringValue(invoice?['grand_total'])) ?? subtotal;
    final bool interstate = _preview?.interstate ?? false;
    return DocumentTotalsBar(
      total: invoice == null ? null : total,
      note: _direct
          ? 'Choose the customer and a product, and the bill is priced with '
              'its tax.'
          : 'Choose what to bill, and it is priced with its tax.',
      figures: [
        ('Taxable', subtotal),
        if (interstate)
          ('IGST', tax)
        else ...[
          ('CGST', tax / 2),
          ('SGST', tax / 2),
        ],
        ('Total', total),
      ],
    );
  }

  Widget _invoiceSidePanel(BuildContext context) {
    final Customer? customer = _customer;
    final List<Widget> line = <Widget>[];
    if (_direct && _directLines.isNotEmpty) {
      final int index = _current.clamp(0, _directLines.length - 1);
      final _DirectLine draft = _directLines[index];
      final Product? product = _product(draft.productId);
      final int? number = _sentNumber(index);
      final Map<String, dynamic>? priced =
          number == null ? null : _pricedByNumber(number, draft.productId);
      final DocumentPreviewLine? companion =
          number == null ? null : _companionFor(number, draft.productId);
      final String source = stringValue(priced?['discount_source']);
      line.addAll([
        DocumentSideHeading('Line ${index + 1} · ${product?.name ?? ''}'),
        DocumentSidePair('Rate', documentMoney(draft.price.text)),
        if (companion != null && companion.lastPrice.isNotEmpty) ...[
          DocumentSidePair(
              'Last to this customer', documentMoney(companion.lastPrice)),
          DocumentSideNote(
              '${companion.lastInvoiceNumber} on ${companion.lastInvoiceDate}'),
        ],
        DocumentSidePair(
          'Discount',
          priced == null ||
                  (double.tryParse(stringValue(priced['discount_percent'])) ??
                          0) ==
                      0
              ? '–'
              : '${trimDiscountRate(stringValue(priced['discount_percent']))}%',
        ),
        DocumentSideNote(
          priced == null
              ? 'blank takes any arrangement on file'
              : discountWasTyped(source) || source.isEmpty
                  ? 'typed on this bill'
                  : 'from ${discountSourceWords(source)}',
        ),
        ...documentTaxLines(
          taxable: double.tryParse(stringValue(priced?['net_amount'])) ?? 0,
          tax: double.tryParse(stringValue(priced?['tax_amount'])) ?? 0,
          interstate: _preview?.interstate,
        ),
        const DocumentSideHeading('Stock'),
        DocumentSidePair(
          'Available',
          companion == null
              ? '—'
              : documentQuantity(companion.availableQuantity),
        ),
        if (draft.productId != null && _isSerialised(draft.productId!)) ...[
          const DocumentSideHeading('Serial numbers'),
          _serialPicker(
            key: ValueKey<String>('serials-direct-$index'),
            productId: draft.productId!,
            warehouseId: _directWarehouse,
            picked: draft.serialIds,
            needed: _SalesInvoiceEditorDialogState._units(draft.quantity.text),
          ),
        ],
      ]);
    } else if (_document != null && _document!.lines.isNotEmpty) {
      final BillableDocument document = _document!;
      final int index = _current.clamp(0, document.lines.length - 1);
      final BillableLine source = document.lines[index];
      final Map<String, dynamic>? priced =
          _pricedBySource(source.sourceDocumentLineId);
      final DocumentPreviewLine? companion = _companionFor(
        (priced?['line_number'] as num?)?.toInt(),
        source.productId,
      );
      line.addAll([
        DocumentSideHeading('Line ${source.lineNumber} · '
            '${source.description.isEmpty ? '' : source.description}'),
        DocumentSidePair('Rate', documentMoney(source.unitPrice)),
        DocumentSideNote('as on ${document.sourceDocumentNumber}; a bill '
            'continues its note rather than repricing it'),
        if (companion != null && companion.lastPrice.isNotEmpty) ...[
          DocumentSidePair(
              'Last to this customer', documentMoney(companion.lastPrice)),
          DocumentSideNote(
              '${companion.lastInvoiceNumber} on ${companion.lastInvoiceDate}'),
        ],
        DocumentSidePair(
          'Discount',
          (double.tryParse(source.discountPercent) ?? 0) > 0
              ? '${trimDiscountRate(source.discountPercent)}%'
              : '–',
        ),
        DocumentSidePair('Dispatched', documentQuantity(source.sourceQuantity)),
        DocumentSidePair(
            'Left to bill', documentQuantity(source.remainingQuantity)),
        ...documentTaxLines(
          taxable: double.tryParse(stringValue(priced?['net_amount'])) ?? 0,
          tax: double.tryParse(stringValue(priced?['tax_amount'])) ?? 0,
          interstate: _preview?.interstate,
        ),
        if (_picksSerials(document, source)) ...[
          const DocumentSideHeading('Serial numbers'),
          _serialPicker(
            key: ValueKey<String>('serials-${source.sourceDocumentLineId}'),
            productId: source.productId,
            warehouseId: source.warehouseId,
            picked: _pickedSerials.putIfAbsent(
                source.sourceDocumentLineId, () => <String>[]),
            needed: _SalesInvoiceEditorDialogState._units(
                _quantities[source.sourceDocumentLineId]?.text ?? ''),
          ),
        ],
      ]);
    }
    return DocumentSidePanel(children: [
      if (line.isEmpty) ...[
        const DocumentSideHeading('The line you are on'),
        DocumentSideNote(_direct
            ? 'Choose the customer and a product: its rate, discount, tax '
                'and stock show here.'
            : 'Choose the delivery note to bill: each line you click shows '
                'its rate, tax and serial numbers here.'),
      ],
      ...line,
      if (customer != null)
        ...documentCustomerLines(
          context,
          customer,
          thisDocument: double.tryParse(
            stringValue(_preview?.invoice['grand_total']),
          ),
          afterLabel: 'After this bill',
        )
      else if (!_direct && _document != null) ...[
        const DocumentSideHeading('Customer'),
        DocumentSidePair('Billed to', _document!.customerName),
      ],
    ]);
  }
}
