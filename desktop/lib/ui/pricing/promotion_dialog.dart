import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/design/design_tokens.dart';
import '../../models/customer.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../../models/firm_member.dart';
import '../../models/pricing.dart';
import '../../models/product.dart';
import '../../models/sales_territory.dart';

/// Agree one offer: what it gives, who it is for, and when it runs.
///
/// A live promotion is **superseded rather than edited** — saving one produces
/// a new revision and retires the old, so an order priced in March stays
/// explicable in September. A draft is edited in place.
class PromotionDialog extends StatefulWidget {
  const PromotionDialog({super.key, required this.api, this.existing});

  final ApiClient api;
  final PromotionRecord? existing;

  @override
  State<PromotionDialog> createState() => _PromotionDialogState();
}

class _PromotionDialogState extends State<PromotionDialog> {
  static const List<String> _statuses = ['DRAFT', 'ACTIVE', 'INACTIVE'];
  static const Map<String, String> _actionLabels = {
    'LINE_DISCOUNT_PERCENT': 'Percent off each line',
    'LINE_DISCOUNT_AMOUNT': 'Amount off each line',
    'BILL_DISCOUNT_PERCENT': 'Percent off the whole bill',
    'BILL_DISCOUNT_AMOUNT': 'Amount off the whole bill',
    'FREE_QUANTITY': 'Free goods (buy X, get Y)',
    'FREE_PRODUCT': 'A free product (buy X, get another)',
    'FREE_SHIPPING': 'Free delivery',
  };

  static const int _pickerPageSize = 20;

  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  final TextEditingController _code = TextEditingController();
  final TextEditingController _name = TextEditingController();
  final TextEditingController _description = TextEditingController();
  final TextEditingController _priority = TextEditingController(text: '100');
  final TextEditingController _from = TextEditingController();
  final TextEditingController _to = TextEditingController();
  final TextEditingController _maxRedemptions = TextEditingController();
  final TextEditingController _maxPerCustomer = TextEditingController();

  String _status = 'DRAFT';
  bool _allowStacking = true;

  /// Off, the offer applies to every sale it matches; on, only to a customer
  /// presenting one of its coupons. The screen had no switch, so an offer
  /// meant for coupon holders reached everybody (D-QA-7).
  bool _requiresCoupon = false;
  List<_ActionDraft> _actions = <_ActionDraft>[_ActionDraft()];
  List<_ConditionDraft> _conditions = <_ConditionDraft>[];
  bool _saving = false;
  String? _error;

  bool get _editing => widget.existing != null;

  /// What a saved id is called, for the ids the server does not name in a
  /// list value (groups, branches, salesmen). Filled as records are picked
  /// and, for an offer being edited, read once on opening.
  final Map<String, String> _names = <String, String>{};
  int _namesVersion = 0;

  /// The category list has no server-side search, so it is read once per
  /// dialog and filtered here.
  Future<List<ProductCategoryRecord>>? _categories;

  @override
  void initState() {
    super.initState();
    final PromotionRecord? row = widget.existing;
    if (row == null) return;
    _code.text = row.code;
    _name.text = row.name;
    _description.text = row.description;
    _priority.text = '${row.priority}';
    _from.text = row.effectiveFrom;
    _to.text = row.effectiveTo;
    _status = _statuses.contains(row.status) ? row.status : 'DRAFT';
    _allowStacking = row.allowStacking;
    _requiresCoupon = row.requiresCoupon;
    _maxRedemptions.text = row.maxRedemptions?.toString() ?? '';
    _maxPerCustomer.text = row.maxRedemptionsPerCustomer?.toString() ?? '';
    _actions = row.actions.isEmpty
        ? <_ActionDraft>[_ActionDraft()]
        : row.actions.map(_ActionDraft.from).toList();
    _conditions = row.conditions.map(_ConditionDraft.from).toList();
    unawaited(_nameSavedIds());
  }

