import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import 'workspace_components.dart';

class WorkspaceNavigationNode {
  const WorkspaceNavigationNode({
    required this.label,
    this.path,
    this.icon,
    this.children = const [],
    this.available = true,
    this.badge,
  });

  final String label;
  final String? path;
  final IconData? icon;
  final List<WorkspaceNavigationNode> children;
  final bool available;
  final String? badge;

  bool get isLeaf => children.isEmpty;
}

class WorkspaceNavigationTree extends StatelessWidget {
  const WorkspaceNavigationTree({
    super.key,
    required this.nodes,
    required this.selectedPath,
    required this.onSelected,
    this.padding = const EdgeInsets.all(12),
  });

  final List<WorkspaceNavigationNode> nodes;
  final String? selectedPath;
  final ValueChanged<String> onSelected;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) => ListView(
        padding: padding,
        children: [
          for (final WorkspaceNavigationNode node in nodes)
            _NavigationNodeTile(
              node: node,
              selectedPath: selectedPath,
              onSelected: onSelected,
              depth: 0,
            ),
        ],
      );
}

class _NavigationNodeTile extends StatelessWidget {
  const _NavigationNodeTile({
    required this.node,
    required this.selectedPath,
    required this.onSelected,
    required this.depth,
  });

  final WorkspaceNavigationNode node;
  final String? selectedPath;
  final ValueChanged<String> onSelected;
  final int depth;

  bool get _selected =>
      node.path != null &&
      (selectedPath == node.path ||
          (selectedPath != null && selectedPath!.startsWith('${node.path}/')));

  bool get _hasSelectedDescendant {
    bool hasSelectedDescendant(WorkspaceNavigationNode current) {
      for (final WorkspaceNavigationNode child in current.children) {
        final bool childSelected = child.path != null &&
            (selectedPath == child.path ||
                (selectedPath != null &&
                    selectedPath!.startsWith('${child.path}/')));
        if (childSelected || hasSelectedDescendant(child)) {
          return true;
        }
      }
      return false;
    }

    return hasSelectedDescendant(node);
  }

  @override
  Widget build(BuildContext context) {
    final EdgeInsetsGeometry tilePadding =
        EdgeInsets.only(left: 8.0 * depth, right: 8, top: 2, bottom: 2);
    if (node.children.isEmpty) {
      return Padding(
        padding: tilePadding,
        child: ListTile(
          enabled: node.available,
          selected: _selected,
          leading: node.icon == null ? null : Icon(node.icon, size: 20),
          title: Text(node.label),
          trailing: node.badge == null
              ? null
              : StatusBadge(label: node.badge!, tone: StatusBadgeTone.info),
          onTap: !node.available || node.path == null
              ? null
              : () => onSelected(node.path!),
        ),
      );
    }
    return Padding(
      padding: tilePadding,
      child: ExpansionTile(
        enabled: node.available,
        initiallyExpanded: _selected || _hasSelectedDescendant,
        leading: node.icon == null ? null : Icon(node.icon, size: 20),
        title: Text(node.label),
        children: [
          for (final WorkspaceNavigationNode child in node.children)
            _NavigationNodeTile(
              node: child,
              selectedPath: selectedPath,
              onSelected: onSelected,
              depth: depth + 1,
            ),
        ],
      ),
    );
  }
}

class EnterpriseWorkspace extends StatelessWidget {
  const EnterpriseWorkspace({
    super.key,
    required this.title,
    required this.description,
    this.navigation,
    required this.content,
    this.toolbar,
    this.statusBar,
    this.leadingActions = const [],
    this.breadcrumbs = const [],
    this.navigationWidth = 320,
  });

  final String title;
  final String description;

