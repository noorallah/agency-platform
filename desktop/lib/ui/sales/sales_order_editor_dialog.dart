import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/design/design_tokens.dart';
import '../../models/branch_warehouse.dart';
import '../../models/customer.dart';
import '../../models/entities.dart';
import '../../models/firm_member.dart';
import '../../models/product.dart';
import '../workspace/desktop_framework.dart';

/// One line of the order, while it is being typed.
///
/// The controllers belong to the draft rather than to the state, because a
/// line removed from the middle of the list has to take its own text with it
/// -- parallel lists of controllers are how a deleted row leaves the quantity
/// of the row below it behind.
class _LineDraft {
  _LineDraft({
    required this.productId,
    String quantity = '1',
    String unitPrice = '0',
    String free = '',
    String discountPercent = '',
    String discountAmount = '',
  })  : quantity = TextEditingController(text: quantity),
        unitPrice = TextEditingController(text: unitPrice),
        free = TextEditingController(text: free),
        discountPercent = TextEditingController(text: discountPercent),
        discountAmount = TextEditingController(text: discountAmount);

  String? productId;
  final TextEditingController quantity;
  final TextEditingController unitPrice;

  /// Goods thrown in with this line. Charged for at nothing, so it never
  /// enters the line's value -- but stock moves for it, and the order says so.
  final TextEditingController free;

  /// Left blank on a new line **on purpose**. Blank is omitted from the
  /// payload, and absent is what lets the server apply the more specific
  /// arrangement it knows about: the firm's price list for this customer and
  /// product first, the customer's blanket rate after it. A typed zero is an
  /// instruction -- "not this time" -- and is sent as zero.
  final TextEditingController discountPercent;

  /// A flat figure off this line, which beats the percentage when both are
  /// given. Same rule: blank says nothing, zero refuses.
  final TextEditingController discountAmount;

  /// True once somebody typed a price.
  ///
  /// A line nobody has priced follows whichever product is chosen; one that
  /// has been typed into does not, because refilling it would overwrite a
  /// price the salesman had just agreed.
  bool priceEdited = false;

  /// Fill the price from the product's own, unless it was typed into.
  void followProduct(String price) {
    if (priceEdited) return;
    unitPrice.text = price;
  }

  double get _quantity => double.tryParse(quantity.text.trim()) ?? 0;
  double get _price => double.tryParse(unitPrice.text.trim()) ?? 0;

  /// What this line is worth before any discount. Free goods are outside it
  /// everywhere on this platform, so they are never discounted either.
  double get gross => _quantity * _price;

  /// What this line adds to the order, before tax and before any discount on
  /// the whole document. An amount beats a percentage, as it does on the
  /// server.
  double get netOfDiscount {
    final double amount = double.tryParse(discountAmount.text.trim()) ?? -1;
    if (amount >= 0) return gross - amount;
    final double percent = double.tryParse(discountPercent.text.trim()) ?? 0;
    return gross * (1 - percent / 100);
  }

  void dispose() {
    quantity.dispose();
    unitPrice.dispose();
    free.dispose();
    discountPercent.dispose();
    discountAmount.dispose();
  }
}

/// Taking an order.
///
/// A sales order could only appear here by converting a quotation, so a phone
/// order had to be typed as an offer and accepted in the same breath -- two
/// documents, and an acceptance the customer never gave. `POST
/// /api/v1/sales-orders` had worked all along with nothing on the desktop
/// calling it.
///
/// It loads its own pickers rather than being handed them, so the management
/// page needs to know nothing but the id of the order to open.
class SalesOrderEditorDialog extends StatefulWidget {
  const SalesOrderEditorDialog({
    super.key,
    required this.api,
    required this.today,
    this.orderId,
  });

  final ApiClient api;

  /// Passed in rather than read here, so the dialog is testable.
  final DateTime today;

  /// The draft being corrected, or null to take a new order.
  ///
  /// Only a draft can be corrected -- the server refuses anything else,
  /// because an approved order has committed credit and a delivered one has
  /// moved stock.
  final String? orderId;

  @override
  State<SalesOrderEditorDialog> createState() => _SalesOrderEditorDialogState();
}

