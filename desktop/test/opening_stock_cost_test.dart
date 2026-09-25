// D-QA-5: the opening-stock dialog had no unit cost, batch or expiry field.
//
// The backend has always taken all three, but a screen that never sent them
// brought day-one stock in at zero value -- wrong stock value and wrong margins
// from the first sale -- and a batch-tracked product could not be loaded at
// all. These cases drive the dialog and read what it actually posts.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/inventory.dart';
import 'package:agency_desktop/ui/inventory/inventory_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>[
      'INVENTORY_VIEW',
      'OPENING_STOCK_CREATE',
      'OPENING_STOCK_UPDATE',
    ],
  }));

Json _paged(List<Json> rows) => {
      'data': rows,
      'pagination': {
        'page': 1,
        'page_size': 20,
        'total_records': rows.length,
        'total_pages': 1,
      },
    };

Json _product({bool trackBatch = false}) => {
      'id': 'prod-1',
      'code': 'QA-P1',
      'name': 'QA Product One',
      'purchase_price': '80.00',
      'selling_price': '100.00',
      'mrp': '120.00',
      'status': 'ACTIVE',
      'track_batch': trackBatch,
    };

final Json _batch = {
  'id': 'batch-1',
  'version': 1,
  'firm_id': 'firm-1',
  'branch_id': 'branch-1',
  'branch_code': 'HO',
  'branch_name': 'Head Office',
  'warehouse_id': 'wh-1',
  'warehouse_code': 'MAIN',
  'warehouse_name': 'Main Store',
  'reference_number': 'OPEN-001',
  'posting_date': '2026-09-25',
  'source_format': 'MANUAL',
  'status': 'DRAFT',
  'lines': const <dynamic>[],
  'created_at': '2026-09-25T00:00:00Z',
  'updated_at': '2026-09-25T00:00:00Z',
};

class _OpeningStockApi extends ApiClient {
  _OpeningStockApi({this.trackBatch = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool trackBatch;
  final List<Json> created = <Json>[];

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async {
    if (method == 'POST' && path == '/api/v1/inventory/opening-stock') {
      created.add(body!);
      return {'data': _batch};
    }
    if (path == '/api/v1/products') {
      return _paged([_product(trackBatch: trackBatch)]);
    }
    if (path == '/api/v1/branches') {
      return _paged([
        {'id': 'branch-1', 'code': 'HO', 'name': 'Head Office'},
      ]);
    }
    if (path == '/api/v1/warehouses') {
      return _paged([
        {
          'id': 'wh-1',
          'code': 'MAIN',
          'name': 'Main Store',
          'branch_id': 'branch-1',
        },
      ]);
    }
    return _paged(const []);
  }
}

Future<void> _openDialog(WidgetTester tester, _OpeningStockApi api) async {
  await tester.binding.setSurfaceSize(const Size(1600, 1000));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: InventoryManagementPage(
        api: api,
        preferences: DesktopPreferencesService(),
        permissions: _permissions(),
        hasActiveFirm: true,
        section: InventorySection.openingStock,
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.text('New opening stock'));
  await tester.pumpAndSettle();
  await tester
      .tap(find.widgetWithText(DropdownButtonFormField<String>, 'Product'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('QA-P1 - QA Product One').last);
  await tester.pumpAndSettle();
  await tester.enterText(find.widgetWithText(TextField, 'Quantity'), '10');
}

Future<void> _save(WidgetTester tester) async {
  await tester.ensureVisible(find.widgetWithText(FilledButton, 'Save'));
  await tester.tap(find.widgetWithText(FilledButton, 'Save'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a line posts its unit cost, batch and expiry', (tester) async {
    final _OpeningStockApi api = _OpeningStockApi();
    await _openDialog(tester, api);

    // The purchase price is the starting value; what is typed wins.
    final TextField cost = tester
        .widget<TextField>(find.byKey(const ValueKey('opening-unit-cost-0')));
    expect(cost.controller!.text, '80.00');
    await tester.enterText(
        find.byKey(const ValueKey('opening-unit-cost-0')), '75.50');
    await tester.enterText(
        find.byKey(const ValueKey('opening-batch-0')), 'B-001');
    await tester.enterText(
        find.byKey(const ValueKey('opening-expiry-0')), '2027-06-30');
    await _save(tester);

    expect(api.created, hasLength(1));
    final Json line = (api.created.single['lines'] as List).single as Json;
    expect(line['unit_cost'], 75.5);
    expect(line['batch_number'], 'B-001');
    expect(line['expiry_date'], '2027-06-30');
  });

  testWidgets('a line with no cost is saved only when the user confirms',
      (tester) async {
    final _OpeningStockApi api = _OpeningStockApi();
    await _openDialog(tester, api);
    await tester.enterText(
        find.byKey(const ValueKey('opening-unit-cost-0')), '');

    await _save(tester);
    expect(api.created, isEmpty, reason: 'the first Save only warns');
    expect(find.textContaining('valued at zero'), findsWidgets);

    await _save(tester);
    expect(api.created, hasLength(1));
    final Json line = (api.created.single['lines'] as List).single as Json;
    expect(line.containsKey('unit_cost'), isFalse);
  });

  testWidgets('a batch-tracked product needs its batch number', (tester) async {
    final _OpeningStockApi api = _OpeningStockApi(trackBatch: true);
    await _openDialog(tester, api);

    await _save(tester);
    expect(api.created, isEmpty);
    expect(find.textContaining('is batch-tracked'), findsOneWidget);
  });

  test('a draft reads its cost, batch and expiry back for editing', () {
    final OpeningStockLineRecord line = OpeningStockLineRecord.fromJson({
      'id': 'line-1',
      'line_number': 1,
      'product_id': 'prod-1',
      'quantity': '10.0000',
      'unit_cost': '75.500000',
      'batch_number': 'B-001',
      'expiry_date': '2027-06-30',
    });
    expect(line.unitCost, '75.500000');
    expect(line.batchNumber, 'B-001');
    expect(line.expiryDate, '2027-06-30');
  });
}
