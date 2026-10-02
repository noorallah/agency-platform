import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../workspace/master_import_dialog.dart';

/// `yyyy-mm-dd`, the form the server reads a posting date in.
String _isoDate(DateTime value) => '${value.year.toString().padLeft(4, '0')}-'
    '${value.month.toString().padLeft(2, '0')}-'
    '${value.day.toString().padLeft(2, '0')}';

/// Bring the stock on hand at cutover in from one file: the shared
/// [MasterImportDialog] wired to the opening stock endpoints, with the posting
/// date every document is created and posted on.
///
/// The server groups the rows into one opening stock document per warehouse
/// and posts them all, or none. There is nothing to update -- opening stock is
/// posted once -- so the "update existing" option is not offered. Closes with
/// the applied `FileImportReport`, or null if nothing was imported.
class OpeningStockImportDialog extends StatefulWidget {
  const OpeningStockImportDialog({
    super.key,
    required this.api,
    this.initialDate,
    this.pickFileOverride,
    this.saveBytesOverride,
  });

  final ApiClient api;

  /// The posting date offered first; today when null.
  final DateTime? initialDate;
  final Future<XFile?> Function()? pickFileOverride;
  final SaveBytesOverride? saveBytesOverride;

  @override
  State<OpeningStockImportDialog> createState() =>
      _OpeningStockImportDialogState();
}

class _OpeningStockImportDialogState extends State<OpeningStockImportDialog> {
  late final TextEditingController _postingDate = TextEditingController(
    text: _isoDate(widget.initialDate ?? DateTime.now()),
  );

  @override
  void dispose() {
    _postingDate.dispose();
    super.dispose();
  }

  Future<void> _pickDate(VoidCallback changed) async {
    final DateTime initial =
        DateTime.tryParse(_postingDate.text.trim()) ?? DateTime.now();
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked == null) return;
    _postingDate.text = _isoDate(picked);
    changed();
  }

  Widget _fields(BuildContext context, VoidCallback changed) => TextField(
        key: const ValueKey<String>('opening-stock-import-posting-date'),
        controller: _postingDate,
        onChanged: (_) => changed(),
        decoration: InputDecoration(
          labelText: 'Posting date (yyyy-mm-dd)',
          helperText:
              'Every warehouse\'s opening stock is created and posted on this '
              'date.',
          suffixIcon: IconButton(
            tooltip: 'Choose a date',
            icon: const Icon(Icons.calendar_today_outlined),
            onPressed: () => _pickDate(changed),
          ),
        ),
      );

  @override
  Widget build(BuildContext context) => MasterImportDialog(
        noun: 'opening stock',
        fileStem: 'opening-stock',
        downloadTemplate: (format) =>
            widget.api.openingStockImportTemplate(format: format),
        checkFile: ({
          required String fileName,
          required List<int> bytes,
          required bool updateExisting,
          required bool apply,
          Map<String, String?>? mapping,
        }) =>
            widget.api.checkOpeningStockImportFile(
          fileName: fileName,
          bytes: bytes,
          postingDate: _postingDate.text.trim(),
          apply: apply,
          mapping: mapping,
        ),
        mappingApi: widget.api,
        mappingKind: 'opening-stock',
        canUpdate: false,
        offersUpdate: false,
        extraFields: _fields,
        pickFileOverride: widget.pickFileOverride,
        saveBytesOverride: widget.saveBytesOverride,
      );
}
