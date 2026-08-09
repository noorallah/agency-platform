import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/document_framework.dart';
import '../document_framework/document_framework_widgets.dart';
import '../workspace/workspace_components.dart';
import '../workspace/workspace_templates.dart';

class SalesOrderManagementPage extends StatefulWidget {
  const SalesOrderManagementPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    this.onOpenGlobalSearch,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final Future<void> Function()? onOpenGlobalSearch;

  @override
  State<SalesOrderManagementPage> createState() => _SalesOrderManagementPageState();
}

class _SalesOrderManagementPageState extends State<SalesOrderManagementPage> {
  final TextEditingController _search = TextEditingController();
  bool _loading = false;
  static const int _rowsPerPage = 50;
  int _page = 1;
  int _total = 0;
  String? _error;
  List<Map<String, dynamic>> _orders = const [];
  Map<String, dynamic>? _selected;
  List<DocumentTimelineSnapshot> _history = const [];
  Map<String, dynamic> _summary = const {};

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


  /// Whether the signed-in user may run this lifecycle action.
  ///
  /// The backend gates approve, close, complete and dispatch on
  /// SALES_APPROVE and cancel on SALES_CANCEL. The toolbar used to enable
  /// every action for anyone holding SALES_VIEW, so a read-only user was
  /// offered buttons the server would refuse.
  bool _mayApprove() => widget.permissions.hasPermission('SALES_APPROVE');

  bool _mayRun(DocumentToolbarAction action) => switch (action) {
        DocumentToolbarAction.approve ||
        DocumentToolbarAction.close ||
        DocumentToolbarAction.archive ||
        DocumentToolbarAction.requestApproval =>
          _mayApprove(),
        DocumentToolbarAction.cancel || DocumentToolbarAction.reject =>
          widget.permissions.hasPermission('SALES_CANCEL'),
        DocumentToolbarAction.newDocument =>
          widget.permissions.hasPermission('SALES_CREATE'),
        DocumentToolbarAction.save =>
          widget.permissions.hasPermission('SALES_UPDATE'),
        DocumentToolbarAction.exportDocument =>
          widget.permissions.hasPermission('SALES_EXPORT'),
        _ => true,
      };

