import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../../core/dialogs/app_dialogs.dart';
import 'workspace_interactions.dart';

/// What to put in a telephone box, for the fields the server checks.
///
/// Firms, customers and vendors all run their numbers through the same E.164
/// validator, whose refusal -- "A valid E.164 phone number is required." --
/// names a standard without showing the shape it wants. One constant so the
/// three forms cannot describe the same rule differently. Spaces, brackets,
/// dots and hyphens are stripped before the check, so grouping is fine.
const String phoneHelperText = 'With country code, e.g. +919876543210.';

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
  Widget build(BuildContext context) => LayoutBuilder(
        builder: (context, constraints) {
          final bool wrapActions =
              !constraints.hasBoundedWidth || constraints.maxWidth < 720;
          final Widget titleBlock = Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.headlineMedium),
              if (description != null) ...[
                const SizedBox(height: AppSpacing.xs),
                Text(
                  description!,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ],
            ],
          );
          if (wrapActions) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                titleBlock,
                if (actions.isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.md),
                  Wrap(
                      spacing: AppSpacing.sm,
                      runSpacing: AppSpacing.sm,
                      children: actions),
                ],
              ],
            );
          }
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: titleBlock),
              if (actions.isNotEmpty) ...[
                const SizedBox(width: AppSpacing.lg),
                Wrap(spacing: AppSpacing.sm, children: actions),
              ],
            ],
          );
        },
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
  Widget build(BuildContext context) => LayoutBuilder(
        builder: (context, constraints) {
          final Widget titleBlock = Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              if (description != null) Text(description!),
            ],
          );
          if (!constraints.hasBoundedWidth || constraints.maxWidth < 720) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                titleBlock,
                if (trailing != null) ...[
                  const SizedBox(height: AppSpacing.md),
                  trailing!,
                ],
              ],
            );
          }
          return Row(children: [
            Expanded(child: titleBlock),
            if (trailing != null) trailing!,
          ]);
        },
      );
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

class Breadcrumb extends StatelessWidget {
  const Breadcrumb({super.key, required this.items});

  final List<String> items;

  @override
  Widget build(BuildContext context) => WorkspaceBreadcrumbs(items: items);
}

class SummaryCards extends StatelessWidget {
  const SummaryCards({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: AppSpacing.md,
        runSpacing: AppSpacing.md,
        children: children,
      );
}

class QuickActions extends StatelessWidget {
  const QuickActions({super.key, required this.actions});

  final List<Widget> actions;

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: actions,
      );
}

class AuditPanel extends StatelessWidget {
  const AuditPanel({
    super.key,
    required this.title,
    this.lines = const [],
    this.emptyMessage = 'No audit trail available.',
  });

  final String title;
  final List<DetailLine> lines;
  final String emptyMessage;

  @override
  Widget build(BuildContext context) => Card(
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              const Divider(),
              if (lines.isEmpty)
                Text(emptyMessage)
              else
                for (final DetailLine line in lines)
                  Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.md),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(line.label,
                            style: Theme.of(context).textTheme.labelMedium),
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

class HistoryPanel extends StatelessWidget {
  const HistoryPanel({
    super.key,
    required this.title,
    this.entries = const [],
    this.emptyMessage = 'No history available.',
  });

  final String title;
  final List<String> entries;
  final String emptyMessage;

  @override
  Widget build(BuildContext context) => Card(
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              const Divider(),
              if (entries.isEmpty)
                Text(emptyMessage)
              else
                for (final String entry in entries)
                  Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                    child: Text(entry),
                  ),
            ],
          ),
        ),
      );
}

class AttachmentPanel extends StatelessWidget {
  const AttachmentPanel({
    super.key,
    required this.title,
    this.items = const [],
    this.emptyMessage = 'No attachments available.',
  });

  final String title;
  final List<Widget> items;
  final String emptyMessage;

  @override
  Widget build(BuildContext context) => Card(
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              const Divider(),
              if (items.isEmpty)
                Text(emptyMessage)
              else
                for (final Widget item in items) ...[
                  item,
                  const SizedBox(height: AppSpacing.sm),
                ],
            ],
          ),
        ),
      );
}

