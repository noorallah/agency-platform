part of 'sales_return_editor_dialog.dart';

/// One line of the source document on the phase 2 return screen: how much
/// of it came back, in what condition, and which units.
class _ReturnLineDraft {
  _ReturnLineDraft(this.line);

  final ReturnableLine line;
  String quantity = '0';
  String damaged = '0';
  String scrap = '0';

  /// How many of what comes back are free goods; blank lets the server take
  /// the charged units first.
  String free = '';

  /// What the line may name, read the first time the line is looked at.
  ReturnableSerials serials = ReturnableSerials.untracked;
  bool serialsRead = false;
  final Set<String> picked = <String>{};

  /// L5 step 10: the line's Box, Pcs, Free box and Free pcs cells, used
  /// while the return is typed in boxes and pieces. [quantity] and [free]
  /// stay the figures sent, in pieces.
  final BoxPieceEntry boxes = BoxPieceEntry();

  /// L5 step 10: the pack the line went out at, or null where it had none.
  double? get pack => packOf(line.packSize);

  /// Fill the box cells from the figures in pieces.
  void loadBoxes() => boxes.load(quantity: quantity, free: free, pack: pack);

  /// The Draft's own line for this row while one is edited (D-UI-39); null
  /// on a new return and on a row the Draft brings nothing back on.
  SalesReturnLine? stored;

  /// Open the row holding what the Draft's line holds.
  ///
  /// The free box is filled only where the line brought free goods back.
  /// The server keeps one free figure whether somebody typed it or it took
  /// the charged units first, so the two cannot be told apart afterwards;
  /// sending the figure back is what keeps a save with nothing changed from
  /// moving a unit between charged and free. A stored 0 stays blank: blank
  /// reaches 0 by itself, and a typed 0 would refuse a thirteenth unit that
  /// blank takes as the free one.
  void hold(SalesReturnLine held) {
    stored = held;
    quantity = _plain(held.currentReturnQuantity);
    damaged = _plain(held.damagedQuantity);
    scrap = _plain(held.scrapQuantity);
    free = (double.tryParse(held.freeQuantity) ?? 0) > 0
        ? _plain(held.freeQuantity)
        : '';
    picked
      ..clear()
      ..addAll(held.serials.map((unit) => unit.id));
  }

  /// "5.0000" as somebody would type it: "5".
  static String _plain(String value) {
    final String text = value.trim();
    if (text.isEmpty) return '0';
    if (!text.contains('.')) return text;
    final String cut = text.replaceFirst(RegExp(r'0+$'), '');
    return cut.endsWith('.') ? cut.substring(0, cut.length - 1) : cut;
  }

  double get typedQuantity => double.tryParse(quantity.trim()) ?? 0;

  /// Everything coming back on the line. A quantity of 0 beside a free
  /// figure is the other way of typing free goods alone ("0 charged, 1
  /// free"), and the server reads it as that many, all free (D-PRC-51).
  double get returned => typedQuantity > 0
      ? typedQuantity
      : (line.shippedFree ? freeQuantity : 0);
  double get damagedQuantity => double.tryParse(damaged.trim()) ?? 0;
  double get scrapQuantity => double.tryParse(scrap.trim()) ?? 0;
  double get sent => double.tryParse(line.quantity) ?? 0;
  double get sentFree => double.tryParse(line.freeQuantity) ?? 0;
  double get freeQuantity => double.tryParse(free.trim()) ?? 0;

  /// Everything the line may bring back: the charged units and the free ones
  /// it sent.
  double get mayReturn => sent + sentFree;
  double get restock => returned - damagedQuantity - scrapQuantity;
}

/// The sales return screen in the phase 2 app: the documents' one-screen
/// layout (wireframe view 7) for goods coming back -- the delivery note or
/// invoice they went out on, **every** line of it as a table so a return of
/// several products is one document, the credit and its tax priced as it
/// is typed by `POST /sales-returns/preview`, and a side panel for the line's
/// figures and the serial numbers coming back. The dialog still hands its
/// payload to the caller, which creates the return.
extension _Phase2SalesReturnEditor on _SalesReturnEditorDialogState {
  List<DocumentColumn> get _columns => [
    const DocumentColumn('#', 28),
    DocumentColumn(
      'Product',
      0,
      // L5 step 10: the toggle above the lines, with room kept for it
      // before the table scrolls sideways.
      minWidth: _offersBoxes ? 300 : DocumentLineTable.minFlexWidth,
      heading: _offersBoxes
          ? BoxPieceToggle(
              key: const ValueKey('sales-return-box-and-pieces'),
              label: 'Product',
              value: _boxAndPieces,
              onChanged: saving ? null : _setBoxAndPieces,
            )
          : null,
    ),
    // "3 x 12 + 5" is wider than a figure.
    DocumentColumn('Sent', _boxAndPieces ? 84 : 64, numeric: true),
    // L5 step 10: typed as boxes and pieces, Returning and Of which free
    // become four cells.
    if (_boxAndPieces)
      ...boxPieceColumns
    else ...const [
      DocumentColumn('Returning', 80, numeric: true),
      DocumentColumn('Of which free', 96, numeric: true),
    ],
    const DocumentColumn('Damaged', 70, numeric: true),
    const DocumentColumn('Scrap', 60, numeric: true),
    const DocumentColumn('To shelf', 68, numeric: true),
    const DocumentColumn('Rate', 84, numeric: true),
    const DocumentColumn('Taxable', 92, numeric: true),
    const DocumentColumn('GST', 48, numeric: true),
    const DocumentColumn('Amount', 100, numeric: true),
  ];

