// The firm's counter shifts (backlog 87 #7, SG-7): who opened a till, what it
// took, what was counted and how far off the count was.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';
import 'counter_shift_widgets.dart';

const int _pageSize = 50;

String _iso(DateTime date) => date.toIso8601String().substring(0, 10);

String _money(dynamic value) {
  final double? parsed = double.tryParse(stringValue(value));
  return parsed == null ? stringValue(value) : parsed.toStringAsFixed(2);
}

String _statusLabel(String status) =>
    status.isEmpty ? '' : status[0] + status.substring(1).toLowerCase();

/// The shifts, with filters on status and dates, a view of one shift's
/// summary and its printed report.
class CounterShiftsPage extends StatefulWidget {
  const CounterShiftsPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    this.saveBytesOverride,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// Tests inject this, because a widget test cannot open a save panel.
  final SaveBytesOverride? saveBytesOverride;

  @override
  State<CounterShiftsPage> createState() => _CounterShiftsPageState();
}

class _CounterShiftsPageState extends State<CounterShiftsPage> {
  List<Json> _rows = const [];
  String _status = '';
  DatePeriod _period = const DatePeriod.all();
  int _page = 1;
  int _total = 0;
  bool _loading = true;
  String? _error;
  String? _selectedId;

  bool get _mayView => widget.permissions.hasAnyPermission(
      const ['SALES_VIEW', 'REPORT_VIEW', 'SALES_INVOICE_CREATE']);

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) unawaited(_load());
  }

  Future<void> _load({int? requestedPage}) async {
    setState(() {
      _loading = true;
      _error = null;
      if (requestedPage != null) _page = requestedPage;
    });
    try {
      final Json response = await widget.api.counterShifts(
        page: _page,
        pageSize: _pageSize,
        status: _status.isEmpty ? null : _status,
        fromDate: _period.from == null ? null : _iso(_period.from!),
        toDate: _period.to == null ? null : _iso(_period.to!),
      );
      final List<Json> rows = [
        for (final dynamic item in (response['data'] as List? ?? const []))
          if (item is Map) Map<String, dynamic>.from(item),
      ];
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _total = pagedTotal(response, fallback: rows.length);
        if (!rows.any((row) => stringValue(row['id']) == _selectedId)) {
          _selectedId = null;
        }
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _rows = const [];
        _total = 0;
        _loading = false;
      });
    }
  }

  Json? get _selected => _rows
      .where((row) => stringValue(row['id']) == _selectedId)
      .firstOrNull;

  void _tell(String message, AppNotificationKind kind) =>
      NotificationService.show(context, message, kind: kind);

  Future<void> _print(Json shift) async {
    try {
      await saveShiftReport(
        widget.api,
        stringValue(shift['id']),
        stringValue(shift['shift_number']),
        saveBytesOverride: widget.saveBytesOverride,
      );
      if (!mounted) return;
      _tell('The shift report was saved.', AppNotificationKind.success);
    } on ApiException catch (error) {
      if (!mounted) return;
      _tell(error.message, AppNotificationKind.error);
    }
  }

  Future<void> _view(Json shift) => showDialog<void>(
        context: context,
        builder: (_) => _ShiftSummaryDialog(
          api: widget.api,
          shiftId: stringValue(shift['id']),
        ),
      );

  static const List<GridColumn> _columns = [
    GridColumn(key: 'number', label: 'Shift'),
    GridColumn(key: 'cashier', label: 'Cashier'),
    GridColumn(key: 'opened', label: 'Opened'),
    GridColumn(key: 'closed', label: 'Closed', priority: 2),
    GridColumn(key: 'float', label: 'Float', numeric: true, priority: 2),
    GridColumn(key: 'expected', label: 'Expected', numeric: true),
    GridColumn(key: 'counted', label: 'Counted', numeric: true),
    GridColumn(key: 'difference', label: 'Difference', numeric: true),
    GridColumn(key: 'status', label: 'Status'),
  ];

  List<String> _cells(Json row) {
    final bool closed = stringValue(row['status']) == 'CLOSED';
    return [
      stringValue(row['shift_number']),
      stringValue(row['cashier_name']),
      shiftStamp(row['opened_at']),
      closed ? shiftStamp(row['closed_at']) : '',
      _money(row['opening_float']),
      _money(row['expected_cash']),
      closed ? _money(row['counted_cash']) : '',
      closed ? _money(row['difference']) : '',
      _statusLabel(stringValue(row['status'])),
    ];
  }

  Widget _filters() {
    return Wrap(
      spacing: AppSpacing.md,
      runSpacing: AppSpacing.sm,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(
          width: 180,
          child: DropdownButtonFormField<String>(
            key: ValueKey('shifts-status-$_status'),
            isExpanded: true,
            initialValue: _status,
            decoration:
                const InputDecoration(labelText: 'Status', isDense: true),
            items: const [
              DropdownMenuItem(value: '', child: Text('Any status')),
              DropdownMenuItem(value: 'OPEN', child: Text('Open')),
              DropdownMenuItem(value: 'CLOSED', child: Text('Closed')),
            ],
            onChanged: (value) {
              setState(() => _status = value ?? '');
              unawaited(_load(requestedPage: 1));
            },
          ),
        ),
        DateRangeFilter(
          key: const ValueKey('shifts-period'),
          value: _period,
          onChanged: (period) {
            setState(() => _period = period);
            unawaited(_load(requestedPage: 1));
          },
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Counter shifts belong to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see counter shifts',
        message: 'Reading them needs the view sales permission.',
      );
    }
    final Json? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'Each cashier’s till from opening to closing: what it took by '
          'mode, what was counted, and how far the count was from the cash '
          'expected. A shift opens and closes from the counter bill.',
      toolbar: WorkspaceToolbar(
        actions: const [ToolbarAction.refresh],
        isEnabled: (action) => true,
        onAction: (action) => unawaited(_load()),
        commands: [
          ToolbarCommand(
            id: 'view-shift',
            label: 'View',
            icon: Icons.visibility_outlined,
            onPressed: picked == null ? null : () => unawaited(_view(picked)),
          ),
          ToolbarCommand(
            id: 'print-shift-report',
            label: 'Print report',
            icon: Icons.print_outlined,
            onPressed: picked == null ? null : () => unawaited(_print(picked)),
          ),
        ],
      ),
      searchPanel: const SizedBox.shrink(),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary(
              title: stringValue(picked['shift_number']),
              detail: [
                stringValue(picked['cashier_name']),
                _statusLabel(stringValue(picked['status'])),
              ].where((part) => part.isNotEmpty).join(' · '),
              onClear: () => setState(() => _selectedId = null),
            ),
      primaryContent: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: AppSpacing.sm),
          _filters(),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(_error!,
                  style:
                      TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          const SizedBox(height: AppSpacing.md),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _rows.isEmpty
                    ? const WorkspaceEmptyState(
                        title: 'No shifts yet',
                        message: 'Open one from the counter bill.',
                      )
                    : EnterpriseDataGrid<Json>(
                        items: _rows,
                        total: _total,
                        pageOffset: (_page - 1) * _pageSize,
                        rowsPerPage: _pageSize,
                        availableRowsPerPage: const [_pageSize],
                        selectedId: _selectedId,
                        columns: _columns,
                        id: (row) => stringValue(row['id']),
                        cells: _cells,
                        onSelect: (row) =>
                            setState(() => _selectedId = stringValue(row['id'])),
                        onOpen: (row) => unawaited(_view(row)),
                        onPageChanged: (offset) {
                          final int next = offset ~/ _pageSize + 1;
                          if (next != _page) {
                            unawaited(_load(requestedPage: next));
                          }
                        },
                      ),
          ),
        ],
      ),
      statusBar: WorkspaceStatusBar(
        total: _total,
        selected: picked != null,
        message: 'Counter shifts',
      ),
    );
  }
}

