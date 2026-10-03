import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/adjustment_approval.dart';
import '../../models/bulk_action.dart';
import '../../models/entities.dart';
import '../../models/product.dart';
import '../workspace/bulk_action.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';

/// Large stock adjustments and write-offs waiting for somebody whose limit is
/// high enough (STK-8).
///
/// Nothing has moved until a request is approved; approving posts the movement
/// the poster could not. Approve and Reject act on the row picked, and ticking
/// more than one offers a bulk approve that is judged per row on the server.
class AdjustmentApprovalsPage extends StatefulWidget {
  const AdjustmentApprovalsPage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<AdjustmentApprovalsPage> createState() =>
      _AdjustmentApprovalsPageState();
}

class _AdjustmentApprovalsPageState extends State<AdjustmentApprovalsPage> {
  String _status = 'PENDING';
  List<AdjustmentRequestRecord> _rows = const [];
  Map<String, String> _productNames = const {};
  Set<String> _ticked = <String>{};
  String? _selectedId;
  String? _error;
  bool _loading = true;
  bool _busy = false;

  bool get _mayDecide => widget.permissions.hasPermission('INVENTORY_ADJUST');

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
      final List<AdjustmentRequestRecord> rows =
          await widget.api.adjustmentRequests(status: _status);
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _ticked =
            _ticked.where((id) => rows.any((row) => row.id == id)).toSet();
        if (!rows.any((row) => row.id == _selectedId)) _selectedId = null;
        _loading = false;
      });
      unawaited(_loadProductNames());
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  /// Names for the products on show. A failed lookup leaves the id in the
  /// column, which still identifies the row.
  Future<void> _loadProductNames() async {
    try {
      final PagedResult<Product> page =
          await widget.api.products(pageSize: 100);
      if (!mounted) return;
      setState(() => _productNames = {
            for (final Product product in page.items)
              product.id: '${product.code} - ${product.name}',
          });
    } on ApiException {
      // The id stands in.
    }
  }

  AdjustmentRequestRecord? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  List<AdjustmentRequestRecord> get _tickedRows =>
      _rows.where((row) => _ticked.contains(row.id)).toList();

  void _toast(String message, AppNotificationKind kind) {
    if (!mounted) return;
    NotificationService.show(context, message, kind: kind);
  }

  Future<void> _approve(AdjustmentRequestRecord row) async {
    setState(() => _busy = true);
    try {
      await widget.api.approveAdjustmentRequest(row.id);
      _toast('Approved. The stock has moved.', AppNotificationKind.success);
    } on ApiException catch (error) {
      _toast(error.message, AppNotificationKind.error);
    }
    if (!mounted) return;
    setState(() => _busy = false);
    await _load();
  }

  Future<void> _reject(AdjustmentRequestRecord row) async {
    final String? reason = await askForReason(
      context,
      title: 'Reject this request',
      explanation: 'The person who asked sees why. Nothing moves.',
      confirmLabel: 'Reject',
    );
    if (reason == null || !mounted) return;
    setState(() => _busy = true);
    try {
      await widget.api.rejectAdjustmentRequest(row.id, reason);
      _toast('Rejected.', AppNotificationKind.success);
    } on ApiException catch (error) {
      _toast(error.message, AppNotificationKind.error);
    }
    if (!mounted) return;
    setState(() => _busy = false);
    await _load();
  }

  Future<void> _bulkApprove() async {
    final List<BulkRow> rows = [
      for (final AdjustmentRequestRecord row in _tickedRows)
        (id: row.id, version: row.version),
    ];
    await runBulkAction(
      context,
      verb: 'Approved',
      rows: rows,
      send: widget.api.bulkApproveAdjustmentRequests,
    );
    if (!mounted) return;
    setState(() => _ticked = <String>{});
    await _load();
  }

  String _when(String iso) {
    if (iso.length < 16) return iso;
    return iso.substring(0, 16).replaceFirst('T', ' ');
  }

  @override
  Widget build(BuildContext context) {
    final AdjustmentRequestRecord? selected = _selected;
    final bool pending = _status == 'PENDING';
    final bool canAct = _mayDecide && !_busy && !_loading;
    final bool bulk = _ticked.length > 1;
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
              SegmentedButton<String>(
                key: const ValueKey('adjustment-approvals-status'),
                segments: const [
                  ButtonSegment(value: 'PENDING', label: Text('Pending')),
                  ButtonSegment(value: 'APPROVED', label: Text('Approved')),
                  ButtonSegment(value: 'REJECTED', label: Text('Rejected')),
                ],
                selected: {_status},
                onSelectionChanged: (value) {
                  setState(() {
                    _status = value.first;
                    _ticked = <String>{};
                    _selectedId = null;
                  });
                  unawaited(_load());
                },
              ),
              if (pending && bulk)
                FilledButton.icon(
                  key: const ValueKey('adjustment-bulk-approve'),
                  onPressed: canAct ? () => unawaited(_bulkApprove()) : null,
                  icon: const Icon(Icons.done_all),
                  label: Text('Approve ${_ticked.length} selected'),
                )
              else if (pending) ...[
                FilledButton.icon(
                  key: const ValueKey('adjustment-approve'),
                  onPressed: canAct && selected != null
                      ? () => unawaited(_approve(selected))
                      : null,
                  icon: const Icon(Icons.check_circle_outline),
                  label: const Text('Approve'),
                ),
                OutlinedButton.icon(
                  key: const ValueKey('adjustment-reject'),
                  onPressed: canAct && selected != null
                      ? () => unawaited(_reject(selected))
                      : null,
                  icon: const Icon(Icons.cancel_outlined),
                  label: const Text('Reject'),
                ),
              ],
              OutlinedButton.icon(
                onPressed: _loading ? null : () => unawaited(_load()),
                icon: const Icon(Icons.refresh),
                label: const Text('Refresh'),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            'Approving posts the movement; it is refused if it is above your '
            'own limit.',
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
          Expanded(child: _content(pending)),
        ],
      ),
    );
  }

  Widget _content(bool pending) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_rows.isEmpty) {
      return WorkspaceEmptyState(
        title: 'Nothing here',
        message: pending
            ? 'No adjustment or write-off is waiting for approval.'
            : 'No ${_status.toLowerCase()} requests.',
      );
    }
    return EnterpriseDataGrid<AdjustmentRequestRecord>(
      items: _rows,
      total: _rows.length,
      pageOffset: 0,
      rowsPerPage: _rows.length,
      availableRowsPerPage: [_rows.length],
      selectedId: _selectedId,
      selectedIds: _ticked,
      onSelectionChanged:
          pending ? (ticked) => setState(() => _ticked = ticked) : null,
      columns: const [
        GridColumn(key: 'kind', label: 'Kind'),
        GridColumn(key: 'product', label: 'Product'),
        GridColumn(key: 'quantity', label: 'Quantity', numeric: true),
        GridColumn(key: 'value', label: 'Estimated value', numeric: true),
        GridColumn(key: 'requested', label: 'Requested at'),
      ],
      id: (row) => row.id,
      cells: (row) => [
        row.kindLabel,
        _productNames[row.productId] ?? row.productId,
        row.quantity,
        row.estimatedValue,
        _when(row.requestedAt),
      ],
      onSelect: (row) => setState(() => _selectedId = row.id),
      onPageChanged: (_) {},
    );
  }
}
