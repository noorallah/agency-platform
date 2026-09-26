part of 'goods_receipt_editor_dialog.dart';

/// The goods receipt screen in the phase 2 app: the documents' one-screen
/// layout (wireframe view 7) for what came off the lorry -- the order it
/// arrived against, the order's lines with what is still due and what was
/// accepted, rejected and damaged, and a side panel with the rest of the
/// line being typed: where it went, its dates and remarks. The dialog's
/// state, validation and save are reused unchanged.
///
/// Not priced by the server: a receipt is valued at its order's rates, and
/// the bill it answers to is entered as a purchase invoice.
extension _Phase2GoodsReceiptEditor on _GoodsReceiptEditorDialogState {
  static const List<DocumentColumn> _columns = [
    DocumentColumn('#', 28),
    DocumentColumn('Product', 0),
    DocumentColumn('Ordered', 70, numeric: true),
    DocumentColumn('Received', 70, numeric: true),
    DocumentColumn('Due', 66, numeric: true),
    DocumentColumn('Accepted', 78, numeric: true),
    DocumentColumn('Free', 60, numeric: true),
    DocumentColumn('Rejected', 70, numeric: true),
    DocumentColumn('Damaged', 70, numeric: true),
    DocumentColumn('Batch', 110),
    DocumentColumn('Value', 96, numeric: true),
  ];

  Widget _phase2Page(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final GoodsReceiptRecord? current = widget.existing;
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
                title: _isEditing ? 'Goods receipt' : 'New goods receipt',
                chips: [
                  if (current != null && current.grnNumber.isNotEmpty)
                    current.grnNumber,
                  if (_order != null) 'against ${_order!.poNumber}',
                  'Draft',
                ],
                hint: 'Enter next field  ·  Ctrl+S save',
                actions: [
                  TextButton(
                    onPressed: _saving ? null : () => Navigator.pop(context),
                    child: const Text('Cancel'),
                  ),
                  FilledButton(
                    key: const ValueKey('goods-receipt-save'),
                    onPressed: _saving ? null : () => unawaited(_save()),
                    child: const Text('Save receipt'),
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
                            _receiptHeader(context),
                            Expanded(child: _receiptLines(context)),
                            _receiptTotals(),
                          ],
                        ),
                      ),
                      if (constraints.maxWidth >= DocumentSidePanel.showFrom)
                        _receiptSidePanel(context),
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
          suffixIcon: onClear != null
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

  Widget _receiptHeader(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final PurchaseOrder? order = _order;
    return DocumentHeader(children: [
      DocumentField(
        label: 'Purchase order (approved orders only)',
        width: 400,
        below: order == null
            ? null
            : Text(
                [
                  'ordered ${_dayOf(order.purchaseDate)}',
                  if (order.expectedDeliveryDate.isNotEmpty)
                    'expected ${_dayOf(order.expectedDeliveryDate)}',
                  '${order.lines.length} '
                      '${order.lines.length == 1 ? 'line' : 'lines'}',
                ].join('  ·  '),
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall?.copyWith(
                  fontSize: 11,
                  color: scheme.onSurfaceVariant,
                ),
              ),
        child: DropdownMenu<String>(
          key: const ValueKey('goods-receipt-order'),
          initialSelection: order?.id,
          width: 400,
          // A draft being corrected stays against its order: its lines are
          // that order's lines.
          enabled: !_saving && !_isEditing,
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
            for (final PurchaseOrder item in widget.purchaseOrders)
              DropdownMenuEntry<String>(
                value: item.id,
                label: '${item.poNumber}  ${_dayOf(item.purchaseDate)}',
              ),
          ],
          onSelected: (value) {
            for (final PurchaseOrder item in widget.purchaseOrders) {
              if (item.id == value && item.id != _order?.id) {
                _current = 0;
                unawaited(_selectOrder(item));
              }
            }
          },
        ),
      ),
      DocumentField(
        label: 'Receipt date',
        auto: !_isEditing,
        width: 140,
        child: _dateBox(
          context,
          key: const ValueKey('goods-receipt-date'),
          value: _receiptDate,
          onPicked: (day) => _setState(() => _receiptDate = day),
        ),
      ),
      _box(
        context,
        label: "Supplier's invoice number",
        value: _invoiceReference,
        width: 180,
        onChanged: (value) => _invoiceReference = value,
      ),
      _box(
        context,
        label: 'Transport',
        value: _transportDetails,
        width: 180,
        onChanged: (value) => _transportDetails = value,
      ),
      if (widget.features.isEnabled('VEHICLE_TRACKING'))
        _box(
          context,
          label: 'Vehicle number',
          value: _vehicleNumber,
          width: 140,
          onChanged: (value) => _vehicleNumber = value,
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

  String _dayOf(String value) {
    final DateTime? day = DateTime.tryParse(value);
    return day == null ? value : documentDate(day);
  }

  Widget _receiptLines(BuildContext context) {
    if (_order == null) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'No purchase order chosen',
        message: 'A goods receipt records what arrived against an order. '
            'Choose the order above and its lines appear here.',
      );
    }
    return DocumentLineTable(
      columns: _columns,
      rows: [
        for (int i = 0; i < _lines.length; i++) _receiptRow(context, i),
      ],
    );
  }

  Widget _cellBox(
    BuildContext context, {
    required int index,
    required String name,
    required String value,
    required ValueChanged<String> onChanged,
    bool figure = true,
    bool over = false,
    String? hint,
  }) =>
      TextFormField(
        // Keyed on the order too, so choosing another order re-reads them.
        key: ValueKey<String>('goods-receipt-$name-${_order?.id}-$index'),
        // A saved draft reads back "6.0000"; shown as the 6 it is.
        initialValue:
            figure && value.trim().isNotEmpty ? documentQuantity(value) : value,
        readOnly: _saving,
        textAlign: figure ? TextAlign.right : TextAlign.start,
        keyboardType: figure ? TextInputType.number : null,
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              fontSize: 13,
              color: over ? Theme.of(context).colorScheme.error : null,
            ),
        decoration: documentCellDecoration(context, hint: hint),
        onTap: () => _setState(() => _current = index),
        onChanged: (next) => _setState(() {
          _current = index;
          onChanged(next);
        }),
      );

