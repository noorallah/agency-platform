import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
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
  });

  final ApiClient api;

  /// Passed in rather than read here, so the dialog is testable.
  final DateTime today;

  @override
  State<SalesInvoiceEditorDialog> createState() =>
      _SalesInvoiceEditorDialogState();
}

class _SalesInvoiceEditorDialogState extends State<SalesInvoiceEditorDialog> {
  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  final TextEditingController _reference = TextEditingController();
  final TextEditingController _billDiscount = TextEditingController();
  final Map<String, TextEditingController> _quantities =
      <String, TextEditingController>{};

  List<BillableDocument> _billable = const [];
  BillableDocument? _document;
  bool _loading = true;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _reference.dispose();
    _billDiscount.dispose();
    for (final TextEditingController controller in _quantities.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final List<BillableDocument> rows =
          await widget.api.billableDocuments();
      if (!mounted) return;
      setState(() {
        _billable = rows;
        _loading = false;
        if (rows.length == 1) _choose(rows.first);
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
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

  String _iso(DateTime value) => value.toIso8601String().split('T').first;

  Json? _payload() {
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
      await widget.api.createSalesInvoice(payload);
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
      title: const Text('New Invoice'),
      content: SizedBox(
        width: 720,
        child: _loading
            ? const Center(
                child: Padding(
                  padding: EdgeInsets.all(32),
                  child: CircularProgressIndicator(),
                ),
              )
            : _billable.isEmpty
                ? const WorkspaceEmptyState(
                    title: 'Nothing is waiting to be billed',
                    message: 'Dispatch a delivery note and it appears here. '
                        'A note that has already been invoiced in full does '
                        'not.',
                  )
                : _form_(theme),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _saving || _billable.isEmpty ? null : _save,
          child: Text(_saving ? 'Saving…' : 'Create draft'),
        ),
      ],
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
                  for (final BillableDocument item in _billable)
                    DropdownMenuItem(
                      value: item.sourceDocumentId,
                      child: Text(item.label, overflow: TextOverflow.ellipsis),
                    ),
                ],
                validator: (value) =>
                    value == null ? 'Choose a delivery note.' : null,
                onChanged: (value) => setState(() {
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
