// Row L3 step 5: the lot's page shows its two prices and the margins they
// were worked at, with any MRP warning; a holder of BATCH_UPDATE in a firm
// costing by lot may change the prices without the BATCH_PTR_PTS feature.

import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/stock_costing.dart';
import 'package:agency_desktop/ui/inventory/batch_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/access_token.dart';

BatchRecord _batch() => BatchRecord.fromJson(<String, dynamic>{
      'id': 'batch-1',
      'version': 3,
      'product_id': 'p-1',
      'product_code': 'PRD-001',
      'product_name': 'Pain Relief',
      'batch_number': 'LOT-7',
      'status': 'AVAILABLE',
      'quantity': '100',
      'available_quantity': '100',
      'mrp': '130.00',
      'ptr': '125.00',
      'pts': '110.00',
      'retail_margin_percent': '25.0000',
      'wholesale_margin_percent': '10.0000',
      'mrp_warning': 'The retail price 125.00 with GST is above the MRP 130.00.',
    });

class _LotApi extends ApiClient {
  _LotApi({required this.byLot, this.features = const <String>[]})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool byLot;
  final List<String> features;
  Json? updated;

  @override
  Future<List<String>> activeBusinessFeatureCodes() async => features;

  @override
  Future<LotSettings> lotSettings() async =>
      LotSettings(costingMethod: byLot ? 'BY_LOT' : 'AVERAGE');

  @override
  Future<PagedResult<BatchRecord>> batches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BatchQuery filters = const BatchQuery(),
  }) async =>
      PagedResult<BatchRecord>(items: <BatchRecord>[_batch()], total: 1);

  @override
  Future<BatchRecord> updateBatch(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    updated = data;
    return _batch();
  }

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

Future<void> _open(
  WidgetTester tester,
  _LotApi api, {
  List<String> codes = const <String>['BATCH_VIEW', 'BATCH_UPDATE'],
}) async {
  tester.view.physicalSize = const Size(1600, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory temp = Directory.systemTemp.createTempSync('batch-lot');
  addTearDown(() => temp.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: BatchManagementPage(
        api: api,
        preferences: DesktopPreferencesService(directory: temp),
        permissions: PermissionService()
          ..applyAccessToken(accessTokenFor(codes)),
        hasActiveFirm: true,
        section: BatchSerialSection.batches,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

/// Double-click the lot's row to open its details.
Future<void> _openDetails(WidgetTester tester) async {
  await tester.tap(find.text('LOT-7'));
  await tester.pump(const Duration(milliseconds: 50));
  await tester.tap(find.text('LOT-7'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('by lot: the list and details show both prices and margins',
      (tester) async {
    await _open(tester, _LotApi(byLot: true));
    // No BATCH_PTR_PTS, so the plain words.
    expect(find.text('Retail price'), findsOneWidget);
    expect(find.text('Wholesale price'), findsOneWidget);
    expect(find.text('125.00'), findsOneWidget);

    await _openDetails(tester);
    expect(find.text('Retail margin %'), findsOneWidget);
    expect(find.text('25.0000'), findsOneWidget);
    expect(find.text('Wholesale margin %'), findsOneWidget);
    expect(find.textContaining('above the MRP 130.00'), findsOneWidget);
  });

  testWidgets('by lot: BATCH_UPDATE edits the prices without the feature',
      (tester) async {
    final _LotApi api = _LotApi(byLot: true);
    await _open(tester, api);
    await _openDetails(tester);
    await tester.tap(find.widgetWithText(TextButton, 'Edit'));
    await tester.pumpAndSettle();

    expect(find.widgetWithText(TextFormField, 'Retail price'), findsOneWidget);
    await tester.enterText(
        find.byKey(const ValueKey('batch-form-ptr')), '120');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.updated!['ptr'], '120');
    expect(api.updated!['pts'], '110.00');
  });

  testWidgets('with BATCH_PTR_PTS the details say PTR and PTS',
      (tester) async {
    await _open(
      tester,
      _LotApi(byLot: true, features: const <String>['BATCH_PTR_PTS']),
    );
    await _openDetails(tester);
    expect(find.text('Retail price (PTR)'), findsOneWidget);
    expect(find.text('Wholesale price (PTS)'), findsOneWidget);
  });

  testWidgets('on Average without the feature the prices are not offered',
      (tester) async {
    await _open(tester, _LotApi(byLot: false));
    expect(find.text('Retail price'), findsNothing);
    expect(find.text('PTR'), findsNothing);
  });
}
