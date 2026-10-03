// PMT-06 deposits (GST-7): the cash a quarterly (QRMP) filer pays into the
// electronic cash ledger in the first two months of a quarter, the balance the
// ledger holds, and recording or reversing a deposit.
//
// A monthly filer has no use for the screen and is told so.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/expense.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';

const List<String> _heads = ['igst', 'cgst', 'sgst', 'cess'];

String _iso(DateTime value) => '${value.year.toString().padLeft(4, '0')}-'
    '${value.month.toString().padLeft(2, '0')}-'
    '${value.day.toString().padLeft(2, '0')}';

String _monthOf(DateTime value) => '${value.year.toString().padLeft(4, '0')}-'
    '${value.month.toString().padLeft(2, '0')}';

/// The deposits recorded, the cash ledger balance and the record action.
class GstDepositsPage extends StatefulWidget {
  const GstDepositsPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    this.today,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// For tests; the clock otherwise.
  final DateTime? today;

  @override
  State<GstDepositsPage> createState() => _GstDepositsPageState();
}

class _GstDepositsPageState extends State<GstDepositsPage> {
  Json? _plan;
  List<Json> _rows = const [];
  bool _loading = false;
  String? _error;
  String? _notice;

  bool get _canView =>
      widget.permissions.hasPermission('ACCOUNT_VIEW') ||
      widget.permissions.hasPermission('SALES_VIEW');
  bool get _canRecord => widget.permissions.hasPermission('JOURNAL_POST');
  bool get _quarterly => _plan?['filing_frequency'] == 'QUARTERLY';

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _canView) unawaited(_load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final Json plan = await widget.api.gstFilingPlan();
      final List<Json> rows = plan['filing_frequency'] == 'QUARTERLY'
          ? await widget.api.gstCashDeposits()
          : const <Json>[];
      if (!mounted) return;
      setState(() {
        _plan = plan;
        _rows = rows;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _plan = null;
        _rows = const [];
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _record() async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (context) => _DepositDialog(
        api: widget.api,
        today: widget.today ?? DateTime.now(),
        method: '${_plan?['qrmp_payment_method'] ?? 'FIXED_SUM'}',
      ),
    );
    if (saved == true && mounted) {
      setState(() => _notice = 'PMT-06 deposit recorded.');
      await _load();
    }
  }

  Future<void> _reverse(Json row) async {
    final String? reason = await askForReason(
      context,
      title: 'Reverse the deposit for ${row['return_period']}',
      explanation: 'The deposit is taken back with a mirror journal.',
      confirmLabel: 'Reverse',
    );
    if (reason == null || !mounted) return;
    try {
      await widget.api.reverseGstCashDeposit('${row['id']}', reason);
      if (!mounted) return;
      setState(() => _notice = 'Deposit for ${row['return_period']} reversed.');
      await _load();
    } on ApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'PMT-06 deposits',
        message: 'You do not have permission to view GST deposits.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'PMT-06 deposits',
        message: 'Choose a firm to see its deposits.',
      );
    }
    final ThemeData theme = Theme.of(context);
    final Json? plan = _plan;
    if (plan != null && !_quarterly) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'No deposits to make',
        message: 'PMT-06 deposits are for quarterly (QRMP) filers. This firm '
            'files monthly; change that under the GST document settings.',
      );
    }
    final Map<String, dynamic> ledger =
        plan?['cash_ledger'] is Map
            ? Map<String, dynamic>.from(plan!['cash_ledger'] as Map)
            : const <String, dynamic>{};
    return LoadingOverlay(
      loading: _loading,
      child: ListView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        children: [
          Wrap(
            spacing: AppSpacing.md,
            runSpacing: AppSpacing.sm,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Phase2Refresh(
                onPressed: _loading ? null : () => unawaited(_load()),
                child: const SizedBox.shrink(),
              ),
              if (_canRecord && _quarterly)
                FilledButton.icon(
                  key: const ValueKey('gst-deposit-record'),
                  onPressed: _loading ? null : () => unawaited(_record()),
                  icon: const Icon(Icons.add, size: 18),
                  label: const Text('Record deposit'),
                ),
            ],
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(_error!,
                  style: TextStyle(color: theme.colorScheme.error)),
            ),
          if (_notice != null)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(_notice!, style: theme.textTheme.bodyMedium),
            ),
          if (plan != null) ...[
            const SizedBox(height: AppSpacing.md),
            Text('Cash ledger balance', style: theme.textTheme.titleSmall),
            const SizedBox(height: AppSpacing.xs),
            Text(
              key: const ValueKey('gst-deposit-ledger'),
              [
                for (final String head in _heads)
                  '${head.toUpperCase()} ${stringValue(ledger[head])}',
              ].join('   '),
              style: theme.textTheme.bodyMedium,
            ),
          ],
          const Divider(height: AppSpacing.xl),
          Text('Deposits recorded', style: theme.textTheme.titleSmall),
          if (_rows.isEmpty)
            Text('None yet.', style: theme.textTheme.bodySmall),
          for (final Json row in _rows)
            ListTile(
              key: ValueKey('gst-deposit-${row['return_period']}'),
              dense: true,
              title: Text('${row['return_period']}  ${row['status']}  '
                  '${stringValue(row['total'])}'),
              subtitle: Text(
                'Deposited ${row['deposit_date']} · '
                '${'${row['method']}' == 'SELF_ASSESSMENT' ? 'self-assessment' : 'fixed sum'}'
                '${stringValue(row['challan_cpin']).isEmpty ? '' : ' · CPIN ${row['challan_cpin']}'}',
              ),
              trailing: _canRecord && row['status'] == 'POSTED'
                  ? TextButton(
                      key: ValueKey('gst-deposit-reverse-${row['return_period']}'),
                      onPressed: () => unawaited(_reverse(row)),
                      child: const Text('Reverse'),
                    )
                  : null,
            ),
        ],
      ),
    );
  }
}