class NotificationCenter extends StatelessWidget {
  const NotificationCenter({
    super.key,
    required this.title,
    this.children = const [],
    this.emptyMessage = 'No notifications.',
  });

  final String title;
  final List<Widget> children;
  final String emptyMessage;

  @override
  Widget build(BuildContext context) => Card(
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              const Divider(),
              if (children.isEmpty) Text(emptyMessage) else ...children,
            ],
          ),
        ),
      );
}

class StatusBar extends StatelessWidget {
  const StatusBar({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => child;
}

class EditorDialog extends StatelessWidget {
  const EditorDialog({
    super.key,
    required this.title,
    required this.child,
    this.subtitle,
    this.onCancel,
    this.onSave,
    this.loading = false,
  });

  final String title;
  final String? subtitle;
  final Widget child;
  final VoidCallback? onCancel;
  final VoidCallback? onSave;
  final bool loading;

  @override
  Widget build(BuildContext context) => Dialog(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720, maxHeight: 760),
          child: Column(
            mainAxisSize: MainAxisSize.max,
            children: [
              ListTile(
                title: Text(title),
                subtitle: subtitle == null ? null : Text(subtitle!),
                trailing: IconButton(
                  onPressed: loading ? null : onCancel,
                  icon: const Icon(Icons.close),
                ),
              ),
              const Divider(height: 1),
              Expanded(child: child),
              const Divider(height: 1),
              Padding(
                padding: const EdgeInsets.all(AppSpacing.md),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    TextButton(
                      onPressed: loading ? null : onCancel,
                      child: const Text('Cancel'),
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    FilledButton(
                      onPressed: loading ? null : onSave,
                      child: const Text('Save'),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
}

class ConfirmationDialog extends StatelessWidget {
  const ConfirmationDialog({
    super.key,
    required this.title,
    required this.message,
    this.confirmLabel = 'Confirm',
    this.onConfirm,
    this.onCancel,
  });

  final String title;
  final String message;
  final String confirmLabel;
  final VoidCallback? onConfirm;
  final VoidCallback? onCancel;

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          TextButton(onPressed: onCancel, child: const Text('Cancel')),
          FilledButton(
            onPressed: onConfirm,
            child: Text(confirmLabel),
          ),
        ],
      );
}

class ImportWizard extends StatelessWidget {
  const ImportWizard({
    super.key,
    required this.title,
    required this.body,
    this.onClose,
    this.onImport,
    this.loading = false,
  });

  final String title;
  final Widget body;
  final VoidCallback? onClose;
  final VoidCallback? onImport;
  final bool loading;

  @override
  Widget build(BuildContext context) => EditorDialog(
        title: title,
        onCancel: onClose,
        onSave: onImport,
        loading: loading,
        child: body,
      );
}

class ExportWizard extends StatelessWidget {
  const ExportWizard({
    super.key,
    required this.title,
    required this.body,
    this.onClose,
    this.onExport,
    this.loading = false,
  });

  final String title;
  final Widget body;
  final VoidCallback? onClose;
  final VoidCallback? onExport;
  final bool loading;

  @override
  Widget build(BuildContext context) => EditorDialog(
        title: title,
        onCancel: onClose,
        onSave: onExport,
        loading: loading,
        child: body,
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

/// A compact page control for screens that render their own list.
///
/// [EnterpriseDataGrid] paginates through `PaginatedDataTable`, but the
/// document workspaces and the goods receipt screen render bespoke lists and so
/// had no pager at all: they fetched a page count they never showed and stayed
/// on page one for the life of the screen, which put every record past the
/// first twenty out of reach.
class WorkspacePager extends StatelessWidget {
  const WorkspacePager({
    super.key,
    required this.page,
    required this.pageSize,
    required this.total,
    required this.onPageChanged,
  });

  /// The page currently shown, counting from one.
  final int page;
  final int pageSize;
  final int total;

  /// Called with the requested page, counting from one.
  final ValueChanged<int> onPageChanged;

  int get _lastPage => total <= 0 ? 1 : ((total - 1) ~/ pageSize) + 1;

  @override
  Widget build(BuildContext context) {
    if (total <= pageSize) {
      return const SizedBox.shrink();
    }
    final ThemeData theme = Theme.of(context);
    final int first = ((page - 1) * pageSize) + 1;
    final int last = first + pageSize - 1;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          Text(
            '$first–${last > total ? total : last} of $total',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(width: 8),
          IconButton(
            tooltip: 'Previous page',
            icon: const Icon(Icons.chevron_left, size: 20),
            onPressed: page > 1 ? () => onPageChanged(page - 1) : null,
          ),
          IconButton(
            tooltip: 'Next page',
            icon: const Icon(Icons.chevron_right, size: 20),
            onPressed: page < _lastPage ? () => onPageChanged(page + 1) : null,
          ),
        ],
      ),
    );
  }
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
    this.trailing = const [],
  });

  final ValueChanged<ToolbarAction> onAction;
  final bool Function(ToolbarAction) isEnabled;
  final bool Function(ToolbarAction)? isVisible;
  final List<ToolbarAction> actions;

  /// Resource-specific actions the standard set cannot express, rendered after
  /// it. `ToolbarAction` is a closed enum shared by every workspace, so a
  /// one-resource action like "provision storage" has nowhere else to go.
  final List<Widget> trailing;

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: 4,
        runSpacing: 4,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          ...actions.where((action) => isVisible?.call(action) ?? true).map(
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
              ),
          ...trailing,
        ],
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
    this.onChanged,
    this.onClear,
  });

