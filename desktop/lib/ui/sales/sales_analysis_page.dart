import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../workspace/analysis_page.dart';

/// Billed sales pivoted by one or two dimensions, with drill-down. The pivot
/// is the shared [AnalysisPage]; this only says what a sale is called.
class SalesAnalysisPage extends StatelessWidget {
  const SalesAnalysisPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    this.today,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// Overridable so a test is not at the mercy of the calendar.
  final DateTime? today;

  @override
  Widget build(BuildContext context) => AnalysisPage(
        permissions: permissions,
        hasActiveFirm: hasActiveFirm,
        today: today,
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
            'customer': 'customer_id',
            'customer_group': 'customer_group_id',
            'salesman': 'salesman_id',
            'territory': 'territory_id',
            'route': 'route_id',
            'branch': 'branch_id',
          },
          fetch: api.salesAnalysis,
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
