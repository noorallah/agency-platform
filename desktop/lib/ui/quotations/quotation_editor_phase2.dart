part of 'quotation_editor_dialog.dart';

/// The new-quotation screen in the phase 2 app, as the owner approved it in
/// the wireframe (view 7, 2026-09-26): one screen -- the header that fills
/// itself from the customer, the lines as a table, the terms, the totals at
/// the foot -- and a side panel that follows the line being typed: where its
/// rate and discount came from, what this customer last paid, the stock, and
/// its tax. Drawn with the pieces the order and invoice screens share
/// (`lib/phase2/document_page.dart`).
///
/// The figures are the save's own: every change asks the server to price
/// the offer exactly as saving would (`POST /quotations/preview`) and save
/// nothing. The state, the payload and every rule about typed and inherited
/// prices are the dialog's; only the layout is new.
extension _Phase2QuotationEditor on _QuotationEditorDialogState {
  List<DocumentColumn> get _columns => [
    const DocumentColumn('#', 28),
    const DocumentColumn('Product (code, name or barcode)', 0),
    const DocumentColumn('HSN', 66),
    const DocumentColumn('Qty', 66, numeric: true),
    const DocumentColumn('Free', 56, numeric: true),
    const DocumentColumn('Unit', 50),
    // The rate says which rate it holds (backlog 64 row 4).
    _rateIncludesTax
        ? const DocumentColumn('Rate incl. GST', 104, numeric: true)
        : const DocumentColumn('Rate', 84, numeric: true),
    const DocumentColumn('Disc %', 60, numeric: true),
    const DocumentColumn('Taxable', 96, numeric: true),
    const DocumentColumn('GST', 48, numeric: true),
    const DocumentColumn('Amount', 104, numeric: true),
    const DocumentColumn('', 28),
  ];

  /// Turn the offer's "Rate includes GST" switch. A rate still showing the
  /// product's own price was never typed, and that price is before tax, so
  /// it is cleared going on (blank takes it, before tax) and put back coming
  /// off.
  void _setRateIncludesTax(bool value) {
    _setState(() {
      _rateIncludesTax = value;
      for (final _LineDraft line in _lines) {
        final Product? product = _product(line.productId);
        if (product == null) continue;
        final String price = line.unitPrice.text.trim();
        if (value && price == product.sellingPrice.trim()) {
          line.unitPrice.clear();
          line.priceEdited = false;
        } else if (!value && price.isEmpty) {
          final double master = double.tryParse(product.sellingPrice) ?? 0;
          if (master > 0) line.unitPrice.text = product.sellingPrice.trim();
        }
      }
    });
    _schedulePreview();
  }