/// Recording one deposit: amounts prefilled from the suggestion.
class _DepositDialog extends StatefulWidget {
  const _DepositDialog({
    required this.api,
    required this.today,
    required this.method,
  });

  final ApiClient api;
  final DateTime today;
  final String method;

  @override
  State<_DepositDialog> createState() => _DepositDialogState();
}

class _DepositDialogState extends State<_DepositDialog>
    with SaveInDialog<_DepositDialog> {
  late String _period = _monthOf(widget.today);
  late String _method = widget.method;
  late final TextEditingController _date =
      TextEditingController(text: _iso(widget.today));
  final TextEditingController _cpin = TextEditingController();
  final TextEditingController _cin = TextEditingController();
  final TextEditingController _narration = TextEditingController();
  final Map<String, TextEditingController> _amounts = {
    for (final String head in _heads) head: TextEditingController(text: '0'),
  };
  ExpenseAccountChoices? _accounts;
  String? _moneyAccountId;
  String? _basis;
  String? _due;
  String? _hint;
  bool _suggesting = false;

  List<String> get _months => [
        for (int back = 0; back < 12; back++)
          _monthOf(DateTime(widget.today.year, widget.today.month - back)),
      ];

  @override
  void initState() {
    super.initState();
    unawaited(_loadAccounts());
    unawaited(_suggest());
  }

  @override
  void dispose() {
    for (final TextEditingController c in [
      _date,
      _cpin,
      _cin,
      _narration,
      ..._amounts.values,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _loadAccounts() async {
    try {
      final ExpenseAccountChoices choices =
          await widget.api.expenseAccountChoices();
      if (!mounted) return;
      setState(() {
        _accounts = choices;
        if (choices.paidFromAccounts.length == 1) {
          _moneyAccountId = choices.paidFromAccounts.single.id;
        }
      });
    } on ApiException {
      // Saving says what is missing.
    }
  }

  Future<void> _suggest() async {
    setState(() {
      _suggesting = true;
      _hint = null;
      _basis = null;
      _due = null;
    });
    try {
      final Json s = await widget.api
          .gstCashDepositSuggestion(returnPeriod: _period, method: _method);
      if (!mounted) return;
      final Object? heads = s['heads'];
      setState(() {
        for (final String head in _heads) {
          _amounts[head]!.text =
              heads is Map ? stringValue(heads[head]) : '0';
          if (_amounts[head]!.text.isEmpty) _amounts[head]!.text = '0';
        }
        _basis = stringValue(s['basis']);
        _due = stringValue(s['due_date']);
      });
    } on ApiException catch (exception) {
      if (mounted) setState(() => _hint = exception.message);
    } finally {
      if (mounted) setState(() => _suggesting = false);
    }
  }

  Future<void> _save() {
    final String? account = _moneyAccountId;
    if (account == null) {
      setState(() => saveError = 'Choose the bank account paid from.');
      return Future<void>.value();
    }
    return saveAndClose<bool>(() async {
      await widget.api.recordGstCashDeposit({
        'return_period': _period,
        'deposit_date': _date.text.trim(),
        'money_account_id': account,
        'method': _method,
        for (final String head in _heads)
          'amount_$head': _amounts[head]!.text.trim().isEmpty
              ? '0'
              : _amounts[head]!.text.trim(),
        if (_cpin.text.trim().isNotEmpty) 'challan_cpin': _cpin.text.trim(),
        if (_cin.text.trim().isNotEmpty) 'challan_cin': _cin.text.trim(),
        if (_narration.text.trim().isNotEmpty)
          'narration': _narration.text.trim(),
      });
      if (mounted) {
        NotificationService.show(
          context,
          'PMT-06 deposit recorded.',
          kind: AppNotificationKind.success,
        );
      }
      return true;
    });
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<ExpenseAccountOption> money =
        _accounts?.paidFromAccounts ?? const [];
    return AlertDialog(
      scrollable: true,
      title: const Text('Record PMT-06 deposit'),
      content: SizedBox(
        width: 460,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            saveErrorBanner(),
            DropdownButtonFormField<String>(
              key: const ValueKey('gst-deposit-period'),
              initialValue: _period,
              decoration: const InputDecoration(
                  labelText: 'Month', isDense: true),
              items: [
                for (final String month in _months)
                  DropdownMenuItem(value: month, child: Text(month)),
              ],
              onChanged: saving
                  ? null
                  : (value) {
                      if (value == null) return;
                      setState(() => _period = value);
                      unawaited(_suggest());
                    },
            ),
            const SizedBox(height: AppSpacing.md),
            DropdownButtonFormField<String>(
              key: const ValueKey('gst-deposit-method'),
              isExpanded: true,
              initialValue: _method,
              decoration: const InputDecoration(
                  labelText: 'Method', isDense: true),
              items: const [
                DropdownMenuItem(
                    value: 'FIXED_SUM',
                    child: Text('Fixed sum: 35% of last quarter')),
                DropdownMenuItem(
                    value: 'SELF_ASSESSMENT', child: Text('Self-assessment')),
              ],
              onChanged: saving
                  ? null
                  : (value) {
                      if (value == null) return;
                      setState(() => _method = value);
                      unawaited(_suggest());
                    },
            ),
            if (_hint != null)
              Padding(
                padding: const EdgeInsets.only(top: AppSpacing.sm),
                child: Text(_hint!,
                    key: const ValueKey('gst-deposit-hint'),
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: theme.colorScheme.error)),
              ),
            if (_basis != null && _basis!.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: AppSpacing.sm),
                child: Text(
                  '$_basis${_due == null || _due!.isEmpty ? '' : ' Due $_due.'}',
                  key: const ValueKey('gst-deposit-basis'),
                  style: theme.textTheme.bodySmall,
                ),
              ),
            const SizedBox(height: AppSpacing.md),
            Wrap(
              spacing: AppSpacing.md,
              runSpacing: AppSpacing.sm,
              children: [
                for (final String head in _heads)
                  SizedBox(
                    width: 100,
                    child: TextField(
                      key: ValueKey('gst-deposit-$head'),
                      controller: _amounts[head],
                      enabled: !saving && !_suggesting,
                      keyboardType: const TextInputType.numberWithOptions(
                          decimal: true),
                      decoration: InputDecoration(
                          labelText: head.toUpperCase(), isDense: true),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),
            TextField(
              key: const ValueKey('gst-deposit-date'),
              controller: _date,
              enabled: !saving,
              decoration: const InputDecoration(
                  labelText: 'Deposited on', isDense: true),
            ),
            const SizedBox(height: AppSpacing.md),
            DropdownButtonFormField<String>(
              key: const ValueKey('gst-deposit-bank'),
              isExpanded: true,
              initialValue: money.any((a) => a.id == _moneyAccountId)
                  ? _moneyAccountId
                  : null,
              decoration: const InputDecoration(
                  labelText: 'Paid from', isDense: true),
              items: [
                for (final ExpenseAccountOption account in money)
                  DropdownMenuItem(
                    value: account.id,
                    child: Text('${account.code} ${account.name}',
                        overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: saving
                  ? null
                  : (id) => setState(() => _moneyAccountId = id),
            ),
            const SizedBox(height: AppSpacing.md),
            Row(children: [
              Expanded(
                child: TextField(
                  key: const ValueKey('gst-deposit-cpin'),
                  controller: _cpin,
                  enabled: !saving,
                  decoration:
                      const InputDecoration(labelText: 'CPIN', isDense: true),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: TextField(
                  key: const ValueKey('gst-deposit-cin'),
                  controller: _cin,
                  enabled: !saving,
                  decoration:
                      const InputDecoration(labelText: 'CIN', isDense: true),
                ),
              ),
            ]),
            const SizedBox(height: AppSpacing.md),
            TextField(
              key: const ValueKey('gst-deposit-narration'),
              controller: _narration,
              enabled: !saving,
              decoration: const InputDecoration(
                  labelText: 'Narration', isDense: true),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: cancelHandler,
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('gst-deposit-save'),
          onPressed: saving || _suggesting ? null : _save,
          child: Text(saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}
