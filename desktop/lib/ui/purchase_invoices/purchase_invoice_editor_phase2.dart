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

  /// An order's lines: what was ordered, what has arrived, what is still due.
  static const List<DocumentColumn> _orderColumns = [
    DocumentColumn('#', 28),
    DocumentColumn('Product', 0),
    DocumentColumn('HSN', 66),
    DocumentColumn('Ordered', 72, numeric: true),
    DocumentColumn('Arrived', 64, numeric: true),
    DocumentColumn('Due', 60, numeric: true),
    DocumentColumn('Billing', 76, numeric: true),
    DocumentColumn('Rate', 90, numeric: true),
    DocumentColumn('Taxable', 96, numeric: true),
    DocumentColumn('GST', 48, numeric: true),
    DocumentColumn('Amount', 104, numeric: true),
  ];

  static const List<DocumentColumn> _directColumns = [
    DocumentColumn('#', 28),
    DocumentColumn('Product (code, name or barcode)', 0),
    DocumentColumn('HSN', 66),
    DocumentColumn('Qty', 66, numeric: true),
    DocumentColumn('Free', 56, numeric: true),
    DocumentColumn('Unit', 50),
    DocumentColumn('Rate', 84, numeric: true),
    DocumentColumn('Disc %', 60, numeric: true),
    DocumentColumn('Taxable', 96, numeric: true),
    DocumentColumn('GST', 48, numeric: true),
    DocumentColumn('Amount', 104, numeric: true),
    DocumentColumn('', 28),
  ];

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
    final DocumentStep<Json>? approve = stepAfterSave(widget.steps);
    final Json? saved = _saved;
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.escape): () {
          if (!_saving) Navigator.pop(context, saved);
        },
        const SingleActivator(LogicalKeyboardKey.keyS, control: true): () {
          if (!_saving && saved == null) unawaited(_save());
        },
        const SingleActivator(LogicalKeyboardKey.enter, control: true): () {
          if (_direct && !_saving) _addDirectLine();
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
                  if (_order != null) 'against ${_order!.poNumber}',
                  'Draft',
                ],
                hint: _direct
                    ? 'Ctrl+Enter new line  ·  Ctrl+S save'
                    : 'Enter next field  ·  Ctrl+S save',
                actions: [
                  TextButton(
                    onPressed:
                        _saving ? null : () => Navigator.pop(context, saved),
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
                                documentId: saved == null
                                    ? null
                                    : stringValue(saved['id']),
                                subtitle: stringValue(saved?['invoice_number']),
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
                      saveLabel: 'Save bill',
                      onSave: _saving ? null : () => unawaited(_save()),
                      stepKey: const ValueKey('purchase-invoice-save-approve'),
                      stepLabel: approve?.afterSave,
                      onStep: _saving || approve == null
                          ? null
                          : () => unawaited(_saveAndStep(approve)),
                    ),
                ],
              ),
              for (final String message in [
                if (_error != null) _error!,
                if (duplicate.isNotEmpty &&
                    _supplierInvoiceNumber.trim().isNotEmpty)
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
                              child: _direct
                                  ? _directLinesTable(context)
                                  : _billLines(context),
                            ),
                            _billTotals(),
                          ],
                        ),
                      ),
                      if (constraints.maxWidth >= DocumentSidePanel.showFrom)
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

  Product? _product(String id) => _productById(id);

  Vendor? _vendor(String? id) {
    for (final Vendor item in widget.vendors) {
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
          child: DropdownMenu<String>(
            key: const ValueKey('purchase-invoice-vendor'),
            initialSelection: _vendorId,
            width: 400,
            enabled: !_saving,
            enableFilter: true,
            requestFocusOnTap: true,
            menuHeight: 320,
            inputDecorationTheme: _pickerTheme(scheme),
            dropdownMenuEntries: [
              for (final Vendor item in widget.vendors)
                DropdownMenuEntry<String>(
                  value: item.id,
                  label: '${item.displayName} — ${item.code}',
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
      // PG-12: the currency the supplier billed in. Untouched, it is the
      // supplier's; blank or INR is rupees.
      DocumentField(
        label: 'Currency',
        width: 110,
        child: TextFormField(
          key: ValueKey<String>(
            'purchase-invoice-currency-${_billSupplierId ?? ''}-'
            '$_supplierCurrency',
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
          child: TextFormField(
            key: ValueKey<String>(
                'purchase-invoice-exchange-rate-$_billCurrency'),
            initialValue: _exchangeRate,
            readOnly: _saving,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: documentBoxDecoration(context, hint: 'e.g. 84.10'),
            onChanged: (value) {
              _setState(() => _exchangeRate = value);
              _schedulePreview();
            },
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
            _setState(() => _tcsRate = value);
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
            _setState(() => _tcsAmount = value);
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
  }) =>
      TextFormField(
        key: ValueKey<String>(
          'purchase-invoice-$name-${_receipt?.id ?? _order?.id ?? 'direct'}'
          '-$index$epoch${_extraReceipts.map((r) => r.id).join()}',
        ),
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

  List<Widget> _figures(
    BuildContext context,
    Map<String, dynamic>? priced,
    double typed, {
    bool billing = true,
  }) {
    final TextStyle? text =
        Theme.of(context).textTheme.bodyMedium?.copyWith(fontSize: 13);
    final double taxable = priced == null
        ? typed
        : _number(stringValue(priced['gross_amount'])) -
            _number(stringValue(priced['discount_amount']));
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
          // Blank takes the receipt's (or the order's) price; say which.
          hint: documentMoney(line.receiptUnitPrice),
          onChanged: (value) => line.unitPrice = value,
        ),
        ..._figures(context, priced, _typedTaxable(line), billing: billing > 0),
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
    final Map<String, dynamic>? priced =
        _pricedByNumber(_sentNumber(index), line.productId);
    final DocumentPreviewLine? companion = _companionOf(priced);
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
    final bool? interstate = _preview?.interstate;
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
        : _number(stringValue(priced['gross_amount'])) -
            _number(stringValue(priced['discount_amount']));
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
      DocumentSidePair(
        order ? 'Ordered' : 'Received',
        documentQuantity(line.receivedQuantity),
      ),
      DocumentSidePair(
        order ? 'Arrived before' : 'Billed before',
        documentQuantity(line.alreadyInvoiced),
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
      ...documentTaxLines(
        taxable: taxable,
        tax: tax,
        interstate: _preview?.interstate,
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
            : 'the receipt already put it into stock; the bill records what '
                'is owed for it',
      ),
    ]);
  }

  Widget _directSidePanel(BuildContext context) {
    final Vendor? vendor = _vendor(_vendorId);
    final int index = _current.clamp(0, _directLines.length - 1);
    final PurchaseDirectLine line = _directLines[index];
    final Product? product = _productById(line.productId);
    final Map<String, dynamic>? priced =
        _pricedByNumber(_sentNumber(index), line.productId);
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
              : _number(stringValue(priced['gross_amount'])) -
                  _number(stringValue(priced['discount_amount'])),
          tax: priced == null ? 0 : _number(stringValue(priced['tax_amount'])),
          interstate: _preview?.interstate,
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
      DocumentSidePair('Billed by', vendor?.displayName ?? '—'),
      const DocumentSideNote(
        'This firm buys directly: saving raises the order and the receipt '
        'behind this bill, so the goods come into the default warehouse and '
        'their cost is recorded with them.',
      ),
    ]);
  }
}
