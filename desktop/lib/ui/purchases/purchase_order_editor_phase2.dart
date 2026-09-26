part of 'purchase_management_page.dart';

/// The purchase order screen in the phase 2 app: the sales documents'
/// one-screen layout (wireframe view 7) for an order to a supplier -- the
/// header, the lines as a table, the terms and totals, and the side panel for
/// the line being typed -- priced as it is typed by `POST /purchases/preview`.
/// The dialog's state, save, approval actions and the delivery schedule,
/// attachment and note sections are reused unchanged; only the layout is
/// phase 2's.
extension _Phase2PurchaseOrderEditor on _PurchaseOrderEditorDialogState {
  static const List<DocumentColumn> _columns = [
    DocumentColumn('#', 28),
    DocumentColumn('Product (code, name or barcode)', 0),
    DocumentColumn('HSN', 66),
    DocumentColumn('Qty', 66, numeric: true),
    DocumentColumn('Free', 56, numeric: true),
    DocumentColumn('Unit', 76),
    DocumentColumn('Rate', 84, numeric: true),
    DocumentColumn('Disc %', 60, numeric: true),
    DocumentColumn('Disc amt', 76, numeric: true),
    DocumentColumn('Taxable', 92, numeric: true),
    DocumentColumn('GST', 48, numeric: true),
    DocumentColumn('Amount', 100, numeric: true),
    DocumentColumn('', 28),
  ];

  static const List<String> _sections = [
    'Lines',
    'Delivery schedule',
    'Notes & files',
    'History',
  ];

  /// Nothing about an order that is only being looked at, or that the server
  /// will no longer let change, is typed.
  bool get _locked => widget.isReadOnly || !_draft.isEditable;

