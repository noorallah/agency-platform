// Backlog 79 row 7: a batch carries its own MRP and selling price -- shown in
// the list, offered on the form, and sent only when typed.

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
      'product_id': 'p-1',
      'product_code': 'PRD-001',
      'product_name': 'Pain Relief',
      'batch_number': number,
      'expiry_date': '2026-12-31',
      'status': 'AVAILABLE',
      'quantity': '100',
      'available_quantity': '100',
      'mrp': '120.00',
      'selling_price': '95.50',
    });

class _BatchApi extends ApiClient {
  _BatchApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? created;

  @override
  Future<PagedResult<BatchRecord>> batches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BatchQuery filters = const BatchQuery(),
  }) async =>
      PagedResult<BatchRecord>(items: <BatchRecord>[_batch('B-001')], total: 1);

  @override
  Future<BatchRecord> createBatch(Json data) async {
    created = data;
    return _batch('B-900');
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
  Future<BatchSummaryRecord> batchSummary() async => const BatchSummaryRecord(
        totalBatches: 1,
        nearExpiry: 0,
        expired: 0,
        quarantine: 0,
      );

  @override
  Future<ExpiryDashboardRecord> expiryDashboard() async =>
      const ExpiryDashboardRecord(
        expiredToday: 0,
        expireIn7Days: 0,
        expireIn30Days: 0,
        totalExpired: 0,
        quarantine: 0,
        recalled: 0,
      );
}

Future<void> _open(WidgetTester tester, _BatchApi api) async {
  tester.view.physicalSize = const Size(1600, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory temp = Directory.systemTemp.createTempSync('batch-mrp');
  addTearDown(() => temp.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: BatchManagementPage(
        api: api,
        preferences: DesktopPreferencesService(directory: temp),
        permissions: PermissionService()
          ..applyAccessToken(
              accessTokenFor(const <String>['BATCH_VIEW', 'BATCH_CREATE'])),
        hasActiveFirm: true,
        section: BatchSerialSection.batches,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

/// A new batch names its product (D-UI-72).
Future<void> _pickProduct(WidgetTester tester) async {
  await tester.enterText(
      find.byKey(const ValueKey('batch-form-product')), 'Pain');
  await tester.pumpAndSettle();
  await tester.tap(find.text('PRD-001 · Pain Relief').last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the list shows each batch MRP', (tester) async {
    await _open(tester, _BatchApi());
    expect(find.text('MRP'), findsWidgets);
    expect(find.text('120.00'), findsOneWidget);
  });

  testWidgets('a typed MRP and selling price are sent', (tester) async {
    final _BatchApi api = _BatchApi();
    await _open(tester, api);
    await tester.tap(find.text('Add Batch').first);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Batch Number *'), 'B-900');
    await tester.enterText(find.byKey(const ValueKey('batch-form-mrp')), '120');
    await tester.enterText(
        find.byKey(const ValueKey('batch-form-selling-price')), '95.5');
    await _pickProduct(tester);
    await tester.tap(find.widgetWithText(FilledButton, 'Create'));
    await tester.pumpAndSettle();

    expect(api.created!['mrp'], '120');
    expect(api.created!['selling_price'], '95.5');
  });

  testWidgets('left blank, neither is sent', (tester) async {
    final _BatchApi api = _BatchApi();
    await _open(tester, api);
    await tester.tap(find.text('Add Batch').first);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Batch Number *'), 'B-901');
    await _pickProduct(tester);
    await tester.tap(find.widgetWithText(FilledButton, 'Create'));
    await tester.pumpAndSettle();

    expect(api.created!.containsKey('mrp'), isFalse);
    expect(api.created!.containsKey('selling_price'), isFalse);
  });
}