  /// Optional in-workspace sub-navigation. Leave null when the module's
  /// sub-navigation already lives in the unified `EnterpriseSidebar` tree —
  /// that is the standard for every module going forward, so business data
  /// gets the full workspace width instead of a second permanent panel.
  final Widget? navigation;
  final Widget content;
  final Widget? toolbar;
  final Widget? statusBar;
  final List<Widget> leadingActions;
  final List<String> breadcrumbs;
  final double navigationWidth;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return LayoutBuilder(
      builder: (context, constraints) {
        final bool wide =
            constraints.maxWidth >= AppDimensions.compactBreakpoint;
        final Widget body = Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.xl,
                AppSpacing.xl,
                AppSpacing.xl,
                AppSpacing.md,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (breadcrumbs.isNotEmpty) ...[
                    WorkspaceBreadcrumbs(items: breadcrumbs),
                    const SizedBox(height: AppSpacing.sm),
                  ],
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(title, style: theme.textTheme.headlineMedium),
                            const SizedBox(height: AppSpacing.xs),
                            Text(description,
                                style: theme.textTheme.bodyMedium),
                          ],
                        ),
                      ),
                      if (leadingActions.isNotEmpty) ...[
                        const SizedBox(width: AppSpacing.lg),
                        Wrap(spacing: AppSpacing.sm, children: leadingActions),
                      ],
                    ],
                  ),
                  if (toolbar != null) ...[
                    const SizedBox(height: AppSpacing.lg),
                    toolbar!,
                  ],
                ],
              ),
            ),
            Expanded(child: content),
            if (statusBar != null) statusBar!,
          ],
        );

        if (!wide) {
          return Scaffold(
            appBar: AppBar(
              title: Text(title),
              actions: leadingActions,
            ),
            drawer: navigation == null ? null : Drawer(child: navigation),
            body: body,
          );
        }

        if (navigation == null) {
          return Scaffold(body: body);
        }

        return Scaffold(
          body: Row(
            children: [
              SizedBox(width: navigationWidth, child: navigation),
              const VerticalDivider(width: 1),
              Expanded(child: body),
            ],
          ),
        );
      },
    );
  }
}

class ConfigurationWorkspace extends StatelessWidget {
  const ConfigurationWorkspace({
    super.key,
    required this.title,
    required this.description,
    this.navigation,
    required this.content,
    this.toolbar,
    this.statusBar,
    this.breadcrumbs = const [],
    this.leadingActions = const [],
    this.navigationWidth = 320,
  });

  final String title;
  final String description;
  final Widget? navigation;
  final Widget content;
  final Widget? toolbar;
  final Widget? statusBar;
  final List<String> breadcrumbs;
  final List<Widget> leadingActions;
  final double navigationWidth;

  @override
  Widget build(BuildContext context) => EnterpriseWorkspace(
        title: title,
        description: description,
        navigation: navigation,
        content: content,
        toolbar: toolbar,
        statusBar: statusBar,
        breadcrumbs: breadcrumbs,
        leadingActions: leadingActions,
        navigationWidth: navigationWidth,
      );
}

class MasterManagementWorkspace extends StatelessWidget {
  const MasterManagementWorkspace({
    super.key,
    required this.title,
    required this.description,
    required this.grid,
    required this.detailsPanel,
    this.toolbar,
    this.search,
    this.filterPanel,
    this.summaryCards,
    this.statusBar,
    this.breadcrumbs = const [],
    this.leadingActions = const [],
    this.detailsWidth = 320,
  });

  final String title;
  final String description;
  final Widget grid;
  final Widget detailsPanel;
  final Widget? toolbar;
  final Widget? search;
  final Widget? filterPanel;
  final Widget? summaryCards;
  final Widget? statusBar;
  final List<String> breadcrumbs;
  final List<Widget> leadingActions;
  final double detailsWidth;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.xl,
              AppSpacing.xl,
              AppSpacing.xl,
              AppSpacing.md,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (breadcrumbs.isNotEmpty) ...[
                  WorkspaceBreadcrumbs(items: breadcrumbs),
                  const SizedBox(height: AppSpacing.sm),
                ],
                PageHeader(
                  title: title,
                  description: description,
                  actions: leadingActions,
                ),
                if (summaryCards != null) ...[
                  const SizedBox(height: AppSpacing.lg),
                  summaryCards!,
                ],
                if (search != null || toolbar != null) ...[
                  const SizedBox(height: AppSpacing.lg),
                  LayoutBuilder(
                    builder: (context, constraints) {
                      if (constraints.maxWidth <
                          AppDimensions.controlsWrapBreakpoint) {
                        return Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            if (search != null) search!,
                            if (search != null && toolbar != null)
                              const SizedBox(height: AppSpacing.sm),
                            if (toolbar != null) toolbar!,
                          ],
                        );
                      }
                      return Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (search != null) Expanded(child: search!),
                          if (search != null && toolbar != null)
                            const SizedBox(width: AppSpacing.md),
                          if (toolbar != null) toolbar!,
                        ],
                      );
                    },
                  ),
                ],
                if (filterPanel != null) ...[
                  const SizedBox(height: AppSpacing.md),
                  filterPanel!,
                ],
              ],
            ),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl),
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final double panelWidth = detailsWidth
                      .clamp(240, constraints.maxWidth * .38)
                      .toDouble();
                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Expanded(child: grid),
                      const SizedBox(width: AppSpacing.lg),
                      SizedBox(width: panelWidth, child: detailsPanel),
                    ],
                  );
                },
              ),
            ),
          ),
          if (statusBar != null) statusBar!,
        ],
      ),
    );
  }
}

