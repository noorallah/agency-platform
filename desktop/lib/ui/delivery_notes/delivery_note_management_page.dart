import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/document_framework.dart';
import '../../models/entities.dart';
import '../document_framework/document_framework_widgets.dart';
import '../workspace/workspace_components.dart';

class DeliveryNoteManagementPage extends StatefulWidget {
  const DeliveryNoteManagementPage({
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
  State<DeliveryNoteManagementPage> createState() => _DeliveryNoteManagementPageState();
}

class _DeliveryNoteManagementPageState extends State<DeliveryNoteManagementPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  bool _loading = false;
  String? _error;
  int _page = 1;
  int _total = 0;
  Json _summary = const {};
  List<_DeliveryNoteRecord> _notes = const [];
  _DeliveryNoteRecord? _selected;
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
        widget.api.documentSummary('delivery-notes'),
        widget.api.documentPage(
          'delivery-notes',
          page: _page,
          pageSize: _rowsPerPage,
          search: _search.text.trim(),
          sortBy: 'delivery_date',
          descending: true,
          additionalQuery: _filtersForTab(),
        ),
      ]);
      final Json summary = _unwrap(responses[0]);
      final Json page = _unwrap(responses[1]);
      final List<_DeliveryNoteRecord> notes = _recordsFromResponse(page);
      _DeliveryNoteRecord? selected = _selected;
      if (selected != null) {
        final List<_DeliveryNoteRecord> matches = notes.where((item) => item.id == selected!.id).toList();
        selected = matches.isEmpty ? null : matches.first;
      }
      if (selected == null && notes.isNotEmpty) {
        selected = notes.first;
      }
      List<DocumentTimelineSnapshot> history = const [];
      if (selected != null) {
        try {
          final Json timeline = _unwrap(await widget.api.documentHistory('delivery-notes', selected.id));
          history = _timelineFromResponse(timeline);
        } on ApiException {
          history = const [];
        }
      }
      if (!mounted) return;
      setState(() {
        _summary = summary;
        _notes = notes;
        _total = page['pagination'] is Map ? (page['pagination']['total'] as num?)?.toInt() ?? notes.length : notes.length;
        _selected = selected;
        _history = history;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString();
        _notes = const [];
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

  @override
  Widget build(BuildContext context) {
    final _DeliveryNoteRecord? selected = _selected;
    final DocumentHeaderSnapshot header = selected?.toHeader() ??
        const DocumentHeaderSnapshot(
          documentTypeCode: 'DELIVERY_NOTE',
          documentTypeName: 'Delivery Note',
          documentNumber: '-',
          documentDate: '-',
          status: 'DRAFT',
        );
    final DocumentTotalsSnapshot totals = selected?.toTotals() ??
        const DocumentTotalsSnapshot(
          subtotal: '0',
          discount: '0',
          tax: '0',
          charges: '0',
          roundOff: '0',
          grandTotal: '0',
        );
    return ModuleWorkspaceFrame(
      title: 'Delivery Notes',
      description: 'Manage dispatches, reservation release, and inventory deduction.',
      breadcrumbs: const ['Workspace', 'Delivery Notes'],
      child: Column(
        children: [
          if (_loading) const LinearProgressIndicator(minHeight: 2),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 12),
            child: SummaryCards(
              children: [
                _summaryCard('Total', '${_summary['total'] ?? 0}'),
                _summaryCard('Draft', '${_summary['draft'] ?? 0}'),
                _summaryCard('Approved', '${_summary['approved'] ?? 0}'),
                _summaryCard('Dispatched', '${_summary['dispatched'] ?? 0}'),
                _summaryCard('Completed', '${_summary['completed'] ?? 0}'),
                _summaryCard('Cancelled', '${_summary['cancelled'] ?? 0}'),
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
                                labelText: 'Search delivery notes',
                                prefixIcon: Icon(Icons.search),
                              ),
                              onSubmitted: (_) => _load(requestedPage: 1),
                            ),
                          ),
                          Expanded(
                            child: ListView.separated(
                              itemCount: _notes.length,
                              separatorBuilder: (_, __) => const Divider(height: 1),
                              itemBuilder: (context, index) {
                                final _DeliveryNoteRecord row = _notes[index];
                                final bool selected = _selected?.id == row.id;
                                return ListTile(
                                  selected: selected,
                                  title: Text(row.deliveryNoteNumber),
                                  subtitle: Text('${row.salesOrderReference} • ${row.deliveryDate} • ${row.status}'),
                                  trailing: Text(row.grandTotal),
                                  onTap: () => _selectNote(row),
                                );
                              },
                            ),
                          ),
                          Padding(
                            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                            child: Align(
                              alignment: Alignment.centerRight,
                              child: Text('$_total notes'),
                            ),
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
                              DocumentToolbarAction.requestApproval,
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
                                  case DocumentToolbarAction.requestApproval:
                                    if (selected.status == 'APPROVED') {
                                      await _act('/dispatch');
                                    } else {
                                      await _act('/complete');
                                    }
                                    break;
                                  case DocumentToolbarAction.cancel:
                                    await _act('/cancel');
                                    break;
                                  case DocumentToolbarAction.close:
                                    await _act('/close');
                                    break;
                                  default:
                                    NotificationService.show(
                                      context,
                                      'Placeholder action for delivery notes.',
                                      kind: AppNotificationKind.information,
                                    );
                                }
                              } on ApiException catch (error) {
                                NotificationService.show(context, error.message, kind: AppNotificationKind.error);
                              }
                            },
                          ),
                          const SizedBox(height: 12),
                          EnterpriseDocumentHeader(header: header),
                          const SizedBox(height: 12),
                          EnterpriseDocumentLines(
                            lines: selected == null
                                ? const []
                                : [
                                    for (final _DeliveryNoteLine line in selected.lines)
                                      DocumentLineSnapshot(
                                        lineNumber: line.lineNumber,
                                        product: line.productId,
                                        description: line.description,
                                        uom: line.salesUomId,
                                        packaging: line.packagingTypeId,
                                        quantity: line.currentDeliveryQuantity,
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

  Future<void> _act(String suffix) async {
    final _DeliveryNoteRecord? selected = _selected;
    if (selected == null) return;
    await widget.api.documentAction('delivery-notes', selected.id, suffix);
    await _load();
  }

  Future<void> _selectNote(_DeliveryNoteRecord row) async {
    setState(() => _selected = row);
    try {
      final Json timeline = _unwrap(await widget.api.documentHistory('delivery-notes', row.id));
      if (!mounted) return;
      setState(() => _history = _timelineFromResponse(timeline));
    } on ApiException {
      if (!mounted) return;
      setState(() => _history = const []);
    }
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
        'pending-deliveries' => const {'status': 'APPROVED'},
        'partial-deliveries' => const {'status': 'DISPATCHED'},
        'delivery-history' => const {'status': 'COMPLETED'},
        _ => const {},
      };

  Json _unwrap(dynamic response) {
    if (response is! Json) return const {};
    final dynamic data = response['data'];
    return data is Json ? data : response;
  }

  List<_DeliveryNoteRecord> _recordsFromResponse(Json response) {
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => _DeliveryNoteRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false);
  }

  List<DocumentTimelineSnapshot> _timelineFromResponse(Json response) {
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => DocumentTimelineSnapshot.fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false);
  }
}

class _DeliveryNoteRecord {
  const _DeliveryNoteRecord({
    required this.id,
    required this.deliveryNoteNumber,
    required this.deliveryDate,
    required this.salesOrderReference,
    required this.status,
    required this.subtotal,
    required this.taxTotal,
    required this.additionalCharges,
    required this.roundOff,
    required this.grandTotal,
    required this.branchId,
    required this.warehouseId,
    required this.remarks,
    required this.lines,
  });

  final String id;
  final String deliveryNoteNumber;
  final String deliveryDate;
  final String salesOrderReference;
  final String status;
  final String subtotal;
  final String taxTotal;
  final String additionalCharges;
  final String roundOff;
  final String grandTotal;
  final String branchId;
  final String warehouseId;
  final String remarks;
  final List<_DeliveryNoteLine> lines;

  factory _DeliveryNoteRecord.fromJson(Json json) {
    final List<_DeliveryNoteLine> lines = (json['lines'] is List)
        ? (json['lines'] as List)
            .whereType<Map>()
            .map((item) => _DeliveryNoteLine.fromJson(Map<String, dynamic>.from(item)))
            .toList()
        : const [];
    return _DeliveryNoteRecord(
      id: stringValue(json['id']),
      deliveryNoteNumber: stringValue(json['delivery_note_number']),
      deliveryDate: stringValue(json['delivery_date']),
      salesOrderReference: stringValue(json['sales_order_reference']),
      status: stringValue(json['status']),
      subtotal: stringValue(json['subtotal']),
      taxTotal: stringValue(json['tax_total']),
      additionalCharges: stringValue(json['additional_charges']),
      roundOff: stringValue(json['round_off']),
      grandTotal: stringValue(json['grand_total']),
      branchId: stringValue(json['branch_id']),
      warehouseId: stringValue(json['warehouse_id']),
      remarks: stringValue(json['remarks']),
      lines: lines,
    );
  }

  DocumentHeaderSnapshot toHeader() => DocumentHeaderSnapshot(
        documentTypeCode: 'DELIVERY_NOTE',
        documentTypeName: 'Delivery Note',
        documentNumber: deliveryNoteNumber,
        documentDate: deliveryDate,
        reference: salesOrderReference,
        branch: branchId,
        warehouse: warehouseId,
        status: status,
        remarks: remarks,
      );

  DocumentTotalsSnapshot toTotals() => DocumentTotalsSnapshot(
        subtotal: subtotal,
        discount: '0',
        tax: taxTotal,
        charges: additionalCharges,
        roundOff: roundOff,
        grandTotal: grandTotal,
      );
}

class _DeliveryNoteLine {
  const _DeliveryNoteLine({
    required this.lineNumber,
    required this.productId,
    required this.description,
    required this.salesUomId,
    required this.packagingTypeId,
    required this.currentDeliveryQuantity,
    required this.freeQuantity,
    required this.unitPrice,
    required this.discountAmount,
    required this.taxProfileId,
    required this.grossAmount,
    required this.netAmount,
    required this.remarks,
  });

  final int lineNumber;
  final String productId;
  final String description;
  final String salesUomId;
  final String packagingTypeId;
  final String currentDeliveryQuantity;
  final String freeQuantity;
  final String unitPrice;
  final String discountAmount;
  final String taxProfileId;
  final String grossAmount;
  final String netAmount;
  final String remarks;

  factory _DeliveryNoteLine.fromJson(Json json) => _DeliveryNoteLine(
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: stringValue(json['product_id']),
        description: stringValue(json['description']),
        salesUomId: stringValue(json['sales_uom_id']),
        packagingTypeId: stringValue(json['packaging_type_id']),
        currentDeliveryQuantity: stringValue(json['current_delivery_quantity']),
        freeQuantity: stringValue(json['free_quantity']),
        unitPrice: stringValue(json['unit_price']),
        discountAmount: stringValue(json['discount_amount']),
        taxProfileId: stringValue(json['tax_profile_id']),
        grossAmount: stringValue(json['gross_amount']),
        netAmount: stringValue(json['net_amount']),
        remarks: stringValue(json['remarks']),
      );
}