  Widget _rateIncludesTaxField() => DocumentField(
        label: 'Rate includes GST',
        width: 150,
        child: Row(
          children: [
            Switch(
              key: const ValueKey('quotation-rate-includes-tax'),
              value: _rateIncludesTax,
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              onChanged: _setRateIncludesTax,
            ),
            const SizedBox(width: 6),
            Flexible(
              child: Text(
                _rateIncludesTax ? 'Shelf price' : 'Before tax',
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      );

  Widget _phase2Page(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final bool revising = widget.existing != null;
    if (widget.customers.isEmpty || widget.products.isEmpty) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'Nothing to quote yet',
        message: 'A quotation needs a customer to send it to and a product '
            'to price.',
      );
    }
    final String number = widget.existing?.quotationNumber ??
        (_preview?.quotation.quotationNumber.isNotEmpty ?? false
            ? '${_preview!.quotation.quotationNumber} (new)'
            : '');
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.escape): () =>
            leaveDocument(context),
        const SingleActivator(LogicalKeyboardKey.keyS, control: true): () =>
            _finish(print: false),
        const SingleActivator(LogicalKeyboardKey.enter, control: true): _newRow,
      },
      // A scope, not a plain Focus: after a click outside a text box the
      // focus falls to the nearest scope, which was above these
      // shortcuts, so Esc and Ctrl+S did nothing (SC-SO-029).
      child: FocusScope(
        autofocus: true,
        child: Material(
        color: scheme.surface,
        child: Form(
          key: _form,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DocumentPageBand(
                title: revising ? 'Revise quotation' : 'New quotation',
                number: widget.existing?.quotationNumber ?? '',
                chips: [
                  if (number.isNotEmpty && widget.existing == null) number,
                  'Draft',
                ],
                hint: 'Enter next field  ·  Ctrl+Enter new line  ·  '
                    'Ctrl+S save',
                actions: [
                  TextButton(
                    onPressed: () => leaveDocument(context),
                    child: const Text('Cancel'),
                  ),
                  OutlinedButton(
                    key: const ValueKey('quotation-save-print'),
                    onPressed: _saving ? null : () => _finish(print: true),
                    child: const Text('Save & print'),
                  ),
                  FilledButton(
                    key: const ValueKey('quotation-save'),
                    onPressed: _saving ? null : () => _finish(print: false),
                    child: Text(revising ? 'Save revision' : 'Save draft'),
                  ),
                ],
              ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                  child: _errorBanner(),
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
                            _header(context),
                            Expanded(
                              child: DocumentLineTable(
                                columns: _columns,
                                rows: [
                                  for (int i = 0; i < _lines.length; i++)
                                    _row(context, i),
                                ],
                                addLabel: '${_lines.length + 1}     + add a '
                                    'product (Ctrl+Enter)',
                                onAdd: _newRow,
                              ),
                            ),
                            _additionalDetails(
                              maxHeight: 132,
                              padding:
                                  const EdgeInsets.fromLTRB(12, 8, 12, 0),
                            ),
                            _terms(context),
                            _totals(),
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
      ),
    );
  }

  void _newRow() {
    _addLine();
    _current = _lines.length - 1;
    _schedulePreview();
  }

  Customer? get _customer {
    for (final Customer item in widget.customers) {
      if (item.id == _customerId) return item;
    }
    return null;
  }

  Product? _product(String? id) {
    for (final Product item in widget.products) {
      if (item.id == id) return item;
    }
    return null;
  }

  Widget _header(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final Customer? customer = _customer;
    final String place =
        customer == null ? '' : documentCustomerPlace(customer);
    return DocumentHeader(children: [
      DocumentField(
        label: 'Customer (type code, name or phone)',
        width: 420,
        below: customer == null ? null : DocumentCustomerLine(customer),
        child: DropdownMenu<String>(
          key: const ValueKey('quotation-customer'),
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
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(5)),
          ),
          dropdownMenuEntries: [
            for (final Customer item in widget.customers)
              DropdownMenuEntry<String>(
                value: item.id,
                label: '${item.displayName} — ${item.code}'
                    '${item.phone.isEmpty ? '' : '  ${item.phone}'}',
              ),
          ],
          onSelected: (value) {
            _chooseCustomer(value);
            _fillFromCustomer();
            _schedulePreview();
          },
        ),
      ),
      DocumentField(
        label: 'Quotation date',
        auto: true,
        width: 130,
        child: InputDecorator(
          decoration: documentBoxDecoration(context),
          child: Text(documentDate(widget.today)),
        ),
      ),
      DocumentField(
        label: 'Valid until',
        auto: true,
        width: 150,
        child: InkWell(
          key: const ValueKey('quotation-valid-until'),
          onTap: () async {
            await _pickValidUntil();
            _schedulePreview();
          },
          child: InputDecorator(
            decoration: documentBoxDecoration(context).copyWith(
              suffixIcon: const Icon(Icons.event, size: 16),
              suffixIconConstraints:
                  const BoxConstraints(minWidth: 28, minHeight: 20),
            ),
            child: Text(documentDate(_validUntil)),
          ),
        ),
      ),
      DocumentField(
        label: 'Place of supply',
        auto: true,
        width: 190,
        child: InputDecorator(
          decoration: documentBoxDecoration(context),
          child: Text(
            _preview == null
                ? (place.isEmpty ? '—' : place)
                : '${place.isEmpty ? 'Customer' : place}'
                    ' · ${_preview!.interstate ? 'IGST' : 'CGST + SGST'}',
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ),
      DocumentField(
        label: 'Branch · ships from',
        // Only where the firm's defaults chose them: with no default branch
        // the form asks rather than guess (D-QA-17).
        auto: _branchId != null && _warehouseId != null,
        width: 300,
        child: Row(
          // Tops aligned: an error under one box must not push the other.
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
          Expanded(
            child: DropdownButtonFormField<String>(
              isExpanded: true,
              isDense: true,
              initialValue: _branchId,
              decoration: documentBoxDecoration(context, hint: 'Branch'),
              items: [
                for (final BranchRecord item in widget.branches)
                  DropdownMenuItem(
                    value: item.id,
                    child: Text(item.code, overflow: TextOverflow.ellipsis),
                  ),
              ],
              autovalidateMode: AutovalidateMode.onUserInteraction,
              validator: (value) => value == null ? 'Choose a branch.' : null,
              onChanged: (value) {
                _setState(() {
                  _branchId = value;
                  _warehouseId = _warehouseFor(value);
                });
                _schedulePreview();
              },
            ),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: DropdownButtonFormField<String>(
              key: ValueKey<String>('quotation-warehouse-${_branchId ?? ''}'),
              isExpanded: true,
              isDense: true,
              initialValue: _warehouseId,
              decoration: documentBoxDecoration(context, hint: 'Warehouse'),
              items: [
                for (final WarehouseRecord item in _branchWarehouses())
                  DropdownMenuItem(
                    value: item.id,
                    child: Text(item.code, overflow: TextOverflow.ellipsis),
                  ),
              ],
              autovalidateMode: AutovalidateMode.onUserInteraction,
              validator: (value) =>
                  value == null ? 'Choose a warehouse.' : null,
              onChanged: (value) {
                _setState(() => _warehouseId = value);
                _schedulePreview();
              },
            ),
          ),
        ]),
      ),
      _rateIncludesTaxField(),
      DocumentField(
        label: "Customer's reference",
        width: 200,
        child: TextFormField(
          controller: _reference,
          decoration:
              documentBoxDecoration(context, hint: 'their enquiry number'),
        ),
      ),
      DocumentField(
        label: 'Coupon',
        width: 130,
        child: TextFormField(
          key: const ValueKey('quotation-coupon'),
          controller: _coupon,
          decoration: documentBoxDecoration(context),
          textCapitalization: TextCapitalization.characters,
          onChanged: (_) => _schedulePreview(),
        ),
      ),
    ]);
  }

  /// Fill the terms a customer carries, where they are still empty.
  void _fillFromCustomer() {
    final Customer? customer = _customer;
    if (customer == null) return;
    if (_paymentTerms.text.trim().isEmpty && customer.paymentTermsDays > 0) {
      _paymentTerms.text = '${customer.paymentTermsDays} days';
    }
  }

  QuotationLine? _pricedLine(int index) {
    final QuotationPreviewRecord? preview = _preview;
    if (preview == null) return null;
    for (final QuotationLine line in preview.quotation.lines) {
      if (line.lineNumber == _pricedAs[index] &&
          line.productId == _lines[index].productId) {
        return line;
      }
    }
    return null;
  }

  QuotationPreviewLine? _companion(int index) {
    final QuotationPreviewRecord? preview = _preview;
    if (preview == null) return null;
    for (final QuotationPreviewLine line in preview.lines) {
      if (line.lineNumber == _pricedAs[index] &&
          line.productId == _lines[index].productId) {
        return line;
      }
    }
    return null;
  }

  /// A small box inside a table cell.
  Widget _numberBox(
    BuildContext context,
    TextEditingController controller, {
    required String? Function(String?) validator,
    required VoidCallback onTyped,
    String? hint,
  }) =>
      TextFormField(
        controller: controller,
        textAlign: TextAlign.right,
        keyboardType: TextInputType.number,
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontSize: 13),
        decoration: documentCellDecoration(context, hint: hint),
        autovalidateMode: AutovalidateMode.onUserInteraction,
        validator: validator,
        onChanged: (_) {
          // Redrawn at once on what is typed; the server's figures follow.
          _setState(onTyped);
          _schedulePreview();
        },
      );