class TransactionWorkspace extends StatelessWidget {
  const TransactionWorkspace({
    super.key,
    required this.title,
    required this.description,
    required this.grid,
    required this.documentPreview,
    this.toolbar,
    this.search,
    this.filterPanel,
    this.summaryCards,
    this.historyPanel,
    this.timelinePanel,
    this.statusBar,
    this.breadcrumbs = const [],
    this.leadingActions = const [],
    this.previewWidth = 360,
  });

  final String title;
  final String description;
  final Widget grid;
  final Widget documentPreview;
  final Widget? toolbar;
  final Widget? search;
  final Widget? filterPanel;
  final Widget? summaryCards;
  final Widget? historyPanel;
  final Widget? timelinePanel;
  final Widget? statusBar;
  final List<String> breadcrumbs;
  final List<Widget> leadingActions;
  final double previewWidth;

  @override
  Widget build(BuildContext context) {
    final List<Widget> rightRail = [
      documentPreview,
      if (historyPanel != null) ...[
        const SizedBox(height: AppSpacing.lg),
        historyPanel!,
      ],
      if (timelinePanel != null) ...[
        const SizedBox(height: AppSpacing.lg),
        timelinePanel!,
      ],
    ];
    return MasterManagementWorkspace(
      title: title,
      description: description,
      grid: grid,
      detailsPanel: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: rightRail,
      ),
      toolbar: toolbar,
      search: search,
      filterPanel: filterPanel,
      summaryCards: summaryCards,
      statusBar: statusBar,
      breadcrumbs: breadcrumbs,
      leadingActions: leadingActions,
      detailsWidth: previewWidth,
    );
  }
}

class ReportWorkspace extends StatelessWidget {
  const ReportWorkspace({
    super.key,
    required this.title,
    required this.description,
    required this.body,
    this.toolbar,
    this.filters,
    this.summaryCards,
    this.statusBar,
    this.breadcrumbs = const [],
    this.leadingActions = const [],
  });

  final String title;
  final String description;
  final Widget body;
  final Widget? toolbar;
  final Widget? filters;
  final Widget? summaryCards;
  final Widget? statusBar;
  final List<String> breadcrumbs;
  final List<Widget> leadingActions;

  @override
  Widget build(BuildContext context) => WorkspaceLayout(
        title: title,
        description: description,
        breadcrumbs: breadcrumbs,
        headerActions: leadingActions,
        toolbar: toolbar,
        filterPanel: filters,
        statusBar: statusBar,
        content: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (summaryCards != null) ...[
              Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.xl,
                  0,
                  AppSpacing.xl,
                  AppSpacing.md,
                ),
                child: summaryCards!,
              ),
            ],
            Expanded(child: body),
          ],
        ),
      );
}

class DashboardWorkspace extends StatelessWidget {
  const DashboardWorkspace({
    super.key,
    required this.title,
    required this.description,
    required this.body,
    this.toolbar,
    this.statusBar,
    this.breadcrumbs = const [],
    this.leadingActions = const [],
  });

  final String title;
  final String description;
  final Widget body;
  final Widget? toolbar;
  final Widget? statusBar;
  final List<String> breadcrumbs;
  final List<Widget> leadingActions;

  @override
  Widget build(BuildContext context) => WorkspaceLayout(
        title: title,
        description: description,
        breadcrumbs: breadcrumbs,
        headerActions: leadingActions,
        toolbar: toolbar,
        statusBar: statusBar,
        content: body,
      );
}

class SettingsWorkspace extends StatelessWidget {
  const SettingsWorkspace({
    super.key,
    required this.title,
    required this.description,
    required this.body,
    this.toolbar,
    this.statusBar,
    this.breadcrumbs = const [],
    this.leadingActions = const [],
  });

  final String title;
  final String description;
  final Widget body;
  final Widget? toolbar;
  final Widget? statusBar;
  final List<String> breadcrumbs;
  final List<Widget> leadingActions;

  @override
  Widget build(BuildContext context) => WorkspaceLayout(
        title: title,
        description: description,
        breadcrumbs: breadcrumbs,
        headerActions: leadingActions,
        toolbar: toolbar,
        statusBar: statusBar,
        content: body,
      );
}
