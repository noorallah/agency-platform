import 'package:flutter/material.dart';

import '../workspace/module_catalog.dart';

/// One page for several catalogue tabs that share a sidebar entry.
///
/// Roles and Permissions are the first: two reference screens somebody opens
/// a few times a year, which used to be two rows in a menu scanned every day.
/// The sidebar shows one entry, and this page puts the members side by side
/// as a tab strip over whichever is current.
///
/// The selection is **not** this widget's state. Each member keeps its own
/// catalogue id, which is its address -- what Ctrl+K opens, what the router
/// carries, what the remembered last screen restores -- so choosing a tab
/// here goes through [onSelect] to the router, the workspace rebuilds with
/// the new id, and the strip reflects [current]. That is what keeps the
/// heading, the sidebar highlight and the remembered workspace agreeing on
/// which half is open; a local index would drift from all three.
///
/// The strip is the framework's own tab shape, the `SegmentedButton` that
/// `ModuleWorkspaceFrame` renders for a module with tabs, so a grouped page
/// looks like every other tabbed workspace rather than like a third kind of
/// navigation.
class TabGroupPage extends StatelessWidget {
  const TabGroupPage({
    super.key,
    required this.members,
    required this.current,
    required this.onSelect,
    required this.builder,
  });

  /// The visible members, in catalogue order.
  final List<ModuleTabDefinition> members;

  /// The member whose screen is showing.
  final String current;

  /// Called with a member's id when it is chosen.
  final ValueChanged<String> onSelect;

  /// Builds one member's screen.
  final Widget Function(String tabId) builder;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // With one visible member there is nothing to choose between, and a
          // strip of one button is a control that does nothing.
          if (members.length > 1)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
              child: Align(
                alignment: Alignment.centerLeft,
                child: SegmentedButton<String>(
                  segments: [
                    for (final ModuleTabDefinition tab in members)
                      ButtonSegment<String>(
                        value: tab.id,
                        label: Text(tab.label),
                      ),
                  ],
                  selected: {current},
                  showSelectedIcon: false,
                  onSelectionChanged: (selection) => onSelect(selection.first),
                ),
              ),
            ),
          Expanded(child: builder(current)),
        ],
      );
}
