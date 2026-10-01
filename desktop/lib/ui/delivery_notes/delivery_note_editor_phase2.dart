part of 'delivery_note_editor_dialog.dart';

/// The delivery note screen in the phase 2 app: the documents' one-screen
/// layout (wireframe view 7) for goods going out -- the order they leave
/// against, its lines as a table with what is reserved and what is going,
/// and a side panel for the line being typed: the warehouse it leaves from,
/// the batches it is expected to come off, the serial numbers going out and
/// remarks. The dialog's state, validation and save are reused unchanged.
///
/// Not priced by the server: a note is valued at its order's rates, and the
/// bill it leads to is the sales invoice.
extension _Phase2DeliveryNoteEditor on _DeliveryNoteEditorDialogState {
  static const List<DocumentColumn> _columns = [
    DocumentColumn('#', 28),
    DocumentColumn('Product', 0),
    DocumentColumn('Ordered', 70, numeric: true),
    DocumentColumn('Reserved', 72, numeric: true),
    DocumentColumn('Delivered', 74, numeric: true),
    DocumentColumn('Delivering', 84, numeric: true),
    DocumentColumn('Free', 60, numeric: true),
    DocumentColumn('Damaged', 70, numeric: true),
    DocumentColumn('Value', 96, numeric: true),
  ];

