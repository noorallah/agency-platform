import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../../models/branch_warehouse.dart';
import '../../models/customer.dart';
import '../../models/entities.dart';
import '../../models/product.dart';
import '../../models/quotation.dart';
import '../workspace/desktop_framework.dart';

/// One line of the offer, while it is being typed.
///
/// The controllers belong to the draft rather than to the state, because a line
/// removed from the middle of the list has to take its own text with it —
/// keeping three parallel lists of controllers is how a deleted row leaves the
/// quantity of the row below it behind.
class _LineDraft {
  _LineDraft({
    required this.productId,
    String quantity = '1',
    String unitPrice = '0',
    String discount = '0',
    String free = '',
  })  : quantity = TextEditingController(text: quantity),
        unitPrice = TextEditingController(text: unitPrice),
        discount = TextEditingController(text: discount),
        free = TextEditingController(text: free);

  String? productId;
  final TextEditingController quantity;
  final TextEditingController unitPrice;
  final TextEditingController discount;

  /// Goods thrown in with this line. Charged for at nothing, so it never
  /// enters the line's value -- but stock moves for it, and the bill says so.
  final TextEditingController free;

  /// True once somebody typed in the discount box.
  ///
  /// A line nobody has touched follows whichever customer is chosen; one that
  /// has been typed into does not, because refilling it would overwrite a
  /// price the salesman had just agreed.
  bool discountEdited = false;

  /// Fill the box from the customer's standing rate, unless it was typed into.
  void followCustomer(String percent) {
    if (discountEdited) return;
    discount.text = percent;
  }

  double get _quantity => double.tryParse(quantity.text.trim()) ?? 0;
  double get _price => double.tryParse(unitPrice.text.trim()) ?? 0;
  double get _discount => double.tryParse(discount.text.trim()) ?? 0;

  /// What this line adds to the offer, before tax.
  double get netOfDiscount => _quantity * _price * (1 - _discount / 100);

  void dispose() {
    quantity.dispose();
    unitPrice.dispose();
    discount.dispose();
    free.dispose();
  }
}

/// Writing an offer.
///
/// The one field a quotation has that an order does not is how long the prices
/// stand for, so it is not buried among the terms: an offer with no end date is
/// one the firm is still bound by next year.
///
/// The backend takes up to 1,000 lines and this form wrote exactly one, so a
/// quotation for more than a single product could not be raised from the
/// desktop at all — the customer was quoted per item, or somebody went to the
/// API. Lines are added and removed here now.
class QuotationEditorDialog extends StatefulWidget {
  const QuotationEditorDialog({
    super.key,
    required this.customers,
    required this.products,
    required this.branches,
    required this.warehouses,
    required this.today,
    this.existing,
  });

  final List<Customer> customers;
  final List<Product> products;
  final List<BranchRecord> branches;
  final List<WarehouseRecord> warehouses;

  /// Passed in rather than read here, so the dialog is testable.
  final DateTime today;

  /// The quotation being revised, if this is a revision rather than a new one.
  final Quotation? existing;

  @override
  State<QuotationEditorDialog> createState() => _QuotationEditorDialogState();
}

class _QuotationEditorDialogState extends State<QuotationEditorDialog> {
  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  final TextEditingController _reference = TextEditingController();
  final TextEditingController _paymentTerms = TextEditingController();
  final TextEditingController _deliveryTerms = TextEditingController();
  final TextEditingController _remarks = TextEditingController();
  final List<_LineDraft> _lines = <_LineDraft>[];

  /// A discount on the whole offer, as a percentage. It comes off what
  /// the lines already discounted to, and the server splits it across
  /// them so the tax falls with it.
  final TextEditingController _billDiscount = TextEditingController();

  String? _customerId;
  String? _branchId;
  String? _warehouseId;
  late DateTime _validUntil;

