// Rule 42 (GST-4): input credit on goods and services used for both taxable
// and exempt sales is given back in proportion to the exempt share
// (D1 = C2 x E / F). The screen shows the arithmetic for a month or for a
// financial year and, where the firm has switched posting on, posts it.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';

/// The common-credit reversal for a month or a year, and the posted list.
class Rule42Page extends StatefulWidget {
  const Rule42Page({
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
  State<Rule42Page> createState() => _Rule42PageState();
}

class _Rule42PageState extends State<Rule42Page> {
  late final DateTime _now = widget.today ?? DateTime.now();
  late DateTime _month = DateTime(_now.year, _now.month - 1);
  late String _year = _financialYears().first;
  bool _annual = false;
  Json? _data;
  List<Json> _posted = <Json>[];
  String? _error;
  bool _loading = false;

  bool get _canView =>
      widget.permissions.hasPermission('ACCOUNT_VIEW') ||
      widget.permissions.hasPermission('SALES_VIEW');
  bool get _canPost => widget.permissions.hasPermission('JOURNAL_POST');

  /// The current financial year and the two before it, newest first.
  List<String> _financialYears() {
    final int start = _now.month >= 4 ? _now.year : _now.year - 1;
    return [
      for (int y = start; y > start - 3; y--)
        '$y-${((y + 1) % 100).toString().padLeft(2, '0')}',
    ];
  }

  String get _periodText =>
      '${_month.year.toString().padLeft(4, '0')}-'
      '${_month.month.toString().padLeft(2, '0')}';

  /// The day after the year's 31 March: the earliest the true-up may post.
  String get _yearPostingDefault => '${int.parse(_year.split('-').first) + 1}'
      '-04-01';

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _canView) _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final Json data = _annual
          ? await widget.api.rule42Annual(_year)
          : await widget.api.rule42Period(_periodText);
      final List<Json> posted = await widget.api.rule42Posted();
      if (!mounted) return;
      setState(() {
        _data = data;
        _posted = posted;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _data = null;
        _error = error.message;
        _loading = false;
      });
    }
  }

  void _shiftMonth(int by) {
    setState(() => _month = DateTime(_month.year, _month.month + by));
    _load();
  }

  Future<void> _post() async {
    final String? mode = _data == null ? null : stringValue(_data!['mode']);
    if (mode != 'POST') return;
    final bool? done = await showDialog<bool>(
      context: context,
      builder: (context) => _PostDialog(
        annual: _annual,
        label: _annual ? _year : _periodText,
        initialDate: _annual ? _yearPostingDefault : null,
        range: _annual ? null : _monthRange(),
        onSave: (String? date) async {
          if (_annual) {
            await widget.api.postRule42Annual(_year, date!);
          } else {
            await widget.api.postRule42Period(_periodText, postingDate: date);
          }
        },
      ),
    );
    if (done != true || !mounted) return;
    NotificationService.show(
      context,
      'Rule 42 reversal posted.',
      kind: AppNotificationKind.success,
    );
    await _load();
  }

  (DateTime, DateTime) _monthRange() =>
      (_month, DateTime(_month.year, _month.month + 1, 0));

  Future<void> _takeBack(Json row) async {
    final String? reason = await askForReason(
      context,
      title: 'Take back rule 42 reversal',
      explanation: 'The reversal for ${stringValue(row['period_from'])} to '
          '${stringValue(row['period_to'])} is reversed and the credit is '
          'available again. The reason is kept in the trail.',
      confirmLabel: 'Take back',
    );
    if (reason == null || !mounted) return;
    setState(() => _loading = true);
    try {
      await widget.api.reverseRule42('${row['id']}', reason);
      if (!mounted) return;
      NotificationService.show(
        context,
        'Rule 42 reversal taken back.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _loading = false);
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
      return;
    }
    await _load();
  }

  static double _num(Object? value) => double.tryParse('${value ?? 0}') ?? 0;

  static String _money(num value) => value.toStringAsFixed(2);

  static double _head(Object? block, String head) =>
      block is Map ? _num(block[head]) : 0;

  static double _total(Object? block) =>
      ['igst', 'cgst', 'sgst', 'cess'].fold(0, (a, h) => a + _head(block, h));

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Rule 42',
        message: 'You do not have permission to see this.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Rule 42',
        message: 'Choose a firm to see its common credit.',
      );
    }
    final ThemeData theme = Theme.of(context);
    final String mode = stringValue(_data?['mode']);
    return LoadingOverlay(
      loading: _loading,
      child: ListView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        children: [
          _controls(mode),
          const SizedBox(height: AppSpacing.md),
          if (_error != null)
            Text(_error!,
                key: const ValueKey('rule42-error'),
                style: theme.textTheme.bodyMedium
                    ?.copyWith(color: theme.colorScheme.error))
          else if (_data != null) ...[
            if (mode == 'OFF')
              Text(
                'Rule 42 is switched off in Settings > Tax > GST Documents.',
                key: const ValueKey('rule42-off'),
                style: theme.textTheme.bodyMedium,
              )
            else ...[
              if (mode != 'POST')
                Text(
                  'Reported only — choose Report and post in GST '
                  'settings to post.',
                  key: const ValueKey('rule42-report-note'),
                  style: theme.textTheme.bodySmall,
                ),
              const SizedBox(height: AppSpacing.sm),
              _arithmetic(theme),
              const SizedBox(height: AppSpacing.md),
              _heads(theme),
            ],
          ],
          const SizedBox(height: AppSpacing.lg),
          Text('Posted', style: theme.textTheme.titleSmall),
          const SizedBox(height: AppSpacing.sm),
          _postedTable(theme),
        ],
      ),
    );
  }

  Widget _controls(String mode) {
    return Wrap(
      spacing: AppSpacing.md,
      runSpacing: AppSpacing.sm,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SegmentedButton<bool>(
          key: const ValueKey('rule42-basis'),
          showSelectedIcon: false,
          segments: const [
            ButtonSegment(value: false, label: Text('Period')),
            ButtonSegment(value: true, label: Text('Year')),
          ],
          selected: {_annual},
          onSelectionChanged: _loading
              ? null
              : (Set<bool> value) {
                  setState(() => _annual = value.first);
                  _load();
                },
        ),
        if (!_annual) ...[
          IconButton(
            key: const ValueKey('rule42-prev'),
            tooltip: 'Previous month',
            onPressed: _loading ? null : () => _shiftMonth(-1),
            icon: const Icon(Icons.chevron_left),
          ),
          Text(_periodText, key: const ValueKey('rule42-period')),
          IconButton(
            key: const ValueKey('rule42-next'),
            tooltip: 'Next month',
            onPressed: _loading ? null : () => _shiftMonth(1),
            icon: const Icon(Icons.chevron_right),
          ),
        ] else
          DropdownButton<String>(
            key: const ValueKey('rule42-year'),
            value: _year,
            items: [
              for (final String year in _financialYears())
                DropdownMenuItem(value: year, child: Text(year)),
            ],
            onChanged: _loading
                ? null
                : (String? value) {
                    if (value == null) return;
                    setState(() => _year = value);
                    _load();
                  },
          ),
        if (mode == 'POST' && _canPost)
          FilledButton.icon(
            key: const ValueKey('rule42-post'),
            onPressed: _loading ? null : _post,
            icon: const Icon(Icons.playlist_add_check),
            label: const Text('Post'),
          ),
      ],
    );
  }

  Widget _arithmetic(ThemeData theme) {
    final double e = _num(_data!['exempt_turnover']);
    final double f = _num(_data!['total_turnover']);
    final double share = _num(_data!['exempt_share']);
    return Wrap(
      key: const ValueKey('rule42-arithmetic'),
      spacing: AppSpacing.xl,
      runSpacing: AppSpacing.sm,
      children: [
        _figure(theme, 'E — exempt turnover', _money(e)),
        _figure(theme, 'F — total turnover', _money(f)),
        _figure(theme, 'E ÷ F', '${_money(share * 100)}%'),
      ],
    );
  }

  Widget _figure(ThemeData theme, String label, String value) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label, style: theme.textTheme.bodySmall),
          Text(value, style: theme.textTheme.titleMedium),
        ],
      );

  Widget _heads(ThemeData theme) {
    final Object? common = _data!['common'];
    final Object? reversal = _data!['reversal'];
    final bool annual = _annual;
    final Object? already = _data!['already_reversed'];
    final Object? difference = _data!['difference'];
    const List<(String, String)> heads = [
      ('igst', 'IGST'),
      ('cgst', 'CGST'),
      ('sgst', 'SGST'),
      ('cess', 'Cess'),
    ];
    String diff(double v) =>
        v < 0 ? '${_money(-v)} claim back' : _money(v);
    DataRow row(String label, double c, double d, double a, double x) =>
        DataRow(cells: [
          DataCell(Text(label)),
          DataCell(Text(_money(c))),
          DataCell(Text(_money(d))),
          if (annual) DataCell(Text(_money(a))),
          if (annual) DataCell(Text(diff(x))),
        ]);
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DataTable(
        key: const ValueKey('rule42-heads'),
        columns: [
          const DataColumn(label: Text('Tax')),
          const DataColumn(label: Text('Common credit (C2)'), numeric: true),
          const DataColumn(label: Text('Reversal (D1)'), numeric: true),
          if (annual)
            const DataColumn(label: Text('Already reversed'), numeric: true),
          if (annual)
            const DataColumn(label: Text('Difference'), numeric: true),
        ],
        rows: [
          for (final (String, String) h in heads)
            row(
              h.$2,
              _head(common, h.$1),
              _head(reversal, h.$1),
              _head(already, h.$1),
              _head(difference, h.$1),
            ),
          row(
            'Total',
            _total(common),
            _total(reversal),
            _total(already),
            _total(difference),
          ),
        ],
      ),
    );
  }

  Widget _postedTable(ThemeData theme) {
    if (_posted.isEmpty) {
      return Text('Nothing has been posted under rule 42.',
          key: const ValueKey('rule42-none-posted'),
          style: theme.textTheme.bodySmall);
    }
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DataTable(
        columns: const [
          DataColumn(label: Text('Kind')),
          DataColumn(label: Text('Period')),
          DataColumn(label: Text('Movement date')),
          DataColumn(label: Text('Reversed'), numeric: true),
          DataColumn(label: Text('Status')),
          DataColumn(label: Text('')),
        ],
        rows: [
          for (final Json row in _posted)
            DataRow(
              key: ValueKey('rule42-posted-${row['id']}'),
              cells: [
                DataCell(Text(stringValue(row['kind']) == 'ANNUAL'
                    ? 'Annual'
                    : 'Monthly')),
                DataCell(Text('${stringValue(row['period_from'])} to '
                    '${stringValue(row['period_to'])}')),
                DataCell(Text(stringValue(row['movement_date']))),
                DataCell(Text(_money(_total(row['reversed'])))),
                DataCell(stringValue(row['status']) == 'POSTED'
                    ? const StatusBadge(
                        label: 'Posted', tone: StatusBadgeTone.success)
                    : const StatusBadge(label: 'Taken back')),
                DataCell(
                  stringValue(row['status']) == 'POSTED' && _canPost
                      ? TextButton(
                          key: ValueKey('rule42-takeback-${row['id']}'),
                          onPressed: _loading ? null : () => _takeBack(row),
                          child: const Text('Take back'),
                        )
                      : const SizedBox.shrink(),
                ),
              ],
            ),
        ],
      ),
    );
  }
}

