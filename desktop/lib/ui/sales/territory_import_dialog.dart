import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/sales_territory.dart';
import '../workspace/desktop_framework.dart';

/// Load a territory hierarchy from a CSV file.
///
/// `POST /import` has accepted a hierarchy — and customer mappings through an
/// optional `CustomerCodes` column — since the module was written, and the
/// toolbar's Import action did nothing at all.
///
/// Thinner than the branch and warehouse importer on purpose: the server owns
/// the parsing here, so validating rows client-side would be a second,
/// disagreeing implementation of the same rules.
class TerritoryImportDialog extends StatefulWidget {
  const TerritoryImportDialog({
    super.key,
    required this.api,
    this.pickFileOverride,
  });

  final ApiClient api;

  /// Injected by tests, which cannot open a native file dialog.
  final Future<XFile?> Function()? pickFileOverride;

  @override
  State<TerritoryImportDialog> createState() => _TerritoryImportDialogState();
}

class _TerritoryImportDialogState extends State<TerritoryImportDialog> {
  String _fileName = '';
  List<int>? _bytes;
  int _lineCount = 0;
  bool _busy = false;
  String? _error;
  List<SalesTerritory>? _imported;

  Future<void> _pick() async {
    final XFile? picked = widget.pickFileOverride != null
        ? await widget.pickFileOverride!()
        : await openFile(
            acceptedTypeGroups: const [
              XTypeGroup(label: 'CSV', extensions: ['csv']),
            ],
            confirmButtonText: 'Select import file',
          );
    if (picked == null) return;
    final List<int> bytes = await picked.readAsBytes();
    if (!mounted) return;
    setState(() {
      _fileName = picked.name;
      _bytes = bytes;
      _imported = null;
      _error = null;
      // A count for the person, not a validation. The server decides what is
      // acceptable and says so per row.
      _lineCount = String.fromCharCodes(bytes)
          .split('\n')
          .where((line) => line.trim().isNotEmpty)
          .length;
      if (_lineCount > 0) _lineCount -= 1; // the header
    });
  }

  Future<void> _import() async {
    final List<int>? bytes = _bytes;
    if (bytes == null || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final List<SalesTerritory> rows = await widget.api.importTerritories(
        fileName: _fileName,
        bytes: bytes,
      );
      if (!mounted) return;
      setState(() {
        _imported = rows;
        _busy = false;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        // True, and worth saying: the whole file is one transaction, so a row
        // refused anywhere leaves the firm exactly as it was. The first
        // question after a failed import is always whether half of it went in.
        _error = '${exception.message} Nothing was imported.';
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final List<SalesTerritory>? imported = _imported;
    return AlertDialog(
      title: const Text('Import territories'),
      content: SizedBox(
        width: 560,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'CSV columns: Code, Name, Level, ParentCode, Status and an '
              'optional CustomerCodes list. Level is the display name of a '
              'hierarchy level, and ParentCode must already exist or appear '
              'earlier in the file.',
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                OutlinedButton.icon(
                  onPressed: _busy ? null : _pick,
                  icon: const Icon(Icons.upload_file),
                  label: const Text('Choose file'),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    _fileName.isEmpty
                        ? 'No file chosen'
                        : '$_fileName — $_lineCount row(s)',
                  ),
                ),
              ],
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              WorkspaceErrorState(message: _error!, onRetry: _import),
            ],
            if (imported != null) ...[
              const SizedBox(height: 12),
              Text('${imported.length} territory(ies) imported.'),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _busy ? null : () => Navigator.pop(context, _imported != null),
          child: Text(_imported == null ? 'Cancel' : 'Close'),
        ),
        FilledButton(
          onPressed: _bytes == null || _busy || _imported != null ? null : _import,
          child: Text(_busy ? 'Importing...' : 'Import'),
        ),
      ],
    );
  }
}
