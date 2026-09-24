import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/design/design_tokens.dart';
import '../../models/customer.dart';
import '../../models/entities.dart';
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
  };

  /// The condition fields that name a record, and so are picked rather than
  /// typed as an id (BL-31.15).
  static const Set<String> _idFields = <String>{
    'product_id',
    'product_category_id',
    'customer_id',
    'territory_id',
    'route_id',
  };
  static const int _pickerPageSize = 20;

  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  final TextEditingController _code = TextEditingController();
  final TextEditingController _name = TextEditingController();
  final TextEditingController _description = TextEditingController();
  final TextEditingController _priority = TextEditingController(text: '100');
  final TextEditingController _from = TextEditingController();
  final TextEditingController _to = TextEditingController();

  String _status = 'DRAFT';
  bool _allowStacking = true;
  List<_ActionDraft> _actions = <_ActionDraft>[_ActionDraft()];
  List<_ConditionDraft> _conditions = <_ConditionDraft>[];
  bool _saving = false;
  String? _error;

  bool get _editing => widget.existing != null;

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
    _actions = row.actions.isEmpty
        ? <_ActionDraft>[_ActionDraft()]
        : row.actions.map(_ActionDraft.from).toList();
    _conditions = row.conditions.map(_ConditionDraft.from).toList();
  }

  @override
  void dispose() {
    _code.dispose();
    _name.dispose();
    _description.dispose();
    _priority.dispose();
    _from.dispose();
    _to.dispose();
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

  Future<void> _save() async {
    if (!(_form.currentState?.validate() ?? false)) return;
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
        _error =
            saveFailureMessage(error, 'promotion', changesKept: true);
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
        width: 720,
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
                        decoration:
                            const InputDecoration(labelText: 'Status'),
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
          if (isFree) ...[
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

  Widget _idPicker(_ConditionDraft condition) {
    final String field =
        promotionFieldLabels[condition.fieldKey] ?? condition.fieldKey;
    return Autocomplete<_PickOption>(
      key: ObjectKey((condition, condition.fieldKey)),
      initialValue: TextEditingValue(text: condition.label),
      displayStringForOption: (option) => option.label,
      optionsBuilder: (value) => _options(condition.fieldKey, value.text),
      onSelected: (option) {
        condition.valueText.text = option.id;
        condition.label = option.label;
      },
      fieldViewBuilder: (context, controller, focusNode, onSubmitted) =>
          TextFormField(
        controller: controller,
        focusNode: focusNode,
        decoration: InputDecoration(
          labelText: field,
          helperText: 'Type to search',
          suffixIcon: const Icon(Icons.search, size: 18),
        ),
        // Typing over a chosen record un-chooses it: the id must never
        // disagree with the name on the screen.
        onChanged: (text) {
          if (text != condition.label) {
            condition.valueText.clear();
            condition.label = '';
          }
        },
        validator: (text) =>
            (text ?? '').trim().isNotEmpty && condition.valueText.text.isEmpty
                ? 'Pick one from the list.'
                : null,
      ),
    );
  }

  Widget _conditionRow(int index) {
    final _ConditionDraft condition = _conditions[index];
    final bool numeric = condition.fieldKey.endsWith('_quantity') ||
        condition.fieldKey.endsWith('_gross');
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
                // An id picked for one kind of record means nothing to
                // another.
                if (_idFields.contains(condition.fieldKey) ||
                    _idFields.contains(next)) {
                  condition.valueText.clear();
                  condition.label = '';
                }
                condition.fieldKey = next;
              }),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: DropdownButtonFormField<String>(
              initialValue: condition.operator,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Test'),
              items: [
                for (final MapEntry<String, String> entry
                    in promotionOperatorLabels.entries)
                  DropdownMenuItem(value: entry.key, child: Text(entry.value)),
              ],
              onChanged: (value) => setState(
                () => condition.operator = value ?? condition.operator,
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            flex: 2,
            child: _idFields.contains(condition.fieldKey)
                ? _idPicker(condition)
                : TextFormField(
                    controller:
                        numeric ? condition.valueNumber : condition.valueText,
                    decoration: const InputDecoration(labelText: 'Value'),
                  ),
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
    final _ActionDraft draft = _ActionDraft()
      ..actionType = record.actionType;
    draft.percent.text = record.percent;
    draft.amount.text = record.amount;
    draft.buyQuantity.text = record.buyQuantity;
    draft.freeQuantity.text = record.freeQuantity;
    return draft;
  }

  String actionType = 'LINE_DISCOUNT_PERCENT';
  final TextEditingController percent = TextEditingController();
  final TextEditingController amount = TextEditingController();
  final TextEditingController buyQuantity = TextEditingController();
  final TextEditingController freeQuantity = TextEditingController();

  Json toJson(int sequence) => PromotionActionRecord(
        actionType: actionType,
        sequence: sequence,
        percent: percent.text,
        amount: amount.text,
        buyQuantity: buyQuantity.text,
        freeQuantity: freeQuantity.text,
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

/// One condition being edited.
class _ConditionDraft {
  _ConditionDraft();

  factory _ConditionDraft.from(PromotionConditionRecord record) {
    final _ConditionDraft draft = _ConditionDraft()
      ..fieldKey = record.fieldKey
      ..operator = record.operator;
    draft.valueText.text = record.valueText;
    draft.valueNumber.text = record.valueNumber;
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

  Json toJson(int sequence) => PromotionConditionRecord(
        fieldKey: fieldKey,
        operator: operator,
        sequence: sequence,
        valueText: valueText.text,
        valueNumber: valueNumber.text,
      ).toJson();
}