  /// A saved group, branch or salesman condition arrives as a bare id; read
  /// the three short lists once so the screen shows names, not ids.
  Future<void> _nameSavedIds() async {
    final Set<String> wanted = <String>{
      for (final _ConditionDraft c in _conditions) c.fieldKey,
    };
    try {
      if (wanted.contains('customer_group_id')) {
        final PagedResult<CustomerGroup> page =
            await widget.api.customerGroups(pageSize: 100);
        for (final CustomerGroup g in page.items) {
          _names[g.id] = _coded(g.code, g.name);
        }
      }
      if (wanted.contains('branch_id')) {
        final PagedResult<BranchRecord> page =
            await widget.api.branches(pageSize: 100);
        for (final BranchRecord b in page.items) {
          _names[b.id] = _coded(b.code, b.name);
        }
      }
      if (wanted.contains('salesman_id')) {
        for (final FirmMember m in await widget.api.firmMembers()) {
          _names[m.userId] = m.label;
        }
      }
    } on Exception {
      return;
    }
    if (!mounted) return;
    setState(() {
      _namesVersion++;
      for (final _ConditionDraft c in _conditions) {
        if (c.label.isNotEmpty && c.label == c.valueText.text) {
          c.label = _names[c.valueText.text] ?? c.label;
        }
        c.values = [
          for (final _PickOption v in c.values)
            _PickOption(v.id, _names[v.id] ?? v.label),
        ];
      }
    });
  }

  @override
  void dispose() {
    for (final _ConditionDraft c in _conditions) {
      c.dispose();
    }
    _code.dispose();
    _name.dispose();
    _description.dispose();
    _priority.dispose();
    _from.dispose();
    _to.dispose();
    _maxRedemptions.dispose();
    _maxPerCustomer.dispose();
    super.dispose();
  }

  Json _payload() => <String, dynamic>{
        'code': _code.text.trim(),
        'name': _name.text.trim(),
        if (_description.text.trim().isNotEmpty)
          'description': _description.text.trim(),
        'priority': int.tryParse(_priority.text.trim()) ?? 100,
        'status': _status,
        'allow_stacking': _allowStacking,
        // Sent every time: an update replaces the offer, so leaving these
        // out would clear a coupon rule or a limit set anywhere else.
        'requires_coupon': _requiresCoupon,
        'max_redemptions': int.tryParse(_maxRedemptions.text.trim()),
        'max_redemptions_per_customer':
            int.tryParse(_maxPerCustomer.text.trim()),
        if (_from.text.trim().isNotEmpty) 'effective_from': _from.text.trim(),
        if (_to.text.trim().isNotEmpty) 'effective_to': _to.text.trim(),
        'conditions': [
          for (int index = 0; index < _conditions.length; index++)
            _conditions[index].toJson(index + 1),
        ],
        'actions': [
          for (int index = 0; index < _actions.length; index++)
            _actions[index].toJson(index + 1),
        ],
      };

  /// Blank is no limit; anything else must be a whole number of 1 or more.
  String? _optionalLimit(String? value) {
    final String text = value?.trim() ?? '';
    if (text.isEmpty) return null;
    final int? parsed = int.tryParse(text);
    return parsed == null || parsed < 1
        ? 'A whole number of 1 or more, or blank'
        : null;
  }

  /// What the server would refuse about a condition, said before it is sent:
  /// an `IN` with nothing in it, a `BETWEEN` without two numbers, a test with
  /// no value to compare against.
  String? _conditionProblem() {
    for (final _ConditionDraft c in _conditions) {
      final String name = promotionFieldLabels[c.fieldKey] ?? c.fieldKey;
      final String op = c.operator;
      if (promotionUnaryOperators.contains(op)) continue;
      if (promotionListOperators.contains(op)) {
        if (c.values.isEmpty) {
          return 'Add at least one value to the "$name" condition.';
        }
      } else if (op == 'BETWEEN') {
        if (num.tryParse(c.low.text.trim()) == null ||
            num.tryParse(c.high.text.trim()) == null) {
          return 'The "$name" condition needs two numbers.';
        }
      } else {
        final String kind = _kindOfField(c.fieldKey);
        final bool blank = switch (kind) {
          'number' => c.valueNumber.text.trim().isEmpty,
          'date' => DateTime.tryParse(c.valueDate.text.trim()) == null,
          _ => c.valueText.text.trim().isEmpty,
        };
        if (blank) {
          return kind == 'date'
              ? 'The "$name" condition needs a date (YYYY-MM-DD).'
              : 'The "$name" condition needs a value.';
        }
      }
    }
    return null;
  }