  final TextEditingController controller;
  final ValueChanged<String> onSearch;
  final List<Widget>? filters;
  final String hintText;
  final FocusNode? focusNode;

  /// Fires on every keystroke so the caller can debounce a request.
  final ValueChanged<String>? onChanged;
  final VoidCallback? onClear;

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: 12,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 360),
            // Rebuilds the suffix as the field empties and fills, so the clear
            // button only exists when there is something to clear.
            child: ValueListenableBuilder<TextEditingValue>(
              valueListenable: controller,
              builder: (context, value, _) => TextField(
                focusNode: focusNode,
                controller: controller,
                onSubmitted: onSearch,
                onChanged: onChanged,
                decoration: InputDecoration(
                  hintText: hintText,
                  prefixIcon: const Icon(Icons.search),
                  // The old trailing icon was a second Search button beside the
                  // search icon, which is the one thing this slot should not be.
                  suffixIcon: value.text.isEmpty
                      ? null
                      : IconButton(
                          tooltip: 'Clear search',
                          icon: const Icon(Icons.close),
                          onPressed: () {
                            controller.clear();
                            if (onClear != null) {
                              onClear!();
                            } else {
                              onSearch('');
                            }
                          },
                        ),
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
    this.detailsPanel,
    required this.statusBar,
    this.detailsWidth = 300,
    this.filterPanel,
  });

  final Widget toolbar;
  final Widget searchPanel;
  final Widget primaryContent;
  final Widget? detailsPanel;
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
                if (detailsPanel == null) {
                  return primaryContent;
                }
                final double panelWidth = detailsWidth
                    .clamp(240, constraints.maxWidth * .36)
                    .toDouble();
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
    required this.key,
    required this.label,
    this.onSort,
    this.visible = true,
    this.tooltip,
  });
  final String key;
  final String label;
  final void Function(bool ascending)? onSort;
  final bool visible;
  final String? tooltip;
}

class EnterpriseDataGrid<T> extends StatefulWidget {
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
    this.selectedIds = const {},
    this.onSelectionChanged,
    this.rowsPerPage = 20,
    this.availableRowsPerPage = const [20],
    this.onRowsPerPageChanged,
    this.onOpen,
    this.contextActions = const [],
    this.contextActionsFor,
    this.onContextAction,
    this.showRowNumbers = false,
    this.rowNumberLabel = '#',
    this.cellBuilder,
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
  final Set<String> selectedIds;
  final ValueChanged<Set<String>>? onSelectionChanged;
  final int rowsPerPage;
  final List<int> availableRowsPerPage;
  final ValueChanged<int?>? onRowsPerPageChanged;
  final ValueChanged<T>? onOpen;
  final List<WorkspaceContextAction> contextActions;
  final List<WorkspaceContextAction> Function(T item)? contextActionsFor;
  final void Function(WorkspaceContextAction action, T item)? onContextAction;
  final bool showRowNumbers;
  final String rowNumberLabel;
  final Widget Function(int columnIndex, String value, T item)? cellBuilder;