class _SalesOrderEditorDialogState extends State<SalesOrderEditorDialog> {
  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  final TextEditingController _customerReference = TextEditingController();
  final TextEditingController _reference = TextEditingController();
  final TextEditingController _remarks = TextEditingController();

  /// A deal struck on the whole order. The server takes it off what the lines
  /// discounted to and splits it back across them, so the tax falls with it.
  final TextEditingController _billDiscountPercent = TextEditingController();
  final TextEditingController _billDiscountAmount = TextEditingController();

  final List<_LineDraft> _lines = <_LineDraft>[];

  List<Customer> _customers = const [];
  List<Product> _products = const [];
  List<BranchRecord> _branches = const [];
  List<WarehouseRecord> _warehouses = const [];

  String? _customerId;

  /// Who took the order.
  ///
  /// Optional on the API and optional here, but what a blank costs is worth
  /// saying, so the field carries its own helper. Two things make the honest
  /// sentence longer than it looks: where the customer is on a round, the
  /// server derives that round's salesman for a document that names none
  /// (`_derived_salesman` in `app/sales/services/scope_resolution.py`), so a
  /// blank is not automatically nobody -- and where they are not, the money
  /// this order collects lands in the commission report's Unassigned bucket,
  /// which belongs to nobody and pays nobody.
  ///
  /// The picker offers every member of the firm and does not filter by who
  /// covers the customer's round. The server refuses a salesman who does not,
  /// in a sentence that names the reason; filtering here would need the
  /// customer's assignments on every keystroke and would still have to trust
  /// that refusal.
  String? _salesmanId;
  List<FirmMember> _members = const <FirmMember>[];
  String? _branchId;
  String? _warehouseId;
  late DateTime _orderDate;
  DateTime? _deliveryDate;

  bool _loading = true;
  bool _saving = false;
  String? _error;

  /// The version the order was read at, sent back as `If-Match`. The update
  /// replaces the whole line collection, so a lost race costs every line
  /// somebody entered rather than a single field.
  int _version = 0;

  /// The order's status as it was read. Only a draft may be rewritten.
  String _status = 'DRAFT';

  bool get _editing => widget.orderId != null;

  bool get _locked => _editing && _status != 'DRAFT';

  @override
  void initState() {
    super.initState();
    _orderDate = widget.today;
    _load();
  }

  @override
  void dispose() {
    for (final _LineDraft line in _lines) {
      line.dispose();
    }
    _customerReference.dispose();
    _reference.dispose();
    _remarks.dispose();
    _billDiscountPercent.dispose();
    _billDiscountAmount.dispose();
    super.dispose();
  }

