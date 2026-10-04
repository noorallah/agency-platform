// Price revisions with an effective date (MST-2): the product record's
// "Price history" section, the "New rates from..." dialog whose 409 keeps it
// open, and the import of dated rates from a file.

import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/file_import.dart';
import 'package:agency_desktop/models/price_revision.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/products/price_revisions_section.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/import_file.dart';

const ProductMetadataRecord _metadata = ProductMetadataRecord(
  profileCode: 'WHOLESALE',
  features: [],
  categories: [],
  taxProfiles: [],
  requiredAttributeDefinitionIds: [],
  optionalAttributeDefinitionIds: [],
);

final Product _product = Product.fromJson(const {
  'id': 'product-1',
  'code': 'PROD-001',
  'name': 'Pain Relief',
  'product_type': 'STOCK_ITEM',
  'status': 'ACTIVE',
  'unit': 'BOX',
  'purchase_price': '80',
  'selling_price': '100',
  'mrp': '120',
  'stock_on_hand': '42',
});

PriceRevision _revision(String id, String from,
        {String selling = '', bool current = false}) =>
    PriceRevision.fromJson({
      'id': id,
      'product_id': 'product-1',
      'effective_from': from,
      'selling_price': selling,
      'purchase_price': '',
      'mrp': '',
      'remarks': 'r-$id',
      'is_current': current,
    });

class _Recorder {
  final List<Json> added = [];
  final List<String> deleted = [];
  bool refuse = false;
  List<PriceRevision> rows = [
    _revision('new', '2026-10-01', selling: '110', current: true),
    _revision('old', '2026-01-01', selling: '100'),
  ];

  PriceRevisionActions get actions => PriceRevisionActions(
        load: (productId) async => rows,
        add: (productId, body) async {
          if (refuse) {
            throw const ApiException(
                'Rates from 2026-10-01 already exist for this product.');
          }
          added.add(body);
          return _revision('x', body['effective_from'] as String);
        },
        delete: (productId, revisionId) async => deleted.add(revisionId),
      );
}

Future<void> _pumpEditor(WidgetTester tester, _Recorder recorder) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: ProductWorkspaceDialog(
        mode: ProductDialogMode.edit,
        product: _product,
        categories: const [],
        uoms: const [],
        definitions: const [],
        metadata: _metadata,
        initialTab: 'general',
        onMetadataForCategory: (_) async => _metadata,
        onSave: (payload) async => _product,
        onTabChanged: (_) {},
        priceRevisions: recorder.actions,
        canManagePriceRevisions: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _openNewRates(WidgetTester tester) async {
  final Finder add = find.byKey(const ValueKey('price-revision-add'));
  await tester.ensureVisible(add);
  await tester.pumpAndSettle();
  await tester.tap(add);
  await tester.pumpAndSettle();
}

class _ImportApi extends ApiClient {
  _ImportApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<String> paths = [];
  final List<Map<String, String>> fields = [];

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
    int? expectedVersion,
  }) async {
    paths.add(path);
    this.fields.add(fields);
    return {
      'data': {
        'rows': 2,
        'to_create': 2,
        'to_update': 0,
        'skipped_blank': 0,
        'columns_used': ['ProductCode'],
        'columns_ignored': [],
        'issues': [],
        'imported': fields['apply'] == 'true',
      },
    };
  }

  @override
  Future<ImportPreview> importPreview({
    required String kind,
    required String fileName,
    required List<int> bytes,
  }) async =>
      throw const ApiException('no preview');
}

