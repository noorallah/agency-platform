import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/document_framework.dart';
import '../../models/goods_receipt.dart';
import '../document_framework/document_framework_widgets.dart';
import '../workspace/desktop_framework.dart';

class GoodsReceiptManagementPage extends StatefulWidget {
  const GoodsReceiptManagementPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    required this.tabId,
    this.onNavigateToTab,
    this.onOpenGlobalSearch,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final String tabId;
  final ValueChanged<String>? onNavigateToTab;
  final Future<void> Function()? onOpenGlobalSearch;

  @override
  State<GoodsReceiptManagementPage> createState() =>
      _GoodsReceiptManagementPageState();
}

class _GoodsReceiptManagementPageState extends State<GoodsReceiptManagementPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  bool _loading = false;
  String? _error;
  int _page = 1;
  int _total = 0;
  Json _summary = const {};
  List<GoodsReceiptRecord> _receipts = const [];
  GoodsReceiptRecord? _selected;
  List<DocumentTimelineSnapshot> _history = const [];

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load({int? requestedPage}) async {
    if (!widget.hasActiveFirm || !widget.permissions.hasPermission('PURCHASE_VIEW')) {
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
      if (requestedPage != null) {
        _page = requestedPage;
      }
    });
    try {
      final List<dynamic> results = await Future.wait<dynamic>([
        widget.api.goodsReceiptSummary(),
        widget.api.goodsReceipts(
          page: _page,
          pageSize: _rowsPerPage,
          search: _search.text.trim(),
          sortBy: 'receipt_date',
          descending: true,
          filters: _filtersForTab(),
        ),
      ]);
      final Json summary = results[0] as Json;
      final PagedResult<GoodsReceiptRecord> receipts =
          results[1] as PagedResult<GoodsReceiptRecord>;
      GoodsReceiptRecord? selected = _selected;
      if (selected != null) {
        final List<GoodsReceiptRecord> matches =
            receipts.items.where((item) => item.id == selected!.id).toList();
        selected = matches.isEmpty ? null : matches.first;
      }
      if (selected == null && receipts.items.isNotEmpty) {
        selected = receipts.items.first;
      }
      List<DocumentTimelineSnapshot> history = const [];
      if (selected != null) {
        try {
          history = await widget.api.goodsReceiptHistory(selected.id);
        } on ApiException {
          history = const [];
        }
      }
      if (!mounted) return;
      setState(() {
        _summary = summary;
        _receipts = receipts.items;
        _total = receipts.total;
        _selected = selected;
        _history = history;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString();
        _receipts = const [];
        _selected = null;
        _history = const [];
        _total = 0;
      });
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  /// Whether [action] is valid for the selected receipt's current status.
  bool _isReceiptActionAllowed(DocumentToolbarAction action) {
    final String status = _selected?.status.trim().toUpperCase() ?? '';
    return switch (action) {
      DocumentToolbarAction.requestApproval => status == 'DRAFT',
      DocumentToolbarAction.cancel => status != 'CANCELLED' && status != 'CLOSED',
      DocumentToolbarAction.close => status != 'CLOSED',
      _ => false,
    };
  }

  /// Run a lifecycle action against the selected receipt and reload.
  Future<void> _runReceiptAction(DocumentToolbarAction action) async {
    final GoodsReceiptRecord? selected = _selected;
    if (selected == null || !_isReceiptActionAllowed(action)) return;
    try {
      switch (action) {
        case DocumentToolbarAction.requestApproval:
          await widget.api.completeGoodsReceipt(selected.id);
        case DocumentToolbarAction.cancel:
          await widget.api.cancelGoodsReceipt(selected.id);
        case DocumentToolbarAction.close:
          await widget.api.closeGoodsReceipt(selected.id);
        default:
          return;
      }
      await _load();
      if (!mounted) return;
      NotificationService.show(
        context,
        'Goods receipt ${selected.grnNumber} updated.',
        kind: AppNotificationKind.success,
      );
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
    final DocumentTotalsSnapshot totals =
        _selected?.toTotals() ?? const DocumentTotalsSnapshot(
          subtotal: '0',
          discount: '0',
          tax: '0',
          charges: '0',
          roundOff: '0',
          grandTotal: '0',
        );
    final DocumentHeaderSnapshot header = _selected?.toHeader() ??
        const DocumentHeaderSnapshot(
          documentTypeCode: 'GOODS_RECEIPT_NOTE',
          documentTypeName: 'Goods Receipt Note',
          documentNumber: '-',
          documentDate: '-',
          status: 'DRAFT',
        );
    return ModuleWorkspaceFrame(
      title: 'Goods Receipt Notes',
      description: 'Manage GRN execution, receipt history, and inventory posting.',
      breadcrumbs: const ['Workspace', 'Goods Receipts'],
      status: _loading
          ? const LinearProgressIndicator(minHeight: 2)
          : null,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 12),
            child: SummaryCards(
              children: [
                _summaryCard('Total', '${_summary['total'] ?? 0}'),
                _summaryCard('Draft', '${_summary['draft'] ?? 0}'),
                _summaryCard('Completed', '${_summary['completed'] ?? 0}'),
                _summaryCard('Cancelled', '${_summary['cancelled'] ?? 0}'),
                _summaryCard('Closed', '${_summary['closed'] ?? 0}'),
              ],
            ),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    flex: 3,
                    child: Card(
                      clipBehavior: Clip.antiAlias,
                      child: Column(
                        children: [
                          Padding(
                            padding: const EdgeInsets.all(16),
                            child: TextField(
                              controller: _search,
                              decoration: const InputDecoration(
                                labelText: 'Search receipts',
                                prefixIcon: Icon(Icons.search),
                              ),
                              onSubmitted: (_) => _load(requestedPage: 1),
                            ),
                          ),
                          Expanded(
                            child: ListView.separated(
                              itemCount: _receipts.length,
                              separatorBuilder: (_, __) =>
                                  const Divider(height: 1),
                              itemBuilder: (context, index) {
                                final GoodsReceiptRecord row = _receipts[index];
                                final bool selected = _selected?.id == row.id;
                                return ListTile(
                                  selected: selected,
                                  title: Text(row.grnNumber),
                                  subtitle: Text(
                                    '${row.purchaseOrderNumber} • ${row.receiptDate} • ${row.status}',
                                  ),
                                  trailing: Text(row.grandTotal),
                                  onTap: () => setState(() {
                                    _selected = row;
                                  }),
                                );
                              },
                            ),
                          ),
                          WorkspacePager(
                            page: _page,
                            pageSize: _rowsPerPage,
                            total: _total,
                            onPageChanged: (next) =>
                                _load(requestedPage: next),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    flex: 4,
                    child: SingleChildScrollView(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          EnterpriseDocumentToolbar(
                            actions: const [
                              DocumentToolbarAction.requestApproval,
                              DocumentToolbarAction.cancel,
                              DocumentToolbarAction.close,
                            ],
                            // A goods receipt has no approve/reject step, and
                            // print, email and direct create have no backend at
                            // all — offering them enabled meant eight buttons
                            // that silently did nothing.
                            isEnabled: (action) =>
                                _selected != null && _isReceiptActionAllowed(action),
                            onAction: _runReceiptAction,
                          ),
                          const SizedBox(height: 12),
                          EnterpriseDocumentHeader(header: header),
                          const SizedBox(height: 12),
                          EnterpriseDocumentLines(
                            lines: _selected == null
                                ? const []
                                : [
                                    for (final GoodsReceiptLine line
                                        in _selected!.lines)
                                      DocumentLineSnapshot(
                                        lineNumber: line.lineNumber,
                                        product: line.productId,
                                        description: line.description,
                                        uom: line.inventoryUomId,
                                        packaging: line.packagingTypeId,
                                        quantity: line.currentReceiptQuantity,
                                        freeQuantity: line.freeQuantity,
                                        unitPrice: line.unitPrice,
                                        discount: line.discountAmount,
                                        taxProfile: line.taxProfileId,
                                        amount: line.grossAmount,
                                        netAmount: line.netAmount,
                                        remarks: line.remarks,
                                      ),
                                  ],
                          ),
                          const SizedBox(height: 12),
                          EnterpriseTotalsPanel(totals: totals),
                          const SizedBox(height: 12),
                          EnterpriseTimeline(entries: _history),
                          const SizedBox(height: 12),
                          EnterpriseApprovalPanel(
                            status: header.status,
                            message: 'Approval workflow placeholder.',
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
        ],
      ),
    );
  }

  Widget _summaryCard(String label, String value) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: Theme.of(context).textTheme.labelMedium),
              const SizedBox(height: 8),
              Text(value, style: Theme.of(context).textTheme.headlineSmall),
            ],
          ),
        ),
      );

  Map<String, String> _filtersForTab() => switch (widget.tabId) {
        'pending-receipts' => const {'status': 'DRAFT'},
        'completed-receipts' => const {'status': 'COMPLETED'},
        'grn-history' => const {'status': 'COMPLETED'},
        _ => const {},
      };
}
