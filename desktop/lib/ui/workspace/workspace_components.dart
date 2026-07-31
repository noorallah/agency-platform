import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../../core/dialogs/app_dialogs.dart';
import 'workspace_interactions.dart';

class PageHeader extends StatelessWidget {
  const PageHeader({
    super.key,
    required this.title,
    this.description,
    this.actions = const [],
  });

  final String title;
  final String? description;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.headlineMedium),
                if (description != null) ...[
                  const SizedBox(height: AppSpacing.xs),
                  Text(description!,
                      style: Theme.of(context).textTheme.bodyMedium),
                ],
              ],
            ),
          ),
          if (actions.isNotEmpty) ...[
            const SizedBox(width: AppSpacing.lg),
            Wrap(spacing: AppSpacing.sm, children: actions),
          ],
        ],
      );
}

class SectionHeader extends StatelessWidget {
  const SectionHeader({
    super.key,
    required this.title,
    this.description,
    this.trailing,
  });

  final String title;
  final String? description;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Row(children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              if (description != null) Text(description!),
            ],
          ),
        ),
        if (trailing != null) trailing!,
      ]);
}

class WorkspaceLayout extends StatelessWidget {
  const WorkspaceLayout({
    super.key,
    required this.title,
    required this.content,
    this.description,
    this.breadcrumbs = const [],
    this.toolbar,
    this.search,
    this.filterPanel,
    this.statusBar,
    this.headerActions = const [],
  });

  final String title;
  final String? description;
  final List<String> breadcrumbs;
  final Widget? toolbar;
  final Widget? search;
  final Widget? filterPanel;
  final Widget content;
  final Widget? statusBar;
  final List<Widget> headerActions;

  @override
  Widget build(BuildContext context) => SafeArea(
        child: Column(children: [
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
                  actions: headerActions,
                ),
                if (toolbar != null || search != null) ...[
                  const SizedBox(height: AppSpacing.lg),
                  LayoutBuilder(
                    builder: (context, constraints) {
                      final List<Widget> controls = [
                        if (search != null) Expanded(child: search!),
                        if (toolbar != null) toolbar!,
                      ];
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
                          ...controls.expand(
                            (control) => [
                              control,
                              if (control != controls.last)
                                const SizedBox(width: AppSpacing.md),
                            ],
                          ),
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
          Expanded(child: content),
          if (statusBar != null) statusBar!,
        ]),
      );
}

class WorkspaceBreadcrumbs extends StatelessWidget {
  const WorkspaceBreadcrumbs({super.key, required this.items});
  final List<String> items;

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: 6,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          for (var index = 0; index < items.length; index++) ...[
            Text(
              items[index],
              style: index == items.length - 1
                  ? Theme.of(context).textTheme.bodySmall
                  : Theme.of(context)
                      .textTheme
                      .bodySmall
                      ?.copyWith(color: Theme.of(context).colorScheme.primary),
            ),
            if (index != items.length - 1)
              const Icon(Icons.chevron_right, size: 16),
          ],
        ],
      );
}

class ModuleWorkspaceFrame extends StatelessWidget {
  const ModuleWorkspaceFrame({
    super.key,
    required this.title,
    required this.description,
    required this.child,
    this.breadcrumbs = const [],
    this.tabs,
    this.selectedTab = 0,
    this.onTabChanged,
    this.status,
  });

  final String title;
  final String description;
  final Widget child;
  final List<String> breadcrumbs;
  final List<WorkspaceTab>? tabs;
  final int selectedTab;
  final ValueChanged<int>? onTabChanged;
  final Widget? status;

