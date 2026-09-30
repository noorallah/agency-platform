// Suppliers are imported from a file the server checks. Import is offered only
// after a clean check of the file as it now stands, and the server -- not the
// client -- says what is wrong with it.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/file_import.dart';
import 'package:agency_desktop/ui/workspace/master_import_dialog.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

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
  Future<List<int>> vendorImportTemplate({String format = 'xlsx'}) async {
    templates.add(format);
    return <int>[1, 2, 3];
  }

  @override
  Future<FileImportReport> checkVendorImportFile({
    required String fileName,
    required List<int> bytes,
    required bool updateExisting,
    required bool apply,
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
}) =>
    FileImportReport(
      rows: created + updated,
      toCreate: created,
      toUpdate: updated,
      skippedBlank: 0,
      columnsUsed: const ['code', 'name'],
      columnsIgnored: const ['colour'],
      issues: issues,
      imported: imported,
    );

XFile _csv() {
  final Directory dir = Directory.systemTemp.createTempSync('supplier-import');
  final File file = File('${dir.path}/suppliers.csv')
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
                  builder: (context) => MasterImportDialog(
                    noun: 'suppliers',
                    fileStem: 'supplier',
                    downloadTemplate: (format) =>
                        api.vendorImportTemplate(format: format),
                    checkFile: api.checkVendorImportFile,
                    canUpdate: permissions.hasPermission('VENDOR_UPDATE'),
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
  await tester.runAsync(() async {
    await tester.tap(find.text('Choose file…'));
    await Future<void>.delayed(const Duration(milliseconds: 200));
  });
  await tester.pumpAndSettle();
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
    await _open(tester, api, _permissions(['VENDOR_IMPORT']), saved: saved)();
    await _chooseFile(tester);
    expect(_import(tester).onPressed, isNull);

    await tester.ensureVisible(find.text('Check file'));
    await tester.pumpAndSettle();
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
    expect(saved, ['supplier_import_problems.csv']);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a clean check enables Import, which applies and closes',
      (tester) async {
    final _Api api = _Api(
      checkReport: _report(),
      applyReport: _report(imported: true),
    );
    await _open(tester, api, _permissions(['VENDOR_IMPORT']))();
    await _chooseFile(tester);
    await tester.ensureVisible(find.text('Check file'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Check file'));
    await tester.pumpAndSettle();
    expect(_import(tester).onPressed, isNotNull);

    await tester.tap(find.widgetWithText(FilledButton, 'Import'));
    await tester.pumpAndSettle();

    expect(api.calls.map((c) => c.apply), [false, true]);
    expect(api.calls.last.update, isFalse);
    expect(find.text('Import suppliers'), findsNothing);
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
      _permissions(['VENDOR_IMPORT', 'VENDOR_UPDATE']),
    )();
    await _chooseFile(tester);
    await tester.ensureVisible(find.text('Check file'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Check file'));
    await tester.pumpAndSettle();
    expect(_import(tester).onPressed, isNotNull);

    await tester.tap(find.byType(CheckboxListTile));
    await tester.pumpAndSettle();
    expect(_import(tester).onPressed, isNull);

    await tester.ensureVisible(find.text('Check file'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Check file'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Import'));
    await tester.pumpAndSettle();

    expect(api.calls.map((c) => c.update), [false, true, true]);
    expect(api.calls.last.apply, isTrue);
  });

  testWidgets('the update checkbox is disabled without VENDOR_UPDATE',
      (tester) async {
    final _Api api = _Api(checkReport: _report());
    await _open(tester, api, _permissions(['VENDOR_IMPORT']))();
    final CheckboxListTile box =
        tester.widget<CheckboxListTile>(find.byType(CheckboxListTile));
    expect(box.onChanged, isNull);
    expect(box.value, isFalse);
  });

  testWidgets('both templates download through the save path', (tester) async {
    final _Api api = _Api(checkReport: _report());
    final List<String> saved = <String>[];
    await _open(tester, api, _permissions(['VENDOR_IMPORT']), saved: saved)();
    await tester.tap(find.text('Template (Excel)'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Template (CSV)'));
    await tester.pumpAndSettle();
    expect(api.templates, ['xlsx', 'csv']);
    expect(saved, [
      'supplier_import_template.xlsx',
      'supplier_import_template.csv',
    ]);
  });
}
