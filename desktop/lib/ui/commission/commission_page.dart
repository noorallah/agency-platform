import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/commission.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';

/// What each salesman earns, and what a period of collections earned them.
///
/// Two things about this module surprise everybody who reads it for the first
/// time, so both are said on screen rather than left in the documentation:
///
/// * a rule with **no salesman** is the firm-wide default — the rate anybody
///   with no rule of their own earns; and
/// * commission is earned on money **actually collected** in the period, not
///   on what was invoiced. An invoice raised in March and paid in May earns
///   its commission in May, and a payment later taken back stops earning it.
///
/// Reading needs `COMMISSION_VIEW`, which is all the report needs. Recording
/// or changing a rate needs `COMMISSION_MANAGE`; without it the screen is
/// read-only and carries no add control at all.
class CommissionPage extends StatefulWidget {
  const CommissionPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<CommissionPage> createState() => _CommissionPageState();
}

/// Which half of the screen is showing.
enum _CommissionView { rules, report }

class _CommissionPageState extends State<CommissionPage> {
  late final TextEditingController _from =
      TextEditingController(text: isoDate(_firstOfThisMonth()));
  late final TextEditingController _to =
      TextEditingController(text: isoDate(DateTime.now()));

  _CommissionView _view = _CommissionView.rules;

  List<CommissionRuleRecord> _rules = const [];
  CommissionReport? _report;
  String? _selectedId;
  String? _rulesError;
  String? _reportError;
  bool _loadingRules = true;
  bool _loadingReport = false;

  /// The firm's people, so a rate can be agreed with somebody who has never
  /// had one. Without this list the picker could only offer names lifted off
  /// existing rules, which makes every rate but the first impossible to add.
  List<CommissionSalesman> _people = const <CommissionSalesman>[];

  bool get _mayView => widget.permissions.hasPermission('COMMISSION_VIEW');
  bool get _mayManage => widget.permissions.hasPermission('COMMISSION_MANAGE');

