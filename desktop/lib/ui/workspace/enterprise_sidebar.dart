import 'package:flutter/material.dart';

import 'module_catalog.dart';
import 'workspace_components.dart';
import 'workspace_templates.dart';

/// The single, unified navigation surface for the desktop shell.
///
/// This replaces the legacy pattern of a fixed module rail *plus* a second,
/// permanently visible sub-navigation panel inside every workspace. All
/// module and sub-module entries now live in one collapsible hierarchical
/// tree, so business data (grids, forms, reports) can use the maximum
/// available width. See `docs/DESKTOP_UI_FRAMEWORK.md` for the navigation
/// standard this widget implements.
class EnterpriseSidebar extends StatefulWidget {
  const EnterpriseSidebar({
    super.key,
    required this.appName,
    required this.modules,
    required this.navigationChildren,
    required this.selectedModule,
    required this.selectedPath,
    required this.onSelectModule,
    required this.onSelectLeaf,
    required this.collapsed,
    required this.onToggleCollapsed,
    this.sections = const [],
    this.footer,
  });

  final String appName;
  final List<ModuleDefinition> modules;
  final List<WorkspaceNavigationNode> Function(ModuleDefinition module)
      navigationChildren;
  final AppModule selectedModule;
  final String? selectedPath;
  final ValueChanged<AppModule> onSelectModule;
  final void Function(AppModule module, String path) onSelectLeaf;
  final bool collapsed;
  final VoidCallback onToggleCollapsed;
  final List<EnterpriseSidebarSection> sections;
  final Widget? footer;

  @override
  State<EnterpriseSidebar> createState() => _EnterpriseSidebarState();
}