  /// Read the pickers and, when correcting one, the order itself.
  ///
  /// Every picker is paged through rather than asked for in one large page:
  /// `MAX_PAGE_SIZE` is 100 and a request above it is refused rather than
  /// clamped, which surfaces as a 500 on some routers.
  Future<void> _load() async {
    try {
      final List<dynamic> loaded = await Future.wait<dynamic>(<Future<dynamic>>[
        fetchAllPages<Customer>((int page) =>
            widget.api.customers(page: page, pageSize: maxApiPageSize)),
        fetchAllPages<Product>((int page) =>
            widget.api.products(page: page, pageSize: maxApiPageSize)),
        fetchAllPages<BranchRecord>((int page) =>
            widget.api.branches(page: page, pageSize: maxApiPageSize)),
        fetchAllPages<WarehouseRecord>((int page) =>
            widget.api.warehouses(page: page, pageSize: maxApiPageSize)),
        // Not paged: one firm's people, and the endpoint answers them all.
        widget.api.firmMembers(),
      ]);
      final String? id = widget.orderId;
      final Json? existing =
          id == null ? null : _unwrap(await widget.api.salesOrder(id));
      if (!mounted) return;
      setState(() {
        _customers = (loaded[0] as List<dynamic>).cast<Customer>();
        _products = (loaded[1] as List<dynamic>).cast<Product>();
        _branches = (loaded[2] as List<dynamic>).cast<BranchRecord>();
        _warehouses = (loaded[3] as List<dynamic>).cast<WarehouseRecord>();
        _members = (loaded[4] as List<dynamic>).cast<FirmMember>();
        _loading = false;
        if (existing != null) {
          _adoptExisting(existing);
        } else {
          // The branch and the warehouse are nearly always the same ones, and
          // the firm says which. The customer is left unchosen: it is the
          // point of the document, and defaulting it means an order can be
          // raised for the wrong shop by not touching the field.
          _branchId = _defaultOf<BranchRecord>(
              _branches, (BranchRecord item) => item.isDefault, (item) => item.id);
          _warehouseId = _defaultOf<WarehouseRecord>(_warehouses,
              (WarehouseRecord item) => item.isDefault, (item) => item.id);
        }
        if (_lines.isEmpty) _lines.add(_newLine());
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  /// The one the firm marked as its default, or the first, or none at all.
  String? _defaultOf<T>(
    List<T> rows,
    bool Function(T) isDefault,
    String Function(T) idOf,
  ) {
    if (rows.isEmpty) return null;
    for (final T row in rows) {
      if (isDefault(row)) return idOf(row);
    }
    return idOf(rows.first);
  }

  Json _unwrap(Json response) {
    final dynamic data = response['data'];
    return data is Map ? Map<String, dynamic>.from(data) : response;
  }

  /// Build the form from an order that already exists.
  ///
  /// Everything comes off the document rather than off the masters: an order
  /// records what was agreed on the day it was taken, and re-reading a price
  /// or a discount out of the customer master would rewrite it.
  void _adoptExisting(Json order) {
    _version = (order['version'] as num?)?.toInt() ?? 0;
    _status = stringValue(order['status']).isEmpty
        ? 'DRAFT'
        : stringValue(order['status']);
    _customerId = _blankToNull(stringValue(order['customer_id']));
    _salesmanId = _blankToNull(stringValue(order['salesman_id']));
    _branchId = _blankToNull(stringValue(order['branch_id']));
    _warehouseId = _blankToNull(stringValue(order['warehouse_id']));
    _orderDate = DateTime.tryParse(stringValue(order['order_date'])) ?? _orderDate;
    _deliveryDate = DateTime.tryParse(stringValue(order['delivery_date']));
    _customerReference.text = stringValue(order['customer_reference']);
    _reference.text = stringValue(order['reference_number']);
    _remarks.text = stringValue(order['remarks']);
    // Blank rather than '0' where there was none, so the box reads as empty
    // and the payload omits it.
    _billDiscountPercent.text = _positiveOrBlank(order['bill_discount_percent']);
    _billDiscountAmount.text = _positiveOrBlank(order['bill_discount_amount']);

    final List<dynamic> lines =
        order['lines'] is List ? order['lines'] as List : const [];
    for (final dynamic raw in lines) {
      final Json line = Map<String, dynamic>.from(raw as Map);
      _lines.add(_LineDraft(
        productId: _blankToNull(stringValue(line['product_id'])),
        quantity: stringValue(line['quantity']),
        unitPrice: stringValue(line['unit_price']),
        free: _positiveOrBlank(line['free_quantity']),
        // The stored rate is echoed **including a zero**, because the document
        // is the record of what was agreed. Sending nothing instead would let
        // a price list or a standing rate introduced since apply to a line
        // that was priced without one.
        //
        // Only the rate: the amount stored beside it is the same deduction
        // expressed as currency, and a flat amount wins over a rate, so
        // sending both would pin the discount to a figure that no longer
        // matches once somebody edits the quantity.
        discountPercent: stringValue(line['discount_percent']),
      )..priceEdited = true);
    }
  }

  String? _blankToNull(String value) => value.isEmpty ? null : value;

  /// A stored figure as the box should read it: blank when it is nothing.
  String _positiveOrBlank(dynamic value) {
    final String text = stringValue(value);
    return (double.tryParse(text) ?? 0) > 0 ? text : '';
  }

  /// What a product sells for, as the price box should read.
  ///
  /// Shown rather than applied silently on the server, because a price is the
  /// central term of a sale -- a document that says nothing about it is
  /// incomplete, not one that means "the usual". The API requires an explicit
  /// price for the same reason.
  String _priceOf(String? productId) {
    for (final Product item in _products) {
      if (item.id != productId) continue;
      final double price = double.tryParse(item.sellingPrice.trim()) ?? 0;
      return price > 0 ? item.sellingPrice.trim() : '0';
    }
    return '0';
  }

  /// What the product lists at, where that is worth saying.
  ///
  /// Silent once somebody has typed: the number on screen is then theirs, and
  /// repeating the list price beside it reads as a correction.
  String? _priceHelper(_LineDraft line) {
    if (line.priceEdited) return null;
    for (final Product item in _products) {
      if (item.id != line.productId) continue;
      final double mrp = double.tryParse(item.mrp.trim()) ?? 0;
      final double price = double.tryParse(item.sellingPrice.trim()) ?? 0;
      if (price <= 0) return null;
      return mrp > 0 ? 'lists at ${item.sellingPrice}, MRP ${item.mrp}' : null;
    }
    return null;
  }

  /// Move an unpriced line onto the newly chosen product's price.
  void _chooseProduct(_LineDraft line, String? productId) {
    setState(() {
      line.productId = productId;
      line.followProduct(_priceOf(productId));
    });
  }

  /// A fresh line, defaulted to the first product so the row is savable as it
  /// stands rather than starting invalid.
  _LineDraft _newLine() {
    final String? productId = _products.isEmpty ? null : _products.first.id;
    return _LineDraft(productId: productId, unitPrice: _priceOf(productId));
  }

  void _addLine() => setState(() => _lines.add(_newLine()));

  void _removeLine(int index) {
    // An order with no lines is not an order, and the server refuses one, so
    // the last row cannot be taken away -- the way to abandon it is Cancel.
    if (_lines.length <= 1) return;
    setState(() => _lines.removeAt(index).dispose());
  }

  /// The chosen customer's standing discount, or an empty string where there
  /// is none. Said on screen rather than filled into the boxes: filling it
  /// would turn an inherited rate into an explicit one, and an explicit rate
  /// outranks the firm's price list for this customer and product.
  String get _customerDiscount {
    for (final Customer item in _customers) {
      if (item.id != _customerId) continue;
      final double rate =
          double.tryParse(item.defaultDiscountPercent.trim()) ?? 0;
      return rate > 0 ? item.defaultDiscountPercent.trim() : '';
    }
    return '';
  }

  /// What the order comes to before tax, after both discounts.
  double get _beforeTax {
    final double lines = _lines.fold<double>(
      0,
      (double running, _LineDraft line) => running + line.netOfDiscount,
    );
    final double amount =
        double.tryParse(_billDiscountAmount.text.trim()) ?? -1;
    if (amount >= 0) return lines - amount;
    final double percent =
        double.tryParse(_billDiscountPercent.text.trim()) ?? 0;
    return percent <= 0 ? lines : lines * (1 - percent / 100);
  }

  String _iso(DateTime value) => value.toIso8601String().split('T').first;

  String? _positive(String? value, String what) {
    final double parsed = double.tryParse((value ?? '').trim()) ?? -1;
    if (parsed <= 0) return 'Enter the $what.';
    return null;
  }

  /// A quantity given away cannot be a negative number of goods.
  String? _quantityOrBlank(String? value) {
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

  /// A discount above what it comes off is refused by the server, because it
  /// produces a negative taxable value.
  String? _discountAmount(String? value, double ceiling, String subject) {
    final String text = (value ?? '').trim();
    if (text.isEmpty) return null;
    final double? parsed = double.tryParse(text);
    if (parsed == null) return 'Enter an amount.';
    if (parsed < 0) return 'Cannot be negative.';
    if (parsed > ceiling) return 'More than $subject comes to.';
    return null;
  }

  Json? _payload() {
    if (!(_form.currentState?.validate() ?? false)) return null;
    if (_customerId == null || _branchId == null || _warehouseId == null) {
      return null;
    }
    if (_lines.any((_LineDraft line) => line.productId == null)) return null;
    final DateTime? delivery = _deliveryDate;
    return <String, dynamic>{
      'customer_id': _customerId,
      // Omitted when nobody was named rather than sent null: absent is what
      // the create schema reads as "no salesman", and this form has no reason
      // to distinguish that from clearing one.
      if (_salesmanId != null) 'salesman_id': _salesmanId,
      'branch_id': _branchId,
      'warehouse_id': _warehouseId,
      'order_date': _iso(_orderDate),
      if (delivery != null) 'delivery_date': _iso(delivery),
      if (_customerReference.text.trim().isNotEmpty)
        'customer_reference': _customerReference.text.trim(),
      if (_reference.text.trim().isNotEmpty)
        'reference_number': _reference.text.trim(),
      if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
      // Omitted when blank: absent is what tells the server there is no
      // discount on the order, and an empty string is a schema error.
      if (_billDiscountPercent.text.trim().isNotEmpty)
        'bill_discount_percent': _billDiscountPercent.text.trim(),
      if (_billDiscountAmount.text.trim().isNotEmpty)
        'bill_discount_amount': _billDiscountAmount.text.trim(),
      'lines': <Json>[
        for (int index = 0; index < _lines.length; index += 1)
          <String, dynamic>{
            'line_number': index + 1,
            'product_id': _lines[index].productId,
            'quantity': _lines[index].quantity.text.trim(),
            'unit_price': _lines[index].unitPrice.text.trim(),
            if (_lines[index].free.text.trim().isNotEmpty)
              'free_quantity': _lines[index].free.text.trim(),
            // Blank is omitted and zero is sent. Absent means the server
            // applies the price list or the customer's standing rate; zero
            // means somebody refused it for this line. Coercing blank to zero
            // would switch every standing arrangement off silently.
            if (_lines[index].discountPercent.text.trim().isNotEmpty)
              'discount_percent': _lines[index].discountPercent.text.trim(),
            if (_lines[index].discountAmount.text.trim().isNotEmpty)
              'discount_amount': _lines[index].discountAmount.text.trim(),
          },
      ],
    };
  }

  Future<void> _save() async {
    final Json? payload = _payload();
    if (payload == null) {
      setState(() => _error = 'Check the fields marked below.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final String? id = widget.orderId;
      if (id == null) {
        await widget.api.createSalesOrder(payload);
      } else {
        await widget.api.updateSalesOrder(
          id,
          payload,
          expectedVersion: preconditionFor(_version),
        );
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        // This dialog saves from inside itself, so a refusal leaves every
        // keystroke on screen -- and the message has to say so, because
        // closing the form is what throws them away.
        _error = saveFailureMessage(error, 'sales order', changesKept: true);
        _saving = false;
      });
    }
  }

  Future<void> _pickOrderDate() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _orderDate,
      // An order taken last week is ordinary; one dated next year is a typo.
      firstDate: widget.today.subtract(const Duration(days: 365)),
      lastDate: widget.today.add(const Duration(days: 365)),
      helpText: 'Order taken on',
    );
    if (picked != null) setState(() => _orderDate = picked);
  }

  Future<void> _pickDeliveryDate() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _deliveryDate ?? _orderDate,
      firstDate: _orderDate,
      lastDate: _orderDate.add(const Duration(days: 730)),
      helpText: 'Wanted by',
    );
    if (picked != null) setState(() => _deliveryDate = picked);
  }

  /// The items for one picker, with the stored id kept even when it is not in
  /// the loaded list.
  ///
  /// A customer who has since been deactivated, or a product beyond the pages
  /// read, would otherwise leave `DropdownButtonFormField` holding a value
  /// that matches no item -- which asserts, and on a form that survives it
  /// saves as blank.
  List<DropdownMenuItem<String>> _items(
    List<({String id, String label})> options,
    String? selected,
  ) {
    final List<DropdownMenuItem<String>> items = <DropdownMenuItem<String>>[
      for (final ({String id, String label}) option in options)
        DropdownMenuItem<String>(
          value: option.id,
          child: Text(option.label, overflow: TextOverflow.ellipsis),
        ),
    ];
    if (selected != null && !options.any((option) => option.id == selected)) {
      items.add(DropdownMenuItem<String>(
        value: selected,
        child: const Text('On the order, no longer listed',
            overflow: TextOverflow.ellipsis),
      ));
    }
    return items;
  }

  /// A picker that may honestly be left blank.
  ///
  /// [_picker] validates its value away from null, which is right for the
  /// customer and the warehouse and wrong for a salesman: an order taken at
  /// the counter was taken by nobody in particular, and refusing to save
  /// without a name would put a wrong one on every such order.
  Widget _optionalPicker({
    required String label,
    required String helperText,
    required String blankLabel,
    required String? value,
    required List<({String id, String label})> options,
    required ValueChanged<String?> onChanged,
    Key? key,
  }) =>
      DropdownButtonFormField<String?>(
        key: key,
        initialValue: value,
        isExpanded: true,
        decoration: InputDecoration(
          labelText: label,
          helperText: helperText,
          helperMaxLines: 3,
        ),
        items: <DropdownMenuItem<String?>>[
          DropdownMenuItem<String?>(
            value: null,
            child: Text(blankLabel, overflow: TextOverflow.ellipsis),
          ),
          for (final ({String id, String label}) option in options)
            DropdownMenuItem<String?>(
              value: option.id,
              child: Text(option.label, overflow: TextOverflow.ellipsis),
            ),
          // A stored id nobody in the list carries -- somebody who has left --
          // must stay an item of its own, or the widget asserts and the form
          // saves the order as though no salesman had ever been on it.
          if (value != null && !options.any((option) => option.id == value))
            DropdownMenuItem<String?>(
              value: value,
              child: Text(value, overflow: TextOverflow.ellipsis),
            ),
        ],
        onChanged: _locked ? null : onChanged,
      );

  Widget _picker({
    required String label,
    String? helperText,
    required String? value,
    required List<({String id, String label})> options,
    required ValueChanged<String?> onChanged,
    required String emptyMessage,
    Key? key,
  }) =>
      DropdownButtonFormField<String>(
        key: key,
        initialValue: value,
        // Without this the button's row is `mainAxisSize: min` and never
        // constrains the label, so `ellipsis` has nothing to ellipsise
        // against and a long name overflows instead of eliding.
        isExpanded: true,
        decoration: InputDecoration(
          labelText: label,
          helperText: helperText,
          helperMaxLines: 2,
        ),
        items: _items(options, value),
        validator: (String? chosen) => chosen == null ? emptyMessage : null,
        onChanged: _locked ? null : onChanged,
      );

  /// One line's row of controls.
  ///
  /// Each line carries its own running total, because the order's total alone
  /// does not say which of five lines was mistyped.
  Widget _lineEditor(int index) {
    final _LineDraft line = _lines[index];
    final bool removable = _lines.length > 1 && !_locked;
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            Expanded(
              child: _picker(
                key: ValueKey<String>('sales-order-line-product-$index'),
                label: 'Product ${index + 1}',
                value: line.productId,
                options: <({String id, String label})>[
                  for (final Product item in _products)
                    (id: item.id, label: '${item.code}  ${item.name}'),
                ],
                onChanged: (String? value) => _chooseProduct(line, value),
                emptyMessage: 'Choose a product.',
              ),
            ),
            IconButton(
              onPressed: removable ? () => _removeLine(index) : null,
              icon: const Icon(Icons.close, size: 18),
              tooltip: removable
                  ? 'Remove this line'
                  : 'An order needs at least one line',
            ),
          ]),
          const SizedBox(height: AppSpacing.sm),
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(
              child: TextFormField(
                controller: line.quantity,
                enabled: !_locked,
                decoration: const InputDecoration(labelText: 'Quantity'),
                keyboardType: TextInputType.number,
                validator: (String? value) => _positive(value, 'quantity'),
                onChanged: (_) => setState(() {}),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: TextFormField(
                controller: line.free,
                enabled: !_locked,
                decoration: const InputDecoration(
                  labelText: 'Free',
                  helperText: 'Outside the price and the tax.',
                  helperMaxLines: 2,
                ),
                keyboardType: TextInputType.number,
                validator: _quantityOrBlank,
                onChanged: (_) => setState(() {}),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: TextFormField(
                controller: line.unitPrice,
                enabled: !_locked,
                decoration: InputDecoration(
                  labelText: 'Unit price',
                  helperText: _priceHelper(line),
                  helperMaxLines: 2,
                ),
                keyboardType: TextInputType.number,
                validator: (String? value) => _positive(value, 'price'),
                // onChanged fires only for typing, never for the programmatic
                // fill above, which is what keeps the two distinguishable.
                onChanged: (_) => setState(() => line.priceEdited = true),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: TextFormField(
                controller: line.discountPercent,
                enabled: !_locked,
                decoration: InputDecoration(
                  labelText: 'Discount %',
                  helperText: _customerDiscount.isEmpty
                      ? 'Blank takes the arrangement on file.'
                      : "Blank takes this customer's $_customerDiscount%.",
                  helperMaxLines: 2,
                ),
                keyboardType: TextInputType.number,
                validator: _percentage,
                onChanged: (_) => setState(() {}),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: TextFormField(
                controller: line.discountAmount,
                enabled: !_locked,
                decoration: const InputDecoration(
                  labelText: 'Discount amount',
                  helperText: 'Beats the percentage.',
                  helperMaxLines: 2,
                ),
                keyboardType: TextInputType.number,
                validator: (String? value) =>
                    _discountAmount(value, line.gross, 'the line'),
                onChanged: (_) => setState(() {}),
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

  Widget _dateField({
    required String label,
    required String value,
    required String helperText,
    required VoidCallback onPick,
    VoidCallback? onClear,
  }) =>
      InputDecorator(
        decoration: InputDecoration(
          labelText: label,
          helperText: helperText,
          helperMaxLines: 2,
        ),
        child: Row(children: [
          Expanded(child: Text(value, overflow: TextOverflow.ellipsis)),
          if (onClear != null)
            TextButton(
              onPressed: _locked ? null : onClear,
              child: const Text('Clear'),
            ),
          TextButton.icon(
            onPressed: _locked ? null : onPick,
            icon: const Icon(Icons.event, size: 18),
            label: const Text('Change'),
          ),
        ]),
      );

  Widget _body(ThemeData theme) => Form(
        key: _form,
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_locked) ...[
                MaterialBanner(
                  content: Text(
                    'This order is $_status, so it can no longer be rewritten. '
                    'Its lines are what stock and credit were committed '
                    'against.',
                  ),
                  actions: const [SizedBox.shrink()],
                ),
                const SizedBox(height: AppSpacing.lg),
              ],
              if (_error != null) ...[
                MaterialBanner(
                  content: Text(_error!),
                  actions: [
                    TextButton(
                      onPressed: () => setState(() => _error = null),
                      child: const Text('Dismiss'),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.lg),
              ],
              const SectionHeader(
                title: 'Order',
                description: 'Who it is for, which branch takes it, and where '
                    'it will ship from.',
              ),
              const SizedBox(height: AppSpacing.md),
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(
                  flex: 2,
                  child: _picker(
                    key: const ValueKey<String>('sales-order-customer'),
                    label: 'Customer',
                    value: _customerId,
                    options: <({String id, String label})>[
                      for (final Customer item in _customers)
                        (id: item.id, label: item.displayName),
                    ],
                    // Fixed while correcting: an order for a different shop is
                    // a different order, and its credit was checked against
                    // this one.
                    onChanged: _editing
                        ? (String? value) {}
                        : (String? value) => setState(() => _customerId = value),
                    emptyMessage: 'Choose a customer.',
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  flex: 2,
                  child: _optionalPicker(
                    key: const ValueKey<String>('sales-order-salesman'),
                    label: 'Salesman',
                    blankLabel: 'Nobody',
                    helperText: 'Who took the order. Left blank, the '
                        "customer's round supplies one where they are on a "
                        'round; otherwise what this order collects earns '
                        'nobody commission.',
                    value: _salesmanId,
                    options: <({String id, String label})>[
                      for (final FirmMember item in _members)
                        (id: item.userId, label: item.label),
                    ],
                    onChanged: (String? value) =>
                        setState(() => _salesmanId = value),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(
                  child: _picker(
                    key: const ValueKey<String>('sales-order-branch'),
                    label: 'Branch',
                    value: _branchId,
                    options: <({String id, String label})>[
                      for (final BranchRecord item in _branches)
                        (id: item.id, label: item.displayName),
                    ],
                    onChanged: (String? value) =>
                        setState(() => _branchId = value),
                    emptyMessage: 'Choose a branch.',
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: _picker(
                    key: const ValueKey<String>('sales-order-warehouse'),
                    label: 'Ships from',
                    helperText: 'Stock is committed here on approval.',
                    value: _warehouseId,
                    options: <({String id, String label})>[
                      for (final WarehouseRecord item in _warehouses)
                        (id: item.id, label: item.displayName),
                    ],
                    onChanged: (String? value) =>
                        setState(() => _warehouseId = value),
                    emptyMessage: 'Choose a warehouse.',
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(
                  child: _dateField(
                    label: 'Order taken on',
                    value: _iso(_orderDate),
                    helperText: 'The date the rules and rates are read at.',
                    onPick: _pickOrderDate,
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: _dateField(
                    label: 'Wanted by',
                    value: _deliveryDate == null
                        ? 'Not promised'
                        : _iso(_deliveryDate!),
                    helperText: 'Optional. Nothing is scheduled from it.',
                    onPick: _pickDeliveryDate,
                    onClear: _deliveryDate == null
                        ? null
                        : () => setState(() => _deliveryDate = null),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                  child: TextFormField(
                    controller: _customerReference,
                    enabled: !_locked,
                    decoration: const InputDecoration(
                      labelText: "Customer's reference",
                    ),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: TextFormField(
                    controller: _reference,
                    enabled: !_locked,
                    decoration:
                        const InputDecoration(labelText: 'Our reference'),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.xl),
              const SectionHeader(
                title: 'What was ordered',
                description: 'A price starts at what the product lists at and '
                    'stays as it is typed.',
              ),
              const SizedBox(height: AppSpacing.md),
              for (int index = 0; index < _lines.length; index += 1)
                _lineEditor(index),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: _locked ? null : _addLine,
                  icon: const Icon(Icons.add, size: 18),
                  label: const Text('Add line'),
                ),
              ),
              const SizedBox(height: AppSpacing.sm),
              // Below the lines and above the total, because it is a deal
              // struck on the whole order rather than a property of any line.
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(
                  child: TextFormField(
                    controller: _billDiscountPercent,
                    enabled: !_locked,
                    decoration: const InputDecoration(
                      labelText: 'Discount on the whole order %',
                      helperText: 'Comes off what the lines discounted to, and '
                          'the tax falls with it.',
                      helperMaxLines: 2,
                    ),
                    keyboardType: TextInputType.number,
                    validator: _percentage,
                    onChanged: (_) => setState(() {}),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: TextFormField(
                    controller: _billDiscountAmount,
                    enabled: !_locked,
                    decoration: const InputDecoration(
                      labelText: 'Discount on the whole order',
                      helperText: 'A flat figure. Beats the percentage.',
                      helperMaxLines: 2,
                    ),
                    keyboardType: TextInputType.number,
                    validator: (String? value) => _discountAmount(
                      value,
                      _lines.fold<double>(
                        0,
                        (double running, _LineDraft line) =>
                            running + line.netOfDiscount,
                      ),
                      'the order',
                    ),
                    onChanged: (_) => setState(() {}),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.sm),
              Text(
                'Ordered before tax: ${_beforeTax.toStringAsFixed(2)}. Tax is '
                'worked out by the server at the rate in force.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              TextFormField(
                controller: _remarks,
                enabled: !_locked,
                decoration: const InputDecoration(labelText: 'Remarks'),
                maxLines: 2,
              ),
            ],
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool nothingToOrder =
        !_loading && (_customers.isEmpty || _products.isEmpty) && !_editing;
    return WorkspaceDialog(
      title: _editing ? 'Edit draft order' : 'New sales order',
      subtitle: _editing
          ? 'Correcting a draft. Only a draft can be rewritten.'
          : 'Taken over the counter or the phone, without a quotation first.',
      icon: Icons.receipt_long_outlined,
      loading: _loading || _saving,
      onClose: () => Navigator.of(context).pop(false),
      saveLabel: _editing ? 'Save order' : 'Create draft',
      onSave: _locked || nothingToOrder ? null : _save,
      // WorkspaceDialog drops its whole footer when there is nothing to save,
      // which would leave a locked order with no way out but Escape.
      footer: _locked || nothingToOrder
          ? Padding(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: Row(mainAxisAlignment: MainAxisAlignment.end, children: [
                TextButton(
                  onPressed: () => Navigator.of(context).pop(false),
                  child: const Text('Close'),
                ),
              ]),
            )
          : null,
      body: _loading
          ? const Center(
              child: Padding(
                padding: EdgeInsets.all(AppSpacing.xxl),
                child: CircularProgressIndicator(),
              ),
            )
          : nothingToOrder
              ? const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'Nothing to order yet',
                  message: 'An order needs a customer to take it from and a '
                      'product to sell.',
                )
              : _body(theme),
    );
  }
}
