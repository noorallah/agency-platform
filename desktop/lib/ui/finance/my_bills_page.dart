// My Bills to Collect (backlog 123): the collector's one screen. It lists the
// unpaid bills the office handed to the signed-in person and, marked apart,
// the other unpaid bills of the same customers. Read-only: it records no
// receipt and takes nothing back. Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/bill_handover.dart';
import '../../models/entities.dart';
import '../../phase2/display_dates.dart';
import '../../phase2/indian_format.dart';
import '../workspace/desktop_framework.dart';

const int _pageSize = 50;

/// A stored day as the person's own date format writes it; blank stays blank.
String _day(String value) {
  final DateTime? parsed =
      value.length >= 10 ? DateTime.tryParse(value.substring(0, 10)) : null;
  return parsed == null ? value : DisplayDates.write(parsed);
}

String _bills(int count) => count == 1 ? '1 bill' : '$count bills';

class MyBillsPage extends StatefulWidget {
  const MyBillsPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<MyBillsPage> createState() => _MyBillsPageState();
}

class _MyBillsPageState extends State<MyBillsPage> {
  static const List<GridColumn> _columns = [
    GridColumn(key: 'customer', label: 'Customer'),
    GridColumn(key: 'bill', label: 'Bill'),
    GridColumn(key: 'bill-date', label: 'Date', priority: 2),
    GridColumn(key: 'due', label: 'Due', priority: 2),
    GridColumn(key: 'overdue', label: 'Days overdue', numeric: true),
    GridColumn(key: 'outstanding', label: 'Outstanding', numeric: true),
    GridColumn(key: 'with', label: 'With me'),
  ];

  List<MyBill> _rows = const [];
  bool _loading = true;
  String? _error;

  bool get _mayView => widget.permissions.hasPermission('COLLECTION_OWN_VIEW');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) unawaited(_load());
  }

  /// Reads every page, so the totals above the grid are the whole list's.
  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _rows = const [];
    });
    try {
      final List<MyBill> rows = await fetchAllPages<MyBill>((page) async {
        final Json response =
            await widget.api.myBillsToCollect(page: page, pageSize: _pageSize);
        final List<MyBill> items = [
          for (final dynamic item in (response['data'] as List? ?? const []))
            if (item is Map) MyBill.fromJson(Map<String, dynamic>.from(item)),
        ];
        return PagedResult<MyBill>(
          items: items,
          total: pagedTotal(response, fallback: items.length),
        );
      });
      if (!mounted) return;
      setState(() {
        _rows = rows;
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

  Iterable<MyBill> get _mine => _rows.where((row) => row.handedToMe);
  Iterable<MyBill> get _others => _rows.where((row) => !row.handedToMe);

  double _sum(Iterable<MyBill> rows) =>
      rows.fold<double>(0, (total, row) => total + row.owed);

  String _line(String label, Iterable<MyBill> rows) =>
      '$label: ${_bills(rows.length)}, '
      '${indianAmount(_sum(rows), full: true)} outstanding';

  Widget _cell(String value, MyBill item) {
    final ThemeData theme = Theme.of(context);
    return Tooltip(
      message: value,
      child: SizedBox(
        width: double.infinity,
        child: Text(
          value,
          overflow: TextOverflow.ellipsis,
          style: item.handedToMe
              ? null
              : TextStyle(color: theme.colorScheme.onSurfaceVariant),
        ),
      ),
    );
  }

  Widget _grid() {
    return EnterpriseDataGrid<MyBill>(
      items: _rows,
      total: _rows.length,
      pageOffset: 0,
      rowsPerPage: _rows.length,
      availableRowsPerPage: [_rows.length],
      columns: _columns,
      id: (row) => row.invoiceId,
      cells: (row) => [
        row.customerLabel,
        row.invoiceNumber,
        _day(row.invoiceDate),
        _day(row.dueDate),
        '${row.daysOverdue}',
        indianAmount(row.owed, full: true),
        row.handedToMe
            ? (row.handedOn.isEmpty
                ? 'With me'
                : 'With me, ${_day(row.handedOn)}')
            : 'Not handed to me',
      ],
      onSelect: (_) {},
      onPageChanged: (_) {},
      cellBuilder: (columnIndex, value, item) => _cell(value, item),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Bills to collect belong to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see the bills to collect',
        message: 'Reading them needs the view own collections permission.',
      );
    }
    final ThemeData theme = Theme.of(context);
    return ManagementWorkspaceLayout(
      toolbar: WorkspaceToolbar(
        actions: const [ToolbarAction.refresh],
        isEnabled: (action) => !_loading,
        onAction: (action) => unawaited(_load()),
      ),
      searchPanel: const SizedBox.shrink(),
      primaryContent: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: AppSpacing.sm),
          if (!_loading && _error == null && _rows.isNotEmpty) ...[
            Text(
              _line('Handed to me', _mine),
              key: const ValueKey('my-bills-mine'),
              style: theme.textTheme.titleSmall,
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              _line('Other unpaid bills of the same customers', _others),
              key: const ValueKey('my-bills-others'),
              style: theme.textTheme.bodySmall,
            ),
          ],
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(_error!,
                  style: TextStyle(color: theme.colorScheme.error)),
            ),
          const SizedBox(height: AppSpacing.sm),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _error != null
                    // A list that could not be read is not an empty bag.
                    ? const SizedBox.shrink()
                    : _rows.isEmpty
                        ? const WorkspaceEmptyState(
                            title: 'No bills handed to you',
                            message:
                                'No bill has been handed to you to collect.',
                          )
                        : _grid(),
          ),
        ],
      ),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: false,
        message: 'My bills to collect',
      ),
    );
  }
}
