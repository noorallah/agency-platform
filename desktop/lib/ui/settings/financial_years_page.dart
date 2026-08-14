import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/finance.dart';
import '../workspace/desktop_framework.dart';

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

  bool get _canView => widget.permissions.hasPermission('accounting');

  /// Closing a period stops anybody booking into it, so it is gated on the
  /// same code the server gates the endpoint with.
  bool get _canClose => widget.permissions.hasPermission('financial_year');

  @override
  void initState() {
    super.initState();
    unawaited(_load());
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

  Future<void> _setStatus(AccountingPeriod period, String status) async {
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
          ]),
        );
      },
    );
  }
}
