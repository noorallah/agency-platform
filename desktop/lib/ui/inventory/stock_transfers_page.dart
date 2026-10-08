import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/batch_serial.dart';
import '../../models/branch_warehouse.dart';
import '../../models/product.dart';
import '../../models/stock_transfer.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/printed_document.dart';
import '../workspace/reason_prompt.dart';
import 'stock_transfer_dialog.dart';
import 'stock_transfer_steps_dialogs.dart';

/// Stock transfers between warehouses (STK-1), as a document: a draft is
/// written, dispatched with a challan, and received at the other end, where a
/// shortage is written off and breakage is recorded.
///
/// Looking needs `INVENTORY_VIEW`; writing, dispatching, receiving and
/// cancelling need `INVENTORY_ADJUST`.
class StockTransfersPage extends StatefulWidget {
  const StockTransfersPage({
    super.key,
    required this.api,
    required this.permissions,
    this.openPdfOverride,
  });

  final ApiClient api;
  final PermissionService permissions;

  /// Replaces the print preview, for tests.
  final Future<void> Function(String name, List<int> bytes)? openPdfOverride;

  @override
  State<StockTransfersPage> createState() => _StockTransfersPageState();
}

class _StockTransfersPageState extends State<StockTransfersPage> {
  static const List<String> _statuses = [
    'DRAFT',
    'DISPATCHED',
    'RECEIVED',
    'CANCELLED',
  ];

  List<StockTransferRecord> _rows = const [];
  String? _selectedId;
  String? _status;
  String? _error;
  bool _loading = true;
  bool _busy = false;

  bool get _mayWrite => widget.permissions.hasPermission('INVENTORY_ADJUST');

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
      final List<StockTransferRecord> rows =
          await widget.api.stockTransfers(status: _status);
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

  StockTransferRecord? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  void _toast(String message, AppNotificationKind kind) {
    if (!mounted) return;
    NotificationService.show(context, message, kind: kind);
  }

  /// Runs one action against the server, then reloads whatever the outcome.
  Future<void> _act(
    Future<void> Function() call,
    String success,
  ) async {
    setState(() => _busy = true);
    try {
      await call();
      _toast(success, AppNotificationKind.success);
    } on ApiException catch (error) {
      _toast(error.message, AppNotificationKind.error);
    }
    if (!mounted) return;
    setState(() => _busy = false);
    await _load();
  }

  Future<void> _openEditor(StockTransferRecord? existing) async {
    setState(() => _busy = true);
    List<WarehouseRecord> warehouses = const [];
    List<Product> products = const [];
    try {
      // A draft is re-read before it is edited, so the editor holds what the
      // server holds now rather than what the list read a while ago.
      if (existing != null) {
        existing = await widget.api.stockTransfer(existing.id);
      }
      final List<dynamic> results = await Future.wait<dynamic>([
        fetchAllPages((page) =>
            widget.api.warehouses(page: page, pageSize: maxApiPageSize)),
        fetchAllPages((page) =>
            widget.api.products(page: page, pageSize: maxApiPageSize)),
      ]);
      warehouses = results[0] as List<WarehouseRecord>;
      products = results[1] as List<Product>;
    } on ApiException catch (error) {
      _toast(error.message, AppNotificationKind.error);
      if (mounted) setState(() => _busy = false);
      return;
    }
    if (!mounted) return;
    setState(() => _busy = false);
    final dynamic saved = await showDialog<dynamic>(
      context: context,
      builder: (context) => StockTransferDialog(
        existing: existing,
        warehouses: [
          for (final WarehouseRecord warehouse in warehouses)
            TransferOption(
              id: warehouse.id,
              label: '${warehouse.code} - ${warehouse.name}',
            ),
        ],
        products: [
          for (final Product product in products)
            TransferOption(
              id: product.id,
              label: '${product.code} - ${product.name}',
              trackSerial: product.trackSerial,
            ),
        ],
        loadSerials: (productId, warehouseId) async {
          final List<SerialRecord> found = await fetchAllPages<SerialRecord>(
            (page) => widget.api.serials(
              page: page,
              pageSize: maxApiPageSize,
              sortBy: 'serial_number',
              descending: false,
              filters: SerialQuery(
                productId: productId,
                warehouseId: warehouseId,
                status: 'AVAILABLE',
              ),
            ),
          );
          return [
            for (final SerialRecord serial in found)
              PickedSerial(id: serial.id, serialNumber: serial.serialNumber),
          ];
        },
        loadBatches: (productId, warehouseId) async {
          final result = await widget.api.batches(
            pageSize: maxApiPageSize,
            filters: BatchQuery(productId: productId, warehouseId: warehouseId),
          );
          return [
            for (final BatchRecord batch in result.items)
              TransferOption(
                id: batch.id,
                label: '${batch.batchNumber} (${batch.availableQuantity})',
              ),
          ];
        },
        onSave: (body) async {
          if (existing == null) {
            await widget.api.createStockTransfer(body);
          } else {
            await widget.api.updateStockTransfer(existing.id, body);
          }
        },
      ),
    );
    if (saved == null || !mounted) return;
    _toast('Draft saved.', AppNotificationKind.success);
    await _load();
  }