/// One shift read afresh: its cashier, its times, the takings by mode and the
/// count against the cash expected.
class _ShiftSummaryDialog extends StatefulWidget {
  const _ShiftSummaryDialog({required this.api, required this.shiftId});

  final ApiClient api;
  final String shiftId;

  @override
  State<_ShiftSummaryDialog> createState() => _ShiftSummaryDialogState();
}

class _ShiftSummaryDialogState extends State<_ShiftSummaryDialog> {
  Json? _shift;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_read());
  }

  Future<void> _read() async {
    try {
      final Json shift = await widget.api.counterShift(widget.shiftId);
      if (mounted) setState(() => _shift = shift);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  Widget _line(String label, String value, {bool bold = false}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 1),
        child: Row(
          children: [
            Expanded(child: Text(label)),
            Text(value,
                style: bold ? const TextStyle(fontWeight: FontWeight.w600) : null),
          ],
        ),
      );

  Widget _body(BuildContext context) {
    final Json? shift = _shift;
    if (_error != null) {
      return Text(_error!,
          style: TextStyle(color: Theme.of(context).colorScheme.error));
    }
    if (shift == null) return const Center(child: CircularProgressIndicator());
    final dynamic rawSummary = shift['summary'];
    final Json summary = rawSummary is Map
        ? Map<String, dynamic>.from(rawSummary)
        : <String, dynamic>{};
    final dynamic rawTenders = summary['tenders'];
    final Map<String, dynamic> tenders = rawTenders is Map
        ? Map<String, dynamic>.from(rawTenders)
        : <String, dynamic>{};
    final bool closed = stringValue(shift['status']) == 'CLOSED';
    final double difference =
        double.tryParse(stringValue(shift['difference'])) ?? 0;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _line('Cashier', stringValue(shift['cashier_name'])),
        _line('Opened', shiftStamp(shift['opened_at'])),
        if (closed) _line('Closed', shiftStamp(shift['closed_at'])),
        const Divider(),
        _line('Bills', '${summary['bills'] ?? 0}'),
        _line('Total billed', _money(summary['total_billed'])),
        for (final MapEntry<String, dynamic> entry in tenders.entries)
          _line(entry.key, _money(entry.value)),
        if ((summary['held_bills'] as num?) != null &&
            (summary['held_bills'] as num) > 0)
          _line('Bills still held', '${summary['held_bills']}'),
        const Divider(),
        _line('Opening float', _money(shift['opening_float'])),
        _line('Cash expected', _money(shift['expected_cash']), bold: true),
        if (closed) ...[
          _line('Cash counted', _money(shift['counted_cash'])),
          Text(differenceLabel(difference),
              key: const ValueKey('shift-summary-difference')),
          if (stringValue(shift['closing_note']).isNotEmpty)
            Text('Note: ${stringValue(shift['closing_note'])}'),
        ],
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('Shift ${stringValue(_shift?['shift_number'])}'.trim()),
      content: SizedBox(
        width: 420,
        child: SingleChildScrollView(child: _body(context)),
      ),
      actions: [
        TextButton(
          key: const ValueKey('shift-summary-close'),
          onPressed: () => Navigator.pop(context),
          child: const Text('Close'),
        ),
      ],
    );
  }
}