class _EnterpriseSidebarState extends State<EnterpriseSidebar> {
  void _openFlyout(
    BuildContext anchorContext,
    ModuleDefinition module,
    List<WorkspaceNavigationNode> children,
  ) {
    if (children.isEmpty) {
      widget.onSelectModule(module.id);
      return;
    }
    showFlyoutMenu(
      context: anchorContext,
      title: module.label,
      nodes: children,
      selectedPath:
          widget.selectedModule == module.id ? widget.selectedPath : null,
      onSelected: (path) => widget.onSelectLeaf(module.id, path),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Material(
      color: theme.colorScheme.surfaceContainerLowest,
      child: SafeArea(
        child: Column(children: [
          _header(theme),
          const Divider(height: 1),
          Expanded(
            child: widget.collapsed ? _collapsedRail() : _expandedTree(),
          ),
          if (widget.footer != null) ...[
            const Divider(height: 1),
            widget.footer!,
          ],
        ]),
      ),
    );
  }

  Widget _header(ThemeData theme) => SizedBox(
        height: 56,
        child: Row(children: [
          const SizedBox(width: 12),
          Icon(Icons.account_balance,
              size: 22, color: theme.colorScheme.primary),
          if (!widget.collapsed) ...[
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                widget.appName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.titleSmall,
              ),
            ),
          ],
          IconButton(
            tooltip:
                widget.collapsed ? 'Expand navigation' : 'Collapse navigation',
            onPressed: widget.onToggleCollapsed,
            icon: Icon(
                widget.collapsed ? Icons.chevron_right : Icons.chevron_left),
          ),
        ]),
      );

  /// Icon-only rail used when the sidebar is collapsed. Tapping a module
  /// opens a `FlyoutMenu` anchored to that icon (Outlook / VS Code /
  /// Azure-Portal style), instead of pushing a second permanent panel.
  Widget _collapsedRail() => ListView(
        padding: const EdgeInsets.symmetric(vertical: 8),
        children: widget.modules.map((module) {
          final bool selected = module.id == widget.selectedModule;
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            child: Tooltip(
              message: module.label,
              child: Builder(
                builder: (anchorContext) => Material(
                  color: selected
                      ? Theme.of(anchorContext).colorScheme.primaryContainer
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(10),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(10),
                    onTap: () => _openFlyout(
                      anchorContext,
                      module,
                      widget.navigationChildren(module),
                    ),
                    child: SizedBox(
                      height: 44,
                      child: Icon(module.icon),
                    ),
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      );

  /// Full hierarchical tree used when the sidebar is expanded. Only one
  /// navigation surface exists: module groups collapse/expand in place.
  Widget _expandedTree() {
    final List<EnterpriseSidebarSection> sections = widget.sections.isNotEmpty
        ? widget.sections
        : [
            EnterpriseSidebarSection(
              label: 'WORKSPACE',
              moduleIds: widget.modules.map((module) => module.id).toList(),
            ),
          ];
    final Map<AppModule, ModuleDefinition> moduleById = {
      for (final ModuleDefinition module in widget.modules) module.id: module,
    };
    final List<Widget> tiles = [];
    for (final EnterpriseSidebarSection section in sections) {
      final List<ModuleDefinition> sectionModules = section.moduleIds
          .map((id) => moduleById[id])
          .whereType<ModuleDefinition>()
          .toList();
      if (sectionModules.isEmpty) {
        continue;
      }
      tiles.add(
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 6),
          child: Text(
            section.label,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                  fontWeight: FontWeight.w700,
                  letterSpacing: .7,
                ),
          ),
        ),
      );
      for (final ModuleDefinition module in sectionModules) {
        final bool hasChildren = _addExpandedModuleTile(tiles, module);
        if (!hasChildren) {
          continue;
        }
      }
    }
    return ListView(
      padding: const EdgeInsets.symmetric(vertical: 4),
      children: tiles,
    );
  }

  bool _addExpandedModuleTile(List<Widget> tiles, ModuleDefinition module) {
    final List<WorkspaceNavigationNode> children = widget.navigationChildren(
      module,
    );
    final bool selectedModule = module.id == widget.selectedModule;
    if (children.isEmpty) {
      tiles.add(
        ListTile(
          selected: selectedModule,
          leading: Icon(module.icon),
          title: Text(module.label),
          onTap: () => widget.onSelectModule(module.id),
        ),
      );
      return true;
    }
    tiles.add(
      _ModuleGroup(
        key: ValueKey(module.id),
        module: module,
        children: children,
        initiallyExpanded: selectedModule,
        selectedPath: selectedModule ? widget.selectedPath : null,
        onSelectedPath: (path) => widget.onSelectLeaf(module.id, path),
      ),
    );
    return true;
  }
}

class EnterpriseSidebarSection {
  const EnterpriseSidebarSection({
    required this.label,
    required this.moduleIds,
  });

  final String label;
  final List<AppModule> moduleIds;
}

/// Top-level "CollapsibleGroup": one module entry that expands in place to
/// reveal its children, instead of opening a second panel.
class _ModuleGroup extends StatefulWidget {
  const _ModuleGroup({
    super.key,
    required this.module,
    required this.children,
    required this.initiallyExpanded,
    required this.selectedPath,
    required this.onSelectedPath,
  });

  final ModuleDefinition module;
  final List<WorkspaceNavigationNode> children;
  final bool initiallyExpanded;
  final String? selectedPath;
  final ValueChanged<String> onSelectedPath;

  @override
  State<_ModuleGroup> createState() => _ModuleGroupState();
}

class _ModuleGroupState extends State<_ModuleGroup> {
  late bool _expanded = widget.initiallyExpanded;

  @override
  void didUpdateWidget(covariant _ModuleGroup oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.initiallyExpanded && !oldWidget.initiallyExpanded) {
      _expanded = true;
    }
  }

  @override
  Widget build(BuildContext context) => Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          initiallyExpanded: _expanded,
          onExpansionChanged: (value) => setState(() => _expanded = value),
          leading: Icon(widget.module.icon),
          title: Text(widget.module.label),
          childrenPadding: const EdgeInsets.only(left: 8),
          children: [
            for (final WorkspaceNavigationNode node in widget.children)
              CollapsibleGroupTile(
                node: node,
                selectedPath: widget.selectedPath,
                onSelected: widget.onSelectedPath,
                depth: 0,
              ),
          ],
        ),
      );
}