  Future<void> _dispatch(StockTransferRecord row) async {
    final dynamic done = await showDialog<dynamic>(
      context: context,
      builder: (context) => DispatchTransferDialog(
        transfer: row,
        onSave: (body) async {
          await widget.api.dispatchStockTransfer(row.id, body);
        },
      ),
    );
    if (done == null || !mounted) return;
    _toast('Transfer dispatched.', AppNotificationKind.success);
    await _load();
  }

  Future<void> _receive(StockTransferRecord row) async {
    final dynamic done = await showDialog<dynamic>(
      context: context,
      builder: (context) => ReceiveTransferDialog(
        transfer: row,
        onSave: (body) async {
          await widget.api.receiveStockTransfer(row.id, body);
        },
      ),
    );
    if (done == null || !mounted) return;
    _toast('Transfer received.', AppNotificationKind.success);
    await _load();
  }

  Future<void> _cancel(StockTransferRecord row) async {
    final String? reason = await askForReason(
      context,
      title: 'Cancel transfer ${row.transferNumber}',
      explanation: row.isDispatched
          ? 'The goods in transit go back to the source warehouse. The '
              'reason stays on the record.'
          : 'The draft is closed without moving any stock. The reason stays '
              'on the record.',
      confirmLabel: 'Cancel transfer',
      cancelLabel: 'Keep it',
    );
    if (reason == null || !mounted) return;
    await _act(
      () async {
        await widget.api.cancelStockTransfer(row.id, reason);
      },
      'Transfer cancelled.',
    );
  }

