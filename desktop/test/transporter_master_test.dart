// SG-5: the transporter master, and the carrier a delivery note picks from it.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/inventory.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/transporter.dart';
import 'package:agency_desktop/ui/delivery_notes/delivery_note_editor_dialog.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const List<Map<String, dynamic>> _carriers = [
  {
    'id': 'tr-1',
    'name': 'Speedy Carriers',
    'gstin': '27AAAPL1234C1ZV',
    'transporter_ref': '27AAAPL1234C1ZV',
    'phone': '9822000000',
    'default_mode': 'RAIL',
    'is_active': true,
    'version': 1,
  },
  {
    'id': 'tr-2',
    'name': 'Blue Dart Freight',
    'gstin': null,
    'transporter_ref': null,
    'phone': null,
    'default_mode': null,
    'is_active': true,
    'version': 1,
  },
];

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? sent;
  int transporterReads = 0;

  @override
  Future<List<TransporterRecord>> transporters({
    bool activeOnly = false,
  }) async {
    transporterReads++;
    return [for (final c in _carriers) TransporterRecord.fromJson(c)];
  }

  @override
  Future<PagedResult<TransporterRecord>> transportersPage({
    int page = 1,
    String search = '',
    String sortBy = 'name',
    bool descending = false,
  }) async {
    final rows = await transporters();
    return PagedResult(items: rows, total: rows.length);
  }

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
      const {'data': <dynamic>[]};

  @override
  Future<PagedResult<InventoryRecord>> inventory({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    InventoryQuery filters = const InventoryQuery(),
  }) async =>
      const PagedResult<InventoryRecord>(items: [], total: 0);

  @override
  Future<Json> create(String resource, Json body) async {
    sent = body;
    return {
      'data': {'id': 'dn-1', 'delivery_note_number': 'DN-1', 'status': 'DRAFT'}
    };
  }
}

void main() {
  test('a transporter is written with its id, mode and active flag', () {
    final definition = transporterDefinition(_Api(), PermissionService());
    expect(definition.resource, 'delivery-notes/transporters');
    expect(
      definition.payload(
        {
          'name': 'Speedy',
          'gstin': '',
          'transporter_ref': '',
          'phone': '98',
          'default_mode': 'ROAD',
          'is_active': true,
        },
        true,
      ),
      {
        'name': 'Speedy',
        'gstin': null,
        'transporter_ref': null,
        'phone': '98',
        'default_mode': 'ROAD',
        'is_active': true,
      },
    );
  });

  testWidgets('the list shows the transporters the API returns',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final PermissionService permissions = PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': <String>['SALES_VIEW', 'SALES_UPDATE'],
      }));
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: ResourceManagementPage<TransporterRecord>(
          api: api,
          definition: transporterDefinition(api, permissions),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Speedy Carriers'), findsOneWidget);
    expect(find.text('Blue Dart Freight'), findsOneWidget);
    expect(find.text('Rail'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  group('the delivery note editor', () {
    Future<void> open(WidgetTester tester, _Api api) async {
      tester.view.physicalSize = const Size(1600, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Phase2Scope(
            child: DeliveryNoteEditorDialog(
              api: api,
              salesOrders: [
                <String, dynamic>{
                  'id': 'so-1',
                  'order_number': 'SO-2026-000001',
                  'order_date': '2026-08-01',
                  'customer_id': 'c1',
                  'warehouse_id': 'wh-1',
                  'status': 'APPROVED',
                  'lines': <Json>[
                    <String, dynamic>{
                      'id': 'so-line-1',
                      'line_number': 1,
                      'product_id': 'prod-1',
                      'description': 'Amoxicillin 500mg',
                      'quantity': '10',
                      'reserved_quantity': '10',
                      'unit_price': '40',
                      'sales_uom_id': 'uom-box',
                      'warehouse_id': 'wh-1',
                    },
                  ],
                },
              ],
              warehouses: [
                WarehouseRecord.fromJson(
                    {'id': 'wh-1', 'code': 'MAIN', 'name': 'Main'}),
              ],
              products: [
                Product.fromJson({
                  'id': 'prod-1',
                  'code': 'SKU-1',
                  'name': 'Amoxicillin 500mg',
                }),
              ],
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('delivery-note-order')));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('SO-2026-000001').last);
      await tester.pumpAndSettle();
    }

    testWidgets('choosing a carrier fills the boxes and is sent',
        (tester) async {
      final _Api api = _Api();
      await open(tester, api);
      expect(api.transporterReads, 1);
      await tester
          .tap(find.byKey(const ValueKey('delivery-note-transporter')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Speedy Carriers').last);
      await tester.pumpAndSettle();
      await tester
          .tap(find.byKey(const ValueKey('delivery-note-freight-terms')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('To pay').last);
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<EditableText>(find.descendant(
              of: find.byKey(
                  const ValueKey('delivery-note-transporter-gstin')),
              matching: find.byType(EditableText),
            ))
            .controller
            .text,
        '27AAAPL1234C1ZV',
      );
      await tester.tap(find.byKey(const ValueKey('delivery-note-save')));
      await tester.pumpAndSettle();
      expect(api.sent!['transporter_id'], 'tr-1');
      expect(api.sent!['freight_terms'], 'TO_PAY');
      expect(api.sent!['transporter_name'], 'Speedy Carriers');
      expect(api.sent!['transporter_gstin'], '27AAAPL1234C1ZV');
      expect(api.sent!['transport_mode'], 'RAIL');
      expect(api.transporterReads, 1);
    });

    testWidgets('with no carrier chosen both are sent as null',
        (tester) async {
      final _Api api = _Api();
      await open(tester, api);
      await tester.tap(find.byKey(const ValueKey('delivery-note-save')));
      await tester.pumpAndSettle();
      expect(api.sent!.containsKey('transporter_id'), isTrue);
      expect(api.sent!['transporter_id'], isNull);
      expect(api.sent!['freight_terms'], isNull);
    });
  });
}
