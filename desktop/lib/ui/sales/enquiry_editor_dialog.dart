// The enquiry form (SEL-10): who asked, what for, and when to follow up. The
// buyer is an existing customer or a prospect typed in here; a prospect becomes
// a customer only when the enquiry is converted to a quotation. Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/branch_warehouse.dart';
import '../../models/customer.dart';
import '../../models/enquiry.dart';
import '../../models/entities.dart';
import '../../models/firm_member.dart';
import '../../models/product.dart';
import '../workspace/desktop_framework.dart';

String _iso(DateTime date) => date.toIso8601String().substring(0, 10);

DateTime? _parse(String? text) =>
    text == null || text.isEmpty ? null : DateTime.tryParse(text);

String? _blankToNull(String text) {
  final String trimmed = text.trim();
  return trimmed.isEmpty ? null : trimmed;
}

/// One row of the lines grid, with the boxes it owns.
class _LineDraft {
  _LineDraft({
    this.productId,
    String description = '',
    String? quantity,
    String? price,
  })
      : description = TextEditingController(text: description),
        quantity = TextEditingController(text: quantity ?? '1'),
        price = TextEditingController(text: price ?? '');

  String? productId;
  final TextEditingController description;
  final TextEditingController quantity;
  final TextEditingController price;

  void dispose() {
    description.dispose();
    quantity.dispose();
    price.dispose();
  }
}

/// Create an enquiry, or correct an open one: pops the saved [Enquiry];
/// stays open with the server's message on a refusal.
class EnquiryEditorDialog extends StatefulWidget {
  const EnquiryEditorDialog({super.key, required this.api, this.enquiry});

  final ApiClient api;

  /// The enquiry being corrected; null raises a new one.
  final Enquiry? enquiry;

  @override
  State<EnquiryEditorDialog> createState() => _EnquiryEditorDialogState();
}

