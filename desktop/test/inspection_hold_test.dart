// The quality inspection hold (BUY-9).
//
// The product and category forms carry "Inspect on receipt"; the Quality
// inspection screen lists what waits and posts pass / reject to the line's
// own path; a refusal keeps the dialog open with the server's message.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:agency_desktop/ui/purchases/quality_inspection_page.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> perms) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': perms,
  }));

Json _row(String line, String product, {String status = 'PENDING'}) => {
      'goods_receipt_id': 'gr-1',
      'grn_number': 'GRN-0001',
      'receipt_date': '2026-10-02',
      'vendor_id': 'v-1',
      'vendor_name': 'Sharma Pharma',
      'line_id': line,
      'line_number': 1,
      'product_id': 'p-$line',
      'product_code': 'P$line',
      'product_name': product,
      'batch_number': 'B1',
      'warehouse_id': 'w-1',
      'quantity': '10.000',
      'status': status,
      'passed_quantity': status == 'DONE' ? '8.000' : null,
      'rejected_quantity': status == 'DONE' ? '2.000' : null,
      'rejected_action': status == 'DONE' ? 'RETURN' : null,
    };

class _Api extends ApiClient {
  _Api({this.refuse = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool refuse;
  final List<String> requested = <String>[];
  final List<Map<String, String>?> queries = [];
  Json? posted;
  Json? categoryBody;

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
    requested.add('$method $path');
    if (method == 'POST' && path.endsWith('/inspection')) {
      posted = body;
      if (refuse) {
        throw const ApiException(
          'Passed and rejected must add up to 10.',
          statusCode: 422,
        );
      }
      return {'data': _row('l-1', 'Paracetamol', status: 'DONE')};
    }
    if (method == 'POST' && path == '/api/v1/products/categories') {
      categoryBody = body;
      return {'data': {'id': 'cat-new', ...?body}};
    }
    if (method == 'GET' && path == '/api/v1/goods-receipts/inspections') {
      queries.add(query);
      return {
        'data': query?['status'] == 'DONE'
            ? [_row('l-3', 'Ibuprofen', status: 'DONE')]
            : [_row('l-1', 'Paracetamol'), _row('l-2', 'Cough syrup')],
      };
    }
    if (path == '/api/v1/products/categories') {
      return {
        'data': [
          {
            'id': 'cat-1',
            'code': 'MEDS',
            'name': 'Medicines',
            'level': 1,
            'path': 'MEDS',
            'is_active': true,
            'inspection_required': true,
          },
        ],
      };
    }
    return {'data': const <dynamic>[]};
  }
}

Future<void> _pumpPage(
  WidgetTester tester,
  _Api api, {
  List<String> perms = const ['PURCHASE_VIEW', 'PURCHASE_INSPECT'],
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: QualityInspectionPage(
        api: api,
        preferences: DesktopPreferencesService(
          directory: Directory.systemTemp.createTempSync('inspection-hold'),
        ),
        permissions: _permissions(perms),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _openInspect(WidgetTester tester) async {
  await tester.tap(find.text('Paracetamol').first);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('selection-inspect')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the product form sends inspection_required', (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    Json? sent;
    final Product product = Product.fromJson(const {
      'id': 'product-1',
      'code': 'PROD-001',
      'name': 'Pain Relief',
      'product_type': 'STOCK_ITEM',
      'status': 'ACTIVE',
      'unit': 'BOX',
    });
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: ProductWorkspaceDialog(
          mode: ProductDialogMode.edit,
          product: product,
          categories: const [],
          uoms: const [],
          definitions: const [],
          metadata: const ProductMetadataRecord(
            profileCode: 'WHOLESALE',
            features: [],
            categories: [],
            taxProfiles: [],
            requiredAttributeDefinitionIds: [],
            optionalAttributeDefinitionIds: [],
          ),
          initialTab: 'general',
          onMetadataForCategory: (_) async => const ProductMetadataRecord(
            profileCode: 'WHOLESALE',
            features: [],
            categories: [],
            taxProfiles: [],
            requiredAttributeDefinitionIds: [],
            optionalAttributeDefinitionIds: [],
          ),
          onSave: (payload) async {
            sent = payload;
            return product;
          },
          onTabChanged: (_) {},
        ),
      ),
    ));
    await tester.pumpAndSettle();

    final Finder box = find.byKey(const ValueKey('product-inspection-required'));
    await tester.ensureVisible(box);
    expect(find.text('Received goods wait in quarantine until passed'),
        findsOneWidget);
    await tester.tap(box);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('product-save')));
    await tester.pumpAndSettle();

    expect(sent?['inspection_required'], isTrue);
  });

  testWidgets('the category form sends inspection_required', (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: ResourceManagementPage<ProductCategoryRecord>(
          api: api,
          definition: productCategoryDefinition(
            api,
            _permissions(const ['PRODUCT_VIEW', 'PRODUCT_UPDATE']),
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'New').hitTestable());
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Category code'), 'MEDS2');
    await tester.enterText(find.widgetWithText(TextFormField, 'Name'), 'Meds');
    await tester.tap(find.widgetWithText(SwitchListTile, 'Inspect on receipt'));
    await tester.pumpAndSettle();
    expect(find.text('Received goods wait in quarantine until passed'),
        findsOneWidget);
    await tester.tap(find.text('Save & Close'));
    await tester.pumpAndSettle();

    final List<String> writes =
        api.requested.where((r) => r.startsWith('POST')).toList();
    expect(writes, ['POST /api/v1/products/categories']);
    expect(api.categoryBody?['inspection_required'], isTrue);
  });

  testWidgets('the grid lists pending rows and toggles to done',
      (tester) async {
    final _Api api = _Api();
    await _pumpPage(tester, api);

    expect(api.queries.first?['status'], 'PENDING');
    expect(find.text('Paracetamol'), findsOneWidget);
    expect(find.text('Cough syrup'), findsOneWidget);
    expect(find.text('Sharma Pharma'), findsWidgets);

    await tester.tap(find.byKey(const ValueKey('inspection-status-filter')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Done').last);
    await tester.pumpAndSettle();

    expect(api.queries.last?['status'], 'DONE');
    expect(find.text('Ibuprofen'), findsOneWidget);
    expect(find.text('Kept for return'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('without the inspect permission there is no Inspect action',
      (tester) async {
    await _pumpPage(tester, _Api(), perms: const ['PURCHASE_VIEW']);
    await tester.tap(find.text('Paracetamol').first);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('selection-inspect')), findsNothing);
  });

  testWidgets('inspecting posts the split to the line path, prefilled in full',
      (tester) async {
    final _Api api = _Api();
    await _pumpPage(tester, api);
    await _openInspect(tester);

    expect(
      tester
          .widget<TextField>(find.byKey(const ValueKey('inspection-passed')))
          .controller!
          .text,
      '10',
    );
    await tester.enterText(
        find.byKey(const ValueKey('inspection-passed')), '8');
    await tester.enterText(
        find.byKey(const ValueKey('inspection-rejected')), '2');
    await tester.tap(find.byKey(const ValueKey('inspection-action')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Keep for return to supplier').last);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('inspection-remarks')), 'Cracked seals');
    await tester.tap(find.byKey(const ValueKey('inspection-save')));
    await tester.pumpAndSettle();

    expect(api.requested,
        contains('POST /api/v1/goods-receipts/gr-1/lines/l-1/inspection'));
    expect(api.posted, <String, dynamic>{
      'passed_quantity': '8',
      'rejected_quantity': '2',
      'rejected_action': 'RETURN',
      'remarks': 'Cracked seals',
    });
    expect(find.byKey(const ValueKey('inspection-save')), findsNothing);
  });

  testWidgets('rejecting without saying what happens is stopped here',
      (tester) async {
    final _Api api = _Api();
    await _pumpPage(tester, api);
    await _openInspect(tester);
    await tester.enterText(
        find.byKey(const ValueKey('inspection-passed')), '8');
    await tester.enterText(
        find.byKey(const ValueKey('inspection-rejected')), '2');
    await tester.tap(find.byKey(const ValueKey('inspection-save')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('inspection-problem')), findsOneWidget);
    expect(api.posted, isNull);
  });

  testWidgets('a refusal keeps the dialog open with the message',
      (tester) async {
    final _Api api = _Api(refuse: true);
    await _pumpPage(tester, api);
    await _openInspect(tester);
    await tester.tap(find.byKey(const ValueKey('inspection-save')));
    await tester.pumpAndSettle();

    expect(api.posted?['rejected_action'], isNull);
    expect(find.byKey(const ValueKey('inspection-save')), findsOneWidget);
    expect(find.text('Passed and rejected must add up to 10.'),
        findsOneWidget);
  });
}