  @override
  Widget build(BuildContext context) {
    final List<WorkspaceTab> workspaceTabs = tabs ?? const [];
    return SafeArea(
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 20, 24, 12),
          child: Align(
            alignment: Alignment.centerLeft,
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (breadcrumbs.isNotEmpty) ...[
                WorkspaceBreadcrumbs(items: breadcrumbs),
                const SizedBox(height: 8),
              ],
              Text(title, style: Theme.of(context).textTheme.headlineMedium),
              const SizedBox(height: 4),
              Text(description, style: Theme.of(context).textTheme.bodyMedium),
            ]),
          ),
        ),
        if (workspaceTabs.isNotEmpty)
          Align(
            alignment: Alignment.centerLeft,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: SegmentedButton<int>(
                  segments: [
                    for (var index = 0; index < workspaceTabs.length; index++)
                      ButtonSegment(
                        value: index,
                        label: Text(workspaceTabs[index].label),
                        enabled: workspaceTabs[index].available,
                      ),
                  ],
                  selected: {selectedTab.clamp(0, workspaceTabs.length - 1)},
                  onSelectionChanged: onTabChanged == null
                      ? null
                      : (selection) => onTabChanged!(selection.first),
                  showSelectedIcon: false,
                ),
              ),
            ),
          ),
        const SizedBox(height: 12),
        Expanded(child: child),
        if (status != null) status!,
      ]),
    );
  }
}

class WorkspaceTab {
  const WorkspaceTab({
    required this.label,
    this.available = true,
  });
  final String label;
  final bool available;
}

enum ToolbarAction {
  newItem,
  edit,
  delete,
  view,
  refresh,
  import,
  export,
  print,
  settings
}

extension ToolbarActionDetails on ToolbarAction {
  String get label => switch (this) {
        ToolbarAction.newItem => 'New',
        ToolbarAction.edit => 'Edit',
        ToolbarAction.delete => 'Delete',
        ToolbarAction.view => 'View',
        ToolbarAction.refresh => 'Refresh',
        ToolbarAction.import => 'Import',
        ToolbarAction.export => 'Export',
        ToolbarAction.print => 'Print',
        ToolbarAction.settings => 'Settings',
      };
  IconData get icon => switch (this) {
        ToolbarAction.newItem => Icons.add,
        ToolbarAction.edit => Icons.edit_outlined,
        ToolbarAction.delete => Icons.delete_outline,
        ToolbarAction.view => Icons.visibility_outlined,
        ToolbarAction.refresh => Icons.refresh,
        ToolbarAction.import => Icons.file_upload_outlined,
        ToolbarAction.export => Icons.file_download_outlined,
        ToolbarAction.print => Icons.print_outlined,
        ToolbarAction.settings => Icons.settings_outlined,
      };
}

class WorkspaceToolbar extends StatelessWidget {
  const WorkspaceToolbar({
    super.key,
    required this.onAction,
    required this.isEnabled,
    this.isVisible,
    this.actions = ToolbarAction.values,
  });

  final ValueChanged<ToolbarAction> onAction;
  final bool Function(ToolbarAction) isEnabled;
  final bool Function(ToolbarAction)? isVisible;
  final List<ToolbarAction> actions;

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: 4,
        runSpacing: 4,
        children: actions
            .where((action) => isVisible?.call(action) ?? true)
            .map(
              (action) => Tooltip(
                message: action.label,
                child: action == ToolbarAction.newItem
                    ? FilledButton.icon(
                        onPressed:
                            isEnabled(action) ? () => onAction(action) : null,
                        icon: Icon(action.icon),
                        label: Text(action.label),
                      )
                    : IconButton(
                        onPressed:
                            isEnabled(action) ? () => onAction(action) : null,
                        icon: Icon(action.icon),
                      ),
              ),
            )
            .toList(),
      );
}

class SearchFilterPanel extends StatelessWidget {
  const SearchFilterPanel({
    super.key,
    required this.controller,
    required this.onSearch,
    this.filters,
    this.hintText = 'Search',
    this.focusNode,
  });

