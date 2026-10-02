// Every file import maps the file's columns onto the template's (B3): the
// server's suggestion is preselected, a change is what Check sends, a
// required column nobody maps blocks Check, and a mapping can be saved and
// loaded again.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/file_import.dart';
import 'package:agency_desktop/ui/products/product_import_dialog.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';


class _Api extends ApiClient {
  _Api({this.saved = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<ImportMapping> saved;
  final List<Map<String, String?>?> sent = <Map<String, String?>?>[];
  final List<String> savedPosts = <String>[];
  final List<Map<String, String?>> savedMappings = <Map<String, String?>>[];
  final List<String> kinds = <String>[];

  @override
  Future<ImportPreview> importPreview({
    required String kind,
    required String fileName,
    required List<int> bytes,
  }) async {
    kinds.add(kind);
    return const ImportPreview(
      fileHeadings: ['Item Code', 'Item Name', 'Colour'],
      columns: [
        ImportColumn(
          heading: 'code',
          required: true,
          takes: 'text',
          example: 'A',
        ),
        ImportColumn(
          heading: 'name',
          required: true,
          takes: 'text',
          example: 'B',
        ),
        ImportColumn(
          heading: 'brand',
          required: false,
          takes: 'text',
          example: 'C',
        ),
      ],
      suggested: {'Item Code': 'code', 'Item Name': null, 'Colour': null},
      sampleRows: [
        ['A1', 'Apple', 'Red'],
      ],
    );
  }

  @override
  Future<List<ImportMapping>> importMappings(String kind) async => saved;

  final List<String> deleted = <String>[];

  @override
  Future<void> deleteImportMapping(String id) async => deleted.add(id);

  @override
  Future<ImportMapping> saveImportMapping(
    String kind,
    String name,
    Map<String, String?> mapping,
  ) async {
    savedPosts.add(name);
    savedMappings.add(mapping);
    return ImportMapping(id: 'm-new', kind: kind, name: name, mapping: mapping);
  }

  @override
  Future<FileImportReport> checkProductImportFile({
    required String fileName,
    required List<int> bytes,
    required bool updateExisting,
    required bool apply,
    Map<String, String?>? mapping,
  }) async {
    sent.add(mapping);
    return const FileImportReport(
      rows: 1,
      toCreate: 1,
      toUpdate: 0,
      skippedBlank: 0,
      columnsUsed: ['code', 'name'],
      columnsIgnored: [],
      issues: [],
      imported: false,
    );
  }
}

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(
    'h.${base64Url.encode(utf8.encode(jsonEncode({
              'roles': <String>['user'],
              'permissions': <String>['PRODUCT_IMPORT'],
            }))).replaceAll('=', '')}.s',
  );

/// Opens the dialog and chooses the file. Check is disabled while the preview
/// is loading and on a blocked mapping, so this waits on the preview itself.
Future<void> _open(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1000, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory dir = Directory.systemTemp.createTempSync('mapping-import');
  final File file = File('${dir.path}/items.csv')
    ..writeAsStringSync('Item Code,Item Name,Colour\nA1,Apple,Red\n');
  await tester.pumpWidget(
    MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: TextButton(
            onPressed: () => showDialog<FileImportReport>(
              context: context,
              builder: (context) => ProductImportDialog(
                api: api,
                permissions: _permissions(),
                pickFileOverride: () async => XFile(file.path),
              ),
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  await tester.runAsync(() async {
    await tester.tap(find.text('Choose file…'));
  });
  final Stopwatch elapsed = Stopwatch()..start();
  while (find.byKey(const ValueKey<String>('import-map-Item Code')).evaluate().isEmpty &&
      elapsed.elapsed < const Duration(seconds: 20)) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 20)),
    );
    await tester.pump();
  }
  await tester.pumpAndSettle();
}

String? _value(WidgetTester tester, String heading) => tester
    .widget<DropdownButton<String?>>(
      find.byKey(ValueKey<String>('import-map-$heading')),
    )
    .value;

Future<void> _choose(WidgetTester tester, String heading, String label) async {
  final Finder box = find.byKey(ValueKey<String>('import-map-$heading'));
  await tester.ensureVisible(box);
  await tester.tap(box);
  await tester.pumpAndSettle();
  await tester.tap(find.text(label).last);
  await tester.pumpAndSettle();
}