  Future<void> _save() async {
    if (!(_form.currentState?.validate() ?? false)) return;
    final String? problem = _conditionProblem();
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final PromotionRecord? existing = widget.existing;
      if (existing == null) {
        await widget.api.createPromotion(_payload());
      } else {
        await widget.api.updatePromotion(
          existing.id,
          _payload(),
          expectedVersion: existing.version,
        );
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        // The dialog stays open, so the typing survives a refusal and the
        // message says so.
        _error = saveFailureMessage(error, 'promotion', changesKept: true);
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text(_editing ? 'Edit promotion' : 'New promotion'),
      content: SizedBox(
        width: 820,
        child: Form(
          key: _form,
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: TextFormField(
                        controller: _code,
                        enabled: !_editing,
                        decoration: const InputDecoration(labelText: 'Code'),
                        validator: (value) => (value ?? '').trim().isEmpty
                            ? 'A promotion needs a code.'
                            : null,
                      ),
                    ),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      flex: 2,
                      child: TextFormField(
                        controller: _name,
                        decoration: const InputDecoration(labelText: 'Name'),
                        validator: (value) => (value ?? '').trim().isEmpty
                            ? 'A promotion needs a name.'
                            : null,
                      ),
                    ),
                  ],
                ),
                TextFormField(
                  controller: _description,
                  decoration: const InputDecoration(labelText: 'Description'),
                ),
                const SizedBox(height: AppSpacing.md),
                Row(
                  children: [
                    Expanded(
                      child: TextFormField(
                        controller: _priority,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          labelText: 'Applies at',
                          helperText: 'Lowest first',
                        ),
                      ),
                    ),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: DropdownButtonFormField<String>(
                        isExpanded: true,
                        initialValue: _status,
                        decoration: const InputDecoration(labelText: 'Status'),
                        items: [
                          for (final String value in _statuses)
                            DropdownMenuItem(value: value, child: Text(value)),
                        ],
                        onChanged: (value) =>
                            setState(() => _status = value ?? _status),
                      ),
                    ),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: TextFormField(
                        controller: _from,
                        decoration: const InputDecoration(
                          labelText: 'From',
                          hintText: 'YYYY-MM-DD',
                        ),
                      ),
                    ),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: TextFormField(
                        controller: _to,
                        decoration: const InputDecoration(
                          labelText: 'Until',
                          hintText: 'YYYY-MM-DD',
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.md),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  value: _allowStacking,
                  onChanged: (value) => setState(() => _allowStacking = value),
                  title: const Text('Other promotions may still apply'),
                  subtitle: Text(
                    _allowStacking
                        ? 'Percentages compound on what is left, so two ten '
                            'percent offers take nineteen percent, not twenty.'
                        : 'This offer ends the stack: nothing after it applies.',
                    style: theme.textTheme.bodySmall,
                  ),
                ),
                SwitchListTile(
                  key: const ValueKey('promotion-requires-coupon'),
                  contentPadding: EdgeInsets.zero,
                  value: _requiresCoupon,
                  onChanged: (value) => setState(() => _requiresCoupon = value),
                  title: const Text('Only with a coupon'),
                  subtitle: Text(
                    _requiresCoupon
                        ? 'Applies only when the customer presents one of '
                            "this offer's coupons. Mint them under Coupons."
                        : 'Applies to every sale that meets the conditions.',
                    style: theme.textTheme.bodySmall,
                  ),
                ),
                Row(
                  children: [
                    Expanded(
                      child: TextFormField(
                        key: const ValueKey('promotion-max-redemptions'),
                        validator: _optionalLimit,
                        controller: _maxRedemptions,
                        decoration: const InputDecoration(
                          labelText: 'Total uses',
                          helperText: 'Blank = no limit',
                        ),
                      ),
                    ),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: TextFormField(
                        key: const ValueKey('promotion-max-per-customer'),
                        validator: _optionalLimit,
                        controller: _maxPerCustomer,
                        decoration: const InputDecoration(
                          labelText: 'Uses per customer',
                          helperText: 'Blank = no limit',
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.md),
                Text('Gives', style: theme.textTheme.titleSmall),
                for (int index = 0; index < _actions.length; index++)
                  _actionRow(index),
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    onPressed: () =>
                        setState(() => _actions.add(_ActionDraft())),
                    icon: const Icon(Icons.add, size: 18),
                    label: const Text('Add benefit'),
                  ),
                ),
                const SizedBox(height: AppSpacing.md),
                Text('Applies when', style: theme.textTheme.titleSmall),
                Text(
                  'No conditions means every line qualifies.',
                  style: theme.textTheme.bodySmall,
                ),
                for (int index = 0; index < _conditions.length; index++)
                  _conditionRow(index),
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    onPressed: () =>
                        setState(() => _conditions.add(_ConditionDraft())),
                    icon: const Icon(Icons.add, size: 18),
                    label: const Text('Add condition'),
                  ),
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

  Widget _actionRow(int index) {
    final _ActionDraft action = _actions[index];
    final bool isPercent = action.actionType.endsWith('_PERCENT');
    final bool isFree = action.actionType == 'FREE_QUANTITY';
    final bool isGift = action.actionType == 'FREE_PRODUCT';
    final bool isShipping = action.actionType == 'FREE_SHIPPING';
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 3,
            child: DropdownButtonFormField<String>(
              initialValue: action.actionType,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Benefit'),
              items: [
                for (final MapEntry<String, String> entry
                    in _actionLabels.entries)
                  DropdownMenuItem(value: entry.key, child: Text(entry.value)),
              ],
              onChanged: (value) => setState(
                () => action.actionType = value ?? action.actionType,
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          if (isShipping)
            const Expanded(
              child: Padding(
                padding: EdgeInsets.only(top: AppSpacing.md),
                child: Text('The delivery charge is waived whole.'),
              ),
            )
          else if (isGift) ...[
            Expanded(
              flex: 2,
              child: _searchBox(
                key: ObjectKey((action, 'gift', _namesVersion)),
                source: 'product_id',
                label: 'Product given away',
                initial: action.freeProductLabel,
                onSelected: (option) {
                  action.freeProductId = option.id;
                  action.freeProductLabel = option.label;
                },
                onTyped: (text) {
                  if (text != action.freeProductLabel) {
                    action.freeProductId = '';
                    action.freeProductLabel = '';
                  }
                },
                validator: (text) => action.freeProductId.isEmpty
                    ? 'Pick the product to give away.'
                    : null,
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: TextFormField(
                controller: action.buyQuantity,
                decoration: const InputDecoration(
                  labelText: 'Buy',
                  helperText: 'Blank = every order',
                ),
                keyboardType: TextInputType.number,
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: TextFormField(
                controller: action.freeQuantity,
                decoration: const InputDecoration(labelText: 'Get free'),
                keyboardType: TextInputType.number,
                validator: (value) =>
                    (double.tryParse((value ?? '').trim()) ?? 0) <= 0
                        ? 'How many?'
                        : null,
              ),
            ),
          ] else if (isFree) ...[
            Expanded(
              child: TextFormField(
                controller: action.buyQuantity,
                decoration: const InputDecoration(labelText: 'Buy'),
                keyboardType: TextInputType.number,
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: TextFormField(
                controller: action.freeQuantity,
                decoration: const InputDecoration(labelText: 'Get free'),
                keyboardType: TextInputType.number,
              ),
            ),
          ] else
            Expanded(
              child: TextFormField(
                controller: isPercent ? action.percent : action.amount,
                decoration: InputDecoration(
                  labelText: isPercent ? 'Percent' : 'Amount',
                ),
                keyboardType: TextInputType.number,
                validator: (value) => (value ?? '').trim().isEmpty
                    ? 'A benefit needs a figure.'
                    : null,
              ),
            ),
          // "20% off, up to 500": the cap on the whole document (60 item 1).
          if (isPercent) ...[
            const SizedBox(width: AppSpacing.sm),
            SizedBox(
              width: 120,
              child: TextFormField(
                key: ValueKey('promotion-action-cap-$index'),
                controller: action.maxAmount,
                decoration: const InputDecoration(
                  labelText: 'Up to',
                  helperText: 'Blank: no cap',
                ),
                keyboardType: TextInputType.number,
              ),
            ),
          ],
          IconButton(
            tooltip: 'Remove benefit',
            onPressed: _actions.length == 1
                ? null
                : () => setState(() => _actions.removeAt(index)),
            icon: const Icon(Icons.close, size: 18),
          ),
        ],
      ),
    );
  }

  /// The records a picker offers for [fieldKey], searched on the server as
  /// the person types, shown as "CODE — name".
  Future<List<_PickOption>> _options(String fieldKey, String text) async {
    final String search = text.trim();
    try {
      switch (fieldKey) {
        case 'product_id':
          final PagedResult<Product> page = await widget.api
              .products(search: search, pageSize: _pickerPageSize);
          return [
            for (final Product item in page.items)
              _PickOption(item.id, _coded(item.code, item.name)),
          ];
        case 'customer_id':
          final PagedResult<Customer> page = await widget.api
              .customers(search: search, pageSize: _pickerPageSize);
          return [
            for (final Customer item in page.items)
              _PickOption(
                item.id,
                _coded(
                  item.code,
                  item.displayName.isNotEmpty ? item.displayName : item.name,
                ),
              ),
          ];
        case 'product_category_id':
          final List<ProductCategoryRecord> all =
              await (_categories ??= widget.api.productCategories());
          final String needle = search.toLowerCase();
          return [
            for (final ProductCategoryRecord item in all.where((item) =>
                needle.isEmpty ||
                item.code.toLowerCase().contains(needle) ||
                item.name.toLowerCase().contains(needle)))
              _PickOption(item.id, _coded(item.code, item.name)),
          ].take(_pickerPageSize).toList();
        case 'customer_group_id':
          final PagedResult<CustomerGroup> page = await widget.api
              .customerGroups(search: search, pageSize: _pickerPageSize);
          return [
            for (final CustomerGroup item in page.items)
              _named(item.id, _coded(item.code, item.name)),
          ];
        case 'branch_id':
          final PagedResult<BranchRecord> page = await widget.api
              .branches(search: search, pageSize: _pickerPageSize);
          return [
            for (final BranchRecord item in page.items)
              _named(item.id, _coded(item.code, item.name)),
          ];
        case 'salesman_id':
          final String needle = search.toLowerCase();
          return [
            for (final FirmMember item in await widget.api.firmMembers())
              if (needle.isEmpty ||
                  item.label.toLowerCase().contains(needle) ||
                  item.email.toLowerCase().contains(needle))
                _named(item.userId, item.label),
          ].take(_pickerPageSize).toList();
        case 'territory_id':
          final PagedResult<SalesTerritory> page = await widget.api
              .territories(search: search, pageSize: _pickerPageSize);
          return [
            for (final SalesTerritory item in page.items)
              _PickOption(item.id, _coded(item.code, item.name)),
          ];
        case 'route_id':
          // A route is a territory node with a route profile, and the id a
          // condition holds is the profile's. Nothing lists routes alone, so
          // a wider page is read and the plain nodes are dropped.
          final PagedResult<SalesTerritory> page =
              await widget.api.territories(search: search, pageSize: 100);
          return [
            for (final SalesTerritory item in page.items)
              if (!item.isDeleted &&
                  (item.routeProfile?.id.isNotEmpty ?? false))
                _PickOption(
                  item.routeProfile!.id,
                  _coded(item.code, item.name),
                ),
          ].take(_pickerPageSize).toList();
      }
    } on Exception {
      return const <_PickOption>[];
    }
    return const <_PickOption>[];
  }

  static String _coded(String code, String name) =>
      code.isEmpty ? name : '$code — $name';

  /// An option that is also remembered by id, so a list of them can be named
  /// again after the picker that offered them is gone.
  _PickOption _named(String id, String label) {
    _names[id] = label;
    return _PickOption(id, label);
  }

  /// A search-as-you-type box over [source], shown as "CODE — name".
  Widget _searchBox({
    required Object key,
    required String source,
    required String label,
    String initial = '',
    required void Function(_PickOption option) onSelected,
    void Function(String text)? onTyped,
    String? Function(String? text)? validator,
    bool clearOnSelect = false,
  }) {
    TextEditingController? box;
    return Autocomplete<_PickOption>(
      key: ObjectKey(key),
      initialValue: TextEditingValue(text: initial),
      displayStringForOption: (option) => option.label,
      optionsBuilder: (value) => _options(source, value.text),
      onSelected: (option) {
        onSelected(option);
        if (clearOnSelect) box?.clear();
      },
      fieldViewBuilder: (context, controller, focusNode, onSubmitted) {
        box = controller;
        return TextFormField(
          controller: controller,
          focusNode: focusNode,
          decoration: InputDecoration(
            labelText: label,
            helperText: 'Type to search',
            suffixIcon: const Icon(Icons.search, size: 18),
          ),
          onChanged: onTyped,
          validator: validator,
        );
      },
    );
  }

  Widget _idPicker(_ConditionDraft condition) {
    final String field =
        promotionFieldLabels[condition.fieldKey] ?? condition.fieldKey;
    return _searchBox(
      key: (condition, condition.fieldKey, _namesVersion),
      source: condition.fieldKey,
      label: field,
      initial: condition.label,
      onSelected: (option) {
        condition.valueText.text = option.id;
        condition.label = option.label;
      },
      // Typing over a chosen record un-chooses it: the id must never
      // disagree with the name on the screen.
      onTyped: (text) {
        if (text != condition.label) {
          condition.valueText.clear();
          condition.label = '';
        }
      },
      validator: (text) =>
          (text ?? '').trim().isNotEmpty && condition.valueText.text.isEmpty
              ? 'Pick one from the list.'
              : null,
    );
  }

  Widget _dateBox(TextEditingController controller, String label) {
    return TextFormField(
      controller: controller,
      decoration: InputDecoration(
        labelText: label,
        hintText: 'YYYY-MM-DD',
        suffixIcon: IconButton(
          tooltip: 'Pick a date',
          icon: const Icon(Icons.calendar_today, size: 16),
          onPressed: () async {
            final DateTime? picked = await showDatePicker(
              context: context,
              initialDate:
                  DateTime.tryParse(controller.text.trim()) ?? DateTime.now(),
              firstDate: DateTime(2000),
              lastDate: DateTime(2100),
            );
            if (picked == null) return;
            controller.text = '${picked.year.toString().padLeft(4, '0')}-'
                '${picked.month.toString().padLeft(2, '0')}-'
                '${picked.day.toString().padLeft(2, '0')}';
          },
        ),
      ),
    );
  }

  /// The value input that suits this field *and* this test.
  Widget _valueInput(_ConditionDraft condition) {
    final String op = condition.operator;
    final String kind = _kindOfField(condition.fieldKey);
    if (promotionUnaryOperators.contains(op)) {
      return Padding(
        padding: const EdgeInsets.only(top: AppSpacing.md),
        child: Text(
          'Nothing to enter.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
      );
    }
    if (promotionListOperators.contains(op)) return _listInput(condition);
    if (op == 'BETWEEN') {
      return Row(
        children: [
          Expanded(
            child: TextFormField(
              controller: condition.low,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Min'),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: TextFormField(
              controller: condition.high,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Max'),
            ),
          ),
        ],
      );
    }
    switch (kind) {
      case 'id':
        return _idPicker(condition);
      case 'type':
        return DropdownButtonFormField<String>(
          key: ObjectKey((condition, 'type', condition.fieldKey)),
          isExpanded: true,
          initialValue: promotionTransactionTypeLabels
                  .containsKey(condition.valueText.text)
              ? condition.valueText.text
              : null,
          decoration: const InputDecoration(labelText: 'Document'),
          items: [
            for (final MapEntry<String, String> entry
                in promotionTransactionTypeLabels.entries)
              DropdownMenuItem(value: entry.key, child: Text(entry.value)),
          ],
          onChanged: (value) => condition.valueText.text = value ?? '',
        );
      case 'date':
        return _dateBox(condition.valueDate, 'Date');
      case 'number':
        return TextFormField(
          controller: condition.valueNumber,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Value'),
        );
    }
    return TextFormField(
      controller: condition.valueText,
      decoration: const InputDecoration(labelText: 'Value'),
    );
  }

  /// Several values for `IN` / `NOT_IN`: chips for what is chosen and a way
  /// to add one more.
  Widget _listInput(_ConditionDraft condition) {
    final String kind = _kindOfField(condition.fieldKey);
    final Widget adder;
    if (kind == 'type') {
      adder = Wrap(
        spacing: AppSpacing.xs,
        children: [
          for (final MapEntry<String, String> entry
              in promotionTransactionTypeLabels.entries)
            FilterChip(
              label: Text(entry.value),
              selected: condition.values.any((v) => v.id == entry.key),
              onSelected: (on) => setState(() {
                condition.values.removeWhere((v) => v.id == entry.key);
                if (on) {
                  condition.values.add(_PickOption(entry.key, entry.value));
                }
              }),
            ),
        ],
      );
    } else if (kind == 'id') {
      adder = _searchBox(
        key: (condition, condition.fieldKey, 'add'),
        source: condition.fieldKey,
        label: 'Add one',
        clearOnSelect: true,
        onSelected: (option) {
          if (condition.values.any((v) => v.id == option.id)) return;
          setState(() => condition.values.add(option));
        },
      );
    } else {
      void add() {
        final String text = condition.adder.text.trim();
        if (text.isEmpty || condition.values.any((v) => v.id == text)) return;
        setState(() {
          condition.values.add(_PickOption(text, text));
          condition.adder.clear();
        });
      }

      adder = TextField(
        controller: condition.adder,
        decoration: InputDecoration(
          labelText: 'Add a value',
          suffixIcon: IconButton(
            tooltip: 'Add',
            icon: const Icon(Icons.add, size: 18),
            onPressed: add,
          ),
        ),
        onSubmitted: (_) => add(),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (kind != 'type' && condition.values.isNotEmpty)
          Wrap(
            spacing: AppSpacing.xs,
            runSpacing: AppSpacing.xs,
            children: [
              for (final _PickOption option in condition.values)
                InputChip(
                  label: Text(option.label),
                  onDeleted: () =>
                      setState(() => condition.values.remove(option)),
                ),
            ],
          ),
        adder,
      ],
    );
  }

  Widget _conditionRow(int index) {
    final _ConditionDraft condition = _conditions[index];
    final List<String> operators = _operatorsFor(condition.fieldKey);
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 2,
            child: DropdownButtonFormField<String>(
              initialValue: condition.fieldKey,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'When'),
              items: [
                for (final MapEntry<String, String> entry
                    in promotionFieldLabels.entries)
                  DropdownMenuItem(value: entry.key, child: Text(entry.value)),
              ],
              onChanged: (value) => setState(() {
                final String next = value ?? condition.fieldKey;
                if (next == condition.fieldKey) return;
                // A value chosen for one kind of field means nothing to
                // another, and an id picked for one kind of record even less.
                condition.clearValues();
                condition.fieldKey = next;
                if (!_operatorsFor(next).contains(condition.operator)) {
                  condition.operator = 'EQUALS';
                }
              }),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: DropdownButtonFormField<String>(
              key: ObjectKey((condition, 'op', condition.operator)),
              initialValue: condition.operator,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Test'),
              items: [
                for (final String key in <String>{
                  ...operators,
                  condition.operator,
                })
                  DropdownMenuItem(
                    value: key,
                    child: Text(promotionOperatorLabels[key] ?? key),
                  ),
              ],
              onChanged: (value) => setState(
                () => condition.operator = value ?? condition.operator,
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            flex: 2,
            child: _valueInput(condition),
          ),
          IconButton(
            tooltip: 'Remove condition',
            onPressed: () => setState(() => _conditions.removeAt(index)),
            icon: const Icon(Icons.close, size: 18),
          ),
        ],
      ),
    );
  }
}