  @override
  void initState() {
    super.initState();
    // Thirty days is the ordinary term and the only defensible default; the
    // alternative is an empty field somebody has to fill in every time.
    _validUntil = widget.today.add(const Duration(days: 30));
    final Quotation? existing = widget.existing;
    _customerId = existing?.customerId ??
        (widget.customers.isEmpty ? null : widget.customers.first.id);
    _branchId = existing?.branchId ??
        (widget.branches.isEmpty ? null : widget.branches.first.id);
    _warehouseId = existing?.warehouseId ??
        (widget.warehouses.isEmpty ? null : widget.warehouses.first.id);
    if (existing != null) {
      _reference.text = existing.customerReference;
      _paymentTerms.text = existing.paymentTerms;
      _deliveryTerms.text = existing.deliveryTerms;
      _remarks.text = existing.remarks;
      _validUntil = DateTime.tryParse(existing.validUntil) ?? _validUntil;
      // Blank rather than '0' where there was none, so the box reads as empty
      // and the payload omits it.
      _billDiscount.text = (double.tryParse(existing.billDiscountPercent) ?? 0) > 0
          ? existing.billDiscountPercent
          : '';
      // Every line, in the order the document holds them. Taking only the
      // first is what made a revision quietly delete the rest of the offer:
      // the update replaces the whole collection with what is sent.
      for (final QuotationLine line in existing.lines) {
        // What the document holds counts as typed: a revision must not have
        // its agreed rates rewritten because the customer master moved.
        _lines.add(_LineDraft(
          productId: line.productId,
          quantity: line.quantity,
          unitPrice: line.unitPrice,
          discount: line.discountPercent,
          free: (double.tryParse(line.freeQuantity) ?? 0) > 0
              ? line.freeQuantity
              : '',
        )..discountEdited = true);
      }
    }
    if (_lines.isEmpty) _lines.add(_newLine());
  }

  /// A fresh line, defaulted to the first product so the row is savable as it
  /// stands rather than starting invalid.
  _LineDraft _newLine() => _LineDraft(
        productId: widget.products.isEmpty ? null : widget.products.first.id,
        discount: _customerDiscount,
      );

  /// The chosen customer's standing discount, as the box should read.
  ///
  /// Shown rather than left blank and filled in by the server: the number on
  /// screen is what the customer is being quoted, and a salesman who cannot
  /// see the discount cannot tell that it applied.
  String get _customerDiscount {
    for (final Customer item in widget.customers) {
      if (item.id == _customerId) {
        final double rate =
            double.tryParse(item.defaultDiscountPercent.trim()) ?? 0;
        return rate <= 0 ? '0' : item.defaultDiscountPercent.trim();
      }
    }
    return '0';
  }

  /// Move every untouched line onto the newly chosen customer's rate.
  void _chooseCustomer(String? value) {
    setState(() {
      _customerId = value;
      final String percent = _customerDiscount;
      for (final _LineDraft line in _lines) {
        line.followCustomer(percent);
      }
    });
  }

  @override
  void dispose() {
    for (final _LineDraft line in _lines) {
      line.dispose();
    }
    _billDiscount.dispose();
    _reference.dispose();
    _paymentTerms.dispose();
    _deliveryTerms.dispose();
    _remarks.dispose();
    super.dispose();
  }

  /// What the customer would be quoted before tax, across every line. Shown as
  /// it is typed, because a price list nobody can total is one somebody totals
  /// by hand.
  /// What the offer comes to before tax, after both discounts.
  double get _quotedBeforeTax {
    final double lines = _netOfDiscount;
    final double rate = double.tryParse(_billDiscount.text.trim()) ?? 0;
    if (rate <= 0) return lines;
    return lines * (1 - rate / 100);
  }

  double get _netOfDiscount => _lines.fold<double>(
        0,
        (double running, _LineDraft line) => running + line.netOfDiscount,
      );

  String? _positive(String? value, String what) {
    final double parsed = double.tryParse((value ?? '').trim()) ?? -1;
    if (parsed <= 0) return 'Enter the $what.';
    return null;
  }

  void _addLine() => setState(() => _lines.add(_newLine()));

  void _removeLine(int index) {
    // A quotation with no lines is not an offer, and the server refuses one,
    // so the last row cannot be taken away — the way to abandon a quotation is
    // to cancel the dialog.
    if (_lines.length <= 1) return;
    setState(() => _lines.removeAt(index).dispose());
  }