  Future<void> _printChallan(StockTransferRecord row) async {
    setState(() => _busy = true);
    try {
      final List<int> pdf = await widget.api.stockTransferChallan(row.id);
      if (!mounted) return;
      final String name = 'Challan ${row.transferNumber}';
      if (widget.openPdfOverride != null) {
        await widget.openPdfOverride!(name, pdf);
      } else {
        await printDocument(context, bytes: pdf, documentName: name);
      }
    } on ApiException catch (error) {
      _toast(error.message, AppNotificationKind.error);
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final StockTransferRecord? selected = _selected;
    final bool idle = !_busy && !_loading;
    final bool canAct = _mayWrite && idle && selected != null;
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
                key: const ValueKey('transfer-new'),
                onPressed:
                    _mayWrite && idle ? () => unawaited(_openEditor(null)) : null,
                icon: const Icon(Icons.add),
                label: const Text('New transfer'),
              ),
              OutlinedButton.icon(
                key: const ValueKey('transfer-edit'),
                onPressed: canAct && selected.isDraft
                    ? () => unawaited(_openEditor(selected))
                    : null,
                icon: const Icon(Icons.edit_outlined),
                label: const Text('Edit'),
              ),
              OutlinedButton.icon(
                key: const ValueKey('transfer-dispatch'),
                onPressed: canAct && selected.isDraft
                    ? () => unawaited(_dispatch(selected))
                    : null,
                icon: const Icon(Icons.local_shipping_outlined),
                label: const Text('Dispatch'),
              ),
              OutlinedButton.icon(
                key: const ValueKey('transfer-receive'),
                onPressed: canAct && selected.isDispatched
                    ? () => unawaited(_receive(selected))
                    : null,
                icon: const Icon(Icons.move_to_inbox_outlined),
                label: const Text('Receive'),
              ),
              OutlinedButton.icon(
                key: const ValueKey('transfer-challan'),
                onPressed: idle && selected != null && selected.hasChallan
                    ? () => unawaited(_printChallan(selected))
                    : null,
                icon: const Icon(Icons.print_outlined),
                label: const Text('Print challan'),
              ),
              OutlinedButton.icon(
                key: const ValueKey('transfer-cancel'),
                onPressed: canAct && (selected.isDraft || selected.isDispatched)
                    ? () => unawaited(_cancel(selected))
                    : null,
                icon: const Icon(Icons.undo),
                label: const Text('Cancel transfer'),
              ),
              SizedBox(
                width: 180,
                child: DropdownButtonFormField<String?>(
                  key: const ValueKey('transfer-status-filter'),
                  isExpanded: true,
                  initialValue: _status,
                  decoration: const InputDecoration(
                    labelText: 'Status',
                    isDense: true,
                  ),
                  items: [
                    const DropdownMenuItem<String?>(
                      value: null,
                      child: Text('All'),
                    ),
                    for (final String status in _statuses)
                      DropdownMenuItem<String?>(
                        value: status,
                        child: Text(StockTransferRecord(
                          id: '',
                          transferNumber: '',
                          transferDate: '',
                          status: status,
                        ).statusLabel),
                      ),
                  ],
                  onChanged: _loading
                      ? null
                      : (value) {
                          _status = value;
                          unawaited(_load());
                        },
                ),
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
            'Move stock from one warehouse to another. It leaves the source '
            'when dispatched and arrives when received; what does not arrive '
            'is written off as a shortage.',
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

  Widget _content(StockTransferRecord? selected) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_rows.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No stock transfers',
        message: 'Write one when stock has to move between warehouses.',
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(
          flex: 3,
          child: EnterpriseDataGrid<StockTransferRecord>(
            items: _rows,
            total: _rows.length,
            pageOffset: 0,
            rowsPerPage: _rows.length,
            availableRowsPerPage: [_rows.length],
            selectedId: _selectedId,
            columns: const [
              GridColumn(key: 'number', label: 'Transfer'),
              GridColumn(key: 'date', label: 'Date'),
              GridColumn(key: 'from', label: 'From'),
              GridColumn(key: 'to', label: 'To'),
              GridColumn(key: 'status', label: 'Status'),
              GridColumn(key: 'value', label: 'Value', numeric: true),
              GridColumn(key: 'shortage', label: 'Shortage', numeric: true),
            ],
            id: (row) => row.id,
            cells: (row) => [
              row.transferNumber,
              row.transferDate,
              row.fromWarehouseName,
              row.toWarehouseName,
              row.statusLabel,
              row.dispatchedValue,
              row.shortageValue,
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

  Widget _details(StockTransferRecord row) {
    final TextTheme text = Theme.of(context).textTheme;
    return Card(
      key: const ValueKey('transfer-details'),
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('${row.transferNumber} - ${row.transferDate}',
                style: text.titleMedium),
            const SizedBox(height: AppSpacing.sm),
            Wrap(spacing: AppSpacing.lg, runSpacing: AppSpacing.xs, children: [
              Text('${row.fromWarehouseName} to ${row.toWarehouseName}'),
              if (row.vehicleNumber.isNotEmpty)
                Text('Vehicle ${row.vehicleNumber}'),
              if (row.transporterName.isNotEmpty)
                Text('Transporter ${row.transporterName}'),
              if (row.dispatchedOn.isNotEmpty)
                Text('Dispatched ${row.dispatchedOn}'),
              if (row.receivedOn.isNotEmpty) Text('Received ${row.receivedOn}'),
            ]),
            if (row.remarks.isNotEmpty) Text('Remarks: ${row.remarks}'),
            if (row.receiptRemarks.isNotEmpty)
              Text('Receipt: ${row.receiptRemarks}'),
            if (row.isCancelled && row.cancelReason.isNotEmpty)
              Text('Cancelled: ${row.cancelReason}'),
            const SizedBox(height: AppSpacing.sm),
            for (final StockTransferLineRecord line in row.lines)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(children: [
                  Expanded(
                    child: Text(
                      line.batchNumber.isEmpty
                          ? line.productLabel
                          : '${line.productLabel} (${line.batchNumber})',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  Text('Sent ${line.quantity}'),
                  if (row.isReceived) ...[
                    const SizedBox(width: AppSpacing.md),
                    Text('Received ${line.receivedQuantity}'),
                    const SizedBox(width: AppSpacing.md),
                    Text('Damaged ${line.damagedQuantity}'),
                    const SizedBox(width: AppSpacing.md),
                    Text('Short ${line.shortQuantity}'),
                  ],
                ]),
              ),
            // The units a serial-tracked line names, and where each is now.
            for (final StockTransferLineRecord line in row.lines)
              if (line.serials.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Text(
                    key: ValueKey('transfer-serials-${line.lineNumber}'),
                    'Serial numbers, line ${line.lineNumber}: '
                    '${[
                      for (final PickedSerial s in line.serials)
                        s.status.isEmpty || s.status == 'AVAILABLE'
                            ? s.serialNumber
                            : '${s.serialNumber} (${_serialStatus(s.status)})',
                    ].join(', ')}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
          ],
        ),
      ),
    );
  }

  /// A serial's status in words: IN_TRANSIT reads "in transit".
  String _serialStatus(String status) =>
      status.replaceAll('_', ' ').toLowerCase();
}
