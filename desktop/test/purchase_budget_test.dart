// Purchase budgets (BUY-14): the budgets screen lists a month's budgets and
// posts a new one; the buying stages dialog sends `budget_policy`; a saved
// order's editor shows each budget it counts against, flagged when exceeded.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/document_preview.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/purchases/purchase_budgets_dialog.dart';
import 'package:agency_desktop/ui/purchases/purchase_management_page.dart';
import 'package:agency_desktop/ui/purchases/purchase_workflow_settings_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

PermissionService _permissions(List<String> codes) {
  final String payload = base64Url
      .encode(utf8.encode(jsonEncode(<String, dynamic>{
        'roles': <String>['user'],
        'permissions': codes,
      })))
      .replaceAll('=', '');
  return PermissionService()..applyAccessToken('header.$payload.sig');
}

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<String> monthsAsked = <String>[];
  final List<Json> posted = <Json>[];
  final List<Json> savedSettings = <Json>[];

  @override
  Future<List<PurchaseBudget>> purchaseBudgets(String month) async {
    monthsAsked.add(month);
    return [
      PurchaseBudget.fromJson(<String, dynamic>{
        'id': 'b-1',
        'budget_month': month,
        'label': 'All purchases',
        'amount': '100000.00',
        'used': '40000.00',
        'available': '60000.00',
        'version': 1,
      }),
    ];
  }

  @override
  Future<PurchaseBudget> savePurchaseBudget(Json body, {String? id}) async {
    posted.add(body);
    return PurchaseBudget.fromJson(<String, dynamic>{
      'id': 'b-2',
      'budget_month': body['budget_month'],
      'label': 'x',
      'amount': body['amount'],
      'used': '0',
      'available': body['amount'],
    });
  }

  @override
  Future<PagedResult<BranchRecord>> branches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BranchQuery filters = const BranchQuery(),
  }) async =>
      const PagedResult<BranchRecord>(items: [], total: 0);

  @override
  Future<List<ProductCategoryRecord>> productCategories() async => const [];

  @override
  Future<PurchaseWorkflowSettings> purchaseWorkflowSettings() async =>
      PurchaseWorkflowSettings.fromJson(<String, dynamic>{
        'purchase_order_stage': true,
        'goods_receipt_stage': true,
        'is_configured': true,
      });

  @override
  Future<PurchaseWorkflowSettings> updatePurchaseWorkflowSettings(
    PurchaseWorkflowSettings settings,
  ) async {
    savedSettings.add(settings.toJson());
    return settings;
  }

  @override
  Future<PurchaseOrderPreviewRecord> previewPurchaseOrder(
    PurchaseOrder order,
  ) async =>
      PurchaseOrderPreviewRecord(
        order: order,
        interstate: false,
        lines: const <DocumentPreviewLine>[],
      );

  @override
  Future<List<PurchaseOrderHistoryRecord>> purchaseOrderHistory(
    String id,
  ) async =>
      const <PurchaseOrderHistoryRecord>[];

  @override
  Future<List<PurchaseOrderBudgetRow>> purchaseOrderBudget(
    String orderId,
  ) async =>
      [
        PurchaseOrderBudgetRow.fromJson(<String, dynamic>{
          'budget_id': 'b-1',
          'label': 'All purchases',
          'amount': '100000.00',
          'used': '90000.00',
          'this_order': '20000.00',
          'available': '-10000.00',
          'exceeded': true,
        }),
        PurchaseOrderBudgetRow.fromJson(<String, dynamic>{
          'budget_id': 'b-2',
          'label': 'Main Branch',
          'amount': '50000.00',
          'used': '1000.00',
          'this_order': '500.00',
          'available': '48500.00',
          'exceeded': false,
        }),
      ];
}

void main() {
  testWidgets('the budgets screen lists the month and adds a budget',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: PurchaseBudgetsDialog(
          api: api,
          permissions:
              _permissions(['PURCHASE_VIEW', 'PURCHASE_MANAGE_SETTINGS']),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    final DateTime now = DateTime.now();
    final String thisMonth =
        '${now.year}-${now.month.toString().padLeft(2, '0')}-01';
    expect(api.monthsAsked.first, thisMonth);
    expect(find.text('All purchases'), findsOneWidget);
    expect(find.text('Available'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('budget-add')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('budget-form-amount')), '75000');
    await tester.tap(find.byKey(const ValueKey('budget-form-save')));
    await tester.pumpAndSettle();

    expect(api.posted.single, <String, dynamic>{
      'budget_month': thisMonth,
      'branch_id': null,
      'product_category_id': null,
      'amount': '75000',
    });
    expect(tester.takeException(), isNull);
  });

  testWidgets('without the settings permission a budget cannot be added',
      (tester) async {
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: PurchaseBudgetsDialog(
          api: api,
          permissions: _permissions(['PURCHASE_VIEW']),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(
      tester
          .widget<OutlinedButton>(find.byKey(const ValueKey('budget-add')))
          .onPressed,
      isNull,
    );
  });

  testWidgets('the settings dialog sends the budget policy', (tester) async {
    tester.view.physicalSize = const Size(1366, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: PurchaseWorkflowSettingsDialog(
          api: api,
          permissions:
              _permissions(['PURCHASE_VIEW', 'PURCHASE_MANAGE_SETTINGS']),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    final Finder choice = find.byKey(const ValueKey('budget-policy'));
    await tester.ensureVisible(choice);
    await tester.tap(choice);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Needs approval').last);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    expect(api.savedSettings.single['budget_policy'], 'NEEDS_APPROVAL');
  });

  testWidgets('an order editor shows an exceeded budget row', (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: PurchaseOrderEditorDialog(
            api: api,
            permissions: PermissionService(),
            mode: PurchaseDialogMode.view,
            order: PurchaseOrder.fromJson(<String, dynamic>{
              'id': 'po-1',
              'firm_id': 'firm-1',
              'branch_id': 'branch-1',
              'warehouse_id': 'warehouse-1',
              'vendor_id': 'vendor-1',
              'po_number': 'PO-0001',
              'purchase_date': '2026-10-01',
              'status': 'SUBMITTED',
              'grand_total': '20000.00',
              'lines': [
                {
                  'id': 'line-1',
                  'line_number': 1,
                  'product_id': 'product-1',
                  'ordered_quantity': '5',
                  'free_quantity': '0',
                  'unit_price': '100',
                  'discount_percent': '0',
                  'net_amount': '500.00',
                },
              ],
            }),
            vendors: const <Vendor>[],
            branches: const <BranchRecord>[],
            warehouses: const <WarehouseRecord>[],
            products: const <Product>[],
            buyers: const [],
            taxProfiles: const [],
            storageNodes: const [],
            canSubmit: false,
            canApprove: false,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();

    expect(find.text('BUDGET'), findsOneWidget);
    final Finder over = find.textContaining('All purchases: used');
    expect(over, findsOneWidget);
    expect(tester.widget<Text>(over).data, contains('(over budget)'));
    expect(find.textContaining('Main Branch: used'), findsOneWidget);
    expect(
      tester.widget<Text>(find.textContaining('Main Branch: used')).data,
      isNot(contains('over budget')),
    );
  });
}
