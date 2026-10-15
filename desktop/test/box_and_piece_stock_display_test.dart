// L5 step 11 (BOX_AND_PIECE_LINE_DESIGN 4, "Stock, shown as boxes and
// pieces"): *Show boxes* on the stock screens, the stock reports, their
// downloads and the count sheet. A way of showing and nothing more: offered
// only where a row read carries the item's pack (the server sends one only
// where a box switch is on), it adds no call, and it is remembered per user
// on this PC.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/physical_count.dart';
import 'package:agency_desktop/models/report.dart';
import 'package:agency_desktop/phase2/list_view_request.dart';
import 'package:agency_desktop/ui/inventory/batch_management_page.dart';
import 'package:agency_desktop/ui/inventory/inventory_management_page.dart';
import 'package:agency_desktop/ui/inventory/physical_count_sheet_dialog.dart';
import 'package:agency_desktop/ui/purchases/reorder_dialog.dart';
import 'package:agency_desktop/ui/reports/reports_workspace.dart';
import 'package:agency_desktop/ui/workspace/box_piece_cells.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:excel/excel.dart' as xls;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Signed in as [user] with [permissions]: the token's `sub` is what the
/// choice is remembered under.
PermissionService _signedIn(String user, List<String> permissions) {
  final String claims = base64Url
      .encode(utf8.encode(jsonEncode(<String, dynamic>{
        'sub': user,
        'roles': const <String>['user'],
        'permissions': permissions,
      })))
      .replaceAll('=', '');
  return PermissionService()..applyAccessToken('header.$claims.sig');
}

Json _paged(List<Json> rows) => <String, dynamic>{
      'data': rows,
      'pagination': <String, dynamic>{
        'page': 1,
        'page_size': 20,
        'total_records': rows.length,
        'total_pages': 1,
      },
    };

/// Soap, 89 pieces of a 12-box; tea, 7 loose with no pack.
Json _stock(String id, String quantity, {String? pack}) => <String, dynamic>{
      'id': id,
      'transaction_id': id,
      'product_id': 'p-$id',
      'product_code': id == 'soap' ? 'P-1' : 'P-2',
      'product_name': id == 'soap' ? 'Soap' : 'Tea',
      'branch_code': 'BR',
      'warehouse_code': 'WH',
      'status': 'ACTIVE',
      'current_quantity': quantity,
      'available_quantity': quantity,
      'reserved_quantity': '0',
      'transaction_type': 'RECEIPT',
      'transaction_date': '2026-10-15',
      'reference_number': 'GR-1',
      'quantity': quantity,
      'new_current_quantity': quantity,
      'pack_size': pack,
      'pack_unit_code': pack == null ? null : 'BOX',
    };

class _StockApi extends ApiClient {
  _StockApi({required this.packed})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// Whether the firm has a box switch on, so the rows carry a pack.
  final bool packed;

  /// Every call made, in order.
  final List<String> calls = <String>[];

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
    calls.add('$method $path');
    if (path == '/api/v1/inventory' || path == '/api/v1/inventory/ledger') {
      return _paged(<Json>[
        _stock('soap', '89.0000', pack: packed ? '12.0000' : null),
        _stock('tea', '7.0000'),
      ]);
    }
    return _paged(const <Json>[]);
  }
}

