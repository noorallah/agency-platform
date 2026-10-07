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
    // Save & approve (D-BUY-22), and once this window has saved the note,
    // that note's own steps instead of a second save.
    final DocumentStep<Json>? approve = stepAfterSave(widget.steps);
    final Json? saved = _saved;
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.escape): () {
          if (!_saving) leaveDocument(context, result: saved, saved: saved != null);
        },
        const SingleActivator(LogicalKeyboardKey.keyS, control: true): () {
          if (!_saving && saved == null) unawaited(_save());
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
                    onPressed:
                        _saving ? null : () => leaveDocument(context, result: saved, saved: saved != null),
                    child: Text(saved == null ? 'Cancel' : 'Close'),
                  ),
                  if (saved != null)
                    DocumentStepStrip<Json>(
                      record: saved,
                      steps: widget.steps,
                      enabled: !_saving,
                      onRefused: (message) =>
                          _setState(() => _error = message),
                    )
                  else
                    ...saveButtons(
                      saveKey: const ValueKey('delivery-note-save'),
                      saveLabel: 'Save delivery note',
                      onSave: _saving ? null : () => unawaited(_save()),
                      stepKey: const ValueKey('delivery-note-save-approve'),
                      stepLabel: approve?.afterSave,
                      onStep: _saving || approve == null
                          ? null
                          : () => unawaited(_saveAndStep(approve)),
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
                            AdditionalDetailsSection(
                              controller: _customFields,
                              noun: 'delivery notes',
                              maxHeight: 132,
                              padding:
                                  const EdgeInsets.fromLTRB(12, 8, 12, 0),
                            ),
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
    // Choosing a carrier re-keys the three boxes it fills (SG-5), so each
    // starts again from the text just copied in.
    final Key refilled = ValueKey<int>(_transporterEpoch);
    return [
      DocumentField(
        label: 'Carrier (master)',
        width: 170,
        child: DropdownButtonFormField<String?>(
          key: const ValueKey('delivery-note-transporter'),
          initialValue: _transporters.any((t) => t.id == _transporterId)
              ? _transporterId
              : null,
          isExpanded: true,
          isDense: true,
          decoration: documentBoxDecoration(context),
          items: [
            const DropdownMenuItem<String?>(value: null, child: Text('(none)')),
            for (final TransporterRecord row in _transporters)
              DropdownMenuItem<String?>(
                value: row.id,
                child: Text(row.name, overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: _saving ? null : _chooseTransporter,
        ),
      ),
      DocumentField(
        label: 'Freight',
        width: 120,
        child: DropdownButtonFormField<String?>(
          key: const ValueKey('delivery-note-freight-terms'),
          initialValue: _freightTerms,
          isExpanded: true,
          isDense: true,
          decoration: documentBoxDecoration(context),
          items: [
            const DropdownMenuItem<String?>(value: null, child: Text('—')),
            for (final MapEntry<String, String> term in kFreightTerms.entries)
              DropdownMenuItem<String?>(
                value: term.key,
                child: Text(term.value, overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: _saving
              ? null
              : (value) => _setState(() => _freightTerms = value),
        ),
      ),
      KeyedSubtree(
        key: refilled,
        child: _box(
          context,
          label: 'Transporter',
          value: _transporterName,
          width: 170,
          onChanged: (value) => _transporterName = value,
        ),
      ),
      KeyedSubtree(
        key: ValueKey<String>('gstin-$_transporterEpoch'),
        child: DocumentField(
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
      ),
      KeyedSubtree(
        key: ValueKey<String>('mode-$_transporterEpoch'),
        child: DocumentField(
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
      if (line.ordersFreeGoods)
        DocumentSidePair(
          'Free on the order',
          documentQuantity(line.orderFreeQuantity),
        ),
      DocumentSideNote(freeBoxHelper(line).toLowerCase()),
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

  List<Widget> _batchPicker(
    BuildContext context,
    DeliveryDraftLine line,
    int index,
  ) {
    // A line entered in another unit than stock is converted by the server,
    // so the editor cannot say whether the split adds up.
    final bool comparable = line.salesUomId.isEmpty ||
        line.inventoryUomId.isEmpty ||
        line.salesUomId == line.inventoryUomId;
    return [
      BatchPickerPanel(
        api: widget.api,
        lineId: line.salesOrderLineId,
        salesOrderLineId: line.salesOrderLineId,
        customerId: stringValue(_order?['customer_id']),
        productId: line.productId,
        warehouseId: line.warehouseId,
        asOf: _deliveryDate,
        quantity: _number(line.deliveryQuantity),
        picks: line.batchPicks,
        enabled: !_saving,
        comparable: comparable,
        showPtrPts: widget.features.isEnabled('BATCH_PTR_PTS'),
        onChanged: (picks) => _setState(() => line.batchPicks = picks),
      ),
    ];
  }
}
