import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../../models/product.dart';
import '../../models/purchase.dart';
import '../../phase2/document_page.dart' show documentMoney;
import '../workspace/save_in_dialog.dart';

/// What the firm means to spend on buying, a month at a time (BUY-14).
///
/// A budget is for a month and, optionally, one branch and one product
/// category; with neither it is the firm-wide figure. Reading needs
/// `PURCHASE_VIEW`; adding, changing and removing need
/// `PURCHASE_MANAGE_SETTINGS`. What a budget has spent is the server's count
/// of the month's approved orders, shown beside it.
class PurchaseBudgetsDialog extends StatefulWidget {
  const PurchaseBudgetsDialog({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<PurchaseBudgetsDialog> createState() => _PurchaseBudgetsDialogState();
}

String _monthStart(DateTime date) =>
    '${date.year.toString().padLeft(4, '0')}-'
    '${date.month.toString().padLeft(2, '0')}-01';

const List<String> _monthNames = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

String _monthLabel(DateTime date) =>
    '${_monthNames[date.month - 1]} ${date.year}';

class _PurchaseBudgetsDialogState extends State<PurchaseBudgetsDialog> {
  late DateTime _month = DateTime(DateTime.now().year, DateTime.now().month);
  List<PurchaseBudget> _rows = const [];
  bool _loading = true;
  String? _error;

  bool get _mayManage =>
      widget.permissions.hasPermission('PURCHASE_MANAGE_SETTINGS');

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final DateTime asked = _month;
    try {
      final List<PurchaseBudget> rows =
          await widget.api.purchaseBudgets(_monthStart(asked));
      if (!mounted || asked != _month) return;
      setState(() {
        _rows = rows;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted || asked != _month) return;
      setState(() {
        _rows = const [];
        _error = error.message;
        _loading = false;
      });
    }
  }

  void _step(int months) {
    setState(() => _month = DateTime(_month.year, _month.month + months));
    unawaited(_load());
  }

  Future<void> _edit([PurchaseBudget? budget]) async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (_) => _BudgetEditDialog(
        api: widget.api,
        month: _month,
        budget: budget,
      ),
    );
    if (saved == true) await _load();
  }

