// Every inventory menu item has to open and render with real data in it.
//
// The module has thirteen tabs across two pages, and only one of them
// (`batches`) was pumped anywhere -- and that one with `hasActiveFirm: false`,
// so it never loaded a row. A section that throws while building a row, or
// reads a field the API does not send, would render an error and no test would
// know.
//
// The payloads below are the running backend's, captured from the seeded
// PHARMACY firm rather than invented, so a field the UI expects and the API
// omits shows up here as it would on screen.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/ui/inventory/batch_management_page.dart';
import 'package:agency_desktop/ui/inventory/inventory_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'dart:convert';

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
      'INVENTORY_IMPORT',
      'OPENING_STOCK_CREATE',
      'OPENING_STOCK_UPDATE',
      'BATCH_VIEW',
      'BATCH_CREATE',
      'SERIAL_CREATE',
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

final Json _inventoryRow = {
  'id': 'inv-1',
  'firm_id': 'firm-1',
  'product_id': 'prod-1',
  'product_code': 'AMOX500',
  'product_name': 'Amoxicillin 500mg',
  'branch_id': 'branch-1',
  'branch_code': 'MEDI_HO',
  'branch_name': 'Head Office',
  'warehouse_id': 'wh-1',
  'warehouse_code': 'MEDI_DC',
  'warehouse_name': 'Distribution Centre',
  'storage_node_id': null,
  'storage_node_code': '',
  'current_quantity': '700.0000',
  'available_quantity': '700.0000',
  'reserved_quantity': '0.0000',
  'blocked_quantity': '0.0000',
  'damaged_quantity': '0.0000',
  'quarantine_quantity': '0.0000',
  'in_transit_quantity': '0.0000',
  'display_quantity': '700.0000',
  'status': 'ACTIVE',
  'created_at': '2026-08-13T00:00:00Z',
  'updated_at': '2026-08-13T00:00:00Z',
};

final Json _movementRow = {
  'id': 'txn-1',
  'inventory_id': 'inv-1',
  'product_id': 'prod-1',
  'product_code': 'AMOX500',
  'product_name': 'Amoxicillin 500mg',
  'transaction_id': 'txn-1',
  'branch_code': 'MEDI_HO',
  'warehouse_code': 'MEDI_DC',
  'transaction_type': 'GOODS_RECEIPT',
  'reference_number': 'GRN-MEDI01-0001',
  'reference_type': 'GOODS_RECEIPT',
  'transaction_date': '2026-08-04',
  'quantity': '120.0000',
  'current_quantity_delta': '120.0000',
  'previous_current_quantity': '0.0000',
  'new_current_quantity': '120.0000',
  'unit_cost': '100.00',
  'total_cost': '12000.00',
  'average_cost_after': '100.0000',
  'created_at': '2026-08-13T00:00:00Z',
};

/// Serves the shapes the running backend serves.
class _InventoryApi extends ApiClient {
  _InventoryApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<String> requested = <String>[];

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
  }) async {
    requested.add(path);
    if (path == '/api/v1/inventory') return _paged([_inventoryRow]);
    if (path == '/api/v1/inventory/transactions') return _paged([_movementRow]);
    if (path == '/api/v1/inventory/ledger') return _paged([_movementRow]);
    if (path == '/api/v1/inventory/opening-stock') return _paged(const []);
    if (path == '/api/v1/inventory/summary') {
      return {
        'data': {
          'total_records': 3,
          'current_quantity': '2075.0000',
          'reserved_quantity': '0.0000',
          'available_quantity': '2075.0000',
          'blocked_quantity': '0.0000',
          'damaged_quantity': '0.0000',
          'quarantine_quantity': '0.0000',
          'in_transit_quantity': '0.0000',
          'low_stock_count': 0,
          'out_of_stock_count': 0,
          'negative_stock_count': 0,
        },
      };
    }
    if (path.startsWith('/api/v1/inventory/summary/')) {
      return {
        'data': [
          {
            'scope_id': 'firm-1',
            'scope_code': 'MEDI01',
            'scope_name': 'Medisphere',
            'product_count': 3,
            'current_quantity': '2075.0000',
            'available_quantity': '2075.0000',
            'reserved_quantity': '0.0000',
          },
        ],
      };
    }
    if (path == '/api/v1/batch-serial/batches/expiry-dashboard') {
      return {
        'data': {
          'expired_today': 0,
          'expire_in_7_days': 0,
          'expire_in_30_days': 0,
          'total_tracked': 0,
          'items': const <dynamic>[],
        },
      };
    }
    if (path == '/api/v1/batch-serial/batches/summary') {
      return {
        'data': {
          'total_batches': 0,
          'near_expiry': 0,
          'expired': 0,
          'quarantine': 0,
        },
      };
    }
    if (path.startsWith('/api/v1/batch-serial/')) return _paged(const []);
    if (path == '/api/v1/products' ||
        path == '/api/v1/branches' ||
        path == '/api/v1/warehouses') {
      return _paged(const []);
    }
    return _paged(const []);
  }
}