/// One benefit being edited.
class _ActionDraft {
  _ActionDraft();

  factory _ActionDraft.from(PromotionActionRecord record) {
    final _ActionDraft draft = _ActionDraft()..actionType = record.actionType;
    draft.percent.text = record.percent;
    draft.amount.text = record.amount;
    draft.buyQuantity.text = record.buyQuantity;
    draft.freeQuantity.text = record.freeQuantity;
    draft.freeProductId = record.freeProductId;
    draft.maxAmount.text = record.maxAmount;
    // Nothing reads one product by id, so a saved gift is named generically
    // until somebody searches for another.
    draft.freeProductLabel =
        record.freeProductId.isEmpty ? '' : 'Product chosen earlier';
    return draft;
  }

  String actionType = 'LINE_DISCOUNT_PERCENT';
  final TextEditingController percent = TextEditingController();
  final TextEditingController amount = TextEditingController();
  final TextEditingController buyQuantity = TextEditingController();
  final TextEditingController freeQuantity = TextEditingController();
  final TextEditingController maxAmount = TextEditingController();
  String freeProductId = '';
  String freeProductLabel = '';

  /// Only the figures this benefit reads: a figure typed for another benefit
  /// and then switched away from must not ride along.
  Json toJson(int sequence) => PromotionActionRecord(
        actionType: actionType,
        sequence: sequence,
        percent: actionType.endsWith('_PERCENT') ? percent.text : '',
        amount: actionType.endsWith('_AMOUNT') ? amount.text : '',
        buyQuantity:
            actionType == 'FREE_QUANTITY' || actionType == 'FREE_PRODUCT'
                ? buyQuantity.text
                : '',
        freeQuantity:
            actionType == 'FREE_QUANTITY' || actionType == 'FREE_PRODUCT'
                ? freeQuantity.text
                : '',
        freeProductId: actionType == 'FREE_PRODUCT' ? freeProductId : '',
        maxAmount: actionType.endsWith('_PERCENT') ? maxAmount.text : '',
      ).toJson();
}

