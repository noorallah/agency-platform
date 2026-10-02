import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/file_import.dart';

/// What the mapping step tells the dialog around it.
///
/// [mapping] is what Check and Import send, or null when the file is read as
/// it always was (no preview, or one that failed). [blocked] is true while the
/// choices are unusable -- a required column nobody maps to, or two headings
/// on one column -- and [loading] while the preview is on its way.
typedef ImportMappingChanged = void Function({
  required Map<String, String?>? mapping,
  required bool blocked,
  required bool loading,
});

/// The common mapping step of every file import (B3): the file's own headings
/// against the template's columns, as an exported Tally, Marg, Busy or Excel
/// file needs. Pre-set from what the server would read today, so a file that
/// already matches the template is one glance and no change.
///
/// A failed preview (an older server, no permission) leaves the dialog reading
/// the file as before: [onChanged] reports a null mapping and nothing is shown.
class ImportMappingPanel extends StatefulWidget {
  const ImportMappingPanel({
    super.key,
    required this.api,
    required this.kind,
    required this.fileName,
    required this.bytes,
    required this.onChanged,
  });

  final ApiClient api;

  /// `products`, `customers`, `vendors`, `customer-opening-bills`,
  /// `vendor-opening-bills` or `opening-stock`.
  final String kind;
  final String fileName;
  final List<int> bytes;
  final ImportMappingChanged onChanged;

  @override
  State<ImportMappingPanel> createState() => _ImportMappingPanelState();
}

