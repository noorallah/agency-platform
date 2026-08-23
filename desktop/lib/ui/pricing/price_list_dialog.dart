import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/customer.dart';
import '../../models/entities.dart';
import '../../models/pricing.dart';
import '../../models/product.dart';

/// Writing one arrangement.
///
/// The scope is a single choice rather than two independent pickers, because
/// a list scoped to a customer *and* a territory at once has no defensible
/// precedence against one scoped to only the first — the server refuses it,
/// and offering it here would only produce a refusal somebody has to read.
enum _Scope { everyone, customer, territory }

class PriceListDialog extends StatefulWidget {
  const PriceListDialog({
    super.key,
    required this.api,
    required this.customers,
    required this.products,
    this.existing,
  });

  final ApiClient api;
  final List<Customer> customers;
  final List<Product> products;

  /// The list being revised, or null to agree a new one.
  final PriceListRecord? existing;

  @override
  State<PriceListDialog> createState() => _PriceListDialogState();
}

class _PriceListDialogState extends State<PriceListDialog> {
  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  late final TextEditingController _code =
      TextEditingController(text: widget.existing?.code ?? '');
  late final TextEditingController _name =
      TextEditingController(text: widget.existing?.name ?? '');
  late final TextEditingController _from = TextEditingController(
      text: widget.existing?.effectiveFrom ?? _todayIso());
  late final TextEditingController _to =
      TextEditingController(text: widget.existing?.effectiveTo ?? '');

  late _Scope _scope = _scopeOf(widget.existing);
  late String? _customerId = widget.existing?.customerId.isEmpty ?? true
      ? null
      : widget.existing!.customerId;
  // Read from an existing list and carried back unchanged: this screen
  // does not yet pick a territory, so it must not silently drop one that
  // was agreed through the API.
  late final String? _territoryId =
      widget.existing?.territoryId.isEmpty ?? true
          ? null
          : widget.existing!.territoryId;
  late List<_RateDraft> _rates = [
    for (final PriceListItemRecord item in widget.existing?.items ?? const [])
      _RateDraft(productId: item.productId, percent: item.discountPercent),
  ];

  bool _saving = false;
  String? _error;

  static String _todayIso() => DateTime.now().toIso8601String().split('T').first;

  static _Scope _scopeOf(PriceListRecord? row) {
    if (row == null) return _Scope.everyone;
    if (row.customerId.isNotEmpty) return _Scope.customer;
    if (row.territoryId.isNotEmpty) return _Scope.territory;
    return _Scope.everyone;
  }

  @override
  void dispose() {
    for (final TextEditingController c in [_code, _name, _from, _to]) {
      c.dispose();
    }
    for (final _RateDraft rate in _rates) {
      rate.dispose();
    }
    super.dispose();
  }

  void _addRate() {
    setState(() {
      _rates = [
        ..._rates,
        _RateDraft(
          productId:
              widget.products.isEmpty ? null : widget.products.first.id,
          percent: '',
        ),
      ];
    });
  }

  void _removeRate(int index) {
    setState(() {
      final List<_RateDraft> next = [..._rates];
      next.removeAt(index).dispose();
      _rates = next;
    });
  }

  Json? _payload() {
    if (!(_form.currentState?.validate() ?? false)) return null;
    final List<Json> items = [
      for (final _RateDraft rate in _rates)
        if (rate.productId != null && rate.percent.text.trim().isNotEmpty)
          <String, dynamic>{
            'product_id': rate.productId,
            'discount_percent': rate.percent.text.trim(),
          },
    ];
    return <String, dynamic>{
      'code': _code.text.trim().toUpperCase(),
      'name': _name.text.trim(),
      // One scope or none: the server refuses both, so the form cannot offer
      // both either.
      'customer_id': _scope == _Scope.customer ? _customerId : null,
      'territory_id': _scope == _Scope.territory ? _territoryId : null,
      'effective_from': _from.text.trim(),
      'effective_to': _to.text.trim().isEmpty ? null : _to.text.trim(),
      'status': widget.existing?.status ?? 'ACTIVE',
      'items': items,
    };
  }