void main() {
  testWidgets('the history lists every row and marks the one in force',
      (tester) async {
    await _pumpEditor(tester, _Recorder());
    await tester.ensureVisible(find.text('2026-10-01'));
    expect(find.text('Price history'), findsWidgets);
    expect(find.text('2026-10-01'), findsOneWidget);
    expect(find.text('2026-01-01'), findsOneWidget);
    expect(find.text('110'), findsOneWidget);
    expect(find.text('In force'), findsOneWidget);
    expect(find.text('r-new'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('new rates post only what was typed, with the date',
      (tester) async {
    final _Recorder recorder = _Recorder();
    await _pumpEditor(tester, recorder);
    await _openNewRates(tester);
    expect(find.text('Blank keeps that price as it is'), findsNWidgets(3));

    await tester.enterText(
        find.byKey(const ValueKey('price-revision-selling')), '125');
    await tester.enterText(
        find.byKey(const ValueKey('price-revision-remarks')), 'Festival');
    await tester.tap(find.byKey(const ValueKey('price-revision-save')));
    await tester.pumpAndSettle();

    expect(recorder.added, hasLength(1));
    final Json body = recorder.added.single;
    expect(body['selling_price'], '125');
    expect(body['remarks'], 'Festival');
    expect(body.containsKey('purchase_price'), isFalse);
    expect(body.containsKey('mrp'), isFalse);
    expect(body['effective_from'], matches(RegExp(r'^\d{4}-\d{2}-\d{2}$')));
    expect(find.byType(NewRatesDialog), findsNothing,
        reason: 'closed after a successful save');
  });

  testWidgets('a dialog with no price says so and posts nothing',
      (tester) async {
    final _Recorder recorder = _Recorder();
    await _pumpEditor(tester, recorder);
    await _openNewRates(tester);
    await tester.tap(find.byKey(const ValueKey('price-revision-save')));
    await tester.pumpAndSettle();
    expect(find.text('Enter at least one price.'), findsOneWidget);
    expect(recorder.added, isEmpty);
  });

  testWidgets('a 409 keeps the dialog open with the message and the typing',
      (tester) async {
    final _Recorder recorder = _Recorder()..refuse = true;
    await _pumpEditor(tester, recorder);
    await _openNewRates(tester);
    await tester.enterText(
        find.byKey(const ValueKey('price-revision-selling')), '125');
    await tester.tap(find.byKey(const ValueKey('price-revision-save')));
    await tester.pumpAndSettle();

    expect(find.byType(NewRatesDialog), findsOneWidget);
    expect(find.byKey(const ValueKey('save-error-banner')), findsOneWidget);
    expect(find.textContaining('already exist'), findsOneWidget);
    expect(find.text('125'), findsOneWidget);
  });

  testWidgets('deleting a row asks first, then removes it', (tester) async {
    final _Recorder recorder = _Recorder();
    await _pumpEditor(tester, recorder);
    await tester.ensureVisible(find.text('2026-01-01'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('2026-01-01'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('price-revision-delete')));
    await tester.pumpAndSettle();
    expect(find.text('Delete these rates?'), findsOneWidget);
    expect(recorder.deleted, isEmpty);

    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    expect(recorder.deleted, ['old']);
  });

  testWidgets('import posts the file to the price revision path',
      (tester) async {
    tester.view.physicalSize = const Size(800, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _ImportApi api = _ImportApi();
    final Directory dir = Directory.systemTemp.createTempSync('price-rev');
    final File file = File('${dir.path}/rates.csv')
      ..writeAsStringSync('ProductCode,EffectiveFrom,SellingPrice\nA,2026-10-01,5\n');
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: TextButton(
            onPressed: () => showDialog<void>(
              context: context,
              builder: (context) => PriceRevisionImportDialog(
                api: api,
                pickFileOverride: () async => XFile(file.path),
              ),
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text('Template (Excel)'), findsNothing);
    expect(find.text('Template (CSV)'), findsOneWidget);

    await chooseImportFile(tester);
    await tester.ensureVisible(find.text('Check file'));
    await tester.tap(find.text('Check file'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Import'));
    await tester.pumpAndSettle();

    expect(api.paths, [
      '/api/v1/products/price-revisions/import-file',
      '/api/v1/products/price-revisions/import-file',
    ]);
    expect(api.fields.map((f) => f['apply']), ['false', 'true']);
  });
}