  Widget _phase2Page(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
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
                title: 'New delivery note',
                chips: [
                  if (_order != null) 'against $_orderNumber',
                  'Draft',
                ],
                hint: 'Enter next field  ·  Ctrl+S save',
                actions: [
                  TextButton(
                    onPressed: _saving ? null : () => Navigator.pop(context),
                    child: const Text('Cancel'),
                  ),
                  FilledButton(
                    key: const ValueKey('delivery-note-save'),
                    onPressed: _saving ? null : () => unawaited(_save()),
                    child: const Text('Save delivery note'),
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
                            _noteHeader(context),
                            Expanded(child: _noteLines(context)),
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

  Widget _noteHeader(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final Json? order = _order;
    final DateTime? day = DateTime.tryParse(_deliveryDate);
    final String customer = stringValue(order?['customer_name']);
    return DocumentHeader(children: [
      DocumentField(
        label: 'Sales order (approved orders only)',
        width: 400,
        below: order == null
            ? null
            : Text(
                [
                  if (customer.isNotEmpty) customer,
                  'ordered ${_dayOf(stringValue(order['order_date']))}',
                ].join('  ·  '),
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall?.copyWith(
                  fontSize: 11,
                  color: scheme.onSurfaceVariant,
                ),
              ),
        child: DropdownMenu<String>(
          key: const ValueKey('delivery-note-order'),
          initialSelection: order == null ? null : stringValue(order['id']),
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
            for (final Json item in widget.salesOrders)
              DropdownMenuEntry<String>(
                value: stringValue(item['id']),
                label: [
                  stringValue(item['order_number']),
                  _dayOf(stringValue(item['order_date'])),
                  stringValue(item['customer_name']),
                ].where((part) => part.isNotEmpty).join('  '),
              ),
          ],
          onSelected: (value) {
            for (final Json item in widget.salesOrders) {
              if (stringValue(item['id']) == value &&
                  value != stringValue(_order?['id'])) {
                _current = 0;
                unawaited(_selectOrder(item));
              }
            }
          },
        ),
      ),
      if (_addresses.isNotEmpty)
        ShipToField(
          key: const ValueKey('delivery-note-ship-to'),
          scope: stringValue(order?['id']),
          addresses: _addresses,
          value: _shippingAddressId,
          enabled: !_saving,
          onChanged: (value) => _setState(() => _shippingAddressId = value),
        ),
      DocumentField(
        label: 'Delivery date',
        auto: true,
        width: 140,
        child: InkWell(
          key: const ValueKey('delivery-note-date'),
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
                  _setState(() => _deliveryDate =
                      picked.toIso8601String().split('T').first);
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
      DocumentField(
        label: 'Reason',
        width: 210,
        child: DropdownButtonFormField<String>(
          key: const ValueKey('delivery-note-challan-reason'),
          initialValue: _challanReason,
          isExpanded: true,
          isDense: true,
          decoration: documentBoxDecoration(context),
          items: [
            for (final (String value, String label) in challanReasons)
              DropdownMenuItem<String>(
                value: value,
                child: Text(label, overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: _saving
              ? null
              : (value) =>
                  _setState(() => _challanReason = value ?? _challanReason),
        ),
      ),
      if (_challanReason == 'OTHER')
        DocumentField(
          label: 'Say why',
          width: 240,
          child: TextFormField(
            key: const ValueKey('delivery-note-challan-reason-note'),
            initialValue: _challanReasonNote,
            readOnly: _saving,
            maxLength: 200,
            buildCounter: (context,
                    {required currentLength, required isFocused, maxLength}) =>
                null,
            decoration: documentBoxDecoration(context),
            onChanged: (next) => _setState(() => _challanReasonNote = next),
          ),
        ),
      if (widget.features.isEnabled('VEHICLE_TRACKING'))
        _box(
          context,
          label: 'Vehicle',
          value: _vehicle,
          width: 140,
          onChanged: (value) => _vehicle = value,
        ),
      _box(
        context,
        label: 'Driver',
        value: _driver,
        width: 160,
        onChanged: (value) => _driver = value,
      ),
      ..._transportFields(context),
      _box(
        context,
        label: 'Remarks',
        value: _remarks,
        width: 240,
        onChanged: (value) => _remarks = value,
      ),
    ]);
  }

  /// How the goods travel (backlog 67 row 5): beside the vehicle and driver.
  /// The e-way bill takes whatever is blank on it from these.
  List<Widget> _transportFields(BuildContext context) {
    final DateTime? lrDay = DateTime.tryParse(_lrDate);
    return [
      _box(
        context,
        label: 'Transporter',
        value: _transporterName,
        width: 170,
        onChanged: (value) => _transporterName = value,
      ),
      DocumentField(
        label: 'Transporter GSTIN',
        width: 160,
        child: TextFormField(
          key: const ValueKey('delivery-note-transporter-gstin'),
          initialValue: _transporterGstin,
          readOnly: _saving,
          textCapitalization: TextCapitalization.characters,
          decoration: documentBoxDecoration(context),
          onChanged: (next) => _setState(() => _transporterGstin = next),
        ),
      ),
      DocumentField(
        label: 'Moving by',
        width: 110,
        child: DropdownButtonFormField<String?>(
          key: const ValueKey('delivery-note-transport-mode'),
          initialValue: _transportMode,
          isExpanded: true,
          isDense: true,
          decoration: documentBoxDecoration(context),
          items: const [
            DropdownMenuItem<String?>(value: null, child: Text('—')),
            DropdownMenuItem<String?>(value: 'ROAD', child: Text('Road')),
            DropdownMenuItem<String?>(value: 'RAIL', child: Text('Rail')),
            DropdownMenuItem<String?>(value: 'AIR', child: Text('Air')),
            DropdownMenuItem<String?>(value: 'SHIP', child: Text('Ship')),
          ],
          onChanged: _saving
              ? null
              : (value) => _setState(() => _transportMode = value),
        ),
      ),
      _box(
        context,
        label: 'LR / docket no.',
        value: _lrNumber,
        width: 130,
        onChanged: (value) => _lrNumber = value,
      ),
      DocumentField(
        label: 'LR date',
        width: 130,
        child: InkWell(
          key: const ValueKey('delivery-note-lr-date'),
          onTap: _saving
              ? null
              : () async {
                  final DateTime? picked = await showDatePicker(
                    context: context,
                    initialDate: lrDay ?? DateTime.now(),
                    firstDate: DateTime(2000),
                    lastDate: DateTime(2100),
                  );
                  if (picked == null) return;
                  _setState(() =>
                      _lrDate = picked.toIso8601String().split('T').first);
                },
          child: InputDecorator(
            decoration: documentBoxDecoration(context).copyWith(
              suffixIcon: _lrDate.isEmpty || _saving
                  ? const Icon(Icons.event, size: 16)
                  : IconButton(
                      tooltip: 'Clear',
                      iconSize: 14,
                      visualDensity: VisualDensity.compact,
                      onPressed: () => _setState(() => _lrDate = ''),
                      icon: const Icon(Icons.close),
                    ),
              suffixIconConstraints:
                  const BoxConstraints(minWidth: 28, minHeight: 20),
            ),
            child: Text(lrDay == null ? '—' : documentDate(lrDay)),
          ),
        ),
      ),
      DocumentField(
        label: 'Distance (km)',
        width: 100,
        child: TextFormField(
          key: const ValueKey('delivery-note-distance'),
          initialValue: _distanceKm,
          readOnly: _saving,
          keyboardType: TextInputType.number,
          inputFormatters: [FilteringTextInputFormatter.digitsOnly],
          decoration: documentBoxDecoration(context),
          onChanged: (next) => _setState(() => _distanceKm = next),
        ),
      ),
    ];
  }

  Widget _noteLines(BuildContext context) {
    if (_order == null) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'No sales order chosen',
        message: 'A delivery note records what leaves against an order. '
            'Choose the order above and its lines appear here, at what is '
            'reserved for them.',
      );
    }
    return DocumentLineTable(
      columns: _columns,
      rows: [for (int i = 0; i < _lines.length; i++) _noteRow(context, i)],
    );
  }

  Widget _cellBox(
    BuildContext context, {
    required int index,
    required String name,
    required String value,
    required ValueChanged<String> onChanged,
    bool over = false,
  }) =>
      TextFormField(
        key: ValueKey<String>(
          'delivery-note-$name-${stringValue(_order?['id'])}-$index',
        ),
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
        onChanged: (next) => _setState(() {
          _current = index;
          onChanged(next);
        }),
      );

  Widget _noteRow(BuildContext context, int index) {
    final ThemeData theme = Theme.of(context);
    final DeliveryDraftLine line = _lines[index];
    final Product? product = _product(line.productId);
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final TextStyle? quiet =
        text?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final double delivering = _number(line.deliveryQuantity);
    return DocumentLineRow(
      key: ValueKey<String>('delivery-note-line-$index'),
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
        Text(documentQuantity(line.orderedQuantity), style: quiet),
        Text(
          documentQuantity(_trim(line.reserved)),
          style: line.reserved <= 0 && line.outstanding > 0
              ? text?.copyWith(color: theme.colorScheme.error)
              : quiet,
        ),
        Text(documentQuantity(line.alreadyDelivered), style: quiet),
        _cellBox(
          context,
          index: index,
          name: 'delivering',
          value: line.deliveryQuantity,
          over: delivering > line.deliverable,
          onChanged: (value) => line.deliveryQuantity = value,
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
          name: 'damaged',
          value: line.damagedQuantity,
          onChanged: (value) => line.damagedQuantity = value,
        ),
        Text(
          indianAmount(delivering * _number(line.unitPrice), full: true),
          style: text?.copyWith(fontWeight: FontWeight.w600),
        ),
      ],
    );
  }

  Widget _noteTotals() {
    double value = 0;
    for (final DeliveryDraftLine line in _lines) {
      value += _number(line.deliveryQuantity) * _number(line.unitPrice);
    }
    return DocumentTotalsBar(
      total: _order == null ? null : value,
      note: 'Choose the order going out.',
      figures: [("Value at the order's rates, before tax", value)],
    );
  }

  Widget _noteSidePanel(BuildContext context) {
    if (_lines.isEmpty) {
      return const DocumentSidePanel(children: [
        DocumentSideHeading('Dispatching'),
        DocumentSideNote(
          'Choose the order going out. Each line starts at what is reserved '
          'for it; batches can be chosen per line, earliest expiry first by default.',
        ),
      ]);
    }
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final int index = _current.clamp(0, _lines.length - 1);
    final DeliveryDraftLine line = _lines[index];
    final Product? product = _product(line.productId);
    final double delivering = _number(line.deliveryQuantity);
    final List<SerialRecord> onShelf =
        _serialsOnShelf[_DeliveryNoteEditorDialogState._shelfKey(
              line.productId,
              line.warehouseId,
            )] ??
            const [];
    final int? needed = line.unitsLeaving;
    return DocumentSidePanel(children: [
      DocumentSideHeading(
        'Line ${line.lineNumber} · ${product?.name ?? line.description}',
      ),
      DocumentSidePair('Ordered', documentQuantity(line.orderedQuantity)),
      DocumentSidePair(
        'Delivered before',
        documentQuantity(line.alreadyDelivered),
      ),
      DocumentSidePair(
        'Can go now',
        documentQuantity(_trim(line.deliverable)),
        bold: true,
        tone: delivering > line.deliverable ? scheme.error : null,
      ),
      if (line.outstanding <= 0)
        const DocumentSideNote('this line has been delivered in full')
      else if (line.reserved <= 0)
        const DocumentSideNote(
          'nothing is reserved for this line, so dispatching it would be '
          'refused; approve the sales order first',
        ),
      const SizedBox(height: 8),
      DocumentField(
        label: 'Leaves from warehouse',
        width: 258,
        child: DropdownButtonFormField<String>(
          key: ValueKey<String>(
            'delivery-note-warehouse-${stringValue(_order?['id'])}-$index',
          ),
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
              : (value) async {
                  _setState(() {
                    line.warehouseId = value ?? '';
                    // A unit is picked off one shelf; moving the line to
                    // another shelf un-picks it.
                    line.serialIds.clear();
                  });
                  await _loadSerials([line]);
                  if (mounted) _setState(() {});
                },
        ),
      ),
      if (!line.trackSerial) ..._batchPicker(context, line, index),
      if (line.trackSerial) ...[
        DocumentSideHeading(
          needed == null
              ? 'Serial numbers · ${line.serialIds.length} picked'
              : 'Serial numbers · ${line.serialIds.length} of $needed',
        ),
        if (onShelf.isEmpty)
          const DocumentSideNote(
            'none of this product is numbered and available in that '
            'warehouse; number the units under Stock first',
          )
        else
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (final SerialRecord serial in onShelf)
              FilterChip(
                key: ValueKey<String>('serial-pick-${serial.id}'),
                label: Text(serial.serialNumber),
                selected: line.serialIds.contains(serial.id),
                onSelected: _saving
                    ? null
                    : (picked) => _setState(() {
                          if (picked) {
                            line.serialIds.add(serial.id);
                          } else {
                            line.serialIds.remove(serial.id);
                          }
                        }),
              ),
          ]),
      ],
      const SizedBox(height: 8),
      DocumentField(
        label: 'Line remarks',
        width: 258,
        child: TextFormField(
          key: ValueKey<String>(
            'delivery-note-remarks-${stringValue(_order?['id'])}-$index',
          ),
          initialValue: line.remarks,
          readOnly: _saving,
          decoration: documentBoxDecoration(context),
          onChanged: (value) => line.remarks = value,
        ),
      ),
    ]);
  }

  String _availabilityKey(DeliveryDraftLine line) => [
        line.productId,
        line.warehouseId,
        _deliveryDate,
        line.deliveryQuantity.trim(),
      ].join('|');

  /// Ask for a line's batches when what they depend on has changed, a moment
  /// after the last change so typing a quantity is not a request per key.
  void _watchAvailability(DeliveryDraftLine line) {
    if (line.trackSerial || line.warehouseId.isEmpty) return;
    final String id = line.salesOrderLineId;
    final String key = _availabilityKey(line);
    if (_availabilityAsked[id] == key) return;
    _availabilityAsked[id] = key;
    _availabilityTimers[id]?.cancel();
    _availabilityTimers[id] = Timer(
      const Duration(milliseconds: 350),
      () => unawaited(_loadAvailability(line, key)),
    );
  }

  Future<void> _loadAvailability(DeliveryDraftLine line, String key) async {
    final String id = line.salesOrderLineId;
    final double quantity = _number(line.deliveryQuantity);
    try {
      final List<BatchAvailabilityRecord> rows =
          await widget.api.batchAvailability(
        productId: line.productId,
        warehouseId: line.warehouseId,
        asOf: DateTime.tryParse(_deliveryDate) == null ? null : _deliveryDate,
        quantity: quantity > 0 ? quantity : null,
        salesOrderLineId: id,
      );
      if (!mounted || _availabilityAsked[id] != key) return;
      _setState(() {
        _availability[id] = rows;
        _availabilityFailed.remove(id);
      });
    } on Object {
      // The picker is a courtesy: without it the server still goes earliest
      // expiry first at dispatch.
      if (!mounted || _availabilityAsked[id] != key) return;
      _setState(() => _availabilityFailed.add(id));
    }
  }

  /// What a batch's box shows: the person's own figure once they have made a
  /// choice, otherwise the earliest-expiry-first share the server suggests.
  double _shownPick(DeliveryDraftLine line, BatchAvailabilityRecord batch) {
    if (batch.expired) return 0;
    final Map<String, double>? picks = line.batchPicks;
    if (picks != null && picks.isNotEmpty) return picks[batch.batchId] ?? 0;
    return batch.fefo;
  }

  void _pickBatch(
    DeliveryDraftLine line,
    List<BatchAvailabilityRecord> batches,
    BatchAvailabilityRecord edited,
    String text,
  ) {
    // The first edit makes the whole split the person's own, starting from
    // what the boxes were showing.
    final Map<String, double> next = {
      for (final BatchAvailabilityRecord batch in batches)
        if (!batch.expired) batch.batchId: _shownPick(line, batch),
    };
    next[edited.batchId] = _number(text);
    _setState(() => line.batchPicks = next);
  }

  List<Widget> _batchPicker(
    BuildContext context,
    DeliveryDraftLine line,
    int index,
  ) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final TextStyle? small = theme.textTheme.bodySmall?.copyWith(fontSize: 11);
    final TextStyle? quiet = small?.copyWith(color: scheme.onSurfaceVariant);
    _watchAvailability(line);
    final String id = line.salesOrderLineId;
    final List<BatchAvailabilityRecord>? batches = _availability[id];
    final double delivering = _number(line.deliveryQuantity);
    final Map<String, double>? picks = line.batchPicks;
    final bool explicit = picks != null && picks.isNotEmpty;
    final List<Widget> out = [const DocumentSideHeading('Batches')];
    if (batches == null) {
      out.add(DocumentSideNote(_availabilityFailed.contains(id)
          ? 'could not read the batches; they will go earliest expiry first '
              'when the note is dispatched'
          : line.warehouseId.isEmpty
              ? 'choose the warehouse to see its batches'
              : 'reading the batches...'));
      return out;
    }
    if (batches.isEmpty) {
      out.add(const DocumentSideNote(
          'no stock of this product in that warehouse'));
      return out;
    }
    double chosen = 0;
    for (final BatchAvailabilityRecord batch in batches) {
      chosen += _shownPick(line, batch);
    }
    // A line entered in another unit than stock is converted by the server,
    // so the editor cannot say whether the split adds up.
    final bool comparable = line.salesUomId.isEmpty ||
        line.inventoryUomId.isEmpty ||
        line.salesUomId == line.inventoryUomId;
    final bool mismatch =
        comparable && delivering > 0 && (chosen - delivering).abs() > 0.0005;
    final int epoch = _pickEpoch[id] ?? 0;
    out.add(Column(
      key: const ValueKey('delivery-note-batch-picker'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final BatchAvailabilityRecord batch in batches)
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Opacity(
              opacity: batch.expired ? 0.5 : 1,
              child: Row(children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        batch.batchNumber.isEmpty
                            ? 'untracked stock'
                            : batch.batchNumber,
                        overflow: TextOverflow.ellipsis,
                        style: small?.copyWith(fontWeight: FontWeight.w600),
                      ),
                      Text(
                        [
                          if (batch.expiryDate.isNotEmpty)
                            'exp ${_dayOf(batch.expiryDate)}'
                          else
                            'no expiry',
                          if (batch.daysToExpiry != null && !batch.expired)
                            '${batch.daysToExpiry}d left',
                          'can take ${_trim(batch.availableToLine)}',
                        ].join(' · '),
                        overflow: TextOverflow.ellipsis,
                        style: quiet,
                      ),
                      if (batch.expired || batch.nearExpiry)
                        Padding(
                          padding: const EdgeInsets.only(top: 2),
                          child: StatusBadge(
                            label: batch.expired ? 'Expired' : 'Near expiry',
                            tone: batch.expired
                                ? StatusBadgeTone.danger
                                : StatusBadgeTone.warning,
                          ),
                        ),
                    ],
                  ),
                ),
                const SizedBox(width: 6),
                SizedBox(
                  width: 64,
                  child: KeyedSubtree(
                    key: ValueKey<String>(
                      'batch-pick-box-$id-${batch.batchId}-$epoch-'
                      '${_trim(batch.fefo)}',
                    ),
                    child: TextFormField(
                      key: ValueKey<String>('batch-pick-$id-${batch.batchId}'),
                      initialValue: _trim(_shownPick(line, batch)),
                      enabled: !batch.expired,
                      readOnly: _saving,
                      textAlign: TextAlign.right,
                      keyboardType: TextInputType.number,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        fontSize: 13,
                        color: _shownPick(line, batch) > batch.availableToLine
                            ? scheme.error
                            : null,
                      ),
                      decoration: documentCellDecoration(context),
                      onChanged: (value) =>
                          _pickBatch(line, batches, batch, value),
                    ),
                  ),
                ),
              ]),
            ),
          ),
        DocumentSidePair(
          'Chosen ${_trim(chosen)} of ${_trim(delivering)}',
          explicit ? 'your choice' : 'earliest expiry',
          bold: true,
          tone: mismatch ? scheme.error : null,
        ),
        if (mismatch)
          Text(
            'The batches do not add up to what this line delivers; '
            'dispatch will be refused.',
            style: small?.copyWith(color: scheme.error),
          ),
        if (line.batchPicks != null)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              key: const ValueKey('delivery-note-batch-reset'),
              onPressed: _saving
                  ? null
                  : () => _setState(() {
                        line.batchPicks = {};
                        _pickEpoch[id] = epoch + 1;
                      }),
              child: const Text('Use earliest expiry'),
            ),
          ),
      ],
    ));
    return out;
  }
}
