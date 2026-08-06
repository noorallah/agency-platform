import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/document_framework.dart';
import '../document_framework/document_framework_widgets.dart';
import '../workspace/workspace_components.dart';
import '../workspace/workspace_templates.dart';

class PurchaseInvoiceManagementPage extends StatefulWidget {
  const PurchaseInvoiceManagementPage({
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
  State<PurchaseInvoiceManagementPage> createState() =>
      _PurchaseInvoiceManagementPageState();
}

class _PurchaseInvoiceManagementPageState extends State<PurchaseInvoiceManagementPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  bool _loading = false;
  String? _error;
  int _page = 1;
  int _total = 0;
  Map<String, dynamic> _summary = const {};
  List<_PurchaseInvoiceRecord> _invoices = const [];
  _PurchaseInvoiceRecord? _selected;
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
      final List<dynamic> responses = await Future.wait<dynamic>([
        widget.api.request('GET', '/api/v1/purchase-invoices/summary'),
        widget.api.request(
          'GET',
          '/api/v1/purchase-invoices',
          query: {
            'page': '$_page',
            'page_size': '$_rowsPerPage',
            'search': _search.text.trim(),
            'sort_by': 'invoice_date',
            'sort_direction': 'desc',
          },
        ),
      ]);
      final Map<String, dynamic> summary = _unwrap(responses[0]);
      final Map<String, dynamic> page = _unwrap(responses[1]);
      final List<_PurchaseInvoiceRecord> invoices = _recordsFromResponse(page);
      _PurchaseInvoiceRecord? selected = _selected;
      if (selected != null) {
        final String selectedId = selected.id;
        final List<_PurchaseInvoiceRecord> matches =
            invoices.where((item) => item.id == selectedId).toList();
        selected = matches.isEmpty ? null : matches.first;
      }
      if (selected == null && invoices.isNotEmpty) {
        selected = invoices.first;
      }
      List<DocumentTimelineSnapshot> history = const [];
      if (selected != null) {
        try {
          final Map<String, dynamic> timeline = _unwrap(await widget.api.request(
            'GET',
            '/api/v1/purchase-invoices/${selected.id}/history',
          ));
          history = _timelineFromResponse(timeline);
        } on ApiException {
          history = const [];
        }
      }
      if (!mounted) {
        return;
      }
      setState(() {
        _summary = summary;
        _invoices = invoices;
        _total = page['pagination'] is Map
            ? (page['pagination']['total'] as num?)?.toInt() ?? invoices.length
            : invoices.length;
        _selected = selected;
        _history = history;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = error.toString();
        _invoices = const [];
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
    final _PurchaseInvoiceRecord? selected = _selected;
    final DocumentHeaderSnapshot header = selected?.toHeader() ??
        const DocumentHeaderSnapshot(
          documentTypeCode: 'PURCHASE_INVOICE',
          documentTypeName: 'Purchase Invoice',
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
    return EnterpriseWorkspace(
      title: 'Purchase Invoices',
      description: 'Manage supplier invoices, GRN matching, and accounting events.',
      breadcrumbs: const ['Workspace', 'Purchase Invoices'],
      content: Column(
        children: [
          if (_loading) const LinearProgressIndicator(minHeight: 2),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 12),
            child: SummaryCards(
              children: [
                _summaryCard('Total', '${_summary['total'] ?? 0}'),
                _summaryCard('Draft', '${_summary['draft'] ?? 0}'),
                _summaryCard('Approved', '${_summary['approved'] ?? 0}'),
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
                                labelText: 'Search invoices',
                                prefixIcon: Icon(Icons.search),
                              ),
                              onSubmitted: (_) => _load(requestedPage: 1),
                            ),
                          ),
                          Expanded(
                            child: ListView.separated(
                              itemCount: _invoices.length,
                              separatorBuilder: (_, __) => const Divider(height: 1),
                              itemBuilder: (context, index) {
                                final _PurchaseInvoiceRecord row = _invoices[index];
                                final bool selected = _selected?.id == row.id;
                                return ListTile(
                                  selected: selected,
                                  title: Text(row.invoiceNumber),
                                  subtitle: Text(
                                    '${row.supplierInvoiceNumber} • ${row.invoiceDate} • ${row.status}',
                                  ),
                                  trailing: Text(row.grandTotal),
                                  onTap: () => _selectInvoice(row),
                                );
                              },
                            ),
                          ),
                          Padding(
                            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                            child: Align(
                              alignment: Alignment.centerRight,
                              child: Text('$_total invoices'),
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
                              DocumentToolbarAction.reject,
                              DocumentToolbarAction.cancel,
                              DocumentToolbarAction.close,
                            ],
                            isEnabled: (action) => selected != null,
                            onAction: (action) async {
                              if (selected == null) {
                                return;
                              }
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
                                  NotificationService.show(
                                    context,
                                    'Placeholder action for purchase invoices.',
                                  kind: AppNotificationKind.information,
                                  );
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
                                    for (final _PurchaseInvoiceLine line in selected.lines)
                                      DocumentLineSnapshot(
                                        lineNumber: line.lineNumber,
                                        product: line.productId,
                                        description: line.description,
                                        uom: line.invoiceUomId,
                                        packaging: line.packagingTypeId,
                                        quantity: line.currentInvoiceQuantity,
                                        freeQuantity: '0',
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
              child: Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
        ],
      ),
    );
  }

  Future<void> _act(String suffix) async {
    final _PurchaseInvoiceRecord? selected = _selected;
    if (selected == null) {
      return;
    }
    try {
      await widget.api.request('POST', '/api/v1/purchase-invoices/${selected.id}$suffix');
      await _load();
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _selectInvoice(_PurchaseInvoiceRecord row) async {
    setState(() => _selected = row);
    try {
      final Map<String, dynamic> timeline = _unwrap(await widget.api.request(
        'GET',
        '/api/v1/purchase-invoices/${row.id}/history',
      ));
      if (!mounted) {
        return;
      }
      setState(() => _history = _timelineFromResponse(timeline));
    } on ApiException {
      if (!mounted) {
        return;
      }
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

  Map<String, dynamic> _unwrap(dynamic response) {
    if (response is Map<String, dynamic>) {
      final dynamic data = response['data'];
      if (data is Map<String, dynamic>) {
        return data;
      }
      return response;
    }
    return const <String, dynamic>{};
  }

  List<_PurchaseInvoiceRecord> _recordsFromResponse(Map<String, dynamic> response) {
    final dynamic data = response['data'];
    if (data is! List) {
      return const [];
    }
    return data
        .whereType<Map>()
        .map((item) => _PurchaseInvoiceRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  List<DocumentTimelineSnapshot> _timelineFromResponse(Map<String, dynamic> response) {
    final dynamic data = response['data'];
    if (data is! List) {
      return const [];
    }
    return data
        .whereType<Map>()
        .map((item) => DocumentTimelineSnapshot.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }
}

class _PurchaseInvoiceRecord {
  const _PurchaseInvoiceRecord({
    required this.id,
    required this.invoiceNumber,
    required this.invoiceDate,
    required this.supplierInvoiceNumber,
    required this.status,
    required this.subtotal,
    required this.taxTotal,
    required this.additionalCharges,
    required this.roundOff,
    required this.grandTotal,
    required this.businessProfileId,
    required this.branchId,
    required this.vendorId,
    required this.currencyCode,
    required this.exchangeRate,
    required this.paymentTerms,
    required this.remarks,
    required this.lines,
    required this.sources,
  });

  final String id;
  final String invoiceNumber;
  final String invoiceDate;
  final String supplierInvoiceNumber;
  final String status;
  final String subtotal;
  final String taxTotal;
  final String additionalCharges;
  final String roundOff;
  final String grandTotal;
  final String businessProfileId;
  final String branchId;
  final String vendorId;
  final String currencyCode;
  final String exchangeRate;
  final String paymentTerms;
  final String remarks;
  final List<_PurchaseInvoiceLine> lines;
  final List<Json> sources;

  factory _PurchaseInvoiceRecord.fromJson(Map<String, dynamic> json) {
    final List<_PurchaseInvoiceLine> lines = (json['lines'] is List)
        ? (json['lines'] as List)
            .whereType<Map>()
            .map((item) => _PurchaseInvoiceLine.fromJson(Map<String, dynamic>.from(item)))
            .toList()
        : const [];
    return _PurchaseInvoiceRecord(
      id: stringValue(json['id']),
      invoiceNumber: stringValue(json['invoice_number']),
      invoiceDate: stringValue(json['invoice_date']),
      supplierInvoiceNumber: stringValue(json['supplier_invoice_number']),
      status: stringValue(json['status']),
      subtotal: stringValue(json['subtotal']),
      taxTotal: stringValue(json['tax_total']),
      additionalCharges: stringValue(json['additional_charges']),
      roundOff: stringValue(json['round_off']),
      grandTotal: stringValue(json['grand_total']),
      businessProfileId: stringValue(json['business_profile_id']),
      branchId: stringValue(json['branch_id']),
      vendorId: stringValue(json['vendor_id']),
      currencyCode: stringValue(json['currency_code']),
      exchangeRate: stringValue(json['exchange_rate']),
      paymentTerms: stringValue(json['payment_terms']),
      remarks: stringValue(json['remarks']),
      lines: lines,
      sources: (json['sources'] is List)
          ? (json['sources'] as List).whereType<Map>().map((item) => Map<String, dynamic>.from(item)).toList()
          : const [],
    );
  }

  DocumentHeaderSnapshot toHeader() => DocumentHeaderSnapshot(
        documentTypeCode: 'PURCHASE_INVOICE',
        documentTypeName: 'Purchase Invoice',
        documentNumber: invoiceNumber,
        documentDate: invoiceDate,
        reference: supplierInvoiceNumber,
        branch: branchId,
        firm: '',
        businessProfile: businessProfileId,
        currency: currencyCode,
        exchangeRate: exchangeRate,
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

class _PurchaseInvoiceLine {
  const _PurchaseInvoiceLine({
    required this.lineNumber,
    required this.productId,
    required this.description,
    required this.invoiceUomId,
    required this.packagingTypeId,
    required this.currentInvoiceQuantity,
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
  final String invoiceUomId;
  final String packagingTypeId;
  final String currentInvoiceQuantity;
  final String unitPrice;
  final String discountAmount;
  final String taxProfileId;
  final String grossAmount;
  final String netAmount;
  final String remarks;

  factory _PurchaseInvoiceLine.fromJson(Map<String, dynamic> json) => _PurchaseInvoiceLine(
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: stringValue(json['product_id']),
        description: stringValue(json['description']),
        invoiceUomId: stringValue(json['invoice_uom_id']),
        packagingTypeId: stringValue(json['packaging_type_id']),
        currentInvoiceQuantity: stringValue(json['current_invoice_quantity']),
        unitPrice: stringValue(json['unit_price']),
        discountAmount: stringValue(json['discount_amount']),
        taxProfileId: stringValue(json['tax_profile_id']),
        grossAmount: stringValue(json['gross_amount']),
        netAmount: stringValue(json['net_amount']),
        remarks: stringValue(json['remarks']),
      );
}