  final TextEditingController controller;
  final ValueChanged<String> onSearch;
  final List<Widget>? filters;
  final String hintText;
  final FocusNode? focusNode;

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: 12,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 360),
            child: TextField(
              focusNode: focusNode,
              controller: controller,
              onSubmitted: onSearch,
              decoration: InputDecoration(
                hintText: hintText,
                prefixIcon: const Icon(Icons.search),
                suffixIcon: IconButton(
                  tooltip: 'Search',
                  icon: const Icon(Icons.search),
                  onPressed: () => onSearch(controller.text),
                ),
              ),
            ),
          ),
          if (filters != null) ...filters!,
        ],
      );
}

class FilterPanel extends StatelessWidget {
  const FilterPanel({
    super.key,
    required this.children,
    this.expanded = false,
    this.activeFilterCount = 0,
    this.onClear,
    this.onApply,
    this.onExpandedChanged,
  });

  final List<Widget> children;
  final bool expanded;
  final int activeFilterCount;
  final VoidCallback? onClear;
  final VoidCallback? onApply;
  final ValueChanged<bool>? onExpandedChanged;

  @override
  Widget build(BuildContext context) => ExpansionTile(
        initiallyExpanded: expanded,
        onExpansionChanged: onExpandedChanged,
        leading: const Icon(Icons.filter_alt_outlined),
        title: Text(
          activeFilterCount == 0
              ? 'Filters'
              : 'Filters ($activeFilterCount active)',
        ),
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.lg,
              0,
              AppSpacing.lg,
              AppSpacing.lg,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Wrap(
                  spacing: AppSpacing.md,
                  runSpacing: AppSpacing.md,
                  children: children,
                ),
                const SizedBox(height: AppSpacing.md),
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    TextButton(
                      onPressed: activeFilterCount == 0 ? null : onClear,
                      child: const Text('Clear filters'),
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    FilledButton.tonal(
                      onPressed: onApply,
                      child: const Text('Apply filters'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      );
}

class ManagementWorkspaceLayout extends StatelessWidget {
  const ManagementWorkspaceLayout({
    super.key,
    required this.toolbar,
    required this.searchPanel,
    required this.primaryContent,
    required this.detailsPanel,
    required this.statusBar,
    this.detailsWidth = 300,
    this.filterPanel,
  });

  final Widget toolbar;
  final Widget searchPanel;
  final Widget primaryContent;
  final Widget detailsPanel;
  final Widget statusBar;
  final double detailsWidth;
  final Widget? filterPanel;

  @override
  Widget build(BuildContext context) => Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 12, 24, 0),
          child: LayoutBuilder(
            builder: (context, constraints) {
              if (constraints.maxWidth < 900) {
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    searchPanel,
                    const SizedBox(height: 8),
                    toolbar,
                  ],
                );
              }
              return Row(children: [
                Expanded(child: searchPanel),
                const SizedBox(width: 12),
                toolbar,
              ]);
            },
          ),
        ),
        if (filterPanel != null) filterPanel!,
        const SizedBox(height: 8),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: LayoutBuilder(
              builder: (context, constraints) {
                final double panelWidth =
                    detailsWidth.clamp(240, constraints.maxWidth * .36);
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(child: primaryContent),
                    const SizedBox(width: 16),
                    SizedBox(width: panelWidth, child: detailsPanel),
                  ],
                );
              },
            ),
          ),
        ),
        statusBar,
      ]);
}

class GridColumn {
  const GridColumn({
    required this.label,
    this.onSort,
    this.visible = true,
  });
  final String label;
  final void Function(bool ascending)? onSort;
  final bool visible;
}

class EnterpriseDataGrid<T> extends StatelessWidget {
  const EnterpriseDataGrid({
    super.key,
    required this.items,
    required this.total,
    required this.pageOffset,
    required this.columns,
    required this.id,
    required this.cells,
    required this.onSelect,
    required this.onPageChanged,
    this.selectedId,
    this.rowsPerPage = 20,
    this.onOpen,
    this.contextActions = const [],
    this.contextActionsFor,
    this.onContextAction,
  });

