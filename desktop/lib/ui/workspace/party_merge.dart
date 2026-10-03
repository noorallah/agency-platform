// Duplicate warning and merge for customers and suppliers (MST-3).
//
// Two halves, one file, because customers and suppliers behave the same way:
//
// * [saveUnlessDuplicate] asks the server who already looks like a NEW record
//   and, if anybody does, lets the user choose. It is advice -- the server
//   never refuses on a duplicate, and a check that itself fails never blocks
//   the save.
// * [showPartyMergeDialog] folds one record into another. The server moves the
//   documents, adds the balances and soft-deletes the duplicate; the dialog
//   only chooses which and asks why.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/entities.dart';
import 'save_in_dialog.dart';

/// Raised from a save that the user backed out of at the duplicate warning, so
/// the editor stays open with what was typed.
const String duplicateCancelledMessage =
    'Not saved: a record that looks the same already exists.';

/// One line a candidate is listed by: code, name and why it matched.
String duplicateLine(Json row) {
  final dynamic reasons = row['reasons'];
  final String why = reasons is List && reasons.isNotEmpty
      ? ' (${reasons.join(', ')})'
      : '';
  return '${row['code'] ?? ''}  ${row['name'] ?? ''}$why'.trim();
}

/// Run [save] for a new record, first warning if [check] finds look-alikes.
///
/// Returns what [save] returns. When the user cancels at the warning this
/// throws an [ApiException], which every saving dialog already shows in place
/// without closing. A [check] that throws is ignored.
Future<T> saveUnlessDuplicate<T>(
  BuildContext context, {
  required Future<List<Json>> Function() check,
  required Future<T> Function() save,
  String noun = 'record',
}) async {
  List<Json> candidates = const [];
  try {
    candidates = await check();
  } on ApiException {
    // Advice only: a failed check must not stop a save.
  }
  if (candidates.isEmpty || !context.mounted) return save();
  final bool? proceed = await showDialog<bool>(
    context: context,
    builder: (_) => _DuplicateWarning(candidates: candidates, noun: noun),
  );
  if (proceed != true) {
    throw const ApiException(duplicateCancelledMessage);
  }
  return save();
}

class _DuplicateWarning extends StatelessWidget {
  const _DuplicateWarning({required this.candidates, required this.noun});

  final List<Json> candidates;
  final String noun;

  @override
  Widget build(BuildContext context) => AlertDialog(
        key: const ValueKey<String>('duplicate-warning'),
        title: Text('Possible duplicate $noun'),
        content: SizedBox(
          width: 480,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'These existing ${noun}s look like the one you are saving. '
                'Save anyway only if it really is a different one.',
              ),
              const SizedBox(height: 12),
              for (final Json row in candidates)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Text(duplicateLine(row)),
                ),
            ],
          ),
        ),
        actions: [
          TextButton(
            key: const ValueKey<String>('duplicate-cancel'),
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey<String>('duplicate-save-anyway'),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Save anyway'),
          ),
        ],
      );
}

/// Open the merge dialog for [survivorLabel]. Returns the server's summary on
/// success, null when dismissed.
///
/// [likely] lists the look-alikes first; [search] finds any other record by
/// typed text; [merge] sends `{duplicate_id, reason}`.
Future<Json?> showPartyMergeDialog(
  BuildContext context, {
  required String noun,
  required String survivorId,
  required String survivorLabel,
  required Future<List<Json>> Function() likely,
  required Future<List<Json>> Function(String text) search,
  required Future<Json> Function(Json body) merge,
}) =>
    showDialog<Json>(
      context: context,
      builder: (_) => _PartyMergeDialog(
        noun: noun,
        survivorId: survivorId,
        survivorLabel: survivorLabel,
        likely: likely,
        search: search,
        merge: merge,
      ),
    );

/// The sentence shown after a merge.
String mergeSummary(Json result) => 'Merged: ${result['rows_moved'] ?? 0} '
    'rows moved';

class _PartyMergeDialog extends StatefulWidget {
  const _PartyMergeDialog({
    required this.noun,
    required this.survivorId,
    required this.survivorLabel,
    required this.likely,
    required this.search,
    required this.merge,
  });