class _EnquiryEditorDialogState extends State<EnquiryEditorDialog>
    with SaveInDialog {
  final TextEditingController _name = TextEditingController();
  final TextEditingController _company = TextEditingController();
  final TextEditingController _phone = TextEditingController();
  final TextEditingController _email = TextEditingController();
  final TextEditingController _city = TextEditingController();
  final TextEditingController _value = TextEditingController(text: '0');
  final TextEditingController _remarks = TextEditingController();
  final List<_LineDraft> _lines = <_LineDraft>[];

  List<Customer> _customers = const [];
  List<Product> _products = const [];
  List<BranchRecord> _branches = const [];
  List<FirmMember> _members = const [];
  bool _loading = true;
  String? _loadNote;
  String? _problem;

  bool _existingCustomer = false;
  String? _customerId;
  String? _branchId;
  String? _salesmanId;
  String _source = 'WALK_IN';
  DateTime _date = DateTime.now();
  DateTime? _closeOn;
  DateTime? _followUpOn;

  @override
  void initState() {
    super.initState();
    final Enquiry? e = widget.enquiry;
    if (e != null) {
      _existingCustomer = e.customerId != null;
      _customerId = e.customerId;
      _branchId = e.branchId;
      _salesmanId = e.salesmanId;
      _source = e.source.isEmpty ? 'OTHER' : e.source;
      _date = _parse(e.enquiryDate) ?? _date;
      _closeOn = _parse(e.expectedCloseOn);
      _followUpOn = _parse(e.nextFollowUpOn);
      _name.text = e.prospectName;
      _company.text = e.prospectCompany;
      _phone.text = e.prospectPhone;
      _email.text = e.prospectEmail;
      _city.text = e.prospectCity;
      _value.text = e.expectedValue;
      _remarks.text = e.remarks;
      for (final EnquiryLine line in e.lines) {
        _lines.add(_LineDraft(
          productId: line.productId,
          description: line.description,
          quantity: line.quantity,
          price: line.expectedPrice,
        ));
      }
    }
    if (_lines.isEmpty) _lines.add(_LineDraft());
    unawaited(_load());
  }

  @override
  void dispose() {
    for (final TextEditingController box in [
      _name,
      _company,
      _phone,
      _email,
      _city,
      _value,
      _remarks,
    ]) {
      box.dispose();
    }
    for (final _LineDraft line in _lines) {
      line.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final List<dynamic> loaded = await Future.wait<dynamic>(<Future<dynamic>>[
        fetchAllPages<Customer>(
          (int page) =>
              widget.api.customers(page: page, pageSize: maxApiPageSize),
        ),
        fetchAllPages<Product>(
          (int page) =>
              widget.api.products(page: page, pageSize: maxApiPageSize),
        ),
        fetchAllPages<BranchRecord>(
          (int page) =>
              widget.api.branches(page: page, pageSize: maxApiPageSize),
        ),
        widget.api.firmMembers(),
      ]);
      if (!mounted) return;
      setState(() {
        _customers = (loaded[0] as List<dynamic>).cast<Customer>();
        _products = (loaded[1] as List<dynamic>).cast<Product>();
        _branches = (loaded[2] as List<dynamic>).cast<BranchRecord>();
        _members = (loaded[3] as List<dynamic>).cast<FirmMember>();
        _branchId ??= preferredBranchId(_branches);
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _loadNote = error.message;
        _loading = false;
      });
    }
  }

  Future<DateTime?> _choose(DateTime? current) => showDatePicker(
        context: context,
        initialDate: current ?? DateTime.now(),
        firstDate: DateTime(2000),
        lastDate: DateTime(2100),
      );

  Future<void> _pick(String which) async {
    final DateTime? picked = await _choose(switch (which) {
      'close' => _closeOn,
      'follow' => _followUpOn,
      _ => _date,
    });
    if (picked == null) return;
    setState(() {
      switch (which) {
        case 'close':
          _closeOn = picked;
        case 'follow':
          _followUpOn = picked;
        default:
          _date = picked;
      }
    });
  }

  String? _check() {
    if (_branchId == null) return 'Choose the branch.';
    if (_existingCustomer) {
      if (_customerId == null) return 'Choose the customer.';
    } else if (_name.text.trim().isEmpty) {
      return 'Name the prospect who asked.';
    }
    final double? value = double.tryParse(_value.text.trim());
    if (value == null || value < 0) return 'Enter the expected value.';
    for (int i = 0; i < _lines.length; i++) {
      final _LineDraft line = _lines[i];
      final double? qty = double.tryParse(line.quantity.text.trim());
      if (line.productId == null && line.description.text.trim().isEmpty) {
        return 'Line ${i + 1}: choose a product or describe what was asked.';
      }
      if (qty == null || qty <= 0) return 'Line ${i + 1}: enter a quantity.';
      final String price = line.price.text.trim();
      if (price.isNotEmpty && (double.tryParse(price) ?? -1) < 0) {
        return 'Line ${i + 1}: the expected price is not a number.';
      }
    }
    return null;
  }

  /// Exactly the keys `EnquiryWrite` declares.
  Json _body() => <String, dynamic>{
        'enquiry_date': _iso(_date),
        'branch_id': _branchId,
        'customer_id': _existingCustomer ? _customerId : null,
        'prospect_name': _existingCustomer ? null : _blankToNull(_name.text),
        'prospect_company':
            _existingCustomer ? null : _blankToNull(_company.text),
        'prospect_phone': _existingCustomer ? null : _blankToNull(_phone.text),
        'prospect_email': _existingCustomer ? null : _blankToNull(_email.text),
        'prospect_city': _existingCustomer ? null : _blankToNull(_city.text),
        'source': _source,
        'salesman_id': _salesmanId,
        'expected_value': _value.text.trim(),
        'expected_close_on': _closeOn == null ? null : _iso(_closeOn!),
        'next_follow_up_on': _followUpOn == null ? null : _iso(_followUpOn!),
        'remarks': _blankToNull(_remarks.text),
        'lines': [
          for (final _LineDraft line in _lines)
            <String, dynamic>{
              'product_id': line.productId,
              'description': _blankToNull(line.description.text),
              'quantity': line.quantity.text.trim(),
              'expected_price': _blankToNull(line.price.text),
            },
        ],
      };

  void _save() {
    final String? problem = _check();
    setState(() => _problem = problem);
    if (problem != null) return;
    final Enquiry? existing = widget.enquiry;
    unawaited(saveAndClose<Enquiry>(
      () => existing == null
          ? widget.api.createEnquiry(_body())
          : widget.api.updateEnquiry(existing.id, _body()),
    ));
  }

  Widget _dateField(String key, String label, DateTime? value,
          {bool clearable = false}) =>
      InkWell(
        key: ValueKey('enquiry-$key'),
        onTap: saving ? null : () => unawaited(_pick(key)),
        child: InputDecorator(
          decoration: InputDecoration(
            labelText: label,
            suffixIcon: clearable && value != null
                ? IconButton(
                    icon: const Icon(Icons.clear, size: 16),
                    onPressed: saving
                        ? null
                        : () => setState(() {
                              if (key == 'close') _closeOn = null;
                              if (key == 'follow') _followUpOn = null;
                            }),
                  )
                : null,
          ),
          child: Text(value == null ? 'Not set' : _iso(value)),
        ),
      );

  Widget _text(String key, String label, TextEditingController controller,
          {TextInputType? keyboard}) =>
      TextField(
        key: ValueKey('enquiry-$key'),
        controller: controller,
        enabled: !saving,
        keyboardType: keyboard,
        decoration: InputDecoration(labelText: label),
      );

  Widget _buyer() {
    if (_existingCustomer) {
      return DropdownButtonFormField<String>(
        key: const ValueKey('enquiry-customer'),
        isExpanded: true,
        initialValue: _customerId,
        decoration: const InputDecoration(labelText: 'Customer'),
        items: [
          for (final Customer c in _customers)
            DropdownMenuItem<String>(
              value: c.id,
              child: Text(c.name, overflow: TextOverflow.ellipsis),
            ),
        ],
        onChanged: saving ? null : (id) => setState(() => _customerId = id),
      );
    }
    return Column(children: [
      Row(children: [
        Expanded(child: _text('name', 'Prospect name', _name)),
        const SizedBox(width: AppSpacing.md),
        Expanded(child: _text('company', 'Company', _company)),
      ]),
      Row(children: [
        Expanded(
            child: _text('phone', 'Phone (+919876543210)', _phone,
                keyboard: TextInputType.phone)),
        const SizedBox(width: AppSpacing.md),
        Expanded(
            child: _text('email', 'Email', _email,
                keyboard: TextInputType.emailAddress)),
        const SizedBox(width: AppSpacing.md),
        Expanded(child: _text('city', 'City', _city)),
      ]),
    ]);
  }

  Widget _lineRow(int index) {
    final _LineDraft line = _lines[index];
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(
          flex: 3,
          child: DropdownButtonFormField<String?>(
            key: ValueKey('enquiry-line-product-$index'),
            isExpanded: true,
            initialValue: line.productId,
            decoration: const InputDecoration(
                labelText: 'Product', isDense: true),
            items: [
              const DropdownMenuItem<String?>(
                  value: null, child: Text('Not in the catalogue')),
              for (final Product p in _products)
                DropdownMenuItem<String?>(
                  value: p.id,
                  child: Text(p.name, overflow: TextOverflow.ellipsis),
                ),
            ],
            onChanged: saving
                ? null
                : (id) => setState(() => line.productId = id),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          flex: 3,
          child: TextField(
            key: ValueKey('enquiry-line-description-$index'),
            controller: line.description,
            enabled: !saving,
            decoration: const InputDecoration(
                labelText: 'Description', isDense: true),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        SizedBox(
          width: 90,
          child: TextField(
            key: ValueKey('enquiry-line-quantity-$index'),
            controller: line.quantity,
            enabled: !saving,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration:
                const InputDecoration(labelText: 'Quantity', isDense: true),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        SizedBox(
          width: 110,
          child: TextField(
            key: ValueKey('enquiry-line-price-$index'),
            controller: line.price,
            enabled: !saving,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
                labelText: 'Expected price', isDense: true),
          ),
        ),
        IconButton(
          tooltip: 'Remove line',
          icon: const Icon(Icons.delete_outline),
          onPressed: saving || _lines.length == 1
              ? null
              : () => setState(() => _lines.removeAt(index).dispose()),
        ),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text(widget.enquiry == null
          ? 'New enquiry'
          : 'Enquiry ${widget.enquiry!.enquiryNumber}'),
      content: SizedBox(
        width: 780,
        child: _loading
            ? const SizedBox(
                height: 120,
                child: Center(child: CircularProgressIndicator()),
              )
            : SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    saveErrorBanner(),
                    if (_loadNote != null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                        child: Text(_loadNote!,
                            style: TextStyle(color: theme.colorScheme.error)),
                      ),
                    Row(children: [
                      Expanded(child: _dateField('date', 'Date', _date)),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          key: const ValueKey('enquiry-branch'),
                          isExpanded: true,
                          initialValue: _branchId,
                          decoration:
                              const InputDecoration(labelText: 'Branch'),
                          items: [
                            for (final BranchRecord b in _branches)
                              DropdownMenuItem<String>(
                                value: b.id,
                                child: Text(b.name,
                                    overflow: TextOverflow.ellipsis),
                              ),
                          ],
                          onChanged: saving
                              ? null
                              : (id) => setState(() => _branchId = id),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          key: const ValueKey('enquiry-source'),
                          isExpanded: true,
                          initialValue: _source,
                          decoration:
                              const InputDecoration(labelText: 'Source'),
                          items: [
                            for (final (String code, String label)
                                in enquirySources)
                              DropdownMenuItem<String>(
                                  value: code, child: Text(label)),
                          ],
                          onChanged: saving
                              ? null
                              : (code) =>
                                  setState(() => _source = code ?? _source),
                        ),
                      ),
                    ]),
                    const SizedBox(height: AppSpacing.md),
                    SegmentedButton<bool>(
                      key: const ValueKey('enquiry-buyer-kind'),
                      segments: const [
                        ButtonSegment<bool>(
                            value: false, label: Text('New prospect')),
                        ButtonSegment<bool>(
                            value: true, label: Text('Existing customer')),
                      ],
                      selected: {_existingCustomer},
                      onSelectionChanged: saving
                          ? null
                          : (set) =>
                              setState(() => _existingCustomer = set.first),
                    ),
                    _buyer(),
                    const SizedBox(height: AppSpacing.sm),
                    Row(children: [
                      Expanded(
                        child: DropdownButtonFormField<String?>(
                          key: const ValueKey('enquiry-salesman'),
                          isExpanded: true,
                          initialValue: _members
                                  .any((m) => m.userId == _salesmanId)
                              ? _salesmanId
                              : null,
                          decoration:
                              const InputDecoration(labelText: 'Salesman'),
                          items: [
                            const DropdownMenuItem<String?>(
                                value: null, child: Text('Nobody')),
                            for (final FirmMember m in _members)
                              DropdownMenuItem<String?>(
                                value: m.userId,
                                child: Text(m.label,
                                    overflow: TextOverflow.ellipsis),
                              ),
                          ],
                          onChanged: saving
                              ? null
                              : (id) => setState(() => _salesmanId = id),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: _text('value', 'Expected value', _value,
                            keyboard: const TextInputType.numberWithOptions(
                                decimal: true)),
                      ),
                    ]),
                    const SizedBox(height: AppSpacing.sm),
                    Row(children: [
                      Expanded(
                          child: _dateField(
                              'close', 'Expected close', _closeOn,
                              clearable: true)),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                          child: _dateField(
                              'follow', 'Next follow-up', _followUpOn,
                              clearable: true)),
                    ]),
                    _text('remarks', 'Remarks', _remarks),
                    const SizedBox(height: AppSpacing.md),
                    Text('What was asked for', style: theme.textTheme.titleSmall),
                    const SizedBox(height: AppSpacing.sm),
                    for (int i = 0; i < _lines.length; i++) _lineRow(i),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton.icon(
                        key: const ValueKey('enquiry-add-line'),
                        onPressed: saving
                            ? null
                            : () => setState(() => _lines.add(_LineDraft())),
                        icon: const Icon(Icons.add),
                        label: const Text('Add line'),
                      ),
                    ),
                    if (_problem != null)
                      Padding(
                        padding: const EdgeInsets.only(top: AppSpacing.sm),
                        child: Text(_problem!,
                            key: const ValueKey('enquiry-problem'),
                            style: TextStyle(color: theme.colorScheme.error)),
                      ),
                  ],
                ),
              ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('enquiry-save'),
          onPressed: saving || _loading ? null : _save,
          child: Text(saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}
