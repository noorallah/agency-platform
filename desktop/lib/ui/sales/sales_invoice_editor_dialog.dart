import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../../models/customer.dart';
import '../../models/product.dart';
import '../../models/sales_invoice.dart';
import '../workspace/desktop_framework.dart';

/// Billing a delivery note.
///
/// Until this existed a firm using only the desktop could quote, order and
/// dispatch — and then had no way to raise the invoice. `POST /sales-invoices`
/// had worked all along and `SALES_INVOICE_CREATE` was seeded with no screen
/// checking it, so the authority was modelled and the capability was not
/// reachable. It also meant the invoice print feature had nothing to print.
///
/// The picker offers only documents with something left to bill, which the
/// server works out: a client cannot know how much of a delivery line earlier
/// invoices already took, and one that guessed would offer paperwork the save
/// then refuses.
class SalesInvoiceEditorDialog extends StatefulWidget {
  const SalesInvoiceEditorDialog({
    super.key,
    required this.api,
    required this.today,
    this.invoiceId,
  });

  final ApiClient api;

  /// Passed in rather than read here, so the dialog is testable.
  final DateTime today;

  /// The draft being corrected, or null to raise a new one.
  ///
  /// A draft could only be cancelled and re-raised before this: `PUT
  /// /api/v1/sales-invoices/{id}` existed and nothing in the desktop called
  /// it, so a mistyped quantity cost the document.
  final String? invoiceId;

  @override
  State<SalesInvoiceEditorDialog> createState() =>
      _SalesInvoiceEditorDialogState();
}

class _SalesInvoiceEditorDialogState extends State<SalesInvoiceEditorDialog> {
  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  final TextEditingController _reference = TextEditingController();
  final TextEditingController _billDiscount = TextEditingController();
  final TextEditingController _freight = TextEditingController();
  final Map<String, TextEditingController> _quantities =
      <String, TextEditingController>{};

  List<BillableDocument> _billable = const [];
  BillableDocument? _document;
  bool _loading = true;
  bool _saving = false;
  String? _error;

  /// The draft as it was read, when correcting one.
  Json? _existing;

  /// How much of each source line this draft already bills. In edit mode the
  /// ceiling is that plus whatever is still unbilled elsewhere, because the
  /// draft's own quantity is counted against the source line and would
  /// otherwise be subtracted from the number the user is allowed to keep.
  final Map<String, double> _ownQuantities = <String, double>{};

  bool get _editing => widget.invoiceId != null;

  /// Which stages this firm types. A firm that types neither the order nor the
  /// delivery note has nothing to pick from, so it names products instead and
  /// the server raises the documents behind the bill.
  SalesWorkflowSettings _stages = SalesWorkflowSettings.wholeChain;
  bool get _direct => _stages.billsDirectly && !_editing;