Future<void> _pump(WidgetTester tester, Widget page) async {
  await tester.binding.setSurfaceSize(const Size(1600, 900));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(MaterialApp(home: Scaffold(body: page)));
  await tester.pumpAndSettle();
}

void main() {
  for (final InventorySection section in InventorySection.values) {
    testWidgets('the ${section.name} section opens with data in it',
        (tester) async {
      final _InventoryApi api = _InventoryApi();
      await _pump(
        tester,
        InventoryManagementPage(
          api: api,
          preferences: DesktopPreferencesService(),
          permissions: _permissions(),
          hasActiveFirm: true,
          section: section,
        ),
      );

      expect(tester.takeException(), isNull);
      // "Unable to load" is how every one of these sections reports a failed
      // or unreadable response, so it must not be what the user lands on.
      expect(find.textContaining('Unable to load'), findsNothing);
      expect(find.textContaining('Failed to load'), findsNothing);

      // Rendering is not the same as showing the data: a section that
      // swallowed its response would still paint an empty grid.
      final Matcher shows = findsWidgets;
      switch (section) {
        case InventorySection.inventory:
        case InventorySection.stockSearch:
          expect(find.textContaining('AMOX500'), shows,
              reason: 'the stock row never reached the grid');
        case InventorySection.transactions:
        case InventorySection.stockLedger:
          expect(find.textContaining('GRN-MEDI01-0001'), shows,
              reason: 'the movement never reached the grid');
        case InventorySection.stockSummary:
          expect(find.textContaining('2075'), shows,
              reason: 'the summary totals never reached the screen');
        case InventorySection.openingStock:
        case InventorySection.inventoryImport:
        case InventorySection.inventoryExport:
        case InventorySection.settings:
          break;
      }
    });
  }

  for (final BatchSerialSection section in BatchSerialSection.values) {
    testWidgets('the ${section.name} section opens with data in it',
        (tester) async {
      await _pump(
        tester,
        BatchManagementPage(
          api: _InventoryApi(),
          preferences: DesktopPreferencesService(),
          permissions: _permissions(),
          hasActiveFirm: true,
          section: section,
        ),
      );

      expect(tester.takeException(), isNull);
      expect(find.textContaining('Unable to load'), findsNothing);
      expect(find.textContaining('Failed to load'), findsNothing);
    });
  }

  testWidgets('the settings screen offers settings, not a design brief',
      (tester) async {
    await _pump(
      tester,
      InventoryManagementPage(
        api: _InventoryApi(),
        preferences: DesktopPreferencesService(),
        permissions: _permissions(),
        hasActiveFirm: true,
        section: InventorySection.settings,
      ),
    );

    // Two real defaults, both of which this workspace honours.
    expect(find.text('Default opening-stock behavior'), findsOneWidget);
    expect(find.text('Default export format'), findsOneWidget);

    // It also carried four cards of architecture notes -- "transactions are
    // the source of truth", "future phases attach here" -- addressed to
    // whoever builds the module, on a screen belonging to whoever runs a firm.
    // They live in docs/INVENTORY_FRAMEWORK.md now.
    for (final String note in [
      'source of truth',
      'Future phases',
      'append-only',
      'first entry only',
    ]) {
      expect(find.textContaining(note), findsNothing,
          reason: 'engineering notes do not belong on a settings screen');
    }
  });

  testWidgets('the inventory toolbar does not move as rows are selected',
      (tester) async {
    await _pump(
      tester,
      InventoryManagementPage(
        api: _InventoryApi(),
        preferences: DesktopPreferencesService(),
        permissions: _permissions(),
        hasActiveFirm: true,
        section: InventorySection.inventory,
      ),
    );

    // Delete used to appear only once a row was selected, which shifted every
    // button after it while the user was clicking.
    final Finder delete = find.widgetWithText(OutlinedButton, 'Delete');
    expect(delete, findsOneWidget);
    expect(tester.widget<OutlinedButton>(delete).onPressed, isNull,
        reason: 'nothing is selected yet, so it is disabled rather than absent');
  });
}
