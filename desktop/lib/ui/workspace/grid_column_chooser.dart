import 'package:flutter/material.dart';

import '../../core/preferences/desktop_preferences_service.dart';
import 'workspace_components.dart';

/// One column a list can show, with how to fill its cell.
///
/// The owner asked for the sales lists to offer more columns (2026-09-27);
/// Busy, Tally and Vyapar let each user choose theirs. A list declares every
/// column it can show, the few it shows by default, and the ones that cannot
/// be hidden (the number, which is how a row is named).
class ChoosableColumn<T> {
  const ChoosableColumn({
    required this.column,
    required this.cell,
    this.shownByDefault = false,
    this.required = false,
  });

  final GridColumn column;
  final String Function(T item) cell;
  final bool shownByDefault;

  /// Always shown, and not offered in the chooser.
  final bool required;

  String get key => column.key;
}

/// Which columns a list shows, remembered per screen on this PC in the
/// desktop's workspace state (the store for a screen's own layout,
/// `desktop/docs/DESKTOP_FRAMEWORK.md`).
class ColumnChoice<T> {
  ColumnChoice({
    required this.preferences,
    required this.stateKey,
    required this.columns,
  }) : shown = _load(preferences, stateKey, columns);

  final DesktopPreferencesService preferences;
  final String stateKey;
  final List<ChoosableColumn<T>> columns;
  Set<String> shown;

  static Set<String> _load<T>(
    DesktopPreferencesService preferences,
    String stateKey,
    List<ChoosableColumn<T>> columns,
  ) {
    final Object? saved = preferences.workspaceState(stateKey)['columns'];
    final Set<String> known = {for (final c in columns) c.key};
    final Set<String> chosen = saved is List
        ? {for (final Object? key in saved) '$key'}.intersection(known)
        : {
            for (final c in columns)
              if (c.shownByDefault) c.key,
          };
    return {
      ...chosen,
      for (final c in columns)
        if (c.required) c.key,
    };
  }

  /// The grid's columns: every declared one, hidden where not chosen, so the
  /// cells stay aligned with their headings.
  List<GridColumn> get gridColumns => [
        for (final ChoosableColumn<T> c in columns)
          GridColumn(
            key: c.column.key,
            label: c.column.label,
            onSort: c.column.onSort,
            tooltip: c.column.tooltip,
            numeric: c.column.numeric,
            priority: c.column.priority,
            visible: shown.contains(c.key),
          ),
      ];

  List<String> cells(T item) => [for (final c in columns) c.cell(item)];

  /// Ask which columns to show; true when the choice changed.
  Future<bool> choose(BuildContext context) async {
    final Set<String>? picked = await pick(context);
    if (picked == null) return false;
    await apply(picked);
    return true;
  }

  /// The chooser itself: the columns picked, or null when cancelled.
  Future<Set<String>?> pick(BuildContext context) => showDialog<Set<String>>(
        context: context,
        builder: (_) =>
            _ColumnChooserDialog<T>(columns: columns, shown: shown),
      );

  /// Show [picked] (and the columns that cannot be hidden) and remember it.
  Future<void> apply(Set<String> picked) async {
    shown = {
      ...picked,
      for (final c in columns)
        if (c.required) c.key,
    };
    await preferences.saveWorkspaceState(stateKey, {
      ...preferences.workspaceState(stateKey),
      'columns': [
        for (final c in columns)
          if (shown.contains(c.key)) c.key,
      ],
    });
  }
}

/// The button that opens the chooser, beside a list's search box.
class ColumnsButton extends StatelessWidget {
  const ColumnsButton({super.key, required this.onPressed});

  final VoidCallback onPressed;

  // An icon with its name on hover: the page line it sits on is shared with
  // the title, the counters and the search.
  @override
  Widget build(BuildContext context) => IconButton.outlined(
        key: const ValueKey('grid-columns'),
        tooltip: 'Columns',
        onPressed: onPressed,
        icon: const Icon(Icons.view_column_outlined, size: 18),
      );
}

class _ColumnChooserDialog<T> extends StatefulWidget {
  const _ColumnChooserDialog({required this.columns, required this.shown});

  final List<ChoosableColumn<T>> columns;
  final Set<String> shown;

  @override
  State<_ColumnChooserDialog<T>> createState() =>
      _ColumnChooserDialogState<T>();
}

class _ColumnChooserDialogState<T> extends State<_ColumnChooserDialog<T>> {
  late final Set<String> _shown = {...widget.shown};

  @override
  Widget build(BuildContext context) {
    final List<ChoosableColumn<T>> offered = [
      for (final c in widget.columns)
        if (!c.required) c,
    ];
    return AlertDialog(
      title: const Text('Columns'),
      content: SizedBox(
        width: 360,
        child: ListView(
          shrinkWrap: true,
          children: [
            for (final ChoosableColumn<T> c in offered)
              CheckboxListTile(
                key: ValueKey('grid-column-${c.key}'),
                dense: true,
                value: _shown.contains(c.key),
                title: Text(c.column.label),
                controlAffinity: ListTileControlAffinity.leading,
                onChanged: (value) => setState(() {
                  if (value ?? false) {
                    _shown.add(c.key);
                  } else {
                    _shown.remove(c.key);
                  }
                }),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => setState(() {
            _shown
              ..clear()
              ..addAll({
                for (final c in widget.columns)
                  if (c.shownByDefault || c.required) c.key,
              });
          }),
          child: const Text('Default'),
        ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('grid-columns-apply'),
          onPressed: () => Navigator.of(context).pop(_shown),
          child: const Text('Apply'),
        ),
      ],
    );
  }
}