/// One record a condition picker offers.
class _PickOption {
  const _PickOption(this.id, this.label);

  final String id;
  final String label;

  @override
  String toString() => label;
}

/// How a field's value is entered: `id` (picked), `type` (one of the
/// document types), `date`, `number`, or plain `text`.
String _kindOfField(String fieldKey) {
  switch (fieldKey) {
    case 'product_id':
    case 'product_category_id':
    case 'customer_id':
    case 'customer_group_id':
    case 'branch_id':
    case 'territory_id':
    case 'route_id':
    case 'salesman_id':
      return 'id';
    case 'transaction_type':
      return 'type';
    case 'transaction_date':
      return 'date';
    case 'line_quantity':
    case 'line_gross':
    case 'document_gross':
      return 'number';
  }
  return 'text';
}

/// The tests that mean something for a field. The server can order only
/// numbers and dates, and `BETWEEN` only numbers; "is set" is pointless for a
/// value every line has.
List<String> _operatorsFor(String fieldKey) => switch (_kindOfField(fieldKey)) {
      'number' => const <String>[
          'EQUALS',
          'NOT_EQUALS',
          'GREATER_OR_EQUAL',
          'GREATER_THAN',
          'LESS_OR_EQUAL',
          'LESS_THAN',
          'BETWEEN',
        ],
      'date' => const <String>[
          'EQUALS',
          'NOT_EQUALS',
          'GREATER_OR_EQUAL',
          'GREATER_THAN',
          'LESS_OR_EQUAL',
          'LESS_THAN',
        ],
      _ => const <String>[
          'EQUALS',
          'NOT_EQUALS',
          'IN',
          'NOT_IN',
          'EXISTS',
          'NOT_EXISTS',
        ],
    };

