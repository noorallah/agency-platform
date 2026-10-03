// BUY-4: a supplier's catalogue on the phase 2 supplier record.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/vendors/supplier_catalogue_section.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _row(String id, String from, {bool current = true}) => <String, dynamic>{
      'id': id,
      'vendor_id': 'v-1',
      'product_id': 'p-1',
      'product_code': 'P001',
      'product_name': 'Widget',
      'supplier_product_code': 'W-9',
      'supplier_product_name': 'Widget nine',
      'unit_price': '12.50',
      'pack_size': '6',
      'minimum_order_quantity': '12',
      'lead_time_days': '4',
      'effective_from': from,
      'remarks': '',
      'is_current': current,
    };

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<String> calls = <String>[];
  final List<Map<String, String>?> queries = <Map<String, String>?>[];
  Json? lastBody;
  String? refuse;
  Map<String, String>? lastFields;

  @override
  Future<PagedResult<Product>> products({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    ProductQuery filters = const ProductQuery(),
  }) async =>
      PagedResult<Product>(items: [
        Product.fromJson(<String, dynamic>{
          'id': 'p-1',
          'code': 'P001',
          'name': 'Widget',
        }),
      ], total: 1);

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
    queries.add(query);
    if (method != 'GET') lastBody = body;
    if (method != 'GET' && refuse != null) throw ApiException(refuse!);
    if (method == 'GET') {
      final bool history = query?['history'] == 'true';
      return <String, dynamic>{
        'data': <Json>[
          _row('r-1', '2026-09-01'),
          if (history) _row('r-0', '2026-01-01', current: false),
        ],
      };
    }
    return <String, dynamic>{'data': _row('r-new', '2026-10-03')};
  }

  @override
  Future<Json> multipartRequest(
    String method,
    String path, {
    required Map<String, String> fields,
    String? fileField,
    String? fileName,
    List<int>? fileBytes,
    String? fileContentType,
    bool authenticated = true,
    bool retrying = false,
  }) async {
    calls.add('$method $path');
    lastFields = fields;
    return <String, dynamic>{
      'data': <String, dynamic>{
        'rows': 1,
        'to_create': 1,
        'to_update': 0,
        'skipped_blank': 0,
        'columns_used': <String>[],
        'columns_ignored': <String>[],
        'issues': <Json>[],
        'imported': false,
      },
    };
  }
}

Future<void> _open(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: SingleChildScrollView(
        child: SupplierCatalogueSection(
          api: api,
          vendorId: 'v-1',
          canManage: true,
          canImport: true,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _fillAndSave(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('catalogue-add')));
  await tester.pumpAndSettle();
  expect(find.text('A change is a new row from a later date'), findsOneWidget);
  await tester.tap(find.byKey(const ValueKey('catalogue-product')));
  await tester.pumpAndSettle();
  await tester.tap(find.text('P001 Widget').last);
  await tester.pumpAndSettle();
  await tester.enterText(find.byKey(const ValueKey('catalogue-price')), '9');
  await tester.enterText(
      find.byKey(const ValueKey('catalogue-supplier-code')), 'W-1');
  await tester.tap(find.byKey(const ValueKey('catalogue-save')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('lists current rows; Show history asks again with history=true',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    expect(find.text('P001 Widget'), findsOneWidget);
    expect(find.text('2026-01-01'), findsNothing);
    expect(api.queries.last, {'history': 'false'});

    await tester.tap(find.byKey(const ValueKey('catalogue-history')));
    await tester.pumpAndSettle();
    expect(api.calls.last, 'GET /api/v1/vendors/v-1/catalogue');
    expect(api.queries.last, {'history': 'true'});
    expect(find.text('2026-01-01'), findsOneWidget);
    expect(find.text('Past'), findsOneWidget);
  });

  testWidgets('Add row posts the body to the catalogue path', (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _fillAndSave(tester);
    expect(api.calls, contains('POST /api/v1/vendors/v-1/catalogue'));
    final String today = DateTime.now().toIso8601String().substring(0, 10);
    expect(api.lastBody, <String, dynamic>{
      'product_id': 'p-1',
      'effective_from': today,
      'supplier_product_code': 'W-1',
      'unit_price': '9',
    });
    expect(find.byKey(const ValueKey('catalogue-save')), findsNothing);
  });

  testWidgets('a 409 keeps the dialog open with the message', (tester) async {
    final _Api api = _Api()..refuse = 'That product already has a row.';
    await _open(tester, api);
    await _fillAndSave(tester);
    expect(find.byKey(const ValueKey('catalogue-save')), findsOneWidget);
    expect(find.text('That product already has a row.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Delete row is off until a row is chosen, then deletes',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    OutlinedButton del() => tester.widget<OutlinedButton>(
        find.byKey(const ValueKey('catalogue-delete')));
    expect(del().onPressed, isNull);
    await tester.tap(find.text('P001 Widget'));
    await tester.pumpAndSettle();
    expect(del().onPressed, isNotNull);
    await tester.tap(find.byKey(const ValueKey('catalogue-delete')));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Delete'));
    await tester.pumpAndSettle();
    expect(api.calls, contains('DELETE /api/v1/vendors/v-1/catalogue/r-1'));
  });

  testWidgets('Import file opens the import dialog', (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await tester.tap(find.byKey(const ValueKey('catalogue-import')));
    await tester.pumpAndSettle();
    expect(find.text('Choose file…'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test('the import check posts to the catalogue import-file path', () async {
    final _Api api = _Api();
    await api.checkSupplierCatalogueImportFile(
      'v-1',
      fileName: 'rows.csv',
      bytes: const <int>[1],
      updateExisting: true,
      apply: false,
    );
    expect(api.calls.single, 'POST /api/v1/vendors/v-1/catalogue/import-file');
    expect(api.lastFields, {'existing': 'update', 'apply': 'false'});
  });
}
