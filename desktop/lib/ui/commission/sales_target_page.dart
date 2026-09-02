import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/commission.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';

/// What a firm expects to sell, and how it went.
///
/// The by-salesman and by-territory reports have always answered "how much"
/// and never "how much against what". This is that missing half.
///
/// Two things the screen has to say plainly. Achievement is measured over the
/// **target's own** period, not the window typed above it — so a monthly
/// target still reads as a month even when the report covers a year. And on
/// the target's own **basis**: a firm measuring what was collected and one
/// measuring what was invoiced want different numbers from the same documents.
class SalesTargetPage extends StatefulWidget {
  const SalesTargetPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<SalesTargetPage> createState() => _SalesTargetPageState();
}

class _SalesTargetPageState extends State<SalesTargetPage> {
  final TextEditingController _from = TextEditingController();
  final TextEditingController _to = TextEditingController();

  List<SalesTargetRecord> _targets = const [];
  List<SalesTargetAchievementRecord> _achievement = const [];
  bool _showingAchievement = false;
  bool _loading = true;
  String? _error;

  bool get _mayManage =>
      widget.permissions.hasPermission('SALES_TARGET_MANAGE');

  @override
  void initState() {
    super.initState();
    final DateTime now = DateTime.now();
    _from.text = _iso(DateTime(now.year, now.month, 1));
    _to.text = _iso(DateTime(now.year, now.month + 1, 0));
    unawaited(_load());
  }

  @override
  void dispose() {
    _from.dispose();
    _to.dispose();
    super.dispose();
  }

  static String _iso(DateTime value) =>
      value.toIso8601String().split('T').first;

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      if (_showingAchievement) {
        final List<SalesTargetAchievementRecord> rows =
            await widget.api.salesTargetAchievement(
          fromDate: _from.text.trim(),
          toDate: _to.text.trim(),
        );
        if (!mounted) return;
        setState(() {
          _achievement = rows;
          _loading = false;
        });
        return;
      }
      final PagedResult<SalesTargetRecord> rows =
          await widget.api.salesTargets();
      if (!mounted) return;
      setState(() {
        _targets = rows.items;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _edit({SalesTargetRecord? existing}) async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (_) => _SalesTargetDialog(api: widget.api, existing: existing),
    );
    if (saved ?? false) unawaited(_load());
  }

  Future<void> _delete(SalesTargetRecord row) async {
    try {
      await widget.api.deleteSalesTarget(row.id);
      if (!mounted) return;
      NotificationService.show(
        context,
        'Target withdrawn.',
        kind: AppNotificationKind.success,
      );
      unawaited(_load());
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(type: EmptyStateType.noFirmSelected);
    }
    return ManagementWorkspaceLayout(
      toolbar: Wrap(
        spacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          SegmentedButton<bool>(
            segments: const [
              ButtonSegment(value: false, label: Text('Targets')),
              ButtonSegment(value: true, label: Text('Achievement')),
            ],
            selected: {_showingAchievement},
            onSelectionChanged: (choice) {
              setState(() => _showingAchievement = choice.first);
              unawaited(_load());
            },
          ),
          if (_mayManage && !_showingAchievement)
            FilledButton.icon(
              onPressed: () => unawaited(_edit()),
              icon: const Icon(Icons.add),
              label: const Text('New target'),
            ),
          if (_showingAchievement) ...[
            SizedBox(
              width: 150,
              child: TextField(
                controller: _from,
                decoration: const InputDecoration(labelText: 'From'),
              ),
            ),
            SizedBox(
              width: 150,
              child: TextField(
                controller: _to,
                decoration: const InputDecoration(labelText: 'To'),
              ),
            ),
          ],
          OutlinedButton.icon(
            onPressed: () => unawaited(_load()),
            icon: const Icon(Icons.refresh),
            label: Text(_showingAchievement ? 'Show' : 'Refresh'),
          ),
        ],
      ),
      // No search panel: a firm sets a handful of targets a period, and a
      // search box over six rows is furniture rather than a tool.
      searchPanel: const SizedBox.shrink(),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _showingAchievement ? _achievement.length : _targets.length,
        selected: false,
        message: _loading ? 'Loading...' : null,
      ),
    );
  }

  Widget _content() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(title: 'Targets unavailable', message: _error!);
    }
    return _showingAchievement ? _achievementGrid() : _targetGrid();
  }

  Widget _targetGrid() {
    if (_targets.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No targets set',
        message: 'Without one, the by-salesman reports say how much was sold '
            'and nothing about whether that was enough.',
      );
    }
    return EnterpriseDataGrid<SalesTargetRecord>(
      items: _targets,
      total: _targets.length,
      pageOffset: 0,
      rowsPerPage: _targets.length,
      columns: const [
        GridColumn(key: 'scope', label: 'For'),
        GridColumn(key: 'period', label: 'Period'),
        GridColumn(key: 'type', label: 'Runs'),
        GridColumn(key: 'basis', label: 'Counts'),
        GridColumn(key: 'amount', label: 'Target'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (row) => row.id,
      onSelect: (_) {},
      onPageChanged: (_) {},
      cells: (row) => [
        row.scopeLabel,
        '${row.periodStart} to ${row.periodEnd}',
        row.periodType,
        row.basis == 'COLLECTED' ? 'Money collected' : 'Value invoiced',
        row.targetAmount,
        row.status,
      ],
      contextActions: const [
        WorkspaceContextAction.edit,
        WorkspaceContextAction.delete,
      ],
      onContextAction: (action, row) {
        if (!_mayManage) return;
        if (action == WorkspaceContextAction.edit) {
          unawaited(_edit(existing: row));
        }
        if (action == WorkspaceContextAction.delete) unawaited(_delete(row));
      },
    );
  }

  Widget _achievementGrid() {
    if (_achievement.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No targets cover that window',
        message: 'A target is reported when its own period overlaps the dates '
            'asked for, and is measured over its own period rather than these.',
      );
    }
    return EnterpriseDataGrid<SalesTargetAchievementRecord>(
      items: _achievement,
      total: _achievement.length,
      pageOffset: 0,
      rowsPerPage: _achievement.length,
      columns: const [
        GridColumn(key: 'scope', label: 'For'),
        GridColumn(key: 'period', label: 'Its period'),
        GridColumn(key: 'basis', label: 'Counts'),
        GridColumn(key: 'target', label: 'Target'),
        GridColumn(key: 'achieved', label: 'Achieved'),
        GridColumn(key: 'short', label: 'Still to sell'),
        GridColumn(key: 'percent', label: 'Of target'),
      ],
      id: (row) => row.targetId,
      onSelect: (_) {},
      onPageChanged: (_) {},
      cells: (row) => [
        row.salesmanName,
        '${row.periodStart} to ${row.periodEnd}',
        row.basis == 'COLLECTED' ? 'Money collected' : 'Value invoiced',
        row.targetAmount,
        row.achievedAmount,
        // Zero rather than a negative: a target beaten has nothing left to
        // sell, and a minus sign there reads as a fault.
        row.shortfallAmount,
        '${row.achievedPercent}%',
      ],
    );
  }
}

