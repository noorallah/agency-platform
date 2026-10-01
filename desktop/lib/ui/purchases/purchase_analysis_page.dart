import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../workspace/analysis_page.dart';

/// Billed purchases pivoted by one or two dimensions, with drill-down. The
/// pivot is the shared [AnalysisPage]; this only says what a purchase is
/// called.
class PurchaseAnalysisPage extends StatelessWidget {
  const PurchaseAnalysisPage({
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
            'supplier': 'Supplier',
            'supplier_category': 'Supplier category',
            'branch': 'Branch',
          },
          filterParameters: const {
            'product': 'product_id',
            'category': 'category_id',
            'supplier': 'supplier_id',
            'supplier_category': 'supplier_category_id',
            'branch': 'branch_id',
          },
          fetch: api.purchaseAnalysis,
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
