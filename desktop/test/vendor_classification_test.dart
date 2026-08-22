// `vendors.category_id` and `vendors.type_id` have been columns since the
// module was written, and `VendorWrite` has always accepted both. Nothing in
// the desktop could set either: the editor offered no such field, and the two
// master tables they point at had no screen, so there was nothing to point at
// in the first place. Every vendor anybody has created here carries NULL in
// both.
//
// These pin the two halves that close it -- the masters exist in the menu, and
// the form can choose one -- and the rule that keeps the fix from becoming the
// defect it resembles: a dialog that could not load the lists must send
// neither key, because the API replaces what it is given and a null would
// clear a category somebody set.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/vendors/vendor_management_page.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:agency_desktop/ui/workspace/workspace_templates.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['VENDOR_VIEW', 'VENDOR_CREATE', 'VENDOR_UPDATE'],
  }));

Json _vendorJson({String categoryId = '', String typeId = ''}) =>
    <String, dynamic>{
      'id': 'v-1',
      'firm_id': 'firm-1',
      'code': 'V001',
      'name': 'Supplier One',
      'display_name': 'Supplier One',
      'status': 'ACTIVE',
      if (categoryId.isNotEmpty) 'category_id': categoryId,
      if (typeId.isNotEmpty) 'type_id': typeId,
    };

class _VendorApi extends ApiClient {
  _VendorApi({this.rows = const <Json>[], this.optionsFail = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;

  /// Whether the two master lists refuse to load, which is the case the
  /// payload rule exists for.
  final bool optionsFail;
  Json? saved;

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async =>
      PagedResult<Vendor>(
        items: <Vendor>[for (final Json row in rows) Vendor.fromJson(row)],
        total: rows.length,
      );

  @override
  Future<List<AssignmentOption>> options(String resource) async {
    if (optionsFail) {
      throw ApiException('the list is unavailable', statusCode: 503);
    }
    return switch (resource) {
      'vendors/categories' => const <AssignmentOption>[
          AssignmentOption(id: 'cat-raw', label: 'RAW'),
          AssignmentOption(id: 'cat-pack', label: 'PACK'),
        ],
      'vendors/types' => const <AssignmentOption>[
          AssignmentOption(id: 'type-local', label: 'LOCAL'),
        ],
      _ => const <AssignmentOption>[],
    };
  }

  @override
  Future<Vendor> updateVendor(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    saved = data;
    return Vendor.fromJson(_vendorJson());
  }
}

Future<void> _openEditor(WidgetTester tester, _VendorApi api) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: VendorManagementPage(
        api: api,
        permissions: _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.text('V001').first);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
  await tester.tap(find.byTooltip('Edit').first);
  await tester.pumpAndSettle();
}

void main() {
  group('the masters have a screen', () {
    test('both tabs are declared under Masters', () {
      final Set<String> ids =
          ModuleCatalog.byId(AppModule.masters).tabs.map((tab) => tab.id).toSet();

      expect(ids, containsAll(<String>['vendor-categories', 'vendor-types']));
    });

    test('they sit under Vendors, with the vendor list', () {
      Iterable<WorkspaceNavigationNode> flatten(
        Iterable<WorkspaceNavigationNode> input,
      ) sync* {
        for (final WorkspaceNavigationNode node in input) {
          yield node;
          yield* flatten(node.children);
        }
      }

      final List<WorkspaceNavigationNode> nodes =
          ModuleCatalog.navigationChildren(
        AppModule.masters,
        <String>{'vendors', 'vendor-categories', 'vendor-types'},
      );
      final WorkspaceNavigationNode vendors =
          nodes.firstWhere((node) => node.label == 'Vendors');

      expect(vendors.path, isNull, reason: 'it expands, it does not navigate');
      expect(
        flatten(<WorkspaceNavigationNode>[vendors]).map((node) => node.path),
        containsAll(<String>['vendors', 'vendor-categories', 'vendor-types']),
      );
    });
  });

  group('the vendor form can choose one', () {
    testWidgets('both pickers are offered', (tester) async {
      final _VendorApi api = _VendorApi(rows: <Json>[_vendorJson()]);
      await _openEditor(tester, api);

      expect(find.widgetWithText(DropdownButtonFormField<String?>, 'RAW'),
          findsNothing,
          reason: 'nothing chosen yet');
      expect(find.text('Category'), findsOneWidget);
      expect(find.text('Type'), findsOneWidget);
    });

    testWidgets('choosing a category sends its id', (tester) async {
      final _VendorApi api = _VendorApi(rows: <Json>[_vendorJson()]);
      await _openEditor(tester, api);

      await tester.tap(find.text('Category'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('RAW').last);
      await tester.pumpAndSettle();

      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(api.saved, isNotNull);
      expect(api.saved!['category_id'], 'cat-raw');
      expect(api.saved!['type_id'], isNull,
          reason: 'nothing was chosen, and Not set means exactly that');
    });

    testWidgets('a stored id the list does not hold stays selected',
        (tester) async {
      // A category since deactivated, or a list that did not arrive. Dropping
      // it makes `DropdownButtonFormField` assert and the form save as blank.
      final _VendorApi api = _VendorApi(
        rows: <Json>[_vendorJson(categoryId: 'cat-gone')],
      );
      await _openEditor(tester, api);

      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(api.saved!['category_id'], 'cat-gone',
          reason: 'a value the form could not show must survive the save');
    });

    testWidgets('a failed load sends neither key rather than two nulls',
        (tester) async {
      // The API replaces what it is given. Sending null for a field this
      // dialog never managed to populate would clear a category somebody set
      // -- the shape that cost a vendor its addresses in PR #73.
      final _VendorApi api = _VendorApi(
        rows: <Json>[_vendorJson(categoryId: 'cat-raw', typeId: 'type-local')],
        optionsFail: true,
      );
      await _openEditor(tester, api);

      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(api.saved, isNotNull);
      expect(api.saved!.containsKey('category_id'), isFalse);
      expect(api.saved!.containsKey('type_id'), isFalse);
    });
  });
}
