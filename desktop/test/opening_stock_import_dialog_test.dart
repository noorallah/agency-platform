// Opening stock comes in from one file the server checks (backlog 36, 46).
// The shared import dialog carries a posting date the server needs, hides the
// "update existing" option opening stock has no use for, and discards a check
// when the date changes, so Import is offered only for what was checked.

import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/file_import.dart';
import 'package:agency_desktop/ui/inventory/opening_stock_import_dialog.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/import_file.dart';

class _Call {
  _Call(this.apply, this.postingDate);
  final bool apply;
  final String postingDate;
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
  Future<List<int>> openingStockImportTemplate({String format = 'xlsx'}) async {
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
  Future<FileImportReport> checkOpeningStockImportFile({
    required String fileName,
    required List<int> bytes,
    required String postingDate,
    required bool apply,
    Map<String, String?>? mapping,
  }) async {
    calls.add(_Call(apply, postingDate));
    return apply ? (applyReport ?? checkReport) : checkReport;
  }
}

FileImportReport _report({
  int rows = 3,
  bool imported = false,
  List<FileImportIssue> issues = const [],
}) =>
    FileImportReport(
      rows: rows,
      toCreate: rows,
      toUpdate: 0,
      skippedBlank: 0,
      columnsUsed: const ['ProductCode', 'Warehouse', 'Quantity'],
      columnsIgnored: const [],
      issues: issues,
      imported: imported,
    );

XFile _csv() {
  final Directory dir = Directory.systemTemp.createTempSync('opening-import');
  final File file = File('${dir.path}/stock.csv')
    ..writeAsStringSync('ProductCode,Warehouse,Quantity\nRICE,MAIN,10\n');
  return XFile(file.path);
}

Future<void> _open(
  WidgetTester tester,
  _Api api, {
  List<String>? saved,
}) async {
  tester.view.physicalSize = const Size(800, 600);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: TextButton(
            onPressed: () => showDialog<FileImportReport>(
              context: context,
              builder: (context) => OpeningStockImportDialog(
                api: api,
                initialDate: DateTime(2026, 8, 1),
                pickFileOverride: () async => _csv(),
                saveBytesOverride: (name, bytes) async => saved?.add(name),
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
}

Future<void> _chooseFile(WidgetTester tester) async {
  await chooseImportFile(tester);
}

Future<void> _check(WidgetTester tester) async {
  await tester.ensureVisible(find.text('Check file'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Check file'));
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
          code: 'SYRUP',
          column: 'Batch',
          message: 'is required: SYRUP is batch-tracked.',
          text: 'Row 3 (SYRUP): Batch: is required: SYRUP is batch-tracked.',
        ),
      ]),
    );
    await _open(tester, api);
    expect(find.text('Import opening stock'), findsOneWidget);
    expect(find.byType(CheckboxListTile), findsNothing,
        reason: 'opening stock is posted once; nothing to update');
    await _chooseFile(tester);
    await _check(tester);

    expect(
      find.text('Row 3 (SYRUP): Batch: is required: SYRUP is batch-tracked.'),
      findsOneWidget,
    );
    expect(find.textContaining('3 rows to import'), findsOneWidget);
    expect(_import(tester).onPressed, isNull);
    expect(api.calls.single.apply, isFalse);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a clean check imports with the posting date and closes',
      (tester) async {
    final _Api api = _Api(
      checkReport: _report(),
      applyReport: _report(imported: true),
    );
    await _open(tester, api);
    await _chooseFile(tester);
    await _check(tester);
    expect(_import(tester).onPressed, isNotNull);

    await tester.tap(find.widgetWithText(FilledButton, 'Import'));
    await tester.pumpAndSettle();

    expect(api.calls.map((c) => c.apply), [false, true]);
    expect(api.calls.map((c) => c.postingDate), ['2026-08-01', '2026-08-01']);
    expect(find.text('Import opening stock'), findsNothing);
  });

  testWidgets('changing the posting date needs a fresh check and is sent',
      (tester) async {
    final _Api api = _Api(
      checkReport: _report(),
      applyReport: _report(imported: true),
    );
    await _open(tester, api);
    await _chooseFile(tester);
    await _check(tester);
    expect(_import(tester).onPressed, isNotNull);

    await tester.enterText(
      find.byKey(const ValueKey<String>('opening-stock-import-posting-date')),
      '2026-07-31',
    );
    await tester.pumpAndSettle();
    expect(_import(tester).onPressed, isNull);

    await _check(tester);
    await tester.tap(find.widgetWithText(FilledButton, 'Import'));
    await tester.pumpAndSettle();

    expect(
      api.calls.map((c) => c.postingDate),
      ['2026-08-01', '2026-07-31', '2026-07-31'],
    );
    expect(api.calls.last.apply, isTrue);
  });

  testWidgets('both templates download as opening-stock files', (tester) async {
    final _Api api = _Api(checkReport: _report());
    final List<String> saved = <String>[];
    await _open(tester, api, saved: saved);
    await tester.tap(find.text('Template (Excel)'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Template (CSV)'));
    await tester.pumpAndSettle();
    expect(api.templates, ['xlsx', 'csv']);
    expect(saved, [
      'opening-stock_import_template.xlsx',
      'opening-stock_import_template.csv',
    ]);
  });
}