  static DateTime _firstOfThisMonth() {
    final DateTime now = DateTime.now();
    return DateTime(now.year, now.month);
  }

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) _loadRules();
  }

  @override
  void dispose() {
    _from.dispose();
    _to.dispose();
    super.dispose();
  }

  Future<void> _loadRules() async {
    setState(() {
      _loadingRules = true;
      _rulesError = null;
    });
    try {
      // Paged through rather than asked for in one oversized page: anything
      // above `MAX_PAGE_SIZE` is refused rather than clamped.
      final List<CommissionRuleRecord> rows =
          await fetchAllPages<CommissionRuleRecord>(
        (page) => widget.api.commissionRules(page: page),
      );
      final List<CommissionSalesman> people =
          await widget.api.commissionSalesmen();
      if (!mounted) return;
      setState(() {
        _rules = rows;
        _people = people;
        _loadingRules = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _rulesError = error.message;
        _loadingRules = false;
      });
    }
  }

  Future<void> _loadReport() async {
    final DateTime? from = parseIsoDate(_from.text);
    final DateTime? to = parseIsoDate(_to.text);
    if (from == null || to == null) {
      setState(() => _reportError =
          'Both dates must be written as YYYY-MM-DD, for example '
          '${isoDate(_firstOfThisMonth())}.');
      return;
    }
    if (to.isBefore(from)) {
      setState(() => _reportError = 'The period cannot end before it starts.');
      return;
    }
    setState(() {
      _loadingReport = true;
      _reportError = null;
      // Cleared before the read: a failed load must not leave one period's
      // figures on screen under a different period's dates.
      _report = null;
    });
    try {
      final CommissionReport report = await widget.api.commissionReport(
        fromDate: isoDate(from),
        toDate: isoDate(to),
      );
      if (!mounted) return;
      setState(() {
        _report = report;
        _loadingReport = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _reportError = error.message;
        _loadingReport = false;
      });
    }
  }

  Future<void> _edit({CommissionRuleRecord? rule}) async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (context) => CommissionRuleDialog(
        api: widget.api,
        rule: rule,
        // The firm's people, plus anybody a rule names who has since left.
        known: _knownSalesmen(),
      ),
    );
    if (saved == true) await _loadRules();
  }

  /// The people this screen can name.
  ///
  /// The firm's own members, read from `/commission/salesmen`, **plus**
  /// anybody a rule already names who is no longer among them -- somebody who
  /// has left still explains the payouts their rule made, and dropping them
  /// would make `DropdownButtonFormField` assert on a stored id that is not in
  /// its list and save the rule as firm-wide.
  List<CommissionSalesman> _knownSalesmen() {
    final Map<String, CommissionSalesman> byId = {
      for (final CommissionSalesman person in _people) person.id: person,
    };
    for (final CommissionRuleRecord rule in _rules) {
      if (rule.salesmanId.isEmpty || byId.containsKey(rule.salesmanId)) {
        continue;
      }
      byId[rule.salesmanId] = CommissionSalesman(
        id: rule.salesmanId,
        name: rule.salesmanName.isEmpty ? rule.salesmanId : rule.salesmanName,
      );
    }
    return byId.values.toList()..sort((a, b) => a.name.compareTo(b.name));
  }

  Future<void> _delete(CommissionRuleRecord rule) async {
    try {
      await widget.api.deleteCommissionRule(rule.id);
      if (!mounted) return;
      NotificationService.show(
        context,
        '${rule.whoLabel} — rule removed. It still explains the payouts it '
        'made while it was in force.',
        kind: AppNotificationKind.success,
      );
      await _loadRules();
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
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Commission rates and collections are recorded per firm.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see commission',
        message: 'Reading commission rates and the collections report needs '
            'the view commission permission.',
      );
    }
    final bool onRules = _view == _CommissionView.rules;
    return ManagementWorkspaceLayout(
      toolbar: Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          if (onRules && _mayManage)
            FilledButton.icon(
              onPressed: () => _edit(),
              icon: const Icon(Icons.add),
              label: const Text('Add rule'),
            ),
          OutlinedButton.icon(
            onPressed: onRules ? _loadRules : _loadReport,
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh'),
          ),
        ],
      ),
      searchPanel: onRules ? const SizedBox.shrink() : _periodPanel(),
      viewBar: SegmentedButton<_CommissionView>(
        segments: const [
          ButtonSegment(
            value: _CommissionView.rules,
            label: Text('Rates'),
            icon: Icon(Icons.percent),
          ),
          ButtonSegment(
            value: _CommissionView.report,
            label: Text('Collected'),
            icon: Icon(Icons.payments_outlined),
          ),
        ],
        selected: {_view},
        showSelectedIcon: false,
        onSelectionChanged: (selection) {
          setState(() => _view = selection.first);
          if (_view == _CommissionView.report &&
              _report == null &&
              !_loadingReport) {
            _loadReport();
          }
        },
      ),
      primaryContent: onRules ? _rulesContent() : _reportContent(),
      statusBar: WorkspaceStatusBar(
        total: onRules ? _rules.length : (_report?.rows.length ?? 0),
        selected: onRules && _selectedId != null,
        message: onRules
            ? 'A rate with no salesman applies to everybody without one of '
                'their own.'
            : 'Earned on money collected, not on invoiced value.',
      ),
    );
  }

  // ------------------------------------------------------------------
  // The rates
  // ------------------------------------------------------------------

  Widget _rulesContent() {
    if (_loadingRules) {
      return const Center(child: CircularProgressIndicator());
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const CommissionNotice(
          icon: Icons.groups_outlined,
          text: 'A rule with no salesman is the firm-wide default: the rate '
              'anybody with no rule of their own earns.',
        ),
        if (_rulesError != null) ...[
          const SizedBox(height: AppSpacing.sm),
          _ErrorLine(message: _rulesError!),
        ],
        const SizedBox(height: AppSpacing.md),
        Expanded(child: _rulesGrid()),
      ],
    );
  }

  Widget _rulesGrid() {
    if (_rules.isEmpty) {
      return WorkspaceEmptyState(
        title: 'No commission rates yet',
        message: _mayManage
            ? 'Add one for the whole firm, or one for a particular salesman.'
            : 'Recording a rate needs the manage commission permission.',
      );
    }
    return EnterpriseDataGrid<CommissionRuleRecord>(
      items: _rules,
      total: _rules.length,
      pageOffset: 0,
      rowsPerPage: _rules.length,
      availableRowsPerPage: [_rules.length],
      selectedId: _selectedId,
      columns: const [
        GridColumn(key: 'who', label: 'Applies to'),
        GridColumn(key: 'rate', label: 'Rate'),
        GridColumn(key: 'window', label: 'In force'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (row) => row.id,
      cells: (row) => [
        row.whoLabel,
        '${trimDecimal(row.percentage)}%',
        row.windowLabel,
        row.status,
      ],
      onSelect: (row) => setState(() => _selectedId = row.id),
      onPageChanged: (_) {},
      onOpen: _mayManage ? (row) => _edit(rule: row) : null,
      contextActions: _mayManage
          ? const [
              WorkspaceContextAction.edit,
              WorkspaceContextAction.delete,
            ]
          : const [],
      onContextAction: (action, row) {
        if (!_mayManage) return;
        if (action == WorkspaceContextAction.edit) _edit(rule: row);
        if (action == WorkspaceContextAction.delete) _delete(row);
      },
    );
  }

  // ------------------------------------------------------------------
  // The report
  // ------------------------------------------------------------------

  Widget _periodPanel() => Card(
        margin: EdgeInsets.zero,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Wrap(
            spacing: AppSpacing.md,
            runSpacing: AppSpacing.sm,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              SizedBox(
                width: 190,
                child: CommissionDateField(
                  controller: _from,
                  label: 'Collected from',
                ),
              ),
              SizedBox(
                width: 190,
                child: CommissionDateField(
                  controller: _to,
                  label: 'Collected to',
                ),
              ),
              FilledButton.tonalIcon(
                onPressed: _loadingReport ? null : _loadReport,
                icon: const Icon(Icons.calculate_outlined, size: 18),
                label: const Text('Show'),
              ),
            ],
          ),
        ),
      );

  Widget _reportContent() {
    final CommissionReport? report = _report;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const CommissionNotice(
          icon: Icons.info_outline,
          text: 'Commission is earned on money actually collected in this '
              'period, not on what was invoiced. An invoice raised earlier '
              'and paid now earns it now, and a payment taken back stops '
              'earning it.',
        ),
        if (_reportError != null) ...[
          const SizedBox(height: AppSpacing.sm),
          _ErrorLine(message: _reportError!),
        ],
        const SizedBox(height: AppSpacing.md),
        if (_loadingReport)
          const Expanded(child: Center(child: CircularProgressIndicator()))
        else if (report == null)
          const Expanded(
            child: WorkspaceEmptyState(
              icon: Icons.date_range_outlined,
              title: 'Choose a period',
              message: 'Pick the dates money was collected between, then '
                  'press Show.',
            ),
          )
        else ...[
          _totals(report),
          const SizedBox(height: AppSpacing.md),
          Expanded(child: _reportGrid(report)),
          const SizedBox(height: AppSpacing.sm),
          const CommissionNotice(
            icon: Icons.help_outline,
            text: 'Unassigned is money collected against invoices that '
                'carried no salesman. It belongs to nobody, and it is counted '
                'in the totals so they reconcile against the cash book.',
          ),
        ],
      ],
    );
  }

  Widget _totals(CommissionReport report) => Wrap(
        spacing: AppSpacing.md,
        runSpacing: AppSpacing.sm,
        children: [
          _TotalCard(
            label: 'Collected ${report.fromDate} to ${report.toDate}',
            value: report.totalCollectedAmount,
          ),
          _TotalCard(
            label: 'Commission earned',
            value: report.totalCommissionAmount,
          ),
        ],
      );

  Widget _reportGrid(CommissionReport report) {
    if (report.rows.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'Nothing was collected in this period',
        message: 'No settlement was allocated to an invoice between these '
            'dates, so no commission was earned.',
      );
    }
    return EnterpriseDataGrid<CommissionRow>(
      items: report.rows,
      total: report.rows.length,
      pageOffset: 0,
      rowsPerPage: report.rows.length,
      availableRowsPerPage: [report.rows.length],
      columns: const [
        GridColumn(key: 'salesman', label: 'Salesman'),
        GridColumn(key: 'collected', label: 'Collected'),
        GridColumn(key: 'commission', label: 'Commission'),
        GridColumn(key: 'invoices', label: 'Invoices'),
      ],
      id: (row) => row.salesmanId.isEmpty ? 'unassigned' : row.salesmanId,
      cells: (row) => [
        row.salesmanId.isEmpty
            ? 'Unassigned (no salesman on the invoice)'
            : row.salesmanName,
        row.collectedAmount,
        row.commissionAmount,
        '${row.invoiceCount}',
      ],
      onSelect: (_) {},
      onPageChanged: (_) {},
    );
  }
}