  @override
  State<EnterpriseDataGrid<T>> createState() => _EnterpriseDataGridState<T>();
}

class _EnterpriseDataGridState<T> extends State<EnterpriseDataGrid<T>> {
  /// Owned here so the visible scrollbar and the scroll view share one
  /// controller; a `Scrollbar` with `thumbVisibility` needs a controller that
  /// survives rebuilds, which a stateless widget cannot give it.
  final ScrollController _horizontal = ScrollController();

  @override
  void dispose() {
    _horizontal.dispose();
    super.dispose();
  }

  bool get _showActionsColumn =>
      widget.onOpen != null ||
      widget.contextActions.isNotEmpty ||
      widget.contextActionsFor != null ||
      widget.onContextAction != null;

  bool get _multiSelection => widget.onSelectionChanged != null;

  int get _page => widget.rowsPerPage <= 0
      ? 1
      : (widget.pageOffset ~/ widget.rowsPerPage) + 1;

  List<MapEntry<int, GridColumn>> get _visibleColumns => widget.columns
      .asMap()
      .entries
      .where((entry) => entry.value.visible)
      .toList();

  bool _isSelected(String itemId) =>
      widget.selectedIds.contains(itemId) || widget.selectedId == itemId;

  List<WorkspaceContextAction> _actionsFor(T item) =>
      widget.contextActionsFor?.call(item) ?? widget.contextActions;

  /// Toggling the tick, when there is anything to tick *for*.
  ///
  /// Null leaves the checkbox column out entirely; rows are still selected by
  /// the tap handler each cell carries.
  ValueChanged<bool?>? _onSelectChanged(T item, String itemId) =>
      !_multiSelection
          ? null
          : (_) {
              final Set<String> next = {...widget.selectedIds};
              if (!next.remove(itemId)) next.add(itemId);
              widget.onSelectionChanged?.call(next);
              widget.onSelect(item);
            };

  /// One row of data cells. Rows come from `items` only, so a page shows
  /// exactly what it holds.
  ///
  /// This used to be a `DataTableSource` behind a `PaginatedDataTable`, which
  /// pads every page out to `rowsPerPage` with blank rows -- and with a checkbox
  /// column each blank drew a disabled checkbox. Three records under a 25-row
  /// page size meant twenty-two phantom rows.
  DataRow _dataRow(BuildContext context, T item, int index) {
    final List<String> values = widget.cells(item);
    final String itemId = widget.id(item);
    // Both, not one or the other. This used to read
    // `_multiSelection ? selectedIds.contains(id) : selectedId == id`, and
    // because the workspace always wires multi-selection, the row's appearance
    // was driven only by the checkbox: clicking a row enabled View/Edit/Delete
    // in the toolbar and left the row looking untouched.
    final bool isSelected = _isSelected(itemId);
    final List<WorkspaceContextAction> itemContextActions = _actionsFor(item);
    return DataRow(
      selected: isSelected,
      onSelectChanged: _onSelectChanged(item, itemId),
      cells: [
        // The row number goes through the same builder as every other cell.
        // It used to be a bare `DataCell(Text(...))`: no tap handler, so the
        // whole column was dead to the mouse, and because it took the leading
        // position it also displaced the selection marker -- which is why
        // Products, the one master grid that numbers its rows, showed no
        // marker at all on the row it had selected.
        if (widget.showRowNumbers)
          _dataCell(
            context,
            item: item,
            content: Text('${index + 1}'),
            isLeading: true,
            isSelected: isSelected,
            itemContextActions: itemContextActions,
          ),
        ..._visibleColumns.asMap().entries.map((visible) {
          final MapEntry<int, GridColumn> entry = visible.value;
          final String value =
              entry.key < values.length ? values[entry.key] : '';
          return _dataCell(
            context,
            item: item,
            content: widget.cellBuilder?.call(entry.key, value, item) ??
                Tooltip(
                  message: value,
                  child: SizedBox(
                    width: double.infinity,
                    child: Text(value, overflow: TextOverflow.ellipsis),
                  ),
                ),
            isLeading: visible.key == 0 && !widget.showRowNumbers,
            isSelected: isSelected,
            itemContextActions: itemContextActions,
          );
        }),
      ],
    );
  }

