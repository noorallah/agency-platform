import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../workspace/analysis_page.dart';
import '../workspace/export_file.dart';

/// Billed sales pivoted by one or two dimensions, with drill-down. The pivot
/// is the shared [AnalysisPage]; this only says what a sale is called.
class SalesAnalysisPage extends StatelessWidget {
  const SalesAnalysisPage({
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
      case 'brand_id':
        return [
          for (final b in (await api.brandsPage(search: search)).items)
            AnalysisOption(id: b.id, label: b.name),
        ];
      case 'principal_id':
        return [
          for (final p in (await api.principalsPage(search: search)).items)
            AnalysisOption(id: p.id, label: p.name),
        ];
      case 'customer_id':
        return [
          for (final c in (await api.customers(search: search, pageSize: 50))
              .items)
            AnalysisOption(id: c.id, label: c.name),
        ];
      case 'customer_group_id':
        return [
          for (final g in (await api.customerGroups(search: search)).items)
            AnalysisOption(id: g.id, label: g.name),
        ];
      case 'salesman_id':
        final String needle = search.toLowerCase();
        return [
          for (final m in await api.firmMembers())
            if (needle.isEmpty || m.label.toLowerCase().contains(needle))
              AnalysisOption(id: m.userId, label: m.label),
        ];
      case 'territory_id':
        return [
          for (final t in await api.searchTerritories(search))
            AnalysisOption(id: t.id, label: t.name),
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
          title: 'Sales analysis',
          noun: 'invoice',
          nounPlural: 'invoices',
          netLabel: 'Net sales',
          countLabel: 'Invoices',
          averageLabel: 'Average bill',
          emptyTitle: 'Nothing sold in this period',
          permissionCodes: const ['SALES_VIEW', 'REPORT_VIEW'],
          defaultRows: 'customer',
          dimensions: const {
            'day': 'Day',
            'week': 'Week',
            'month': 'Month',
            'quarter': 'Quarter',
            'year': 'Year',
            'product': 'Product',
            'category': 'Category',
            'goods_type': 'Goods type',
            'brand': 'Brand',
            'principal': 'Principal',
            'customer': 'Customer',
            'customer_group': 'Customer group',
            'salesman': 'Salesman',
            'territory': 'Territory',
            'route': 'Route',
            'branch': 'Branch',
          },
          filterParameters: const {
            'product': 'product_id',
            'category': 'category_id',
            'goods_type': 'goods_type_id',
            'brand': 'brand_id',
            'principal': 'principal_id',
            'customer': 'customer_id',
            'customer_group': 'customer_group_id',
            'salesman': 'salesman_id',
            'territory': 'territory_id',
            'route': 'route_id',
            'branch': 'branch_id',
          },
          fetch: api.salesAnalysis,
          advanced: AnalysisAdvanced(
            reportCode: 'sales_analysis',
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
                api.salesAnalysis(
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
              'brand_id': 'Brand',
              'principal_id': 'Principal',
              'customer_id': 'Customer',
              'customer_group_id': 'Customer group',
              'salesman_id': 'Salesman',
              'territory_id': 'Territory',
              'branch_id': 'Branch',
            },
            options: _options,
            listLayouts: () => api.reportLayouts('sales_analysis'),
            saveLayout: (name, settings) async {
              await api.saveReportLayout(
                reportCode: 'sales_analysis',
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
            for (final invoice in await api.salesAnalysisInvoices(
              fromDate: fromDate,
              toDate: toDate,
              filters: filters,
            ))
              AnalysisDocument(
                id: invoice.id,
                number: invoice.invoiceNumber,
                date: invoice.invoiceDate,
                net: invoice.net,
              ),
          ],
        ),
      );
}
