// Products are imported from a file the server checks. Import is offered only
// after a clean check of the file as it now stands, and the server -- not the
// client -- says what is wrong with it.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/file_import.dart';
import 'package:agency_desktop/ui/products/product_import_dialog.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/import_file.dart';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(
    'h.${base64Url.encode(utf8.encode(jsonEncode({
              'roles': <String>['user'],
              'permissions': codes,
            }))).replaceAll('=', '')}.s',
  );

class _Call {
  _Call(this.apply, this.update);
  final bool apply;
  final bool update;
}

class _Api extends ApiClient {
  _Api({required this.checkReport, this.applyReport})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final FileImportReport checkReport;
  final FileImportReport? applyReport;
  final List<_Call> calls = <_Call>[];
  final List<String> templates = <String>[];

  @override
  Future<List<int>> productImportTemplate({String format = 'xlsx'}) async {
    templates.add(format);
    return <int>[1, 2, 3];
  }

  @override
  Future<ImportPreview> importPreview({
    required String kind,
    required String fileName,
    required List<int> bytes,
  }) async =>
      throw const ApiException('no preview');

  @override
  Future<FileImportReport> checkProductImportFile({
    required String fileName,
    required List<int> bytes,
    required bool updateExisting,
    required bool apply,
    Map<String, String?>? mapping,
  }) async {
    calls.add(_Call(apply, updateExisting));
    return apply ? (applyReport ?? checkReport) : checkReport;
  }
}

FileImportReport _report({
  int created = 2,
  int updated = 1,
  bool imported = false,
  List<FileImportIssue> issues = const [],
  List<FileImportIssue> warnings = const [],
}) =>
    FileImportReport(
      rows: created + updated,
      toCreate: created,
      toUpdate: updated,
      skippedBlank: 0,
      columnsUsed: const ['code', 'name'],
      columnsIgnored: const ['colour'],
      issues: issues,
      warnings: warnings,
      imported: imported,
    );

XFile _csv() {
  final Directory dir = Directory.systemTemp.createTempSync('product-import');
  final File file = File('${dir.path}/products.csv')
    ..writeAsStringSync('code,name\nA,Apple\n');
  return XFile(file.path);
}