  /// One cell: the marker when it leads the row, the context menu, and the
  /// tap handlers that make single-click select and double-click open.
  DataCell _dataCell(
    BuildContext context, {
    required T item,
    required Widget content,
    required bool isLeading,
    required bool isSelected,
    required List<WorkspaceContextAction> itemContextActions,
  }) {
    Widget cell = content;
    if (isLeading) {
      // A marker on the row's leading edge, so the selection is not signalled
      // by colour alone -- the tint is easy to lose in high contrast, and
      // `DataRow` has no border of its own to use.
      cell = Container(
        padding: const EdgeInsets.only(left: AppSpacing.sm),
        decoration: BoxDecoration(
          border: Border(
            left: BorderSide(
              color: isSelected
                  ? Theme.of(context).colorScheme.primary
                  : Colors.transparent,
              width: 3,
            ),
          ),
        ),
        child: cell,
      );
    }
    return DataCell(
      GestureDetector(
        behavior: HitTestBehavior.opaque,
        onSecondaryTapDown: itemContextActions.isEmpty
            ? null
            : (details) {
                widget.onSelect(item);
                showWorkspaceContextMenu(
                  context,
                  position: details.globalPosition,
                  actions: itemContextActions,
                  onSelected: (action) =>
                      widget.onContextAction?.call(action, item),
                );
              },
        child: cell,
      ),
      onTap: () => widget.onSelect(item),
      onDoubleTap: widget.onOpen == null ? null : () => widget.onOpen!(item),
    );
  }

  /// The same row, in the pinned table: one cell, carrying the actions.
  ///
  /// It repeats `selected` so the row tint and the theme's `dataRowColor` carry
  /// across the seam instead of stopping halfway.
  DataRow _actionsRow(T item) {
    final String itemId = widget.id(item);
    return DataRow(
      selected: _isSelected(itemId),
      onSelectChanged: _onSelectChanged(item, itemId),
      cells: [
        DataCell(
          _RowActions<T>(
            item: item,
            actions: _actionsFor(item),
            onOpen: widget.onOpen,
            onSelect: widget.onSelect,
            onContextAction: widget.onContextAction,
          ),
        ),
      ],
    );
  }

  DataTable _dataTable(BuildContext context) => DataTable(
        // Flutter also needs a row that is selectable; rows only carry
        // `onSelectChanged` when multi-selection is wired, so the column
        // disappears together with its purpose.
        showCheckboxColumn: _multiSelection,
        onSelectAll: !_multiSelection
            ? null
            : (checked) {
                final Set<String> pageIds = widget.items.map(widget.id).toSet();
                widget.onSelectionChanged!(
                  checked ?? false
                      ? {...widget.selectedIds, ...pageIds}
                      : widget.selectedIds.difference(pageIds),
                );
              },
        columns: [
          if (widget.showRowNumbers)
            DataColumn(label: Text(widget.rowNumberLabel), numeric: true),
          for (final MapEntry<int, GridColumn> entry in _visibleColumns)
            DataColumn(
              label: Tooltip(
                message: entry.value.tooltip ?? entry.value.label,
                child: Text(entry.value.label),
              ),
              onSort: entry.value.onSort == null
                  ? null
                  : (_, ascending) => entry.value.onSort!(ascending),
            ),
        ],
        rows: [
          for (int index = 0; index < widget.items.length; index++)
            _dataRow(context, widget.items[index], widget.pageOffset + index),
        ],
      );

  /// The pinned half. Never inside the horizontal scroll, so the row actions
  /// stay reachable however wide the data grows.
  Widget _pinnedActions(BuildContext context) => DecoratedBox(
        decoration: BoxDecoration(
          border: Border(
            left:
                BorderSide(color: Theme.of(context).colorScheme.outlineVariant),
          ),
        ),
        child: DataTable(
          showCheckboxColumn: false,
          columns: const [DataColumn(label: Text('Actions'))],
          rows: [for (final T item in widget.items) _actionsRow(item)],
        ),
      );

