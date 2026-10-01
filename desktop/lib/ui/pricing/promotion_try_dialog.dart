// Trying offers on a made-up document before they go live.
//
// Asks the server what a document would earn -- the same engine every sales
// document calls -- and shows the answer *and the reasons*: the table of every
// offer tried says why one applied and another did not, which is the question
// somebody asks the day an offer "does not work". Nothing is saved, and no
// coupon is claimed, by asking. The date is the point: type next week's date
// and see today what next week's offer does.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/customer.dart';
import '../../models/entities.dart';
import '../../models/pricing.dart';
import '../../models/product.dart';
import '../workspace/desktop_framework.dart';

/// One line being typed: a product, how many, and at what rate.
class _TryLine {
  _TryLine();

  String productId = '';
  String productLabel = '';
  final TextEditingController quantity = TextEditingController(text: '1');
  final TextEditingController rate = TextEditingController();

  void dispose() {
    quantity.dispose();
    rate.dispose();
  }
}

/// Try the firm's offers on a document nobody has written yet.
class PromotionTryDialog extends StatefulWidget {
  const PromotionTryDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<PromotionTryDialog> createState() => _PromotionTryDialogState();
}

class _PromotionTryDialogState extends State<PromotionTryDialog> {
  final TextEditingController _date = TextEditingController();
  final TextEditingController _coupon = TextEditingController();
  final TextEditingController _delivery = TextEditingController();
  final List<_TryLine> _lines = <_TryLine>[_TryLine()];

  String _documentType = promotionTransactionTypeLabels.keys.first;
  String _customerId = '';
  String _customerGroupId = '';
  String _customerLabel = '';
  final Map<String, String> _productNames = <String, String>{};

  bool _busy = false;
  String? _error;
  PromotionTryResult? _result;

  @override
  void initState() {
    super.initState();
    _date.text = _isoDay(DateTime.now());
  }

  @override
  void dispose() {
    _date.dispose();
    _coupon.dispose();
    _delivery.dispose();
    for (final _TryLine line in _lines) {
      line.dispose();
    }
    super.dispose();
  }

  static String _isoDay(DateTime day) => '${day.year.toString().padLeft(4, '0')}-'
      '${day.month.toString().padLeft(2, '0')}-'
      '${day.day.toString().padLeft(2, '0')}';