/// Confirms a posting, with the posting date: optional for a month (the
/// period's last day is used), required for the year.
class _PostDialog extends StatefulWidget {
  const _PostDialog({
    required this.annual,
    required this.label,
    required this.onSave,
    this.initialDate,
    this.range,
  });

  final bool annual;
  final String label;
  final String? initialDate;
  final (DateTime, DateTime)? range;
  final Future<void> Function(String? date) onSave;

  @override
  State<_PostDialog> createState() => _PostDialogState();
}

class _PostDialogState extends State<_PostDialog> with SaveInDialog {
  late String? _date = widget.initialDate;

  static String _iso(DateTime v) => '${v.year.toString().padLeft(4, '0')}-'
      '${v.month.toString().padLeft(2, '0')}-'
      '${v.day.toString().padLeft(2, '0')}';

  Future<void> _pick() async {
    final (DateTime, DateTime)? range = widget.range;
    final DateTime first = range?.$1 ?? DateTime(2017);
    final DateTime last = range?.$2 ?? DateTime(2100);
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _date == null ? last : DateTime.parse(_date!),
      firstDate: first,
      lastDate: last,
    );
    if (picked != null && mounted) setState(() => _date = _iso(picked));
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text('Post rule 42 for ${widget.label}'),
      content: SizedBox(
        width: 420,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              saveErrorBanner(),
              Text(
                widget.annual
                    ? 'The year’s true-up is posted on a date after '
                        '31 March.'
                    : 'Leave the date empty to post on the last day of the '
                        'period.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              Wrap(
                spacing: AppSpacing.sm,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  OutlinedButton.icon(
                    key: const ValueKey('rule42-posting-date'),
                    onPressed: saving ? null : _pick,
                    icon: const Icon(Icons.event, size: 18),
                    label: Text(_date == null
                        ? 'Posting date (optional)'
                        : 'Posting date $_date'),
                  ),
                  if (!widget.annual && _date != null)
                    TextButton(
                      onPressed: saving ? null : () => setState(() => _date = null),
                      child: const Text('Clear'),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('rule42-post-confirm'),
          onPressed: saving || (widget.annual && _date == null)
              ? null
              : () => saveAndClose<bool>(() async {
                    await widget.onSave(_date);
                    return true;
                  }),
          child: const Text('Post'),
        ),
      ],
    );
  }
}