  final List<T> items;
  final int total;
  final int pageOffset;
  final List<GridColumn> columns;
  final String Function(T) id;
  final List<String> Function(T) cells;
  final ValueChanged<T> onSelect;
  final ValueChanged<int> onPageChanged;
  final String? selectedId;
  final int rowsPerPage;
  final ValueChanged<T>? onOpen;
  final List<WorkspaceContextAction> contextActions;
  final List<WorkspaceContextAction> Function(T item)? contextActionsFor;
  final void Function(WorkspaceContextAction action, T item)? onContextAction;

  @override
  Widget build(BuildContext context) {
    final List<MapEntry<int, GridColumn>> visibleColumns =
        columns.asMap().entries.where((entry) => entry.value.visible).toList();
    return Card(
      clipBehavior: Clip.antiAlias,
      child: LayoutBuilder(
        builder: (context, constraints) => SingleChildScrollView(
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: SizedBox(
              width: constraints.maxWidth < 720 ? 720 : constraints.maxWidth,
              child: PaginatedDataTable(
                key: ValueKey(pageOffset),
                showCheckboxColumn: true,
                rowsPerPage: rowsPerPage,
                availableRowsPerPage: [rowsPerPage],
                initialFirstRowIndex: pageOffset,
                showFirstLastButtons: true,
                onPageChanged: onPageChanged,
                columns: [
                  for (final MapEntry<int, GridColumn> entry in visibleColumns)
                    DataColumn(
                      label: Text(entry.value.label),
                      onSort: entry.value.onSort == null
                          ? null
                          : (_, ascending) => entry.value.onSort!(ascending),
                    ),
                ],
                source: _GridDataSource<T>(
                  menuContext: context,
                  items: items,
                  total: total,
                  pageOffset: pageOffset,
                  id: id,
                  cells: cells,
                  visibleColumnIndexes:
                      visibleColumns.map((entry) => entry.key).toList(),
                  selectedId: selectedId,
                  onSelect: onSelect,
                  onOpen: onOpen,
                  contextActions: contextActions,
                  contextActionsFor: contextActionsFor,
                  onContextAction: onContextAction,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _GridDataSource<T> extends DataTableSource {
  _GridDataSource({
    required this.menuContext,
    required this.items,
    required this.total,
    required this.pageOffset,
    required this.id,
    required this.cells,
    required this.visibleColumnIndexes,
    required this.selectedId,
    required this.onSelect,
    required this.onOpen,
    required this.contextActions,
    required this.contextActionsFor,
    required this.onContextAction,
  });
  final BuildContext menuContext;
  final List<T> items;
  final int total;
  final int pageOffset;
  final String Function(T) id;
  final List<String> Function(T) cells;
  final List<int> visibleColumnIndexes;
  final String? selectedId;
  final ValueChanged<T> onSelect;
  final ValueChanged<T>? onOpen;
  final List<WorkspaceContextAction> contextActions;
  final List<WorkspaceContextAction> Function(T item)? contextActionsFor;
  final void Function(WorkspaceContextAction action, T item)? onContextAction;

  @override
  DataRow? getRow(int index) {
    final int localIndex = index - pageOffset;
    if (localIndex < 0 || localIndex >= items.length) return null;
    final T item = items[localIndex];
    final List<String> values = cells(item);
    final List<WorkspaceContextAction> itemContextActions =
        contextActionsFor?.call(item) ?? contextActions;
    return DataRow.byIndex(
      index: index,
      selected: selectedId == id(item),
      onSelectChanged: (_) => onSelect(item),
      cells: visibleColumnIndexes.map((columnIndex) {
        final String value =
            columnIndex < values.length ? values[columnIndex] : '';
        return DataCell(
          GestureDetector(
            behavior: HitTestBehavior.opaque,
            onSecondaryTapDown: itemContextActions.isEmpty
                ? null
                : (details) {
                    onSelect(item);
                    showWorkspaceContextMenu(
                      menuContext,
                      position: details.globalPosition,
                      actions: itemContextActions,
                      onSelected: (action) =>
                          onContextAction?.call(action, item),
                    );
                  },
            child: Tooltip(
              message: value,
              child: SizedBox(
                width: double.infinity,
                child: Text(value, overflow: TextOverflow.ellipsis),
              ),
            ),
          ),
          onTap: () => onSelect(item),
          onDoubleTap: onOpen == null ? null : () => onOpen!(item),
        );
      }).toList(),
    );
  }

  @override
  bool get isRowCountApproximate => false;
  @override
  int get rowCount => total;
  @override
  int get selectedRowCount => selectedId == null ? 0 : 1;
}

class DetailLine {
  const DetailLine(this.label, this.value);
  final String label;
  final String value;
}

class QuickSummaryPanel extends StatelessWidget {
  const QuickSummaryPanel({
    super.key,
    required this.title,
    required this.lines,
    this.onView,
    this.onEdit,
  });

  final String title;
  final List<DetailLine> lines;
  final VoidCallback? onView;
  final VoidCallback? onEdit;

  @override
  Widget build(BuildContext context) => Card(
        clipBehavior: Clip.antiAlias,
        child: Column(children: [
          Expanded(
            child: lines.isEmpty
                ? Center(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Text(
                        title,
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                    ),
                  )
                : SingleChildScrollView(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        const Divider(),
                        for (final DetailLine line in lines)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 12),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  line.label,
                                  style:
                                      Theme.of(context).textTheme.labelMedium,
                                ),
                                const SizedBox(height: 2),
                                SelectableText(line.value),
                              ],
                            ),
                          ),
                      ],
                    ),
                  ),
          ),
          if (onView != null || onEdit != null) ...[
            const Divider(height: 1),
            Padding(
              padding: const EdgeInsets.all(12),
              child: Row(children: [
                if (onView != null)
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: onView,
                      icon: const Icon(Icons.open_in_full),
                      label: const Text('View Details'),
                    ),
                  ),
                if (onView != null && onEdit != null) const SizedBox(width: 8),
                if (onEdit != null)
                  Expanded(
                    child: FilledButton.tonalIcon(
                      onPressed: onEdit,
                      icon: const Icon(Icons.edit_outlined),
                      label: const Text('Edit'),
                    ),
                  ),
              ]),
            ),
          ],
        ]),
      );
}

