import 'package:flutter/material.dart';

import '../../core/dialogs/app_dialogs.dart';

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
  });

  final TextEditingController controller;
  final ValueChanged<String> onSearch;
  final List<Widget>? filters;
  final String hintText;

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: 12,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 360),
            child: TextField(
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

class ManagementWorkspaceLayout extends StatelessWidget {
  const ManagementWorkspaceLayout({
    super.key,
    required this.toolbar,
    required this.searchPanel,
    required this.primaryContent,
    required this.detailsPanel,
    required this.statusBar,
    this.detailsWidth = 300,
  });

  final Widget toolbar;
  final Widget searchPanel;
  final Widget primaryContent;
  final Widget detailsPanel;
  final Widget statusBar;
  final double detailsWidth;

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
                  items: items,
                  total: total,
                  pageOffset: pageOffset,
                  id: id,
                  cells: cells,
                  visibleColumnIndexes:
                      visibleColumns.map((entry) => entry.key).toList(),
                  selectedId: selectedId,
                  onSelect: onSelect,
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
    required this.items,
    required this.total,
    required this.pageOffset,
    required this.id,
    required this.cells,
    required this.visibleColumnIndexes,
    required this.selectedId,
    required this.onSelect,
  });
  final List<T> items;
  final int total;
  final int pageOffset;
  final String Function(T) id;
  final List<String> Function(T) cells;
  final List<int> visibleColumnIndexes;
  final String? selectedId;
  final ValueChanged<T> onSelect;

  @override
  DataRow? getRow(int index) {
    final int localIndex = index - pageOffset;
    if (localIndex < 0 || localIndex >= items.length) return null;
    final T item = items[localIndex];
    return DataRow.byIndex(
      index: index,
      selected: selectedId == id(item),
      onSelectChanged: (_) => onSelect(item),
      cells: visibleColumnIndexes.map((columnIndex) {
        final List<String> values = cells(item);
        final String value =
            columnIndex < values.length ? values[columnIndex] : '';
        return DataCell(
          Tooltip(
            message: value,
            child: Text(value, overflow: TextOverflow.ellipsis),
          ),
          onTap: () => onSelect(item),
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

class WorkspaceLoadingState extends StatelessWidget {
  const WorkspaceLoadingState({super.key});
  @override
  Widget build(BuildContext context) =>
      const Center(child: CircularProgressIndicator());
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
  });
  final String title;
  final String message;
  final IconData icon;
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
          ]),
        ),
      );
}

Future<bool> showWorkspaceConfirmDialog(
  BuildContext context, {
  required String title,
  required String message,
  String confirmLabel = 'Confirm',
}) =>
    AppDialogs.confirm(
      context,
      title: title,
      message: message,
      confirmLabel: confirmLabel,
    );