  Widget _receiptRow(BuildContext context, int index) {
    final ThemeData theme = Theme.of(context);
    final GoodsReceiptDraftLine line = _lines[index];
    final Product? product = _product(line.productId);
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final TextStyle? quiet =
        text?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final double accepted = _number(line.receiptQuantity);
    final bool over = accepted > line.outstanding;
    return DocumentLineRow(
      key: ValueKey<String>('goods-receipt-line-$index'),
      columns: _columns,
      current: index == _current,
      onTap: () => _setState(() => _current = index),
      cells: [
        Text('${line.lineNumber}', style: text),
        Padding(
          padding: const EdgeInsets.only(right: 8),
          child: Text(
            product == null
                ? line.description.ifEmpty(line.productId)
                : '${product.name}  ${product.code}',
            overflow: TextOverflow.ellipsis,
            style: text,
          ),
        ),
        Text(documentQuantity(line.orderedQuantity), style: quiet),
        Text(documentQuantity(line.alreadyReceived), style: quiet),
        Text(
          documentQuantity(_GoodsReceiptEditorDialogState._trim(
            line.outstanding,
          )),
          style: text?.copyWith(fontWeight: FontWeight.w600),
        ),
        Tooltip(
          message: over ? 'More than is still due on the order' : '',
          child: _cellBox(
            context,
            index: index,
            name: 'accepted',
            over: over,
            value: line.receiptQuantity,
            onChanged: (value) => line.receiptQuantity = value,
          ),
        ),
        _cellBox(
          context,
          index: index,
          name: 'free',
          value: line.freeQuantity,
          onChanged: (value) => line.freeQuantity = value,
        ),
        _cellBox(
          context,
          index: index,
          name: 'rejected',
          value: line.rejectedQuantity,
          onChanged: (value) => line.rejectedQuantity = value,
        ),
        _cellBox(
          context,
          index: index,
          name: 'damaged',
          value: line.damagedQuantity,
          onChanged: (value) => line.damagedQuantity = value,
        ),
        _cellBox(
          context,
          index: index,
          name: 'batch',
          value: line.batchNumber,
          figure: false,
          hint: line.batchRequired ? 'required' : null,
          onChanged: (value) => line.batchNumber = value,
        ),
        Text(
          indianAmount(accepted * _number(line.unitPrice), full: true),
          style: text?.copyWith(fontWeight: FontWeight.w600),
        ),
      ],
    );
  }

  Widget _receiptTotals() {
    double value = 0;
    for (final GoodsReceiptDraftLine line in _lines) {
      value += _number(line.receiptQuantity) * _number(line.unitPrice);
    }
    return DocumentTotalsBar(
      total: _order == null ? null : value,
      note: 'Choose the order that arrived.',
      figures: [('Value at the order\'s rates, before tax', value)],
    );
  }

