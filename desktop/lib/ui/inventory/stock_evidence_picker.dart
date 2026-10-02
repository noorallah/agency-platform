import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../../models/entities.dart' show Json;
import '../delivery_notes/delivery_proof_dialog.dart' show proofMimeType;

/// The most files one movement or count sheet is given in a single save.
const int maxStockEvidenceFiles = 10;

/// Photos and documents to keep with a stock movement or a count sheet
/// (STK-9): each picked file with an optional caption and a way to take it
/// back out. The list leaves through [onChanged] as the `attachments` items
/// the server declares (`file_name`, `mime_type`, `file_path`, `caption`).
class StockEvidencePicker extends StatefulWidget {
  const StockEvidencePicker({
    super.key,
    required this.onChanged,
    this.pickFiles,
    this.remaining = maxStockEvidenceFiles,
  });

  final ValueChanged<List<Json>> onChanged;

  /// How files are picked: the platform's chooser unless a test says
  /// otherwise.
  final Future<List<XFile>> Function()? pickFiles;

  /// How many more files may be added (the cap less what is already kept).
  final int remaining;

  @override
  State<StockEvidencePicker> createState() => _StockEvidencePickerState();
}

class _PickedFile {
  _PickedFile(this.file);

  final XFile file;
  final TextEditingController caption = TextEditingController();
}

class _StockEvidencePickerState extends State<StockEvidencePicker> {
  final List<_PickedFile> _files = [];

  @override
  void dispose() {
    for (final _PickedFile picked in _files) {
      picked.caption.dispose();
    }
    super.dispose();
  }

  int get _cap => widget.remaining < maxStockEvidenceFiles
      ? widget.remaining
      : maxStockEvidenceFiles;

  void _emit() {
    widget.onChanged(<Json>[
      for (final _PickedFile picked in _files)
        <String, dynamic>{
          'file_name': picked.file.name,
          'mime_type': proofMimeType(picked.file.name),
          'file_path': picked.file.path,
          if (picked.caption.text.trim().isNotEmpty)
            'caption': picked.caption.text.trim(),
        },
    ]);
  }

  Future<void> _attach() async {
    final List<XFile> chosen = await (widget.pickFiles ?? openFiles)();
    if (chosen.isEmpty || !mounted) return;
    setState(() {
      for (final XFile file in chosen) {
        if (_files.length >= _cap) break;
        _files.add(_PickedFile(file));
      }
    });
    _emit();
  }

  void _remove(_PickedFile picked) {
    setState(() => _files.remove(picked));
    picked.caption.dispose();
    _emit();
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final _PickedFile picked in _files)
          Padding(
            key: ValueKey<String>('evidence-file-${picked.file.name}'),
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Row(
              children: [
                const Icon(Icons.attach_file, size: 18),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  flex: 2,
                  child: Text(picked.file.name, overflow: TextOverflow.ellipsis),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  flex: 3,
                  child: TextField(
                    controller: picked.caption,
                    maxLength: 200,
                    decoration: const InputDecoration(
                      labelText: 'Caption (optional)',
                      counterText: '',
                      isDense: true,
                    ),
                    onChanged: (_) => _emit(),
                  ),
                ),
                IconButton(
                  tooltip: 'Remove',
                  icon: const Icon(Icons.close, size: 18),
                  onPressed: () => _remove(picked),
                ),
              ],
            ),
          ),
        Row(
          children: [
            OutlinedButton.icon(
              onPressed: _files.length >= _cap ? null : _attach,
              icon: const Icon(Icons.add_a_photo_outlined, size: 18),
              label: const Text('Attach photo or document'),
            ),
            const SizedBox(width: AppSpacing.md),
            Text(
              '${_files.length} of $_cap',
              style: theme.textTheme.bodySmall,
            ),
          ],
        ),
      ],
    );
  }
}
