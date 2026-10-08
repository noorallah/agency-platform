// A refused batch save is shown inside the dialog (D-DLG-6).
//
// It was a SnackBar, which draws on the Scaffold behind the dialog's barrier,
// so the person pressed Save, nothing happened, and what was typed stayed
// with no reason given.

import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/inventory/batch_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/access_token.dart';

BatchRecord _batch(String number) => BatchRecord.fromJson(<String, dynamic>{
      'id': 'batch-$number',
      'firm_id': 'firm-1',
      'product_id': 'p-1',
      'product_code': 'PRD-001',
      'product_name': 'Pain Relief',
      'warehouse_id': 'w-1',
      'warehouse_code': 'WH1',
      'warehouse_name': 'Main Store',
      'branch_id': 'b-1',
      'branch_code': 'HO',
      'branch_name': 'Head Office',
      'batch_number': number,
      'expiry_date': '2026-12-31',
      'status': 'ACTIVE',
      'quantity': '100',
      'available_quantity': '100',
    });

class _BatchApi extends ApiClient {
  _BatchApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  @override
  Future<PagedResult<BatchRecord>> batches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BatchQuery filters = const BatchQuery(),
  }) async =>
      PagedResult<BatchRecord>(
        items: <BatchRecord>[_batch('B-001'), _batch('B-002')],
        total: 2,
      );

  /// What Create sent, each time it was pressed with a product chosen.
  final List<Json> created = <Json>[];

  @override
  Future<BatchRecord> createBatch(Json data) async {
    created.add(data);
    throw const ApiException(
      'Batch number already exists for this product.',
      statusCode: 422,
    );
  }

  @override
  Future<PagedResult<Product>> products({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    ProductQuery filters = const ProductQuery(),
  }) async =>
      PagedResult<Product>(
        items: <Product>[
          Product.fromJson(<String, dynamic>{
            'id': 'p-1',
            'code': 'PRD-001',
            'name': 'Pain Relief',
          }),
        ],
        total: 1,
      );

  @override
  Future<BatchSummaryRecord> batchSummary() async =>
      const BatchSummaryRecord(
        totalBatches: 2,
        nearExpiry: 1,
        expired: 0,
        quarantine: 0,
      );

  @override
  Future<ExpiryDashboardRecord> expiryDashboard() async =>
      const ExpiryDashboardRecord(
        expiredToday: 0,
        expireIn7Days: 1,
        expireIn30Days: 2,
        totalExpired: 0,
        quarantine: 0,
        recalled: 0,
      );
}

void main() {
  testWidgets('a refused batch stays open, says why, and keeps the typing',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final Directory temp = Directory.systemTemp.createTempSync('batch-form');
    addTearDown(() => temp.deleteSync(recursive: true));
    final _BatchApi api = _BatchApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: BatchManagementPage(
          api: api,
          preferences: DesktopPreferencesService(directory: temp),
          permissions: PermissionService()
            ..applyAccessToken(accessTokenFor(
                const <String>['BATCH_VIEW', 'BATCH_CREATE'])),
          hasActiveFirm: true,
          section: BatchSerialSection.batches,
        ),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Add Batch').first);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Batch Number *'), 'B-900');

    // D-UI-72: the dialog had no product box, so every batch added from the
    // screen was refused "product_id: Field required". With none chosen the
    // dialog says so itself and sends nothing.
    await tester.tap(find.widgetWithText(FilledButton, 'Create'));
    await tester.pumpAndSettle();
    expect(find.text('Choose the product this batch is of.'), findsOneWidget);
    expect(api.created, isEmpty);

    await tester.enterText(
        find.byKey(const ValueKey('batch-form-product')), 'Pain');
    await tester.pumpAndSettle();
    await tester.tap(find.text('PRD-001 · Pain Relief').last);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Create'));
    await tester.pumpAndSettle();
    expect(api.created.single['product_id'], 'p-1');

    expect(
      find.descendant(
        of: find.byType(AlertDialog),
        matching: find.text('Batch number already exists for this product.'),
      ),
      findsOneWidget,
      reason: 'the refusal has to be on the dialog, not behind its barrier',
    );
    expect(find.text('B-900'), findsOneWidget, reason: 'what was typed stays');
  });
}