class DetailsPanel extends StatelessWidget {
  const DetailsPanel({super.key, required this.title, required this.lines});
  final String title;
  final List<DetailLine> lines;

  @override
  Widget build(BuildContext context) => Card(
        clipBehavior: Clip.antiAlias,
        child: lines.isEmpty
            ? Center(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(
                    'Select a record to view its details.',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ),
              )
            : SingleChildScrollView(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: Theme.of(context).textTheme.titleMedium),
                    const Divider(),
                    for (final DetailLine line in lines)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              line.label,
                              style: Theme.of(context).textTheme.labelLarge,
                            ),
                            const SizedBox(height: 2),
                            SelectableText(line.value),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
      );
}

class WorkspaceStatusBar extends StatelessWidget {
  const WorkspaceStatusBar({
    super.key,
    required this.total,
    required this.selected,
    this.message,
  });
  final int total;
  final bool selected;
  final String? message;

  @override
  Widget build(BuildContext context) => Material(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
          child: Row(children: [
            Text('$total record${total == 1 ? '' : 's'}'),
            if (selected) const Text('  |  1 selected'),
            const Spacer(),
            if (message != null) Text(message!),
          ]),
        ),
      );
}

enum ConnectionStateIndicator { online, offline, checking, unknown }

class ApplicationStatusBar extends StatelessWidget {
  const ApplicationStatusBar({
    super.key,
    this.stateText = 'Ready',
    this.currentUser,
    this.currentFirm,
    this.backend = ConnectionStateIndicator.checking,
    this.database = ConnectionStateIndicator.checking,
    this.environment,
    this.version,
    this.selectedRecords = 0,
    this.backgroundTask,
  });

