part of 'proforma_page.dart';

/// Raising a proforma in the phase 2 app: the documents' one-screen layout
/// (wireframe view 7), read-only below the header because a proforma
/// restates an order's lines exactly as they stand -- the server snapshots
/// them, and a screen that let them be edited would state a price the order
/// never agreed. What is chosen is the order, how long the prices stand and
/// the terms; what is shown is what the customer will be holding.
class _Phase2RaiseProforma extends StatefulWidget {
  const _Phase2RaiseProforma({
    required this.orders,
    required this.productNames,
    required this.today,
  });

  final List<Json> orders;

  /// Product names by id; an order line carries only the id.
  final Map<String, String> productNames;
  final DateTime today;

  @override
  State<_Phase2RaiseProforma> createState() => _Phase2RaiseProformaState();
}

class _Phase2RaiseProformaState extends State<_Phase2RaiseProforma> {
  static const List<DocumentColumn> _columns = [
    DocumentColumn('#', 28),
    DocumentColumn('Product', 0),
    DocumentColumn('Qty', 66, numeric: true),
    DocumentColumn('Free', 56, numeric: true),
    DocumentColumn('Rate', 88, numeric: true),
    DocumentColumn('Discount', 84, numeric: true),
    DocumentColumn('Taxable', 96, numeric: true),
    DocumentColumn('GST', 48, numeric: true),
    DocumentColumn('Amount', 104, numeric: true),
  ];

  late Json _order = widget.orders.first;
  DateTime? _validUntil;
  final TextEditingController _paymentTerms = TextEditingController();
  final TextEditingController _deliveryTerms = TextEditingController();
  int _current = 0;

  @override
  void dispose() {
    _paymentTerms.dispose();
    _deliveryTerms.dispose();
    super.dispose();
  }

  static String _iso(DateTime day) => day.toIso8601String().split('T').first;

  double _number(dynamic value) => double.tryParse('${value ?? ''}') ?? 0;

  List<Json> get _lines => [
        for (final dynamic line in _order['lines'] as List? ?? const [])
          if (line is Map) Map<String, dynamic>.from(line),
      ];

  String _nameOf(Json line) {
    final String description = stringValue(line['description']);
    if (description.isNotEmpty) return description;
    return widget.productNames[stringValue(line['product_id'])] ??
        'Line ${line['line_number']}';
  }

  double _taxable(Json line) =>
      _number(line['gross_amount']) -
      _number(line['discount_amount']) -
      _number(line['bill_discount_amount']);

