part of 'sales_invoice_editor_dialog.dart';

/// The sales invoice screen in the phase 2 app: the quotation's approved
/// one-screen layout (wireframe view 7) for a bill -- priced as it is typed
/// by `POST /sales-invoices/preview`. Both of the dialog's ways of billing
/// keep their rules: billing a dispatched note or an order (its lines, its
/// prices, only the quantity typed) and, for a firm that bills directly,
/// naming products. Serial numbers are picked in the side panel for the
/// line being typed, rather than under every row.
extension _Phase2SalesInvoiceEditor on _SalesInvoiceEditorDialogState {
  List<DocumentColumn> get _documentColumns => [
    const DocumentColumn('#', 28),
    const DocumentColumn('Item', 0),
    const DocumentColumn('Left to bill', 84, numeric: true),
    const DocumentColumn('Bill qty', 78, numeric: true),
    _rateColumn,
    const DocumentColumn('Disc %', 60, numeric: true),
    const DocumentColumn('Taxable', 96, numeric: true),
    const DocumentColumn('GST', 48, numeric: true),
    const DocumentColumn('Amount', 104, numeric: true),
  ];

  List<DocumentColumn> get _directColumns => [
    const DocumentColumn('#', 28),
    const DocumentColumn('Product (code, name or barcode)', 0),
    const DocumentColumn('HSN', 66),
    const DocumentColumn('Qty', 66, numeric: true),
    const DocumentColumn('Unit', 50),
    _rateColumn,
    const DocumentColumn('Disc %', 60, numeric: true),
    const DocumentColumn('Taxable', 96, numeric: true),
    const DocumentColumn('GST', 48, numeric: true),
    const DocumentColumn('Amount', 104, numeric: true),
    const DocumentColumn('', 28),
  ];

  /// The rate column says which rate it holds (backlog 64 row 4).
  DocumentColumn get _rateColumn => _rateIncludesTax
      ? const DocumentColumn('Rate incl. GST', 104, numeric: true)
      : const DocumentColumn('Rate', 84, numeric: true);

  /// Turn the bill's "Rate includes GST" switch. A rate still showing the
  /// product's own price was never typed, and that price is before tax, so
  /// it is cleared going on (blank takes it, before tax) and put back
  /// coming off.
  void _setRateIncludesTax(bool value) {
    _setState(() {
      _rateIncludesTax = value;
      for (final _DirectLine line in _directLines) {
        final Product? product = _product(line.productId);
        if (product == null) continue;
        final String price = line.price.text.trim();
        if (value && price == product.sellingPrice) {
          line.price.clear();
        } else if (!value && price.isEmpty) {
          final double master = double.tryParse(product.sellingPrice) ?? 0;
          if (master > 0) line.price.text = product.sellingPrice;
        }
      }
    });
    _schedulePreview();
  }

