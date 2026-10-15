part of 'purchase_invoice_editor_dialog.dart';

/// The supplier bill screen in the phase 2 app: the documents' one-screen
/// layout (wireframe view 7) for a bill -- what it charges for and the
/// supplier's own number and date, the lines as a table, the totals to check
/// against the paper, and a side panel for the line being typed -- priced as
/// it is typed by `POST /purchase-invoices/preview`. The dialog's state,
/// validation and save are reused unchanged.
///
/// What the bill charges for follows the firm's buying stages (backlog §38):
/// a completed receipt on the whole chain, an approved order where nobody
/// types receipts, and a list of products where nobody types either -- the
/// server then raises the order and the receipt behind the bill.
extension _Phase2PurchaseInvoiceEditor on _PurchaseInvoiceEditorDialogState {
  List<DocumentColumn> get _columns => [
    const DocumentColumn('#', 28),
    _productColumn('Product'),
    const DocumentColumn('HSN', 66),
    // L5: typed as boxes and pieces, the figures read "3 x 12 + 5" and
    // Billing becomes the two boxes.
    DocumentColumn('Received', _boxAndPieces ? 84 : 72, numeric: true),
    DocumentColumn('Billed', _boxAndPieces ? 84 : 64, numeric: true),
    DocumentColumn('Due', _boxAndPieces ? 84 : 60, numeric: true),
    if (_boxAndPieces)
      ...boxPieceColumns.take(2)
    else
      const DocumentColumn('Billing', 76, numeric: true),
    const DocumentColumn('Rate', 90, numeric: true),
    const DocumentColumn('Taxable', 96, numeric: true),
    const DocumentColumn('GST', 48, numeric: true),
    const DocumentColumn('Amount', 104, numeric: true),
  ];

  /// An order's lines: what was ordered, what has arrived, what is still due.
  List<DocumentColumn> get _orderColumns => [
    const DocumentColumn('#', 28),
    _productColumn('Product'),
    const DocumentColumn('HSN', 66),
    DocumentColumn('Ordered', _boxAndPieces ? 84 : 72, numeric: true),
    DocumentColumn('Arrived', _boxAndPieces ? 84 : 64, numeric: true),
    DocumentColumn('Due', _boxAndPieces ? 84 : 60, numeric: true),
    if (_boxAndPieces)
      ...boxPieceColumns.take(2)
    else
      const DocumentColumn('Billing', 76, numeric: true),
    const DocumentColumn('Rate', 90, numeric: true),
    const DocumentColumn('Taxable', 96, numeric: true),
    const DocumentColumn('GST', 48, numeric: true),
    const DocumentColumn('Amount', 104, numeric: true),
  ];

  List<DocumentColumn> get _directColumns => [
    const DocumentColumn('#', 28),
    _productColumn('Product (code, name or barcode)'),
    const DocumentColumn('HSN', 66),
    if (_boxAndPieces)
      ...boxPieceColumns
    else ...const [
      DocumentColumn('Qty', 66, numeric: true),
      DocumentColumn('Free', 56, numeric: true),
    ],
    const DocumentColumn('Unit', 50),
    const DocumentColumn('Rate', 84, numeric: true),
    const DocumentColumn('Disc %', 60, numeric: true),
    const DocumentColumn('Taxable', 96, numeric: true),
    const DocumentColumn('GST', 48, numeric: true),
    const DocumentColumn('Amount', 104, numeric: true),
    const DocumentColumn('', 28),
  ];

  /// L5: the product column, with the boxes-and-pieces toggle drawn in its
  /// heading where it is offered and room kept for it.
  DocumentColumn _productColumn(String label) => DocumentColumn(
        label,
        0,
        minWidth: _offersBoxes ? 260 : DocumentLineTable.minFlexWidth,
        heading: _offersBoxes
            ? BoxPieceToggle(
                key: const ValueKey('purchase-invoice-box-and-pieces'),
                label: label,
                value: _boxAndPieces,
                onChanged: _saving || _editHeld
                    ? null
                    : (value) {
                        _setState(() => _boxesChoice = value);
                        _schedulePreview();
                      },
              )
            : null,
      );

  /// L5: the bill as saved said boxes and pieces.
  bool get _savedBoxes => widget.existing?['box_and_piece_entry'] == true;

  /// L5: the receipt or order being billed was typed in boxes and pieces.
  bool get _sourceBoxes => switch (_mode) {
        PurchaseBillMode.receipt => _receipt?.boxAndPieceEntry ?? false,
        PurchaseBillMode.order => _order?.boxAndPieceEntry ?? false,
        PurchaseBillMode.products => false,
      };

  /// Whether the toggle is offered: the firm's buying switch is on, or the
  /// bill or what it bills was typed in boxes and pieces.
  bool get _offersBoxes =>
      widget.stages.boxAndPieceEntry ||
      _sourceBoxes ||
      (_editing && _savedBoxes);

  /// Whether the lines are typed as boxes and pieces: as moved by hand, else
  /// as saved, else as the receipt or order being billed was typed, else --
  /// a bill of products -- the supplier's mark where the switch is on.
  bool get _boxAndPieces {
    if (!_phase2 || !_offersBoxes) return false;
    final bool? chosen = _boxesChoice;
    if (chosen != null) return chosen;
    if (_editing) return _savedBoxes;
    if (_direct) {
      return widget.stages.boxAndPieceEntry &&
          (_vendor(_vendorId)?.boxAndPieceEntry ?? false);
    }
    return _sourceBoxes;
  }

  /// L5: a bill of products' line: the pack it was saved at, else its
  /// item's buying pack; '' where it has none.
  String _directPackSize(PurchaseDirectLine line) => line.heldPack.isNotEmpty
      ? line.heldPack
      : _productById(line.productId)?.buyingPackSize ?? '';

  double? _directPack(PurchaseDirectLine line) =>
      packOf(_directPackSize(line));

  /// L5: a source line's cells, filled from its figure in pieces whenever
  /// they are drawn for another pack or after the pieces-only layout.
  BoxPieceEntry _billEntry(PurchaseInvoiceDraftLine line) {
    final String stamp = 'on|${line.packSize}';
    if (line.boxStamp != stamp) {
      line.boxes.load(
        quantity: line.invoiceQuantity,
        free: '',
        pack: packOf(line.packSize),
      );
      line.boxStamp = stamp;
    }
    return line.boxes;
  }

  /// L5: the same for a bill of products' line.
  BoxPieceEntry _directEntry(PurchaseDirectLine line) {
    final String stamp = 'on|${line.productId}|${_directPackSize(line)}';
    if (line.boxStamp != stamp) {
      line.boxes.load(
        quantity: line.quantity,
        free: line.freeQuantity,
        pack: _directPack(line),
      );
      line.boxStamp = stamp;
    }
    return line.boxes;
  }

  /// L5: a figure in pieces as the layout shows it.
  String _billFigure(PurchaseInvoiceDraftLine line, String value) =>
      _boxAndPieces
          ? boxesAndPieces(value, line.packSize)
          : documentQuantity(value);

  void _addDirectLine() {
    _setState(() {
      _directLines.add(PurchaseDirectLine());
      _current = _directLines.length - 1;
    });
  }

