// Expiry rules per product (STK-5).
//
// The product and category forms carry three optional day counts (blank
// inherits, sent as null) and the Expiry Monitor lists the batches that are
// inside their return-to-supplier window.

import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/inventory/batch_management_page.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/access_token.dart';

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

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
    if (method == 'POST' && path == '/api/v1/products/categories') {
      categoryBody = body;
      return {'data': {'id': 'cat-new', ...?body}};
    }
    return {'data': const <dynamic>[]};
  }

  @override
  Future<PagedResult<BatchRecord>> batches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BatchQuery filters = const BatchQuery(),
  }) async =>
      PagedResult<BatchRecord>(items: <BatchRecord>[], total: 0);

  @override
  Future<ExpiryDashboardRecord> expiryDashboard() async =>
      const ExpiryDashboardRecord(
        expiredToday: 0,
        expireIn7Days: 0,
        expireIn30Days: 0,
        totalExpired: 0,
        quarantine: 0,
        recalled: 0,
      );

  @override
  Future<List<ReturnDueRecord>> batchesReturnsDue() async => [
        ReturnDueRecord.fromJson(const {
          'batch_id': 'b-1',
          'batch_number': 'LOT-77',
          'product_id': 'p-1',
          'product_code': 'PCM500',
          'product_name': 'Paracetamol 500',
          'vendor_id': 'v-1',
          'expiry_date': '2026-11-20',
          'days_to_expiry': 48,
          'quantity': '120.000',
        }),
      ];
}

const ProductMetadataRecord _metadata = ProductMetadataRecord(
  profileCode: 'WHOLESALE',
  features: [],
  categories: [],
  taxProfiles: [],
  requiredAttributeDefinitionIds: [],
  optionalAttributeDefinitionIds: [],
);

Future<Json?> _saveProduct(
  WidgetTester tester,
  Map<String, dynamic> json, {
  Future<void> Function()? edit,
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  Json? sent;
  final Product product = Product.fromJson({
    'id': 'product-1',
    'code': 'PROD-001',
    'name': 'Pain Relief',
    'product_type': 'STOCK_ITEM',
    'status': 'ACTIVE',
    'unit': 'BOX',
    ...json,
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
        metadata: _metadata,
        initialTab: 'general',
        onMetadataForCategory: (_) async => _metadata,
        onSave: (payload) async {
          sent = payload;
          return product;
        },
        onTabChanged: (_) {},
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester
      .ensureVisible(find.byKey(const ValueKey('product-expiry-stop-sale')));
  if (edit != null) await edit();
  await tester.tap(find.byKey(const ValueKey('product-save')));
  await tester.pumpAndSettle();
  return sent;
}

void main() {
  testWidgets('the product form sends the three expiry windows',
      (tester) async {
    final Json? sent = await _saveProduct(tester, const {}, edit: () async {
      expect(find.text('Stop selling (days before expiry)'), findsOneWidget);
      expect(find.text("Blank takes the category's, then the firm's"),
          findsNWidgets(3));
      await tester.enterText(
          find.byKey(const ValueKey('product-expiry-stop-sale')), '30');
      await tester.enterText(
          find.byKey(const ValueKey('product-expiry-alert')), '90');
      await tester.enterText(
          find.byKey(const ValueKey('product-expiry-return')), '60');
    });
    expect(sent?['expiry_stop_sale_days'], 30);
    expect(sent?['expiry_alert_days'], 90);
    expect(sent?['expiry_return_days'], 60);
  });

  testWidgets('a blank box is sent as null, and a stored value is shown',
      (tester) async {
    final Json? sent = await _saveProduct(
      tester,
      const {'expiry_stop_sale_days': 15, 'expiry_alert_days': 45},
      edit: () async {
        expect(
          tester
              .widget<TextField>(
                  find.byKey(const ValueKey('product-expiry-alert')))
              .controller!
              .text,
          '45',
        );
        await tester.enterText(
            find.byKey(const ValueKey('product-expiry-stop-sale')), '');
      },
    );
    expect(sent!.containsKey('expiry_stop_sale_days'), isTrue);
    expect(sent['expiry_stop_sale_days'], isNull);
    expect(sent['expiry_alert_days'], 45);
    expect(sent['expiry_return_days'], isNull);
  });

  testWidgets('the category form sends the three expiry windows',
      (tester) async {
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
            PermissionService()
              ..applyAccessToken(accessTokenFor(
                  const ['PRODUCT_VIEW', 'PRODUCT_UPDATE'])),
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
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Stop selling (days before expiry)'),
        '20');
    await tester.enterText(
        find.widgetWithText(
            TextFormField, 'Return to supplier (days before expiry)'),
        '75');
    await tester.tap(find.text('Save & Close'));
    await tester.pumpAndSettle();

    expect(api.categoryBody?['expiry_stop_sale_days'], 20);
    expect(api.categoryBody?['expiry_return_days'], 75);
    expect(api.categoryBody!.containsKey('expiry_alert_days'), isTrue);
    expect(api.categoryBody?['expiry_alert_days'], isNull);
  });

  testWidgets('the expiry monitor lists the batches to return',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final Directory temp = Directory.systemTemp.createTempSync('expiry-rules');
    addTearDown(() => temp.deleteSync(recursive: true));
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: BatchManagementPage(
          api: _Api(),
          preferences: DesktopPreferencesService(directory: temp),
          permissions: PermissionService()
            ..applyAccessToken(accessTokenFor(const ['BATCH_VIEW'])),
          hasActiveFirm: true,
          section: BatchSerialSection.expiryMonitor,
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Return to supplier now'), findsOneWidget);
    expect(find.text('PCM500 - Paracetamol 500'), findsOneWidget);
    expect(find.textContaining('LOT-77'), findsOneWidget);
    expect(find.text('Qty 120.000'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