  @override
  Widget build(BuildContext context) {
    final List<int> sizeOptions =
        widget.availableRowsPerPage.contains(widget.rowsPerPage)
            ? widget.availableRowsPerPage
            : [widget.rowsPerPage, ...widget.availableRowsPerPage];
    final bool showSizeSelector =
        widget.onRowsPerPageChanged != null && sizeOptions.length > 1;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: [
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                // A minimum, not a fixed width: a bare `DataTable` cannot shrink
                // below the width its columns need and would overflow instead.
                final double minWidth =
                    constraints.maxWidth < 720 ? 720 : constraints.maxWidth;
                Widget scrollingData(double available) => Scrollbar(
                      controller: _horizontal,
                      // Flutter's `MaterialScrollBehavior` adds a scrollbar for
                      // vertical scroll views and never for horizontal ones, so
                      // a table wider than its viewport gave no sign that
                      // anything lay off the right edge.
                      thumbVisibility: true,
                      child: SingleChildScrollView(
                        controller: _horizontal,
                        scrollDirection: Axis.horizontal,
                        child: ConstrainedBox(
                          constraints: BoxConstraints(minWidth: available),
                          child: _dataTable(context),
                        ),
                      ),
                    );
                if (!_showActionsColumn) {
                  return SingleChildScrollView(
                    child: scrollingData(minWidth),
                  );
                }
                // One vertical scroll around both halves, so they move together
                // without anything having to synchronise them. They line up row
                // for row because `ThemeRegistry` fixes `dataRowMinHeight`,
                // `dataRowMaxHeight` and `headingRowHeight` -- if those ever
                // become variable, this alignment is the first thing to check.
                return SingleChildScrollView(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // A second LayoutBuilder because the first cannot know
                      // how much room the pinned column will take. A Row
                      // measures its non-flex children first, so by the time
                      // this runs `inner.maxWidth` is what is genuinely left --
                      // and the data table fills it instead of sitting at its
                      // intrinsic width with a stretch of nothing before the
                      // actions, which is what a three-column grid looked like.
                      Expanded(
                        child: LayoutBuilder(
                          builder: (context, inner) =>
                              scrollingData(inner.maxWidth),
                        ),
                      ),
                      _pinnedActions(context),
                    ],
                  ),
                );
              },
            ),
          ),
          if (widget.total > 0)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  if (showSizeSelector) ...[
                    Text(
                      'Rows per page:',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    DropdownButton<int>(
                      value: widget.rowsPerPage,
                      underline: const SizedBox.shrink(),
                      isDense: true,
                      onChanged: widget.onRowsPerPageChanged,
                      items: [
                        for (final int size in sizeOptions)
                          DropdownMenuItem<int>(
                            value: size,
                            child: Text('$size'),
                          ),
                      ],
                    ),
                  ],
                  // Reports a row offset, not a page number: every caller has
                  // always converted with `offset ~/ rowsPerPage + 1`.
                  WorkspacePager(
                    page: _page,
                    pageSize: widget.rowsPerPage,
                    total: widget.total,
                    onPageChanged: (page) =>
                        widget.onPageChanged((page - 1) * widget.rowsPerPage),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

/// Row actions: the two everyone uses, then everything else behind one menu.
///
/// Every applicable action used to render as its own `IconButton`, so a row
/// with view/edit/delete/copy carried four icons and a grid of 25 rows carried
/// a hundred. At that density the icons stop being scannable and the row reads
/// as decoration. View and Edit stay inline because they are the actions taken
/// constantly; the destructive and occasional ones move behind the overflow,
/// where a deliberate second click is a feature rather than a cost.
class _RowActions<T> extends StatelessWidget {
  const _RowActions({
    required this.item,
    required this.actions,
    required this.onOpen,
    required this.onSelect,
    required this.onContextAction,
  });

  final T item;
  final List<WorkspaceContextAction> actions;
  final ValueChanged<T>? onOpen;
  final ValueChanged<T> onSelect;
  final void Function(WorkspaceContextAction action, T item)? onContextAction;

  /// Actions that belong to the whole grid rather than to one row.
  static const Set<WorkspaceContextAction> _notRowScoped = {
    WorkspaceContextAction.refresh,
    WorkspaceContextAction.export,
  };

  static const Set<WorkspaceContextAction> _primary = {
    WorkspaceContextAction.view,
    WorkspaceContextAction.edit,
  };

  void _invoke(WorkspaceContextAction action) {
    onSelect(item);
    onContextAction?.call(action, item);
  }

  @override
  Widget build(BuildContext context) {
    final List<WorkspaceContextAction> rowActions =
        actions.where((action) => !_notRowScoped.contains(action)).toList();
    final bool viewInline =
        onOpen != null || rowActions.contains(WorkspaceContextAction.view);
    final List<WorkspaceContextAction> overflow = rowActions
        .where((action) => !_primary.contains(action))
        .toList(growable: false);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (viewInline)
          IconButton(
            tooltip: WorkspaceContextAction.view.label,
            visualDensity: VisualDensity.compact,
            icon: Icon(WorkspaceContextAction.view.icon, size: 18),
            onPressed: () {
              onSelect(item);
              final ValueChanged<T>? open = onOpen;
              if (open != null) {
                open(item);
              } else {
                onContextAction?.call(WorkspaceContextAction.view, item);
              }
            },
          ),
        if (rowActions.contains(WorkspaceContextAction.edit))
          IconButton(
            tooltip: WorkspaceContextAction.edit.label,
            visualDensity: VisualDensity.compact,
            icon: Icon(WorkspaceContextAction.edit.icon, size: 18),
            onPressed: onContextAction == null
                ? null
                : () => _invoke(WorkspaceContextAction.edit),
          ),
        if (overflow.isNotEmpty)
          PopupMenuButton<WorkspaceContextAction>(
            tooltip: 'More actions',
            icon: const Icon(Icons.more_vert, size: 18),
            position: PopupMenuPosition.under,
            onSelected: _invoke,
            itemBuilder: (context) => [
              for (final WorkspaceContextAction action in overflow)
                PopupMenuItem<WorkspaceContextAction>(
                  value: action,
                  child: Row(
                    children: [
                      Icon(action.icon, size: 18),
                      const SizedBox(width: AppSpacing.md),
                      Text(action.label),
                    ],
                  ),
                ),
            ],
          ),
      ],
    );
  }
}