bool _checkEnabled(WidgetTester tester) => tester
    .widget<ButtonStyleButton>(
      find.ancestor(
        of: find.text('Check file'),
        matching: find.byWidgetPredicate((w) => w is ButtonStyleButton),
      ),
    )
    .enabled;

void main() {
  wireTests();
  testWidgets('the suggestion is preselected and a required gap blocks Check',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);

    expect(api.kinds, ['products']);
    expect(_value(tester, 'Item Code'), 'code');
    expect(_value(tester, 'Item Name'), isNull);
    expect(
      find.byKey(const ValueKey<String>('import-mapping-missing')),
      findsOneWidget,
    );
    expect(_checkEnabled(tester), isFalse);
  });

  testWidgets('a changed mapping is what Check sends', (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _choose(tester, 'Item Name', 'name *');

    expect(
      find.byKey(const ValueKey<String>('import-mapping-missing')),
      findsNothing,
    );
    await tester.ensureVisible(find.text('Check file'));
    await tester.tap(find.text('Check file'));
    await tester.pumpAndSettle();

    expect(api.sent.single, {
      'Item Code': 'code',
      'Item Name': 'name',
      'Colour': null,
    });
  });

  testWidgets('two headings on one column block Check', (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _choose(tester, 'Item Name', 'name *');
    await _choose(tester, 'Colour', 'name *');

    expect(
      find.byKey(const ValueKey<String>('import-mapping-duplicate')),
      findsOneWidget,
    );
    expect(_checkEnabled(tester), isFalse);
  });

  testWidgets('a saved mapping is applied to the headings it names',
      (tester) async {
    final _Api api = _Api(saved: const [
      ImportMapping(
        id: 'm1',
        kind: 'products',
        name: 'Tally items',
        mapping: {'Item Name': 'name', 'Not In File': 'brand'},
      ),
    ]);
    await _open(tester, api);
    await tester.tap(
      find.byKey(const ValueKey<String>('import-mapping-saved')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Tally items').last);
    await tester.pumpAndSettle();

    expect(_value(tester, 'Item Name'), 'name');
    expect(_value(tester, 'Item Code'), 'code');
    expect(_checkEnabled(tester), isTrue);
  });

  testWidgets('a saved mapping once applied can be deleted', (tester) async {
    final _Api api = _Api(saved: const [
      ImportMapping(
        id: 'm1',
        kind: 'products',
        name: 'Tally items',
        mapping: {'Item Name': 'name'},
      ),
    ]);
    await _open(tester, api);
    expect(
      find.byKey(const ValueKey<String>('import-mapping-delete')),
      findsNothing,
    );
    await tester.tap(
      find.byKey(const ValueKey<String>('import-mapping-saved')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Tally items').last);
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey<String>('import-mapping-delete')),
    );
    await tester.pumpAndSettle();

    expect(api.deleted, ['m1']);
    expect(find.text('Deleted "Tally items".'), findsOneWidget);
    expect(_value(tester, 'Item Name'), 'name');
  });

  testWidgets('Save mapping as posts the name and the current mapping',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _choose(tester, 'Item Name', 'name *');
    final Finder save = find.byKey(const ValueKey<String>('import-mapping-save'));
    await tester.ensureVisible(save);
    await tester.tap(save);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey<String>('import-mapping-name')),
      'Tally items',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.savedPosts, ['Tally items']);
    expect(api.savedMappings.single['Item Name'], 'name');
    expect(find.textContaining('Saved as "Tally items"'), findsOneWidget);
  });
}

class _WireApi extends ApiClient {
  _WireApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Map<String, String>> fields = <Map<String, String>>[];

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
    this.fields.add(fields);
    return <String, dynamic>{
      'success': true,
      'data': <String, dynamic>{'rows': 0},
    };
  }
}

void wireTests() {
  test('the mapping goes as a JSON form field, and only when there is one',
      () async {
    final _WireApi api = _WireApi();
    await api.checkProductImportFile(
      fileName: 'a.csv',
      bytes: const [1],
      updateExisting: false,
      apply: false,
      mapping: const {'Item Code': 'code', 'Colour': null},
    );
    await api.checkCustomerImportFile(
      fileName: 'a.csv',
      bytes: const [1],
      updateExisting: false,
      apply: false,
    );
    expect(
      jsonDecode(api.fields.first['mapping']!),
      {'Item Code': 'code', 'Colour': null},
    );
    expect(api.fields.last.containsKey('mapping'), isFalse);
  });
}
