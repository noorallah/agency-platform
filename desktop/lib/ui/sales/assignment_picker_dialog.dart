import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../workspace/desktop_framework.dart';

/// One thing that can be put on a round: a customer, a salesperson.
class AssignableOption {
  const AssignableOption({
    required this.id,
    required this.label,
    this.secondary = '',
  });

  final String id;

  /// What the user calls it — a customer's name, a person's name.
  final String label;

  /// The detail that separates two similar labels: a code, an email.
  final String secondary;

  bool matches(String term) {
    if (term.isEmpty) return true;
    final String lower = term.toLowerCase();
    return label.toLowerCase().contains(lower) ||
        secondary.toLowerCase().contains(lower);
  }
}

/// Choose who or what belongs on a round.
///
/// This replaces a text box that asked for **comma-separated UUIDs**. Both
/// assignment dialogs on the Geography screen were built that way, which meant
/// the feature existed and could not be used: nobody knows a customer's id, and
/// pasting the wrong one assigns a different customer with no way to notice.
///
/// The list is a replace, not an add — the server treats what it receives as
/// the whole assignment — so it opens with the current members ticked and the
/// caller sends back everything still ticked.
class AssignmentPickerDialog extends StatefulWidget {
  const AssignmentPickerDialog({
    super.key,
    required this.title,
    required this.options,
    required this.selectedIds,
    required this.emptyMessage,
    this.searchHint = 'Search',
  });

  final String title;
  final List<AssignableOption> options;
  final Set<String> selectedIds;

  /// Shown when the firm has nothing to assign — a firm with no customers on
  /// its books needs to be told that, not shown an empty list it might read as
  /// a loading failure.
  final String emptyMessage;
  final String searchHint;

  @override
  State<AssignmentPickerDialog> createState() => _AssignmentPickerDialogState();
}

class _AssignmentPickerDialogState extends State<AssignmentPickerDialog> {
  late final Set<String> _selected = <String>{...widget.selectedIds};
  final TextEditingController _search = TextEditingController();

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  List<AssignableOption> get _visible {
    final String term = _search.text.trim();
    return widget.options.where((option) => option.matches(term)).toList();
  }

  /// Anything ticked but filtered out of view still counts. Sending only what
  /// is on screen would silently unassign everyone the search hid.
  int get _hiddenSelected =>
      _selected.length - _visible.where((o) => _selected.contains(o.id)).length;

  @override
  Widget build(BuildContext context) {
    final List<AssignableOption> visible = _visible;
    return AlertDialog(
      title: Text(widget.title),
      content: SizedBox(
        width: 560,
        height: 460,
        child: widget.options.isEmpty
            ? StandardEmptyState(
                type: EmptyStateType.noRecords,
                title: 'Nothing to assign',
                message: widget.emptyMessage,
              )
            : Column(
                children: [
                  TextField(
                    controller: _search,
                    decoration: InputDecoration(
                      labelText: widget.searchHint,
                      prefixIcon: const Icon(Icons.search),
                    ),
                    onChanged: (_) => setState(() {}),
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      _hiddenSelected > 0
                          ? '${_selected.length} selected '
                              '($_hiddenSelected not shown by this search)'
                          : '${_selected.length} selected',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  Expanded(
                    child: visible.isEmpty
                        ? const StandardEmptyState(
                            type: EmptyStateType.noSearchResults,
                          )
                        : ListView.builder(
                            itemCount: visible.length,
                            itemBuilder: (context, index) {
                              final AssignableOption option = visible[index];
                              return CheckboxListTile(
                                dense: true,
                                value: _selected.contains(option.id),
                                title: Text(option.label,
                                    overflow: TextOverflow.ellipsis),
                                subtitle: option.secondary.isEmpty
                                    ? null
                                    : Text(option.secondary,
                                        overflow: TextOverflow.ellipsis),
                                onChanged: (checked) => setState(() {
                                  if (checked == true) {
                                    _selected.add(option.id);
                                  } else {
                                    _selected.remove(option.id);
                                  }
                                }),
                              );
                            },
                          ),
                  ),
                ],
              ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(context, _selected.toList()),
          child: const Text('Save'),
        ),
      ],
    );
  }
}