  Future<void> _pickValidUntil() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _validUntil,
      firstDate: widget.today,
      lastDate: widget.today.add(const Duration(days: 730)),
      helpText: 'These prices stand until',
    );
    if (picked != null) setState(() => _validUntil = picked);
  }

  /// Goods given away cannot be a negative number of goods.
  String? _freeQuantity(String? value) {
    final String text = (value ?? '').trim();
    if (text.isEmpty) return null;
    final double? parsed = double.tryParse(text);
    if (parsed == null) return 'Enter a quantity.';
    if (parsed < 0) return 'Cannot be negative.';
    return null;
  }

  /// A rate the server would refuse, caught before the round trip.
  String? _percentage(String? value) {
    final String text = (value ?? '').trim();
    if (text.isEmpty) return null;
    final double? parsed = double.tryParse(text);
    if (parsed == null) return 'Enter a percentage.';
    if (parsed < 0 || parsed > 100) return 'Between 0 and 100.';
    return null;
  }

  String _iso(DateTime value) => value.toIso8601String().split('T').first;

  Json? _payload() {
    if (!(_form.currentState?.validate() ?? false)) return null;
    if (_customerId == null) return null;
    if (_branchId == null || _warehouseId == null) return null;
    if (_lines.any((_LineDraft line) => line.productId == null)) return null;
    return <String, dynamic>{
      'customer_id': _customerId,
      'branch_id': _branchId,
      'warehouse_id': _warehouseId,
      'quotation_date': _iso(widget.today),
      'valid_until': _iso(_validUntil),
      if (_reference.text.trim().isNotEmpty)
        'customer_reference': _reference.text.trim(),
      if (_paymentTerms.text.trim().isNotEmpty)
        'payment_terms': _paymentTerms.text.trim(),
      if (_deliveryTerms.text.trim().isNotEmpty)
        'delivery_terms': _deliveryTerms.text.trim(),
      if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
      // Omitted when blank: the server reads absent as "no discount on the
      // bill" and would refuse an empty string.
      if (_billDiscount.text.trim().isNotEmpty)
        'bill_discount_percent': _billDiscount.text.trim(),
      'lines': [
        for (int index = 0; index < _lines.length; index += 1)
          <String, dynamic>{
            'line_number': index + 1,
            'product_id': _lines[index].productId,
            'quantity': _lines[index].quantity.text.trim(),
            'unit_price': _lines[index].unitPrice.text.trim(),
            // Omitted rather than sent blank when nobody typed: absent is
            // what tells the server to apply the customer's standing rate,
            // and an empty string is a schema error.
            if (_lines[index].discount.text.trim().isNotEmpty)
              'discount_percent': _lines[index].discount.text.trim(),
            if (_lines[index].free.text.trim().isNotEmpty)
              'free_quantity': _lines[index].free.text.trim(),
          },
      ],
    };
  }

  /// One line's row of controls.
  ///
  /// Each line carries its own running total, because the offer's total alone
  /// does not say which of five lines was mistyped.
  Widget _lineEditor(int index) {
    final _LineDraft line = _lines[index];
    final bool removable = _lines.length > 1;
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            Expanded(
              child: DropdownButtonFormField<String>(
                key: ValueKey<String>('quotation-line-product-$index'),
                initialValue: line.productId,
                decoration: InputDecoration(labelText: 'Product ${index + 1}'),
                items: [
                  for (final Product item in widget.products)
                    DropdownMenuItem(
                      value: item.id,
                      child: Text('${item.code}  ${item.name}',
                          overflow: TextOverflow.ellipsis),
                    ),
                ],
                validator: (value) =>
                    value == null ? 'Choose a product.' : null,
                onChanged: (value) => setState(() => line.productId = value),
              ),
            ),
            IconButton(
              onPressed: removable ? () => _removeLine(index) : null,
              icon: const Icon(Icons.close, size: 18),
              tooltip: removable
                  ? 'Remove this line'
                  : 'A quotation needs at least one line',
            ),
          ]),
          const SizedBox(height: AppSpacing.sm),
          Row(children: [
            Expanded(
              child: TextFormField(
                controller: line.quantity,
                decoration: const InputDecoration(labelText: 'Quantity'),
                keyboardType: TextInputType.number,
                validator: (value) => _positive(value, 'quantity'),
                onChanged: (_) => setState(() {}),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: TextFormField(
                controller: line.unitPrice,
                decoration: const InputDecoration(labelText: 'Unit price'),
                keyboardType: TextInputType.number,
                validator: (value) => _positive(value, 'price'),
                onChanged: (_) => setState(() {}),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: TextFormField(
                controller: line.free,
                decoration: const InputDecoration(labelText: 'Free'),
                keyboardType: TextInputType.number,
                validator: _freeQuantity,
                onChanged: (_) => setState(() {}),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: TextFormField(
                controller: line.discount,
                decoration: InputDecoration(
                  labelText: 'Discount %',
                  helperText: line.discountEdited || _customerDiscount == '0'
                      ? null
                      : "$_customerDiscount% is this customer's rate",
                ),
                keyboardType: TextInputType.number,
                validator: _percentage,
                // onChanged fires only for typing, never for the programmatic
                // fill above, which is what makes the two distinguishable.
                onChanged: (_) => setState(() => line.discountEdited = true),
              ),
            ),
          ]),
          const SizedBox(height: AppSpacing.xs),
          Align(
            alignment: Alignment.centerRight,
            child: Text(
              'Line ${index + 1}: ${line.netOfDiscount.toStringAsFixed(2)}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bool revising = widget.existing != null;
    return WorkspaceDialog(
      title: revising
          ? 'Revise ${widget.existing!.quotationNumber}'
          : 'New quotation',
      saveLabel: revising ? 'Save revision' : 'Create draft',
      onSave: () {
        final Json? payload = _payload();
        if (payload != null) Navigator.of(context).pop(payload);
      },
      body: widget.customers.isEmpty || widget.products.isEmpty
          ? const StandardEmptyState(
              type: EmptyStateType.noRecords,
              title: 'Nothing to quote yet',
              message: 'A quotation needs a customer to send it to and a '
                  'product to price.',
            )
          : Form(
              key: _form,
              child: SingleChildScrollView(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    DropdownButtonFormField<String>(
                      initialValue: _customerId,
                      decoration: const InputDecoration(labelText: 'Customer'),
                      items: [
                        for (final Customer item in widget.customers)
                          DropdownMenuItem(
                            value: item.id,
                            child: Text(item.displayName,
                                overflow: TextOverflow.ellipsis),
                          ),
                      ],
                      validator: (value) =>
                          value == null ? 'Choose a customer.' : null,
                      onChanged: _chooseCustomer,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    // The offer's end date, given its own row rather than
                    // filed under terms: a quotation with no expiry is one the
                    // firm is still bound by a year later.
                    InputDecorator(
                      decoration: const InputDecoration(
                        labelText: 'These prices stand until',
                        helperText: 'Past this date it cannot become an order.',
                      ),
                      child: Row(children: [
                        Expanded(child: Text(_iso(_validUntil))),
                        TextButton.icon(
                          onPressed: _pickValidUntil,
                          icon: const Icon(Icons.event, size: 18),
                          label: const Text('Change'),
                        ),
                      ]),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    for (int index = 0; index < _lines.length; index += 1)
                      _lineEditor(index),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton.icon(
                        onPressed: _addLine,
                        icon: const Icon(Icons.add, size: 18),
                        label: const Text('Add line'),
                      ),
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    // Sits under the lines and above the total, because it is
                    // a deal struck on the whole offer rather than a property
                    // of any one line.
                    TextFormField(
                      controller: _billDiscount,
                      decoration: const InputDecoration(
                        labelText: 'Discount on the whole offer %',
                        helperText: 'Comes off what the lines discounted to, '
                            'and the tax falls with it.',
                      ),
                      keyboardType: TextInputType.number,
                      validator: _percentage,
                      onChanged: (_) => setState(() {}),
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    Text(
                      'Quoted before tax: '
                      '${_quotedBeforeTax.toStringAsFixed(2)}. Tax is worked '
                      'out by the server at the rate in force.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    Row(children: [
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          initialValue: _branchId,
                          decoration:
                              const InputDecoration(labelText: 'Branch'),
                          items: [
                            for (final BranchRecord item in widget.branches)
                              DropdownMenuItem(
                                value: item.id,
                                child: Text(item.displayName,
                                    overflow: TextOverflow.ellipsis),
                              ),
                          ],
                          validator: (value) =>
                              value == null ? 'Choose a branch.' : null,
                          onChanged: (value) =>
                              setState(() => _branchId = value),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          initialValue: _warehouseId,
                          decoration: const InputDecoration(
                            labelText: 'Ships from',
                            helperText: 'Nothing is reserved from it.',
                          ),
                          items: [
                            for (final WarehouseRecord item
                                in widget.warehouses)
                              DropdownMenuItem(
                                value: item.id,
                                child: Text(item.displayName,
                                    overflow: TextOverflow.ellipsis),
                              ),
                          ],
                          validator: (value) =>
                              value == null ? 'Choose a warehouse.' : null,
                          onChanged: (value) =>
                              setState(() => _warehouseId = value),
                        ),
                      ),
                    ]),
                    const SizedBox(height: AppSpacing.md),
                    Row(children: [
                      Expanded(
                        child: TextFormField(
                          controller: _paymentTerms,
                          decoration: const InputDecoration(
                              labelText: 'Payment terms'),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: TextFormField(
                          controller: _deliveryTerms,
                          decoration: const InputDecoration(
                              labelText: 'Delivery terms'),
                        ),
                      ),
                    ]),
                    const SizedBox(height: AppSpacing.md),
                    TextFormField(
                      controller: _reference,
                      decoration: const InputDecoration(
                        labelText: 'Customer’s reference',
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    TextFormField(
                      controller: _remarks,
                      decoration: const InputDecoration(labelText: 'Remarks'),
                      maxLines: 2,
                    ),
                  ],
                ),
              ),
            ),
    );
  }
}