/// One condition being edited.
class _ConditionDraft {
  _ConditionDraft();

  factory _ConditionDraft.from(PromotionConditionRecord record) {
    final _ConditionDraft draft = _ConditionDraft()
      ..fieldKey = record.fieldKey
      ..operator = record.operator;
    draft.valueText.text = record.valueText;
    draft.valueNumber.text = record.valueNumber;
    draft.valueDate.text = record.valueDate;
    if (record.operator == 'BETWEEN' && record.valueList.length == 2) {
      draft.low.text = record.valueList[0];
      draft.high.text = record.valueList[1];
    } else {
      draft.values = [
        for (final String id in record.valueList) _PickOption(id, id),
      ];
    }
    // An id the server could not name is still shown, rather than a blank
    // that would read as "no value".
    draft.label =
        record.valueLabel.isNotEmpty ? record.valueLabel : record.valueText;
    return draft;
  }

  String fieldKey = 'product_category_id';
  String operator = 'EQUALS';

  /// What the picker shows for the id in [valueText].
  String label = '';
  final TextEditingController valueText = TextEditingController();
  final TextEditingController valueNumber = TextEditingController();
  final TextEditingController valueDate = TextEditingController();

  /// The bounds of a `BETWEEN`.
  final TextEditingController low = TextEditingController();
  final TextEditingController high = TextEditingController();

  /// The chosen values of an `IN` / `NOT_IN`.
  List<_PickOption> values = <_PickOption>[];

  /// Where a typed value waits until it is added to [values].
  final TextEditingController adder = TextEditingController();

  /// Forget every value, because the field it was entered for has changed.
  void clearValues() {
    valueText.clear();
    valueNumber.clear();
    valueDate.clear();
    low.clear();
    high.clear();
    adder.clear();
    values = <_PickOption>[];
    label = '';
  }

  void dispose() {
    valueText.dispose();
    valueNumber.dispose();
    valueDate.dispose();
    low.dispose();
    high.dispose();
    adder.dispose();
  }

  Json toJson(int sequence) {
    final String kind = _kindOfField(fieldKey);
    return PromotionConditionRecord(
      fieldKey: fieldKey,
      operator: operator,
      sequence: sequence,
      valueText: kind == 'number' || kind == 'date' ? '' : valueText.text,
      valueNumber: kind == 'number' ? valueNumber.text : '',
      valueDate: kind == 'date' ? valueDate.text : '',
      valueList: operator == 'BETWEEN'
          ? <String>[low.text, high.text]
          : <String>[for (final _PickOption v in values) v.id],
    ).toJson();
  }
}