  Widget _phase2Page(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final String number = stringValue(_preview?.invoice['invoice_number']);
    final String duplicate =
        stringValue(_preview?.invoice['duplicate_warning']);
    final String irnWarning = stringValue(_preview?.invoice['irn_warning']);
    final String lateCredit =
        stringValue(_preview?.invoice['credit_time_limit_warning']);
    // Save & approve (D-BUY-22), and once this window has saved the bill,
    // that bill's own steps instead of a second save.
    // A draft being edited follows what it was stamped with when raised.
    final DocumentStep<Json>? sole = soleSaveStep(widget.steps,
        settingOff: !widget.stages.purchaseInvoiceApproval,
        existing: widget.existing);
    final DocumentStep<Json>? approve = sole ?? stepAfterSave(widget.steps);
    final Json? saved = _saved;
    // D-UI-39: a preview prices a new bill, so while a draft is edited it
    // finds that draft holding the same supplier number. Its own number is
    // not a duplicate.
    final bool ownNumber = _editing &&
        !_savedFigures &&
        _supplierInvoiceNumber.trim() == _held('supplier_invoice_number');
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.escape): () {
          if (!_saving) leaveDocument(context, result: saved, saved: saved != null);
        },
        const SingleActivator(LogicalKeyboardKey.keyS, control: true): () {
          if (!_saving && saved == null && !_editHeld) {
            unawaited(sole != null ? _saveAndStep(sole) : _save());
          }
        },
        const SingleActivator(LogicalKeyboardKey.enter, control: true): () {
          if (_direct && !_saving) _addDirectLine();
        },
      },
      // A scope, not a plain Focus: after a click outside a text box the
      // focus falls to the nearest scope, which was above these
      // shortcuts, so Esc and Ctrl+S did nothing (SC-SO-029).
      child: FocusScope(
        autofocus: true,
        child: Material(
          color: scheme.surface,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DocumentPageBand(
                // D-UI-39: a draft being edited says so, under its own
                // number rather than the next one a new bill would take.
                title: _editing
                    ? 'Edit purchase invoice'
                    : 'New purchase invoice',
                number: _editing ? _held('invoice_number') : '',
                chips: [
                  if (!_editing && number.isNotEmpty) '$number (new)',
                  if (_ownReceipt && _ownOrderNumber.isNotEmpty)
                    'against $_ownOrderNumber'
                  else if (_receipt != null)
                    'against ${_receipt!.grnNumber}',
                  if (_order != null) 'against ${_order!.poNumber}',
                  'Draft',
                ],
                hint: _direct
                    ? 'Ctrl+Enter new line  ·  Ctrl+S save'
                    : 'Enter next field  ·  Ctrl+S save',
                actions: [
                  TextButton(
                    onPressed:
                        _saving ? null : () => leaveDocument(context, result: saved, saved: saved != null),
                    child: Text(saved == null ? 'Cancel' : 'Close'),
                  ),
                  TextButton.icon(
                    key: const ValueKey('purchase-invoice-attachments'),
                    onPressed: _saving
                        ? null
                        : () => showDialog<void>(
                              context: context,
                              builder: (_) => DocumentAttachmentsDialog(
                                api: widget.api,
                                kind: AttachableDocument.purchaseInvoice,
                                // A draft being edited is already on file,
                                // so its files are its own from the start.
                                documentId: saved != null
                                    ? stringValue(saved['id'])
                                    : _editing
                                        ? _held('id')
                                        : null,
                                subtitle: saved != null
                                    ? stringValue(saved['invoice_number'])
                                    : _held('invoice_number'),
                                canEdit: widget.canAttach,
                              ),
                            ),
                    icon: const Icon(Icons.attach_file, size: 16),
                    label: const Text('Attachments'),
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
                      saveKey: const ValueKey('purchase-invoice-save'),
                      saveLabel: sole != null ? 'Save' : 'Save bill',
                      onSave: _saving || _editHeld
                          ? null
                          : sole != null
                              ? () => unawaited(_saveAndStep(sole))
                              : () => unawaited(_save()),
                      stepKey: const ValueKey('purchase-invoice-save-approve'),
                      stepLabel: sole != null ? null : approve?.afterSave,
                      onStep: _saving || _editHeld || approve == null
                          ? null
                          : () => unawaited(_saveAndStep(approve)),
                    ),
                ],
              ),
              for (final String message in [
                if (_error != null) _error!,
                // D-UI-39: the server keeps the receipt such a bill raised
                // as it is when the bill is edited, so a quantity changed
                // here would leave the two disagreeing about what arrives.
                if (_ownReceipt)
                  'This bill receives its own goods'
                      '${_ownOrderNumber.isEmpty ? '' : ' against $_ownOrderNumber'}'
                      '. Its rates, dates and numbers can be changed here; '
                      'its quantities, batches and expiry dates cannot yet. '
                      'To change those, cancel the bill and enter it again.',
                if (duplicate.isNotEmpty &&
                    _supplierInvoiceNumber.trim().isNotEmpty &&
                    !ownNumber)
                  '$duplicate Check it is not the same bill entered twice.',
                if (irnWarning.isNotEmpty) irnWarning,
                // Past the credit's last date (s.16(4), GST-3).
                if (lateCredit.isNotEmpty) lateCredit,
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
                            AdditionalDetailsSection(
                              controller: _customFields,
                              noun: 'purchase invoices',
                              maxHeight: 132,
                              padding:
                                  const EdgeInsets.fromLTRB(12, 8, 12, 0),
                            ),
                            Expanded(
                              child: _editHeld
                                  ? _editHold()
                                  : _direct
                                      ? _directLinesTable(context)
                                      : _billLines(context),
                            ),
                            _billTotals(),
                          ],
                        ),
                      ),
                      if (constraints.maxWidth >= DocumentSidePanel.showFrom &&
                          !_editHeld)
                        _direct
                            ? _directSidePanel(context)
                            : _billSidePanel(context),
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

  /// What stands where the lines go while a draft's receipts are read, or
  /// where it cannot be edited from here: the reason, never empty boxes
  /// that would save as a different bill (D-UI-39).
  Widget _editHold() => _loadingEdit
      ? const SizedBox.shrink()
      : StandardEmptyState(
          key: const ValueKey('purchase-invoice-edit-block'),
          type: EmptyStateType.noRecords,
          title: 'This bill cannot be changed here',
          message: _editBlock ?? '',
        );

  /// Who a draft being edited is from, and what it is typed against. Not a
  /// picker: a bill for the wrong supplier is cancelled, not moved.
  Widget _editSourceField(BuildContext context) {
    final String supplier = _held('vendor_name');
    return DocumentField(
      label: 'Supplier',
      width: 400,
      below: _quietLine(
        context,
        _loadingEdit
            ? 'Reading the bill…'
            : _editBlock != null
                ? ''
                : _direct
                    ? 'typed directly  ·  saving raises its order and '
                        'receipt again'
                    : _ownReceipt
                        ? 'approving the bill receives what it charges for'
                        : 'for the goods receipts on this bill',
      ),
      child: InputDecorator(
        key: const ValueKey('purchase-invoice-edit-supplier'),
        decoration: documentBoxDecoration(context),
        child: Text(
          supplier.isEmpty ? '—' : supplier,
          overflow: TextOverflow.ellipsis,
        ),
      ),
    );
  }

  /// The server's figures for a product line: its line of the last pricing,
  /// or -- while a draft being edited still shows the bill as saved -- the
  /// saved line, for as long as the line is typed as it was saved.
  Map<String, dynamic>? _pricedDirect(int index) {
    final PurchaseDirectLine line = _directLines[index];
    if (_savedFigures) {
      return line.changedSinceSaved || _headerChangedSinceSaved
          ? null
          : line.saved;
    }
    return _pricedByNumber(_sentNumber(index), line.productId);
  }

  Product? _product(String id) => _productById(id);

  Vendor? _vendor(String? id) {
    for (final Vendor item in _vendorChoices) {
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

  InputDecorationTheme _pickerTheme(ColorScheme scheme) => InputDecorationTheme(
        isDense: true,
        filled: true,
        fillColor: scheme.surfaceContainerLowest,
        contentPadding: const EdgeInsets.symmetric(horizontal: 8),
        constraints: const BoxConstraints(maxHeight: 36),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(5)),
      );

  Widget _quietLine(BuildContext context, String text) {
    final ThemeData theme = Theme.of(context);
    return Text(
      text,
      overflow: TextOverflow.ellipsis,
      style: theme.textTheme.bodySmall?.copyWith(
        fontSize: 11,
        color: theme.colorScheme.onSurfaceVariant,
      ),
    );
  }

  /// The line under a supplier picker, with a note added when the supplier
  /// is declared to charge no GST (backlog 78 row 2). Informational only.
  Widget? _withNoGstNote(BuildContext context, Widget? line, Vendor? vendor) {
    if (vendor == null || !vendor.chargesNoGst) return line;
    final ThemeData theme = Theme.of(context);
    final Widget note = Text(
      'This supplier charges no GST; the bill will carry no tax.',
      key: const ValueKey('purchase-invoice-no-gst-note'),
      style: theme.textTheme.bodySmall?.copyWith(
        fontSize: 11,
        color: theme.colorScheme.tertiary,
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [if (line != null) line, note],
    );
  }

  /// What the bill charges for: a receipt, an order or -- typed directly --
  /// the supplier.
  Widget _sourceField(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    if (_editing) return _editSourceField(context);
    switch (_mode) {
      case PurchaseBillMode.receipt:
        final GoodsReceiptRecord? receipt = _receipt;
        final String? vendorId = _tickVendorId;
        return DocumentField(
          label: 'Supplier (only those with receipts to bill)',
          width: 400,
          below: _withNoGstNote(
            context,
            receipt == null
                ? null
                : _quietLine(
                    context,
                    [
                      'received ${_dayOf(receipt.receiptDate)}',
                      if (receipt.purchaseOrderNumber.isNotEmpty)
                        'order ${receipt.purchaseOrderNumber}',
                      if (receipt.invoiceReference.isNotEmpty)
                        'bill noted on receipt ${receipt.invoiceReference}',
                    ].join('  ·  '),
                  ),
            vendorId == null ? null : _vendor(vendorId),
          ),
          child: DropdownMenu<String>(
            key: const ValueKey('purchase-invoice-receipt-supplier'),
            initialSelection: vendorId,
            width: 400,
            enabled: !_saving,
            enableFilter: true,
            requestFocusOnTap: true,
            menuHeight: 320,
            hintText: 'Choose the supplier first',
            inputDecorationTheme: _pickerTheme(scheme),
            dropdownMenuEntries: [
              for (final GoodsReceiptRecord item in _receiptSuppliers)
                DropdownMenuEntry<String>(
                  value: item.vendorId,
                  label: _receiptSupplierName(item),
                ),
            ],
            onSelected: (value) => unawaited(_chooseBillVendor(value)),
          ),
        );
      case PurchaseBillMode.order:
        final PurchaseOrder? order = _order;
        return DocumentField(
          label: 'Purchase order being billed (approved only)',
          width: 400,
          below: _withNoGstNote(
            context,
            order == null
                ? null
                : _quietLine(
                    context,
                    '${_vendor(order.vendorId)?.displayName ?? 'supplier'}'
                    '  ·  ordered ${_dayOf(order.purchaseDate)}'
                    '  ·  saving receives what the bill charges for',
                  ),
            order == null ? null : _vendor(order.vendorId),
          ),
          child: DropdownMenu<String>(
            key: const ValueKey('purchase-invoice-order'),
            initialSelection: order?.id,
            width: 400,
            enabled: !_saving,
            enableFilter: true,
            requestFocusOnTap: true,
            menuHeight: 320,
            inputDecorationTheme: _pickerTheme(scheme),
            dropdownMenuEntries: [
              for (final PurchaseOrder item in widget.orders)
                DropdownMenuEntry<String>(
                  value: item.id,
                  label: '${item.poNumber}  ${_dayOf(item.purchaseDate)}'
                      '  ${_vendor(item.vendorId)?.displayName ?? ''}',
                ),
            ],
            onSelected: (value) {
              for (final PurchaseOrder item in widget.orders) {
                if (item.id == value && item.id != _order?.id) {
                  _current = 0;
                  _preview = null;
                  _selectOrder(item);
                  unawaited(_loadOrderFamily(item));
                  _schedulePreview();
                }
              }
            },
          ),
        );
      case PurchaseBillMode.products:
        final Vendor? vendor = _vendor(_vendorId);
        return DocumentField(
          label: 'Supplier (type code or name)',
          width: 400,
          below: _withNoGstNote(
            context,
            vendor == null
                ? null
                : DocumentGstinLine(
                    gstin: vendor.gstin,
                    leading: [vendor.code],
                  ),
            vendor,
          ),
          // Built again when a supplier is added from here, so the box shows
          // the new name: a DropdownMenu reads its selection only once.
          child: DropdownMenu<String>(
            key: _addedVendors.isEmpty
                ? const ValueKey('purchase-invoice-vendor')
                : ValueKey('purchase-invoice-vendor-${_addedVendors.length}'),
            initialSelection: _vendorId,
            width: 400,
            enabled: !_saving,
            enableFilter: true,
            requestFocusOnTap: true,
            menuHeight: 320,
            inputDecorationTheme: _pickerTheme(scheme),
            dropdownMenuEntries: [
              for (final Vendor item in _vendorChoices)
                DropdownMenuEntry<String>(
                  value: item.id,
                  label: withPlace(
                      '${item.displayName} — ${item.code}', vendorPlace(item)),
                ),
            ],
            onSelected: (value) {
              _setState(() => _vendorId = value);
              _schedulePreview();
            },
          ),
        );
    }
  }

  /// The suppliers with receipts waiting to be billed, one entry each.
  List<GoodsReceiptRecord> get _receiptSuppliers {
    final Map<String, GoodsReceiptRecord> byVendor =
        <String, GoodsReceiptRecord>{};
    for (final GoodsReceiptRecord item in widget.receipts) {
      byVendor.putIfAbsent(item.vendorId, () => item);
    }
    final List<GoodsReceiptRecord> rows = byVendor.values.toList()
      ..sort((a, b) =>
          _receiptSupplierName(a).compareTo(_receiptSupplierName(b)));
    return rows;
  }

  String _receiptSupplierName(GoodsReceiptRecord receipt) {
    if (receipt.vendorName.isNotEmpty) return receipt.vendorName;
    return _vendor(receipt.vendorId)?.displayName ?? receipt.vendorId;
  }

  /// Choose whose receipts are billed: what the bill held goes, and a
  /// supplier with one receipt waiting has it ticked; with more, the list
  /// opens.
  Future<void> _chooseBillVendor(String? value) async {
    if (value == null || value == _tickVendorId) return;
    await _setReceipts(const []);
    if (!mounted) return;
    _setState(() {
      _billVendorId = value;
      _preview = null;
    });
    final List<GoodsReceiptRecord> receipts = _vendorReceipts;
    if (receipts.length == 1) {
      await _setReceipts(receipts);
      _schedulePreview();
    } else if (receipts.length > 1) {
      await _tickReceipts();
    }
  }

  /// Offer the supplier's receipts as a tick list and bill those ticked
  /// (SEL-1, backlog 58 items 2 and 4).
  Future<void> _tickReceipts() async {
    final List<GoodsReceiptRecord> receipts = _vendorReceipts;
    if (receipts.isEmpty) return;
    GoodsReceiptRecord byId(String id) =>
        receipts.firstWhere((item) => item.id == id);
    final List<String>? picked = await showSourceTickDialog(
      context,
      title: 'Goods receipts to bill — ${_receiptSupplierName(receipts.first)}',
      keyPrefix: 'purchase-invoice',
      rows: [
        for (final GoodsReceiptRecord item in receipts)
          SourceTickRow(
            id: item.id,
            number: item.grnNumber,
            date: _dayOf(item.receiptDate),
            order: item.purchaseOrderNumber,
            amount: documentMoney(item.billableAmount),
          ),
      ],
      initial: {
        if (_receipt != null) _receipt!.id,
        for (final GoodsReceiptRecord item in _extraReceipts) item.id,
      },
      clashFor: (id, ticked) => _receiptClash(
        byId(id),
        [for (final String other in ticked) byId(other)],
      ),
      numberLabel: 'Goods receipt',
      amountLabel: 'Left to bill',
      confirmNoun: 'receipt',
    );
    if (picked == null || !mounted) return;
    await _setReceipts([for (final String id in picked) byId(id)]);
    _schedulePreview();
  }

  /// The receipts on the bill, and the button that opens the tick list.
  Widget? _receiptsField(BuildContext context) {
    if (_mode != PurchaseBillMode.receipt || _tickVendorId == null) {
      return null;
    }
    // D-UI-39: a receipt the bill raised itself is not one to choose among,
    // and nothing is offered while a draft is read or cannot be edited.
    if (_ownReceipt || _editHeld) return null;
    final ThemeData theme = Theme.of(context);
    final int waiting = _vendorReceipts.length;
    final List<GoodsReceiptRecord> on = [
      if (_receipt != null) _receipt!,
      ..._extraReceipts,
    ];
    return DocumentField(
      label: 'Goods receipts on this bill',
      width: 400,
      child: Wrap(
        spacing: 6,
        runSpacing: 4,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          for (final GoodsReceiptRecord item in on)
            Chip(
              key: ValueKey<String>('purchase-invoice-receipt-chip-${item.id}'),
              label: Text(item.grnNumber),
              visualDensity: VisualDensity.compact,
            ),
          if (on.isEmpty)
            Text(
              'None ticked yet',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: theme.colorScheme.error),
            ),
          TextButton.icon(
            key: const ValueKey('purchase-invoice-choose-receipts'),
            onPressed: _saving ? null : () => unawaited(_tickReceipts()),
            icon: const Icon(Icons.checklist, size: 16),
            label: Text(waiting == 1
                ? 'Choose receipts (1 waiting)'
                : 'Choose receipts ($waiting waiting)'),
          ),
        ],
      ),
    );
  }

  Widget _billHeader(BuildContext context) {
    final Widget? also = _receiptsField(context);
    return DocumentHeader(children: [
      _sourceField(context),
      // Backlog 128: a supplier not in the list yet is added without
      // leaving the bill.
      if (_mode == PurchaseBillMode.products && widget.canAddVendor)
        DocumentField(
          label: '',
          width: 150,
          child: OutlinedButton.icon(
            key: const ValueKey('purchase-invoice-new-supplier'),
            onPressed: _saving ? null : () => unawaited(_addVendor()),
            icon: const Icon(Icons.add, size: 18),
            label: const Text('New supplier'),
          ),
        ),
      // Backlog 140: the order is on the company and the bill is from one of
      // its offices, or from a branch nobody has entered yet.
      if (_mode == PurchaseBillMode.order && _orderOffices != null)
        DocumentField(
          label: 'Billed by',
          width: 280,
          below: _quietLine(
            context,
            'The office of this supplier the bill is from',
          ),
          child: DropdownMenu<String>(
            key: _officesEpoch == 0
                ? const ValueKey('purchase-invoice-billed-by')
                : ValueKey('purchase-invoice-billed-by-$_officesEpoch'),
            initialSelection: _billedById ?? _order?.vendorId,
            width: 280,
            enabled: !_saving,
            inputDecorationTheme: _pickerTheme(Theme.of(context).colorScheme),
            dropdownMenuEntries: [
              for (final VendorFamilyMember office in _orderOffices!)
                DropdownMenuEntry<String>(
                  value: office.id,
                  label: '${office.code}  ${office.name}'
                      '${office.isParent ? '  (main office)' : ''}',
                ),
            ],
            onSelected: _chooseBilledBy,
          ),
        ),
      if (_offersNewBranch)
        DocumentField(
          label: '',
          width: 140,
          child: OutlinedButton.icon(
            key: const ValueKey('purchase-invoice-new-branch'),
            onPressed: _saving ? null : () => unawaited(_addBranch()),
            icon: const Icon(Icons.add, size: 18),
            label: const Text('New branch'),
          ),
        ),
      if (also != null) also,
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
        label: "IRN (from the supplier's e-invoice)",
        width: 260,
        child: TextFormField(
          key: const ValueKey('purchase-invoice-supplier-irn'),
          initialValue: _supplierIrn,
          readOnly: _saving,
          decoration: documentBoxDecoration(context, hint: '64 characters'),
          onChanged: (value) {
            _setState(() => _supplierIrn = value);
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
            _interstate == null
                ? '—'
                : _interstate!
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
      // PG-12: the currency the supplier billed in. Untouched, it is the
      // order's, or the supplier's where the bill names no order (D-BUY-42);
      // blank or INR is rupees.
      DocumentField(
        label: 'Currency',
        width: 110,
        child: TextFormField(
          key: ValueKey<String>(
            'purchase-invoice-currency-${_billSupplierId ?? ''}-'
            '$_startingCurrency',
          ),
          initialValue: _billCurrency,
          readOnly: _saving,
          maxLength: 3,
          textCapitalization: TextCapitalization.characters,
          decoration: documentBoxDecoration(context, hint: 'INR').copyWith(
            counterText: '',
          ),
          onChanged: (value) {
            _setState(() {
              _currency = value.trim().toUpperCase();
              _currencyTouched = true;
            });
            _schedulePreview();
          },
        ),
      ),
      if (_foreign)
        DocumentField(
          label: 'Exchange rate (₹ per $_billCurrency)',
          width: 190,
          // Rebuilt when the order behind the bill changes, so the box
          // shows that order's rate until somebody types another.
          child: KeyedSubtree(
            key: ValueKey<String>(
              'purchase-invoice-rate-of-${_receipt?.id ?? _order?.id ?? ''}',
            ),
            child: TextFormField(
              key: ValueKey<String>(
                  'purchase-invoice-exchange-rate-$_billCurrency'),
              initialValue: _billRate,
              readOnly: _saving,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: documentBoxDecoration(context, hint: 'e.g. 84.10'),
              onChanged: (value) {
                _setState(() {
                  _exchangeRate = value;
                  _rateTouched = true;
                });
                _schedulePreview();
              },
            ),
          ),
        ),
      if (_foreign)
        DocumentField(
          label: 'Not offered in $_billCurrency',
          width: 330,
          child: InputDecorator(
            decoration: documentBoxDecoration(context),
            child: Text(
              'TCS, TDS and Paid now are rupee matters; pay this bill from '
              'Payments in $_billCurrency.',
              key: const ValueKey('purchase-invoice-foreign-note'),
              style: Theme.of(context).textTheme.bodySmall,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
      // PG-6: TCS the supplier charged under 206C(1H), outside GST. Blank
      // is none; the amount, if typed, wins over the rate.
      if (!_foreign)
      DocumentField(
        label: 'TCS charged by supplier %',
        width: 170,
        child: TextFormField(
          key: const ValueKey('purchase-invoice-tcs-rate'),
          initialValue: _tcsRate,
          readOnly: _saving,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: documentBoxDecoration(context, hint: 'e.g. 0.1'),
          onChanged: (value) {
            _setState(() {
              _tcsRate = value;
              _tcsTouched = true;
            });
            _schedulePreview();
          },
        ),
      ),
      if (!_foreign)
      DocumentField(
        label: 'TCS amount',
        width: 150,
        child: TextFormField(
          key: const ValueKey('purchase-invoice-tcs-amount'),
          initialValue: _tcsAmount,
          readOnly: _saving,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration:
              documentBoxDecoration(context, hint: 'blank: rate x total'),
          onChanged: (value) {
            _setState(() {
              _tcsAmount = value;
              _tcsTouched = true;
            });
            _schedulePreview();
          },
        ),
      ),
    ]);
  }

  Widget _billLines(BuildContext context) {
    if (!_hasSource) {
      final bool order = _mode == PurchaseBillMode.order;
      return StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: order ? 'No purchase order chosen' : 'No goods receipt chosen',
        message: order
            ? 'Choose the order the bill is for and its lines appear here, at '
                'what is still to arrive. Saving the bill receives the goods.'
            : 'A bill charges for what a receipt brought in. Choose the '
                'receipt above and its lines appear here, at what is still to '
                'be billed.',
      );
    }
    return DocumentLineTable(
      columns: _mode == PurchaseBillMode.order ? _orderColumns : _columns,
      rows: [for (int i = 0; i < _lines.length; i++) _billRow(context, i)],
    );
  }

  Map<String, dynamic>? _pricedLine(int index) {
    final PurchaseInvoiceDraftLine line = _lines[index];
    if (_savedFigures) {
      // D-UI-39: a draft being edited shows each line as the bill holds it,
      // for as long as the line is typed as it was saved.
      return line.changedSinceSaved || _headerChangedSinceSaved
          ? null
          : line.saved;
    }
    for (final dynamic raw in _preview?.invoice['lines'] as List? ?? const []) {
      if (raw is Map &&
          stringValue(raw['source_document_line_id']) ==
              line.sourceDocumentLineId) {
        return Map<String, dynamic>.from(raw);
      }
    }
    // An order's lines come back naming the receipt the preview raised, so
    // their own ids cannot match. The preview answers in the lines sent,
    // numbered from one, and a line with nothing to bill is not sent -- so
    // its place among those sent is its number.
    int number = 0;
    for (int i = 0; i <= index && i < _lines.length; i++) {
      final bool sent = _number(_lines[i].invoiceQuantity) > 0;
      if (sent) number++;
      if (i == index && !sent) return null;
    }
    return _pricedByNumber(number, _lines[index].productId);
  }

  Map<String, dynamic>? _pricedByNumber(int? number, String? productId) {
    if (number == null) return null;
    for (final dynamic raw in _preview?.invoice['lines'] as List? ?? const []) {
      if (raw is Map &&
          (raw['line_number'] as num?)?.toInt() == number &&
          (stringValue(raw['product_id']).isEmpty ||
              stringValue(raw['product_id']) == (productId ?? ''))) {
        return Map<String, dynamic>.from(raw);
      }
    }
    return null;
  }

  DocumentPreviewLine? _companionOf(Map<String, dynamic>? priced) {
    if (priced == null) return null;
    final int number = (priced['line_number'] as num?)?.toInt() ?? 0;
    for (final DocumentPreviewLine line
        in _preview?.lines ?? const <DocumentPreviewLine>[]) {
      if (line.lineNumber == number) return line;
    }
    return null;
  }

  DocumentPreviewLine? _companion(int index) =>
      _companionOf(_pricedLine(index));

  /// The line's value before tax, as typed: what shows until the server's
  /// figure arrives, and for a line not being billed.
  double _typedTaxable(PurchaseInvoiceDraftLine line) =>
      _number(line.invoiceQuantity) *
      _number(line.unitPrice.trim().isEmpty
          ? line.receiptUnitPrice
          : line.unitPrice);

  double _typedDirectTaxable(PurchaseDirectLine line) {
    final Product? product = _productById(line.productId);
    final double rate = line.unitPrice.trim().isEmpty
        ? _number(product?.purchasePrice ?? '')
        : _number(line.unitPrice);
    return line.quantityValue *
        rate *
        (1 - _number(line.discountPercent) / 100);
  }

  Widget _cellBox(
    BuildContext context, {
    required int index,
    required String name,
    required String value,
    required ValueChanged<String> onChanged,
    bool over = false,
    String? hint,
    String epoch = '',
    bool locked = false,
  }) =>
      TextFormField(
        key: ValueKey<String>(
          'purchase-invoice-$name-${_receipt?.id ?? _order?.id ?? 'direct'}'
          '-$index$epoch${_extraReceipts.map((r) => r.id).join()}',
        ),
        initialValue: value.trim().isEmpty ? value : documentQuantity(value),
        readOnly: _saving || locked,
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

  List<Widget> _figures(
    BuildContext context,
    Map<String, dynamic>? priced,
    double typed, {
    bool billing = true,
    bool owed = false,
  }) {
    final TextStyle? text =
        Theme.of(context).textTheme.bodyMedium?.copyWith(fontSize: 13);
    if (owed) {
      // D-UI-39: changed since the bill was saved and not priced again, so
      // no figure is shown rather than one worked out here.
      return [Text('—', style: text), Text('', style: text), Text('—', style: text)];
    }
    final double taxable = priced == null
        ? typed
        // With the bill discount's share and the line's charges (D-UI-96):
        // the amount less its tax is what the line was taxed on.
        : documentLineTaxable(priced['net_amount'], priced['tax_amount']) ?? 0;
    final double tax =
        priced == null ? 0 : _number(stringValue(priced['tax_amount']));
    final double rate = taxable > 0 ? tax / taxable * 100 : 0;
    return [
      Text(indianAmount(taxable, full: true), style: text),
      Text(
        priced == null || !billing
            ? ''
            : '${documentQuantity(rate.toStringAsFixed(1))}%',
        style: text,
      ),
      Text(
        indianAmount(taxable + tax, full: true),
        style: text?.copyWith(fontWeight: FontWeight.w600),
      ),
    ];
  }

  Widget _billRow(BuildContext context, int index) {
    final ThemeData theme = Theme.of(context);
    final PurchaseInvoiceDraftLine line = _lines[index];
    final Product? product = _product(line.productId);
    final Map<String, dynamic>? priced = _pricedLine(index);
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final TextStyle? quiet =
        text?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final double billing = _number(line.invoiceQuantity);
    // L5: in the pieces-only layout the box cells go stale; they are filled
    // again when the layout comes back.
    if (!_boxAndPieces) line.boxStamp = '';
    return DocumentLineRow(
      key: ValueKey<String>('purchase-invoice-line-$index'),
      columns: line.billsAnOrder ? _orderColumns : _columns,
      current: index == _current,
      onTap: () => _setState(() => _current = index),
      cells: [
        Text('${line.lineNumber}', style: text),
        Padding(
          padding: const EdgeInsets.only(right: 8),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                product == null
                    ? (line.description.isEmpty
                        ? line.productId
                        : line.description)
                    : '${product.name}  ${product.code}',
                overflow: TextOverflow.ellipsis,
                style: text,
              ),
              // With several receipts on the bill, two "line 1"s are told
              // apart by the receipt each comes from.
              if (_extraReceipts.isNotEmpty)
                _quietLine(context, 'receipt ${_grnOf(line.sourceDocumentId)}'),
            ],
          ),
        ),
        Text(product?.hsnSac ?? '', style: text),
        Text(
          _billFigure(line, line.receivedQuantity),
          key: ValueKey<String>('purchase-invoice-received-$index'),
          style: quiet,
        ),
        Text(
          _billFigure(line, line.alreadyInvoiced),
          key: ValueKey<String>('purchase-invoice-billed-$index'),
          style: quiet,
        ),
        Text(
          _billFigure(
            line,
            _PurchaseInvoiceEditorDialogState._trim(line.outstanding),
          ),
          key: ValueKey<String>('purchase-invoice-due-$index'),
          style: text?.copyWith(fontWeight: FontWeight.w600),
        ),
        if (_boxAndPieces)
          // Billing as two boxes; a bill line has no free cells.
          ...boxPieceCells(
            context,
            entry: _billEntry(line),
            pack: packOf(line.packSize),
            // The receipt this bill raised keeps its quantity on an edit.
            readOnly: _saving || _ownReceipt,
            keyPrefix: 'purchase-invoice-line-$index',
            // A line not billed now stays at nothing.
            chargedRequired: false,
            onChanged: () {
              _setState(() {
                line.invoiceQuantity =
                    line.boxes.quantityText(packOf(line.packSize));
                _current = index;
              });
              _schedulePreview();
            },
          ).take(2)
        else
          _cellBox(
            context,
            index: index,
            name: 'billing',
            value: line.invoiceQuantity,
            over: billing > line.outstanding,
            // The receipt this bill raised keeps its quantity on an edit.
            locked: _ownReceipt,
            onChanged: (value) => line.invoiceQuantity = value,
          ),
        _cellBox(
          context,
          index: index,
          name: 'rate',
          value: line.unitPrice,
          // Blank takes the receipt's (or the order's) price; say which.
          hint: documentMoney(line.receiptUnitPrice),
          onChanged: (value) => line.unitPrice = value,
        ),
        ..._figures(
          context,
          priced,
          _typedTaxable(line),
          billing: billing > 0,
          owed: _figuresOwed && priced == null && billing > 0,
        ),
      ],
    );
  }

  /// Where a direct line stands in what is sent: the payload skips lines
  /// with nothing to bill, so its number is its place among the rest.
  int? _sentNumber(int index) {
    int number = 0;
    for (int i = 0; i <= index && i < _directLines.length; i++) {
      final bool sent = _directLines[i].sendable;
      if (sent) number++;
      if (i == index) return sent ? number : null;
    }
    return null;
  }

  Widget _directLinesTable(BuildContext context) => DocumentLineTable(
        columns: _directColumns,
        rows: [
          for (int i = 0; i < _directLines.length; i++) _directRow(context, i),
        ],
        addLabel: '${_directLines.length + 1}'
            '     + add a product (Ctrl+Enter)',
        onAdd: _saving ? null : _addDirectLine,
      );

  Widget _directRow(BuildContext context, int index) {
    final ThemeData theme = Theme.of(context);
    final PurchaseDirectLine line = _directLines[index];
    final Product? product = _productById(line.productId);
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final Map<String, dynamic>? priced = _pricedDirect(index);
    final DocumentPreviewLine? companion = _companionOf(priced);
    if (!_boxAndPieces) line.boxStamp = '';
    return DocumentLineRow(
      key: ValueKey<String>('purchase-invoice-direct-$index'),
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
              key: ValueKey<String>('purchase-invoice-direct-product-$index'),
              initialSelection: line.productId,
              expandedInsets: EdgeInsets.zero,
              enabled: !_saving,
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
                _setState(() {
                  // L5: another product has its own pack.
                  if (value != line.productId) line.heldPack = '';
                  line.productId = value;
                  _current = index;
                });
                _schedulePreview();
              },
            ),
            if (companion != null)
              _quietLine(
                context,
                'Stock ${documentQuantity(companion.availableQuantity)}'
                '${companion.lastPrice.isEmpty ? '' : '  ·  last from them '
                    '${documentMoney(companion.lastPrice)}'}',
              ),
          ],
        ),
        Text(product?.hsnSac ?? '', style: text),
        if (_boxAndPieces)
          ...boxPieceCells(
            context,
            entry: _directEntry(line),
            pack: _directPack(line),
            readOnly: _saving,
            keyPrefix: 'purchase-invoice-direct-$index',
            onChanged: () {
              final double? pack = _directPack(line);
              _setState(() {
                line.quantity = line.boxes.quantityText(pack);
                line.freeQuantity = line.boxes.freeText(pack);
                _current = index;
              });
              _schedulePreview();
            },
          )
        else ...[
          _cellBox(
            context,
            index: index,
            name: 'direct-quantity',
            value: line.quantity,
            onChanged: (value) => line.quantity = value,
          ),
          _cellBox(
            context,
            index: index,
            name: 'direct-free',
            value: line.freeQuantity,
            onChanged: (value) => line.freeQuantity = value,
          ),
        ],
        Text(product?.unit ?? '', style: text),
        _cellBox(
          context,
          index: index,
          name: 'direct-rate',
          value: line.unitPrice,
          // Never prefilled: blank takes the product's purchase price.
          hint: product == null || product.purchasePrice.isEmpty
              ? null
              : documentMoney(product.purchasePrice),
          onChanged: (value) => line.unitPrice = value,
        ),
        _cellBox(
          context,
          index: index,
          name: 'direct-discount',
          value: line.discountPercent,
          onChanged: (value) => line.discountPercent = value,
        ),
        ..._figures(context, priced, _typedDirectTaxable(line)),
        IconButton(
          tooltip: 'Remove line',
          iconSize: 16,
          visualDensity: VisualDensity.compact,
          onPressed: _directLines.length == 1 || _saving
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

  Widget _billTotals() {
    if (_loadingEdit) {
      return const DocumentTotalsBar(figures: [], note: 'Reading the bill…');
    }
    if (_editBlock != null) {
      return const DocumentTotalsBar(figures: []);
    }
    if (_figuresOwed) {
      // D-UI-39: see [_figuresOwed]. The saved totals are no longer this
      // bill's, and none is worked out here in their place.
      return const DocumentTotalsBar(
        key: ValueKey('purchase-invoice-totals-owed'),
        figures: [],
        note: 'Changed since it was saved: its tax and total are worked out '
            'when the bill is saved.',
      );
    }
    final Map<String, dynamic>? invoice = _preview?.invoice;
    double typed = 0;
    if (_direct) {
      for (final PurchaseDirectLine line in _directLines) {
        typed += _typedDirectTaxable(line);
      }
    } else {
      for (final PurchaseInvoiceDraftLine line in _lines) {
        typed += _typedTaxable(line);
      }
    }
    final double taxable =
        invoice == null ? typed : _number(stringValue(invoice['subtotal']));
    final double tax =
        invoice == null ? 0 : _number(stringValue(invoice['tax_total']));
    final double total = invoice == null
        ? taxable
        : _number(stringValue(invoice['grand_total']));
    final double tds =
        invoice == null ? 0 : _number(stringValue(invoice['tds_amount']));
    final double tcs =
        invoice == null ? 0 : _number(stringValue(invoice['tcs_amount']));
    final bool? interstate = _interstate;
    // PG-12: figures are in the bill's currency; the rupee equivalent is the
    // server's, never worked out here.
    final String previewCurrency = invoice == null
        ? ''
        : stringValue(invoice['currency_code']).toUpperCase();
    final bool foreign =
        _foreign || (previewCurrency.isNotEmpty && previewCurrency != 'INR');
    final String code = _foreign ? _billCurrency : previewCurrency;
    final String baseTotal =
        invoice == null ? '' : stringValue(invoice['base_grand_total']);
    final String baseOwed =
        invoice == null ? '' : stringValue(invoice['base_amount_owed']);
    return DocumentTotalsBar(
      total: invoice == null || foreign ? null : total,
      note: foreign
          ? (baseTotal.isEmpty
              ? 'Totals are in $code; the rupee equivalent follows once the '
                  'rate is typed.'
              : '₹ equivalent  ${indianAmount(_number(baseTotal), full: true)}'
                  '${baseOwed.isEmpty ? '' : '   owed  '
                      '${indianAmount(_number(baseOwed), full: true)}'}')
          : !_hasSource
          ? switch (_mode) {
              PurchaseBillMode.receipt => 'Choose the receipt being billed.',
              PurchaseBillMode.order => 'Choose the order being billed.',
              PurchaseBillMode.products =>
                'Choose the supplier and a product, and the bill is priced '
                    'with its tax.',
            }
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
        (foreign ? 'Total $code' : 'Total', total),
        // PG-5: what was deducted at approval; PG-6: the TCS the supplier
        // charged on top -- and so what is owed.
        if (invoice != null && (tds > 0 || tcs > 0)) ...[
          if (tds > 0) ('TDS ${stringValue(invoice['tds_section'])}', tds),
          if (tcs > 0) ('TCS charged', tcs),
          ('Net payable', total + tcs - tds),
        ],
      ],
    );
  }

  /// The line's input credit choice. Blank is "From product" -- never a
  /// prefilled Eligible, because the server then takes the product's setting
  /// and a tax rule's, and an explicit Eligible would override both.
  Widget _itcField(
    BuildContext context, {
    required String keyPart,
    required String value,
    required ValueChanged<String> onChanged,
  }) =>
      DocumentField(
        label: 'Input credit',
        width: 258,
        child: DropdownButtonFormField<String>(
          key: ValueKey<String>('purchase-invoice-itc-$keyPart'),
          isExpanded: true,
          initialValue: value,
          decoration: documentBoxDecoration(context),
          items: const [
            DropdownMenuItem<String>(value: '', child: Text('From product')),
            DropdownMenuItem<String>(
                value: 'ELIGIBLE', child: Text('Eligible')),
            DropdownMenuItem<String>(
                value: 'BLOCKED', child: Text('Blocked (s.17(5))')),
            DropdownMenuItem<String>(
                value: 'INELIGIBLE', child: Text('Ineligible')),
          ],
          onChanged: _saving
              ? null
              : (picked) => _setState(() => onChanged(picked ?? '')),
        ),
      );

  /// PG-13: the "Capital goods" tick and, once ticked, the asset class the
  /// line's asset is raised in. The class is required then; both keys are
  /// sent only when ticked.
  List<Widget> _capitalGoodsFields(
    BuildContext context, {
    required String keyPart,
    required bool ticked,
    required String classId,
    required void Function(bool ticked, String classId) onChanged,
    bool fixed = false,
  }) {
    // A receipt line received as capital goods starts ticked, so its class is
    // wanted before anything is typed.
    if (ticked && !_assetClassesAsked) {
      WidgetsBinding.instance
          .addPostFrameCallback((_) => unawaited(_loadAssetClasses()));
    }
    return [
        Row(
          children: [
            Checkbox(
              key: ValueKey<String>('purchase-invoice-capital-$keyPart'),
              visualDensity: VisualDensity.compact,
              value: ticked,
              onChanged: _saving || fixed
                  ? null
                  : (value) {
                      _setState(() => onChanged(value ?? false, classId));
                      if (value == true) unawaited(_loadAssetClasses());
                    },
            ),
            const Expanded(
              child: Text('Capital goods (raises a fixed asset when approved)'),
            ),
          ],
        ),
        if (fixed)
          Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Text(
              'Received as capital goods.',
              key: ValueKey<String>('purchase-invoice-capital-fixed-$keyPart'),
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        if (ticked)
          DocumentField(
            label: 'Asset class (required)',
            width: 258,
            child: DropdownButtonFormField<String>(
              key: ValueKey<String>('purchase-invoice-asset-class-$keyPart'),
              isExpanded: true,
              initialValue:
                  _assetClasses.any((c) => c.id == classId) ? classId : null,
              decoration: documentBoxDecoration(context),
              items: [
                for (final AssetClass c in _assetClasses)
                  DropdownMenuItem<String>(
                    value: c.id,
                    child: Text('${c.code} · ${c.name}',
                        overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: _saving
                  ? null
                  : (picked) => _setState(() => onChanged(true, picked ?? '')),
            ),
          ),
      ];
  }

  /// The batch and expiry boxes for a line whose receipt this bill raises:
  /// nobody else will record them.
  List<Widget> _batchFields(
    BuildContext context, {
    required String keyPart,
    required String batch,
    required String expiry,
    required ValueChanged<String> onBatch,
    required ValueChanged<String> onExpiry,
    Product? product,
  }) =>
      [
        const DocumentSideHeading('Batch'),
        DocumentField(
          label: product?.trackBatch == true
              ? 'Batch number (required)'
              : 'Batch number',
          width: 258,
          child: TextFormField(
            key: ValueKey<String>('purchase-invoice-batch-$keyPart'),
            initialValue: batch,
            readOnly: _saving,
            decoration: documentBoxDecoration(context, hint: 'as on the bill'),
            onChanged: (value) => _setState(() => onBatch(value)),
          ),
        ),
        DocumentField(
          label: product?.trackExpiry == true ? 'Expiry (required)' : 'Expiry',
          width: 258,
          child: _dateBox(
            context,
            key: ValueKey<String>('purchase-invoice-expiry-$keyPart'),
            value: expiry,
            onPicked: (day) => _setState(() => onExpiry(day)),
          ),
        ),
      ];

  Widget _billSidePanel(BuildContext context) {
    if (_lines.isEmpty) {
      return DocumentSidePanel(children: [
        const DocumentSideHeading('Billing'),
        DocumentSideNote(
          _mode == PurchaseBillMode.order
              ? 'Choose the order the bill is for. Each line starts at what '
                  'is still to arrive, at the order price; type a rate only '
                  "where the supplier's differs. Saving receives the goods."
              : 'Choose the receipt the bill is for. Each line starts at what '
                  'is still to be billed, at the receipt price; type a rate '
                  "only where the supplier's differs, and check the total "
                  'against the paper.',
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
        // With the bill discount's share and the line's charges (D-UI-96):
        // the amount less its tax is what the line was taxed on.
        : documentLineTaxable(priced['net_amount'], priced['tax_amount']) ?? 0;
    final double tax =
        priced == null ? 0 : _number(stringValue(priced['tax_amount']));
    final bool typedRate = line.unitPrice.trim().isNotEmpty;
    final bool order = line.billsAnOrder;
    String quantity(double value) =>
        documentQuantity(_PurchaseInvoiceEditorDialogState._trim(value));
    return DocumentSidePanel(children: [
      DocumentSideHeading(
        'Line ${line.lineNumber} · ${product?.name ?? line.description}',
      ),
      if (_boxAndPieces && packOf(line.packSize) != null)
        DocumentSideNote(
          boxPieceSummary(
            packSize: line.packSize,
            quantity: line.invoiceQuantity,
            free: '',
            rate: typedRate ? line.unitPrice : line.receiptUnitPrice,
          ),
          key: const ValueKey('purchase-invoice-side-boxes'),
        ),
      DocumentSidePair(
        order ? 'Ordered' : 'Received',
        _billFigure(line, line.receivedQuantity),
      ),
      DocumentSidePair(
        order ? 'Arrived before' : 'Billed before',
        _billFigure(line, line.alreadyInvoiced),
      ),
      DocumentSidePair('Billing now', quantity(billing)),
      DocumentSidePair(
        left < 0
            ? (order ? 'More than ordered by' : 'More than received by')
            : 'Left to bill',
        quantity(left.abs()),
        bold: true,
        tone: left < 0 ? Theme.of(context).colorScheme.error : null,
      ),
      DocumentSidePair(
        'Rate',
        documentMoney(typedRate ? line.unitPrice : line.receiptUnitPrice),
      ),
      DocumentSideNote(
        typedRate
            ? "as on the supplier's bill"
            : order
                ? 'the order price'
                : 'the receipt price',
      ),
      if (companion != null && companion.lastPrice.isNotEmpty) ...[
        DocumentSidePair(
          'Last bill from them',
          documentMoney(companion.lastPrice),
        ),
        DocumentSideNote(
          documentLastBilled(companion.lastInvoiceNumber,
              companion.lastInvoiceDate, companion.lastDiscountPercent),
        ),
      ],
      if (_figuresOwed && priced == null && billing > 0)
        const DocumentSideNote(
          'Changed since the bill was saved: its tax and amount are worked '
          'out when the bill is saved.',
        )
      else
        ...documentTaxLines(
          taxable: taxable,
          tax: tax,
          interstate: _interstate,
          taxRule: LineTaxRule.fromJson(priced),
        ),
      if (order)
        ..._batchFields(
          context,
          keyPart: '${_order?.id}-$index',
          batch: line.batchNumber,
          expiry: line.expiryDate,
          onBatch: (value) => line.batchNumber = value,
          onExpiry: (value) => line.expiryDate = value,
          product: product,
        ),
      _itcField(
        context,
        keyPart: '${_receipt?.id ?? _order?.id}-$index',
        value: line.itcEligibility,
        onChanged: (picked) => line.itcEligibility = picked,
      ),
      ..._capitalGoodsFields(
        context,
        keyPart: '${_receipt?.id ?? _order?.id}-$index',
        ticked: line.capitalGoods,
        classId: line.assetClassId,
        fixed: line.capitalFromReceipt,
        onChanged: (ticked, classId) {
          line.capitalGoods = ticked || line.capitalFromReceipt;
          line.assetClassId = line.capitalGoods ? classId : '';
        },
      ),
      DocumentField(
        label: 'Line remarks',
        width: 258,
        child: TextFormField(
          key: ValueKey<String>(
            'purchase-invoice-remarks-${_receipt?.id ?? _order?.id}-$index'
            '${_extraReceipts.map((r) => r.id).join()}',
          ),
          initialValue: line.remarks,
          readOnly: _saving,
          decoration: documentBoxDecoration(context),
          onChanged: (value) => line.remarks = value,
        ),
      ),
      const DocumentSideHeading('Stock'),
      DocumentSidePair(
        order ? 'In stock now' : 'Where it was received',
        companion == null ? '—' : documentQuantity(companion.availableQuantity),
      ),
      DocumentSideNote(
        order
            ? 'saving the bill receives these goods into stock'
            : _ownReceipt
                ? 'approving the bill receives these goods into stock'
                : 'the receipt already put it into stock; the bill records '
                    'what is owed for it',
      ),
    ]);
  }

  Widget _directSidePanel(BuildContext context) {
    final Vendor? vendor = _vendor(_vendorId);
    final int index = _current.clamp(0, _directLines.length - 1);
    final PurchaseDirectLine line = _directLines[index];
    final Product? product = _productById(line.productId);
    final Map<String, dynamic>? priced = _pricedDirect(index);
    final DocumentPreviewLine? companion = _companionOf(priced);
    return DocumentSidePanel(children: [
      if (product == null) ...[
        const DocumentSideHeading('The line you are on'),
        const DocumentSideNote(
          'Choose the supplier and a product: its rate, tax, stock and batch '
          'show here.',
        ),
      ] else ...[
        DocumentSideHeading('Line ${index + 1} · ${product.name}'),
        if (_boxAndPieces && _directPack(line) != null)
          DocumentSideNote(
            boxPieceSummary(
              packSize: _directPackSize(line),
              quantity: line.quantity,
              free: line.freeQuantity,
              rate: line.unitPrice.trim().isEmpty
                  ? product.purchasePrice
                  : line.unitPrice,
            ),
            key: const ValueKey('purchase-invoice-side-boxes'),
          ),
        DocumentSidePair(
          'Rate',
          documentMoney(line.unitPrice.trim().isEmpty
              ? product.purchasePrice
              : line.unitPrice),
        ),
        DocumentSideNote(
          line.unitPrice.trim().isEmpty
              ? "the product's purchase price"
              : "as on the supplier's bill",
        ),
        if (companion != null && companion.lastPrice.isNotEmpty) ...[
          DocumentSidePair(
            'Last bill from them',
            documentMoney(companion.lastPrice),
          ),
          DocumentSideNote(
            documentLastBilled(companion.lastInvoiceNumber,
                companion.lastInvoiceDate, companion.lastDiscountPercent),
          ),
        ],
        ...documentTaxLines(
          taxable: priced == null
              ? _typedDirectTaxable(line)
              : documentLineTaxable(
                      priced['net_amount'], priced['tax_amount']) ??
                  0,
          tax: priced == null ? 0 : _number(stringValue(priced['tax_amount'])),
          interstate: _interstate,
          taxRule: LineTaxRule.fromJson(priced),
        ),
        ..._batchFields(
          context,
          keyPart: 'direct-$index-${line.productId}',
          batch: line.batchNumber,
          expiry: line.expiryDate,
          onBatch: (value) => line.batchNumber = value,
          onExpiry: (value) => line.expiryDate = value,
          product: product,
        ),
        _itcField(
          context,
          keyPart: 'direct-$index-${line.productId}',
          value: line.itcEligibility,
          onChanged: (picked) => line.itcEligibility = picked,
        ),
        ..._capitalGoodsFields(
          context,
          keyPart: 'direct-$index',
          ticked: line.capitalGoods,
          classId: line.assetClassId,
          onChanged: (ticked, classId) {
            line.capitalGoods = ticked;
            line.assetClassId = ticked ? classId : '';
          },
        ),
        DocumentField(
          label: 'Line remarks',
          width: 258,
          child: TextFormField(
            key: ValueKey<String>('purchase-invoice-direct-remarks-$index'),
            initialValue: line.remarks,
            readOnly: _saving,
            decoration: documentBoxDecoration(context),
            onChanged: (value) => line.remarks = value,
          ),
        ),
        const DocumentSideHeading('Stock'),
        DocumentSidePair(
          'In stock now',
          companion == null
              ? '—'
              : documentQuantity(companion.availableQuantity),
        ),
      ],
      const DocumentSideHeading('Supplier'),
      DocumentSidePair(
        'Billed by',
        vendor?.displayName ??
            (_held('vendor_name').isEmpty ? '—' : _held('vendor_name')),
      ),
      const DocumentSideNote(
        'This firm buys directly: saving raises the order and the receipt '
        'behind this bill, so the goods come into the default warehouse and '
        'their cost is recorded with them.',
      ),
    ]);
  }
}
