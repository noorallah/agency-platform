import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/branch_warehouse.dart';
import '../../models/product.dart';
import '../../models/repack.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';
import 'repack_dialog.dart';

/// Repacking and bulk breaking (STK-4): a sack split into packets, loose
/// goods made up into a carton.
///
/// Lists the firm's repacks; "New repack" posts one, and "Cancel repack"
/// reverses the one picked with a reason. Posting and cancelling need
/// `INVENTORY_ADJUST`; looking needs only `INVENTORY_VIEW`.
class RepackingPage extends StatefulWidget {
  const RepackingPage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<RepackingPage> createState() => _RepackingPageState();
}

class _RepackingPageState extends State<RepackingPage> {
  List<RepackRecord> _rows = const [];
  String? _selectedId;
  String? _error;
  bool _loading = true;
  bool _busy = false;

  bool get _mayPost => widget.permissions.hasPermission('INVENTORY_ADJUST');

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
    try {
      final List<RepackRecord> rows = await widget.api.repacks();
      if (!mounted) return;
      setState(() {
        _rows = rows;
        if (!rows.any((row) => row.id == _selectedId)) _selectedId = null;
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

  RepackRecord? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  void _toast(String message, AppNotificationKind kind) {
    if (!mounted) return;
    NotificationService.show(context, message, kind: kind);
  }

  Future<void> _new() async {
    setState(() => _busy = true);
    List<BranchRecord> branches = const [];
    List<WarehouseRecord> warehouses = const [];
    List<Product> products = const [];
    try {
      final List<dynamic> results = await Future.wait<dynamic>([
        fetchAllPages((page) =>
            widget.api.branches(page: page, pageSize: maxApiPageSize)),
        fetchAllPages((page) =>
            widget.api.warehouses(page: page, pageSize: maxApiPageSize)),
        fetchAllPages((page) =>
            widget.api.products(page: page, pageSize: maxApiPageSize)),
      ]);
      branches = results[0] as List<BranchRecord>;
      warehouses = results[1] as List<WarehouseRecord>;
      products = results[2] as List<Product>;
    } on ApiException catch (error) {
      _toast(error.message, AppNotificationKind.error);
      if (mounted) setState(() => _busy = false);
      return;
    }
    if (!mounted) return;
    setState(() => _busy = false);
    final dynamic posted = await showDialog<dynamic>(
      context: context,
      builder: (context) => RepackDialog(
        branches: [
          for (final BranchRecord branch in branches)
            RepackOption(id: branch.id, label: '${branch.code} - ${branch.name}'),
        ],
        warehouses: [
          for (final WarehouseRecord warehouse in warehouses)
            RepackOption(
              id: warehouse.id,
              label: '${warehouse.code} - ${warehouse.name}',
              parentId: warehouse.branchId,
            ),
        ],
        products: [
          for (final Product product in products)
            RepackOption(
              id: product.id,
              label: '${product.code} - ${product.name}',
              tracksBatch: product.trackBatch,
              tracksExpiry: product.trackExpiry,
            ),
        ],
        onSave: (body) async {
          await widget.api.createRepack(body);
        },
      ),
    );
    if (posted == null || !mounted) return;
    _toast('Repack posted.', AppNotificationKind.success);
    await _load();
  }

  Future<void> _cancel(RepackRecord row) async {
    final String? reason = await askForReason(
      context,
      title: 'Cancel repack ${row.repackNumber}',
      explanation: 'Every movement is reversed and the stock goes back as it '
          'was. The reason stays on the record.',
      confirmLabel: 'Cancel repack',
      cancelLabel: 'Keep it',
    );
    if (reason == null || !mounted) return;
    setState(() => _busy = true);
    try {
      await widget.api.cancelRepack(row.id, reason);
      _toast('Repack cancelled.', AppNotificationKind.success);
    } on ApiException catch (error) {
      _toast(error.message, AppNotificationKind.error);
    }
    if (!mounted) return;
    setState(() => _busy = false);
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    final RepackRecord? selected = _selected;
    final bool idle = !_busy && !_loading;
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(
            spacing: AppSpacing.md,
            runSpacing: AppSpacing.sm,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              FilledButton.icon(
                key: const ValueKey('repack-new'),
                onPressed: _mayPost && idle ? () => unawaited(_new()) : null,
                icon: const Icon(Icons.add),
                label: const Text('New repack'),
              ),
              OutlinedButton.icon(
                key: const ValueKey('repack-cancel'),
                onPressed: _mayPost &&
                        idle &&
                        selected != null &&
                        !selected.isCancelled
                    ? () => unawaited(_cancel(selected))
                    : null,
                icon: const Icon(Icons.undo),
                label: const Text('Cancel repack'),
              ),
              OutlinedButton.icon(
                onPressed: _loading ? null : () => unawaited(_load()),
                icon: const Icon(Icons.refresh),
                label: const Text('Refresh'),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            'Break bulk into packs or make packs up into a larger one. Stock '
            'moves in the same document and the value follows it.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          if (_error != null) ...[
            const SizedBox(height: AppSpacing.sm),
            Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
          const SizedBox(height: AppSpacing.md),
          Expanded(child: _content(selected)),
        ],
      ),
    );
  }

  Widget _content(RepackRecord? selected) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_rows.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No repacks yet',
        message: 'Post one when bulk stock is broken into packs or packs are '
            'made up into a larger one.',
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(
          flex: 3,
          child: EnterpriseDataGrid<RepackRecord>(
            items: _rows,
            total: _rows.length,
            pageOffset: 0,
            rowsPerPage: _rows.length,
            availableRowsPerPage: [_rows.length],
            selectedId: _selectedId,
            columns: const [
              GridColumn(key: 'number', label: 'Repack'),
              GridColumn(key: 'date', label: 'Date'),
              GridColumn(key: 'consumed', label: 'Consumed', numeric: true),
              GridColumn(key: 'wastage', label: 'Wastage %', numeric: true),
              GridColumn(key: 'status', label: 'Status'),
            ],
            id: (row) => row.id,
            cells: (row) => [
              row.repackNumber,
              row.repackDate,
              row.consumedValue,
              row.wastagePercent,
              row.isCancelled ? 'Cancelled' : 'Posted',
            ],
            onSelect: (row) => setState(() => _selectedId = row.id),
            onPageChanged: (_) {},
          ),
        ),
        if (selected != null) ...[
          const SizedBox(height: AppSpacing.md),
          Expanded(flex: 2, child: _details(selected)),
        ],
      ],
    );
  }

  Widget _lineRows(String title, Iterable<RepackLineRecord> lines,
      {required bool showValue}) {
    final TextTheme text = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(title, style: text.titleSmall),
        for (final RepackLineRecord line in lines)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Row(children: [
              Expanded(
                child: Text(line.productLabel, overflow: TextOverflow.ellipsis),
              ),
              Text('Qty ${line.quantity}'),
              if (showValue) ...[
                const SizedBox(width: AppSpacing.md),
                Text('Carried value ${line.value}'),
              ],
            ]),
          ),
      ],
    );
  }

  Widget _details(RepackRecord row) {
    final TextTheme text = Theme.of(context).textTheme;
    return Card(
      key: const ValueKey('repack-details'),
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('${row.repackNumber} - ${row.repackDate}',
                style: text.titleMedium),
            const SizedBox(height: AppSpacing.sm),
            Wrap(spacing: AppSpacing.lg, runSpacing: AppSpacing.xs, children: [
              Text('Consumed value ${row.consumedValue}'),
              Text('Wastage ${row.wastageValue} (${row.wastagePercent}%)'),
            ]),
            if (row.remarks.isNotEmpty) Text('Remarks: ${row.remarks}'),
            if (row.isCancelled && row.cancelReason.isNotEmpty)
              Text('Cancelled: ${row.cancelReason}'),
            const SizedBox(height: AppSpacing.sm),
            _lineRows('Consumed', row.consumed, showValue: false),
            const SizedBox(height: AppSpacing.sm),
            _lineRows('Produced', row.produced, showValue: true),
          ],
        ),
      ),
    );
  }
}
