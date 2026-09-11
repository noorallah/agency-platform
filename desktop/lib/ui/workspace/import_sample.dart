import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

/// A CSV a person can download beside an Import button: the header row an
/// importer reads and one example row filled in, so the format is shown
/// rather than described.
///
/// The columns are the importer's own list, so the sample and the parser
/// cannot drift apart -- a dialog that documents one set of headings and
/// reads another is how a customer's first file gets refused.
class ImportSample {
  const ImportSample({
    required this.fileName,
    required this.columns,
    required this.example,
  });

  /// Suggested name in the save dialog, e.g. `branches_sample.csv`.
  final String fileName;

  /// The header row, spelled exactly as the importer reads it.
  final List<String> columns;

  /// One row of example values, one per column. An empty string leaves the
  /// cell blank, which is itself informative: it shows the column is optional.
  final List<String> example;

  /// The file content: the header row and the example row, RFC 4180 quoted.
  String get csv {
    // A const constructor cannot check this, so it is checked at the one
    // place the two lists are read together; every sample has a test that
    // reads it.
    assert(
      columns.length == example.length,
      'every column needs an example value',
    );
    return '${columns.map(_quote).join(',')}\r\n'
        '${example.map(_quote).join(',')}\r\n';
  }

  static String _quote(String value) {
    if (value.contains(',') ||
        value.contains('"') ||
        value.contains('\n') ||
        value.contains('\r')) {
      return '"${value.replaceAll('"', '""')}"';
    }
    return value;
  }
}

/// How a sample is written to disk. Tests inject one, because a widget test
/// cannot open a native save dialog.
typedef SaveSampleOverride = Future<void> Function(
  String suggestedName,
  String content,
);

/// Ask where to save the sample and write it there.
///
/// Returns true when a file was written, false when the person cancelled the
/// save dialog.
Future<bool> saveImportSample(
  ImportSample sample, {
  SaveSampleOverride? saveOverride,
}) async {
  if (saveOverride != null) {
    await saveOverride(sample.fileName, sample.csv);
    return true;
  }
  final FileSaveLocation? location = await getSaveLocation(
    suggestedName: sample.fileName,
    acceptedTypeGroups: const [
      XTypeGroup(label: 'CSV', extensions: ['csv']),
    ],
  );
  if (location == null) return false;
  await File(location.path).writeAsString(sample.csv, flush: true);
  return true;
}

/// The button that offers a sample beside "Choose file".
///
/// One widget rather than a button per dialog so every importer says the same
/// thing in the same place: a customer who has met it on Branches should
/// recognise it on Territories.
class ImportSampleButton extends StatelessWidget {
  const ImportSampleButton({
    super.key,
    required this.sample,
    this.enabled = true,
    this.saveOverride,
    this.onSaved,
  });

  final ImportSample sample;
  final bool enabled;
  final SaveSampleOverride? saveOverride;

  /// Called after the file was written, so the dialog can say so.
  final VoidCallback? onSaved;

  @override
  Widget build(BuildContext context) => Tooltip(
        message: 'Download a CSV with the column headings and one example row.',
        child: OutlinedButton.icon(
          onPressed: enabled
              ? () async {
                  final bool saved = await saveImportSample(
                    sample,
                    saveOverride: saveOverride,
                  );
                  if (saved) onSaved?.call();
                }
              : null,
          icon: const Icon(Icons.download_outlined),
          label: const Text('Sample file'),
        ),
      );
}