Future<FileImportReport?> Function() _open(
  WidgetTester tester,
  _Api api,
  PermissionService permissions, {
  List<String>? saved,
}) {
  FileImportReport? result;
  bool closed = false;
  tester.view.physicalSize = const Size(800, 600);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  return () async {
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () async {
                result = await showDialog<FileImportReport>(
                  context: context,
                  builder: (context) => ProductImportDialog(
                    api: api,
                    permissions: permissions,
                    pickFileOverride: () async => _csv(),
                    saveBytesOverride: (name, bytes) async => saved?.add(name),
                  ),
                );
                closed = true;
              },
              child: const Text('open'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    return closed ? result : null;
  };
}

Future<void> _chooseFile(WidgetTester tester) async {
  await chooseImportFile(tester);
}

FilledButton _import(WidgetTester tester) =>
    tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Import'));

void main() {
  testWidgets('a check with problems lists them and keeps Import disabled',
      (tester) async {
    final _Api api = _Api(
      checkReport: _report(issues: const [
        FileImportIssue(
          row: 3,
          message: 'Unknown category',
          text: 'Row 3: category - Unknown category',
        ),
      ]),
    );
    final List<String> saved = <String>[];
    await _open(tester, api, _permissions(['PRODUCT_IMPORT']), saved: saved)();
    await _chooseFile(tester);
    expect(_import(tester).onPressed, isNull);

    await tester.tap(find.text('Check file'));
    await tester.pumpAndSettle();

    expect(find.text('Row 3: category - Unknown category'), findsOneWidget);
    expect(find.textContaining('3 rows: 2 new, 1 to update'), findsOneWidget);
    expect(find.textContaining('Columns ignored: colour'), findsOneWidget);
    expect(_import(tester).onPressed, isNull);
    expect(api.calls.single.apply, isFalse);

    await tester.ensureVisible(find.text('Save problems…'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save problems…'));
    await tester.pumpAndSettle();
    expect(saved, ['product_import_problems.csv']);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a clean check enables Import, which applies and closes',
      (tester) async {
    final _Api api = _Api(
      checkReport: _report(),
      applyReport: _report(imported: true),
    );
    await _open(tester, api, _permissions(['PRODUCT_IMPORT']))();
    await _chooseFile(tester);
    await tester.tap(find.text('Check file'));
    await tester.pumpAndSettle();
    expect(_import(tester).onPressed, isNotNull);

    await tester.tap(find.widgetWithText(FilledButton, 'Import'));
    await tester.pumpAndSettle();

    expect(api.calls.map((c) => c.apply), [false, true]);
    expect(api.calls.last.update, isFalse);
    expect(find.text('Import products'), findsNothing);
  });

  testWidgets('a warning is shown and does not stop the import',
      (tester) async {
    // Backlog 89: a unit set marked for another goods type is said, never
    // refused. The file is clean, so Import stays offered.
    const String said = "Row 3 (ENM-1): UnitSet: 'Piece, box of 10' is marked "
        "for other goods types than this product's. It is imported as written.";
    final _Api api = _Api(
      checkReport: _report(warnings: const [
        FileImportIssue(
          row: 3,
          code: 'ENM-1',
          column: 'UnitSet',
          message: 'is marked for other goods types',
          text: said,
        ),
      ]),
      applyReport: _report(imported: true),
    );
    await _open(tester, api, _permissions(['PRODUCT_IMPORT']))();
    await _chooseFile(tester);
    await tester.tap(find.text('Check file'));
    await tester.pumpAndSettle();

    expect(find.text(said), findsOneWidget);
    expect(
      find.text('1 to look at. These do not stop the import.'),
      findsOneWidget,
    );
    expect(find.text('No problems found.'), findsOneWidget);
    expect(_import(tester).onPressed, isNotNull);
    expect(tester.takeException(), isNull);
  });

  test('a report without warnings reads as none, and with them as a list', () {
    final Map<String, dynamic> base = <String, dynamic>{
      'rows': 1,
      'to_create': 1,
      'to_update': 0,
      'skipped_blank': 0,
      'columns_used': ['Code'],
      'columns_ignored': <String>[],
      'issues': <Map<String, dynamic>>[],
      'imported': false,
    };
    expect(FileImportReport.fromJson(base).warnings, isEmpty);
    final FileImportReport warned = FileImportReport.fromJson({
      ...base,
      'warnings': [
        {'row': 2, 'code': 'A', 'column': 'UnitSet', 'message': 'm', 'text': 't'},
      ],
    });
    expect(warned.warnings.single.text, 't');
    expect(warned.isClean, isTrue);
  });

  testWidgets('changing the update choice needs a fresh check and is sent',
      (tester) async {
    final _Api api = _Api(
      checkReport: _report(),
      applyReport: _report(imported: true),
    );
    await _open(
      tester,
      api,
      _permissions(['PRODUCT_IMPORT', 'PRODUCT_UPDATE']),
    )();
    await _chooseFile(tester);
    await tester.tap(find.text('Check file'));
    await tester.pumpAndSettle();
    expect(_import(tester).onPressed, isNotNull);

    await tester.tap(find.byType(CheckboxListTile));
    await tester.pumpAndSettle();
    expect(_import(tester).onPressed, isNull);

    await tester.tap(find.text('Check file'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Import'));
    await tester.pumpAndSettle();

    expect(api.calls.map((c) => c.update), [false, true, true]);
    expect(api.calls.last.apply, isTrue);
  });

  testWidgets('the update checkbox is disabled without PRODUCT_UPDATE',
      (tester) async {
    final _Api api = _Api(checkReport: _report());
    await _open(tester, api, _permissions(['PRODUCT_IMPORT']))();
    final CheckboxListTile box =
        tester.widget<CheckboxListTile>(find.byType(CheckboxListTile));
    expect(box.onChanged, isNull);
    expect(box.value, isFalse);
  });

  testWidgets('both templates download through the save path', (tester) async {
    final _Api api = _Api(checkReport: _report());
    final List<String> saved = <String>[];
    await _open(tester, api, _permissions(['PRODUCT_IMPORT']), saved: saved)();
    await tester.tap(find.text('Template (Excel)'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Template (CSV)'));
    await tester.pumpAndSettle();
    expect(api.templates, ['xlsx', 'csv']);
    expect(saved, [
      'product_import_template.xlsx',
      'product_import_template.csv',
    ]);
  });
}
