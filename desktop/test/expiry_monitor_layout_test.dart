// The Expiry Monitor lays out inside its own scroll view.
//
// It renders the batch grid, and that grid put its table in an `Expanded`.
// Inside a `SingleChildScrollView` the height is unbounded, so `Expanded` is a
// layout assertion rather than a stretch:
//
//   RenderFlex children have non-zero flex but incoming height constraints
//   are unbounded
//
// It threw every time the screen was opened with any batch on it. Nothing
// caught it because the only coverage this page had — `workspace_overflow_test`
// — builds it with `hasActiveFirm: false`, which stops at the "no firm
// selected" empty state and never reaches the grid at all. A screen rendered
// without data is a screen that has not been tested.
//
// A widget test fails on a layout assertion by itself, so these need no
// `expect` for the defect: reaching the end is the assertion.

import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/entities.dart';
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

Future<void> _open(
  WidgetTester tester,
  BatchSerialSection section, {
  Size size = const Size(1600, 1000),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory temp = Directory.systemTemp.createTempSync('expiry-monitor');
  addTearDown(() => temp.deleteSync(recursive: true));

  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: BatchManagementPage(
        api: _BatchApi(),
        preferences: DesktopPreferencesService(directory: temp),
        permissions: PermissionService()
          ..applyAccessToken(accessTokenFor(const <String>['BATCH_VIEW'])),
        // The half the existing coverage never exercised.
        hasActiveFirm: true,
        section: section,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the expiry monitor renders its batches', (tester) async {
    await _open(tester, BatchSerialSection.expiryMonitor);

    expect(find.text('Expiry Monitor'), findsWidgets);
    expect(find.text('All Batches'), findsOneWidget);
    expect(find.text('B-001'), findsWidgets);
  });

  testWidgets('the batches tab still fills the height it is given',
      (tester) async {
    // The other caller, where `Expanded` is right: the workspace hands the
    // grid a bounded height and the table should take what is left.
    await _open(tester, BatchSerialSection.batches);

    expect(find.text('B-001'), findsWidgets);
    expect(find.byType(Expanded), findsWidgets);
  });

  testWidgets('the expiry monitor survives a short window', (tester) async {
    // Unbounded height is the scroll view's doing, not the window's, but a
    // short window is where a reader would expect this to break.
    await _open(tester,
        BatchSerialSection.expiryMonitor, size: const Size(1366, 768));

    expect(find.text('All Batches'), findsOneWidget);
  });
}