  Future<void> _delete(PurchaseBudget budget) async {
    try {
      await widget.api.deletePurchaseBudget(budget.id);
      if (!mounted) return;
      NotificationService.show(
        context,
        'Budget removed.',
        kind: AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      scrollable: true,
      icon: const Icon(Icons.account_balance_wallet_outlined),
      title: const Text('Purchase budgets'),
      content: SizedBox(
        width: 640,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'What the firm means to spend on buying in a month, in total or '
              'for one branch or product category. Used is the total of the '
              "month's approved orders; an order that takes a budget past its "
              'amount is flagged, and the buying stages setting decides '
              'whether approving it needs someone who may go over budget.',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: AppSpacing.md),
            Row(
              children: [
                IconButton(
                  key: const ValueKey('budget-month-previous'),
                  tooltip: 'Previous month',
                  icon: const Icon(Icons.chevron_left),
                  onPressed: () => _step(-1),
                ),
                Expanded(
                  child: Text(
                    _monthLabel(_month),
                    key: const ValueKey('budget-month'),
                    textAlign: TextAlign.center,
                    style: theme.textTheme.titleSmall,
                  ),
                ),
                IconButton(
                  key: const ValueKey('budget-month-next'),
                  tooltip: 'Next month',
                  icon: const Icon(Icons.chevron_right),
                  onPressed: () => _step(1),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: Text(
                  _error!,
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: theme.colorScheme.error),
                ),
              ),
            if (_loading)
              const Padding(
                padding: EdgeInsets.all(AppSpacing.xl),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_rows.isEmpty && _error == null)
              Text(
                'No budget for this month.',
                key: const ValueKey('budgets-empty'),
                style: theme.textTheme.bodySmall,
              )
            else
              _grid(theme),
            const SizedBox(height: AppSpacing.md),
            Align(
              alignment: Alignment.centerLeft,
              child: OutlinedButton.icon(
                key: const ValueKey('budget-add'),
                icon: const Icon(Icons.add),
                label: const Text('Add budget'),
                onPressed: _mayManage && !_loading ? () => _edit() : null,
              ),
            ),
            if (!_mayManage) ...[
              const SizedBox(height: AppSpacing.md),
              Text(
                'Changing budgets needs the manage purchase settings '
                'permission.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }

  Widget _grid(ThemeData theme) {
    return Column(
      key: const ValueKey('budgets-grid'),
      children: [
        _line(
          theme,
          const Text('Budget'),
          const Text('Amount'),
          const Text('Used'),
          const Text('Available'),
          null,
          header: true,
        ),
        const Divider(height: 1),
        for (final PurchaseBudget row in _rows)
          _line(
            theme,
            Text(row.label, overflow: TextOverflow.ellipsis),
            Text(documentMoney(row.amount)),
            Text(documentMoney(row.used)),
            Text(
              documentMoney(row.available),
              style: (double.tryParse(row.available) ?? 0) < 0
                  ? TextStyle(color: theme.colorScheme.error)
                  : null,
            ),
            _mayManage
                ? Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      IconButton(
                        key: ValueKey('budget-edit-${row.id}'),
                        tooltip: 'Edit',
                        icon: const Icon(Icons.edit_outlined, size: 18),
                        onPressed: () => _edit(row),
                      ),
                      IconButton(
                        key: ValueKey('budget-delete-${row.id}'),
                        tooltip: 'Delete',
                        icon: const Icon(Icons.delete_outline, size: 18),
                        onPressed: () => _delete(row),
                      ),
                    ],
                  )
                : null,
          ),
      ],
    );
  }

  Widget _line(
    ThemeData theme,
    Widget label,
    Widget amount,
    Widget used,
    Widget available,
    Widget? actions, {
    bool header = false,
  }) {
    final TextStyle? style =
        header ? theme.textTheme.labelMedium : theme.textTheme.bodyMedium;
    return DefaultTextStyle.merge(
      style: style,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
        child: Row(
          children: [
            Expanded(flex: 3, child: label),
            Expanded(flex: 2, child: amount),
            Expanded(flex: 2, child: used),
            Expanded(flex: 2, child: available),
            SizedBox(width: 104, child: actions),
          ],
        ),
      ),
    );
  }
}

class _BudgetEditDialog extends StatefulWidget {
  const _BudgetEditDialog({
    required this.api,
    required this.month,
    required this.budget,
  });

  final ApiClient api;
  final DateTime month;
  final PurchaseBudget? budget;

  @override
  State<_BudgetEditDialog> createState() => _BudgetEditDialogState();
}

class _BudgetEditDialogState extends State<_BudgetEditDialog>
    with SaveInDialog<_BudgetEditDialog> {
  late DateTime _month = widget.month;
  late String? _branchId = widget.budget?.branchId;
  late String? _categoryId = widget.budget?.productCategoryId;
  late final TextEditingController _amount = TextEditingController(
    text: widget.budget?.amount ?? '',
  );
  List<BranchRecord> _branches = const [];
  List<ProductCategoryRecord> _categories = const [];

  @override
  void initState() {
    super.initState();
    if (widget.budget != null) {
      final DateTime? parsed = DateTime.tryParse(widget.budget!.budgetMonth);
      if (parsed != null) _month = DateTime(parsed.year, parsed.month);
    }
    unawaited(_loadChoices());
  }

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  Future<void> _loadChoices() async {
    try {
      final PagedResult<BranchRecord> branches =
          await widget.api.branches(pageSize: 100, sortBy: 'name');
      if (mounted) setState(() => _branches = branches.items);
    } on ApiException {
      // Without the list the budget can still be firm-wide.
    }
    try {
      final List<ProductCategoryRecord> categories =
          await widget.api.productCategories();
      if (mounted) setState(() => _categories = categories);
    } on ApiException {
      // As above.
    }
  }

  bool _inWindow(DateTime month) {
    final DateTime now = DateTime.now();
    final int diff = (month.year - now.year) * 12 + month.month - now.month;
    return diff >= -6 && diff <= 17;
  }

  List<DateTime> get _months {
    final DateTime now = DateTime.now();
    return [
      for (int i = -6; i <= 17; i++) DateTime(now.year, now.month + i),
      if (!_inWindow(_month)) _month,
    ];
  }

  Future<void> _save() => saveAndClose<bool>(() async {
        final double? amount = double.tryParse(_amount.text.trim());
        if (amount == null || amount <= 0) {
          throw ApiException('The budget must be an amount above zero.');
        }
        await widget.api.savePurchaseBudget(
          <String, dynamic>{
            'budget_month': _monthStart(_month),
            'branch_id': _branchId,
            'product_category_id': _categoryId,
            'amount': _amount.text.trim(),
          },
          id: widget.budget?.id,
        );
        return true;
      });

  @override
  Widget build(BuildContext context) {
    final Set<String> branchIds = {for (final b in _branches) b.id};
    final Set<String> categoryIds = {for (final c in _categories) c.id};
    return AlertDialog(
      scrollable: true,
      title: Text(widget.budget == null ? 'Add budget' : 'Edit budget'),
      content: SizedBox(
        width: 420,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            saveErrorBanner(),
            DropdownButtonFormField<DateTime>(
              key: const ValueKey('budget-form-month'),
              isExpanded: true,
              initialValue: _month,
              decoration: const InputDecoration(labelText: 'Month'),
              items: [
                for (final DateTime m in _months)
                  DropdownMenuItem(value: m, child: Text(_monthLabel(m))),
              ],
              onChanged: saving ? null : (m) => setState(() => _month = m!),
            ),
            const SizedBox(height: AppSpacing.md),
            DropdownButtonFormField<String?>(
              key: const ValueKey('budget-form-branch'),
              isExpanded: true,
              initialValue: branchIds.contains(_branchId) ? _branchId : null,
              decoration: const InputDecoration(
                labelText: 'Branch (optional)',
                helperText: 'Blank: every branch.',
              ),
              items: [
                const DropdownMenuItem<String?>(
                  value: null,
                  child: Text('All branches'),
                ),
                for (final BranchRecord b in _branches)
                  DropdownMenuItem<String?>(
                    value: b.id,
                    child: Text(b.name, overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: saving ? null : (v) => setState(() => _branchId = v),
            ),
            const SizedBox(height: AppSpacing.md),
            DropdownButtonFormField<String?>(
              key: const ValueKey('budget-form-category'),
              isExpanded: true,
              initialValue:
                  categoryIds.contains(_categoryId) ? _categoryId : null,
              decoration: const InputDecoration(
                labelText: 'Product category (optional)',
                helperText: 'Blank: every category.',
              ),
              items: [
                const DropdownMenuItem<String?>(
                  value: null,
                  child: Text('All categories'),
                ),
                for (final ProductCategoryRecord c in _categories)
                  DropdownMenuItem<String?>(
                    value: c.id,
                    child: Text(c.name, overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged:
                  saving ? null : (v) => setState(() => _categoryId = v),
            ),
            const SizedBox(height: AppSpacing.md),
            TextField(
              key: const ValueKey('budget-form-amount'),
              controller: _amount,
              enabled: !saving,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Amount'),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('budget-form-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}
