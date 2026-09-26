part of 'quotation_editor_dialog.dart';

/// The new-quotation screen in the phase 2 app, as the owner approved it in
/// the wireframe (view 7, 2026-09-26): one screen -- the header that fills
/// itself from the customer, the lines as a table, the terms, the totals at
/// the foot -- and a side panel that follows the line being typed: where its
/// rate and discount came from, what this customer last paid, the stock, and
/// its tax.
///
/// The figures are the save's own: every change asks the server to price
/// the offer exactly as saving would (`POST /quotations/preview`) and save
/// nothing, so what is shown is what will be stored. The state, the payload
/// and every rule about typed and inherited prices are the dialog's; only
/// the layout is new.
extension _Phase2QuotationEditor on _QuotationEditorDialogState {
  Widget _phase2Page(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
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
        const SingleActivator(LogicalKeyboardKey.keyS, control: true): () =>
            _finish(print: false),
        const SingleActivator(LogicalKeyboardKey.enter, control: true): () {
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
              _band(
                context,
                Row(children: [
                  Text(
                    revising ? 'Revise quotation' : 'New quotation',
                    style: theme.textTheme.titleMedium
                        ?.copyWith(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(width: 12),
                  if (number.isNotEmpty) _chip(context, number),
                  _chip(context, 'Draft'),
                  // The key hints give way first on a narrow window.
                  Expanded(
                    child: Align(
                      alignment: Alignment.centerRight,
                      child: Text(
                        'Enter next field  ·  Ctrl+Enter new line  ·  '
                        'Ctrl+S save',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.bodySmall
                            ?.copyWith(color: scheme.onSurfaceVariant),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Phase2ButtonTheme(
                    child: Row(children: [
                      TextButton(
                        onPressed: () => Navigator.of(context).pop(),
                        child: const Text('Cancel'),
                      ),
                      const SizedBox(width: 6),
                      OutlinedButton(
                        key: const ValueKey('quotation-save-print'),
                        onPressed: () => _finish(print: true),
                        child: const Text('Save & print'),
                      ),
                      const SizedBox(width: 6),
                      FilledButton(
                        key: const ValueKey('quotation-save'),
                        onPressed: () => _finish(print: false),
                        child: Text(revising ? 'Save revision' : 'Save draft'),
                      ),
                    ]),
                  ),
                ]),
              ),
              Expanded(
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    // The side panel goes first on a narrow window (4.11).
                    final bool side = constraints.maxWidth >= 1150;
                    return Row(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              _header(context),
                              Expanded(child: _table(context)),
                              _terms(context),
                              _totals(context),
                            ],
                          ),
                        ),
                        if (side)
                          SizedBox(width: 290, child: _sidePanel(context)),
                      ],
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Save, and print the saved offer if asked: handed back to the list,
  /// which owns the save and the printer.
  void _finish({required bool print}) {
    final Json? payload = _payload();
    if (payload == null) return;
    Navigator.of(context).pop(<String, dynamic>{
      ...payload,
      if (print) QuotationEditorDialog.printAfterSave: true,
    });
  }

  Widget _band(BuildContext context, Widget child) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLowest,
        border: Border(bottom: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 6, 12, 6),
        child: child,
      ),
    );
  }

  Widget _chip(BuildContext context, String text) => Padding(
        padding: const EdgeInsets.only(right: 8),
        child: Text(
          text,
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                fontSize: 13,
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
        ),
      );

  /// A small labelled box, as the wireframe's header draws them.
  Widget _field(
    BuildContext context, {
    required String label,
    required Widget child,
    bool auto = false,
    double width = 200,
    Widget? below,
  }) {
    final ThemeData theme = Theme.of(context);
    return SizedBox(
      width: width,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(children: [
            Flexible(
              child: Text(
                label,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall?.copyWith(
                  fontSize: 11,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
            if (auto) ...[
              const SizedBox(width: 4),
              Text(
                'auto',
                style: theme.textTheme.bodySmall?.copyWith(
                  fontSize: 10,
                  color: context.semanticColors.success,
                ),
              ),
            ],
          ]),
          const SizedBox(height: 3),
          child,
          if (below != null) ...[const SizedBox(height: 3), below],
        ],
      ),
    );
  }

  InputDecoration _boxDecoration(BuildContext context, {String? hint}) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final OutlineInputBorder edge = OutlineInputBorder(
      borderRadius: BorderRadius.circular(5),
      borderSide: BorderSide(color: scheme.outlineVariant),
    );
    return InputDecoration(
      isDense: true,
      hintText: hint,
      filled: true,
      fillColor: scheme.surfaceContainerLowest,
      contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 9),
      border: edge,
      enabledBorder: edge,
      focusedBorder: edge.copyWith(
        borderSide: BorderSide(color: scheme.primary, width: 1.5),
      ),
    );
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

  /// Where the customer is, from their billing address, else the first.
  String get _customerPlace {
    final Customer? customer = _customer;
    if (customer == null || customer.addresses.isEmpty) return '';
    final CustomerAddress address = customer.addresses.firstWhere(
      (item) => item.isDefaultBilling,
      orElse: () => customer.addresses.first,
    );
    return [address.city, address.state]
        .where((part) => part.trim().isNotEmpty)
        .join(', ');
  }

  Widget _header(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final Customer? customer = _customer;
    final double balance =
        double.tryParse(customer?.currentOutstanding ?? '') ?? 0;
    final double limit = double.tryParse(customer?.creditLimit ?? '') ?? 0;
    final bool high = limit > 0 && balance >= limit * .8;
    final TextStyle? info = theme.textTheme.bodySmall?.copyWith(fontSize: 11);
    return DecoratedBox(
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
        child: Wrap(
          spacing: 14,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.start,
          children: [
            _field(
              context,
              label: 'Customer (type code, name or phone)',
              width: 420,
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
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(5),
                  ),
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
              below: customer == null
                  ? null
                  : Text.rich(
                      TextSpan(style: info, children: [
                        if (customer.gstNumber.isNotEmpty) ...[
                          const TextSpan(text: 'GSTIN '),
                          TextSpan(
                            text: customer.gstNumber,
                            style: const TextStyle(fontWeight: FontWeight.w600),
                          ),
                          const TextSpan(text: '  ·  '),
                        ],
                        if (_customerPlace.isNotEmpty)
                          TextSpan(text: '$_customerPlace  ·  '),
                        const TextSpan(text: 'bal '),
                        TextSpan(
                          text: indianAmount(balance, full: true),
                          style: TextStyle(
                            fontWeight: FontWeight.w600,
                            color: high ? scheme.error : null,
                          ),
                        ),
                        if (limit > 0)
                          TextSpan(
                            text: ' / limit ${indianAmount(limit, full: true)}',
                          ),
                      ]),
                    ),
            ),
            _field(
              context,
              label: 'Quotation date',
              auto: true,
              width: 130,
              child: InputDecorator(
                decoration: _boxDecoration(context),
                child: Text(_display(widget.today)),
              ),
            ),
            _field(
              context,
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
                  decoration: _boxDecoration(context).copyWith(
                    suffixIcon: const Icon(Icons.event, size: 16),
                    suffixIconConstraints:
                        const BoxConstraints(minWidth: 28, minHeight: 20),
                  ),
                  child: Text(_display(_validUntil)),
                ),
              ),
            ),
            _field(
              context,
              label: 'Place of supply',
              auto: true,
              width: 190,
              child: InputDecorator(
                decoration: _boxDecoration(context),
                child: Text(
                  _preview == null
                      ? (_customerPlace.isEmpty ? '—' : _customerPlace)
                      : '${_customerPlace.isEmpty ? 'Customer' : _customerPlace}'
                          ' · ${_preview!.interstate ? 'IGST' : 'CGST + SGST'}',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ),
            _field(
              context,
              label: 'Branch · ships from',
              // Only where the firm's defaults chose them: with no default
              // branch the form asks rather than guess (D-QA-17).
              auto: _branchId != null && _warehouseId != null,
              width: 300,
              child: Row(children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    isExpanded: true,
                    isDense: true,
                    initialValue: _branchId,
                    decoration: _boxDecoration(context, hint: 'Branch'),
                    items: [
                      for (final BranchRecord item in widget.branches)
                        DropdownMenuItem(
                          value: item.id,
                          child:
                              Text(item.code, overflow: TextOverflow.ellipsis),
                        ),
                    ],
                    validator: (value) =>
                        value == null ? 'Choose a branch.' : null,
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
                    key: ValueKey<String>(
                      'quotation-warehouse-${_branchId ?? ''}',
                    ),
                    isExpanded: true,
                    isDense: true,
                    initialValue: _warehouseId,
                    decoration: _boxDecoration(context, hint: 'Warehouse'),
                    items: [
                      for (final WarehouseRecord item in _branchWarehouses())
                        DropdownMenuItem(
                          value: item.id,
                          child:
                              Text(item.code, overflow: TextOverflow.ellipsis),
                        ),
                    ],
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
            _field(
              context,
              label: "Customer's reference",
              width: 200,
              child: TextFormField(
                controller: _reference,
                decoration:
                    _boxDecoration(context, hint: 'their enquiry number'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Fill the terms a customer carries, where they are still empty.
  void _fillFromCustomer() {
    final Customer? customer = _customer;
    if (customer == null) return;
    if (_paymentTerms.text.trim().isEmpty && customer.paymentTermsDays > 0) {
      _paymentTerms.text = '${customer.paymentTermsDays} days';
    }
  }

  static const List<(String, double, bool)> _columns = [
    ('#', 32, false),
    ('Product (code, name or barcode)', 0, false),
    ('HSN', 70, false),
    ('Qty', 70, true),
    ('Free', 60, true),
    ('Unit', 56, false),
    ('Rate', 90, true),
    ('Disc %', 64, true),
    ('Taxable', 96, true),
    ('GST', 54, true),
    ('Amount', 104, true),
    ('', 32, false),
  ];

  Widget _cell(BuildContext context, int index, Widget child) {
    final (String _, double width, bool numeric) = _columns[index];
    final Widget aligned = Align(
      alignment: numeric ? Alignment.centerRight : Alignment.centerLeft,
      child: child,
    );
    // A gap after every column, so "Free" and "Unit" do not run together.
    final Widget spaced = Padding(
      padding: const EdgeInsets.only(right: 8),
      child: aligned,
    );
    return width == 0
        ? Expanded(child: spaced)
        : SizedBox(width: width + 8, child: spaced);
  }

  Widget _table(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final TextStyle? heading = theme.textTheme.labelMedium?.copyWith(
      fontSize: 12,
      fontWeight: FontWeight.w600,
      color: scheme.onSurfaceVariant,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          height: 34,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            color: scheme.surfaceContainerLow,
            border: Border(bottom: BorderSide(color: scheme.outlineVariant)),
          ),
          child: Row(children: [
            for (int i = 0; i < _columns.length; i++)
              _cell(context, i, Text(_columns[i].$1, style: heading)),
          ]),
        ),
        Expanded(
          child: ListView(
            children: [
              for (int index = 0; index < _lines.length; index++)
                _row(context, index),
              InkWell(
                key: const ValueKey('quotation-add-line'),
                onTap: () {
                  _addLine();
                  _current = _lines.length - 1;
                  _schedulePreview();
                },
                child: Container(
                  height: 36,
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  alignment: Alignment.centerLeft,
                  child: Text(
                    '${_lines.length + 1}     + add a product (Ctrl+Enter)',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      fontSize: 13,
                      fontStyle: FontStyle.italic,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  QuotationLine? _pricedLine(int index) {
    final QuotationPreviewRecord? preview = _preview;
    if (preview == null) return null;
    for (final QuotationLine line in preview.quotation.lines) {
      if (line.lineNumber == index + 1 &&
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
      if (line.lineNumber == index + 1 &&
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
        decoration: _boxDecoration(context, hint: hint).copyWith(
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 6, vertical: 7),
          errorStyle: const TextStyle(height: 0, fontSize: 0),
        ),
        validator: validator,
        onChanged: (_) {
          // Redrawn at once on what is typed; the server's figures follow.
          _setState(onTyped);
          _schedulePreview();
        },
      );

  Widget _row(BuildContext context, int index) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final _LineDraft line = _lines[index];
    final Product? product = _product(line.productId);
    final QuotationLine? priced = _pricedLine(index);
    final QuotationPreviewLine? companion = _companion(index);
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final TextStyle? hint = theme.textTheme.bodySmall
        ?.copyWith(fontSize: 11, color: scheme.onSurfaceVariant);
    final double taxable =
        double.tryParse(priced?.netAmount ?? '') ?? line.netOfDiscount;
    final double tax = double.tryParse(priced?.taxAmount ?? '') ?? 0;
    final double rate = taxable > 0 ? tax / taxable * 100 : 0;
    final bool current = index == _current;
    return InkWell(
      key: ValueKey<String>('quotation-line-$index'),
      onTap: () => _setState(() => _current = index),
      child: Container(
        height: 52,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        decoration: BoxDecoration(
          color: current
              ? Color.alphaBlend(
                  scheme.primary.withValues(alpha: .10),
                  scheme.surfaceContainerLowest,
                )
              : scheme.surfaceContainerLowest,
          border: Border(
            bottom: BorderSide(color: scheme.surfaceContainerHighest),
            left: BorderSide(
              color: current ? scheme.primary : Colors.transparent,
              width: 3,
            ),
          ),
        ),
        child: Row(children: [
          _cell(context, 0, Text('${index + 1}', style: text)),
          _cell(
            context,
            1,
            Padding(
              padding: const EdgeInsets.only(right: 12),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  DropdownMenu<String>(
                    key: ValueKey<String>('quotation-line-product-$index'),
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
                      'Stock ${_trim(companion.availableQuantity)}'
                      '${companion.lastPrice.isEmpty ? '' : '  ·  last to them ${_money(companion.lastPrice)}'}',
                      style: hint,
                      overflow: TextOverflow.ellipsis,
                    ),
                ],
              ),
            ),
          ),
          _cell(context, 2, Text(product?.hsnSac ?? '', style: text)),
          _cell(
            context,
            3,
            _numberBox(
              context,
              line.quantity,
              validator: (value) => _positive(value, 'quantity'),
              onTyped: () {},
            ),
          ),
          _cell(
            context,
            4,
            _numberBox(
              context,
              line.free,
              validator: _freeQuantity,
              onTyped: () {},
            ),
          ),
          _cell(context, 5, Text(product?.unit ?? '', style: text)),
          _cell(
            context,
            6,
            _numberBox(
              context,
              line.unitPrice,
              validator: (value) => _positive(value, 'price'),
              onTyped: () => line.priceEdited = true,
            ),
          ),
          _cell(
            context,
            7,
            _numberBox(
              context,
              line.discount,
              validator: _percentage,
              // Blank takes the customer's, group's, price list's or a
              // promotion's rate; what it took shows in the side panel.
              hint: priced == null
                  ? null
                  : trimDiscountRate(priced.discountPercent),
              onTyped: () => line.discountEdited = true,
            ),
          ),
          _cell(
              context, 8, Text(indianAmount(taxable, full: true), style: text)),
          _cell(
            context,
            9,
            Text(priced == null ? '' : '${_trim(rate.toStringAsFixed(1))}%',
                style: text),
          ),
          _cell(
            context,
            10,
            Text(
              indianAmount(taxable + tax, full: true),
              style: text?.copyWith(fontWeight: FontWeight.w600),
            ),
          ),
          _cell(
            context,
            11,
            IconButton(
              tooltip: _lines.length > 1
                  ? 'Remove this line'
                  : 'A quotation needs at least one line',
              iconSize: 16,
              visualDensity: VisualDensity.compact,
              onPressed: _lines.length > 1
                  ? () {
                      _removeLine(index);
                      if (_current >= _lines.length) {
                        _current = _lines.length - 1;
                      }
                      _schedulePreview();
                    }
                  : null,
              icon: const Icon(Icons.close),
            ),
          ),
        ]),
      ),
    );
  }

  Widget _terms(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    Widget box(String label, TextEditingController controller,
            {double width = 180,
            bool number = false,
            bool auto = false,
            String? Function(String?)? validator}) =>
        _field(
          context,
          label: label,
          auto: auto,
          width: width,
          child: TextFormField(
            controller: controller,
            keyboardType: number ? TextInputType.number : null,
            decoration: _boxDecoration(context),
            validator: validator,
            onChanged: (_) {
              _setState(() {});
              if (number) _schedulePreview();
            },
          ),
        );
    return DecoratedBox(
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
        child: Wrap(spacing: 14, runSpacing: 8, children: [
          box('Payment terms', _paymentTerms, auto: true),
          box('Delivery terms', _deliveryTerms),
          box('Discount on the whole offer %', _billDiscount,
              number: true, width: 190, validator: _percentage),
          box('Delivery charge', _freight, number: true, width: 130),
          box('Remarks', _remarks, width: 260),
        ]),
      ),
    );
  }

  Widget _totals(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final QuotationPreviewRecord? preview = _preview;
    final double subtotal =
        double.tryParse(preview?.quotation.subtotal ?? '') ?? _quotedBeforeTax;
    final double tax = double.tryParse(preview?.quotation.taxTotal ?? '') ?? 0;
    final double total =
        double.tryParse(preview?.quotation.grandTotal ?? '') ?? subtotal;
    Widget figure(String label, double value, {bool big = false}) => Padding(
          padding: const EdgeInsets.only(left: 24),
          child: Text.rich(TextSpan(children: [
            TextSpan(
              text: '$label  ',
              style: theme.textTheme.bodyMedium?.copyWith(fontSize: 13),
            ),
            TextSpan(
              text: indianAmount(value, full: true),
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
                fontSize: big ? 18 : 16,
              ),
            ),
          ])),
        );
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 8, 14, 8),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLowest,
        border: Border(top: BorderSide(color: scheme.onSurface, width: 2)),
      ),
      child: Row(children: [
        Expanded(
          child: Text(
            preview != null
                ? indianAmountInWords(total)
                : _branchId == null || _warehouseId == null
                    ? 'Choose the branch and warehouse, and the offer is '
                        'priced with its tax.'
                    : 'Totals follow as the lines are priced.',
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.bodyMedium
                ?.copyWith(color: scheme.onSurfaceVariant),
          ),
        ),
        figure('Taxable', subtotal),
        if (preview != null && preview.interstate)
          figure('IGST', tax)
        else ...[
          figure('CGST', tax / 2),
          figure('SGST', tax / 2),
        ],
        figure('Total', total, big: true),
      ]),
    );
  }

  Widget _sidePanel(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final int index = _current.clamp(0, _lines.length - 1);
    final _LineDraft line = _lines[index];
    final Product? product = _product(line.productId);
    final QuotationLine? priced = _pricedLine(index);
    final QuotationPreviewLine? companion = _companion(index);
    final QuotationPreviewRecord? preview = _preview;
    final TextStyle? small = theme.textTheme.bodySmall
        ?.copyWith(fontSize: 11, color: scheme.onSurfaceVariant);
    Widget heading(String text) => Padding(
          padding: const EdgeInsets.fromLTRB(0, 12, 0, 6),
          child: Text(
            text.toUpperCase(),
            style: theme.textTheme.labelSmall?.copyWith(
              letterSpacing: .8,
              fontWeight: FontWeight.w700,
              color: scheme.onSurfaceVariant,
            ),
          ),
        );
    Widget pair(String label, String value, {bool bold = false, Color? tone}) =>
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 3),
          child: Row(children: [
            Expanded(
              child: Text(label,
                  style: theme.textTheme.bodyMedium
                      ?.copyWith(fontSize: 13, color: scheme.onSurfaceVariant)),
            ),
            Text(
              value,
              style: theme.textTheme.bodyMedium?.copyWith(
                fontSize: 13,
                fontWeight: bold ? FontWeight.w700 : null,
                color: tone,
              ),
            ),
          ]),
        );
    final double taxable =
        double.tryParse(priced?.netAmount ?? '') ?? line.netOfDiscount;
    final double tax = double.tryParse(priced?.taxAmount ?? '') ?? 0;
    final double half = taxable > 0 ? tax / taxable * 50 : 0;
    final Customer? customer = _customer;
    final double balance =
        double.tryParse(customer?.currentOutstanding ?? '') ?? 0;
    final double limit = double.tryParse(customer?.creditLimit ?? '') ?? 0;
    final double total =
        double.tryParse(preview?.quotation.grandTotal ?? '') ?? 0;
    return Container(
      key: const ValueKey('quotation-side-panel'),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        border: Border(left: BorderSide(color: scheme.outlineVariant)),
      ),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        children: [
          heading('Line ${index + 1} · ${product?.name ?? ''}'),
          pair('Rate', _money(line.unitPrice.text)),
          Text(
            line.priceEdited
                ? 'typed on this offer'
                : 'the product\'s selling price'
                    '${(product?.mrp ?? '').isEmpty ? '' : ' (MRP ${_money(product!.mrp)})'}',
            style: small,
          ),
          if (companion != null && companion.lastPrice.isNotEmpty) ...[
            pair('Last to this customer', _money(companion.lastPrice)),
            Text(
              '${companion.lastInvoiceNumber} on '
              '${_displayIso(companion.lastInvoiceDate)}',
              style: small,
            ),
          ],
          pair(
            'Discount',
            priced == null ||
                    (double.tryParse(priced.discountPercent) ?? 0) == 0
                ? '–'
                : '${trimDiscountRate(priced.discountPercent)}%',
          ),
          Text(
            priced == null
                ? (line.discount.text.trim().isEmpty
                    ? 'blank takes any arrangement on file'
                    : 'typed on this offer')
                : discountWasTyped(priced.discountSource)
                    ? 'typed on this offer'
                    : 'from ${discountSourceWords(priced.discountSource)}',
            style: small,
          ),
          if ((double.tryParse(line.free.text.trim()) ?? 0) > 0)
            pair('Free goods',
                '${line.free.text.trim()} ${product?.unit ?? ''}'),
          heading(preview == null
              ? 'Tax'
              : preview.interstate
                  ? 'Tax (inter-state)'
                  : 'Tax (intra-state)'),
          pair('Taxable', indianAmount(taxable, full: true)),
          if (preview != null && preview.interstate)
            pair('IGST ${_trim((half * 2).toStringAsFixed(2))}%',
                indianAmount(tax, full: true))
          else ...[
            pair('CGST ${_trim(half.toStringAsFixed(2))}%',
                indianAmount(tax / 2, full: true)),
            pair('SGST ${_trim(half.toStringAsFixed(2))}%',
                indianAmount(tax / 2, full: true)),
          ],
          const Divider(height: 12),
          pair('Line total', indianAmount(taxable + tax, full: true),
              bold: true),
          if (product != null)
            Text(
              [
                if (product.hsnSac.isNotEmpty) 'HSN ${product.hsnSac}',
                if (product.taxProfileGroupCode.isNotEmpty)
                  'tax group ${product.taxProfileGroupCode}',
              ].join(' · '),
              style: small,
            ),
          heading('Stock'),
          pair(
            'Available where it ships from',
            companion == null ? '—' : _trim(companion.availableQuantity),
          ),
          if (customer != null) ...[
            heading('Customer'),
            pair(
              'Outstanding',
              indianAmount(balance, full: true),
              tone: limit > 0 && balance >= limit * .8 ? scheme.error : null,
            ),
            if (preview != null)
              pair('If it becomes an order',
                  indianAmount(balance + total, full: true)),
            Text(
              [
                if (limit > 0)
                  'credit limit ${indianAmount(limit, full: true)}',
                'a quotation itself owes nothing',
              ].join(' · '),
              style: small,
            ),
          ],
        ],
      ),
    );
  }

  static String _display(DateTime day) =>
      '${day.day.toString().padLeft(2, '0')}-'
      '${day.month.toString().padLeft(2, '0')}-${day.year}';

  static String _displayIso(String iso) {
    final DateTime? day = DateTime.tryParse(iso);
    return day == null ? iso : _display(day);
  }

  static String _money(String value) {
    final double? number = double.tryParse(value.trim());
    return number == null ? value : indianAmount(number, full: true);
  }

  /// A quantity without the store's trailing zeros.
  static String _trim(String value) {
    if (!value.contains('.')) return value;
    final String trimmed = value.replaceFirst(RegExp(r'0+$'), '');
    return trimmed.endsWith('.')
        ? trimmed.substring(0, trimmed.length - 1)
        : trimmed;
  }
}
