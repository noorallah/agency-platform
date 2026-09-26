part of 'sales_order_editor_dialog.dart';

/// The sales order screen in the phase 2 app: the quotation's approved
/// one-screen layout (wireframe view 7) for an order -- the header, the
/// lines as a table, the terms and totals, and the side panel for the line
/// being typed -- priced as it is typed by `POST /sales-orders/preview`.
/// The dialog's state, payload, save and every rule about typed and
/// inherited prices are reused unchanged; only the layout is phase 2's.
extension _Phase2SalesOrderEditor on _SalesOrderEditorDialogState {
  static const List<DocumentColumn> _columns = [
    DocumentColumn('#', 28),
    DocumentColumn('Product (code, name or barcode)', 0),
    DocumentColumn('HSN', 66),
    DocumentColumn('Qty', 66, numeric: true),
    DocumentColumn('Free', 56, numeric: true),
    DocumentColumn('Unit', 50),
    DocumentColumn('Rate', 84, numeric: true),
    DocumentColumn('Disc %', 60, numeric: true),
    DocumentColumn('Disc amt', 76, numeric: true),
    DocumentColumn('Taxable', 92, numeric: true),
    DocumentColumn('GST', 48, numeric: true),
    DocumentColumn('Amount', 100, numeric: true),
    DocumentColumn('', 28),
  ];

