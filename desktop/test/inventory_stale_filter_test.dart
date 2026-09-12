import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/inventory/inventory_management_page.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A filter remembered on this machine names an id from whichever firm it
/// was set in. Restored in another firm it names nothing, and a dropdown
/// handed a value outside its list asserts and takes the section down with
/// "This section failed to render" -- found on the 2026-09-12 manual pass
/// (plan item 8.6) on switching from WHOLE01 to MEDI01 with a warehouse
/// filter set. The page drops such ids when its lists arrive and never hands
/// a dropdown a value its list does not hold.

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() {
  final PermissionService service = PermissionService();
  service.applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['INVENTORY_VIEW', 'INVENTORY_ADJUST'],
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

/// MEDI01's lists: one branch, one warehouse, one product, none of them the
/// ids the remembered filter names.
class _OtherFirmApi extends ApiClient {
  _OtherFirmApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => 'token',
          refreshAccessToken: () async => false,
          activeFirmId: () => 'medi01',
        );

  final List<Map<String, String>?> inventoryQueries = [];

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
      inventoryQueries.add(query);
      return _paged(const []);
    }
    if (path == '/api/v1/branches') {
      return _paged([
        {'id': 'medi-br', 'code': 'MEDI_HO', 'name': 'Hyderabad Pharma Hub'},
      ]);
    }
    if (path == '/api/v1/warehouses') {
      return _paged([
        {
          'id': 'medi-wh',
          'code': 'MEDI_DC',
          'name': 'Cold Chain Distribution Center',
          'branch_id': 'medi-br',
        },
      ]);
    }
    if (path == '/api/v1/products') {
      return _paged([
        {'id': 'medi-p', 'code': 'AMOX500', 'name': 'Amoxicillin 500mg'},
      ]);
    }
    return _paged(const []);
  }
}

void main() {
  testWidgets('a filter remembered from another firm is dropped, not fatal',
      (tester) async {
    final Directory directory =
        Directory.systemTemp.createTempSync('inventory_stale_filter');
    addTearDown(() => directory.deleteSync(recursive: true));
    final DesktopPreferencesService preferences =
        DesktopPreferencesService(directory: directory);
    // Real file IO cannot complete inside the widget test's fake clock, so
    // the seeding runs on the real one.
    await tester.runAsync(() async {
      await preferences.load();
      // What WHOLE01 left behind: its branch, warehouse and product.
      await preferences.saveWorkspaceState('inventory_management', {
        'branch_id': 'whole01-br',
        'warehouse_id': 'whole01-wh',
        'product_id': 'whole01-p',
      });
    });

    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    // Collect what the framework reports rather than failing on the first
    // exception: the question here is the dropdown's value assertion, and
    // a layout overflow elsewhere on the page is another test's business.
    final List<FlutterErrorDetails> reported = [];
    final FlutterExceptionHandler? previous = FlutterError.onError;
    FlutterError.onError = reported.add;
    addTearDown(() => FlutterError.onError = previous);
    final _OtherFirmApi api = _OtherFirmApi();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: InventoryManagementPage(
            api: api,
            preferences: preferences,
            permissions: _permissions(),
            hasActiveFirm: true,
            section: InventorySection.inventory,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    Iterable<String> valueAssertions() => reported
        .map((details) => '${details.exception}')
        .where((message) => message.contains('exactly one item'));
    expect(valueAssertions(), isEmpty);
    // The stale ids are gone from the filter, so the panel counts none.
    expect(find.text('Filters'), findsOneWidget);
    expect(find.textContaining('active)'), findsNothing);
    // And the page can still open its filters and choose this firm's rows.
    await tester.tap(find.text('Filters'));
    await tester.pumpAndSettle();
    expect(valueAssertions(), isEmpty);
    expect(find.text('Warehouse'), findsOneWidget);
  });
}