  void _raise() => Navigator.of(context).pop(<String, dynamic>{
        'sales_order_id': stringValue(_order['id']),
        'proforma_date': _iso(widget.today),
        // Blank means no deadline, which is a real choice.
        if (_validUntil != null) 'valid_until': _iso(_validUntil!),
        if (_paymentTerms.text.trim().isNotEmpty)
          'payment_terms': _paymentTerms.text.trim(),
        if (_deliveryTerms.text.trim().isNotEmpty)
          'delivery_terms': _deliveryTerms.text.trim(),
      });

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final List<Json> lines = _lines;
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.escape): () =>
            Navigator.of(context).pop(),
        const SingleActivator(LogicalKeyboardKey.keyS, control: true): _raise,
      },
      child: Focus(
        autofocus: true,
        child: Material(
          color: scheme.surface,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DocumentPageBand(
                title: 'New proforma invoice',
                chips: ['states ${stringValue(_order['order_number'])}'],
                hint: 'Ctrl+S raise',
                actions: [
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Cancel'),
                  ),
                  FilledButton(
                    key: const ValueKey('proforma-raise'),
                    onPressed: _raise,
                    child: const Text('Raise proforma'),
                  ),
                ],
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
                            _header(context),
                            Expanded(
                              child: DocumentLineTable(
                                columns: _columns,
                                rows: [
                                  for (int i = 0; i < lines.length; i++)
                                    _row(context, i, lines[i]),
                                ],
                              ),
                            ),
                            _totals(),
                          ],
                        ),
                      ),
                      if (constraints.maxWidth >= DocumentSidePanel.showFrom)
                        _sidePanel(lines),
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

  Widget _header(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final DateTime? ordered =
        DateTime.tryParse(stringValue(_order['order_date']));
    return DocumentHeader(children: [
      DocumentField(
        label: 'Sales order it states (approved)',
        width: 440,
        below: Text(
          [
            stringValue(_order['customer_name']),
            if (ordered != null) 'ordered ${documentDate(ordered)}',
          ].where((part) => part.isNotEmpty).join('  ·  '),
          overflow: TextOverflow.ellipsis,
          style: theme.textTheme.bodySmall?.copyWith(
            fontSize: 11,
            color: scheme.onSurfaceVariant,
          ),
        ),
        child: DropdownMenu<String>(
          key: const ValueKey('proforma-order'),
          initialSelection: stringValue(_order['id']),
          width: 440,
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
            for (final Json order in widget.orders)
              DropdownMenuEntry<String>(
                value: stringValue(order['id']),
                label: proformaOrderLabel(order),
              ),
          ],
          onSelected: (value) {
            for (final Json order in widget.orders) {
              if (stringValue(order['id']) == value) {
                setState(() {
                  _order = order;
                  _current = 0;
                });
              }
            }
          },
        ),
      ),
      DocumentField(
        label: 'Dated',
        auto: true,
        width: 130,
        child: InputDecorator(
          decoration: documentBoxDecoration(context),
          child: Text(documentDate(widget.today)),
        ),
      ),
      DocumentField(
        label: 'Prices stand until',
        width: 160,
        child: InkWell(
          key: const ValueKey('proforma-valid-until'),
          onTap: () async {
            final DateTime? picked = await showDatePicker(
              context: context,
              initialDate:
                  _validUntil ?? widget.today.add(const Duration(days: 15)),
              firstDate: widget.today,
              lastDate: DateTime(2100),
            );
            if (picked != null) setState(() => _validUntil = picked);
          },
          child: InputDecorator(
            decoration: documentBoxDecoration(context).copyWith(
              suffixIcon: _validUntil == null
                  ? const Icon(Icons.event, size: 16)
                  : IconButton(
                      tooltip: 'No deadline',
                      iconSize: 14,
                      visualDensity: VisualDensity.compact,
                      onPressed: () => setState(() => _validUntil = null),
                      icon: const Icon(Icons.close),
                    ),
              suffixIconConstraints:
                  const BoxConstraints(minWidth: 28, minHeight: 20),
            ),
            child: Text(
              _validUntil == null ? 'no deadline' : documentDate(_validUntil!),
            ),
          ),
        ),
      ),
      DocumentField(
        label: 'Payment terms',
        width: 200,
        child: TextFormField(
          controller: _paymentTerms,
          decoration: documentBoxDecoration(context),
        ),
      ),
      DocumentField(
        label: 'Delivery terms',
        width: 200,
        child: TextFormField(
          controller: _deliveryTerms,
          decoration: documentBoxDecoration(context),
        ),
      ),
    ]);
  }

  Widget _row(BuildContext context, int index, Json line) {
    final ThemeData theme = Theme.of(context);
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final double taxable = _taxable(line);
    final double tax = _number(line['tax_amount']);
    final double rate = taxable > 0 ? tax / taxable * 100 : 0;
    final double discount = _number(line['discount_amount']) +
        _number(line['bill_discount_amount']);
    return DocumentLineRow(
      key: ValueKey<String>('proforma-line-$index'),
      columns: _columns,
      current: index == _current,
      onTap: () => setState(() => _current = index),
      cells: [
        Text('${line['line_number'] ?? index + 1}', style: text),
        Padding(
          padding: const EdgeInsets.only(right: 8),
          child:
              Text(_nameOf(line), overflow: TextOverflow.ellipsis, style: text),
        ),
        Text(documentQuantity(stringValue(line['quantity'])), style: text),
        Text(
          _number(line['free_quantity']) > 0
              ? documentQuantity(stringValue(line['free_quantity']))
              : '',
          style: text,
        ),
        Text(documentMoney(stringValue(line['unit_price'])), style: text),
        Text(discount > 0 ? indianAmount(discount, full: true) : '',
            style: text),
        Text(indianAmount(taxable, full: true), style: text),
        Text('${documentQuantity(rate.toStringAsFixed(1))}%', style: text),
        Text(
          indianAmount(taxable + tax, full: true),
          style: text?.copyWith(fontWeight: FontWeight.w600),
        ),
      ],
    );
  }

  Widget _totals() {
    final double subtotal = _number(_order['subtotal']);
    final double tax = _number(_order['tax_total']);
    final double total = _number(_order['grand_total']);
    final double other = total - subtotal - tax;
    return DocumentTotalsBar(
      total: total,
      figures: [
        ('Taxable', subtotal),
        ('GST', tax),
        if (other.abs() >= 0.005) ('Other charges', other),
        ('Total', total),
      ],
    );
  }

  Widget _sidePanel(List<Json> lines) {
    if (lines.isEmpty) {
      return const DocumentSidePanel(children: [
        DocumentSideHeading('Proforma'),
        DocumentSideNote('this order has no lines'),
      ]);
    }
    final Json line = lines[_current.clamp(0, lines.length - 1)];
    final double taxable = _taxable(line);
    return DocumentSidePanel(children: [
      DocumentSideHeading('Line ${line['line_number']} · ${_nameOf(line)}'),
      DocumentSidePair('Rate', documentMoney(stringValue(line['unit_price']))),
      DocumentSideNote(
        stringValue(line['discount_source']).isEmpty
            ? 'as the order agreed it'
            : 'discount from ${discountSourceWords(stringValue(line['discount_source']))}',
      ),
      ...documentTaxLines(
        taxable: taxable,
        tax: _number(line['tax_amount']),
        interstate: null,
      ),
      const DocumentSideHeading('What this is'),
      const DocumentSideNote(
        "a statement of the order for the customer's records or advance "
        'payment; it posts nothing and uses its own number series, not the '
        "tax invoice's",
      ),
      const DocumentSideNote(
        'the lines are copied as they stand; editing the order afterwards does '
        'not change the proforma the customer holds',
      ),
    ]);
  }
}
