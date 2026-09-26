part of 'sales_return_editor_dialog.dart';

/// One line of the source document on the phase 2 return screen: how much
/// of it came back, in what condition, and which units.
class _ReturnLineDraft {
  _ReturnLineDraft(this.line);

  final ReturnableLine line;
  String quantity = '0';
  String damaged = '0';
  String scrap = '0';

  /// What the line may name, read the first time the line is looked at.
  ReturnableSerials serials = ReturnableSerials.untracked;
  bool serialsRead = false;
  final Set<String> picked = <String>{};

  double get returned => double.tryParse(quantity.trim()) ?? 0;
  double get damagedQuantity => double.tryParse(damaged.trim()) ?? 0;
  double get scrapQuantity => double.tryParse(scrap.trim()) ?? 0;
  double get sent => double.tryParse(line.quantity) ?? 0;
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
  static const List<DocumentColumn> _columns = [
    DocumentColumn('#', 28),
    DocumentColumn('Product', 0),
    DocumentColumn('Sent', 64, numeric: true),
    DocumentColumn('Returning', 80, numeric: true),
    DocumentColumn('Damaged', 70, numeric: true),
    DocumentColumn('Scrap', 60, numeric: true),
    DocumentColumn('To shelf', 68, numeric: true),
    DocumentColumn('Rate', 84, numeric: true),
    DocumentColumn('Taxable', 92, numeric: true),
    DocumentColumn('GST', 48, numeric: true),
    DocumentColumn('Amount', 100, numeric: true),
  ];

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
    final String number = stringValue(_preview?.salesReturn['return_number']);
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.escape): () =>
            Navigator.of(context).pop(),
        const SingleActivator(LogicalKeyboardKey.keyS, control: true):
            _phase2Save,
      },
      child: Focus(
        autofocus: true,
        child: Material(
          color: scheme.surface,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DocumentPageBand(
                title: 'New sales return',
                chips: [
                  if (number.isNotEmpty) '$number (new)',
                  if (_document != null) 'against ${_document!.number}',
                  'Draft',
                ],
                hint: 'Enter next field  ·  Ctrl+S save',
                actions: [
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Cancel'),
                  ),
                  FilledButton(
                    key: const ValueKey('sales-return-save'),
                    onPressed: _phase2Save,
                    child: const Text('Save draft'),
                  ),
                ],
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
    _setState(() {
      _drafts = [
        for (final ReturnableLine line in document.lines)
          _ReturnLineDraft(line),
      ];
      _current = 0;
      _preview = null;
    });
  }

  /// The return as the caller creates it: every line with something
  /// coming back. Null (with the reason said) while it cannot be saved.
  Json? _phase2Payload({bool pricing = false}) {
    final ReturnableDocument? document = _document;
    if (document == null) return null;
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
      if (draft.returned > draft.sent) {
        problem = '$name: only ${_quantity(draft.sent)} went out.';
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
    return <String, dynamic>{
      'warehouse_id': _warehouseId,
      'return_date': widget.today.toIso8601String().split('T').first,
      if (_customerNumber.text.trim().isNotEmpty)
        'customer_return_number': _customerNumber.text.trim(),
      if (_reason.text.trim().isNotEmpty) 'return_reason': _reason.text.trim(),
      if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
      'lines': [
        for (int i = 0; i < sending.length; i++)
          <String, dynamic>{
            'source_document_type': document.sourceType.code,
            'source_document_id': document.id,
            'source_document_line_id': sending[i].line.id,
            'line_number': i + 1,
            'current_return_quantity': sending[i].quantity.trim(),
            'damaged_quantity': sending[i].damaged.trim().isEmpty
                ? '0'
                : sending[i].damaged.trim(),
            'scrap_quantity':
                sending[i].scrap.trim().isEmpty ? '0' : sending[i].scrap.trim(),
            if (sending[i].serials.serialTracked)
              'serial_ids': [...sending[i].picked],
            if (_reason.text.trim().isNotEmpty)
              'reason_code': _reason.text.trim(),
          },
      ],
    };
  }

  void _phase2Save() {
    final Json? payload = _phase2Payload();
    if (payload != null) Navigator.of(context).pop(payload);
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
      _setState(() => draft.serials = found);
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
        child: DropdownMenu<String>(
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
          child: Text(documentDate(widget.today)),
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
    for (final dynamic raw
        in _preview?.salesReturn['lines'] as List? ?? const []) {
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
      draft.returned * _number(draft.line.unitPrice);

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
        : _number(stringValue(priced['gross_amount'])) -
            _number(stringValue(priced['discount_amount'])) -
            _number(stringValue(priced['bill_discount_amount']));
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
        Text(documentQuantity(draft.line.quantity), style: quiet),
        _cellBox(
          context,
          index: index,
          name: 'returning',
          value: draft.quantity,
          over: draft.returned > draft.sent,
          onChanged: (value) => draft.quantity = value,
        ),
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

  Widget _returnTotals() {
    final Map<String, dynamic>? priced = _preview?.salesReturn;
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
        ('Credit to customer', total),
      ],
    );
  }

  Widget _returnSidePanel(BuildContext context) {
    if (_drafts.isEmpty) {
      return const DocumentSidePanel(children: [
        DocumentSideHeading('Returning'),
        DocumentSideNote('the document chosen has no lines to return'),
      ]);
    }
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final int index = _current.clamp(0, _drafts.length - 1);
    final _ReturnLineDraft draft = _drafts[index];
    final Map<String, dynamic>? priced = _pricedLine(index);
    final DocumentPreviewLine? companion = _companion(index);
    final double taxable = priced == null
        ? _typedTaxable(draft)
        : _number(stringValue(priced['gross_amount'])) -
            _number(stringValue(priced['discount_amount'])) -
            _number(stringValue(priced['bill_discount_amount']));
    final double tax =
        priced == null ? 0 : _number(stringValue(priced['tax_amount']));
    return DocumentSidePanel(children: [
      DocumentSideHeading(
        'Line ${draft.line.lineNumber} · ${draft.line.description}',
      ),
      DocumentSidePair('Went out', documentQuantity(draft.line.quantity)),
      DocumentSidePair('Coming back', _quantity(draft.returned)),
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
