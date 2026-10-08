import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../workspace/analysis_page.dart';
import '../workspace/export_file.dart';

/// Purchases pivoted by one or two dimensions, billed, received or ordered,
/// with drill-down on the billed basis. The pivot is the shared
/// [AnalysisPage]; this only says what a purchase is called.
class PurchaseAnalysisPage extends StatelessWidget {
  const PurchaseAnalysisPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    this.today,
    this.saveExportOverride,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// Overridable so a test is not at the mercy of the calendar.
  final DateTime? today;

  /// Where an export goes in a test, which cannot open a save dialog.
  final SaveExportOverride? saveExportOverride;

  /// What a filter picker offers for a typed search.
  Future<List<AnalysisOption>> _options(String parameter, String search) async {
    switch (parameter) {
      case 'product_id':
        return [
          for (final p in (await api.products(search: search, pageSize: 50))
              .items)
            AnalysisOption(id: p.id, label: p.name),
        ];
      case 'category_id':
        return [
          for (final c in (await api.productCategoryPage(search: search)).items)
            AnalysisOption(id: c.id, label: c.name),
        ];
      case 'goods_type_id':
        // The firm's goods types are a short list read whole; a product
        // with none is General, which no id names.
        return [
          for (final t in await api.goodsTypes())
            if (t.inUse && t.name.toLowerCase().contains(search.toLowerCase()))
              AnalysisOption(id: t.id, label: t.name),
        ];
      case 'supplier_id':
        return [
          for (final v in (await api.vendors(search: search)).items)
            AnalysisOption(id: v.id, label: v.name),
        ];
      case 'supplier_category_id':
        return [
          for (final c in (await api.vendorCategories(search: search)).items)
            AnalysisOption(id: c.id, label: c.name),
        ];
      case 'branch_id':
        return [
          for (final b in (await api.branches(search: search, pageSize: 50))
              .items)
            AnalysisOption(id: b.id, label: b.name),
        ];
    }
    return const [];
  }

  @override
  Widget build(BuildContext context) => AnalysisPage(
        permissions: permissions,
        hasActiveFirm: hasActiveFirm,
        today: today,
        saveExportOverride: saveExportOverride,
        config: AnalysisConfig(
          title: 'Purchase analysis',
          noun: 'bill',
          nounPlural: 'bills',
          netLabel: 'Total billed',
          countLabel: 'Bills',
          averageLabel: 'Average bill',
          emptyTitle: 'Nothing bought in this period',
          permissionCodes: const ['PURCHASE_VIEW', 'REPORT_VIEW'],
          defaultRows: 'supplier',
          dimensions: const {
            'day': 'Day',
            'week': 'Week',
            'month': 'Month',
            'quarter': 'Quarter',
            'year': 'Year',
            'product': 'Product',
            'category': 'Category',
            'goods_type': 'Goods type',
            'supplier': 'Supplier',
            'supplier_category': 'Supplier category',
            'branch': 'Branch',
          },
          filterParameters: const {
            'product': 'product_id',
            'category': 'category_id',
            'goods_type': 'goods_type_id',
            'supplier': 'supplier_id',
            'supplier_category': 'supplier_category_id',
            'branch': 'branch_id',
          },
          fetch: api.purchaseAnalysis,
          advanced: AnalysisAdvanced(
            reportCode: 'purchase_analysis',
            bases: const {
              'billed': 'Billed',
              'received': 'Received',
              'ordered': 'Ordered',
            },
            averageRateColumn: true,
            fetch: ({
              required String rows,
              String? columns,
              required String fromDate,
              required String toDate,
              required bool netOfReturns,
              required Map<String, String> filters,
              required String basis,
              required bool comparePreviousYear,
            }) =>
                api.purchaseAnalysis(
              rows: rows,
              columns: columns,
              fromDate: fromDate,
              toDate: toDate,
              netOfReturns: netOfReturns,
              filters: filters,
              basis: basis,
              comparePreviousYear: comparePreviousYear,
            ),
            pickers: const {
              'product_id': 'Product',
              'category_id': 'Category',
              'goods_type_id': 'Goods type',
              'supplier_id': 'Supplier',
              'supplier_category_id': 'Supplier category',
              'branch_id': 'Branch',
            },
            options: _options,
            listLayouts: () => api.reportLayouts('purchase_analysis'),
            saveLayout: (name, settings) async {
              await api.saveReportLayout(
                reportCode: 'purchase_analysis',
                name: name,
                settings: settings,
              );
            },
            deleteLayout: api.deleteReportLayout,
          ),
          fetchDocuments: ({
            required String fromDate,
            required String toDate,
            required Map<String, String> filters,
          }) async =>
              [
            for (final bill in await api.purchaseAnalysisBills(
              fromDate: fromDate,
              toDate: toDate,
              filters: filters,
            ))
              AnalysisDocument(
                id: bill.id,
                number: bill.invoiceNumber,
                date: bill.invoiceDate,
                net: bill.net,
              ),
          ],
        ),
      );
}