  final String stateText;
  final String? currentUser;
  final String? currentFirm;
  final ConnectionStateIndicator backend;
  final ConnectionStateIndicator database;
  final String? environment;
  final String? version;
  final int selectedRecords;
  final String? backgroundTask;

  @override
  Widget build(BuildContext context) => Material(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        child: SizedBox(
          height: 32,
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
              child: Row(children: [
                _StatusItem(icon: Icons.check_circle_outline, label: stateText),
                if (currentUser != null)
                  _StatusItem(icon: Icons.person_outline, label: currentUser!),
                if (currentFirm != null)
                  _StatusItem(
                      icon: Icons.business_outlined, label: currentFirm!),
                _ConnectionStatus(label: 'API', state: backend),
                _ConnectionStatus(label: 'DB', state: database),
                if (environment != null)
                  _StatusItem(icon: Icons.dns_outlined, label: environment!),
                if (selectedRecords > 0)
                  _StatusItem(
                    icon: Icons.check_box_outlined,
                    label: '$selectedRecords selected',
                  ),
                if (backgroundTask != null)
                  _StatusItem(
                    icon: Icons.sync,
                    label: backgroundTask!,
                  ),
                if (version != null)
                  _StatusItem(icon: Icons.info_outline, label: version!),
              ]),
            ),
          ),
        ),
      );
}

class _StatusItem extends StatelessWidget {
  const _StatusItem({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(right: AppSpacing.lg),
        child: Row(children: [
          Icon(icon, size: 14),
          const SizedBox(width: AppSpacing.xs),
          SelectableText(label, style: Theme.of(context).textTheme.bodySmall),
        ]),
      );
}

class _ConnectionStatus extends StatelessWidget {
  const _ConnectionStatus({required this.label, required this.state});

  final String label;
  final ConnectionStateIndicator state;

  @override
  Widget build(BuildContext context) => _StatusItem(
        icon: switch (state) {
          ConnectionStateIndicator.online => Icons.cloud_done_outlined,
          ConnectionStateIndicator.offline => Icons.cloud_off_outlined,
          ConnectionStateIndicator.checking => Icons.cloud_sync_outlined,
          ConnectionStateIndicator.unknown => Icons.help_outline,
        },
        label: '$label: ${state.name}',
      );
}

class LoadingOverlay extends StatelessWidget {
  const LoadingOverlay({
    super.key,
    required this.loading,
    required this.child,
    this.message,
  });

  final bool loading;
  final Widget child;
  final String? message;

  @override
  Widget build(BuildContext context) => Stack(children: [
        Positioned.fill(child: child),
        if (loading)
          Positioned.fill(
            child: ColoredBox(
              color: Theme.of(context).colorScheme.scrim.withValues(alpha: .18),
              child: Center(
                child: Card(
                  child: Padding(
                    padding: const EdgeInsets.all(AppSpacing.lg),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(strokeWidth: 3),
                        ),
                        if (message != null) ...[
                          const SizedBox(width: AppSpacing.md),
                          Text(message!),
                        ],
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
      ]);
}

class TableLoadingSkeleton extends StatelessWidget {
  const TableLoadingSkeleton({super.key, this.rows = 8, this.columns = 5});

  final int rows;
  final int columns;

  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            children: [
              for (int row = 0; row < rows; row++) ...[
                Row(
                  children: [
                    for (int column = 0; column < columns; column++)
                      Expanded(
                        child: Container(
                          height: 14,
                          margin: const EdgeInsets.all(AppSpacing.sm),
                          decoration: BoxDecoration(
                            color: Theme.of(context)
                                .colorScheme
                                .surfaceContainerHighest,
                            borderRadius: AppRadius.small,
                          ),
                        ),
                      ),
                  ],
                ),
                if (row != rows - 1) const Divider(height: 1),
              ],
            ],
          ),
        ),
      );
}

class WorkspaceLoadingState extends StatelessWidget {
  const WorkspaceLoadingState({super.key, this.message});

