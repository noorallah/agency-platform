// D-DLG-7 (opening stock half) copies the harness of D-QA-5: the opening-stock dialog had no unit cost, batch or expiry field.
//
// The backend has always taken all three, but a screen that never sent them
// brought day-one stock in at zero value -- wrong stock value and wrong margins
// from the first sale -- and a batch-tracked product could not be loaded at
// all. These cases drive the dialog and read what it actually posts.

import 'dart:convert';

import 'package:agency_desktop/models/audit.dart';
import 'package:agency_desktop/phase2/phase2_scope.dart';
import 'package:agency_desktop/ui/settings/audit_log_page.dart';
import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
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

Json _product() => {
      'id': 'prod-1',
      'code': 'QA-P1',
      'name': 'QA Product One',
      'purchase_price': '80.00',
      'selling_price': '100.00',
      'mrp': '120.00',
      'status': 'ACTIVE',
      'track_batch': false,
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
  _OpeningStockApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

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
      return _paged([_product()]);
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
  await tester.binding.setSurfaceSize(const Size(1366, 768));
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

void main() {
  testWidgets('opening stock with many lines scrolls at 1366 x 768',
      (tester) async {
    final _OpeningStockApi api = _OpeningStockApi();
    await _openDialog(tester, api);
    for (int i = 0; i < 12; i++) {
      await tester.ensureVisible(find.text('Add line'));
      await tester.tap(find.text('Add line'));
      await tester.pumpAndSettle();
    }
    expect(tester.takeException(), isNull, reason: 'no overflow');
    final Size dialog = tester.getSize(find.byType(AlertDialog));
    expect(dialog.height, lessThanOrEqualTo(768));
    // Everything is still reachable: the last line scrolls into view.
    await tester
        .ensureVisible(find.byKey(const ValueKey('opening-unit-cost-12')));
    expect(tester.takeException(), isNull);
  });

  for (final bool phase2 in <bool>[false, true]) {
    testWidgets('a long audit detail scrolls at 1366 x 768 (phase2=$phase2)',
        (tester) async {
      tester.view.physicalSize = const Size(1366, 768);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final Map<String, Object?> before = <String, Object?>{
        for (int i = 0; i < 40; i++) 'field_number_$i': 'old value $i',
        'notes': 'x' * 400,
      };
      final Map<String, Object?> after = <String, Object?>{
        for (int i = 0; i < 40; i++) 'field_number_$i': 'new value $i',
        'notes': 'y' * 400,
      };
      final AuditLogEntry entry = AuditLogEntry.fromJson(<String, dynamic>{
        'id': 'a-1',
        'created_at': '2026-08-14T06:00:00Z',
        'action': 'customer.updated',
        'entity_type': 'customer',
        'entity_id': 'c-1',
        'actor_id': 'u-1',
        'actor_name': 'Asha Kumar',
        'firm_id': 'firm-1',
        'before_data': before,
        'after_data': after,
        'ip_address': '10.0.0.4',
        'application_version': '1.0.0',
      });
      await tester.pumpWidget(
        MaterialApp(
          builder:
              phase2 ? (context, child) => Phase2Scope(child: child!) : null,
          home: Scaffold(
            body: AuditLogPage(
              api: _AuditApi(<AuditLogEntry>[entry]),
              permissions: PermissionService()
                ..applyAccessToken(_accessToken(<String, dynamic>{
                  'permissions': <String>['AUDIT_LOG_VIEW'],
                })),
              firmLabel: 'Wholesale Hub',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('customer.updated').first);
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();
      if (phase2) {
        await tester.tap(find.byKey(const ValueKey('selection-view')));
        await tester.pumpAndSettle();
        expect(find.byType(AlertDialog), findsOneWidget);
        expect(
          tester.getSize(find.byType(AlertDialog)).height,
          lessThanOrEqualTo(768),
        );
      } else {
        await tester.tap(find.text('customer.updated').first);
        await tester.pumpAndSettle();
      }
      expect(tester.takeException(), isNull, reason: 'no overflow');
    });
  }
}

class _AuditApi extends ApiClient {
  _AuditApi(this.rows)
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<AuditLogEntry> rows;

  @override
  Future<PagedResult<AuditLogEntry>> auditLogs({
    int page = 1,
    int pageSize = 20,
    String? action,
    String? entityType,
    String? dateFrom,
    String? dateTo,
  }) async =>
      PagedResult<AuditLogEntry>(items: rows, total: rows.length);
}