/// Set one target: who for, over what, and how much.
class _SalesTargetDialog extends StatefulWidget {
  const _SalesTargetDialog({required this.api, this.existing});

  final ApiClient api;
  final SalesTargetRecord? existing;

  @override
  State<_SalesTargetDialog> createState() => _SalesTargetDialogState();
}

class _SalesTargetDialogState extends State<_SalesTargetDialog> {
  final TextEditingController _start = TextEditingController();
  final TextEditingController _end = TextEditingController();
  final TextEditingController _amount = TextEditingController();
  String _period = 'MONTHLY';
  String _basis = 'INVOICED';
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final SalesTargetRecord? row = widget.existing;
    if (row == null) return;
    _start.text = row.periodStart;
    _end.text = row.periodEnd;
    _amount.text = row.targetAmount;
    _period = row.periodType;
    _basis = row.basis;
  }

  @override
  void dispose() {
    _start.dispose();
    _end.dispose();
    _amount.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    final Json body = <String, dynamic>{
      'period_start': _start.text.trim(),
      'period_end': _end.text.trim(),
      'period_type': _period,
      'basis': _basis,
      'target_amount': _amount.text.trim().isEmpty ? '0' : _amount.text.trim(),
      'status': 'ACTIVE',
    };
    try {
      final SalesTargetRecord? existing = widget.existing;
      if (existing == null) {
        await widget.api.createSalesTarget(body);
      } else {
        await widget.api.updateSalesTarget(
          existing.id,
          body,
          expectedVersion: existing.version,
        );
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
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
      title: Text(widget.existing == null ? 'New target' : 'Edit target'),
      content: SizedBox(
        width: 520,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _start,
                    decoration: const InputDecoration(
                      labelText: 'From',
                      hintText: 'YYYY-MM-DD',
                    ),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: TextField(
                    controller: _end,
                    decoration: const InputDecoration(
                      labelText: 'To',
                      hintText: 'YYYY-MM-DD',
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: _period,
                    decoration: const InputDecoration(labelText: 'Runs'),
                    items: const [
                      DropdownMenuItem(
                          value: 'MONTHLY', child: Text('Monthly')),
                      DropdownMenuItem(
                          value: 'QUARTERLY', child: Text('Quarterly')),
                      DropdownMenuItem(value: 'YEARLY', child: Text('Yearly')),
                    ],
                    onChanged: (value) =>
                        setState(() => _period = value ?? _period),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: _basis,
                    decoration: const InputDecoration(labelText: 'Counts'),
                    items: const [
                      DropdownMenuItem(
                          value: 'INVOICED', child: Text('Value invoiced')),
                      DropdownMenuItem(
                          value: 'COLLECTED', child: Text('Money collected')),
                    ],
                    onChanged: (value) =>
                        setState(() => _basis = value ?? _basis),
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              _basis == 'COLLECTED'
                  ? 'Counts money that actually arrived in the period, the way '
                      'commission does.'
                  : 'Counts approved invoices dated in the period. A draft is '
                      'not a sale.',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: AppSpacing.md),
            TextField(
              controller: _amount,
              decoration: const InputDecoration(labelText: 'Target amount'),
              keyboardType: TextInputType.number,
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
}