  Future<void> _load({int? requestedPage}) async {
    if (!widget.hasActiveFirm || !widget.permissions.hasPermission('SALES_VIEW')) {
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
      final List<dynamic> responses = await Future.wait<dynamic>([
        widget.api.documentSummary('sales-orders'),
        widget.api.documentPage(
          'sales-orders',
          page: _page,
          pageSize: _rowsPerPage,
          search: _search.text.trim(),
          sortBy: 'order_date',
          descending: true,
        ),
      ]);
      final Map<String, dynamic> summary = _unwrap(responses[0]);
      final Map<String, dynamic> page = _unwrap(responses[1]);
      final List<Map<String, dynamic>> rows = ((page['data'] as List?) ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: false);
      final Object? pagination = page['pagination'];
      final int total = pagination is Map
          ? (pagination['total_records'] as num?)?.toInt() ?? rows.length
          : rows.length;
      final Map<String, dynamic>? selected = rows.isEmpty
          ? null
          : (_selected == null
              ? rows.first
              : rows.firstWhere(
                  (item) => item['id'] == _selected!['id'],
                  orElse: () => rows.first,
                ));
      List<DocumentTimelineSnapshot> history = const [];
      if (selected != null) {
        final Map<String, dynamic> timeline = _unwrap(
          await widget.api.documentHistory('sales-orders', selected['id']),
        );
        history = ((timeline['data'] as List?) ?? const [])
            .whereType<Map>()
            .map((item) => DocumentTimelineSnapshot.fromJson(Map<String, dynamic>.from(item)))
            .toList(growable: false);
      }
      if (!mounted) return;
      setState(() {
        _summary = summary;
        _orders = rows;
        _total = total;
        _selected = selected;
        _history = history;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _act(String suffix) async {
    final Map<String, dynamic>? selected = _selected;
    if (selected == null) return;
    await widget.api.documentAction('sales-orders', selected['id'] as String, suffix);
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    final Map<String, dynamic>? selected = _selected;
    final DocumentHeaderSnapshot header = selected == null
        ? const DocumentHeaderSnapshot(documentTypeCode: 'SALES_ORDER', documentTypeName: 'Sales Order', documentNumber: '-', documentDate: '-', status: 'DRAFT')
        : DocumentHeaderSnapshot(
            documentTypeCode: 'SALES_ORDER',
            documentTypeName: 'Sales Order',
            documentNumber: '${selected['order_number'] ?? '-'}',
            documentDate: '${selected['order_date'] ?? '-'}',
            status: '${selected['status'] ?? 'DRAFT'}',
            reference: (selected['reference_number'] as String?) ?? '',
            remarks: (selected['remarks'] as String?) ?? '',
          );
    final DocumentTotalsSnapshot totals = DocumentTotalsSnapshot(
      subtotal: '${selected?['subtotal'] ?? '0'}',
      discount: '${selected?['line_discount_total'] ?? '0'}',
      tax: '${selected?['tax_total'] ?? '0'}',
      charges: '${selected?['additional_charges'] ?? '0'}',
      roundOff: '${selected?['round_off'] ?? '0'}',
      grandTotal: '${selected?['grand_total'] ?? '0'}',
    );
    final List<DocumentLineSnapshot> lines = selected == null
        ? const []
        : ((selected['lines'] as List?) ?? const []).whereType<Map>().map((row) {
            final Map<String, dynamic> item = Map<String, dynamic>.from(row);
            return DocumentLineSnapshot(
              lineNumber: (item['line_number'] as num?)?.toInt() ?? 0,
              product: '${item['product_id'] ?? ''}',
              description: (item['description'] as String?) ?? '',
              uom: '${item['sales_uom_id'] ?? ''}',
              packaging: '${item['packaging_type_id'] ?? ''}',
              quantity: '${item['quantity'] ?? '0'}',
              freeQuantity: '${item['free_quantity'] ?? '0'}',
              unitPrice: '${item['unit_price'] ?? '0'}',
              discount: '${item['discount_amount'] ?? '0'}',
              taxProfile: '${item['tax_profile_id'] ?? ''}',
              amount: '${item['gross_amount'] ?? '0'}',
              netAmount: '${item['net_amount'] ?? '0'}',
              remarks: 'Avail: ${item['available_stock'] ?? '0'} | Res: ${item['reserved_stock'] ?? '0'} ${item['remarks'] ?? ''}',
            );
          }).toList(growable: false);

    return EnterpriseWorkspace(
      title: 'Sales Orders',
      description: 'Manage customer sales orders and inventory reservations.',
      breadcrumbs: const ['Workspace', 'Sales Orders'],
      content: Column(
        children: [
          if (_loading) const LinearProgressIndicator(minHeight: 2),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 12),
            child: SummaryCards(children: [
              _card('Total', '${_summary['total'] ?? 0}'),
              _card('Draft', '${_summary['draft'] ?? 0}'),
              _card('Approved', '${_summary['approved'] ?? 0}'),
              _card('Cancelled', '${_summary['cancelled'] ?? 0}'),
              _card('Closed', '${_summary['closed'] ?? 0}'),
            ]),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Row(
                children: [
                  Expanded(
                    flex: 3,
                    child: Card(
                      child: Column(
                        children: [
                          Padding(
                            padding: const EdgeInsets.all(16),
                            child: TextField(
                              controller: _search,
                              decoration: const InputDecoration(labelText: 'Search sales orders', prefixIcon: Icon(Icons.search)),
                              onSubmitted: (_) => _load(),
                            ),
                          ),
                          Expanded(
                            child: ListView.separated(
                              itemCount: _orders.length,
                              separatorBuilder: (_, __) => const Divider(height: 1),
                              itemBuilder: (context, index) {
                                final Map<String, dynamic> row = _orders[index];
                                return ListTile(
                                  selected: _selected?['id'] == row['id'],
                                  title: Text('${row['order_number'] ?? '-'}'),
                                  subtitle: Text('${row['order_date'] ?? '-'} • ${row['status'] ?? ''}'),
                                  trailing: Text('${row['grand_total'] ?? '0'}'),
                                  onTap: () async {
                                    setState(() => _selected = row);
                                    await _load();
                                  },
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
                              DocumentToolbarAction.newDocument,
                              DocumentToolbarAction.printDocument,
                              DocumentToolbarAction.exportDocument,
                              DocumentToolbarAction.emailDocument,
                              DocumentToolbarAction.approve,
                              DocumentToolbarAction.cancel,
                              DocumentToolbarAction.close,
                            ],
                            isEnabled: (action) => selected != null && _mayRun(action),
                            onAction: (action) async {
                              if (selected == null) return;
                              try {
                                switch (action) {
                                  case DocumentToolbarAction.approve:
                                    await _act('/approve');
                                    break;
                                  case DocumentToolbarAction.cancel:
                                    await _act('/cancel');
                                    break;
                                  case DocumentToolbarAction.close:
                                    await _act('/close');
                                    break;
                                  default:
                                    NotificationService.show(context, 'Placeholder action for sales orders.', kind: AppNotificationKind.information);
                                }
                              } on ApiException catch (error) {
                                NotificationService.show(context, error.message, kind: AppNotificationKind.error);
                              }
                            },
                          ),
                          const SizedBox(height: 12),
                          EnterpriseDocumentHeader(header: header),
                          const SizedBox(height: 12),
                          EnterpriseDocumentLines(lines: lines),
                          const SizedBox(height: 12),
                          EnterpriseTotalsPanel(totals: totals),
                          const SizedBox(height: 12),
                          EnterpriseTimeline(entries: _history),
                          const SizedBox(height: 12),
                          EnterpriseApprovalPanel(status: header.status, message: 'Approval workflow placeholder.'),
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

  Widget _card(String label, String value) => Card(
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

  Map<String, dynamic> _unwrap(dynamic response) {
    if (response is! Map<String, dynamic>) return const <String, dynamic>{};
    final dynamic data = response['data'];
    return data is Map<String, dynamic> ? data : response;
  }
}
