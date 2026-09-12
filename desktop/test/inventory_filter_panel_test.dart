import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/inventory/inventory_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The Stock Ledger's filter panel at the smallest desktop the client
/// supports, with real-looking branch, warehouse and product lists so the
/// row of pickers wraps the way it does on screen.
///
/// Found on the 2026-09-12 manual pass (plan item 8.2): the Transaction type
/// picker's floating label was cut in half and a red "overflowed" banner
/// appeared once the panel was opened.

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() {
  final PermissionService service = PermissionService();
  service.applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>[
      'INVENTORY_VIEW',
      'INVENTORY_ADJUST',
      'INVENTORY_TRANSACTION_VIEW',
      'INVENTORY_LEDGER_VIEW',
      'INVENTORY_EXPORT',
    ],
  }));
  return service;
}

Json _paged(List<Json> rows) => {
      'data': rows,
      'pagination': {
        'page': 1,
        'page_size': 20,
        'total_records': rows.length,
        'total_pages': 1,
      },
    };

class _LedgerApi extends ApiClient {
  _LedgerApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => 'token',
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

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
    if (path == '/api/v1/inventory/ledger') {
      return _paged([
        {
          'id': 'led-1',
          'transaction_type': 'GOODS_RECEIPT',
          'reference_number': 'GRN-WHOLE01-BR_NORTH-2026-2027-000001',
          'product_id': 'prod-1',
          'warehouse_id': 'wh-1',
          'quantity': '4.0000',
          'balance_after': '12.0000',
          'created_at': '2026-09-12T10:00:00Z',
        },
      ]);
    }
    if (path == '/api/v1/branches') {
      return _paged([
        {'id': 'br-1', 'code': 'WHL_HO', 'name': 'Chennai Wholesale Branch'},
        {'id': 'br-2', 'code': 'BR_NORTH', 'name': 'North Branch'},
      ]);
    }
    if (path == '/api/v1/warehouses') {
      return _paged([
        {
          'id': 'wh-1',
          'code': 'WHL_DC',
          'name': 'Bulk Goods Warehouse',
          'branch_id': 'br-1',
        },
        {
          'id': 'wh-2',
          'code': 'WH_NORTH',
          'name': 'North Warehouse',
          'branch_id': 'br-2',
        },
      ]);
    }
    if (path == '/api/v1/products') {
      return _paged([
        {'id': 'prod-1', 'code': 'DETER1K', 'name': 'Detergent Powder 1kg'},
      ]);
    }
    return _paged(const []);
  }
}

Future<void> _openLedgerFilters(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: ModuleWorkspaceFrame(
          title: 'Stock Ledger',
          description: 'Every movement, with the balance after it.',
          breadcrumbs: const ['Workspace', 'Inventory', 'Stock Ledger'],
          child: InventoryManagementPage(
            api: _LedgerApi(),
            preferences: DesktopPreferencesService(),
            permissions: _permissions(),
            hasActiveFirm: true,
            section: InventorySection.stockLedger,
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.text('Filters'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the ledger filter panel opens without overflowing at 1366x768',
      (tester) async {
    await _openLedgerFilters(tester);
    expect(tester.takeException(), isNull);

    // Choose a type so the label floats, which is when it was cut off.
    await tester.tap(find.text('Transaction type'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('GOODS_RECEIPT').last);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    final Rect label = tester.getRect(find.text('Transaction type'));
    final Rect panel = tester.getRect(find.byType(FilterPanel));
    expect(
      label.top,
      greaterThanOrEqualTo(panel.top),
      reason: 'the floating label must stay inside the panel',
    );
  });
}
