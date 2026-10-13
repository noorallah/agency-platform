import 'dart:async';
import 'dart:io';

import 'package:excel/excel.dart' as xls;
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import 'export_file.dart';

/// A report or a statement as one sheet of a workbook: what it is, what it
/// was asked for, its column headings and its rows.
///
/// The one shape every Download on a report screen hands over (backlog 117),
/// so the sheet is laid out in one place rather than once per screen.
class WorkbookSheet {
  const WorkbookSheet({
    required this.title,
    required this.headers,
    required this.rows,
    this.notes = const [],
    this.numeric = const {},
  });

  /// The report's name, on the first line of the sheet.
  final String title;

  /// What the figures were asked for, one per line under the title: the
  /// period, the party, the account.
  final List<String> notes;

  final List<String> headers;

  /// The positions in [headers] that hold figures. A cell there that reads
  /// as a number is written as one, so Excel can add the column up; a server
  /// sends a decimal as text to keep its precision.
  final Set<int> numeric;

  /// One list per row, a cell per heading. A cell is a number, a true or
  /// false, text, or null for nothing.
  final List<List<Object?>> rows;
}

/// How a workbook is written to disk. Tests inject one, because a widget
/// test cannot open a native save dialog. Answers the path written, or null
/// when the person cancelled.
typedef SaveWorkbookOverride = Future<String?> Function(
  String suggestedName,
  List<int> bytes,
);

xls.CellValue? _cell(Object? value, {required bool numeric}) {
  if (value == null) return null;
  if (value is bool) return xls.TextCellValue(value ? 'Yes' : 'No');
  if (value is int) return xls.IntCellValue(value);
  if (value is num) return xls.DoubleCellValue(value.toDouble());
  final String text = '$value';
  if (text.isEmpty) return null;
  if (numeric) {
    final double? parsed = double.tryParse(text);
    if (parsed != null) return xls.DoubleCellValue(parsed);
  }
  return xls.TextCellValue(text);
}

/// The bytes of an `.xlsx` holding [sheet]: the title, its notes, a blank
/// line, the headings in bold and then the rows.
List<int> workbookBytes(WorkbookSheet sheet) {
  final xls.Excel workbook = xls.Excel.createExcel();
  final String name = workbook.getDefaultSheet() ?? 'Sheet1';
  final xls.Sheet page = workbook[name];
  final xls.CellStyle bold = xls.CellStyle(bold: true);
  page.appendRow([xls.TextCellValue(sheet.title)]);
  page
      .cell(xls.CellIndex.indexByColumnRow(columnIndex: 0, rowIndex: 0))
      .cellStyle = bold;
  for (final String note in sheet.notes) {
    page.appendRow([xls.TextCellValue(note)]);
  }
  page.appendRow([xls.TextCellValue('')]);
  final int headerRow = sheet.notes.length + 2;
  page.appendRow(sheet.headers.map(xls.TextCellValue.new).toList());
  for (int column = 0; column < sheet.headers.length; column++) {
    page
        .cell(xls.CellIndex.indexByColumnRow(
            columnIndex: column, rowIndex: headerRow))
        .cellStyle = bold;
  }
  for (final List<Object?> row in sheet.rows) {
    page.appendRow([
      for (int column = 0; column < row.length; column++)
        _cell(row[column], numeric: sheet.numeric.contains(column)),
    ]);
  }
  return workbook.encode() ?? const <int>[];
}

/// A file name made of [parts], keeping only what every file system takes.
String workbookFileName(List<String> parts) {
  final String joined = parts
      .map((part) => part.trim())
      .where((part) => part.isNotEmpty)
      .join('-')
      .replaceAll(RegExp(r'[^A-Za-z0-9._-]+'), '-')
      .replaceAll(RegExp(r'-{2,}'), '-');
  return '${joined.isEmpty ? 'report' : joined}.xlsx';
}

/// Ask where to save a workbook and write it there. Answers the path, or
/// null when the person cancelled the dialog.
Future<String?> saveWorkbook({
  required String suggestedName,
  required List<int> bytes,
  SaveWorkbookOverride? override,
}) async {
  if (override != null) return override(suggestedName, bytes);
  final FileSaveLocation? location = await getSaveLocation(
    suggestedName: suggestedName,
    acceptedTypeGroups: const [
      XTypeGroup(label: 'Excel workbook', extensions: ['xlsx']),
    ],
  );
  if (location == null) return null;
  await File(location.path).writeAsBytes(bytes, flush: true);
  return location.path;
}

/// Build [sheet], ask where to save it and say where it went. What the
/// Download button does, for a screen whose download sits in a menu instead:
/// a toolbar with no room for one more button.
Future<void> downloadWorkbook(
  BuildContext context, {
  required String fileName,
  required FutureOr<WorkbookSheet> Function() sheet,
  SaveWorkbookOverride? saveFile,
}) async {
  try {
    final WorkbookSheet built = await sheet();
    final String? path = await saveWorkbook(
      suggestedName: fileName,
      bytes: workbookBytes(built),
      override: saveFile ?? WorkbookDownloadButton.saveOverride,
    );
    if (!context.mounted) return;
    NotificationService.show(
      context,
      path == null ? exportCancelledMessage : exportSavedMessage(path),
      kind: path == null
          ? AppNotificationKind.information
          : AppNotificationKind.success,
    );
  } on ApiException catch (exception) {
    if (!context.mounted) return;
    NotificationService.show(
      context,
      'Download failed: ${exception.message}',
      kind: AppNotificationKind.error,
    );
  } on FileSystemException catch (exception) {
    if (!context.mounted) return;
    NotificationService.show(
      context,
      'The file could not be written: ${exception.message}',
      kind: AppNotificationKind.error,
    );
  }
}

/// The Download button of a report or statement screen: builds the sheet
/// from what the screen holds, asks where to save it and says where it went.
class WorkbookDownloadButton extends StatefulWidget {
  const WorkbookDownloadButton({
    super.key,
    required this.fileName,
    required this.sheet,
    this.enabled = true,
    this.saveFile,
  });

  /// Where every button saves in a widget test, which cannot open the
  /// native dialog; a screen's own [saveFile] still wins.
  @visibleForTesting
  static SaveWorkbookOverride? saveOverride;

  /// The name offered in the save dialog, ending `.xlsx`.
  final String Function() fileName;

  /// The sheet to write, read when the button is pressed. It may ask the
  /// server for the rows the screen is not holding, a paged report's later
  /// pages.
  final FutureOr<WorkbookSheet> Function() sheet;

  /// False while the screen has nothing to download.
  final bool enabled;

  final SaveWorkbookOverride? saveFile;

  @override
  State<WorkbookDownloadButton> createState() => _WorkbookDownloadButtonState();
}

class _WorkbookDownloadButtonState extends State<WorkbookDownloadButton> {
  bool _busy = false;

  Future<void> _download() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await downloadWorkbook(
        context,
        fileName: widget.fileName(),
        sheet: widget.sheet,
        saveFile: widget.saveFile,
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Tooltip(
        message: 'Download as an Excel sheet',
        child: TextButton.icon(
          key: const ValueKey<String>('workbook-download'),
          onPressed:
              widget.enabled && !_busy ? () => unawaited(_download()) : null,
          icon: const Icon(Icons.download_outlined, size: 16),
          label: const Text('Download'),
        ),
      );
}
