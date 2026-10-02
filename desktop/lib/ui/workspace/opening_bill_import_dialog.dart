import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import 'master_import_dialog.dart';

/// `yyyy-mm-dd`, the form the server reads a posting date in.
String _isoDate(DateTime value) => '${value.year.toString().padLeft(4, '0')}-'
    '${value.month.toString().padLeft(2, '0')}-'
    '${value.day.toString().padLeft(2, '0')}';

/// Bring a firm's opening bills in from one file (D-GOLIVE-1): what each
/// customer owed it, or what it owed each supplier, on the day its books here
/// start.
///
/// The shared [MasterImportDialog] wired to one side's opening-bill endpoints,
/// with the posting date every bill is posted on. A bill is posted once and
/// cancelled on its party's screen, so "update existing" is not offered.
/// Closes with the applied `FileImportReport`, or null if nothing was
/// imported.
class OpeningBillImportDialog extends StatefulWidget {
  const OpeningBillImportDialog({
    super.key,
    required this.api,
    required this.side,
    this.initialDate,
    this.pickFileOverride,
    this.saveBytesOverride,
  });

  final ApiClient api;

  /// `customers` or `vendors`.
  final String side;

  /// The posting date offered first; today when null.
  final DateTime? initialDate;
  final Future<XFile?> Function()? pickFileOverride;
  final SaveBytesOverride? saveBytesOverride;

  @override
  State<OpeningBillImportDialog> createState() =>
      _OpeningBillImportDialogState();
}

class _OpeningBillImportDialogState extends State<OpeningBillImportDialog> {
  late final TextEditingController _postingDate = TextEditingController(
    text: _isoDate(widget.initialDate ?? DateTime.now()),
  );

  bool get _suppliers => widget.side == 'vendors';

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
        key: const ValueKey<String>('opening-bill-import-posting-date'),
        controller: _postingDate,
        onChanged: (_) => changed(),
        decoration: InputDecoration(
          labelText: 'Posting date (yyyy-mm-dd)',
          helperText: 'The day the books here start. Every bill is posted on '
              'it, and no bill may be dated after it.',
          suffixIcon: IconButton(
            tooltip: 'Choose a date',
            icon: const Icon(Icons.calendar_today_outlined),
            onPressed: () => _pickDate(changed),
          ),
        ),
      );

  @override
  Widget build(BuildContext context) => MasterImportDialog(
        noun: _suppliers ? "suppliers' opening bills" : "customers' opening bills",
        fileStem:
            _suppliers ? 'supplier-opening-bills' : 'customer-opening-bills',
        downloadTemplate: (format) =>
            widget.api.openingBillImportTemplate(widget.side, format: format),
        checkFile: ({
          required String fileName,
          required List<int> bytes,
          required bool updateExisting,
          required bool apply,
          Map<String, String?>? mapping,
        }) =>
            widget.api.checkOpeningBillImportFile(
          widget.side,
          fileName: fileName,
          bytes: bytes,
          postingDate: _postingDate.text.trim(),
          apply: apply,
          mapping: mapping,
        ),
        mappingApi: widget.api,
        mappingKind: _suppliers
            ? 'vendor-opening-bills'
            : 'customer-opening-bills',
        canUpdate: false,
        offersUpdate: false,
        extraFields: _fields,
        pickFileOverride: widget.pickFileOverride,
        saveBytesOverride: widget.saveBytesOverride,
      );
}