  /// The bill's switch: on a new bill of products, the switch itself; on a
  /// draft, what its rates were typed as, which an edit cannot change.
  Widget? _rateIncludesTaxField(BuildContext context) {
    if (_direct) {
      return DocumentField(
        label: 'Rate includes GST',
        width: 150,
        child: Row(
          children: [
            Switch(
              key: const ValueKey('sales-invoice-rate-includes-tax'),
              value: _rateIncludesTax,
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              onChanged: _saving ? null : _setRateIncludesTax,
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
    }
    if (_editing && _rateIncludesTax) {
      return DocumentField(
        label: 'Rate includes GST',
        auto: true,
        width: 150,
        child: InputDecorator(
          decoration: documentBoxDecoration(context),
          child: const Text('Yes, as typed'),
        ),
      );
    }
    return null;
  }

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
    // Save & approve (D-BUY-22), beside the save.
    final DocumentStep<Json>? approve = stepAfterSave(widget.steps);
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.keyS, control: true): () {
          if (!_saving) unawaited(_save());
        },
        const SingleActivator(LogicalKeyboardKey.keyP, control: true): () {
          if (!_saving) unawaited(_save(print: true));
        },
        const SingleActivator(LogicalKeyboardKey.f9): () {
          if (!_saving) unawaited(_saveApprovePrint());
        },
        const SingleActivator(LogicalKeyboardKey.f8): () {
          if (_counterMode && !_saving) unawaited(_holdBill());
        },
        const SingleActivator(LogicalKeyboardKey.enter, control: true): () {
          if (!_direct && !_addsProducts) return;
          _setState(() {
            _directLines.add(_DirectLine());
            if (_addsProducts) _addedFocus = true;
          });
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
                number: _editing ? number : '',
                chips: [
                  if (number.isNotEmpty && !_editing) '$number (new)',
                  'Draft',
                ],
                hint: _direct || _addsProducts
                    ? 'F9 save & print  ·  F8 hold  ·  Ctrl+Enter new line  ·  Ctrl+S save'
                    : 'F9 save & print  ·  Enter next field  ·  Ctrl+S save',
                actions: [
                  TextButton(
                    onPressed:
                        _saving ? null : () => Navigator.of(context).pop(false),
                    child: const Text('Cancel'),
                  ),
                  // A saved draft's Cancel and Close (D-BUY-22); Approve is
                  // the save button beside it, so the edits go with it.
                  DocumentStepStrip<Json>(
                    record: _existing,
                    steps: [
                      for (final DocumentStep<Json> step in widget.steps)
                        if (step != approve) step,
                    ],
                    enabled: !_saving,
                    onRefused: (message) =>
                        _setState(() => _error = message),
                  ),
                  ..._holdActions(),
                  // A draft prints marked "not a tax invoice" until it is
                  // approved; the list prints the final copy.
                  if (!_direct)
                    OutlinedButton(
                      key: const ValueKey('sales-invoice-save-print'),
                      onPressed:
                          _saving ? null : () => unawaited(_save(print: true)),
                      child: const Text('Save & print'),
                    ),
                  FilledButton.tonal(
                    key: const ValueKey('counter-save-print'),
                    onPressed:
                        _saving ? null : () => unawaited(_saveApprovePrint()),
                    child: const Text('Save & print (F9)'),
                  ),
                  ...saveButtons(
                    saveKey: const ValueKey('sales-invoice-save'),
                    saveLabel: _editing ? 'Save invoice' : 'Save draft',
                    onSave: _saving ? null : () => unawaited(_save()),
                    stepKey: const ValueKey('sales-invoice-save-approve'),
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
                            if (_counterMode) _shiftStrip(),
                            if (_direct || _addsProducts) _scanBar(context),
                            if (_addsProducts)
                              ..._savedAndAddedTables(context)
                            else
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
                                          _setState(() => _directLines
                                              .add(_DirectLine()));
                                          _current = _directLines.length - 1;
                                        },
                                      )
                                    : DocumentLineTable(
                                        columns: _documentColumns,
                                        rows: [
                                          for (int i = 0;
                                              i < _lineEntries.length;
                                              i++)
                                            _documentRow(context, i),
                                        ],
                                      ),
                              ),
                            AdditionalDetailsSection(
                              controller: _customFields,
                              noun: 'sales invoices',
                              maxHeight: 132,
                              padding:
                                  const EdgeInsets.fromLTRB(12, 8, 12, 0),
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

  /// Whether the bill is made out to the firm's cash customer: a walk-in.
  bool get _isWalkIn {
    if (!_direct) return _editedWalkIn;
    final String? id = _customerId;
    if (id == null) return false;
    return id == _walkInId || (_customer?.isCashSale ?? false);
  }

  /// The buyer, sent for a walk-in bill only: the server refuses the keys on
  /// a bill to anyone else, and an emptied box says null so it clears.
  Map<String, dynamic> _buyerFields() {
    if (!_phase2 || !_isWalkIn) return const <String, dynamic>{};
    final String name = _buyerName.text.trim();
    final String phone = _buyerPhone.text.trim();
    return <String, dynamic>{
      'buyer_name': name.isEmpty ? null : name,
      'buyer_phone': phone.isEmpty ? null : phone,
    };
  }

  /// The other charges, sent on every phase 2 save and preview: a row with a
  /// name is a charge, and an empty list clears what a draft held.
  Map<String, dynamic> _chargeFields() {
    if (!_phase2) return const <String, dynamic>{};
    return <String, dynamic>{
      'charges': <Map<String, dynamic>>[
        for (final _ChargeRow row in _charges)
          if (row.name.text.trim().isNotEmpty)
            <String, dynamic>{
              'name': row.name.text.trim(),
              'amount':
                  row.amount.text.trim().isEmpty ? '0' : row.amount.text.trim(),
              'tax_profile_id': row.taxProfileId,
              if (row.sac.text.trim().isNotEmpty)
                'hsn_sac': row.sac.text.trim(),
            },
      ],
    };
  }

  /// A walk-in bill is paid in full: offer the total until a figure is typed.
  void _defaultWalkInReceived() {
    if (!_isWalkIn || _receivedTouched || _splitTender) return;
    if (_editing && '${_existing?['status'] ?? 'DRAFT'}' != 'DRAFT') return;
    if (_billTotal <= 0) return;
    // What is asked for at the counter is the bill in whole paise
    // (`amount_payable`): a total of 97.1376 is paid with 97.14, and the
    // unrounded figure cannot be typed or tendered (D-SELL-83).
    final String payable = stringValue(_preview?.invoice['amount_payable']);
    _receivedNow.text = payable.isNotEmpty
        ? payable
        : stringValue(_preview?.invoice['grand_total']);
  }

  /// Choose the cash customer: ask the server for it (made on the first
  /// ask), make sure the list holds it, and select it like any customer.
  Future<void> _chooseWalkIn() async {
    _setState(() => _walkInBusy = true);
    try {
      final Json made = await widget.api.walkInCustomer();
      final String id = stringValue(made['id']);
      if (!mounted) return;
      _setState(() {
        _walkInBusy = false;
        _walkInId = id;
        if (!_customers.any((item) => item.id == id)) {
          _customers = <Customer>[
            Customer.fromJson(<String, dynamic>{
              'id': id,
              'code': made['code'],
              'name': made['name'],
              'display_name': made['name'],
              'is_cash_sale': true,
            }),
            ..._customers,
          ];
        }
        _customerId = id;
        _shipToId = null;
        _error = null;
      });
      _schedulePreview();
    } on ApiException catch (error) {
      if (!mounted) return;
      _setState(() {
        _walkInBusy = false;
        _error = error.message;
      });
    }
  }

  /// The buyer's name and phone, shown for a walk-in bill only.
  Widget? _buyerField(BuildContext context) {
    if (!_isWalkIn) return null;
    return DocumentField(
      label: 'Buyer (optional)',
      width: 420,
      child: Row(
        children: [
          Expanded(
            child: TextFormField(
              key: const ValueKey('sales-invoice-buyer-name'),
              controller: _buyerName,
              maxLength: 200,
              enabled: !_saving,
              decoration: documentBoxDecoration(context).copyWith(
                hintText: 'Buyer name',
                counterText: '',
              ),
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 140,
            child: TextFormField(
              key: const ValueKey('sales-invoice-buyer-phone'),
              controller: _buyerPhone,
              maxLength: 30,
              enabled: !_saving,
              keyboardType: TextInputType.phone,
              decoration: documentBoxDecoration(context).copyWith(
                hintText: 'Buyer phone',
                counterText: '',
              ),
            ),
          ),
        ],
      ),
    );
  }

  Customer? get _customer {
    final String? id = _direct ? _customerId : _tickCustomerId;
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

  /// Every line of every note on the bill, with the note it belongs to.
  List<(BillableDocument, BillableLine)> get _lineEntries => [
        for (final BillableDocument document in _documents)
          for (final BillableLine line in document.lines) (document, line),
      ];

  /// The customers offered: those with notes waiting, and a draft's own.
  List<BillableDocument> get _billableCustomersWithOwn {
    final List<BillableDocument> rows = _billableCustomers;
    final BillableDocument? own = _document;
    if (own != null && !rows.any((row) => row.customerId == own.customerId)) {
      return [own, ...rows];
    }
    return rows;
  }

  /// The notes on the bill, and the tick list of the customer's notes
  /// (SEL-1, backlog 58 items 2 and 4). A draft being edited keeps its notes:
  /// changing what a bill covers is raising another bill.
  Widget? _notesField(BuildContext context) {
    if (_direct || _tickCustomerId == null) return null;
    final ThemeData theme = Theme.of(context);
    final int waiting = _customerNotes.length;
    return DocumentField(
      label: 'Delivery notes on this bill',
      width: 420,
      child: Wrap(
        spacing: 6,
        runSpacing: 4,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          for (final BillableDocument item in _documents)
            Chip(
              key: ValueKey<String>(
                  'sales-invoice-note-${item.sourceDocumentId}'),
              label: Text(item.sourceDocumentNumber),
              visualDensity: VisualDensity.compact,
            ),
          if (_documents.isEmpty)
            Text(
              'None ticked yet',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: theme.colorScheme.error),
            ),
          if (!_editing)
            TextButton.icon(
              key: const ValueKey('sales-invoice-choose-notes'),
              onPressed: _saving ? null : () => unawaited(_tickNotes()),
              icon: const Icon(Icons.checklist, size: 16),
              label: Text(waiting == 1
                  ? 'Choose notes (1 waiting)'
                  : 'Choose notes ($waiting waiting)'),
            ),
        ],
      ),
    );
  }

  /// Offer the customer's notes as a tick list and bill those ticked.
  Future<void> _tickNotes() async {
    final List<BillableDocument> notes = _customerNotes;
    if (notes.isEmpty) return;
    BillableDocument byId(String id) =>
        notes.firstWhere((item) => item.sourceDocumentId == id);
    final List<String>? picked = await showSourceTickDialog(
      context,
      title: 'Delivery notes to bill — ${notes.first.customerName}',
      keyPrefix: 'sales-invoice',
      rows: [
        for (final BillableDocument item in notes)
          SourceTickRow(
            id: item.sourceDocumentId,
            number: item.sourceDocumentNumber,
            date: _shownDate(item.documentDate),
            order: item.salesOrderNumber,
            amount: documentMoney(item.valueLeft.toStringAsFixed(2)),
          ),
      ],
      initial: {
        for (final BillableDocument item in _documents) item.sourceDocumentId,
      },
      clashFor: (id, ticked) => _noteClash(
        byId(id),
        [for (final String other in ticked) byId(other)],
      ),
      numberLabel: 'Delivery note',
      amountLabel: 'Left to bill (before tax)',
    );
    if (picked == null || !mounted) return;
    _setState(() => _setDocuments([for (final String id in picked) byId(id)]));
    _schedulePreview();
  }

  /// Choose whose notes are billed: what the bill held goes, and a customer
  /// with one note waiting has it ticked; with more, the list opens.
  Future<void> _chooseBillCustomer(String? value) async {
    if (value == null || value == _tickCustomerId) return;
    _setState(() {
      _setDocuments(const []);
      _billCustomerId = value;
      _preview = null;
    });
    final List<BillableDocument> notes = _customerNotes;
    if (notes.length == 1) {
      _setState(() => _setDocuments(notes));
      _schedulePreview();
    } else if (notes.length > 1) {
      await _tickNotes();
    }
  }

  String _shownDate(String iso) {
    final DateTime? day = DateTime.tryParse(iso);
    return day == null ? iso : documentDate(day);
  }

  Widget _invoiceHeader(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final Customer? customer = _customer;
    final String place =
        customer == null ? '' : documentCustomerPlace(customer);
    final Map<String, dynamic>? invoice = _preview?.invoice;
    final String placeOfSupply = stringValue(invoice?['place_of_supply']);
    final Widget? notes = _notesField(context);
    final Widget? inclusive = _rateIncludesTaxField(context);
    final Widget? buyer = _buyerField(context);
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
              _setState(() {
                _customerId = value;
                _shipToId = null;
              });
              _schedulePreview();
            },
          ),
        )
      else
        DocumentField(
          label: 'Customer (only those with notes to bill)',
          width: 420,
          below: customer == null ? null : DocumentCustomerLine(customer),
          child: DropdownMenu<String>(
            key: const ValueKey('sales-invoice-bill-customer'),
            initialSelection: _tickCustomerId,
            width: 420,
            enabled: !_editing && !_saving,
            enableFilter: true,
            requestFocusOnTap: true,
            menuHeight: 320,
            hintText: 'Choose the customer first',
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
              for (final BillableDocument item in _billableCustomersWithOwn)
                DropdownMenuEntry<String>(
                  value: item.customerId,
                  label: item.customerName,
                ),
            ],
            onSelected: (value) => unawaited(_chooseBillCustomer(value)),
          ),
        ),
      if (_direct)
        DocumentField(
          label: 'Counter sale',
          width: 110,
          child: OutlinedButton(
            key: const ValueKey('sales-invoice-walk-in'),
            onPressed: _saving || _walkInBusy ? null : _chooseWalkIn,
            child: const Text('Walk-in'),
          ),
        ),
      if (buyer != null) buyer,
      if (notes != null) notes,
      // "(as delivered)" is null: the server takes the address from the notes
      // billed. Shown when reopening a draft too, with the saved one chosen.
      if (_shipToAddresses.isNotEmpty)
        ShipToField(
          key: const ValueKey('sales-invoice-ship-to'),
          scope: (_direct ? _customerId : _document?.customerId) ?? '',
          addresses: _shipToAddresses,
          value: _shipToId,
          enabled: !_saving,
          blankLabel: _direct ? "(customer's default)" : '(as delivered)',
          onChanged: (value) {
            _setState(() => _shipToId = value);
            _schedulePreview();
          },
        ),
      if (inclusive != null) inclusive,
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
      // New bills of products only: a coupon is applied when the bill is
      // first priced, and the server refuses one on a bill of documents.
      if (_direct)
        DocumentField(
          label: 'Coupon',
          width: 130,
          child: TextFormField(
            key: const ValueKey('sales-invoice-coupon'),
            controller: _coupon,
            decoration: documentBoxDecoration(context),
            textCapitalization: TextCapitalization.characters,
            onChanged: (_) => _schedulePreview(),
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
    // On a saved counter bill the saved lines are sent first.
    int number = _addsProducts ? _billedLineCount() : 0;
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
        autovalidateMode: AutovalidateMode.onUserInteraction,
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
    final (BillableDocument document, BillableLine line) = _lineEntries[index];
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    // A saved counter bill that gained products is priced with every line
    // as a product, so its saved lines are found by their place.
    final Map<String, dynamic>? priced =
        _pricedBySource(line.sourceDocumentLineId) ??
            (_addsProducts && _hasAddedProducts
                ? _pricedByNumber(
                    _documentPlace(line.sourceDocumentLineId) ?? 0,
                    line.productId,
                  )
                : null);
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
      current: index == _current && !_addedFocus,
      onTap: () => _setState(() {
        _current = index;
        _addedFocus = false;
      }),
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
              '${_extraDocuments.isEmpty ? '' : '${document.sourceDocumentNumber}  ·  '}'
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
        // it bills rather than repricing it. A draft typed with GST in its
        // rates shows the rate as typed (backlog 64 row 4).
        Text(
          documentMoney(
              _enteredRates[line.sourceDocumentLineId] ?? line.unitPrice),
          key: ValueKey<String>('sales-invoice-rate-$index'),
          style: text,
        ),
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

  /// SEL-12: the field a barcode scanner types into, above the lines. A
  /// scanner is a keyboard that ends each code with Enter.
  Widget _scanBar(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 2, 12, 2),
      child: Row(
        children: [
          SizedBox(
            width: 300,
            height: 32,
            child: TextField(
              key: const ValueKey('counter-scan-field'),
              controller: _scan,
              focusNode: _scanFocus,
              autofocus: true,
              style: theme.textTheme.bodyMedium?.copyWith(fontSize: 13),
              decoration: const InputDecoration(
                isDense: true,
                contentPadding: EdgeInsets.symmetric(vertical: 6),
                prefixIcon: Icon(Icons.qr_code_scanner, size: 18),
                hintText: 'Scan a barcode',
                border: OutlineInputBorder(),
              ),
              onSubmitted: _scanned,
            ),
          ),
          const SizedBox(width: 12),
          if (_scanMessage != null)
            Expanded(
              child: Text(
                _scanMessage!,
                key: const ValueKey('counter-scan-message'),
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.error,
                ),
              ),
            ),
        ],
      ),
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
      current: index == _current && (!_addsProducts || _addedFocus),
      onTap: () => _setState(() {
        _current = index;
        if (_addsProducts) _addedFocus = true;
      }),
      cells: [
        Text('${index + 1}', style: text),
        Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            KeyedSubtree(
              key: ValueKey<String>('scan-$index-${line.refresh}'),
              child: DropdownMenu<String>(
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
              onSelected: (value) => _pickProduct(index, value),
            ),
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
        _cellBox(
          context,
          line.price,
          hint: _rateIncludesTax ? 'list rate' : null,
        ),
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
          onPressed: _directLines.length == 1 && !_addsProducts
              ? null
              : () {
                  _setState(() {
                    _directLines.removeAt(index);
                    if (_current >= _directLines.length) {
                      _current =
                          _directLines.isEmpty ? 0 : _directLines.length - 1;
                    }
                  });
                  _schedulePreview();
                },
          icon: const Icon(Icons.close),
        ),
      ],
    );
  }

