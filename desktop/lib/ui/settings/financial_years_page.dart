import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/finance.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';

/// The years and periods every posting has to land in.
///
/// This existed on the server and nowhere in the client, which made one
/// refusal unanswerable: a document that will not save because there is no
/// open accounting period gave the operator nothing to go and look at. The
/// screen exists to make that state visible and, where somebody is entitled to,
/// fixable.
class FinancialYearsPage extends StatefulWidget {
  const FinancialYearsPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<FinancialYearsPage> createState() => _FinancialYearsPageState();
}

class _FinancialYearsPageState extends State<FinancialYearsPage> {
  List<FinancialYear> _years = const [];
  List<AccountingPeriod> _periods = const [];
  FinancialYear? _selected;
  bool _loading = false;
  String? _error;

  // Permission *codes*, not the seed's group names: 'accounting' and
  // 'financial_year' are dictionary keys in system_seed.py and never reach
  // a token, so the screen refused everybody (found mapping section 13,
  // 2026-09-13; the widget test passed the group names literally).
  bool get _canView => widget.permissions.hasPermission('FINANCIAL_YEAR_VIEW');

  /// Closing a period stops anybody booking into it, so it is gated on the
  /// same code the server gates the endpoint with.
  bool get _canClose =>
      widget.permissions.hasPermission('FINANCIAL_YEAR_CLOSE') ||
      widget.permissions.hasPermission('FINANCIAL_YEAR_REOPEN');

  bool get _canCloseYear =>
      widget.permissions.hasPermission('FINANCIAL_YEAR_CLOSE');

  bool get _canReopenYear =>
      widget.permissions.hasPermission('FINANCIAL_YEAR_REOPEN');

