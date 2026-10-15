// D-UI-84 (2026-10-08): the app reported "Concurrent modification during
// iteration: Instance(length:7) of '_GrowableList'" three times while the
// batch and serial screens were clicked -- a batch deleted from the row
// menu, and the Serial Numbers list. The report carried no frame of the app.
//
// These drive the same clicks in the phase 2 page frame, with seven rows as
// in the report, and fail on any error the framework catches. They did not
// reproduce it on 2026-10-15; they stay as the guard for when it is found.

import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/inventory/batch_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/access_token.dart';

BatchRecord _batch(int n) => BatchRecord.fromJson(<String, dynamic>{
      'id': 'batch-$n',
      'firm_id': 'firm-1',
      'product_id': 'p-1',
      'product_code': 'P1',
      'product_name': 'Detergent',
      'warehouse_id': 'w-1',
      'warehouse_code': 'WH',
      'warehouse_name': 'North',
      'branch_id': 'b-1',
      'batch_number': 'B-00$n',
      'expiry_date': '2026-12-31',
      'status': 'ACTIVE',
      'quantity': '20',
      'available_quantity': '20',
    });

SerialRecord _serial(int n) => SerialRecord.fromJson(<String, dynamic>{
      'id': 'serial-$n',
      'firm_id': 'firm-1',
      'product_id': 'p-1',
      'product_code': 'P1',
      'product_name': 'Phone',
      'warehouse_id': 'w-1',
      'warehouse_name': 'North',
      'serial_number': 'S-00$n',
      'status': 'AVAILABLE',
    });

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<BatchRecord> batchRows = [for (int n = 1; n <= 7; n++) _batch(n)];
  final List<SerialRecord> serialRows = [
    for (int n = 1; n <= 7; n++) _serial(n),
  ];

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
        items: List.of(batchRows),
        total: batchRows.length,
      );

  @override
  Future<BatchSummaryRecord> batchSummary() async => BatchSummaryRecord(
        totalBatches: batchRows.length,
        nearExpiry: 1,
        expired: 0,
        quarantine: 0,
      );

  @override
  Future<void> deleteBatch(String id) async =>
      batchRows.removeWhere((b) => b.id == id);

  @override
  Future<PagedResult<SerialRecord>> serials({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    SerialQuery filters = const SerialQuery(),
  }) async =>
      PagedResult<SerialRecord>(
        items: List.of(serialRows),
        total: serialRows.length,
      );

  @override
  Future<void> deleteSerial(String id) async =>
      serialRows.removeWhere((s) => s.id == id);

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async =>
      {
        'data': const <Json>[],
        'pagination': {
          'page': 1,
          'page_size': 20,
          'total_records': 0,
          'total_pages': 0,
        },
      };
}

Future<void> _pump(
  WidgetTester tester,
  _Api api,
  BatchSerialSection section,
) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory temp = Directory.systemTemp.createTempSync('d-ui-84');
  addTearDown(() => temp.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: phase2Frame(
        title: 'Batch and serial',
        description: 'Batches, lots and serial numbers.',
        child: BatchManagementPage(
          api: api,
          preferences: DesktopPreferencesService(directory: temp),
          permissions: PermissionService()
            ..applyAccessToken(accessTokenFor(const [
              'BATCH_VIEW',
              'BATCH_DELETE',
              'SERIAL_VIEW',
              'SERIAL_DELETE',
            ])),
          hasActiveFirm: true,
          section: section,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _deleteRow(WidgetTester tester, String text) async {
  await tester.tap(find.text(text), buttons: kSecondaryButton);
  await tester.pumpAndSettle();
  await tester.tap(find.text('Delete').last);
  await tester.pumpAndSettle();
  await tester.tap(find.widgetWithText(FilledButton, 'Delete'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('deleting batches from the row menu raises no error',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, BatchSerialSection.batches);
    for (int i = 0; i < 3; i++) {
      await _deleteRow(tester, 'B-00${i + 1}');
      expect(tester.takeException(), isNull);
    }
    expect(api.batchRows, hasLength(4));
    expect(find.text('B-001'), findsNothing);
  });

  testWidgets('the serial list opens and deletes with no error',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, BatchSerialSection.serials);
    expect(tester.takeException(), isNull);
    expect(find.text('S-007'), findsOneWidget);
    for (int i = 0; i < 3; i++) {
      await _deleteRow(tester, 'S-00${i + 1}');
      expect(tester.takeException(), isNull);
    }
    expect(api.serialRows, hasLength(4));
  });

  testWidgets('deleting while the mouse moves over the rows',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, BatchSerialSection.batches);
    final TestGesture mouse =
        await tester.createGesture(kind: PointerDeviceKind.mouse);
    await mouse.addPointer(location: tester.getCenter(find.text('B-003')));
    addTearDown(mouse.removePointer);
    for (int i = 1; i <= 3; i++) {
      await tester.tap(find.text('B-00$i'));
      await mouse.moveTo(tester.getCenter(find.text('B-00${i + 1}')));
      await tester.pump();
      await _deleteRow(tester, 'B-00$i');
      await mouse.moveTo(tester.getCenter(find.text('B-007')));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    }
    expect(api.batchRows, hasLength(4));
  });
}