  Future<void> _save() async {
    final Json? payload = _payload();
    if (payload == null) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final PriceListRecord? existing = widget.existing;
      if (existing == null) {
        await widget.api.createPriceList(payload);
      } else {
        await widget.api.updatePriceList(
          existing.id,
          payload,
          expectedVersion: existing.version,
        );
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      // The server's sentence names what is wrong -- a clashing code, a
      // scope it refuses -- and is more use than anything invented here.
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
      title: Text(widget.existing == null
          ? 'New price list'
          : 'Edit ${widget.existing!.code}'),
      content: SizedBox(
        width: 640,
        child: Form(
          key: _form,
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'A price list holds rates off the product price, not prices '
                  'of their own — so a product repriced once carries every '
                  'arrangement with it.',
                  style: theme.textTheme.bodySmall,
                ),
                const SizedBox(height: AppSpacing.md),
                Row(children: [
                  Expanded(
                    child: TextFormField(
                      controller: _code,
                      decoration: const InputDecoration(labelText: 'Code'),
                      textCapitalization: TextCapitalization.characters,
                      validator: (value) =>
                          (value ?? '').trim().length < 2 ? 'Give it a code.' : null,
                    ),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    flex: 2,
                    child: TextFormField(
                      controller: _name,
                      decoration: const InputDecoration(labelText: 'Name'),
                      validator: (value) =>
                          (value ?? '').trim().isEmpty ? 'Name it.' : null,
                    ),
                  ),
                ]),
                const SizedBox(height: AppSpacing.md),
                _scopePicker(theme),
                const SizedBox(height: AppSpacing.md),
                Row(children: [
                  Expanded(
                    child: TextFormField(
                      controller: _from,
                      decoration: const InputDecoration(
                        labelText: 'In force from',
                        hintText: 'YYYY-MM-DD',
                      ),
                      validator: _date,
                    ),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: TextFormField(
                      controller: _to,
                      decoration: const InputDecoration(
                        labelText: 'Until',
                        helperText: 'Leave empty to stand until withdrawn.',
                        helperMaxLines: 2,
                      ),
                      validator: _optionalEndDate,
                    ),
                  ),
                ]),
                const SizedBox(height: AppSpacing.md),
                Row(children: [
                  Text('Rates', style: theme.textTheme.titleSmall),
                  const Spacer(),
                  TextButton.icon(
                    onPressed: widget.products.isEmpty ? null : _addRate,
                    icon: const Icon(Icons.add, size: 18),
                    label: const Text('Add product'),
                  ),
                ]),
                if (_rates.isEmpty)
                  Text(
                    'No products yet. A list with no rates changes nothing.',
                    style: theme.textTheme.bodySmall,
                  ),
                for (int index = 0; index < _rates.length; index += 1)
                  _rateRow(index),
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
        ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _saving ? null : _save,
          child: Text(_saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }

  Widget _scopePicker(ThemeData theme) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Applies to', style: theme.textTheme.titleSmall),
          const SizedBox(height: AppSpacing.xs),
          SegmentedButton<_Scope>(
            segments: const [
              ButtonSegment(value: _Scope.everyone, label: Text('Everyone')),
              ButtonSegment(value: _Scope.customer, label: Text('One customer')),
              ButtonSegment(value: _Scope.territory, label: Text('One territory')),
            ],
            selected: {_scope},
            onSelectionChanged: (choice) =>
                setState(() => _scope = choice.first),
          ),
          if (_scope == _Scope.customer)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: DropdownButtonFormField<String>(
                initialValue: _customerId,
                // Without this the button's row never constrains the label and
                // a long customer name overflows instead of ellipsising.
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Customer'),
                items: [
                  for (final Customer item in widget.customers)
                    DropdownMenuItem(
                      value: item.id,
                      child: Text(item.displayName,
                          overflow: TextOverflow.ellipsis),
                    ),
                ],
                validator: (value) => _scope == _Scope.customer && value == null
                    ? 'Choose a customer.'
                    : null,
                onChanged: (value) => setState(() => _customerId = value),
              ),
            ),
          if (_scope == _Scope.territory)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(
                'Territory-scoped lists are set through the API for now; this '
                'screen agrees them with one customer or with everybody.',
                style: theme.textTheme.bodySmall,
              ),
            ),
        ],
      );

  Widget _rateRow(int index) {
    final _RateDraft rate = _rates[index];
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm),
      child: Row(children: [
        Expanded(
          flex: 3,
          child: DropdownButtonFormField<String>(
            key: ValueKey<String>('price-list-rate-product-$index'),
            initialValue: rate.productId,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Product'),
            items: [
              for (final Product item in widget.products)
                DropdownMenuItem(
                  value: item.id,
                  child: Text('${item.code}  ${item.name}',
                      overflow: TextOverflow.ellipsis),
                ),
            ],
            validator: (value) => value == null ? 'Choose a product.' : null,
            onChanged: (value) => setState(() => rate.productId = value),
          ),
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: TextFormField(
            controller: rate.percent,
            decoration: const InputDecoration(labelText: 'Discount %'),
            keyboardType: TextInputType.number,
            validator: _percentage,
          ),
        ),
        IconButton(
          onPressed: () => _removeRate(index),
          icon: const Icon(Icons.close, size: 18),
          tooltip: 'Remove this rate',
        ),
      ]),
    );
  }

  String? _date(String? value) {
    final String text = (value ?? '').trim();
    if (DateTime.tryParse(text) == null) return 'Use YYYY-MM-DD.';
    return null;
  }

  /// The end of the window, which may be absent but not before the start.
  String? _optionalEndDate(String? value) {
    final String text = (value ?? '').trim();
    if (text.isEmpty) return null;
    final DateTime? end = DateTime.tryParse(text);
    if (end == null) return 'Use YYYY-MM-DD.';
    final DateTime? start = DateTime.tryParse(_from.text.trim());
    if (start != null && end.isBefore(start)) {
      return 'Cannot end before it starts.';
    }
    return null;
  }

  String? _percentage(String? value) {
    final String text = (value ?? '').trim();
    if (text.isEmpty) return 'Enter a rate.';
    final double? parsed = double.tryParse(text);
    if (parsed == null) return 'Enter a percentage.';
    if (parsed < 0 || parsed > 100) return 'Between 0 and 100.';
    return null;
  }
}

/// One product's rate while it is being typed.
class _RateDraft {
  _RateDraft({required this.productId, required String percent})
      : percent = TextEditingController(text: percent);

  String? productId;
  final TextEditingController percent;

  void dispose() => percent.dispose();
}
