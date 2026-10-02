// Opening bills come in from one file the server checks (D-GOLIVE-1). The
// shared import dialog carries the cutover day every bill is posted on, sends
// it to the right side of the books, and hides "update existing": a bill is
// posted once and cancelled on its party's screen.

import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/file_import.dart';
import 'package:agency_desktop/ui/workspace/opening_bill_import_dialog.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/import_file.dart';

class _Call {
  _Call(this.side, this.apply, this.postingDate);
  final String side;
  final bool apply;
  final String postingDate;
}

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<_Call> calls = <_Call>[];
  final List<String> templates = <String>[];

  @override
  Future<List<int>> openingBillImportTemplate(
    String side, {
    String format = 'xlsx',
  }) async {
    templates.add('$side.$format');
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
  Future<FileImportReport> checkOpeningBillImportFile(
    String side, {
    required String fileName,
    required List<int> bytes,
    required String postingDate,
    required bool apply,
    Map<String, String?>? mapping,
  }) async {
    calls.add(_Call(side, apply, postingDate));
    return FileImportReport(
      rows: 2,
      toCreate: 2,
      toUpdate: 0,
      skippedBlank: 0,
      columnsUsed: const ['PartyCode', 'BillDate', 'Amount'],
      columnsIgnored: const [],
      issues: const [],
      imported: apply,
    );
  }
}

XFile _csv() {
  final Directory dir = Directory.systemTemp.createTempSync('bill-import');
  final File file = File('${dir.path}/bills.csv')
    ..writeAsStringSync('PartyCode,BillDate,Amount\nC1,01-03-2026,100\n');
  return XFile(file.path);
}

Future<void> _open(
  WidgetTester tester,
  _Api api, {
  required String side,
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
              builder: (context) => OpeningBillImportDialog(
                api: api,
                side: side,
                initialDate: DateTime(2026, 4, 1),
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

Future<void> _checkAndImport(WidgetTester tester) async {
  await chooseImportFile(tester);
  await tester.ensureVisible(find.text('Check file'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Check file'));
  await tester.pumpAndSettle();
  await tester.tap(find.widgetWithText(FilledButton, 'Import'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets("customers' bills go to the customer side with the cutover day",
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api, side: 'customers');
    expect(find.text("Import customers' opening bills"), findsOneWidget);
    expect(find.byType(CheckboxListTile), findsNothing,
        reason: 'a bill is posted once; nothing to update');
    expect(tester.takeException(), isNull);

    await _checkAndImport(tester);

    expect(api.calls.map((c) => (c.side, c.apply, c.postingDate)), [
      ('customers', false, '2026-04-01'),
      ('customers', true, '2026-04-01'),
    ]);
    expect(find.text("Import customers' opening bills"), findsNothing);
  });

  testWidgets("suppliers' bills go to the supplier side", (tester) async {
    final _Api api = _Api();
    await _open(tester, api, side: 'vendors');
    expect(find.text("Import suppliers' opening bills"), findsOneWidget);
    await _checkAndImport(tester);
    expect(api.calls.map((c) => c.side).toSet(), {'vendors'});
  });

  testWidgets('the templates download for the side asked', (tester) async {
    final _Api api = _Api();
    final List<String> saved = <String>[];
    await _open(tester, api, side: 'vendors', saved: saved);
    await tester.tap(find.text('Template (Excel)'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Template (CSV)'));
    await tester.pumpAndSettle();
    expect(api.templates, ['vendors.xlsx', 'vendors.csv']);
    expect(saved, [
      'supplier-opening-bills_import_template.xlsx',
      'supplier-opening-bills_import_template.csv',
    ]);
  });
}