  /// Deleting an empty period is gated like the year's own delete.
  bool get _canDelete =>
      widget.permissions.hasPermission('FINANCIAL_YEAR_CREATE');

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    unawaited(_loadCloseSetting());
    unawaited(_loadAgeing());
  }

  Future<void> _load() async {
    if (!widget.hasActiveFirm || !_canView) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<dynamic> results = await Future.wait<dynamic>([
        widget.api.financialYears(),
        widget.api.accountingPeriods(),
      ]);
      if (!mounted) return;
      final List<FinancialYear> years = results[0] as List<FinancialYear>;
      setState(() {
        _years = years;
        _periods = results[1] as List<AccountingPeriod>;
        final String? selectedId = _selected?.id;
        _selected = years.where((year) => year.id == selectedId).firstOrNull ??
            // The active year first: it is the one somebody is posting into.
            years.where((year) => year.isActive).firstOrNull ??
            years.firstOrNull;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _years = const [];
        _periods = const [];
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  List<AccountingPeriod> get _periodsOfSelected {
    final FinancialYear? year = _selected;
    if (year == null) return const [];
    final List<AccountingPeriod> rows = [
      for (final AccountingPeriod period in _periods)
        if (period.financialYearId == year.id) period,
    ]..sort((a, b) => a.periodNumber.compareTo(b.periodNumber));
    return rows;
  }

  /// Delete a period nothing was written into (D-FIN-15). Without it a
  /// year that had periods could never be deleted.
  Future<void> _deletePeriod(AccountingPeriod period) async {
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('Delete ${period.name}?'),
        content: const Text(
          'Only a period that holds no journal entries can be deleted.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _loading = true);
    try {
      await widget.api.deleteAccountingPeriod(period.id);
      if (!mounted) return;
      NotificationService.show(
        context,
        '${period.name} deleted.',
        kind: AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Close the whole year. The server names what is left when it refuses.
  Future<void> _closeYear(FinancialYear year) async {
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('Close ${year.code}?'),
        content: Text(
          'Nothing can be posted into ${year.code} once it is closed. Every '
          'period must be closed and no draft journal may be dated in it.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Close year'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _loading = true);
    try {
      await widget.api.closeFinancialYear(year.id);
      if (!mounted) return;
      NotificationService.show(
        context,
        '${year.code} is closed. Nothing further can be posted into it.',
        kind: AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _reopenYear(FinancialYear year) async {
    final String? reason = await askForReason(
      context,
      title: 'Reopen ${year.code}?',
      explanation:
          'Postings can be made into ${year.code} again. Its periods '
          'stay closed; open the ones you need afterwards. The reason is '
          'recorded.',
      confirmLabel: 'Reopen year',
    );
    if (reason == null || !mounted) return;
    setState(() => _loading = true);
    try {
      await widget.api.reopenFinancialYear(year.id, reason);
      if (!mounted) return;
      NotificationService.show(
        context,
        '${year.code} is reopened. Its periods are still closed.',
        kind: AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Before a month closes, list what is unfinished in it (ACC-5). Returns
  /// whether to go ahead: a firm that warns may close anyway, one whose
  /// policy refuses is told why and goes no further.
  Future<bool> _confirmClose(AccountingPeriod period) async {
    final Json checks = await widget.api.periodCloseChecks(period.id);
    final List<Json> items = [
      for (final dynamic item
          in checks['items'] is List ? checks['items'] as List : const [])
        if (item is Map) Map<String, dynamic>.from(item),
    ];
    if (items.isEmpty || !mounted) return true;
    final bool refuses = checks['refuses'] == true;
    final bool? go = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(refuses
            ? '${period.name} cannot be closed yet'
            : 'Close ${period.name} with work left in it?'),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final Json item in items)
                  ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(
                      item['blocks'] == true
                          ? Icons.error_outline
                          : Icons.info_outline,
                    ),
                    title: Text('${stringValue(item['label'])}: '
                        '${item['count']}'),
                    subtitle: Text([
                      for (final dynamic example in item['examples'] is List
                          ? item['examples'] as List
                          : const [])
                        '$example',
                    ].join(', ')),
                  ),
                Text(
                  refuses
                      ? 'This firm refuses a close while drafts or unposted '
                          'documents stand. Post or cancel them first.'
                      : 'Closing stops anybody booking into the month. What '
                          'is listed can still be finished after reopening it.',
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text(refuses ? 'OK' : 'Cancel'),
          ),
          if (!refuses)
            FilledButton(
              key: const ValueKey('close-anyway'),
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Close anyway'),
            ),
        ],
      ),
    );
    return go ?? false;
  }

  /// The firm's policy, shown to whoever may change it (ACC-5).
  String? _closeSetting;

  Future<void> _loadCloseSetting() async {
    if (!_canDelete) return;
    try {
      final String value = await widget.api.periodCloseSetting();
      if (mounted) setState(() => _closeSetting = value);
    } on ApiException {
      // The year list still works; the policy control stays hidden.
    }
  }

  /// The firm's ageing columns, shown to the same people (ACC-6).
  final TextEditingController _ageing = TextEditingController();
  List<String> _ageingLabels = const [];
  bool _ageingLoaded = false;
  String? _ageingError;

  @override
  void dispose() {
    _ageing.dispose();
    super.dispose();
  }

  void _applyAgeing(Json settings) {
    final List<dynamic> days = settings['bucket_days'] as List<dynamic>? ?? [];
    final List<dynamic> bands = settings['bands'] as List<dynamic>? ?? [];
    _ageing.text = days.join(', ');
    _ageingLabels = [
      for (final dynamic band in bands) '${(band as Map)['label']}',
    ];
    _ageingLoaded = true;
    _ageingError = null;
  }

  Future<void> _loadAgeing() async {
    if (!_canDelete) return;
    try {
      final Json settings = await widget.api.ageingSettings();
      if (mounted) setState(() => _applyAgeing(settings));
    } on ApiException {
      // The year list still works; the ageing control stays hidden.
    }
  }

  Future<void> _saveAgeing() async {
    final List<String> parts = _ageing.text
        .split(RegExp(r'[,\s]+'))
        .where((String part) => part.isNotEmpty)
        .toList();
    final List<int?> parsed = [for (final String p in parts) int.tryParse(p)];
    if (parts.isEmpty || parsed.contains(null)) {
      setState(() => _ageingError = 'Enter whole numbers of days, such as '
          '30, 60, 90.');
      return;
    }
    try {
      final Json saved = await widget.api.updateAgeingSettings(
        [for (final int? value in parsed) value!],
      );
      if (mounted) setState(() => _applyAgeing(saved));
    } on ApiException catch (exception) {
      if (mounted) setState(() => _ageingError = exception.message);
    }
  }

  Future<void> _setCloseSetting(String value) async {
    try {
      final String saved = await widget.api.setPeriodCloseSetting(value);
      if (mounted) setState(() => _closeSetting = saved);
    } on ApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    }
  }

  Future<void> _setStatus(AccountingPeriod period, String status) async {
    if (status != 'OPEN') {
      try {
        if (!await _confirmClose(period)) return;
      } on ApiException catch (exception) {
        if (mounted) setState(() => _error = exception.message);
        return;
      }
    }
    setState(() => _loading = true);
    try {
      await widget.api.setPeriodStatus(period.id, status);
      if (!mounted) return;
      NotificationService.show(
        context,
        status == 'OPEN'
            ? '${period.name} is open. Documents dated in it can be booked.'
            : '${period.name} is closed. Nothing further can be booked into it.',
        kind: AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Financial years',
        message: 'You do not have permission to view accounting setup.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Financial years',
        message: 'Choose a firm to see its financial years.',
      );
    }
    return LoadingOverlay(
      loading: _loading,
      child: Column(children: [
        if (_error != null)
          Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: MaterialBanner(
              content: Text(_error!),
              actions: [
                TextButton(
                  onPressed: () => setState(() => _error = null),
                  child: const Text('Dismiss'),
                ),
              ],
            ),
          ),
        if (_closeSetting != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(
                AppSpacing.lg, AppSpacing.sm, AppSpacing.lg, 0),
            child: Row(children: [
              const Expanded(
                child: Text('Before closing a month with drafts or '
                    'unposted documents in it'),
              ),
              SizedBox(
                width: 220,
                child: DropdownButtonFormField<String>(
                  key: const ValueKey('period-close-setting'),
                  initialValue: _closeSetting,
                  isExpanded: true,
                  items: const [
                    DropdownMenuItem(value: 'WARN', child: Text('Warn')),
                    DropdownMenuItem(value: 'BLOCK', child: Text('Refuse')),
                  ],
                  onChanged: (String? value) {
                    if (value != null) unawaited(_setCloseSetting(value));
                  },
                ),
              ),
            ]),
          ),
        if (_ageingLoaded)
          Padding(
            padding: const EdgeInsets.fromLTRB(
                AppSpacing.lg, AppSpacing.sm, AppSpacing.lg, 0),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Expanded(child: Text('Ageing columns (days)')),
              SizedBox(
                width: 320,
                child: TextField(
                  key: const ValueKey('ageing-bands'),
                  controller: _ageing,
                  decoration: InputDecoration(
                    isDense: true,
                    helperText: _ageingLabels.join(', '),
                    errorText: _ageingError,
                  ),
                  onSubmitted: (_) => unawaited(_saveAgeing()),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              FilledButton(
                key: const ValueKey('ageing-save'),
                onPressed: () => unawaited(_saveAgeing()),
                child: const Text('Save'),
              ),
            ]),
          ),
        Expanded(
          child: _years.isEmpty
              ? const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'No financial year yet',
                  message: 'Every document is posted into an accounting '
                      'period, and every period belongs to a year. Until one '
                      'exists, nothing can be booked.',
                )
              : Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  Expanded(flex: 2, child: _yearList(context)),
                  const VerticalDivider(width: 1),
                  Expanded(flex: 3, child: _periodList(context)),
                ]),
        ),
      ]),
    );
  }

  Widget _yearList(BuildContext context) => ListView.separated(
        itemCount: _years.length,
        separatorBuilder: (_, __) => const Divider(height: 1),
        itemBuilder: (context, index) {
          final FinancialYear year = _years[index];
          final int open = _periods
              .where((period) =>
                  period.financialYearId == year.id && period.status == 'OPEN')
              .length;
          return ListTile(
            selected: year.id == _selected?.id,
            title: Text('${year.code}  ·  ${year.name}'),
            // How many periods are open is the fact that decides whether
            // anything can be posted; the year's own dates do not.
            subtitle: Text('${year.span}  ·  $open period(s) open'),
            trailing: Row(mainAxisSize: MainAxisSize.min, children: [
              if (year.isLocked) const StatusBadge(label: 'LOCKED'),
              if (year.isActive)
                const Padding(
                  padding: EdgeInsets.only(left: AppSpacing.sm),
                  child: StatusBadge(label: 'ACTIVE'),
                ),
            ]),
            onTap: () => setState(() => _selected = year),
          );
        },
      );

  Widget _periodList(BuildContext context) {
    final FinancialYear? year = _selected;
    if (year == null) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'No year selected',
        message: 'Choose a year to see the periods inside it.',
      );
    }
    final bool showClose = _canCloseYear && !year.isLocked;
    final bool showReopen = _canReopenYear && year.isLocked;
    final Widget body = _periodBody(context, year);
    if (!showClose && !showReopen) return body;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  year.isLocked
                      ? '${year.code} is closed.'
                      : '${year.code} is open for posting.',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (showClose)
                OutlinedButton(
                  onPressed: () => unawaited(_closeYear(year)),
                  child: const Text('Close year'),
                ),
              if (showReopen)
                OutlinedButton(
                  onPressed: () => unawaited(_reopenYear(year)),
                  child: const Text('Reopen year'),
                ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(child: body),
      ],
    );
  }

  Widget _periodBody(BuildContext context, FinancialYear year) {
    final List<AccountingPeriod> periods = _periodsOfSelected;
    if (periods.isEmpty) {
      return StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: '${year.name} has no periods',
        message: 'A year with no periods cannot take a posting. They are '
            'created with the year by the finance setup.',
      );
    }
    return ListView.separated(
      itemCount: periods.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (context, index) {
        final AccountingPeriod period = periods[index];
        final bool isOpen = period.status == 'OPEN';
        return ListTile(
          title: Text('${period.periodNumber}. ${period.name}'),
          subtitle: Text('${period.startsOn} to ${period.endsOn}'),
          trailing: Row(mainAxisSize: MainAxisSize.min, children: [
            StatusBadge(label: period.status),
            if (_canClose && !year.isLocked) ...[
              const SizedBox(width: AppSpacing.md),
              TextButton(
                onPressed: () => unawaited(
                  _setStatus(period, isOpen ? 'CLOSED' : 'OPEN'),
                ),
                child: Text(isOpen ? 'Close' : 'Open'),
              ),
            ],
            if (_canDelete && !year.isLocked)
              IconButton(
                tooltip: 'Delete period',
                onPressed: () => unawaited(_deletePeriod(period)),
                icon: const Icon(Icons.delete_outline),
              ),
          ]),
        );
      },
    );
  }
}