Future<void> _pumpInventory(
  WidgetTester tester,
  _StockApi api,
  DesktopPreferencesService preferences, {
  InventorySection section = InventorySection.inventory,
  String user = 'user-1',
  Size size = const Size(1600, 900),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: InventoryManagementPage(
          key: ValueKey<String>('$user-$section'),
          api: api,
          preferences: preferences,
          permissions: _signedIn(user, const ['INVENTORY_VIEW']),
          hasActiveFirm: true,
          section: section,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

DesktopPreferencesService _preferences() {
  final Directory temp = Directory.systemTemp.createTempSync('show-boxes');
  addTearDown(() {
    if (temp.existsSync()) temp.deleteSync(recursive: true);
  });
  return DesktopPreferencesService(directory: temp);
}

Future<void> _toggle(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey<String>('show-boxes')));
  await tester.pumpAndSettle();
}

/// The cells of a saved workbook's one sheet, as plain values.
List<List<Object?>> _cells(List<int> bytes) {
  final xls.Sheet sheet = xls.Excel.decodeBytes(bytes).tables.values.first;
  return [
    for (final List<xls.Data?> row in sheet.rows)
      [
        for (final xls.Data? cell in row)
          switch (cell?.value) {
            final xls.DoubleCellValue value => value.value,
            final xls.IntCellValue value => value.value,
            final xls.TextCellValue value => '${value.value}',
            null => null,
            final xls.CellValue value => '$value',
          },
      ],
  ];
}

void main() {
  group('the figure', () {
    test('89 of a 12-box reads 7 x 12 + 5 with the pieces beside it', () {
      expect(stockInBoxes('89.0000', '12.0000'), '7 x 12 + 5 (89)');
      expect(stockInBoxes('24', '12'), '2 x 12 (24)');
      expect(stockInBoxes('-14', '12'), '-1 x 12 + 2 (-14)');
      expect(stockInBoxes('1234', '12', beside: '1,234'),
          '102 x 12 + 10 (1,234)');
    });

    test('under a box, or with no pack, it reads as today', () {
      expect(stockInBoxes('5.0000', '12'), '5.0000');
      expect(stockInBoxes('89.0000', ''), '89.0000');
      expect(stockInBoxes('89', '1'), '89');
    });

    test('a download writes boxes, pieces and total as numbers', () {
      expect(stockBoxColumns('89.0000', '12.0000'), <Object?>[7, 5.0, 89.0]);
      expect(stockBoxColumns('7', ''), <Object?>[null, 7.0, 7.0]);
      expect(stockBoxColumns('-14', '12'), <Object?>[-1, -2.0, -14.0]);
      expect(stockBoxHeadings('Closing'),
          <String>['Closing boxes', 'Closing pieces', 'Closing total']);
    });

    test('offered only where a row carries a pack', () {
      expect(offersShowBoxes(<String>['', '1', '']), isFalse);
      expect(offersShowBoxes(<String>['', '12.0000']), isTrue);
    });
  });

  group('stock on hand and the stock ledger', () {
    testWidgets('no toggle where no row carries a pack', (tester) async {
      await _pumpInventory(tester, _StockApi(packed: false), _preferences());
      expect(find.text('89'), findsWidgets);
      expect(find.byKey(const ValueKey<String>('show-boxes')), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('on, a packed item reads 7 x 12 + 5 and the call count stays',
        (tester) async {
      final _StockApi api = _StockApi(packed: true);
      await _pumpInventory(tester, api, _preferences());
      expect(find.byKey(const ValueKey<String>('show-boxes')), findsOneWidget);
      expect(find.text('7 x 12 + 5 (89)'), findsNothing);
      final int before = api.calls.length;

      await _toggle(tester);
      // Current and Available; reserved is nothing.
      expect(find.text('7 x 12 + 5 (89)'), findsNWidgets(2));
      // Tea has no pack: as before.
      expect(find.textContaining('x 12', findRichText: true),
          findsNWidgets(2));
      expect(api.calls.length, before, reason: 'Show boxes asks nothing');

      await _toggle(tester);
      expect(find.text('7 x 12 + 5 (89)'), findsNothing);
      expect(api.calls.length, before);
      expect(tester.takeException(), isNull);
    });

    testWidgets('remembered after reopening, for that user only',
        (tester) async {
      final DesktopPreferencesService preferences = _preferences();
      await _pumpInventory(tester, _StockApi(packed: true), preferences,
          section: InventorySection.stockLedger);
      await _toggle(tester);
      expect(find.text('7 x 12 + 5 (89)'), findsNWidgets(2));
      expect(
        preferences.workspaceState(ShowBoxesChoice.keyFor('user-1')),
        <String, dynamic>{'on': true},
      );

      // Closed and opened again, on another stock screen: still on.
      await tester.pumpWidget(const SizedBox.shrink());
      await _pumpInventory(tester, _StockApi(packed: true), preferences);
      expect(find.text('7 x 12 + 5 (89)'), findsNWidgets(2));

      // Somebody else signed in on this PC has their own choice.
      await _pumpInventory(tester, _StockApi(packed: true), preferences,
          user: 'user-2');
      expect(find.text('7 x 12 + 5 (89)'), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('fits at 800x600 with the toggle on', (tester) async {
      final DesktopPreferencesService preferences = _preferences();
      await _pumpInventory(tester, _StockApi(packed: true), preferences,
          size: const Size(800, 600));
      await _toggle(tester);
      expect(tester.takeException(), isNull);
      await _pumpInventory(tester, _StockApi(packed: true), preferences,
          section: InventorySection.stockLedger, size: const Size(800, 600));
      expect(find.byKey(const ValueKey<String>('show-boxes')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  group('the lot list', () {
    testWidgets('shows a lot of a packed item as boxes', (tester) async {
      final _BatchApi api = _BatchApi();
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Phase2Scope(
            child: BatchManagementPage(
              api: api,
              preferences: _preferences(),
              permissions: _signedIn('user-1', const ['BATCH_VIEW']),
              hasActiveFirm: true,
              section: BatchSerialSection.batches,
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      final int before = api.reads;
      await _toggle(tester);
      expect(find.text('7 x 12 + 5 (89)'), findsNWidgets(2));
      expect(find.text('3'), findsWidgets);
      expect(api.reads, before);
      expect(tester.takeException(), isNull);
    });
  });

  group('the stock reports', () {
    Future<_ReportApi> pumpReport(
      WidgetTester tester, {
      required List<List<int>> saved,
      required DesktopPreferencesService preferences,
      bool packed = true,
    }) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final _ReportApi api = _ReportApi(packed: packed);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Phase2Scope(
            child: ListViewRequestScope(
              request: const ListViewRequest(
                path: 'reports/financial',
                view: 'stock-valuation',
                serial: 1,
              ),
              child: ReportsWorkspace(
                api: api,
                permissions: _signedIn('user-1', const ['REPORT_VIEW']),
                preferences: preferences,
                hasActiveFirm: true,
                tabId: 'financial',
                saveFile: (name, bytes) async {
                  saved.add(bytes);
                  return 'C:/out/$name';
                },
              ),
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      return api;
    }

    testWidgets('no toggle on a firm without the switch', (tester) async {
      await pumpReport(tester,
          saved: [], preferences: _preferences(), packed: false);
      expect(find.byKey(const ValueKey<String>('show-boxes')), findsNothing);
    });

    testWidgets('the valuation reads boxes and downloads three columns',
        (tester) async {
      final List<List<int>> saved = [];
      final _ReportApi api =
          await pumpReport(tester, saved: saved, preferences: _preferences());
      final int before = api.reads;
      await _toggle(tester);
      expect(find.text('7 x 12 + 5 (89)'), findsOneWidget);
      expect(api.reads, before);

      await tester.tap(find.byKey(const ValueKey<String>('workbook-download')));
      await tester.pumpAndSettle();
      final List<List<Object?>> cells = _cells(saved.single);
      final List<Object?> headings = cells[3];
      final int at = headings.indexOf('Quantity boxes');
      expect(headings.sublist(at, at + 3),
          ['Quantity boxes', 'Quantity pieces', 'Quantity total']);
      expect(headings, isNot(contains('Quantity')));
      expect(cells[4].sublist(at, at + 3), [7, 5.0, 89.0]);
      // Tea: no box figure, its pieces the whole.
      expect(cells[5].sublist(at, at + 3), [null, 7.0, 7.0]);
      // The money beside it is untouched.
      expect(cells[4][headings.indexOf('Value at cost')], 890.0);
      expect(tester.takeException(), isNull);
    });

    testWidgets('off, the download is as before', (tester) async {
      final List<List<int>> saved = [];
      await pumpReport(tester, saved: saved, preferences: _preferences());
      await tester.tap(find.byKey(const ValueKey<String>('workbook-download')));
      await tester.pumpAndSettle();
      final List<Object?> headings = _cells(saved.single)[3];
      expect(headings, contains('Quantity'));
      expect(headings, isNot(contains('Quantity boxes')));
    });
  });

  group('below reorder level', () {
    testWidgets('available, reorder level and on order read as boxes; the '
        'order is still typed in pieces', (tester) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final _ReorderApi api = _ReorderApi();
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: ReorderDialog(api: api)),
      ));
      await tester.pumpAndSettle();
      final int before = api.reads;
      await _toggle(tester);
      expect(find.text('2 x 12 + 1 (25)'), findsOneWidget);
      expect(find.text('4 x 12 (48)'), findsOneWidget);
      expect(find.text('1 x 12 (12)'), findsOneWidget);
      final TextField order = tester
          .widget<TextField>(find.byKey(const ValueKey('reorder-quantity-0')));
      expect(order.controller!.text, '60');
      expect(api.reads, before);
      expect(tester.takeException(), isNull);
    });
  });

  group('the count sheet', () {
    PhysicalCountSheet sheet() => PhysicalCountSheet.fromJson(<String, dynamic>{
          'id': 'pc-1',
          'branch_id': 'b-1',
          'warehouse_id': 'w-1',
          'count_number': 'PC-1',
          'count_date': '2026-10-15',
          'status': 'DRAFT',
          'lines': <Json>[
            <String, dynamic>{
              'id': 'l-1',
              'line_number': 1,
              'product_id': 'p-1',
              'product_code': 'P-1',
              'product_name': 'Soap',
              'expected_quantity': '89.0000',
              'counted_quantity': '101',
              'pack_size': '12.0000',
              'pack_unit_code': 'BOX',
            },
            <String, dynamic>{
              'id': 'l-2',
              'line_number': 2,
              'product_id': 'p-2',
              'product_code': 'P-2',
              'product_name': 'Tea',
              'expected_quantity': '7.0000',
            },
          ],
        });

    Future<void> pumpSheet(
      WidgetTester tester,
      DesktopPreferencesService preferences, {
      Size size = const Size(1400, 900),
    }) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: PhysicalCountSheetDialog(
            key: UniqueKey(),
            api: _StockApi(packed: true),
            sheet: sheet(),
            canCount: true,
            boxes: ShowBoxesChoice(preferences: preferences, userId: 'user-1'),
          ),
        ),
      ));
      await tester.pumpAndSettle();
    }

    testWidgets('expected and the difference read as boxes; the count is '
        'typed in pieces, and the choice is kept', (tester) async {
      final DesktopPreferencesService preferences = _preferences();
      await pumpSheet(tester, preferences);
      expect(find.text('89.0000'), findsOneWidget);
      await _toggle(tester);
      expect(find.text('7 x 12 + 5 (89.0000)'), findsOneWidget);
      expect(find.text('+1 x 12 (+12.0000)'), findsOneWidget);
      // The box typed in is still pieces.
      expect(find.widgetWithText(TextField, '101'), findsOneWidget);
      // Tea has no pack.
      expect(find.text('7.0000'), findsOneWidget);

      // Opened again: still on. (At 800x600 the sheet's footer already
      // overflowed before L5; the line with the toggle fits.)
      await tester.pumpWidget(const SizedBox.shrink());
      await pumpSheet(tester, preferences, size: const Size(1024, 768));
      expect(find.text('7 x 12 + 5 (89.0000)'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });
}

class _BatchApi extends ApiClient {
  _BatchApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  int reads = 0;

  BatchRecord _batch(String number, String quantity, String pack) =>
      BatchRecord.fromJson(<String, dynamic>{
        'id': 'batch-$number',
        'product_id': 'p-1',
        'product_code': 'P-1',
        'product_name': 'Soap',
        'warehouse_name': 'North',
        'batch_number': number,
        'expiry_date': '2026-12-31',
        'status': 'ACTIVE',
        'quantity': quantity,
        'available_quantity': quantity,
        'pack_size': pack,
      });

  @override
  Future<PagedResult<BatchRecord>> batches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BatchQuery filters = const BatchQuery(),
  }) async {
    reads++;
    return PagedResult<BatchRecord>(
      items: [_batch('B-1', '89', '12.0000'), _batch('B-2', '3', '')],
      total: 2,
    );
  }

  @override
  Future<BatchSummaryRecord> batchSummary() async {
    reads++;
    return const BatchSummaryRecord(
      totalBatches: 2,
      nearExpiry: 0,
      expired: 0,
      quarantine: 0,
    );
  }

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
    reads++;
    return _paged(const <Json>[]);
  }
}

class _ReportApi extends ApiClient {
  _ReportApi({required this.packed})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool packed;
  int reads = 0;

  @override
  Future<ReportPage> reportRows(
    String path, {
    Map<String, String>? query,
    String? rowsKey,
  }) async {
    reads++;
    return ReportPage(
      rows: <Json>[
        <String, dynamic>{
          'product_code': 'P-1',
          'product_name': 'Soap',
          'unit': 'PCS',
          'quantity': '89.0000',
          'rate': '10.00',
          'value': '890.00',
          'pack_size': packed ? '12.0000' : null,
          'pack_unit_code': packed ? 'BOX' : null,
        },
        <String, dynamic>{
          'product_code': 'P-2',
          'product_name': 'Tea',
          'unit': 'PCS',
          'quantity': '7.0000',
          'rate': '5.00',
          'value': '35.00',
          'pack_size': null,
        },
      ],
      total: 2,
    );
  }
}

class _ReorderApi extends ApiClient {
  _ReorderApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  int reads = 0;

  @override
  Future<List<Json>> belowReorderLevel({String? warehouseId}) async {
    reads++;
    return <Json>[
      <String, dynamic>{
        'warehouse_id': 'w-1',
        'warehouse_code': 'WH',
        'product_id': 'p-1',
        'product_code': 'P-1',
        'product_name': 'Soap',
        'available_quantity': '25.0000',
        'reorder_level': '48.0000',
        'on_order_quantity': '12.0000',
        'suggested_quantity': '60.0000',
        'supplier_id': 's-1',
        'supplier_name': 'Hindustan Traders',
        'pack_size': '12.0000',
        'pack_unit_code': 'BOX',
      },
    ];
  }

  @override
  Future<Json> reorderPlanning() async {
    reads++;
    return <String, dynamic>{'basis': 'LEVEL'};
  }
}