  final String? message;

  @override
  Widget build(BuildContext context) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(),
            if (message != null) ...[
              const SizedBox(height: AppSpacing.md),
              Text(message!),
            ],
          ],
        ),
      );
}

class WorkspaceErrorState extends StatelessWidget {
  const WorkspaceErrorState(
      {super.key, required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;
  @override
  Widget build(BuildContext context) => Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(Icons.error_outline,
              size: 48, color: Theme.of(context).colorScheme.error),
          const SizedBox(height: 12),
          Text(message, textAlign: TextAlign.center),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh),
            label: const Text('Try again'),
          ),
        ]),
      );
}

class WorkspaceEmptyState extends StatelessWidget {
  const WorkspaceEmptyState({
    super.key,
    required this.title,
    required this.message,
    this.icon = Icons.inbox_outlined,
    this.action,
  });
  final String title;
  final String message;
  final IconData icon;
  final Widget? action;
  @override
  Widget build(BuildContext context) => Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon, size: 48, color: Theme.of(context).colorScheme.primary),
            const SizedBox(height: 12),
            Text(title, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(message, textAlign: TextAlign.center),
            if (action != null) ...[
              const SizedBox(height: AppSpacing.lg),
              action!,
            ],
          ]),
        ),
      );
}

enum EmptyStateType {
  noRecords,
  noSearchResults,
  noPermissions,
  noInternet,
  noFirmSelected,
  licenseExpired,
}

class StandardEmptyState extends StatelessWidget {
  const StandardEmptyState({
    super.key,
    required this.type,
    this.action,
    this.title,
    this.message,
  });

  final EmptyStateType type;
  final Widget? action;
  final String? title;
  final String? message;

  @override
  Widget build(BuildContext context) => WorkspaceEmptyState(
        title: title ?? _title,
        message: message ?? _message,
        icon: _icon,
        action: action,
      );

  String get _title => switch (type) {
        EmptyStateType.noRecords => 'No records',
        EmptyStateType.noSearchResults => 'No search results',
        EmptyStateType.noPermissions => 'No permission',
        EmptyStateType.noInternet => 'No internet connection',
        EmptyStateType.noFirmSelected => 'No firm selected',
        EmptyStateType.licenseExpired => 'License expired',
      };

  String get _message => switch (type) {
        EmptyStateType.noRecords => 'Create a record to get started.',
        EmptyStateType.noSearchResults =>
          'Try changing or clearing your search and filters.',
        EmptyStateType.noPermissions =>
          'Contact an administrator if you need access.',
        EmptyStateType.noInternet => 'Check the connection and try again.',
        EmptyStateType.noFirmSelected =>
          'Select a firm before opening this workspace.',
        EmptyStateType.licenseExpired =>
          'Renew the license to continue using this workspace.',
      };

  IconData get _icon => switch (type) {
        EmptyStateType.noRecords => Icons.inbox_outlined,
        EmptyStateType.noSearchResults => Icons.search_off_outlined,
        EmptyStateType.noPermissions => Icons.lock_outline,
        EmptyStateType.noInternet => Icons.cloud_off_outlined,
        EmptyStateType.noFirmSelected => Icons.business_outlined,
        EmptyStateType.licenseExpired => Icons.key_off_outlined,
      };
}

Future<bool> showWorkspaceConfirmDialog(
  BuildContext context, {
  required String title,
  required String message,
  String confirmLabel = 'Confirm',
  ConfirmationType type = ConfirmationType.custom,
}) =>
    AppDialogs.confirm(
      context,
      title: title,
      message: message,
      confirmLabel: confirmLabel,
      type: type,
    );
