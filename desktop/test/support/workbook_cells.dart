import 'package:agency_desktop/ui/workspace/report_workbook.dart';
import 'package:excel/excel.dart' as xls;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The cells of a saved workbook's one sheet, as plain values: a figure
/// comes back a number, text comes back text.
List<List<Object?>> workbookCells(List<int> bytes) {
  final xls.Excel workbook = xls.Excel.decodeBytes(bytes);
  final xls.Sheet sheet = workbook.tables.values.first;
  return [
    for (final List<xls.Data?> row in sheet.rows)
      [
        for (final xls.Data? cell in row)
          switch (cell?.value) {
            final xls.DoubleCellValue value => value.value,
            final xls.IntCellValue value => value.value,
            final xls.TextCellValue value => '${value.value}',
            null => null,
            final xls.CellValue value => '$value',
          },
      ],
  ];
}

/// Presses the Download of the screen on show and answers the sheet it
/// saved, with the file name it offered in [name]. A widget test cannot open
/// the native save dialog, so the button's writer is replaced for the press.
/// [button] is for a screen whose download is a menu entry.
Future<List<List<Object?>>> downloadedSheet(
  WidgetTester tester, {
  List<String>? name,
  Finder? button,
}) async {
  final List<List<int>> saved = [];
  WorkbookDownloadButton.saveOverride = (suggested, bytes) async {
    name?.add(suggested);
    saved.add(bytes);
    return 'C:/out/$suggested';
  };
  addTearDown(() => WorkbookDownloadButton.saveOverride = null);
  final Finder target =
      button ?? find.byKey(const ValueKey<String>('workbook-download'));
  await tester.ensureVisible(target);
  await tester.tap(target);
  await tester.pumpAndSettle();
  return workbookCells(saved.single);
}