  Widget _receiptSidePanel(BuildContext context) {
    if (_lines.isEmpty) {
      return const DocumentSidePanel(children: [
        DocumentSideHeading('Receiving'),
        DocumentSideNote(
          'Choose the order that arrived. Each line starts at what is still '
          'due on it; change what differs, and leave a line at zero if it did '
          'not come.',
        ),
      ]);
    }
    final int index = _current.clamp(0, _lines.length - 1);
    final GoodsReceiptDraftLine line = _lines[index];
    final Product? product = _product(line.productId);
    final double accepted = _number(line.receiptQuantity);
    final double left = line.outstanding - accepted;
    double acceptedAll = 0;
    double refused = 0;
    for (final GoodsReceiptDraftLine item in _lines) {
      acceptedAll += _number(item.receiptQuantity);
      refused += _number(item.rejectedQuantity) + _number(item.damagedQuantity);
    }
    String quantity(double value) =>
        documentQuantity(_GoodsReceiptEditorDialogState._trim(value));
    return DocumentSidePanel(children: [
      DocumentSideHeading(
        'Line ${line.lineNumber} · ${product?.name ?? line.description}',
      ),
      DocumentSidePair('Ordered', documentQuantity(line.orderedQuantity)),
      DocumentSidePair(
          'Received before', documentQuantity(line.alreadyReceived)),
      DocumentSidePair('Accepted now', quantity(accepted)),
      DocumentSidePair(
        left < 0 ? 'Over the order by' : 'Still due after this',
        quantity(left.abs()),
        bold: true,
        tone: left < 0 ? Theme.of(context).colorScheme.error : null,
      ),
      DocumentSidePair('Rate on the order', documentMoney(line.unitPrice)),
      const SizedBox(height: 8),
      DocumentField(
        label: 'Went to warehouse',
        width: 258,
        child: DropdownButtonFormField<String>(
          key: ValueKey<String>('goods-receipt-warehouse-${_order?.id}-$index'),
          isExpanded: true,
          isDense: true,
          initialValue: widget.warehouses.any((w) => w.id == line.warehouseId)
              ? line.warehouseId
              : null,
          decoration: documentBoxDecoration(context, hint: 'Choose'),
          items: [
            for (final WarehouseRecord warehouse in widget.warehouses)
              DropdownMenuItem<String>(
                value: warehouse.id,
                child: Text(
                  '${warehouse.code} - ${warehouse.name}',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
          ],
          onChanged: _saving
              ? null
              : (value) => _setState(() => line.warehouseId = value ?? ''),
        ),
      ),
      if (widget.features.isEnabled('EXPIRY_TRACKING'))
        DocumentField(
          label: line.expiryRequired ? 'Expiry date (required)' : 'Expiry date',
          width: 258,
          child: _dateBox(
            context,
            key: ValueKey<String>('goods-receipt-expiry-${_order?.id}-$index'),
            value: line.expiryDate,
            onPicked: (day) => _setState(() => line.expiryDate = day),
            onClear: line.expiryDate.isEmpty
                ? null
                : () => _setState(() => line.expiryDate = ''),
          ),
        ),
      if (widget.features.isEnabled('MANUFACTURING_DATE'))
        DocumentField(
          label: 'Manufactured on',
          width: 258,
          child: _dateBox(
            context,
            key: ValueKey<String>('goods-receipt-mfg-${_order?.id}-$index'),
            value: line.manufacturingDate,
            onPicked: (day) => _setState(() => line.manufacturingDate = day),
            onClear: line.manufacturingDate.isEmpty
                ? null
                : () => _setState(() => line.manufacturingDate = ''),
          ),
        ),
      DocumentField(
        label: 'Line remarks',
        width: 258,
        child: TextFormField(
          key: ValueKey<String>('goods-receipt-remarks-${_order?.id}-$index'),
          initialValue: line.remarks,
          readOnly: _saving,
          decoration: documentBoxDecoration(context),
          onChanged: (value) => line.remarks = value,
        ),
      ),
      const DocumentSideHeading('This receipt'),
      DocumentSidePair('Accepted', quantity(acceptedAll)),
      DocumentSidePair('Rejected and damaged', quantity(refused)),
      const DocumentSideNote(
        'Completing the receipt puts what was accepted into stock; the '
        "supplier's bill is entered as a purchase invoice.",
      ),
    ]);
  }
}