  /// A saved counter bill: its lines, and below them the products added to
  /// it (D-SELL-59). The saved lines are changed by their quantity -- a
  /// zero takes one off the bill -- and the added ones by their own row.
  List<Widget> _savedAndAddedTables(BuildContext context) => [
        Expanded(
          flex: 3,
          child: DocumentLineTable(
            columns: _documentColumns,
            rows: [
              for (int i = 0; i < _lineEntries.length; i++)
                _documentRow(context, i),
            ],
          ),
        ),
        Expanded(
          flex: 2,
          child: DocumentLineTable(
            key: const ValueKey('sales-invoice-added-products'),
            columns: _directColumns,
            rows: [
              for (int i = 0; i < _directLines.length; i++)
                _directRow(context, i),
            ],
            addLabel: '${_billedLineCount() + _directLines.length + 1}'
                '     + add a product (Ctrl+Enter)',
            onAdd: () {
              _setState(() {
                _directLines.add(_DirectLine());
                _addedFocus = true;
              });
              _current = _directLines.length - 1;
            },
          ),
        ),
      ];

  Widget _invoiceTerms(BuildContext context) => DocumentTerms(children: [
        DocumentField(
          label: 'Discount on the whole bill %',
          width: 190,
          child: TextFormField(
            controller: _billDiscount,
            keyboardType: TextInputType.number,
            decoration: documentBoxDecoration(context),
            autovalidateMode: AutovalidateMode.onUserInteraction,
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
        _chargesSection(context),
        _receivedNowSection(context),
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

  static const int _maxCharges = 10;

  /// Other charges (packing, installation), each taxed by the server at the
  /// profile chosen on its row. Read-only once the bill is not a draft.
  Widget _chargesSection(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool locked =
        _editing && '${_existing?['status'] ?? 'DRAFT'}' != 'DRAFT';
    if (locked && _charges.isEmpty) return const SizedBox.shrink();
    // The server prices the rows that have a name, in order.
    final List<dynamic> priced = _preview?.invoice['charges'] is List
        ? _preview!.invoice['charges'] as List
        : (_existing?['charges'] is List
            ? _existing!['charges'] as List
            : const []);
    final List<_ChargeRow> named = <_ChargeRow>[
      for (final _ChargeRow row in _charges)
        if (row.name.text.trim().isNotEmpty) row,
    ];
    String taxOf(_ChargeRow row) {
      final int at = named.indexOf(row);
      if (at < 0 || at >= priced.length || priced[at] is! Map) return '';
      final double tax =
          double.tryParse(stringValue((priced[at] as Map)['tax_amount'])) ?? 0;
      return tax == 0 ? '' : 'GST ${indianAmount(tax, full: true)}';
    }

    return DocumentField(
      label: 'Other charges',
      width: 560,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (int i = 0; i < _charges.length; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Wrap(
                spacing: 8,
                runSpacing: 6,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  SizedBox(
                    width: 150,
                    child: TextFormField(
                      key: ValueKey<String>('sales-invoice-charge-name-$i'),
                      controller: _charges[i].name,
                      enabled: !locked,
                      maxLength: 120,
                      decoration: documentBoxDecoration(context).copyWith(
                        hintText: 'Name',
                        counterText: '',
                      ),
                      onChanged: (_) {
                        _setState(() {});
                        _schedulePreview();
                      },
                    ),
                  ),
                  SizedBox(
                    width: 90,
                    child: TextFormField(
                      key: ValueKey<String>('sales-invoice-charge-amount-$i'),
                      controller: _charges[i].amount,
                      enabled: !locked,
                      keyboardType: TextInputType.number,
                      decoration: documentBoxDecoration(context)
                          .copyWith(hintText: 'Amount'),
                      onChanged: (_) {
                        _setState(() {});
                        _schedulePreview();
                      },
                    ),
                  ),
                  SizedBox(
                    width: 140,
                    child: DropdownButtonFormField<String?>(
                      key: ValueKey<String>('sales-invoice-charge-tax-$i'),
                      initialValue: _taxProfiles
                              .any((p) => p.id == _charges[i].taxProfileId)
                          ? _charges[i].taxProfileId
                          : null,
                      isExpanded: true,
                      decoration: documentBoxDecoration(context),
                      items: [
                        const DropdownMenuItem<String?>(
                          value: null,
                          child: Text('(no tax)'),
                        ),
                        for (final TaxProfileRecord profile in _taxProfiles)
                          DropdownMenuItem<String?>(
                            value: profile.id,
                            child: Text(
                              profile.label.isEmpty
                                  ? profile.name
                                  : profile.label,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                      ],
                      onChanged: locked
                          ? null
                          : (String? value) {
                              _setState(() => _charges[i].taxProfileId = value);
                              _schedulePreview();
                            },
                    ),
                  ),
                  SizedBox(
                    width: 80,
                    child: TextFormField(
                      key: ValueKey<String>('sales-invoice-charge-sac-$i'),
                      controller: _charges[i].sac,
                      enabled: !locked,
                      maxLength: 20,
                      decoration: documentBoxDecoration(context).copyWith(
                        hintText: 'SAC',
                        counterText: '',
                      ),
                      onChanged: (_) => _schedulePreview(),
                    ),
                  ),
                  if (taxOf(_charges[i]).isNotEmpty)
                    Text(
                      taxOf(_charges[i]),
                      style: theme.textTheme.bodySmall?.copyWith(
                        fontSize: 11,
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  if (!locked)
                    IconButton(
                      key: ValueKey<String>('sales-invoice-charge-remove-$i'),
                      tooltip: 'Remove charge',
                      iconSize: 16,
                      visualDensity: VisualDensity.compact,
                      onPressed: () {
                        _setState(() => _charges.removeAt(i).dispose());
                        _schedulePreview();
                      },
                      icon: const Icon(Icons.close),
                    ),
                ],
              ),
            ),
          if (!locked)
            TextButton.icon(
              key: const ValueKey('sales-invoice-add-charge'),
              onPressed: _charges.length >= _maxCharges
                  ? null
                  : () => _setState(() => _charges.add(_ChargeRow())),
              icon: const Icon(Icons.add, size: 16),
              label: const Text('Add charge'),
            ),
        ],
      ),
    );
  }

  /// What the bill asks for as last priced, in whole paise where the server
  /// says so, for the received-now checks: that is the figure the server
  /// holds the money against (D-SELL-83).
  double get _billTotal =>
      double.tryParse(stringValue(_preview?.invoice['amount_payable'])) ??
      double.tryParse(stringValue(_preview?.invoice['grand_total'])) ??
      0;

  /// Money taken at the counter. Editable while the bill is a draft; once it
  /// is approved the server has recorded the receipt and this only reports it.
  Widget _receivedNowSection(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String status = '${_existing?['status'] ?? 'DRAFT'}';
    if (_editing && status != 'DRAFT') {
      final double got =
          double.tryParse('${_existing?['received_now_amount'] ?? 0}') ?? 0;
      if (got <= 0) return const SizedBox.shrink();
      final double total =
          double.tryParse('${_existing?['grand_total'] ?? 0}') ?? 0;
      final String how = '${_existing?['received_now_method']}' == 'BANK'
          ? 'Bank'
          : 'Cash';
      return SizedBox(
        width: 420,
        child: Padding(
          padding: const EdgeInsets.only(top: 18),
          child: DocumentSideNote(
            [
              'Received ${indianAmount(got, full: true)} ($how)',
              if (got < total)
                'Balance ${indianAmount(total - got, full: true)} on account',
            ].join(' · '),
          ),
        ),
      );
    }
    final double typed = double.tryParse(_receivedNow.text.trim()) ?? 0;
    final bool over = typed > 0 && _billTotal > 0 && typed > _billTotal;
    if (_splitTender) return _tenderSplit(context);
    return DocumentField(
      label: 'Received now',
      width: 420,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              SizedBox(
                width: 110,
                child: TextFormField(
                  key: const ValueKey('received-now-amount'),
                  controller: _receivedNow,
                  keyboardType: TextInputType.number,
                  decoration: documentBoxDecoration(context),
                  onChanged: (_) {
                    _setState(() => _receivedTouched = true);
                    _schedulePreview();
                  },
                ),
              ),
              SegmentedButton<String>(
                key: const ValueKey('received-now-method'),
                showSelectedIcon: false,
                segments: const [
                  ButtonSegment<String>(value: 'CASH', label: Text('Cash')),
                  ButtonSegment<String>(value: 'BANK', label: Text('Bank')),
                ],
                selected: <String>{_receivedMethod},
                onSelectionChanged: (Set<String> chosen) {
                  _setState(() => _receivedMethod = chosen.first);
                  _schedulePreview();
                },
              ),
              if (_receivedMethod == 'BANK')
                SizedBox(
                  width: 150,
                  child: TextFormField(
                    key: const ValueKey('received-now-reference'),
                    controller: _receivedRef,
                    maxLength: 120,
                    decoration: documentBoxDecoration(context).copyWith(
                      hintText: 'Reference',
                      counterText: '',
                    ),
                    onChanged: (_) => _schedulePreview(),
                  ),
                ),
            ],
          ),
          if (_direct)
            TextButton(
              key: const ValueKey('received-now-split'),
              onPressed: () {
                _setState(() {
                  _splitTender = true;
                  if (_tenders.isEmpty) {
                    _tenders.add(_TenderRow(
                      mode: _receivedMethod == 'BANK' ? 'BANK_TRANSFER' : 'CASH',
                      amount: _receivedNow.text.trim(),
                    ));
                  }
                });
                _schedulePreview();
              },
              child: const Text('Split payment'),
            ),
          const SizedBox(height: 2),
          if (over)
            Text(
              'More than the bill -- hand back the change',
              style: theme.textTheme.bodySmall?.copyWith(
                fontSize: 11,
                color: theme.colorScheme.error,
              ),
            )
          else
            DocumentSideNote(
              _isWalkIn
                  ? 'A walk-in bill is paid in full at the counter.'
                  : 'Recorded as a receipt when the bill is approved.',
            ),
        ],
      ),
    );
  }

  static const Map<String, String> _tenderModes = <String, String>{
    'CASH': 'Cash',
    'UPI': 'UPI',
    'CARD': 'Card',
    'BANK_TRANSFER': 'Bank transfer',
  };

  /// SEL-12: the counter payment as rows of mode, amount and reference, with
  /// what is still owed and the change to give back.
  Widget _tenderSplit(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    double paid = 0;
    for (final _TenderRow row in _tenders) {
      paid += row.value;
    }
    final double total = _billTotal;
    final double change = _changeToGive;
    final double balance = total - paid;
    final bool nonCashOver = change <= 0 && total > 0 && paid > total + 0.004;
    return DocumentField(
      label: 'Received now',
      width: 460,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (int i = 0; i < _tenders.length; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: 2),
              child: Wrap(
                key: ValueKey<String>('tender-row-$i'),
                spacing: 6,
                runSpacing: 6,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  SizedBox(
                    width: 130,
                    child: DropdownButtonFormField<String>(
                      key: ValueKey<String>('tender-mode-$i'),
                      isExpanded: true,
                      initialValue: _tenders[i].mode,
                      decoration: documentBoxDecoration(context),
                      items: [
                        for (final MapEntry<String, String> mode
                            in _tenderModes.entries)
                          DropdownMenuItem<String>(
                            value: mode.key,
                            child: Text(mode.value),
                          ),
                      ],
                      onChanged: (String? value) {
                        if (value == null) return;
                        _setState(() => _tenders[i].mode = value);
                        _schedulePreview();
                      },
                    ),
                  ),
                  SizedBox(
                    width: 100,
                    child: TextFormField(
                      key: ValueKey<String>('tender-amount-$i'),
                      controller: _tenders[i].amount,
                      keyboardType: TextInputType.number,
                      decoration: documentBoxDecoration(context)
                          .copyWith(hintText: 'Amount'),
                      onChanged: (_) {
                        _setState(() {});
                        _schedulePreview();
                      },
                    ),
                  ),
                  SizedBox(
                    width: 120,
                    child: TextFormField(
                      key: ValueKey<String>('tender-reference-$i'),
                      controller: _tenders[i].reference,
                      maxLength: 120,
                      decoration: documentBoxDecoration(context).copyWith(
                        hintText: 'Reference',
                        counterText: '',
                      ),
                      onChanged: (_) => _schedulePreview(),
                    ),
                  ),
                  IconButton(
                    key: ValueKey<String>('tender-remove-$i'),
                    tooltip: 'Remove',
                    icon: const Icon(Icons.close, size: 16),
                    onPressed: () {
                      _setState(() {
                        _tenders.removeAt(i).dispose();
                        if (_tenders.isEmpty) _splitTender = false;
                      });
                      _schedulePreview();
                    },
                  ),
                ],
              ),
            ),
          Wrap(
            spacing: 8,
            runSpacing: 0,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              if (_tenders.length < 5)
                TextButton(
                  key: const ValueKey('tender-add'),
                  style: TextButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                  ),
                  onPressed: () =>
                      _setState(() => _tenders.add(_TenderRow(mode: 'UPI'))),
                  child: const Text('Add payment'),
                ),
              TextButton(
                key: const ValueKey('received-now-single'),
                style: TextButton.styleFrom(
                  visualDensity: VisualDensity.compact,
                ),
                onPressed: () {
                  _setState(() => _splitTender = false);
                  _schedulePreview();
                },
                child: const Text('One amount'),
              ),
              Text(
                'Balance ${indianAmount(balance > 0 ? balance : 0, full: true)}',
                key: const ValueKey('tender-balance'),
                style: theme.textTheme.bodySmall,
              ),
              if (change > 0)
                Text(
                  'Change to give ${indianAmount(change, full: true)}',
                  key: const ValueKey('tender-change'),
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
            ],
          ),
          if (nonCashOver)
            Text(
              'More than the bill, and not in cash -- there is no change to '
              'hand back',
              style: theme.textTheme.bodySmall?.copyWith(
                fontSize: 11,
                color: theme.colorScheme.error,
              ),
            ),
        ],
      ),
    );
  }

  Widget _invoiceTotals() {
    final Map<String, dynamic>? invoice = _preview?.invoice;
    final double subtotal =
        double.tryParse(stringValue(invoice?['subtotal'])) ?? _beforeTax;
    final double tax = double.tryParse(stringValue(invoice?['tax_total'])) ?? 0;
    final double total =
        double.tryParse(stringValue(invoice?['grand_total'])) ?? subtotal;
    final double charges =
        double.tryParse(stringValue(invoice?['charges_total'])) ?? 0;
    final bool interstate = _preview?.interstate ?? false;
    return DocumentTotalsBar(
      total: invoice == null ? null : total,
      note: _direct
          ? 'Choose the customer and a product, and the bill is priced with '
              'its tax.'
          : 'Choose what to bill, and it is priced with its tax.',
      figures: [
        ('Taxable', subtotal),
        if (charges != 0) ('Charges', charges),
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

  /// The batch picker of a line the bill dispatches itself, the delivery
  /// note's own panel (backlog 79 row 2). The bill's date is the date the
  /// stock is judged on; the quantity is taken as stock units.
  Widget _batchPanel({
    required String lineId,
    required String productId,
    required String warehouseId,
    required double quantity,
    required Map<String, double>? picks,
    required ValueChanged<Map<String, double>> onChanged,
    ValueChanged<double?>? onBatchPrice,
  }) {
    final Product? product = _product(productId);
    final bool comparable = product == null ||
        product.salesUomId.isEmpty ||
        product.inventoryUomId.isEmpty ||
        product.salesUomId == product.inventoryUomId;
    return BatchPickerPanel(
      key: ValueKey<String>('sales-invoice-batches-$lineId-$productId'),
      api: widget.api,
      lineId: lineId,
      productId: productId,
      customerId: _direct ? _customerId : _document?.customerId,
      warehouseId: warehouseId,
      asOf: _iso(widget.today),
      quantity: quantity,
      picks: picks,
      enabled: !_saving,
      comparable: comparable,
      showPtrPts: widget.features.isEnabled('BATCH_PTR_PTS'),
      onBatchPrice: onBatchPrice,
      keyPrefix: 'sales-invoice',
      unreadableNote: 'could not read the batches; they will go earliest '
          'expiry first when the bill is saved',
      noWarehouseNote: 'this firm names no default warehouse, so the batches '
          'go earliest expiry first',
      mismatchNote: 'The batches do not add up to what this line bills; '
          'saving will be refused.',
      onChanged: onChanged,
    );
  }

  /// Backlog 79 row 7: a counter line shipping from one batch takes that
  /// batch's selling price as its rate, when the firm asks for it and the
  /// person has not typed a rate of their own. The price is before tax, so a
  /// bill whose rates include GST is left alone.
  void _takeBatchPrice(_DirectLine line, double? price) {
    if (!_priceFromBatch || price == null || price <= 0) return;
    if (_rateIncludesTax || !line.priceUntyped) return;
    final String text = price.toStringAsFixed(2);
    if (line.price.text == text) return;
    _setState(() {
      line.price.text = text;
      line.autoPrice = text;
    });
    _schedulePreview();
  }

  Widget _invoiceSidePanel(BuildContext context) {
    final Customer? customer = _customer;
    final List<Widget> line = <Widget>[];
    if ((_direct || (_addsProducts && _addedFocus)) &&
        _directLines.isNotEmpty) {
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
          DocumentSideNote(documentLastBilled(companion.lastInvoiceNumber,
              companion.lastInvoiceDate, companion.lastDiscountPercent)),
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
          taxRule: LineTaxRule.fromJson(priced),
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
        if (draft.productId != null && _isBatched(draft.productId!))
          _batchPanel(
            lineId: 'direct-$index',
            productId: draft.productId!,
            warehouseId: _directWarehouse,
            quantity: double.tryParse(draft.quantity.text.trim()) ?? 0,
            picks: draft.batchPicks,
            onChanged: (picks) => _setState(() => draft.batchPicks = picks),
            onBatchPrice: (price) => _takeBatchPrice(draft, price),
          ),
      ]);
    } else if (_lineEntries.isNotEmpty) {
      final int index = _current.clamp(0, _lineEntries.length - 1);
      final (BillableDocument document, BillableLine source) =
          _lineEntries[index];
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
          DocumentSideNote(documentLastBilled(companion.lastInvoiceNumber,
              companion.lastInvoiceDate, companion.lastDiscountPercent)),
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
          taxRule: LineTaxRule.fromJson(priced),
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
        if (_picksBatches(document, source))
          _batchPanel(
            lineId: source.sourceDocumentLineId,
            productId: source.productId,
            warehouseId: source.warehouseId.isEmpty
                ? _directWarehouse
                : source.warehouseId,
            quantity: _quantityOf(source),
            picks: _batchPicks[source.sourceDocumentLineId],
            onChanged: (picks) => _setState(
                () => _batchPicks[source.sourceDocumentLineId] = picks),
          ),
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