/// Reusable non-scrolling tree tile ("CollapsibleGroup" primitive). Safe to
/// nest inside `ExpansionTile.children` or a `PopupMenuItem` because it never
/// introduces its own scrollable viewport.
class CollapsibleGroupTile extends StatelessWidget {
  const CollapsibleGroupTile({
    super.key,
    required this.node,
    required this.selectedPath,
    required this.onSelected,
    required this.depth,
  });

  final WorkspaceNavigationNode node;
  final String? selectedPath;
  final ValueChanged<String> onSelected;
  final int depth;

  bool get _selected => node.path != null && selectedPath == node.path;

  bool get _hasSelectedDescendant {
    bool search(WorkspaceNavigationNode current) => current.children.any(
          (child) => child.path == selectedPath || search(child),
        );
    return search(node);
  }

  @override
  Widget build(BuildContext context) {
    if (node.children.isEmpty) {
      return ListTile(
        contentPadding: EdgeInsets.only(left: 16.0 + (depth * 12), right: 8),
        dense: true,
        enabled: node.available,
        selected: _selected,
        leading: node.icon == null ? null : Icon(node.icon, size: 18),
        title: Text(node.label),
        trailing: node.badge == null
            ? null
            : StatusBadge(label: node.badge!, tone: StatusBadgeTone.info),
        onTap: !node.available || node.path == null
            ? null
            : () => onSelected(node.path!),
      );
    }
    return Padding(
      padding: EdgeInsets.only(left: depth * 12.0),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          initiallyExpanded: _selected || _hasSelectedDescendant,
          dense: true,
          enabled: node.available,
          leading: node.icon == null ? null : Icon(node.icon, size: 18),
          title: Text(node.label),
          childrenPadding: const EdgeInsets.only(left: 8),
          children: [
            for (final WorkspaceNavigationNode child in node.children)
              CollapsibleGroupTile(
                node: child,
                selectedPath: selectedPath,
                onSelected: onSelected,
                depth: depth + 1,
              ),
          ],
        ),
      ),
    );
  }
}

/// "FlyoutMenu": shown when the sidebar is collapsed to icons only, similar
/// to the collapsed-rail behavior of Visual Studio, Outlook, and the Azure
/// Portal. Renders the same navigation nodes as the expanded tree so the two
/// modes never fall out of sync.
Future<void> showFlyoutMenu({
  required BuildContext context,
  required String title,
  required List<WorkspaceNavigationNode> nodes,
  required String? selectedPath,
  required ValueChanged<String> onSelected,
}) {
  final RenderBox button = context.findRenderObject() as RenderBox;
  final RenderBox overlay =
      Navigator.of(context).overlay!.context.findRenderObject() as RenderBox;
  final Offset anchor =
      button.localToGlobal(Offset(button.size.width, 0), ancestor: overlay);
  final RelativeRect position = RelativeRect.fromLTRB(
    anchor.dx,
    anchor.dy,
    overlay.size.width - anchor.dx,
    0,
  );
  return showMenu<void>(
    context: context,
    position: position,
    constraints: const BoxConstraints(minWidth: 260, maxWidth: 320),
    items: [
      PopupMenuItem<void>(
        enabled: false,
        child: Text(title, style: Theme.of(context).textTheme.titleSmall),
      ),
      const PopupMenuDivider(height: 8),
      PopupMenuItem<void>(
        enabled: false,
        padding: EdgeInsets.zero,
        child: SizedBox(
          width: 280,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (final WorkspaceNavigationNode node in nodes)
                CollapsibleGroupTile(
                  node: node,
                  selectedPath: selectedPath,
                  onSelected: (path) {
                    Navigator.of(context).pop();
                    onSelected(path);
                  },
                  depth: 0,
                ),
            ],
          ),
        ),
      ),
    ],
  );
}