class _ImportMappingPanelState extends State<ImportMappingPanel> {
  ImportPreview? _preview;
  List<ImportMapping> _saved = const [];
  Map<String, String?> _choice = <String, String?>{};
  bool _loading = true;
  String? _notice;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    ImportPreview? preview;
    List<ImportMapping> saved = const [];
    try {
      preview = await widget.api.importPreview(
        kind: widget.kind,
        fileName: widget.fileName,
        bytes: widget.bytes,
      );
    } catch (_) {
      preview = null;
    }
    if (preview != null) {
      try {
        saved = await widget.api.importMappings(widget.kind);
      } catch (_) {
        saved = const [];
      }
    }
    if (!mounted) return;
    setState(() {
      _preview = preview;
      _saved = saved;
      _choice = preview == null
          ? <String, String?>{}
          : <String, String?>{
              for (final String heading in preview.fileHeadings)
                heading: preview.suggested[heading],
            };
      _loading = false;
    });
    _report();
  }

  /// Required columns no heading is mapped to.
  List<String> get _unmappedRequired {
    final ImportPreview? preview = _preview;
    if (preview == null) return const [];
    final Set<String?> taken = _choice.values.toSet();
    return [
      for (final ImportColumn column in preview.columns)
        if (column.required && !taken.contains(column.heading)) column.heading,
    ];
  }

  /// Template columns two or more headings are mapped to.
  List<String> get _duplicated {
    final Map<String, int> counts = <String, int>{};
    for (final String? column in _choice.values) {
      if (column != null) counts[column] = (counts[column] ?? 0) + 1;
    }
    return [
      for (final MapEntry<String, int> entry in counts.entries)
        if (entry.value > 1) entry.key,
    ];
  }

  bool get _blocked =>
      _preview != null &&
      (_unmappedRequired.isNotEmpty || _duplicated.isNotEmpty);

  void _report() {
    widget.onChanged(
      mapping: _preview == null ? null : Map<String, String?>.of(_choice),
      blocked: _blocked,
      loading: _loading,
    );
  }

  void _pick(String heading, String? column) {
    setState(() {
      _choice[heading] = column;
      _notice = null;
    });
    _report();
  }

  void _applySaved(ImportMapping saved) {
    final ImportPreview? preview = _preview;
    if (preview == null) return;
    final Set<String> known = {
      for (final ImportColumn column in preview.columns) column.heading,
    };
    setState(() {
      for (final MapEntry<String, String?> entry in saved.mapping.entries) {
        if (!_choice.containsKey(entry.key)) continue;
        if (entry.value != null && !known.contains(entry.value)) continue;
        _choice[entry.key] = entry.value;
      }
      _notice = 'Applied "${saved.name}".';
    });
    _report();
  }

  Future<void> _saveAs() async {
    final String? name = await _askName(context);
    if (name == null) return;
    try {
      final ImportMapping saved = await widget.api.saveImportMapping(
        widget.kind,
        name,
        Map<String, String?>.of(_choice),
      );
      if (!mounted) return;
      setState(() {
        _saved = [
          for (final ImportMapping other in _saved)
            if (other.id != saved.id && other.name != saved.name) other,
          saved,
        ];
        _notice = 'Saved as "${saved.name}".';
      });
    } on ApiException catch (error) {
      if (mounted) setState(() => _notice = error.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ImportPreview? preview = _preview;
    if (_loading) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
        child: LinearProgressIndicator(),
      );
    }
    if (preview == null) return const SizedBox.shrink();
    final List<String> missing = _unmappedRequired;
    final List<String> duplicated = _duplicated;
    final TextStyle? small = theme.textTheme.bodySmall;
    final TextStyle? warn = small?.copyWith(color: theme.colorScheme.error);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          "Match the file's columns to ours. Anything set to \"Not imported\" "
          'is left out.',
          style: theme.textTheme.bodyMedium,
        ),
        const SizedBox(height: AppSpacing.sm),
        Row(
          children: [
            if (_saved.isNotEmpty)
              Expanded(
                child: DropdownButton<ImportMapping>(
                  key: const ValueKey<String>('import-mapping-saved'),
                  isExpanded: true,
                  isDense: true,
                  hint: const Text('Saved mappings'),
                  value: null,
                  items: [
                    for (final ImportMapping saved in _saved)
                      DropdownMenuItem<ImportMapping>(
                        value: saved,
                        child: Text(
                          saved.name,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                  ],
                  onChanged: (saved) {
                    if (saved != null) _applySaved(saved);
                  },
                ),
              )
            else
              const Spacer(),
            const SizedBox(width: AppSpacing.md),
            OutlinedButton.icon(
              key: const ValueKey<String>('import-mapping-save'),
              onPressed: _saveAs,
              icon: const Icon(Icons.save_outlined),
              label: const Text('Save mapping as…'),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: 260),
          child: ListView(
            shrinkWrap: true,
            children: [
              for (int index = 0; index < preview.fileHeadings.length; index++)
                _row(theme, preview, index),
            ],
          ),
        ),
        if (missing.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.xs),
            child: Text(
              'Required, and no column of the file is mapped to it: '
              '${missing.join(', ')}.',
              key: const ValueKey<String>('import-mapping-missing'),
              style: warn,
            ),
          ),
        if (duplicated.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.xs),
            child: Text(
              'More than one column of the file is mapped to: '
              '${duplicated.join(', ')}.',
              key: const ValueKey<String>('import-mapping-duplicate'),
              style: warn,
            ),
          ),
        if (_notice != null)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.xs),
            child: Text(_notice!, style: small),
          ),
      ],
    );
  }

  Widget _row(ThemeData theme, ImportPreview preview, int index) {
    final String heading = preview.fileHeadings[index];
    final String sample = [
      for (final List<String> row in preview.sampleRows.take(2))
        if (index < row.length && row[index].isNotEmpty) row[index],
    ].join(' · ');
    final String? value = _choice[heading];
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        children: [
          Expanded(
            flex: 2,
            child: Text(heading, overflow: TextOverflow.ellipsis),
          ),
          Expanded(
            flex: 2,
            child: Text(
              sample,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            flex: 3,
            child: DropdownButton<String?>(
              key: ValueKey<String>('import-map-$heading'),
              isExpanded: true,
              isDense: true,
              value: value,
              items: [
                const DropdownMenuItem<String?>(
                  value: null,
                  child: Text('Not imported'),
                ),
                for (final ImportColumn column in preview.columns)
                  DropdownMenuItem<String?>(
                    value: column.heading,
                    child: Text(
                      column.required ? '${column.heading} *' : column.heading,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
              ],
              onChanged: (column) => _pick(heading, column),
            ),
          ),
        ],
      ),
    );
  }
}

/// A small prompt for a name; null for a dismissal or an empty box.
Future<String?> _askName(BuildContext context) => showDialog<String>(
      context: context,
      builder: (context) => const _NameDialog(),
    );

class _NameDialog extends StatefulWidget {
  const _NameDialog();

  @override
  State<_NameDialog> createState() => _NameDialogState();
}

class _NameDialogState extends State<_NameDialog> {
  final TextEditingController _name = TextEditingController();

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Save mapping'),
        content: SizedBox(
          width: 360,
          child: TextField(
            key: const ValueKey<String>('import-mapping-name'),
            controller: _name,
            autofocus: true,
            maxLength: 100,
            decoration: const InputDecoration(
              labelText: 'Name',
              helperText: 'For example "Tally stock export". Saving under an '
                  'existing name replaces it.',
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              final String name = _name.text.trim();
              Navigator.of(context).pop(name.isEmpty ? null : name);
            },
            child: const Text('Save'),
          ),
        ],
      );
}