  Future<void> _try() async {
    final String date = _date.text.trim();
    if (DateTime.tryParse(date) == null) {
      setState(() => _error = 'Enter the date as YYYY-MM-DD.');
      return;
    }
    final List<Json> lines = <Json>[];
    for (final _TryLine line in _lines) {
      final double quantity = double.tryParse(line.quantity.text.trim()) ?? 0;
      final double rate = double.tryParse(line.rate.text.trim()) ?? 0;
      if (line.productId.isEmpty) {
        setState(() => _error = 'Pick a product for every line.');
        return;
      }
      if (quantity <= 0) {
        setState(() => _error = 'Every line needs a quantity above zero.');
        return;
      }
      lines.add(<String, dynamic>{
        'line_number': lines.length + 1,
        'product_id': line.productId,
        'quantity': line.quantity.text.trim(),
        'gross': _money(quantity * rate),
      });
    }
    final double delivery = double.tryParse(_delivery.text.trim()) ?? 0;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final PromotionTryResult result = await widget.api.simulatePromotions(
        <String, dynamic>{
          'transaction_type': _documentType,
          'transaction_date': date,
          if (_customerId.isNotEmpty) 'customer_id': _customerId,
          if (_customerGroupId.isNotEmpty)
            'customer_group_id': _customerGroupId,
          if (_coupon.text.trim().isNotEmpty)
            'coupon_code': _coupon.text.trim(),
          if (delivery > 0) 'freight_amount': _money(delivery),
          'lines': lines,
        },
      );
      if (!mounted) return;
      setState(() {
        _result = result;
        _busy = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _result = null;
        _busy = false;
      });
    }
  }

  static String _money(double value) => value.toStringAsFixed(2);

  Future<Iterable<_Option>> _productOptions(String text) async {
    try {
      final PagedResult<Product> page =
          await widget.api.products(search: text.trim());
      return [
        for (final Product item in page.items)
          _Option(item.id, '${item.code} — ${item.name}',
              extra: item.sellingPrice, name: item.name),
      ];
    } on ApiException {
      return const <_Option>[];
    }
  }

  Future<Iterable<_Option>> _customerOptions(String text) async {
    try {
      final PagedResult<Customer> page =
          await widget.api.customers(search: text.trim());
      return [
        for (final Customer item in page.items)
          _Option(item.id, '${item.code} — ${item.name}',
              extra: item.customerGroupId ?? ''),
      ];
    } on ApiException {
      return const <_Option>[];
    }
  }

  Widget _search({
    required Key key,
    required String label,
    required String helper,
    required Future<Iterable<_Option>> Function(String) source,
    required void Function(_Option) onSelected,
    required VoidCallback onCleared,
    String initial = '',
  }) =>
      Autocomplete<_Option>(
        key: key,
        initialValue: TextEditingValue(text: initial),
        displayStringForOption: (option) => option.label,
        optionsBuilder: (value) => source(value.text),
        onSelected: onSelected,
        fieldViewBuilder: (context, controller, focusNode, onSubmitted) =>
            TextFormField(
          controller: controller,
          focusNode: focusNode,
          decoration: InputDecoration(
            labelText: label,
            helperText: helper,
            suffixIcon: const Icon(Icons.search, size: 18),
          ),
          // Typing over a chosen record un-chooses it, so the id never
          // disagrees with the name on the screen.
          onChanged: (text) {
            if (text.isEmpty) onCleared();
          },
        ),
      );

  Widget _lineRow(int index) {
    final _TryLine line = _lines[index];
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 4,
            child: Container(
              key: Key('try-product-$index'),
              child: _search(
                key: ObjectKey(line),
                label: 'Product',
                helper: 'Type to search',
                initial: line.productLabel,
                source: _productOptions,
                onSelected: (option) => setState(() {
                  line.productId = option.id;
                  line.productLabel = option.label;
                  _productNames[option.id] = option.name;
                  if (line.rate.text.trim().isEmpty) {
                    line.rate.text = option.extra;
                  }
                }),
                onCleared: () => line.productId = '',
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: TextFormField(
              controller: line.quantity,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Quantity'),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: TextFormField(
              controller: line.rate,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Rate'),
            ),
          ),
          IconButton(
            tooltip: 'Remove line',
            onPressed: _lines.length < 2
                ? null
                : () => setState(() => _lines.removeAt(index).dispose()),
            icon: const Icon(Icons.close, size: 18),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) => WorkspaceDialog(
        title: 'Try offers',
        subtitle: 'See what a document would earn, and why each offer did or '
            'did not apply. Nothing is saved.',
        icon: Icons.science_outlined,
        loading: _busy,
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_error != null) ...[
                Text(_error!,
                    key: const Key('try-error'),
                    style: const TextStyle(color: Colors.redAccent)),
                const SizedBox(height: AppSpacing.sm),
              ],
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: TextFormField(
                      key: const Key('try-date'),
                      controller: _date,
                      decoration: InputDecoration(
                        labelText: 'Date',
                        helperText: 'A future date shows a coming offer.',
                        suffixIcon: IconButton(
                          tooltip: 'Pick a date',
                          icon: const Icon(Icons.calendar_today, size: 16),
                          onPressed: () async {
                            final DateTime? picked = await showDatePicker(
                              context: context,
                              initialDate:
                                  DateTime.tryParse(_date.text.trim()) ??
                                      DateTime.now(),
                              firstDate: DateTime(2000),
                              lastDate: DateTime(2100),
                            );
                            if (picked != null) _date.text = _isoDay(picked);
                          },
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      key: const Key('try-document'),
                      isExpanded: true,
                      initialValue: _documentType,
                      decoration: const InputDecoration(labelText: 'Document'),
                      items: [
                        for (final MapEntry<String, String> entry
                            in promotionTransactionTypeLabels.entries)
                          DropdownMenuItem(
                              value: entry.key, child: Text(entry.value)),
                      ],
                      onChanged: (value) =>
                          setState(() => _documentType = value ?? _documentType),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.sm),
              _search(
                key: const Key('try-customer'),
                label: 'Customer (optional)',
                helper: 'Offers aimed at a customer or group need one.',
                initial: _customerLabel,
                source: _customerOptions,
                onSelected: (option) => setState(() {
                  _customerId = option.id;
                  _customerGroupId = option.extra;
                  _customerLabel = option.label;
                }),
                onCleared: () {
                  _customerId = '';
                  _customerGroupId = '';
                },
              ),
              const SizedBox(height: AppSpacing.sm),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: TextFormField(
                      key: const Key('try-coupon'),
                      controller: _coupon,
                      textCapitalization: TextCapitalization.characters,
                      decoration: const InputDecoration(
                        labelText: 'Coupon code (optional)',
                      ),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: TextFormField(
                      key: const Key('try-delivery'),
                      controller: _delivery,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(
                        labelText: 'Delivery charge (optional)',
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              Text('Lines', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: AppSpacing.xs),
              for (int i = 0; i < _lines.length; i++) _lineRow(i),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  key: const Key('try-add-line'),
                  onPressed: () => setState(() => _lines.add(_TryLine())),
                  icon: const Icon(Icons.add, size: 18),
                  label: const Text('Add line'),
                ),
              ),
              if (_result != null) ...[
                const Divider(height: AppSpacing.lg),
                _resultView(_result!),
              ],
            ],
          ),
        ),
        saveLabel: 'Try',
        onSave: _busy ? null : _try,
      );

  Widget _resultView(PromotionTryResult result) {
    final TextTheme text = Theme.of(context).textTheme;
    String codes(List<String> list) => list.isEmpty ? 'no offer' : list.join(', ');
    return Column(
      key: const Key('try-result'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Total saved: ${_money(result.totalSaved)}',
            style: text.titleMedium),
        const SizedBox(height: AppSpacing.sm),
        for (final PromotionTryLine line in result.lines)
          Text(
            'Line ${line.lineNumber}: discount ${line.discountAmount}, '
            'free quantity ${line.freeQuantity} (${codes(line.offerCodes)})',
          ),
        Text('Bill discount: ${result.billDiscount}'),
        Text('Delivery waived: ${result.freightWaived}'),
        const SizedBox(height: AppSpacing.sm),
        Text('Free goods', style: text.titleSmall),
        if (result.gifts.isEmpty)
          const Text('None.')
        else
          for (final PromotionTryGift gift in result.gifts)
            Text('${gift.quantity} x '
                '${_productNames[gift.productId] ?? gift.productId} '
                '(${gift.offerCode})'),
        const SizedBox(height: AppSpacing.sm),
        Text('Every offer tried', style: text.titleSmall),
        const SizedBox(height: AppSpacing.xs),
        if (result.decisions.isEmpty)
          const Text('No offers are live for this document.')
        else
          Table(
            key: const Key('try-decisions'),
            columnWidths: const {
              0: FlexColumnWidth(2),
              1: FixedColumnWidth(64),
              2: FixedColumnWidth(72),
              3: FlexColumnWidth(5),
            },
            children: [
              const TableRow(children: [
                Text('Offer'),
                Text('Priority'),
                Text('Applied'),
                Text('Reason'),
              ]),
              for (final PromotionTryDecision decision in result.decisions)
                TableRow(children: [
                  Text(decision.code),
                  Text('${decision.priority}'),
                  Text(decision.applied ? 'Yes' : 'No'),
                  Text(decision.reason),
                ]),
            ],
          ),
      ],
    );
  }
}

class _Option {
  const _Option(this.id, this.label, {this.extra = '', this.name = ''});

  final String id;
  final String label;

  /// A product's selling price, or a customer's group id.
  final String extra;
  final String name;
}