  final String noun;
  final String survivorId;
  final String survivorLabel;
  final Future<List<Json>> Function() likely;
  final Future<List<Json>> Function(String text) search;
  final Future<Json> Function(Json body) merge;

  @override
  State<_PartyMergeDialog> createState() => _PartyMergeDialogState();
}

class _PartyMergeDialogState extends State<_PartyMergeDialog>
    with SaveInDialog {
  final TextEditingController _find = TextEditingController();
  final TextEditingController _reason = TextEditingController();
  List<Json> _options = const [];
  bool _loading = true;
  String? _picked;

  @override
  void initState() {
    super.initState();
    _loadLikely();
  }

  @override
  void dispose() {
    _find.dispose();
    _reason.dispose();
    super.dispose();
  }

  Future<void> _loadLikely() async {
    List<Json> rows = const [];
    try {
      rows = await widget.likely();
    } on ApiException {
      // Likely duplicates are a convenience; the search still works.
    }
    if (!mounted) return;
    setState(() {
      _options = _withoutSurvivor(rows);
      _loading = false;
    });
  }

  List<Json> _withoutSurvivor(List<Json> rows) =>
      rows.where((row) => row['id'] != widget.survivorId).toList();

  Future<void> _runSearch(String text) async {
    if (text.trim().isEmpty) {
      await _loadLikely();
      return;
    }
    setState(() => _loading = true);
    List<Json> rows = const [];
    try {
      rows = await widget.search(text.trim());
    } on ApiException catch (exception) {
      if (mounted) setState(() => saveError = exception.message);
    }
    if (!mounted) return;
    setState(() {
      _options = _withoutSurvivor(rows);
      _loading = false;
    });
  }

  bool get _ready => _picked != null && _reason.text.trim().isNotEmpty;

  @override
  Widget build(BuildContext context) => AlertDialog(
        key: const ValueKey<String>('party-merge-dialog'),
        title: Text('Merge into ${widget.survivorLabel}'),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                saveErrorBanner(),
                Text(
                  'Choose the ${widget.noun} to fold into '
                  '${widget.survivorLabel}. Its documents move across, its '
                  'balances are added, and it is removed from the list.',
                ),
                const SizedBox(height: 8),
                const Text(
                  'This cannot be undone.',
                  key: ValueKey<String>('merge-warning'),
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 12),
                TextField(
                  key: const ValueKey<String>('merge-search'),
                  controller: _find,
                  decoration: InputDecoration(
                    labelText: 'Find the duplicate ${widget.noun}',
                    prefixIcon: const Icon(Icons.search),
                  ),
                  onSubmitted: _runSearch,
                ),
                const SizedBox(height: 8),
                if (_loading)
                  const LinearProgressIndicator()
                else if (_options.isEmpty)
                  const Text('No other records to show.')
                else
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxHeight: 220),
                    child: RadioGroup<String>(
                      groupValue: _picked,
                      onChanged: (value) {
                        if (!saving) setState(() => _picked = value);
                      },
                      child: ListView(
                        shrinkWrap: true,
                        children: [
                          for (final Json row in _options)
                            RadioListTile<String>(
                              key: ValueKey<String>(
                                'merge-option-${row['id']}',
                              ),
                              dense: true,
                              value: '${row['id']}',
                              title: Text(duplicateLine(row)),
                            ),
                        ],
                      ),
                    ),
                  ),
                const SizedBox(height: 8),
                TextField(
                  key: const ValueKey<String>('merge-reason'),
                  controller: _reason,
                  decoration: const InputDecoration(
                    labelText: 'Reason',
                    helperText: 'Kept in the audit trail.',
                  ),
                  onChanged: (_) => setState(() {}),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: saving ? null : () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey<String>('merge-confirm'),
            onPressed: saving || !_ready
                ? null
                : () => saveAndClose<Json>(
                      () => widget.merge(<String, dynamic>{
                        'duplicate_id': _picked,
                        'reason': _reason.text.trim(),
                      }),
                    ),
            child: Text(saving ? 'Merging...' : 'Merge'),
          ),
        ],
      );
}