/// One bulk operation offered while rows are selected.
class WorkspaceBulkAction {
  const WorkspaceBulkAction({
    required this.label,
    required this.icon,
    required this.onInvoke,
    this.isDestructive = false,
  });

  final String label;
  final IconData icon;

  /// Receives the selected identifiers and returns the message to report.
  final Future<String> Function(Set<String> ids) onInvoke;
  final bool isDestructive;
}

/// Replaces the toolbar while a selection exists.
///
/// Deliberately shows nothing but "clear" when a module declares no bulk
/// actions: most modules have no bulk endpoint, and offering buttons that
/// cannot work would be worse than offering none.
class WorkspaceBulkActionBar extends StatelessWidget {
  const WorkspaceBulkActionBar({
    super.key,
    required this.selectedCount,
    required this.actions,
    required this.onAction,
    required this.onClear,
    this.busy = false,
  });

  final int selectedCount;
  final List<WorkspaceBulkAction> actions;

  /// The bar reports the choice; running it, reporting it and reloading belong
  /// to the workspace that owns the selection.
  final ValueChanged<WorkspaceBulkAction> onAction;
  final VoidCallback onClear;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Material(
      color: theme.colorScheme.primaryContainer,
      borderRadius: AppRadius.medium,
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        child: Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text(
              '$selectedCount selected',
              style: theme.textTheme.titleSmall?.copyWith(
                color: theme.colorScheme.onPrimaryContainer,
              ),
            ),
            for (final WorkspaceBulkAction action in actions)
              TextButton.icon(
                onPressed: busy ? null : () => onAction(action),
                icon: Icon(action.icon, size: 18),
                label: Text(action.label),
                style: TextButton.styleFrom(
                  foregroundColor: action.isDestructive
                      ? theme.colorScheme.error
                      : theme.colorScheme.onPrimaryContainer,
                ),
              ),
            TextButton.icon(
              onPressed: busy ? null : onClear,
              icon: const Icon(Icons.close, size: 18),
              label: const Text('Clear selection'),
              style: TextButton.styleFrom(
                foregroundColor: theme.colorScheme.onPrimaryContainer,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class DetailLine {
  const DetailLine(this.label, this.value);
  final String label;
  final String value;
}

enum StatusBadgeTone {
  neutral,
  success,
  warning,
  danger,
  info,
}

class StatusBadge extends StatelessWidget {
  const StatusBadge({
    super.key,
    required this.label,
    this.tone = StatusBadgeTone.neutral,
  });

  final String label;
  final StatusBadgeTone tone;

  factory StatusBadge.fromStatus(String value) {
    final String status = value.trim().toUpperCase();
    final StatusBadgeTone tone = switch (status) {
      'ACTIVE' || 'APPROVED' => StatusBadgeTone.success,
      'PENDING' ||
      'DRAFT' ||
      'NEAR EXPIRY' ||
      'NEAR_EXPIRY' =>
        StatusBadgeTone.warning,
      'INACTIVE' ||
      'REJECTED' ||
      'BLOCKED' ||
      'DELETED' ||
      'ARCHIVED' ||
      'EXPIRED' =>
        StatusBadgeTone.danger,
      'INFO' => StatusBadgeTone.info,
      _ => StatusBadgeTone.neutral,
    };
    return StatusBadge(label: value, tone: tone);
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    final AppSemanticColors semantic = context.semanticColors;
    final (Color, Color) palette = switch (tone) {
      StatusBadgeTone.success => (semantic.success, semantic.onSuccess),
      StatusBadgeTone.warning => (semantic.warning, semantic.onWarning),
      StatusBadgeTone.danger => (colors.error, colors.onError),
      StatusBadgeTone.info => (semantic.information, semantic.onInformation),
      StatusBadgeTone.neutral => (
          colors.surfaceContainerHighest,
          colors.onSurfaceVariant
        ),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: palette.$1,
        borderRadius: AppRadius.large,
      ),
      child: Text(
        label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: palette.$2,
              fontWeight: FontWeight.w700,
            ),
      ),
    );
  }
}

class SummaryMetricCard extends StatelessWidget {
  const SummaryMetricCard({
    super.key,
    required this.label,
    required this.value,
    required this.icon,
    this.width = 230,
  });

  final String label;
  final String value;
  final IconData icon;
  final double width;

  @override
  Widget build(BuildContext context) => SizedBox(
        width: width,
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Row(children: [
              Icon(icon,
                  size: 32, color: Theme.of(context).colorScheme.primary),
              const SizedBox(width: 16),
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(value, style: Theme.of(context).textTheme.headlineSmall),
                Text(label),
              ]),
            ]),
          ),
        ),
      );
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