  List<Customer> _customers = const [];
  List<Product> _products = const [];
  String? _customerId;
  final List<_DirectLine> _directLines = <_DirectLine>[_DirectLine()];

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _reference.dispose();
    _billDiscount.dispose();
    _freight.dispose();
    for (final TextEditingController controller in _quantities.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    try {
      // Fail open to the whole chain: an unreadable setting must leave the
      // dialog working the way it always has, not strand the user in a mode
      // their firm does not use.
      SalesWorkflowSettings stages = SalesWorkflowSettings.wholeChain;
      try {
        stages = await widget.api.salesWorkflowSettings();
      } on ApiException {
        stages = SalesWorkflowSettings.wholeChain;
      }
      final bool direct = stages.billsDirectly && widget.invoiceId == null;
      final List<BillableDocument> rows =
          direct ? const [] : await widget.api.billableDocuments();
      final List<Customer> customers = direct
          ? (await widget.api.customers(pageSize: 100, sortBy: 'name',
                  descending: false))
              .items
          : const [];
      final List<Product> products = direct
          ? (await widget.api.products(pageSize: 100, sortBy: 'name',
                  descending: false))
              .items
          : const [];
      final String? id = widget.invoiceId;
      final Json? existing =
          id == null ? null : _unwrap(await widget.api.salesInvoice(id));
      if (!mounted) return;
      setState(() {
        _stages = stages;
        _customers = customers;
        _products = products;
        _billable = rows;
        _existing = existing;
        _loading = false;
        if (existing != null) {
          _adoptExisting(existing);
        } else if (rows.length == 1) {
          _choose(rows.first);
        }
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  Json _unwrap(Json response) {
    final dynamic data = response['data'];
    return data is Map ? Map<String, dynamic>.from(data) : response;
  }

  /// Build the form from a draft that already exists.
  ///
  /// Its lines are the truth about what it bills; the billable list only
  /// contributes how much *more* of each source line is available, so a
  /// correction can go up as well as down.
  void _adoptExisting(Json invoice) {
    final List<dynamic> lines =
        invoice['lines'] is List ? invoice['lines'] as List : const [];
    if (lines.isEmpty) return;
    final Json first = Map<String, dynamic>.from(lines.first as Map);
    final String sourceId = '${first['source_document_id'] ?? ''}';

    final Iterable<BillableDocument> matching =
        _billable.where((item) => item.sourceDocumentId == sourceId);
    final List<BillableLine> extra =
        matching.isEmpty ? const [] : matching.first.lines;

    final List<BillableLine> rebuilt = <BillableLine>[];
    for (final dynamic raw in lines) {
      final Json line = Map<String, dynamic>.from(raw as Map);
      final String lineId = '${line['source_document_line_id'] ?? ''}';
      final double own =
          double.tryParse('${line['current_invoice_quantity'] ?? 0}') ?? 0;
      _ownQuantities[lineId] = own;
      final Iterable<BillableLine> still =
          extra.where((item) => item.sourceDocumentLineId == lineId);
      final double elsewhere = still.isEmpty
          ? 0
          : (double.tryParse(still.first.remainingQuantity) ?? 0);
      rebuilt.add(BillableLine(
        sourceDocumentLineId: lineId,
        lineNumber: (line['line_number'] as num?)?.toInt() ?? 0,
        description: '${line['description'] ?? ''}',
        sourceQuantity: '${line['delivered_quantity'] ?? own}',
        alreadyInvoicedQuantity: '0',
        // What this draft may keep, plus anything still unbilled.
        remainingQuantity: '${own + elsewhere}',
        unitPrice: '${line['unit_price'] ?? '0'}',
        discountPercent: '${line['discount_percent'] ?? '0'}',
      ));
    }

    _document = BillableDocument(
      sourceDocumentType: '${first['source_document_type'] ?? 'DELIVERY_NOTE'}',
      sourceDocumentId: sourceId,
      sourceDocumentNumber: '${first['source_document_number'] ?? ''}',
      documentDate: '${invoice['invoice_date'] ?? ''}',
      customerId: '${invoice['customer_id'] ?? ''}',
      customerName: '${invoice['customer_name'] ?? ''}',
      branchId: '${invoice['branch_id'] ?? ''}',
      lines: rebuilt,
    );
    for (final BillableLine line in rebuilt) {
      _quantities[line.sourceDocumentLineId] = TextEditingController(
        text: '${_ownQuantities[line.sourceDocumentLineId] ?? 0}',
      );
    }
    final double bill =
        double.tryParse('${invoice['bill_discount_percent'] ?? 0}') ?? 0;
    if (bill > 0) _billDiscount.text = '${invoice['bill_discount_percent']}';
    _reference.text = '${invoice['reference_number'] ?? ''}';
  }

  /// Take a document and give each of its lines a quantity box.
  ///
  /// Defaulted to what is left rather than to what was dispatched: billing the
  /// remainder is the ordinary act, and the number is one the save accepts.
  void _choose(BillableDocument document) {
    for (final TextEditingController controller in _quantities.values) {
      controller.dispose();
    }
    _quantities.clear();
    for (final BillableLine line in document.lines) {
      _quantities[line.sourceDocumentLineId] =
          TextEditingController(text: line.remainingQuantity);
    }
    _document = document;
  }

  double _quantityOf(BillableLine line) =>
      double.tryParse(_quantities[line.sourceDocumentLineId]?.text.trim() ?? '') ??
      0;

  /// What the invoice comes to before tax, after both discounts.
  double get _beforeTax {
    final BillableDocument? document = _document;
    if (document == null) return 0;
    double lines = 0;
    for (final BillableLine line in document.lines) {
      final double gross =
          _quantityOf(line) * (double.tryParse(line.unitPrice) ?? 0);
      final double rate = double.tryParse(line.discountPercent) ?? 0;
      lines += gross * (1 - rate / 100);
    }
    final double bill = double.tryParse(_billDiscount.text.trim()) ?? 0;
    return bill <= 0 ? lines : lines * (1 - bill / 100);
  }

  /// The documents the picker may offer, one entry per source document.
  ///
  /// A fully billed source is absent from the billable list, so editing its
  /// draft needs it added back — and deduped by id rather than by object,
  /// because the chosen document and its billable twin are different
  /// instances of the same thing and `DropdownButtonFormField` asserts when
  /// two items carry one value.
  List<BillableDocument> get _pickable {
    final Map<String, BillableDocument> byId = <String, BillableDocument>{
      for (final BillableDocument item in _billable) item.sourceDocumentId: item,
    };
    final BillableDocument? chosen = _document;
    if (chosen != null) byId.putIfAbsent(chosen.sourceDocumentId, () => chosen);
    return byId.values.toList();
  }

  String _iso(DateTime value) => value.toIso8601String().split('T').first;

  Json? _payload() {
    if (_direct) return _directPayload();
    final BillableDocument? document = _document;
    if (document == null) return null;
    if (!(_form.currentState?.validate() ?? false)) return null;
    final List<Json> lines = <Json>[];
    for (final BillableLine line in document.lines) {
      final String typed =
          _quantities[line.sourceDocumentLineId]?.text.trim() ?? '';
      // A line billed at nothing is left off entirely rather than sent as a
      // zero: the server would price and store it, and an invoice carrying a
      // line for nothing is one the customer queries.
      if (typed.isEmpty || (double.tryParse(typed) ?? 0) <= 0) continue;
      lines.add(<String, dynamic>{
        'source_document_type': document.sourceDocumentType,
        'source_document_id': document.sourceDocumentId,
        'source_document_line_id': line.sourceDocumentLineId,
        'line_number': lines.length + 1,
        'current_invoice_quantity': typed,
        'unit_price': line.unitPrice,
      });
    }
    if (lines.isEmpty) return null;
    return <String, dynamic>{
      'customer_id': document.customerId,
      if (document.branchId.isNotEmpty) 'branch_id': document.branchId,
      'invoice_date': _iso(widget.today),
      if (_reference.text.trim().isNotEmpty)
        'reference_number': _reference.text.trim(),
      // Omitted when blank: absent is what tells the server there is no
      // discount on the bill, and an empty string is a schema error.
      if (_billDiscount.text.trim().isNotEmpty)
        'bill_discount_percent': _billDiscount.text.trim(),
      if (_freight.text.trim().isNotEmpty)
        'freight_amount': _freight.text.trim(),
      'lines': lines,
    };
  }

  /// A bill that names products rather than the paperwork behind them.
  ///
  /// The server raises the order and the delivery note as it saves, so what
  /// leaves the warehouse is still recorded on a delivery note and cost of
  /// goods sold still belongs to it.
  Json? _directPayload() {
    final String? customerId = _customerId;
    if (customerId == null) return null;
    if (!(_form.currentState?.validate() ?? false)) return null;
    final List<Json> lines = <Json>[];
    for (final _DirectLine line in _directLines) {
      final String product = line.productId ?? '';
      final String quantity = line.quantity.text.trim();
      if (product.isEmpty) continue;
      // A line billed at nothing is left off rather than sent as a zero, the
      // same rule the document path follows.
      if (quantity.isEmpty || (double.tryParse(quantity) ?? 0) <= 0) continue;
      lines.add(<String, dynamic>{
        'product_id': product,
        'line_number': lines.length + 1,
        'current_invoice_quantity': quantity,
        'unit_price': line.price.text.trim().isEmpty
            ? '0'
            : line.price.text.trim(),
        // Omitted when blank on purpose. Saying nothing takes whatever
        // arrangement the customer already has; sending a zero refuses it.
        if (line.discount.text.trim().isNotEmpty)
          'discount_percent': line.discount.text.trim(),
      });
    }
    if (lines.isEmpty) return null;
    return <String, dynamic>{
      'customer_id': customerId,
      'invoice_date': _iso(widget.today),
      if (_reference.text.trim().isNotEmpty)
        'reference_number': _reference.text.trim(),
      if (_billDiscount.text.trim().isNotEmpty)
        'bill_discount_percent': _billDiscount.text.trim(),
      if (_freight.text.trim().isNotEmpty)
        'freight_amount': _freight.text.trim(),
      'lines': lines,
    };
  }

  Future<void> _save() async {
    final Json? payload = _payload();
    if (payload == null) {
      setState(() => _error = 'Bill at least one line.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final String? id = widget.invoiceId;
      if (id == null) {
        await widget.api.createSalesInvoice(payload);
      } else {
        await widget.api.updateSalesInvoice(
          id,
          payload,
          expectedVersion: (_existing?['version'] as num?)?.toInt(),
        );
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      // The server's sentence names what is wrong -- an over-billed line, a
      // closed period, a credit limit -- and is more use than anything this
      // dialog could invent.
      setState(() {
        _error = error.message;
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text(_editing ? 'Edit draft invoice' : 'New Invoice'),
      content: SizedBox(
        width: 720,
        child: _loading
            ? const Center(
                child: Padding(
                  padding: EdgeInsets.all(32),
                  child: CircularProgressIndicator(),
                ),
              )
            : _direct
                ? _directForm(theme)
                : _billable.isEmpty && !_editing
                    ? const WorkspaceEmptyState(
                        title: 'Nothing is waiting to be billed',
                        message: 'Dispatch a delivery note and it appears '
                            'here. A note that has already been invoiced in '
                            'full does not.',
                      )
                    : _form_(theme),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _saving || (!_direct && _billable.isEmpty && !_editing)
              ? null
              : _save,
          child: Text(
            _saving ? 'Saving…' : (_editing ? 'Save' : 'Create draft'),
          ),
        ),
      ],
    );
  }

  /// One screen: who is buying, what they are taking, and what it costs.
  Widget _directForm(ThemeData theme) => Form(
        key: _form,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'This firm bills directly. Saving raises the order and the '
                'delivery note behind this bill, so the goods leave the '
                'warehouse and the cost is recorded with them.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                initialValue: _customerId,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Customer'),
                items: [
                  for (final Customer item in _customers)
                    DropdownMenuItem(
                      value: item.id,
                      child: Text(item.name, overflow: TextOverflow.ellipsis),
                    ),
                ],
                validator: (value) =>
                    value == null ? 'Choose a customer.' : null,
                onChanged: (value) => setState(() => _customerId = value),
              ),
              const SizedBox(height: AppSpacing.md),
              for (int index = 0; index < _directLines.length; index++)
                _directLineRow(index, theme),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: () =>
                      setState(() => _directLines.add(_DirectLine())),
                  icon: const Icon(Icons.add, size: 18),
                  label: const Text('Add line'),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              TextFormField(
                controller: _billDiscount,
                decoration: const InputDecoration(
                  labelText: 'Discount on the whole bill %',
                  helperText: 'Comes off what the lines discounted to, and '
                      'the tax falls with it.',
                  helperMaxLines: 2,
                ),
                keyboardType: TextInputType.number,
                validator: _percentage,
                onChanged: (_) => setState(() {}),
              ),
              TextFormField(
                controller: _freight,
                decoration: const InputDecoration(
                  labelText: 'Delivery charge',
                  // The opposite of the field above it, and the difference
                  // decides the tax -- so it is said rather than assumed.
                  helperText: 'Split across the lines and taxed with them.',
                  helperMaxLines: 2,
                ),
                keyboardType: TextInputType.number,
                onChanged: (_) => setState(() {}),
              ),
              TextFormField(
                controller: _reference,
                decoration:
                    const InputDecoration(labelText: "Customer's reference"),
              ),
              if (_error != null) ...[
                const SizedBox(height: AppSpacing.md),
                Text(
                  _error!,
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: theme.colorScheme.error),
                ),
              ],
            ],
          ),
        ),
      );

  Widget _directLineRow(int index, ThemeData theme) {
    final _DirectLine line = _directLines[index];
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 4,
            child: DropdownButtonFormField<String>(
              initialValue: line.productId,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Product'),
              items: [
                for (final Product item in _products)
                  DropdownMenuItem(
                    value: item.id,
                    child: Text(item.name, overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: (value) => setState(() => line.productId = value),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: TextFormField(
              controller: line.quantity,
              decoration: const InputDecoration(labelText: 'Qty'),
              keyboardType: TextInputType.number,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: TextFormField(
              controller: line.price,
              decoration: const InputDecoration(labelText: 'Price'),
              keyboardType: TextInputType.number,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: TextFormField(
              controller: line.discount,
              decoration: const InputDecoration(
                labelText: 'Disc %',
                // Never prefilled. A literal 0 reads as a refusal of every
                // standing arrangement, so blank is what takes the
                // customer's own rate.
                helperText: 'Blank takes theirs',
                helperMaxLines: 2,
              ),
              keyboardType: TextInputType.number,
              validator: _percentage,
            ),
          ),
          IconButton(
            tooltip: 'Remove line',
            onPressed: _directLines.length == 1
                ? null
                : () => setState(() => _directLines.removeAt(index)),
            icon: const Icon(Icons.close, size: 18),
          ),
        ],
      ),
    );
  }

  Widget _form_(ThemeData theme) => Form(
        key: _form,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DropdownButtonFormField<String>(
                initialValue: _document?.sourceDocumentId,
                // Without this the button's row is `mainAxisSize: min` and
                // never constrains the label, so `ellipsis` has nothing to
                // ellipsise against and a long document name overflows.
                isExpanded: true,
                decoration: const InputDecoration(
                  labelText: 'Bill this delivery note',
                  helperText: 'Only notes with something left to bill.',
                  helperMaxLines: 2,
                ),
                items: [
                  for (final BillableDocument item in _pickable)
                    DropdownMenuItem(
                      value: item.sourceDocumentId,
                      child: Text(item.label, overflow: TextOverflow.ellipsis),
                    ),
                ],
                validator: (value) =>
                    value == null ? 'Choose a delivery note.' : null,
                // Fixed while editing: changing which document a draft bills
                // is raising a different invoice, not correcting this one.
                onChanged: _editing
                    ? null
                    : (value) => setState(() {
                          final Iterable<BillableDocument> found = _billable
                              .where((item) => item.sourceDocumentId == value);
                          if (found.isNotEmpty) _choose(found.first);
                        }),
              ),
              const SizedBox(height: AppSpacing.md),
              if (_document != null) ...[
                for (final BillableLine line in _document!.lines)
                  _lineRow(line, theme),
                const SizedBox(height: AppSpacing.md),
                TextFormField(
                  controller: _billDiscount,
                  decoration: const InputDecoration(
                    labelText: 'Discount on the whole bill %',
                    helperText: 'Comes off what the lines discounted to, and '
                        'the tax falls with it.',
                    helperMaxLines: 2,
                  ),
                  keyboardType: TextInputType.number,
                  validator: _percentage,
                  onChanged: (_) => setState(() {}),
                ),
                TextFormField(
                  controller: _reference,
                  decoration: const InputDecoration(
                    labelText: "Customer's reference",
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  'Billed before tax: ${_beforeTax.toStringAsFixed(2)}. Tax is '
                  'worked out by the server at the rate in force.',
                  style: theme.textTheme.bodySmall,
                ),
              ],
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.md),
                  child: Text(
                    _error!,
                    style: TextStyle(color: theme.colorScheme.error),
                  ),
                ),
            ],
          ),
        ),
      );

  Widget _lineRow(BillableLine line, ThemeData theme) => Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.sm),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              flex: 3,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(line.label),
                  Text(
                    'dispatched ${line.sourceQuantity}'
                    '${line.alreadyInvoicedQuantity == '0' || line.alreadyInvoicedQuantity.isEmpty ? '' : ', already billed ${line.alreadyInvoicedQuantity}'}'
                    ' · at ${line.unitPrice}'
                    '${(double.tryParse(line.discountPercent) ?? 0) > 0 ? ' less ${line.discountPercent}%' : ''}',
                    style: theme.textTheme.bodySmall,
                  ),
                ],
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: TextFormField(
                controller: _quantities[line.sourceDocumentLineId],
                decoration: const InputDecoration(
                  labelText: 'Bill',
                  isDense: true,
                ),
                keyboardType: TextInputType.number,
                validator: (value) => _billableQuantity(value, line),
                onChanged: (_) => setState(() {}),
              ),
            ),
          ],
        ),
      );

  /// A quantity the server would refuse, caught before the round trip.
  String? _billableQuantity(String? value, BillableLine line) {
    final String text = (value ?? '').trim();
    if (text.isEmpty) return null;
    final double? parsed = double.tryParse(text);
    if (parsed == null) return 'Enter a quantity.';
    if (parsed < 0) return 'Cannot be negative.';
    final double remaining = double.tryParse(line.remainingQuantity) ?? 0;
    // The goods left on somebody else's document; billing more than went out
    // is a bill the warehouse cannot reconcile.
    if (parsed > remaining) return 'Only $remaining left to bill.';
    return null;
  }

  String? _percentage(String? value) {
    final String text = (value ?? '').trim();
    if (text.isEmpty) return null;
    final double? parsed = double.tryParse(text);
    if (parsed == null) return 'Enter a percentage.';
    if (parsed < 0 || parsed > 100) return 'Between 0 and 100.';
    return null;
  }
}


/// One line of a bill raised without any paperwork behind it.
class _DirectLine {
  String? productId;
  final TextEditingController quantity = TextEditingController();
  final TextEditingController price = TextEditingController();
  final TextEditingController discount = TextEditingController();
}
