// Selecting a row in a master workspace should mark the row, and nothing else.
//
// Two defects sat behind this. Single-clicking a customer, vendor or product
// opened a summary panel beside the table -- a second reading of a record the
// user had only pointed at, costing ~300px of grid. And the one master grid
// that numbers its rows (Products) drew no selection marker at all: the number
// cell took the leading position, which is where the marker lives, and it was
// a bare `DataCell` with no tap handler, so the whole column was dead.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/inventory/inventory_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The cell carries `onDoubleTap`, so a single tap is held back until the
/// double-tap window closes. `pumpAndSettle` does not advance a bare timer.
Future<void> _settleTap(WidgetTester tester) async {
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

/// The leading-edge markers currently painted, by border colour.
List<Color> _markerColours(WidgetTester tester) => tester
    .widgetList<Container>(find.byType(Container))
    .map((container) => container.decoration)
    .whereType<BoxDecoration>()
    .map((decoration) => decoration.border)
    .whereType<Border>()
    .where((border) => border.left.width == 3)
    .map((border) => border.left.color)
    .toList();

Widget _grid({
  required bool showRowNumbers,
  required ValueChanged<String> onSelect,
  String? selectedId,
}) =>
    MaterialApp(
      theme: ThemeData(
          colorScheme: const ColorScheme.light(primary: Color(0xFF6750A4))),
      home: Scaffold(
        body: EnterpriseDataGrid<String>(
          items: const ['a', 'b'],
          total: 2,
          pageOffset: 0,
          showRowNumbers: showRowNumbers,
          columns: const [
            GridColumn(key: 'name', label: 'Name'),
            GridColumn(key: 'code', label: 'Code'),
          ],
          id: (item) => item,
          cells: (item) => [item.toUpperCase(), item],
          selectedId: selectedId,
          onSelect: onSelect,
          onPageChanged: (_) {},
        ),
      ),
    );

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _withPermissions(List<String> permissions) {
  final PermissionService service = PermissionService();
  service.applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': permissions,
  }));
  return service;
}

/// A backend serving three customers and nothing else.
class _CustomerApi extends ApiClient {
  _CustomerApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
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
    if (path == '/api/v1/customers') {
      return <String, dynamic>{
        'data': [
          for (int index = 0; index < 3; index++)
            {
              'id': 'cust-$index',
              'code': 'CUS-00$index',
              'name': 'Customer $index',
              'display_name': 'Customer $index',
              'customer_type': 'RETAIL',
              'status': 'ACTIVE',
              'currency_code': 'INR',
              'is_deleted': false,
              'version': 0,
              'created_at': '2026-08-01T00:00:00Z',
            },
        ],
        'pagination': {
          'page': 1,
          'page_size': 20,
          'total_records': 3,
          'total_pages': 1,
        },
      };
    }
    return <String, dynamic>{'data': <String, dynamic>{}};
  }
}

void main() {
  group('the numbered grid', () {
    testWidgets('the row number selects the row like any other cell',
        (tester) async {
      final List<String> selected = [];
      await tester.pumpWidget(
        _grid(showRowNumbers: true, onSelect: selected.add),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('1'));
      await _settleTap(tester);

      expect(selected, ['a'],
          reason: 'the number column was a bare DataCell with no onTap');
    });

    testWidgets('a numbered row still shows its selection marker',
        (tester) async {
      await tester.pumpWidget(
        _grid(showRowNumbers: true, onSelect: (_) {}, selectedId: 'a'),
      );
      await tester.pumpAndSettle();

      expect(
        _markerColours(tester),
        contains(const Color(0xFF6750A4)),
        reason: 'the number cell took the leading slot and lost the marker',
      );
    });

    testWidgets('an unnumbered grid keeps its marker on the first column',
        (tester) async {
      await tester.pumpWidget(
        _grid(showRowNumbers: false, onSelect: (_) {}, selectedId: 'a'),
      );
      await tester.pumpAndSettle();

      expect(_markerColours(tester), contains(const Color(0xFF6750A4)));
    });
  });

  group('the customer workspace', () {
    testWidgets('one click marks the row and opens no summary panel',
        (tester) async {
      await tester.binding.setSurfaceSize(const Size(1600, 900));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: CustomerManagementPage(
            api: _CustomerApi(),
            permissions: _withPermissions(['CUSTOMER_VIEW']),
            hasActiveFirm: true,
          ),
        ),
      ));
      await tester.pumpAndSettle();

      List<bool> rowStates() => tester
          .widget<DataTable>(find.byType(DataTable).first)
          .rows
          .map((row) => row.selected)
          .toList();

      expect(rowStates(), [false, false, false]);

      await tester.tap(find.text('CUS-000').first);
      await _settleTap(tester);

      expect(rowStates(), [true, false, false]);
      expect(find.byType(QuickSummaryPanel), findsNothing,
          reason: 'a single click used to open a summary beside the table');
      // The name appears once, in the grid. Twice meant the panel was echoing
      // the row the user had merely pointed at.
      expect(find.text('Customer 0'), findsOneWidget);
    });
  });

  group('the inventory workspace', () {
    testWidgets('one click marks the row, a double click opens the details',
        (tester) async {
      await tester.binding.setSurfaceSize(const Size(1600, 900));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: InventoryManagementPage(
            api: _InventoryApi(),
            preferences: DesktopPreferencesService(),
            permissions: _withPermissions(['INVENTORY_VIEW']),
            hasActiveFirm: true,
            section: InventorySection.inventory,
          ),
        ),
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.text('PROD-0 - Product 0').first);
      await _settleTap(tester);

      expect(
        find.byType(DetailsPanel),
        findsNothing,
        reason: 'a single click used to open a panel beside the table',
      );

      await tester.tap(find.text('PROD-0 - Product 0').first);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(find.text('PROD-0 - Product 0').first);
      await tester.pumpAndSettle();

      expect(find.byType(AlertDialog), findsOneWidget,
          reason: 'opening a row is what double-click is for');
      // The dialog carries what the panel used to, including the id nobody can
      // read off a grid column.
      expect(find.text('inv-0'), findsOneWidget);
    });
  });
}

/// A backend serving two inventory rows and nothing else.
class _InventoryApi extends ApiClient {
  _InventoryApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
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
    if (path == '/api/v1/inventory') {
      return <String, dynamic>{
        'data': [
          for (int index = 0; index < 2; index++)
            {
              'id': 'inv-$index',
              'product_id': 'prod-$index',
              'product_code': 'PROD-$index',
              'product_name': 'Product $index',
              'branch_id': 'branch-1',
              'branch_code': 'BR1',
              'branch_name': 'Main',
              'warehouse_id': 'wh-1',
              'warehouse_code': 'WH1',
              'warehouse_name': 'Central',
              'current_quantity': '10',
              'available_quantity': '10',
              'reserved_quantity': '0',
              'status': 'ACTIVE',
            },
        ],
        'pagination': {'total_records': 2},
      };
    }
    return <String, dynamic>{
      'data': const <dynamic>[],
      'pagination': {'total_records': 0},
    };
  }
}
