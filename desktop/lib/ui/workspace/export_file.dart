import 'dart:io';

import 'package:file_selector/file_selector.dart';

/// How an export is written to disk. Tests inject one, because a widget test
/// cannot open a native save dialog.
typedef SaveExportOverride = Future<String?> Function(
  String suggestedName,
  String content,
);

/// Ask where to save an exported text file and write it there.
///
/// Returns the path written, or null when the person cancelled the dialog.
/// Every Export action goes through this: four of them fetched the CSV from
/// the server, threw it away and reported "Export completed." -- the server
/// log showed the request answered 200, the screen said success, and no
/// file existed anywhere.
Future<String?> saveExportedText({
  required String suggestedName,
  required String content,
  SaveExportOverride? override,
}) async {
  if (override != null) return override(suggestedName, content);
  final FileSaveLocation? location = await getSaveLocation(
    suggestedName: suggestedName,
    acceptedTypeGroups: const [
      XTypeGroup(label: 'CSV', extensions: ['csv']),
    ],
  );
  if (location == null) return null;
  await File(location.path).writeAsString(content, flush: true);
  return location.path;
}

/// The one sentence every export reports, naming where the file went: the
/// question after any export is "where did it go".
String exportSavedMessage(String path) => 'Export saved to $path.';

/// What an export says when the save dialog was dismissed.
const String exportCancelledMessage = 'Export cancelled. No file was saved.';