  Widget _phase2Page(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    final bool nothingToOrder =
        (_customers.isEmpty || _products.isEmpty) && !_editing;
    if (nothingToOrder) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'Nothing to order yet',
        message: 'An order needs a customer to take it from and a product to '
            'sell.',
      );
    }
    final String number = stringValue(_preview?.order['order_number']);
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.keyS, control: true): () {
          if (!_locked && !_saving) unawaited(_save());
        },
        const SingleActivator(LogicalKeyboardKey.enter, control: true): () {
          if (_locked) return;
          _addLine();
          _current = _lines.length - 1;
          _schedulePreview();
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
                title: _editing ? 'Sales order' : 'New sales order',
                chips: [
                  if (number.isNotEmpty) _editing ? number : '$number (new)',
                  _status == 'DRAFT' ? 'Draft' : _status,
                ],
                hint: _locked
                    ? ''
                    : 'Enter next field  ·  Ctrl+Enter new line  ·  '
                        'Ctrl+S save',
                actions: [
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(false),
                    child: Text(_locked ? 'Close' : 'Cancel'),
                  ),
                  if (!_locked)
                    FilledButton(
                      key: const ValueKey('sales-order-save'),
                      onPressed: _saving ? null : () => unawaited(_save()),
                      child: Text(_editing ? 'Save order' : 'Save draft'),
                    ),
                ],
              ),
              if (_locked || _error != null)
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                  child: MaterialBanner(
                    backgroundColor:
                        _error == null ? scheme.surfaceContainerHigh : null,
                    contentTextStyle: theme.textTheme.bodyMedium,
                    content: Text(
                      _error ??
                          'This order is $_status, so it can no longer be '
                              'rewritten. Its lines are what stock and credit '
                              'were committed against.',
                    ),
                    actions: [
                      if (_error != null)
                        TextButton(
                          onPressed: () => _setState(() => _error = null),
                          child: const Text('Dismiss'),
                        )
                      else
                        const SizedBox.shrink(),
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
                            _orderHeader(context),
                            Expanded(
                              child: DocumentLineTable(
                                columns: _columns,
                                rows: [
                                  for (int i = 0; i < _lines.length; i++)
                                    _orderRow(context, i),
                                ],
                                addLabel: _locked
                                    ? null
                                    : '${_lines.length + 1}     + add a '
                                        'product (Ctrl+Enter)',
                                onAdd: () {
                                  _addLine();
                                  _current = _lines.length - 1;
                                  _schedulePreview();
                                },
                              ),
                            ),
                            _orderTerms(context),
                            _orderTotals(),
                          ],
                        ),
                      ),
                      if (constraints.maxWidth >= DocumentSidePanel.showFrom)
                        _orderSidePanel(context),
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
    for (final Customer item in _customers) {
      if (item.id == _customerId) return item;
    }
    return null;
  }

  Product? _product(String? id) {
    for (final Product item in _products) {
      if (item.id == id) return item;
    }
    return null;
  }

  Widget _dateBox(
    BuildContext context, {
    required Key key,
    required String text,
    required VoidCallback onTap,
    VoidCallback? onClear,
  }) =>
      InkWell(
        key: key,
        onTap: _locked ? null : onTap,
        child: InputDecorator(
          decoration: documentBoxDecoration(context).copyWith(
            suffixIcon: onClear != null && !_locked
                ? IconButton(
                    tooltip: 'Clear',
                    iconSize: 14,
                    visualDensity: VisualDensity.compact,
                    onPressed: onClear,
                    icon: const Icon(Icons.close),
                  )
                : const Icon(Icons.event, size: 16),
            suffixIconConstraints:
                const BoxConstraints(minWidth: 28, minHeight: 20),
          ),
          child: Text(text),
        ),
      );

  Widget _orderHeader(BuildContext context) {
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
          key: const ValueKey('sales-order-customer'),
          initialSelection: _customerId,
          width: 420,
          // Fixed while correcting: an order for a different shop is a
          // different order, and its credit was checked against this one.
          enabled: !_editing && !_locked,
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
      ),
      DocumentField(
        label: 'Order date',
        auto: !_editing,
        width: 140,
        child: _dateBox(
          context,
          key: const ValueKey('sales-order-date'),
          text: documentDate(_orderDate),
          onTap: () async {
            await _pickOrderDate();
            _schedulePreview();
          },
        ),
      ),
      DocumentField(
        label: 'Wanted by',
        width: 150,
        child: _dateBox(
          context,
          key: const ValueKey('sales-order-delivery-date'),
          text: _deliveryDate == null ? '—' : documentDate(_deliveryDate!),
          onTap: () async {
            await _pickDeliveryDate();
            _schedulePreview();
          },
          onClear: _deliveryDate == null
              ? null
              : () => _setState(() => _deliveryDate = null),
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
                : '${place.isEmpty ? 'Customer' : place} · '
                    '${_preview!.interstate ? 'IGST' : 'CGST + SGST'}',
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ),
      DocumentField(
        label: 'Salesman',
        width: 200,
        child: DropdownButtonFormField<String?>(
          key: const ValueKey('sales-order-salesman'),
          initialValue: _salesmanId,
          isExpanded: true,
          isDense: true,
          decoration: documentBoxDecoration(context),
          items: [
            const DropdownMenuItem<String?>(
              value: null,
              child: Text('Nobody', overflow: TextOverflow.ellipsis),
            ),
            for (final FirmMember item in _members)
              DropdownMenuItem<String?>(
                value: item.userId,
                child: Text(item.label, overflow: TextOverflow.ellipsis),
              ),
            if (_salesmanId != null &&
                !_members.any((item) => item.userId == _salesmanId))
              DropdownMenuItem<String?>(
                value: _salesmanId,
                child: Text(_salesmanId!, overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged:
              _locked ? null : (value) => _setState(() => _salesmanId = value),
        ),
      ),
      DocumentField(
        label: 'Branch · ships from',
        // Only where the firm's defaults chose them: with no default branch
        // the form asks rather than guess (D-QA-17).
        auto: !_editing && _branchId != null && _warehouseId != null,
        width: 300,
        child: Row(children: [
          Expanded(
            child: DropdownButtonFormField<String>(
              key: const ValueKey('sales-order-branch'),
              isExpanded: true,
              isDense: true,
              initialValue: _branchId,
              decoration: documentBoxDecoration(context, hint: 'Branch'),
              items: _items(
                [
                  for (final BranchRecord item in _branches)
                    (id: item.id, label: item.code),
                ],
                _branchId,
              ),
              validator: (value) => value == null ? 'Choose a branch.' : null,
              onChanged: _locked
                  ? null
                  : (value) {
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
              key: ValueKey<String>('sales-order-warehouse-${_branchId ?? ''}'),
              isExpanded: true,
              isDense: true,
              initialValue: _warehouseId,
              decoration: documentBoxDecoration(context, hint: 'Warehouse'),
              items: _items(
                [
                  for (final WarehouseRecord item in _warehouses)
                    if (_branchId == null ||
                        item.branchId == _branchId ||
                        item.id == _warehouseId)
                      (id: item.id, label: item.code),
                ],
                _warehouseId,
              ),
              validator: (value) =>
                  value == null ? 'Choose a warehouse.' : null,
              onChanged: _locked
                  ? null
                  : (value) {
                      _setState(() => _warehouseId = value);
                      _schedulePreview();
                    },
            ),
          ),
        ]),
      ),
      DocumentField(
        label: "Customer's reference",
        width: 180,
        child: TextFormField(
          controller: _customerReference,
          readOnly: _locked,
          decoration: documentBoxDecoration(context, hint: 'their PO number'),
        ),
      ),
      DocumentField(
        label: 'Our reference',
        width: 160,
        child: TextFormField(
          controller: _reference,
          readOnly: _locked,
          decoration: documentBoxDecoration(context),
        ),
      ),
      DocumentField(
        label: 'Coupon',
        width: 130,
        child: TextFormField(
          controller: _coupon,
          readOnly: _locked,
          decoration: documentBoxDecoration(context),
          onChanged: (_) => _schedulePreview(),
        ),
      ),
    ]);
  }

  Map<String, dynamic>? _pricedLine(int index) {
    final Map<String, dynamic>? order = _preview?.order;
    if (order == null) return null;
    for (final dynamic raw in order['lines'] as List? ?? const []) {
      if (raw is! Map) continue;
      if ((raw['line_number'] as num?)?.toInt() == index + 1 &&
          stringValue(raw['product_id']) == (_lines[index].productId ?? '')) {
        return Map<String, dynamic>.from(raw);
      }
    }
    return null;
  }

  DocumentPreviewLine? _companion(int index) {
    for (final DocumentPreviewLine line
        in _preview?.lines ?? const <DocumentPreviewLine>[]) {
      if (line.lineNumber == index + 1 &&
          line.productId == _lines[index].productId) {
        return line;
      }
    }
    return null;
  }

  Widget _cellBox(
    BuildContext context,
    TextEditingController controller, {
    required String? Function(String?) validator,
    VoidCallback? onTyped,
    String? hint,
  }) =>
      TextFormField(
        controller: controller,
        readOnly: _locked,
        textAlign: TextAlign.right,
        keyboardType: TextInputType.number,
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontSize: 13),
        decoration: documentCellDecoration(context, hint: hint),
        validator: validator,
        onChanged: (_) {
          // Redrawn at once on what is typed; the server's figures follow.
          _setState(() => onTyped?.call());
          _schedulePreview();
        },
      );

  Widget _orderRow(BuildContext context, int index) {
    final ThemeData theme = Theme.of(context);
    final _LineDraft line = _lines[index];
    final Product? product = _product(line.productId);
    final Map<String, dynamic>? priced = _pricedLine(index);
    final DocumentPreviewLine? companion = _companion(index);
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final double taxable =
        double.tryParse(stringValue(priced?['net_amount'])) ??
            line.netOfDiscount;
    final double tax = double.tryParse(stringValue(priced?['tax_amount'])) ?? 0;
    final double rate = taxable > 0 ? tax / taxable * 100 : 0;
    return DocumentLineRow(
      key: ValueKey<String>('sales-order-line-$index'),
      columns: _columns,
      current: index == _current,
      onTap: () => _setState(() => _current = index),
      cells: [
        Text('${index + 1}', style: text),
        Padding(
          padding: const EdgeInsets.only(right: 8),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              DropdownMenu<String>(
                key: ValueKey<String>('sales-order-line-product-$index'),
                initialSelection: line.productId,
                enabled: !_locked,
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
        ),
        Text(product?.hsnSac ?? '', style: text),
        _cellBox(
          context,
          line.quantity,
          validator: (value) => _positive(value, 'quantity'),
        ),
        _cellBox(context, line.free, validator: _quantityOrBlank),
        Text(product?.unit ?? '', style: text),
        _cellBox(
          context,
          line.unitPrice,
          validator: (value) => _positive(value, 'price'),
          onTyped: () => line.priceEdited = true,
        ),
        _cellBox(
          context,
          line.discountPercent,
          validator: _percentage,
          // Blank takes the customer's, group's, price list's or a
          // promotion's rate; what it took shows in the side panel.
          hint: priced == null
              ? null
              : trimDiscountRate(stringValue(priced['discount_percent'])),
        ),
        _cellBox(
          context,
          line.discountAmount,
          validator: (value) => _discountAmount(value, line.gross, 'this line'),
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
              : 'An order needs at least one line',
          iconSize: 16,
          visualDensity: VisualDensity.compact,
          onPressed: _lines.length > 1 && !_locked
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

  Widget _orderTerms(BuildContext context) {
    Widget box(
      String label,
      TextEditingController controller, {
      double width = 180,
      bool figure = false,
      String? Function(String?)? validator,
      String? hint,
    }) =>
        DocumentField(
          label: label,
          width: width,
          child: TextFormField(
            controller: controller,
            readOnly: _locked,
            keyboardType: figure ? TextInputType.number : null,
            decoration: documentBoxDecoration(context, hint: hint),
            validator: validator,
            onChanged: (_) {
              _setState(() {});
              if (figure) _schedulePreview();
            },
          ),
        );
    return DocumentTerms(children: [
      box('Discount on the whole order %', _billDiscountPercent,
          width: 190, figure: true, validator: _percentage),
      box('Or an amount off the whole order', _billDiscountAmount,
          width: 200,
          figure: true,
          hint: _billResolvedHelper.isEmpty ? null : 'blank prices it afresh',
          validator: (value) =>
              _discountAmount(value, _beforeTax + 1e9, 'the order')),
      box('Delivery charge', _freightAmount, width: 130, figure: true),
      box('Remarks', _remarks, width: 280),
    ]);
  }

  Widget _orderTotals() {
    final Map<String, dynamic>? order = _preview?.order;
    final double subtotal =
        double.tryParse(stringValue(order?['subtotal'])) ?? _beforeTax;
    final double tax = double.tryParse(stringValue(order?['tax_total'])) ?? 0;
    final double total =
        double.tryParse(stringValue(order?['grand_total'])) ?? subtotal;
    final bool interstate = _preview?.interstate ?? false;
    return DocumentTotalsBar(
      total: order == null ? null : total,
      note: _branchId == null || _warehouseId == null
          ? 'Choose the branch and warehouse, and the order is priced with '
              'its tax.'
          : 'Totals follow as the lines are priced.',
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

  Widget _orderSidePanel(BuildContext context) {
    final int index = _current.clamp(0, _lines.length - 1);
    final _LineDraft line = _lines[index];
    final Product? product = _product(line.productId);
    final Map<String, dynamic>? priced = _pricedLine(index);
    final DocumentPreviewLine? companion = _companion(index);
    final Customer? customer = _customer;
    final double taxable =
        double.tryParse(stringValue(priced?['net_amount'])) ??
            line.netOfDiscount;
    final double tax = double.tryParse(stringValue(priced?['tax_amount'])) ?? 0;
    final String source = stringValue(priced?['discount_source']);
    final double discount =
        double.tryParse(stringValue(priced?['discount_percent'])) ?? 0;
    return DocumentSidePanel(children: [
      DocumentSideHeading('Line ${index + 1} · ${product?.name ?? ''}'),
      DocumentSidePair('Rate', documentMoney(line.unitPrice.text)),
      DocumentSideNote(
        line.priceEdited
            ? 'as typed on this order'
            : "the product's selling price"
                '${(product?.mrp ?? '').isEmpty ? '' : ' (MRP ${documentMoney(product!.mrp)})'}',
      ),
      if (companion != null && companion.lastPrice.isNotEmpty) ...[
        DocumentSidePair(
            'Last to this customer', documentMoney(companion.lastPrice)),
        DocumentSideNote(
          '${companion.lastInvoiceNumber} on '
          '${DateTime.tryParse(companion.lastInvoiceDate) == null ? companion.lastInvoiceDate : documentDate(DateTime.parse(companion.lastInvoiceDate))}',
        ),
      ],
      DocumentSidePair(
        'Discount',
        priced == null || discount == 0
            ? '–'
            : '${trimDiscountRate(stringValue(priced['discount_percent']))}%',
      ),
      DocumentSideNote(
        priced == null
            ? (line.discountPercent.text.trim().isEmpty &&
                    line.discountAmount.text.trim().isEmpty
                ? 'blank takes any arrangement on file'
                : 'typed on this order')
            : discountWasTyped(source)
                ? 'typed on this order'
                : 'from ${discountSourceWords(source)}',
      ),
      if ((double.tryParse(line.free.text.trim()) ?? 0) > 0)
        DocumentSidePair(
            'Free goods', '${line.free.text.trim()} ${product?.unit ?? ''}'),
      ...documentTaxLines(
        taxable: taxable,
        tax: tax,
        interstate: _preview?.interstate,
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
      const DocumentSideNote('approving the order reserves it'),
      if (customer != null)
        ...documentCustomerLines(
          context,
          customer,
          thisDocument: double.tryParse(
            stringValue(_preview?.order['grand_total']),
          ),
          afterLabel: 'Once it is billed',
          note: 'an order owes nothing until it is billed',
        ),
    ]);
  }
}
