import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../../models/sales_territory.dart';

/// What the owner chose to do with a node from the large tree window.
enum TerritoryTreeAction { filterList, createChild, clearFilter }

/// The choice made in the window: an action and the node it is about.
typedef TerritoryTreeChoice = ({TerritoryTreeAction action, String nodeId});

/// The whole territory tree in a window of its own.
///
/// The Geography screen shows the tree in its narrow side panel, under a
/// dashboard line and two rows of buttons, which left a few lines for the
/// tree itself -- a region, its zones and their routes did not fit (plan item
/// 11.1, 2026-09-13). This window gives the tree most of the screen. It owns
/// its own expanded state and hands the chosen action back to the screen
/// rather than acting itself, so the screen's filters and editors stay the one
/// implementation.
class TerritoryTreeDialog extends StatefulWidget {
  const TerritoryTreeDialog({
    super.key,
    required this.tree,
    required this.canCreate,
    required this.hasParentFilter,
  });

  final List<TerritoryTreeNodeRecord> tree;
  final bool canCreate;
  final bool hasParentFilter;

  static Future<TerritoryTreeChoice?> show(
    BuildContext context, {
    required List<TerritoryTreeNodeRecord> tree,
    required bool canCreate,
    required bool hasParentFilter,
  }) =>
      showDialog<TerritoryTreeChoice>(
        context: context,
        builder: (_) => TerritoryTreeDialog(
          tree: tree,
          canCreate: canCreate,
          hasParentFilter: hasParentFilter,
        ),
      );

  @override
  State<TerritoryTreeDialog> createState() => _TerritoryTreeDialogState();
}

class _TerritoryTreeDialogState extends State<TerritoryTreeDialog> {
  // Opens expanded: the reason to open the window is to see the whole shape.
  bool _expanded = true;
  int _epoch = 0;

  void _setAll(bool expanded) => setState(() {
        _expanded = expanded;
        _epoch++;
      });

  @override
  Widget build(BuildContext context) {
    final Size screen = MediaQuery.sizeOf(context);
    final ThemeData theme = Theme.of(context);
    final double width = screen.width * 0.8 < 960 ? screen.width * 0.8 : 960;
    return Dialog(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: width,
          maxHeight: screen.height * 0.85,
        ),
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Wrap(
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.sm,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  Text('Territory tree', style: theme.textTheme.titleLarge),
                  OutlinedButton.icon(
                    onPressed: () => _setAll(true),
                    icon: const Icon(Icons.unfold_more),
                    label: const Text('Expand all'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () => _setAll(false),
                    icon: const Icon(Icons.unfold_less),
                    label: const Text('Collapse all'),
                  ),
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Close'),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.sm),
              const Divider(height: 1),
              Flexible(
                child: widget.tree.isEmpty
                    ? const Padding(
                        padding: EdgeInsets.all(AppSpacing.lg),
                        child: Text('No territories yet.'),
                      )
                    : ListView(
                        shrinkWrap: true,
                        children: [
                          for (final TerritoryTreeNodeRecord node in widget.tree)
                            _node(node),
                        ],
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _node(TerritoryTreeNodeRecord node) => ExpansionTile(
        key: ValueKey<String>('tree-window-${node.id}-$_epoch'),
        initiallyExpanded: _expanded,
        title: Text('${node.name} (${node.hierarchyLevelName})'),
        subtitle: Text('${node.code}  ·  ${node.path}'),
        trailing: PopupMenuButton<TerritoryTreeAction>(
          tooltip: 'Actions for ${node.code}',
          onSelected: (TerritoryTreeAction action) => Navigator.of(context)
              .pop<TerritoryTreeChoice>((action: action, nodeId: node.id)),
          itemBuilder: (_) => [
            const PopupMenuItem(
              value: TerritoryTreeAction.filterList,
              child: Text('Filter list'),
            ),
            if (widget.canCreate)
              const PopupMenuItem(
                value: TerritoryTreeAction.createChild,
                child: Text('Quick create child'),
              ),
            if (widget.hasParentFilter)
              const PopupMenuItem(
                value: TerritoryTreeAction.clearFilter,
                child: Text('Clear parent filter'),
              ),
          ],
        ),
        childrenPadding: const EdgeInsets.only(left: AppSpacing.lg),
        children: [
          for (final TerritoryTreeNodeRecord child in node.children)
            _node(child),
        ],
      );
}