  /// L5 step 10: whether the toggle is offered. This window reads no
  /// settings and no customer, so it is offered where the note or bill the
  /// goods went out on, or the Draft being put right, was typed as boxes
  /// and pieces -- which only a firm with the switch on can have done.
  bool get _offersBoxes =>
      _phase2 &&
      (_document?.boxAndPieceEntry == true ||
          widget.editing?.boxAndPieceEntry == true);

  /// L5 step 10: the toggle above the lines. Changes no quantity: the same
  /// figures are shown as one cell or as two.
  void _setBoxAndPieces(bool value) {
    _setState(() {
      _boxAndPieces = value;
      if (value) {
        for (final _ReturnLineDraft draft in _drafts) {
          draft.loadBoxes();
        }
      }
    });
  }

  /// L5 step 10: a quantity of [draft]'s line as the lines are shown: "3 x
  /// 12 + 5" while typed in boxes and pieces.
  String _figure(String value, _ReturnLineDraft draft) => _boxAndPieces
      ? boxesAndPieces(value, draft.line.packSize)
      : documentQuantity(value);

  Widget _phase2Page(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    if (widget.documents.isEmpty) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'Nothing has gone out yet',
        message: 'A return is raised against a delivery note or a sales '
            'invoice, so there has to be one before goods can come back.',
      );
    }
    final SalesReturn? editing = widget.editing;
    if (editing != null && _document == null) {
      return StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'Edit ${editing.returnNumber}',
        message: salesReturnEditRefusal(editing, widget.documents) ??
            'The document this return was raised against could not be found.',
      );
    }
    final String number = stringValue(_preview?.salesReturn['return_number']);
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.escape): () =>
            leaveDocument(context),
        const SingleActivator(LogicalKeyboardKey.keyS, control: true):
            _phase2Save,
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
                // A Draft opened again is named by its own number, which
                // the save keeps (D-UI-39).
                title:
                    editing == null ? 'New sales return' : 'Edit sales return',
                number: editing?.returnNumber ?? '',
                chips: [
                  if (editing == null && number.isNotEmpty) '$number (new)',
                  if (_document != null) 'against ${_document!.number}',
                  'Draft',
                ],
                hint: 'Enter next field  ·  Ctrl+S save',
                actions: [
                  TextButton(
                    onPressed: () => leaveDocument(context),
                    child: const Text('Cancel'),
                  ),
                  FilledButton(
                    key: const ValueKey('sales-return-save'),
                    onPressed: saving ? null : _phase2Save,
                    child: const Text('Save draft'),
                  ),
                ],
              ),
              if (saveError != null)
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                  child: saveErrorBanner(),
                ),
              if (_phase2Problem != null)
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                  child: MaterialBanner(
                    contentTextStyle: theme.textTheme.bodyMedium,
                    content: Text(_phase2Problem!),
                    actions: [
                      TextButton(
                        onPressed: () => _setState(() => _phase2Problem = null),
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
                            _returnHeader(context),
                            Expanded(
                              child: DocumentLineTable(
                                columns: _columns,
                                rows: [
                                  for (int i = 0; i < _drafts.length; i++)
                                    _returnRow(context, i),
                                ],
                              ),
                            ),
                            _returnTotals(),
                          ],
                        ),
                      ),
                      if (constraints.maxWidth >= DocumentSidePanel.showFrom)
                        _returnSidePanel(context),
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

  double _number(String value) => double.tryParse(value.trim()) ?? 0;

  String _quantity(double value) => documentQuantity(
        value == value.roundToDouble()
            ? value.toStringAsFixed(0)
            : value.toString(),
      );

  /// Rebuild the lines for the chosen document: nothing coming back until
  /// it is typed, so no line returns by accident.
  void _phase2Document(ReturnableDocument document) {
    final List<_ReturnLineDraft> replaced = _drafts;
    _setState(() {
      _drafts = [
        for (final ReturnableLine line in document.lines)
          _ReturnLineDraft(line),
      ];
      _current = 0;
      _preview = null;
      // L5 step 10: a new return follows the document it is raised against.
      _boxAndPieces = _phase2 && document.boxAndPieceEntry;
      if (_boxAndPieces) {
        for (final _ReturnLineDraft draft in _drafts) {
          draft.loadBoxes();
        }
      }
    });
    // After the frame: the old lines' cells may still be drawn this one.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      for (final _ReturnLineDraft draft in replaced) {
        draft.boxes.dispose();
      }
    });
  }

  /// Open holding the Draft [editing] (D-UI-39): its document, a row for
  /// every line of that document with the Draft's figures on the ones it
  /// brings back, and its own reference, reason and remarks.
  ///
  /// Called from `initState`, so it sets the fields and rebuilds nothing.
  void _phase2Open(SalesReturn editing) {
    _customerNumber.text = editing.customerReturnNumber;
    _reason.text = editing.returnReason;
    _remarks.text = editing.remarks;
    // A warehouse no longer on the list cannot be shown as chosen, so the
    // person chooses one rather than the save moving the goods unseen.
    final bool listed =
        widget.warehouses.any((item) => item.id == editing.warehouseId);
    _warehouseId = listed ? editing.warehouseId : null;
    if (!listed) {
      _phase2Problem = 'The warehouse ${editing.returnNumber} is taken back '
          'into is not on the list any more. Choose one before saving.';
    }
    final SalesReturnLine? first = editing.lines.firstOrNull;
    final ReturnableDocument? document = first == null
        ? null
        : widget.documents
            .where((item) =>
                item.id == first.sourceDocumentId &&
                item.sourceType == first.sourceType)
            .firstOrNull;
    if (document == null) return;
    _document = document;
    _drafts = [
      for (final ReturnableLine line in document.lines) _ReturnLineDraft(line),
    ];
    for (final _ReturnLineDraft draft in _drafts) {
      final SalesReturnLine? held = editing.lines
          .where((item) => item.sourceDocumentLineId == draft.line.id)
          .firstOrNull;
      if (held != null) draft.hold(held);
    }
    final int held = _drafts.indexWhere((draft) => draft.stored != null);
    _current = held < 0 ? 0 : held;
    // L5 step 10: a saved return reopens as it was saved.
    _boxAndPieces = editing.boxAndPieceEntry;
    if (_boxAndPieces) {
      for (final _ReturnLineDraft draft in _drafts) {
        draft.loadBoxes();
      }
    }
    // The units each line may name, so the ones it picked show as picked.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      for (final _ReturnLineDraft draft in _drafts) {
        if (draft.stored != null) unawaited(_phase2Serials(draft));
      }
    });
  }

  bool _same(String left, String right) =>
      (_number(left) - _number(right)).abs() < 0.00005;

  /// Whether the rows and the warehouse are as the Draft holds them, so its
  /// own figures still describe what is on the screen.
  bool _asStored(SalesReturn editing) {
    if (_warehouseId != editing.warehouseId) return false;
    for (final _ReturnLineDraft draft in _drafts) {
      final SalesReturnLine? held = draft.stored;
      if (held == null) {
        if (draft.returned > 0) return false;
        continue;
      }
      if ((draft.returned - _number(held.currentReturnQuantity)).abs() >=
              0.00005 ||
          !_same(draft.free, held.freeQuantity) ||
          !_same(draft.damaged, held.damagedQuantity) ||
          !_same(draft.scrap, held.scrapQuantity)) {
        return false;
      }
    }
    return true;
  }

  /// The return as the server priced it last, or the Draft's own figures
  /// while nothing on it has been changed. A Draft with a figure changed is
  /// priced by the preview as replacing itself (D-UI-99).
  Map<String, dynamic>? get _pricing {
    final Map<String, dynamic>? priced = _preview?.salesReturn;
    final SalesReturn? editing = widget.editing;
    if (priced != null || editing == null || !_asStored(editing)) {
      return priced;
    }
    return <String, dynamic>{
      'subtotal': editing.subtotal,
      'tax_total': editing.taxTotal,
      'grand_total': editing.grandTotal,
      'round_off': editing.roundOff,
      'lines': [
        for (final SalesReturnLine line in editing.lines)
          <String, dynamic>{
            'source_document_line_id': line.sourceDocumentLineId,
            'line_number': line.lineNumber,
            'net_amount': line.netAmount,
            'tax_amount': line.taxAmount,
          },
      ],
    };
  }

  /// What the Draft's header holds that this screen does not show.
  ///
  /// The server replaces a Draft's header from the request, so a field left
  /// out is written empty: changing a quantity would clear the customer's
  /// own return date, the references, the currency, the charges and every
  /// attachment record and note (D-UI-39). Each key is one the server's
  /// write model declares; it refuses the whole request for one it does
  /// not.
  Json _heldHeader(SalesReturn held) => <String, dynamic>{
        for (final (String key, String value) in [
          ('customer_return_date', held.customerReturnDate),
          ('reference_delivery_note_number', held.referenceDeliveryNoteNumber),
          ('reference_invoice_number', held.referenceInvoiceNumber),
          ('currency_code', held.currencyCode),
          ('exchange_rate', held.exchangeRate),
          ('reference_number', held.referenceNumber),
          ('business_profile_id', held.businessProfileId),
        ])
          if (value.isNotEmpty) key: value,
        if (_number(held.additionalCharges) != 0)
          'additional_charges': held.additionalCharges,
        if (_number(held.roundOff) != 0) 'round_off': held.roundOff,
        if (held.attachments.isNotEmpty) 'attachments': held.attachments,
        if (held.notes.isNotEmpty) 'notes': held.notes,
      };

  /// What the Draft's line holds that its row does not show, for the same
  /// reason as [_heldHeader]: the lines are deleted and written again.
  ///
  /// A price or a rate of discount is a figure typed on this server, and
  /// sending one switches off what it does for a line that says nothing --
  /// taking the bill's own worth. So each goes back only where it differs
  /// from the source line's, which is the one case it can have been typed.
  /// The line's own warehouse goes back only where it is not the return's,
  /// so choosing another warehouse above still moves the lines that follow
  /// it.
  Json _heldLine(_ReturnLineDraft draft, SalesReturn editing) {
    final SalesReturnLine? held = draft.stored;
    if (held == null) return const <String, dynamic>{};
    return <String, dynamic>{
      for (final (String key, String value) in [
        ('item_condition', held.itemCondition),
        ('tax_profile_id', held.taxProfileId),
        ('packaging_type_id', held.packagingTypeId),
        ('return_uom_id', held.returnUomId),
        ('storage_node_id', held.storageNodeId),
        ('batch_number', held.batchNumber),
        ('expiry_date', held.expiryDate),
        ('manufacturing_date', held.manufacturingDate),
        ('remarks', held.remarks),
      ])
        if (value.isNotEmpty) key: value,
      if (held.isDamaged) 'is_damaged': true,
      if (held.isExpired) 'is_expired': true,
      if (_number(held.chargesAmount) != 0)
        'charges_amount': held.chargesAmount,
      if (held.conversionFactor.isNotEmpty &&
          !_same(held.conversionFactor, '1'))
        'conversion_factor': held.conversionFactor,
      if (held.warehouseId.isNotEmpty &&
          held.warehouseId != editing.warehouseId)
        'warehouse_id': held.warehouseId,
      if (held.unitPrice.isNotEmpty &&
          !_same(held.unitPrice, draft.line.unitPrice))
        'unit_price': held.unitPrice,
      if (held.discountPercent.isNotEmpty &&
          !_same(held.discountPercent, draft.line.discountPercent))
        'discount_percent': held.discountPercent,
    };
  }

  /// The reason a line carries. A new return writes the header's reason on
  /// every line. A Draft's line follows the header only where it held the
  /// header's reason before; one with a reason of its own keeps it.
  String _lineReason(_ReturnLineDraft draft) {
    final SalesReturnLine? held = draft.stored;
    final SalesReturn? editing = widget.editing;
    if (held != null &&
        editing != null &&
        held.reasonCode != editing.returnReason) {
      return held.reasonCode;
    }
    return _reason.text.trim();
  }

  /// The return as the caller creates it: every line with something
  /// coming back. Null (with the reason said) while it cannot be saved.
  Json? _phase2Payload({bool pricing = false}) {
    final ReturnableDocument? document = _document;
    if (document == null) {
      if (!pricing) {
        _setState(() => _phase2Problem =
            'Choose the delivery note or invoice the goods went out on.');
      }
      return null;
    }
    final List<_ReturnLineDraft> sending = [
      for (final _ReturnLineDraft draft in _drafts)
        if (draft.returned > 0) draft,
    ];
    String? problem;
    if (_warehouseId == null) {
      problem = 'Choose the warehouse the goods are taken back into.';
    } else if (sending.isEmpty) {
      problem = 'Enter how many came back on at least one line.';
    }
    for (final _ReturnLineDraft draft in sending) {
      if (problem != null) break;
      final String name = draft.line.description.isEmpty
          ? 'Line ${draft.line.lineNumber}'
          : draft.line.description;
      if (draft.returned > draft.mayReturn) {
        problem = draft.line.shippedFree
            ? '$name: only ${_quantity(draft.sent)} charged and '
                '${_quantity(draft.sentFree)} free went out.'
            : '$name: only ${_quantity(draft.sent)} went out.';
      } else if (draft.line.shippedFree &&
          draft.freeQuantity > draft.sentFree) {
        problem = '$name: only ${_quantity(draft.sentFree)} free went out.';
      } else if (draft.freeQuantity > draft.returned) {
        problem = '$name: the free goods are more than came back.';
      } else if (draft.restock < 0) {
        problem = '$name: damaged and scrap are more than came back.';
      } else if (!pricing && draft.serials.serialTracked) {
        if (draft.returned != draft.returned.roundToDouble() ||
            draft.picked.length != draft.returned.toInt()) {
          problem = '$name: pick one serial number per unit coming back -- '
              '${_quantity(draft.returned)} needed, ${draft.picked.length} '
              'picked.';
        }
      }
    }
    if (problem != null) {
      if (!pricing) _setState(() => _phase2Problem = problem);
      return null;
    }
    final SalesReturn? editing = widget.editing;
    return <String, dynamic>{
      'warehouse_id': _warehouseId,
      'return_date': _returnDay,
      if (_customerNumber.text.trim().isNotEmpty)
        'customer_return_number': _customerNumber.text.trim(),
      if (_reason.text.trim().isNotEmpty) 'return_reason': _reason.text.trim(),
      if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
      if (editing != null) ..._heldHeader(editing),
      // L5 step 10: only where the toggle is offered; absent takes the
      // document's on a new return and keeps the return's own on an edit.
      if (_offersBoxes) 'box_and_piece_entry': _boxAndPieces,
      'lines': [
        for (int i = 0; i < sending.length; i++)
          <String, dynamic>{
            'source_document_type': document.sourceType.code,
            'source_document_id': document.id,
            'source_document_line_id': sending[i].line.id,
            'line_number': i + 1,
            'current_return_quantity': sending[i].quantity.trim().isEmpty
                ? '0'
                : sending[i].quantity.trim(),
            // L5 step 10: the pack the two cells were added up with, only
            // on a line typed as boxes and pieces.
            if (_boxAndPieces && sending[i].pack != null)
              'pack_size': sending[i].line.packSize,
            // Blank is not sent: the server then takes the charged units
            // first. Only a line that shipped free goods can say otherwise.
            if (sending[i].line.shippedFree &&
                sending[i].free.trim().isNotEmpty)
              'free_quantity': sending[i].free.trim(),
            'damaged_quantity': sending[i].damaged.trim().isEmpty
                ? '0'
                : sending[i].damaged.trim(),
            'scrap_quantity':
                sending[i].scrap.trim().isEmpty ? '0' : sending[i].scrap.trim(),
            // Always said for a Draft: a line that says nothing takes the
            // picks of whichever line held its number before, and the
            // numbers move when a line above stops coming back (D-UI-39).
            if (editing != null || sending[i].serials.serialTracked)
              'serial_ids': [...sending[i].picked],
            if (_lineReason(sending[i]).isNotEmpty)
              'reason_code': _lineReason(sending[i]),
            if (editing != null) ..._heldLine(sending[i], editing),
          },
      ],
    };
  }

  /// The day the return is dated: today for a new one, and its own day for
  /// a Draft opened again -- putting a quantity right must not move it into
  /// another period (D-UI-39).
  String get _returnDay {
    final String held = widget.editing?.returnDate ?? '';
    return held.isNotEmpty
        ? held
        : widget.today.toIso8601String().split('T').first;
  }

  void _phase2Save() {
    final Json? payload = _phase2Payload();
    if (payload != null) unawaited(submit(payload, widget.onSave));
  }

  /// Read which units a line may bring back, the first time it is looked
  /// at with something coming back on it.
  Future<void> _phase2Serials(_ReturnLineDraft draft) async {
    final ReturnableDocument? document = _document;
    final loader = widget.loadSerials;
    if (loader == null || document == null || draft.serialsRead) return;
    draft.serialsRead = true;
    try {
      final ReturnableSerials found = await loader(document, draft.line);
      if (!mounted) return;
      _setState(() {
        draft.serials = found;
        // A unit a Draft picked that may no longer come back is dropped
        // where it can be seen: the count beside the chips falls short and
        // the save asks for another, rather than sending one that has no
        // chip to unpick it by.
        if (found.serialTracked) {
          draft.picked.retainAll(found.serials.map((unit) => unit.id));
        }
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      _setState(() => _phase2Problem =
          'Could not read the serial numbers: ${exception.message}');
    }
  }

  Widget _returnHeader(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final ReturnableDocument? document = _document;
    Widget box(String label, TextEditingController controller, double width,
            {String? hint}) =>
        DocumentField(
          label: label,
          width: width,
          child: TextFormField(
            controller: controller,
            decoration: documentBoxDecoration(context, hint: hint),
          ),
        );
    return DocumentHeader(children: [
      DocumentField(
        label: 'Returned against (delivery note or invoice)',
        width: 420,
        below: document == null
            ? null
            : Text(
                [
                  if (document.customerName.isNotEmpty) document.customerName,
                  if (document.documentDate.isNotEmpty)
                    'on ${_dayOf(document.documentDate)}',
                  '${document.lines.length} '
                      '${document.lines.length == 1 ? 'line' : 'lines'}',
                ].join('  ·  '),
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall?.copyWith(
                  fontSize: 11,
                  color: scheme.onSurfaceVariant,
                ),
              ),
        // Fixed on a Draft opened again (D-UI-39): another document is
        // another customer's goods, which is a new return, not this one put
        // right.
        child: widget.editing != null && document != null
            ? InputDecorator(
                key: const ValueKey('sales-return-document-fixed'),
                decoration: documentBoxDecoration(context),
                child: Text(
                  '${document.sourceType.label}  ${document.label}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              )
            : DropdownMenu<String>(
          key: const ValueKey('sales-return-document'),
          initialSelection: document?.id,
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
            for (final ReturnableDocument item in widget.documents)
              DropdownMenuEntry<String>(
                value: item.id,
                label: '${item.sourceType.label}  ${item.label}',
              ),
          ],
          onSelected: (value) {
            for (final ReturnableDocument item in widget.documents) {
              if (item.id == value && item.id != _document?.id) {
                _selectDocument(item);
              }
            }
          },
        ),
      ),
      DocumentField(
        label: 'Return date',
        auto: true,
        width: 130,
        child: InputDecorator(
          decoration: documentBoxDecoration(context),
          child: Text(_dayOf(_returnDay)),
        ),
      ),
      DocumentField(
        label: 'Taken back into',
        auto: _warehouseId != null,
        width: 200,
        child: DropdownButtonFormField<String>(
          key: const ValueKey('sales-return-warehouse'),
          isExpanded: true,
          isDense: true,
          initialValue: _warehouseId,
          decoration: documentBoxDecoration(context, hint: 'Choose'),
          items: [
            for (final WarehouseRecord item in widget.warehouses)
              DropdownMenuItem<String>(
                value: item.id,
                child: Text(item.code, overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: (value) {
            _setState(() => _warehouseId = value);
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
      box("Customer's reference", _customerNumber, 170,
          hint: 'their paperwork'),
      box('Why it came back', _reason, 220),
      box('Remarks', _remarks, 220),
    ]);
  }

  String _dayOf(String value) {
    final DateTime? day = DateTime.tryParse(value);
    return day == null ? value : documentDate(day);
  }

  Map<String, dynamic>? _pricedLine(int index) {
    final String id = _drafts[index].line.id;
    for (final dynamic raw in _pricing?['lines'] as List? ?? const []) {
      if (raw is Map && stringValue(raw['source_document_line_id']) == id) {
        return Map<String, dynamic>.from(raw);
      }
    }
    return null;
  }

  DocumentPreviewLine? _companion(int index) {
    final Map<String, dynamic>? priced = _pricedLine(index);
    if (priced == null) return null;
    final int number = (priced['line_number'] as num?)?.toInt() ?? 0;
    for (final DocumentPreviewLine line
        in _preview?.lines ?? const <DocumentPreviewLine>[]) {
      if (line.lineNumber == number) return line;
    }
    return null;
  }

  double _typedTaxable(_ReturnLineDraft draft) =>
      (draft.returned - draft.freeQuantity).clamp(0, double.infinity) *
      _number(draft.line.unitPrice);

  Widget _cellBox(
    BuildContext context, {
    required int index,
    required String name,
    required String value,
    required ValueChanged<String> onChanged,
    bool over = false,
  }) =>
      TextFormField(
        key: ValueKey<String>('sales-return-$name-${_document?.id}-$index'),
        initialValue: value,
        textAlign: TextAlign.right,
        keyboardType: TextInputType.number,
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              fontSize: 13,
              color: over ? Theme.of(context).colorScheme.error : null,
            ),
        decoration: documentCellDecoration(context),
        onTap: () => _focusLine(index),
        onChanged: (next) {
          _setState(() => onChanged(next));
          _focusLine(index);
          _schedulePreview();
        },
      );

  void _focusLine(int index) {
    _setState(() => _current = index);
    final _ReturnLineDraft draft = _drafts[index];
    if (draft.returned > 0) unawaited(_phase2Serials(draft));
  }

  Widget _returnRow(BuildContext context, int index) {
    final ThemeData theme = Theme.of(context);
    final _ReturnLineDraft draft = _drafts[index];
    final Map<String, dynamic>? priced = _pricedLine(index);
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final TextStyle? quiet =
        text?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final double taxable = priced == null
        ? _typedTaxable(draft)
        // With the line's charges too (D-UI-96): the amount less its tax
        // is what the line was taxed on.
        : documentLineTaxable(priced['net_amount'], priced['tax_amount']) ?? 0;
    final double tax =
        priced == null ? 0 : _number(stringValue(priced['tax_amount']));
    final double rate = taxable > 0 ? tax / taxable * 100 : 0;
    return DocumentLineRow(
      key: ValueKey<String>('sales-return-line-$index'),
      columns: _columns,
      current: index == _current,
      onTap: () => _focusLine(index),
      cells: [
        Text('${draft.line.lineNumber}', style: text),
        Padding(
          padding: const EdgeInsets.only(right: 8),
          child: Text(
            draft.line.description.isEmpty
                ? 'Line ${draft.line.lineNumber}'
                : draft.line.description,
            overflow: TextOverflow.ellipsis,
            style: text,
          ),
        ),
        Text(
          _figure(draft.line.quantity, draft),
          key: ValueKey<String>('sales-return-sent-$index'),
          style: quiet,
        ),
        if (_boxAndPieces)
          ..._boxCells(context, index)
        else ...[
          _cellBox(
            context,
            index: index,
            name: 'returning',
            value: draft.quantity,
            over: draft.returned > draft.mayReturn,
            onChanged: (value) => draft.quantity = value,
          ),
          if (draft.line.shippedFree)
            Tooltip(
              message: 'Sent ${_quantity(draft.sent)} charged and '
                  '${_quantity(draft.sentFree)} free. Blank takes the charged '
                  'units first; free units are credited nothing. Returning 0 '
                  'with a number here sends back only that many free units.',
              child: _cellBox(
                context,
                index: index,
                name: 'free',
                value: draft.free,
                over: draft.freeQuantity > draft.sentFree ||
                    draft.freeQuantity > draft.returned,
                onChanged: (value) => draft.free = value,
              ),
            )
          else
            Text('', style: quiet),
        ],
        _cellBox(
          context,
          index: index,
          name: 'damaged',
          value: draft.damaged,
          over: draft.restock < 0,
          onChanged: (value) => draft.damaged = value,
        ),
        _cellBox(
          context,
          index: index,
          name: 'scrap',
          value: draft.scrap,
          over: draft.restock < 0,
          onChanged: (value) => draft.scrap = value,
        ),
        Text(
          draft.returned <= 0 ? '' : _quantity(draft.restock),
          style: quiet,
        ),
        Text(documentMoney(draft.line.unitPrice), style: quiet),
        Text(indianAmount(taxable, full: true), style: text),
        Text(
          priced == null || draft.returned <= 0
              ? ''
              : '${documentQuantity(rate.toStringAsFixed(1))}%',
          style: text,
        ),
        Text(
          indianAmount(taxable + tax, full: true),
          style: text?.copyWith(fontWeight: FontWeight.w600),
        ),
      ],
    );
  }

  /// L5 step 10: the line's Box and Pcs cells, and its Free box and Free
  /// pcs where the line sent free goods; blank cells beside a line that
  /// sent none.
  List<Widget> _boxCells(BuildContext context, int index) {
    final _ReturnLineDraft draft = _drafts[index];
    final List<Widget> cells = boxPieceCells(
      context,
      entry: draft.boxes,
      pack: draft.pack,
      readOnly: saving,
      keyPrefix: 'sales-return-line-$index',
      // A line nothing comes back on is left off the return.
      chargedRequired: false,
      onChanged: () {
        _setState(() {
          draft.quantity = draft.boxes.quantityText(draft.pack);
          if (draft.line.shippedFree) {
            draft.free = draft.boxes.freeText(draft.pack);
          }
        });
        _focusLine(index);
        _schedulePreview();
      },
    );
    return [
      ...cells.take(2),
      if (draft.line.shippedFree)
        ...cells.skip(2)
      else ...const [Text(''), Text('')],
    ];
  }

  Widget _returnTotals() {
    final Map<String, dynamic>? priced = _pricing;
    double typed = 0;
    for (final _ReturnLineDraft draft in _drafts) {
      typed += _typedTaxable(draft);
    }
    final double taxable =
        priced == null ? typed : _number(stringValue(priced['subtotal']));
    final double tax =
        priced == null ? 0 : _number(stringValue(priced['tax_total']));
    final double total =
        priced == null ? taxable : _number(stringValue(priced['grand_total']));
    // Backlog 134 (F3): what the server added to reach a whole rupee.
    final double roundOff =
        priced == null ? 0 : _number(stringValue(priced['round_off']));
    final bool? interstate = _preview?.interstate;
    return DocumentTotalsBar(
      total: priced == null ? null : total,
      note: typed <= 0
          ? 'Type how many came back on each line.'
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
        if (roundOff != 0) ('Round off', roundOff),
        ('Credit to customer', total),
      ],
    );
  }

  Widget _returnSidePanel(BuildContext context) {
    if (_drafts.isEmpty) {
      return DocumentSidePanel(children: [
        const DocumentSideHeading('Returning'),
        DocumentSideNote(_document == null
            ? 'choose the document the goods went out on'
            : 'the document chosen has no lines to return'),
      ]);
    }
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final int index = _current.clamp(0, _drafts.length - 1);
    final _ReturnLineDraft draft = _drafts[index];
    final Map<String, dynamic>? priced = _pricedLine(index);
    final DocumentPreviewLine? companion = _companion(index);
    final double taxable = priced == null
        ? _typedTaxable(draft)
        // With the line's charges too (D-UI-96): the amount less its tax
        // is what the line was taxed on.
        : documentLineTaxable(priced['net_amount'], priced['tax_amount']) ?? 0;
    final double tax =
        priced == null ? 0 : _number(stringValue(priced['tax_amount']));
    return DocumentSidePanel(children: [
      DocumentSideHeading(
        'Line ${draft.line.lineNumber} · ${draft.line.description}',
      ),
      if (_boxAndPieces && draft.pack != null)
        DocumentSideNote(
          boxPieceSummary(
            packSize: draft.line.packSize,
            quantity: '${draft.returned}',
            free: draft.free,
            rate: draft.line.unitPrice,
          ),
          key: const ValueKey('sales-return-side-boxes'),
        ),
      DocumentSidePair('Went out', _figure(draft.line.quantity, draft)),
      if (draft.line.shippedFree)
        DocumentSidePair(
            'Went out free', _figure(draft.line.freeQuantity, draft)),
      DocumentSidePair(
        'Coming back',
        _boxAndPieces
            ? _figure('${draft.returned}', draft)
            : _quantity(draft.returned),
      ),
      DocumentSidePair(
        draft.restock < 0 ? 'More than came back by' : 'Back on the shelf',
        _quantity(draft.restock.abs()),
        bold: true,
        tone: draft.restock < 0 ? scheme.error : null,
      ),
      const DocumentSideNote(
        'damaged and scrap stay owned but are not sellable',
      ),
      DocumentSidePair('Rate', documentMoney(draft.line.unitPrice)),
      const DocumentSideNote('the price it went out at'),
      ...documentTaxLines(
        taxable: taxable,
        tax: tax,
        interstate: _preview?.interstate,
      ),
      if (draft.serials.serialTracked) ...[
        DocumentSideHeading(
          'Serial numbers · ${draft.picked.length} of '
          '${_quantity(draft.returned)}',
        ),
        if (draft.serials.serials.isEmpty)
          const DocumentSideNote(
            'none of the units sold on this line is still out with the '
            'customer',
          )
        else
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (final PickedSerial serial in draft.serials.serials)
              FilterChip(
                key: ValueKey<String>('serial-back-${serial.id}'),
                label: Text(serial.serialNumber),
                selected: draft.picked.contains(serial.id),
                onSelected: (picked) => _setState(() {
                  if (picked) {
                    draft.picked.add(serial.id);
                  } else {
                    draft.picked.remove(serial.id);
                  }
                }),
              ),
          ]),
      ],
      const DocumentSideHeading('Stock'),
      DocumentSidePair(
        'Where it comes back',
        companion == null ? '—' : documentQuantity(companion.availableQuantity),
      ),
      const DocumentSideNote(
        'completing the return puts the sellable part back and credits the '
        'customer',
      ),
    ]);
  }
}