  Widget _row(BuildContext context, int index) {
    final ThemeData theme = Theme.of(context);
    final _LineDraft line = _lines[index];
    final Product? product = _product(line.productId);
    final QuotationLine? priced = _pricedLine(index);
    final QuotationPreviewLine? companion = _companion(index);
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final double taxable =
        double.tryParse(priced?.netAmount ?? '') ?? line.netOfDiscount;
    final double tax = double.tryParse(priced?.taxAmount ?? '') ?? 0;
    final double rate = taxable > 0 ? tax / taxable * 100 : 0;
    return DocumentLineRow(
      key: ValueKey<String>('quotation-line-$index'),
      columns: _columns,
      current: index == _current,
      onTap: () => _setState(() => _current = index),
      cells: [
        Text('${index + 1}', style: text),
        Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            DropdownMenu<String>(
              key: ValueKey<String>('quotation-line-product-$index'),
              initialSelection: line.productId,
              expandedInsets: EdgeInsets.zero,
              enableFilter: true,
              filterCallback: (entries, filter) =>
                  productEntriesMatching(entries, filter, widget.products),
              searchCallback: productEntryToHighlight,
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
                for (final Product item in widget.products)
                  DropdownMenuEntry<String>(
                    value: item.id,
                    label: '${item.name}  ${item.code}'
                        '${item.barcode.isEmpty ? '' : '  ${item.barcode}'}',
                  ),
              ],
              onSelected: (value) {
                _chooseProduct(line, value);
                _setState(() => _current = index);
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
        _numberBox(
          context,
          line.quantity,
          validator: (value) => _positive(value, 'quantity'),
          onTyped: () {},
        ),
        _numberBox(
          context,
          line.free,
          validator: _freeQuantity,
          onTyped: () {},
        ),
        Text(product?.unit ?? '', style: text),
        _numberBox(
          context,
          line.unitPrice,
          validator: _priceBox,
          hint: _rateIncludesTax ? 'list rate' : null,
          onTyped: () {
            line.priceEdited = true;
            line.priceSource = '';
          },
        ),
        _numberBox(
          context,
          line.discount,
          validator: _percentage,
          // Blank takes the customer's, group's, price list's or a
          // promotion's rate; what it took shows in the side panel.
          hint:
              priced == null ? null : trimDiscountRate(priced.discountPercent),
          onTyped: () => line.discountEdited = true,
        ),
        Text(indianAmount(taxable, full: true), style: text),
        Text(
          priced == null ? '' : '${documentQuantity(rate.toStringAsFixed(1))}%',
          style: text,
        ),
        Text(
          indianAmount(taxable + tax, full: true),
          style: text?.copyWith(fontWeight: FontWeight.w600),
        ),
        IconButton(
          tooltip: _lines.length > 1
              ? 'Remove this line'
              : 'A quotation needs at least one line',
          iconSize: 16,
          visualDensity: VisualDensity.compact,
          onPressed: _lines.length > 1
              ? () {
                  _removeLine(index);
                  if (_current >= _lines.length) _current = _lines.length - 1;
                  _schedulePreview();
                }
              : null,
          icon: const Icon(Icons.close),
        ),
      ],
    );
  }

  Widget _terms(BuildContext context) {
    Widget box(
      String label,
      TextEditingController controller, {
      double width = 180,
      bool number = false,
      bool auto = false,
      String? Function(String?)? validator,
    }) =>
        DocumentField(
          label: label,
          auto: auto,
          width: width,
          child: TextFormField(
            controller: controller,
            keyboardType: number ? TextInputType.number : null,
            decoration: documentBoxDecoration(context),
            autovalidateMode: AutovalidateMode.onUserInteraction,
            validator: validator,
            onChanged: (_) {
              _setState(() {});
              if (number) _schedulePreview();
            },
          ),
        );
    return DocumentTerms(children: [
      box('Payment terms', _paymentTerms, auto: true),
      box('Delivery terms', _deliveryTerms),
      box('Discount on the whole offer %', _billDiscount,
          number: true, width: 190, validator: _percentage),
      box('Delivery charge', _freight, number: true, width: 130),
      box('Remarks', _remarks, width: 260),
    ]);
  }

  Widget _totals() {
    final QuotationPreviewRecord? preview = _preview;
    final double subtotal =
        double.tryParse(preview?.quotation.subtotal ?? '') ?? _quotedBeforeTax;
    final double tax = double.tryParse(preview?.quotation.taxTotal ?? '') ?? 0;
    final double total =
        double.tryParse(preview?.quotation.grandTotal ?? '') ?? subtotal;
    return DocumentTotalsBar(
      total: preview == null ? null : total,
      // D-UI-91: tax follows the customer's state, so nothing is priced
      // until one is chosen -- say so, or the blank tax reads as a fault.
      note: _customerId == null
          ? 'Choose a customer, and the offer is priced with its tax.'
          : _branchId == null || _warehouseId == null
              ? 'Choose the branch and warehouse, and the offer is priced '
                  'with its tax.'
              : 'Totals follow as the lines are priced.',
      figures: [
        ('Taxable', subtotal),
        if (preview != null && preview.interstate)
          ('IGST', tax)
        else ...[
          ('CGST', tax / 2),
          ('SGST', tax / 2),
        ],
        ('Total', total),
      ],
    );
  }

  Widget _sidePanel(BuildContext context) {
    final int index = _current.clamp(0, _lines.length - 1);
    final _LineDraft line = _lines[index];
    final Product? product = _product(line.productId);
    final QuotationLine? priced = _pricedLine(index);
    final QuotationPreviewLine? companion = _companion(index);
    final QuotationPreviewRecord? preview = _preview;
    final Customer? customer = _customer;
    final double taxable =
        double.tryParse(priced?.netAmount ?? '') ?? line.netOfDiscount;
    final double tax = double.tryParse(priced?.taxAmount ?? '') ?? 0;
    return DocumentSidePanel(children: [
      DocumentSideHeading('Line ${index + 1} · ${product?.name ?? ''}'),
      DocumentSidePair('Rate', documentMoney(line.unitPrice.text)),
      DocumentSideNote(
        line.priceEdited
            ? 'typed on this offer'
            : line.priceSource.isNotEmpty
                ? 'from: ${line.priceSource}'
                : "the product's selling price"
                '${(product?.mrp ?? '').isEmpty ? '' : ' (MRP ${documentMoney(product!.mrp)})'}',
      ),
      if (companion != null && companion.lastPrice.isNotEmpty) ...[
        DocumentSidePair(
            'Last to this customer', documentMoney(companion.lastPrice)),
        DocumentSideNote(
          documentLastBilled(companion.lastInvoiceNumber,
              companion.lastInvoiceDate, companion.lastDiscountPercent),
        ),
        // One click, never automatic (backlog 55 G6): the rate only; the
        // discount box stays blank so any arrangement on file still applies.
        if (double.tryParse(companion.lastPrice) !=
            double.tryParse(line.unitPrice.text.trim()))
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              key: const ValueKey('quotation-use-last-price'),
              onPressed: () {
                _setState(() {
                  line.unitPrice.text = documentQuantity(companion.lastPrice);
                  line.priceEdited = true;
                });
                _schedulePreview();
              },
              child: const Text('Use the last price'),
            ),
          ),
      ],
      DocumentSidePair(
        'Discount',
        priced == null || (double.tryParse(priced.discountPercent) ?? 0) == 0
            ? '–'
            : '${trimDiscountRate(priced.discountPercent)}%',
      ),
      DocumentSideNote(
        priced == null
            ? (line.discount.text.trim().isEmpty
                ? 'blank takes any arrangement on file'
                : 'typed on this offer')
            : discountWasTyped(priced.discountSource)
                ? 'typed on this offer'
                : 'from ${discountSourceWords(priced.discountSource)}',
      ),
      // D-SELL-41: silence takes the offer's free goods, a typed zero refuses.
      const DocumentSideNote('Free: blank takes the offer; 0 refuses it.'),
      if ((double.tryParse(line.free.text.trim()) ?? 0) > 0)
        DocumentSidePair(
            'Free goods', '${line.free.text.trim()} ${product?.unit ?? ''}'),
      ...documentTaxLines(
        taxable: taxable,
        tax: tax,
        interstate: preview?.interstate,
      ),
      if (product != null)
        DocumentSideNote([
          if (product.hsnSac.isNotEmpty) 'HSN ${product.hsnSac}',
          if (product.taxProfileGroupCode.isNotEmpty)
            'tax group ${product.taxProfileGroupCode}',
        ].join(' · ')),
      const DocumentSideHeading('Stock'),
      DocumentSidePair(
        'Available where it ships from',
        companion == null ? '—' : documentQuantity(companion.availableQuantity),
      ),
      if (customer != null)
        ...documentCustomerLines(
          context,
          customer,
          thisDocument: double.tryParse(preview?.quotation.grandTotal ?? ''),
          note: 'a quotation itself owes nothing',
        ),
    ]);
  }
}