/// Record or change one commission rate.
///
/// Both of the server's own rules are restated here so a mistake is caught
/// while the numbers are still on screen: a rate outside 0–100, and a window
/// that closes before it opens. When the server refuses for any other reason
/// its sentence is shown as it stands — it knows things this form does not,
/// such as a rate already covering the same days for the same person.
class CommissionRuleDialog extends StatefulWidget {
  const CommissionRuleDialog({
    super.key,
    required this.api,
    required this.known,
    this.rule,
  });

  final ApiClient api;

  /// The people who can be named, besides the firm as a whole.
  final List<CommissionSalesman> known;

  /// The rule being changed, or null to record a new one.
  final CommissionRuleRecord? rule;

  @override
  State<CommissionRuleDialog> createState() => _CommissionRuleDialogState();
}

class _CommissionRuleDialogState extends State<CommissionRuleDialog> {
  late final TextEditingController _percentage =
      TextEditingController(text: trimDecimal(widget.rule?.percentage ?? ''));
  late final TextEditingController _from = TextEditingController(
      text: widget.rule?.effectiveFrom ?? isoDate(DateTime.now()));
  late final TextEditingController _to =
      TextEditingController(text: widget.rule?.effectiveTo ?? '');

  /// The empty string is the firm-wide default, which belongs to nobody.
  late String _salesmanId = widget.rule?.salesmanId ?? '';
  late String _status = widget.rule?.status ?? 'ACTIVE';

  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _percentage.dispose();
    _from.dispose();
    _to.dispose();
    super.dispose();
  }

  /// Say what is wrong, or nothing.
  String? _validate() {
    final double? percentage = double.tryParse(_percentage.text.trim());
    if (percentage == null) {
      return 'Enter the rate as a number, for example 2.5.';
    }
    if (percentage < 0 || percentage > 100) {
      return 'A commission rate must be between 0 and 100 percent.';
    }
    final DateTime? from = parseIsoDate(_from.text);
    if (from == null) {
      return 'Enter the date the rate starts, written as YYYY-MM-DD.';
    }
    final String to = _to.text.trim();
    if (to.isNotEmpty) {
      final DateTime? until = parseIsoDate(to);
      if (until == null) {
        return 'Enter the date the rate ends as YYYY-MM-DD, or leave it empty '
            'to let it run on.';
      }
      if (until.isBefore(from)) {
        return 'The rate cannot end before it starts.';
      }
    }
    return null;
  }

  /// What to send.
  ///
  /// On a create the salesman is *omitted* when nobody is named, which is how
  /// the server reads the firm-wide default. On an update it is sent as an
  /// explicit null instead: the update model dumps with `exclude_unset`, so
  /// omitting it would mean leave it alone and a rule could never be moved
  /// back to the firm-wide scope.
  Json _payload({required bool creating}) => <String, dynamic>{
        if (_salesmanId.isNotEmpty)
          'salesman_id': _salesmanId
        else if (!creating)
          'salesman_id': null,
        'percentage': _percentage.text.trim(),
        'effective_from': _from.text.trim(),
        'effective_to': _to.text.trim().isEmpty ? null : _to.text.trim(),
        'status': _status,
      };

  Future<void> _save() async {
    final String? problem = _validate();
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final CommissionRuleRecord? rule = widget.rule;
      if (rule == null) {
        await widget.api.createCommissionRule(_payload(creating: true));
      } else {
        await widget.api.updateCommissionRule(
          rule.id,
          _payload(creating: false),
          expectedVersion: preconditionFor(rule.version),
        );
      }
      if (!mounted) return;
      NotificationService.show(
        context,
        rule == null ? 'Commission rate recorded.' : 'Commission rate saved.',
        kind: AppNotificationKind.success,
      );
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        // The typing is still on screen, so the conflict message says so.
        _error = saveFailureMessage(
          error,
          'commission rate',
          changesKept: true,
        );
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    // A rule may name somebody the picker has never heard of — an old rule for
    // a former member. Keeping their id as an item of its own stops the
    // dropdown asserting on a value that is not in its list, which silently
    // saves the field as blank.
    final bool namedIsKnown = _salesmanId.isEmpty ||
        widget.known.any((person) => person.id == _salesmanId);
    return AlertDialog(
      icon: const Icon(Icons.percent),
      title: Text(widget.rule == null
          ? 'Add a commission rate'
          : 'Edit ${widget.rule!.whoLabel}'),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DropdownButtonFormField<String>(
                // Long names are common here, and the button row of a
                // dropdown never constrains its child: without this a name
                // overflows the dialog rather than eliding.
                isExpanded: true,
                initialValue: _salesmanId,
                decoration: const InputDecoration(
                  labelText: 'Applies to',
                  helperText: 'Leave as everyone for the firm-wide default.',
                ),
                items: [
                  const DropdownMenuItem<String>(
                    value: '',
                    child: Text(
                      'Everyone (default)',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  for (final CommissionSalesman person in widget.known)
                    DropdownMenuItem<String>(
                      value: person.id,
                      child:
                          Text(person.name, overflow: TextOverflow.ellipsis),
                    ),
                  if (!namedIsKnown)
                    DropdownMenuItem<String>(
                      value: _salesmanId,
                      child: Text(
                        widget.rule?.whoLabel ?? _salesmanId,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                ],
                onChanged: _saving
                    ? null
                    : (value) => setState(() => _salesmanId = value ?? ''),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _percentage,
                enabled: !_saving,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                inputFormatters: [
                  FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
                ],
                decoration: const InputDecoration(
                  labelText: 'Rate',
                  helperText: 'Percent of the money collected.',
                  suffixText: '%',
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              Row(
                children: [
                  Expanded(
                    child: CommissionDateField(
                      controller: _from,
                      label: 'In force from',
                      enabled: !_saving,
                    ),
                  ),
                  const SizedBox(width: AppSpacing.lg),
                  Expanded(
                    child: CommissionDateField(
                      controller: _to,
                      label: 'Until',
                      helper: 'Leave empty to run on.',
                      enabled: !_saving,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                isExpanded: true,
                initialValue: _status,
                decoration: const InputDecoration(labelText: 'Status'),
                items: const [
                  DropdownMenuItem(value: 'ACTIVE', child: Text('Active')),
                  DropdownMenuItem(value: 'INACTIVE', child: Text('Inactive')),
                ],
                onChanged: _saving
                    ? null
                    : (value) => setState(() => _status = value ?? _status),
              ),
              if (_error != null) ...[
                const SizedBox(height: AppSpacing.lg),
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

/// A date, typed as `YYYY-MM-DD` or chosen from the calendar.
///
/// Typed as well as picked because a report period is usually a month somebody
/// already knows, and four calendar taps to reach it is three too many.
class CommissionDateField extends StatelessWidget {
  const CommissionDateField({
    super.key,
    required this.controller,
    required this.label,
    this.helper,
    this.enabled = true,
    this.onChanged,
  });

  final TextEditingController controller;
  final String label;
  final String? helper;
  final bool enabled;
  final VoidCallback? onChanged;

  Future<void> _pick(BuildContext context) async {
    final DateTime anchor = parseIsoDate(controller.text) ?? DateTime.now();
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: anchor,
      firstDate: DateTime(anchor.year - 5),
      lastDate: DateTime(anchor.year + 5),
    );
    if (picked == null) return;
    controller.text = isoDate(picked);
    onChanged?.call();
  }

  @override
  Widget build(BuildContext context) => TextField(
        controller: controller,
        enabled: enabled,
        decoration: InputDecoration(
          labelText: label,
          helperText: helper ?? 'YYYY-MM-DD',
          isDense: true,
          suffixIcon: IconButton(
            tooltip: 'Pick a date',
            icon: const Icon(Icons.event, size: 18),
            onPressed: enabled ? () => _pick(context) : null,
          ),
        ),
      );
}

/// A quiet line of explanation, in the shape the credit policy dialog uses.
class CommissionNotice extends StatelessWidget {
  const CommissionNotice({super.key, required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 16, color: theme.colorScheme.onSurfaceVariant),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Text(
            text,
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
        ),
      ],
    );
  }
}

class _TotalCard extends StatelessWidget {
  const _TotalCard({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(value, style: theme.textTheme.titleLarge),
          ],
        ),
      ),
    );
  }
}

class _ErrorLine extends StatelessWidget {
  const _ErrorLine({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Text(
      message,
      style: theme.textTheme.bodySmall
          ?.copyWith(color: theme.colorScheme.error),
    );
  }
}

/// Render `2.5000` as `2.5` — the server stores a scale nobody types.
String trimDecimal(String value) {
  if (!value.contains('.')) return value;
  final String trimmed =
      value.replaceAll(RegExp(r'0+$'), '').replaceAll(RegExp(r'\.$'), '');
  return trimmed.isEmpty ? '0' : trimmed;
}

/// A date as the API writes it.
String isoDate(DateTime value) => '${value.year.toString().padLeft(4, '0')}-'
    '${value.month.toString().padLeft(2, '0')}-'
    '${value.day.toString().padLeft(2, '0')}';

/// Read `YYYY-MM-DD`, or nothing.
///
/// Deliberately stricter than `DateTime.tryParse`, which happily accepts a
/// timestamp and half a dozen other shapes — a report period read out of one
/// of those is a period nobody asked for.
DateTime? parseIsoDate(String text) {
  final String trimmed = text.trim();
  if (!RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(trimmed)) return null;
  return DateTime.tryParse(trimmed);
}
