// A supplier's GST type (backlog 78 row 2, decision A37): the form declares it,
// a refusal keeps the page open, a blank type reads off the GSTIN, and the
// bill editor says so when the supplier charges no GST.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/vendors/vendor_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['VENDOR_VIEW', 'VENDOR_CREATE', 'VENDOR_UPDATE'],
  }));

Json _vendorJson({String? type, String gstin = ''}) => <String, dynamic>{
      'id': 'v-1',
      'firm_id': 'firm-1',
      'code': 'V001',
      'name': 'Supplier One',
      'display_name': 'Supplier One',
      'status': 'ACTIVE',
      'gstin': gstin,
      'gst_registration_type': type,
    };

class _VendorApi extends ApiClient {
  _VendorApi(this.rows, {this.refusal})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;
  final ApiException? refusal;
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
  Future<List<GeoPlaceRecord>> geoPlaces(
    GeoLevel level, {
    String parentId = '',
  }) async =>
      const <GeoPlaceRecord>[];

  @override
  Future<Vendor> updateVendor(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    saved = data;
    final ApiException? refused = refusal;
    if (refused != null) throw refused;
    return Vendor.fromJson(_vendorJson());
  }
}

Future<void> _openEditor(WidgetTester tester, _VendorApi api) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
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

Future<void> _chooseComposition(WidgetTester tester) async {
  final Finder dropdown = find.byKey(const ValueKey('vendor-gst-type'));
  await tester.ensureVisible(dropdown);
  await tester.pumpAndSettle();
  await tester.tap(dropdown);
  await tester.pumpAndSettle();
  await tester.tap(find.text('Composition').last);
  await tester.pumpAndSettle();
}

class _InvoiceApi extends ApiClient {
  _InvoiceApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  @override
  Future<Json> documentPage(
    String resource, {
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> additionalQuery = const {},
  }) async =>
      {'data': const <Json>[]};
}

void main() {
  testWidgets('the form sends the declared GST type', (tester) async {
    final _VendorApi api = _VendorApi(<Json>[_vendorJson()]);
    await _openEditor(tester, api);
    expect(find.text(vendorGstTypeNotSet), findsWidgets);

    await _chooseComposition(tester);
    expect(find.text(vendorGstTypeLabels['COMPOSITION']!), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('vendor-save')));
    await tester.pumpAndSettle();
    expect(api.saved?['gst_registration_type'], 'COMPOSITION');
    expect(tester.takeException(), isNull);
  });

  testWidgets("a refusal keeps the page open with the server's message", (
    tester,
  ) async {
    final _VendorApi api = _VendorApi(
      <Json>[_vendorJson()],
      refusal: ApiException('A Composition supplier must have a GST number'),
    );
    await _openEditor(tester, api);
    await _chooseComposition(tester);
    await tester.tap(find.byKey(const ValueKey('vendor-save')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('save-error-banner')), findsOneWidget);
    expect(find.textContaining('must have a GST number'), findsOneWidget);
    // Still open, and what was chosen is still chosen.
    expect(find.byKey(const ValueKey('vendor-save')), findsOneWidget);
    expect(find.text('Composition'), findsWidgets);
  });

  testWidgets('a blank type is shown as what the GSTIN implies', (
    tester,
  ) async {
    expect(
      Vendor.fromJson(_vendorJson(gstin: '33ABCDE1234F1Z5')).gstTypeLabel,
      'Regular (from GSTIN)',
    );
    expect(Vendor.fromJson(_vendorJson()).gstTypeLabel,
        'Unregistered (from GSTIN)');
    expect(Vendor.fromJson(_vendorJson(type: 'SEZ')).gstTypeLabel,
        vendorGstTypeLabels['SEZ']);

    final _VendorApi api = _VendorApi(
      <Json>[_vendorJson(gstin: '33ABCDE1234F1Z5')],
    );
    await _openEditor(tester, api);
    expect(find.text('Regular (from GSTIN)'), findsWidgets);
  });

  testWidgets('the bill editor says a composition supplier charges no GST', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Phase2Scope(
            child: PurchaseInvoiceEditorDialog(
              api: _InvoiceApi(),
              receipts: const [],
              products: [
                Product.fromJson({
                  'id': 'prod-1',
                  'code': 'SKU-1',
                  'name': 'Amoxicillin 500mg',
                }),
              ],
              stages: const PurchaseWorkflowSettings(
                purchaseOrderStage: false,
                goodsReceiptStage: false,
                isConfigured: true,
              ),
              vendors: [
                Vendor.fromJson({
                  'id': 'vendor-1',
                  'code': 'V-001',
                  'name': 'Regular Co',
                  'display_name': 'Regular Co',
                  'gst_registration_type': 'REGULAR',
                }),
                Vendor.fromJson({
                  'id': 'vendor-2',
                  'code': 'V-002',
                  'name': 'Small Trader',
                  'display_name': 'Small Trader',
                  'gst_registration_type': 'COMPOSITION',
                }),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    const Key note = ValueKey('purchase-invoice-no-gst-note');
    expect(find.byKey(note), findsNothing);

    await tester.tap(find.byKey(const ValueKey('purchase-invoice-vendor')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Regular Co').last);
    await tester.pumpAndSettle();
    expect(find.byKey(note), findsNothing);

    await tester.tap(find.byKey(const ValueKey('purchase-invoice-vendor')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Small Trader').last);
    await tester.pumpAndSettle();
    expect(
      find.text('This supplier charges no GST; the bill will carry no tax.'),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });
}