/// Show the same lines a [DetailsPanel] would, on demand.
///
/// A read-only record still needs somewhere to show what a grid column cannot
/// hold. Modules with an editable record open its own dialog in view mode --
/// products and customers do -- but a stock movement or a ledger entry has no
/// such form, and it should not need one invented to be readable.
///
/// This exists so removing a selection-driven side panel does not remove the
/// detail with it: the panel's own [DetailLine] list is handed straight to it.
Future<void> showDetailLinesDialog(
  BuildContext context, {
  required String title,
  required List<DetailLine> lines,
  IconData icon = Icons.receipt_long_outlined,
}) =>
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        icon: Icon(icon),
        title: Text(title),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                for (final DetailLine line in lines)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          line.label,
                          style: Theme.of(context).textTheme.labelLarge,
                        ),
                        const SizedBox(height: 2),
                        // Selectable: the reason people opened the old panel
                        // was usually to copy an id or a reference number.
                        SelectableText(line.value),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );

class WorkspaceStatusBar extends StatelessWidget {
  const WorkspaceStatusBar({
    super.key,
    required this.total,
    required this.selected,
    this.selectedCount,
    this.message,
  });
  final int total;
  final bool selected;
  final int? selectedCount;
  final String? message;

  @override
  Widget build(BuildContext context) => Material(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
          child: Row(children: [
            Text('$total record${total == 1 ? '' : 's'}'),
            if (selected) Text('  |  ${selectedCount ?? 1} selected'),
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