  Widget _phase2Page(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    if (widget.isCreating &&
        (widget.vendors.isEmpty || widget.products.isEmpty)) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'Nothing to order yet',
        message: 'An order needs a vendor to buy from and a product to buy.',
      );
    }
    final String number =
        _draft.poNumber.ifEmpty(_preview?.order.poNumber ?? '');
    final bool canSubmit =
        _toolbarActionEnabled(DocumentToolbarAction.requestApproval);
    final bool canApprove =
        _toolbarActionEnabled(DocumentToolbarAction.approve);
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.escape): () {
          if (!_saving) _close();
        },
        const SingleActivator(LogicalKeyboardKey.keyS, control: true): () {
          if (!_locked && !_saving) unawaited(_save());
        },
        const SingleActivator(LogicalKeyboardKey.enter, control: true):
            _phase2AddLine,
      },
      child: Focus(
        autofocus: true,
        child: Material(
          color: scheme.surface,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DocumentPageBand(
                title: switch (widget.mode) {
                  PurchaseDialogMode.create => 'New purchase order',
                  PurchaseDialogMode.duplicate => 'New purchase order (copy)',
                  _ => 'Purchase order',
                },
                chips: [
                  if (number.isNotEmpty)
                    widget.isCreating ? '$number (new)' : number,
                  _statusWords(_draft.status),
                ],
                hint: _locked
                    ? ''
                    : 'Enter next field  ·  Ctrl+Enter new line  ·  '
                        'Ctrl+S save',
                actions: [
                  TextButton(
                    onPressed: _saving ? null : _close,
                    child: Text(_locked ? 'Close' : 'Cancel'),
                  ),
                  if (_draft.id.isNotEmpty)
                    OutlinedButton(
                      key: const ValueKey('purchase-order-print'),
                      onPressed: _saving
                          ? null
                          : () => _handleToolbarAction(
                                DocumentToolbarAction.printDocument,
                              ),
                      child: const Text('Print'),
                    ),
                  if (widget.canSubmit && canSubmit)
                    OutlinedButton(
                      key: const ValueKey('purchase-order-submit'),
                      onPressed: () => _handleToolbarAction(
                        DocumentToolbarAction.requestApproval,
                      ),
                      child: const Text('Send for approval'),
                    ),
                  if (widget.canApprove && canApprove)
                    OutlinedButton(
                      key: const ValueKey('purchase-order-approve'),
                      onPressed: () =>
                          _handleToolbarAction(DocumentToolbarAction.approve),
                      child: const Text('Approve'),
                    ),
                  if (!_locked)
                    FilledButton(
                      key: const ValueKey('purchase-order-save'),
                      onPressed: _saving ? null : () => unawaited(_save()),
                      child: Text(
                        widget.isCreating ? 'Save draft' : 'Save order',
                      ),
                    ),
                ],
              ),
              if (_error != null || (_locked && !widget.isReadOnly))
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                  child: MaterialBanner(
                    backgroundColor:
                        _error == null ? scheme.surfaceContainerHigh : null,
                    contentTextStyle: theme.textTheme.bodyMedium,
                    content: Text(
                      _error ??
                          _draft.editRefusal ??
                          'This order can no longer be changed.',
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
                            _sectionStrip(context),
                            Expanded(child: _section(context)),
                            if (_phase2Section == 0) ...[
                              _orderTerms(context),
                              _orderTotals(),
                            ],
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

  String _statusWords(String status) => switch (status) {
        '' || 'DRAFT' => 'Draft',
        'SUBMITTED' => 'Awaiting approval',
        'APPROVED' => 'Approved',
        'PARTIALLY_RECEIVED' => 'Part received',
        'RECEIVED' => 'Received',
        'CLOSED' => 'Closed',
        'CANCELLED' => 'Cancelled',
        _ => status.replaceAll('_', ' '),
      };

  /// Change the order and price it again.
  void _change(PurchaseOrder Function(PurchaseOrder order) edit) {
    _setState(() => _draft = edit(_draft));
    _schedulePreview();
  }

  void _changeLine(int index, PurchaseOrderLine line) {
    _updateLine(index, line);
    _schedulePreview();
  }

  void _phase2AddLine() {
    if (_locked) return;
    _addLine();
    final PurchaseOrderLine added = _draft.lines.last;
    if (added.productId.isNotEmpty) {
      _updateLine(_draft.lines.length - 1, _choose(added, added.productId));
    }
    _setState(() => _current = _draft.lines.length - 1);
    _schedulePreview();
  }

  Vendor? get _vendor {
    for (final Vendor item in widget.vendors) {
      if (item.id == _draft.vendorId) return item;
    }
    return null;
  }

  Product? _product(String id) {
    for (final Product item in widget.products) {
      if (item.id == id) return item;
    }
    return null;
  }

  /// A product chosen on a line brings its units and, where the rate was
  /// not typed, its purchase price.
  PurchaseOrderLine _choose(PurchaseOrderLine line, String productId) {
    final Product? product = _product(productId);
    final PurchaseOrderLine chosen = _withProduct(
      line.copyWith(purchaseUomId: '', inventoryUomId: ''),
      productId,
    );
    final String price = product?.purchasePrice ?? '';
    return price.isEmpty ? chosen : chosen.copyWith(unitPrice: price);
  }

  Widget _dateBox(
    BuildContext context, {
    required Key key,
    required String value,
    required ValueChanged<String> onPicked,
    VoidCallback? onClear,
  }) {
    final DateTime? day = DateTime.tryParse(value);
    return InkWell(
      key: key,
      onTap: _locked
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
        child: Text(day == null ? '—' : documentDate(day)),
      ),
    );
  }

  Widget _box(
    BuildContext context, {
    required String label,
    required String value,
    required ValueChanged<String> onChanged,
    double width = 180,
    bool figure = false,
    String? hint,
  }) =>
      DocumentField(
        label: label,
        width: width,
        child: TextFormField(
          initialValue: value,
          readOnly: _locked,
          keyboardType: figure ? TextInputType.number : null,
          textAlign: figure ? TextAlign.right : TextAlign.start,
          decoration: documentBoxDecoration(context, hint: hint),
          onChanged: onChanged,
        ),
      );

  Widget _choice(
    BuildContext context, {
    required Key key,
    required String? value,
    required List<(String, String)> options,
    required ValueChanged<String> onChanged,
    String? hint,
  }) =>
      DropdownButtonFormField<String>(
        key: key,
        isExpanded: true,
        isDense: true,
        initialValue: options.any((item) => item.$1 == value) ? value : null,
        decoration: documentBoxDecoration(context, hint: hint),
        items: [
          for (final (String id, String label) in options)
            DropdownMenuItem<String>(
              value: id,
              child: Text(label, overflow: TextOverflow.ellipsis),
            ),
        ],
        onChanged: _locked
            ? null
            : (next) {
                if (next != null) onChanged(next);
              },
      );

  Widget _orderHeader(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final Vendor? vendor = _vendor;
    return DocumentHeader(children: [
      DocumentField(
        label: 'Vendor (type code, name or phone)',
        width: 420,
        below: vendor == null ? null : _vendorLine(context, vendor),
        child: DropdownMenu<String>(
          key: const ValueKey('purchase-order-vendor'),
          initialSelection: _draft.vendorId.isEmpty ? null : _draft.vendorId,
          width: 420,
          enabled: !_locked,
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
            for (final Vendor item in widget.vendors)
              DropdownMenuEntry<String>(
                value: item.id,
                label: '${item.displayName.ifEmpty(item.name)} — ${item.code}'
                    '${item.phone.isEmpty ? '' : '  ${item.phone}'}',
              ),
          ],
          onSelected: (value) {
            if (value != null) _change((o) => o.copyWith(vendorId: value));
          },
        ),
      ),
      DocumentField(
        label: 'Order date',
        auto: widget.isCreating,
        width: 140,
        child: _dateBox(
          context,
          key: const ValueKey('purchase-order-date'),
          value: _draft.purchaseDate,
          onPicked: (day) => _change((o) => o.copyWith(purchaseDate: day)),
        ),
      ),
      DocumentField(
        label: 'Expected by',
        width: 150,
        child: _dateBox(
          context,
          key: const ValueKey('purchase-order-expected-date'),
          value: _draft.expectedDeliveryDate,
          onPicked: (day) =>
              _change((o) => o.copyWith(expectedDeliveryDate: day)),
          onClear: _draft.expectedDeliveryDate.isEmpty
              ? null
              : () => _change((o) => o.copyWith(expectedDeliveryDate: '')),
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
        label: 'Buyer',
        width: 200,
        child: _choice(
          context,
          key: const ValueKey('purchase-order-buyer'),
          value: _draft.buyerId,
          options: [
            for (final PlatformUser item in widget.buyers)
              (item.id, item.fullName.ifEmpty(item.email)),
          ],
          onChanged: (value) => _change((o) => o.copyWith(buyerId: value)),
        ),
      ),
      DocumentField(
        label: 'Branch · receives into',
        auto: widget.isCreating &&
            _draft.branchId.isNotEmpty &&
            _draft.warehouseId.isNotEmpty,
        width: 300,
        child: Row(children: [
          Expanded(
            child: _choice(
              context,
              key: const ValueKey('purchase-order-branch'),
              value: _draft.branchId,
              hint: 'Branch',
              options: [
                for (final BranchRecord item in widget.branches)
                  (item.id, item.code),
              ],
              onChanged: (value) => _change(
                (o) => o.copyWith(
                  branchId: value,
                  warehouseId: _defaultWarehouseId(value),
                ),
              ),
            ),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: _choice(
              context,
              key: ValueKey<String>(
                'purchase-order-warehouse-${_draft.branchId}',
              ),
              value: _draft.warehouseId,
              hint: 'Warehouse',
              options: [
                for (final WarehouseRecord item in widget.warehouses)
                  if (_draft.branchId.isEmpty ||
                      item.branchId == _draft.branchId ||
                      item.id == _draft.warehouseId)
                    (item.id, item.code),
              ],
              onChanged: (value) =>
                  _change((o) => o.copyWith(warehouseId: value)),
            ),
          ),
        ]),
      ),
      _box(
        context,
        label: "Vendor's quote reference",
        value: _draft.externalReference,
        width: 180,
        onChanged: (value) => _setState(
          () => _draft = _draft.copyWith(externalReference: value),
        ),
      ),
      _box(
        context,
        label: 'Our reference',
        value: _draft.referenceNumber,
        width: 160,
        onChanged: (value) => _setState(
          () => _draft = _draft.copyWith(referenceNumber: value),
        ),
      ),
      DocumentField(
        label: 'Type',
        width: 180,
        child: _choice(
          context,
          key: const ValueKey('purchase-order-type'),
          value: _draft.purchaseType,
          options: [
            for (final String item
                in _PurchaseManagementPageState._purchaseTypes)
              (item, _sentence(item)),
          ],
          onChanged: (value) =>
              _setState(() => _draft = _draft.copyWith(purchaseType: value)),
        ),
      ),
      DocumentField(
        label: 'Priority',
        width: 120,
        child: _choice(
          context,
          key: const ValueKey('purchase-order-priority'),
          value: _draft.priority,
          options: const [
            ('LOW', 'Low'),
            ('NORMAL', 'Normal'),
            ('HIGH', 'High'),
            ('URGENT', 'Urgent'),
          ],
          onChanged: (value) =>
              _setState(() => _draft = _draft.copyWith(priority: value)),
        ),
      ),
    ]);
  }

  String _sentence(String code) {
    final String words = code.replaceAll('_', ' ').toLowerCase();
    return words.isEmpty ? '' : words[0].toUpperCase() + words.substring(1);
  }

  Widget _vendorLine(BuildContext context, Vendor vendor) {
    final ThemeData theme = Theme.of(context);
    final String phone = vendor.mobile.ifEmpty(vendor.phone);
    return Text(
      [
        vendor.code,
        if (vendor.gstin.isNotEmpty)
          'GSTIN ${vendor.gstin}'
        else
          'unregistered',
        if (phone.isNotEmpty) phone,
      ].join('  ·  '),
      overflow: TextOverflow.ellipsis,
      style: theme.textTheme.bodySmall?.copyWith(
        fontSize: 11,
        color: theme.colorScheme.onSurfaceVariant,
      ),
    );
  }

  Widget _sectionStrip(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: Row(children: [
          for (int i = 0; i < _sections.length; i++)
            InkWell(
              key: ValueKey<String>('purchase-order-section-$i'),
              onTap: () => _setState(() => _phase2Section = i),
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  border: Border(
                    bottom: BorderSide(
                      width: 2,
                      color: i == _phase2Section
                          ? scheme.primary
                          : Colors.transparent,
                    ),
                  ),
                ),
                child: Text(
                  i == 0 ? 'Lines (${_draft.lines.length})' : _sections[i],
                  style: theme.textTheme.labelLarge?.copyWith(
                    color: i == _phase2Section
                        ? scheme.onSurface
                        : scheme.onSurfaceVariant,
                  ),
                ),
              ),
            ),
        ]),
      ),
    );
  }

  Widget _section(BuildContext context) {
    if (_phase2Section == 0) {
      return DocumentLineTable(
        columns: _columns,
        rows: [
          for (int i = 0; i < _draft.lines.length; i++) _orderRow(context, i),
        ],
        addLabel: _locked
            ? null
            : '${_draft.lines.length + 1}     + add a product (Ctrl+Enter)',
        onAdd: _phase2AddLine,
      );
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: switch (_phase2Section) {
          1 => [_buildDeliveryTab()],
          2 => [
              _buildAttachmentsTab(),
              const SizedBox(height: 16),
              _buildNotesTab(),
            ],
          _ => [
              _buildHistoryTab(),
              const SizedBox(height: 16),
              _buildAuditTab(),
            ],
        },
      ),
    );
  }

  /// The order the figures are read from: the server's pricing of what is
  /// typed, else -- for an order only being looked at -- what it stored.
  PurchaseOrder? get _priced =>
      _preview?.order ?? (_draft.id.isEmpty ? null : _draft);

  PurchaseOrderLine? _pricedLine(int index) {
    final PurchaseOrder? order = _priced;
    if (order == null) return null;
    for (final PurchaseOrderLine line in order.lines) {
      if (line.lineNumber == index + 1 &&
          line.productId == _draft.lines[index].productId) {
        return line;
      }
    }
    return null;
  }

  DocumentPreviewLine? _companion(int index) {
    for (final DocumentPreviewLine line
        in _preview?.lines ?? const <DocumentPreviewLine>[]) {
      if (line.lineNumber == index + 1 &&
          line.productId == _draft.lines[index].productId) {
        return line;
      }
    }
    return null;
  }

  double _number(String value) => double.tryParse(value.trim()) ?? 0;

  /// The line's value before tax, as typed: what shows until the server's
  /// figure arrives.
  double _typedTaxable(PurchaseOrderLine line) {
    final double gross =
        _number(line.orderedQuantity) * _number(line.unitPrice);
    final double amount = _number(line.discountAmount);
    return gross -
        (amount > 0 ? amount : gross * _number(line.discountPercent) / 100);
  }

  Widget _cellBox(
    BuildContext context, {
    required int index,
    required String name,
    required String value,
    required ValueChanged<String> onChanged,
  }) =>
      TextFormField(
        // Keyed on the line's place and product and on removals, so a box
        // shows its own line's figure after a line above it goes.
        key: ValueKey<String>(
          'purchase-order-$name-$_lineEpoch-$index-'
          '${_draft.lines[index].productId}',
        ),
        initialValue: value,
        readOnly: _locked,
        textAlign: TextAlign.right,
        keyboardType: TextInputType.number,
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontSize: 13),
        decoration: documentCellDecoration(context),
        onChanged: onChanged,
      );

  Widget _orderRow(BuildContext context, int index) {
    final ThemeData theme = Theme.of(context);
    final PurchaseOrderLine line = _draft.lines[index];
    final Product? product = _product(line.productId);
    final PurchaseOrderLine? priced = _pricedLine(index);
    final DocumentPreviewLine? companion = _companion(index);
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final double taxable = priced == null
        ? _typedTaxable(line)
        : _number(priced.grossAmount) - _number(priced.discountAmount);
    final double tax = priced == null ? 0 : _number(priced.taxAmount);
    final double rate = taxable > 0 ? tax / taxable * 100 : 0;
    return DocumentLineRow(
      key: ValueKey<String>('purchase-order-line-$index'),
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
                key: ValueKey<String>(
                  'purchase-order-line-product-$_lineEpoch-$index',
                ),
                initialSelection:
                    line.productId.isEmpty ? null : line.productId,
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
                  for (final Product item in widget.products)
                    DropdownMenuEntry<String>(
                      value: item.id,
                      label: '${item.name}  ${item.code}'
                          '${item.barcode.isEmpty ? '' : '  ${item.barcode}'}',
                    ),
                ],
                onSelected: (value) {
                  if (value == null || value == line.productId) return;
                  _setState(() => _current = index);
                  _changeLine(index, _choose(line, value));
                },
              ),
              if (companion != null)
                Text(
                  'Stock ${documentQuantity(companion.availableQuantity)}'
                  '${companion.lastPrice.isEmpty ? '' : '  ·  last from them '
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
          index: index,
          name: 'qty',
          value: line.orderedQuantity,
          onChanged: (value) =>
              _changeLine(index, line.copyWith(orderedQuantity: value)),
        ),
        _cellBox(
          context,
          index: index,
          name: 'free',
          value: line.freeQuantity,
          onChanged: (value) =>
              _changeLine(index, line.copyWith(freeQuantity: value)),
        ),
        _unitCell(context, index, line, text),
        _cellBox(
          context,
          index: index,
          name: 'rate-$_rateEpoch',
          value: line.unitPrice,
          onChanged: (value) =>
              _changeLine(index, line.copyWith(unitPrice: value)),
        ),
        _cellBox(
          context,
          index: index,
          name: 'disc',
          value: line.discountPercent,
          onChanged: (value) =>
              _changeLine(index, line.copyWith(discountPercent: value)),
        ),
        _cellBox(
          context,
          index: index,
          name: 'disc-amt',
          value: line.discountAmount,
          onChanged: (value) =>
              _changeLine(index, line.copyWith(discountAmount: value)),
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
          tooltip: _draft.lines.length > 1
              ? 'Remove this line'
              : 'An order needs at least one line',
          iconSize: 16,
          visualDensity: VisualDensity.compact,
          onPressed: _draft.lines.length > 1 && !_locked
              ? () {
                  _removeLine(index);
                  _setState(() {
                    _lineEpoch++;
                    if (_current >= _draft.lines.length) {
                      _current = _draft.lines.length - 1;
                    }
                  });
                  _schedulePreview();
                }
              : null,
          icon: const Icon(Icons.close),
        ),
      ],
    );
  }

  /// The unit the vendor sells in, by code: the product's own purchase unit
  /// unless another is chosen.
  Widget _unitCell(
    BuildContext context,
    int index,
    PurchaseOrderLine line,
    TextStyle? text,
  ) {
    if (widget.uoms.isEmpty) {
      return Text(_product(line.productId)?.unit ?? '', style: text);
    }
    final String current = line.purchaseUomId;
    return DropdownButton<String>(
      key: ValueKey<String>('purchase-order-unit-$_lineEpoch-$index'),
      value: current.isEmpty || !widget.uoms.any((unit) => unit.id == current)
          ? null
          : current,
      isExpanded: true,
      isDense: true,
      underline: const SizedBox.shrink(),
      style: text,
      hint: Text(
        (_product(line.productId)?.unit ?? '').ifEmpty('—'),
        style: text,
      ),
      items: [
        for (final UomRecord unit in widget.uoms)
          DropdownMenuItem<String>(
            value: unit.id,
            child: Text(unit.code, overflow: TextOverflow.ellipsis),
          ),
      ],
      onChanged: _locked
          ? null
          : (value) {
              if (value != null) {
                _changeLine(index, line.copyWith(purchaseUomId: value));
              }
            },
    );
  }

  Widget _orderTerms(BuildContext context) => DocumentTerms(children: [
        _box(
          context,
          label: 'Discount on the whole order',
          value: _draft.headerDiscountAmount == '0'
              ? ''
              : _draft.headerDiscountAmount,
          width: 190,
          figure: true,
          hint: 'amount',
          onChanged: (value) =>
              _change((o) => o.copyWith(headerDiscountAmount: value.trim())),
        ),
        _box(
          context,
          label: 'Other charges',
          value:
              _draft.additionalCharges == '0' ? '' : _draft.additionalCharges,
          width: 130,
          figure: true,
          onChanged: (value) =>
              _change((o) => o.copyWith(additionalCharges: value.trim())),
        ),
        _box(
          context,
          label: 'Payment terms',
          value: _draft.paymentTerms,
          width: 170,
          onChanged: (value) =>
              _setState(() => _draft = _draft.copyWith(paymentTerms: value)),
        ),
        _box(
          context,
          label: 'Delivery terms',
          value: _draft.deliveryTerms,
          width: 170,
          onChanged: (value) =>
              _setState(() => _draft = _draft.copyWith(deliveryTerms: value)),
        ),
        _box(
          context,
          label: 'Remarks',
          value: _draft.remarks,
          width: 260,
          onChanged: (value) =>
              _setState(() => _draft = _draft.copyWith(remarks: value)),
        ),
      ]);

  Widget _orderTotals() {
    final PurchaseOrder? order = _priced;
    double typed = 0;
    for (final PurchaseOrderLine line in _draft.lines) {
      typed += _typedTaxable(line);
    }
    final double taxable = order == null
        ? typed
        : _number(order.subtotal) - _number(order.lineDiscountTotal);
    final double tax = order == null ? 0 : _number(order.taxTotal);
    final double off = _number(
      order?.headerDiscountAmount ?? _draft.headerDiscountAmount,
    );
    final double charges =
        _number(order?.additionalCharges ?? _draft.additionalCharges);
    final bool? interstate = _preview?.interstate;
    return DocumentTotalsBar(
      total: order == null ? null : _number(order.grandTotal),
      note: _draft.vendorId.isEmpty ||
              _draft.branchId.isEmpty ||
              _draft.warehouseId.isEmpty
          ? 'Choose the vendor, branch and warehouse, and the order is priced '
              'with its tax.'
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
        if (off != 0) ('Order discount', -off),
        if (charges != 0) ('Other charges', charges),
        (
          'Total',
          order == null ? taxable - off + charges : _number(order.grandTotal)
        ),
      ],
    );
  }

  Widget _orderSidePanel(BuildContext context) {
    final int index = _current.clamp(0, _draft.lines.length - 1);
    final PurchaseOrderLine line = _draft.lines[index];
    final Product? product = _product(line.productId);
    final PurchaseOrderLine? priced = _pricedLine(index);
    final DocumentPreviewLine? companion = _companion(index);
    final Vendor? vendor = _vendor;
    final double taxable = priced == null
        ? _typedTaxable(line)
        : _number(priced.grossAmount) - _number(priced.discountAmount);
    final double tax = priced == null ? 0 : _number(priced.taxAmount);
    final bool typedRate = product == null ||
        _number(product.purchasePrice) != _number(line.unitPrice);
    final double discount = _number(line.discountAmount) > 0
        ? _number(line.discountAmount)
        : _number(line.discountPercent);
    return DocumentSidePanel(children: [
      DocumentSideHeading('Line ${index + 1} · ${product?.name ?? ''}'),
      DocumentSidePair('Rate', documentMoney(line.unitPrice)),
      DocumentSideNote(
        product != null && product.purchasePrice.isEmpty
            ? 'the product has no purchase price; type the rate'
            : typedRate
                ? 'as typed on this order'
                : "the product's purchase price",
      ),
      if (companion != null && companion.lastPrice.isNotEmpty) ...[
        DocumentSidePair(
          'Last from this vendor',
          documentMoney(companion.lastPrice),
        ),
        DocumentSideNote(
          '${companion.lastInvoiceNumber} on '
          '${DateTime.tryParse(companion.lastInvoiceDate) == null ? companion.lastInvoiceDate : documentDate(DateTime.parse(companion.lastInvoiceDate))}',
        ),
        if (!_locked && _number(companion.lastPrice) != _number(line.unitPrice))
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              key: const ValueKey('purchase-order-use-last-price'),
              onPressed: () {
                _setState(() => _rateEpoch++);
                _changeLine(
                  index,
                  line.copyWith(unitPrice: companion.lastPrice),
                );
              },
              child: const Text('Use the last price'),
            ),
          ),
      ],
      DocumentSidePair(
        'Discount',
        discount == 0
            ? '–'
            : _number(line.discountAmount) > 0
                ? documentMoney(line.discountAmount)
                : '${trimDiscountRate(line.discountPercent)}%',
      ),
      if (_number(line.freeQuantity) > 0)
        DocumentSidePair(
          'Free goods',
          '${line.freeQuantity.trim()} ${product?.unit ?? ''}',
        ),
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
        'Where it is received',
        companion == null ? '—' : documentQuantity(companion.availableQuantity),
      ),
      const DocumentSideNote('receiving against the order adds to it'),
      if (vendor != null) ...[
        DocumentSideHeading(vendor.displayName.ifEmpty(vendor.name)),
        DocumentSidePair('GSTIN', vendor.gstin.ifEmpty('unregistered')),
        if (vendor.mobile.ifEmpty(vendor.phone).isNotEmpty)
          DocumentSidePair('Phone', vendor.mobile.ifEmpty(vendor.phone)),
      ],
      const DocumentSideHeading('Approval'),
      DocumentSideNote(_approvalMessage()),
    ]);
  }
}
