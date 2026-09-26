import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/design/design_tokens.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../phase2/indian_format.dart';
import '../../phase2/phase2_scope.dart';
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
  Widget build(BuildContext context) {
    if (Phase2Scope.of(context)) {
      // Phase 2 (4.5): title, counters, search and actions on one line.
      return phase2Frame(
        title: title,
        description: description ?? '',
        actions: [
          if (search != null) ...[
            SizedBox(width: 280, child: search),
            const SizedBox(width: 8),
          ],
          if (toolbar != null) toolbar!,
          ...headerActions,
        ],
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (filterPanel != null) filterPanel!,
            Expanded(child: content),
          ],
        ),
        status: statusBar,
      );
    }
    return _phase1(context);
  }

  Widget _phase1(BuildContext context) => SafeArea(
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
  Widget build(BuildContext context) {
    if (Phase2Scope.of(context)) {
      // Phase 2 (4.5): the figures are counters on the page's one line, not
      // a row of cards above it. Handed to the line and drawn there; where
      // there is no line to hand them to, a compact row in place.
      final Phase2PageBar? bar = Phase2PageBar.of(context);
      if (bar != null) {
        bar.publish(children);
        return const SizedBox.shrink();
      }
      return Wrap(spacing: 6, runSpacing: 6, children: children);
    }
    return Wrap(
      spacing: AppSpacing.md,
      runSpacing: AppSpacing.md,
      children: children,
    );
  }
}

/// One summary figure: "Draft 3", "Overdue 2".
///
/// Phase 1 draws it as the card every document list drew for itself (six
/// private copies, now this one). Phase 2 draws a small counter on the page's
/// one line (UI_PHASE_2_DESIGN.md 4.5) which, given [onTap], is also the
/// quickest filter there is: click "Draft 3" and the list is the three
/// drafts, marked [selected] while it is.
class SummaryCount extends StatelessWidget {
  const SummaryCount({
    super.key,
    required this.label,
    required this.value,
    this.onTap,
    this.selected = false,
    this.alert = false,
    this.width,
    this.largeLabel = false,
  });

  final String label;
  final String value;

  /// Filter the list to what this figure counts.
  final VoidCallback? onTap;
  final bool selected;

  /// A figure somebody should act on (Overdue): drawn in the danger colour
  /// whenever it is not zero.
  final bool alert;

  /// Phase 1's card width, where a screen fixed one.
  final double? width;

  /// Phase 1's label size on the screens that used the larger one.
  final bool largeLabel;

  @override
  Widget build(BuildContext context) =>
      Phase2Scope.of(context) ? _counter(context) : _card(context);

  Widget _card(BuildContext context) {
    final TextTheme text = Theme.of(context).textTheme;
    final Widget card = Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: largeLabel ? text.labelLarge : text.labelMedium),
            const SizedBox(height: 8),
            Text(value, style: text.headlineSmall),
          ],
        ),
      ),
    );
    return width == null ? card : SizedBox(width: width, child: card);
  }

  Widget _counter(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final bool alarming = alert && value.trim() != '0' && value.trim() != '';
    // The wireframe's counter: a pill with a grey edge, "Active 15" in dark
    // text -- the same shape as the "+ filter" chip beside it. The one the
    // list is filtered by is tinted and edged in the accent (4.14: not by
    // tint alone).
    // No alignment: a Container that aligns its child fills the width it is
    // offered, and in a Wrap every counter became a full-width bar.
    final Widget body = Container(
      height: 28,
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(
        color: selected
            ? scheme.primary.withValues(alpha: .12)
            : scheme.surfaceContainerLowest,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: selected ? scheme.primary : scheme.outlineVariant,
          width: selected ? 1.5 : 1,
        ),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Text(label, style: theme.textTheme.bodyMedium?.copyWith(fontSize: 13)),
        const SizedBox(width: 5),
        Text(
          value,
          style: theme.textTheme.bodyMedium?.copyWith(
            fontSize: 13,
            color: alarming ? scheme.error : scheme.onSurface,
            fontWeight: alarming ? FontWeight.w700 : null,
          ),
        ),
      ]),
    );
    if (onTap == null) return body;
    return Tooltip(
      message: selected ? 'Showing $label -- click to show all' : 'Show $label',
      child: InkWell(
        borderRadius: AppRadius.medium,
        onTap: onTap,
        child: body,
      ),
    );
  }
}

/// The start of the phase 2 page line: title, its description behind (i),
/// the page's tabs, and its counters (4.5). Drawn by the list layout when it
/// has claimed the line, and by the frame when nothing has.
class Phase2PageTitle extends StatelessWidget {
  const Phase2PageTitle({super.key, required this.bar});

  final Phase2PageBar bar;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Row(mainAxisSize: MainAxisSize.min, children: [
      ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 260),
        child: Text(
          Phase2ScreenTitle.of(context) ?? bar.title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: theme.textTheme.titleMedium
              ?.copyWith(fontWeight: FontWeight.w700),
        ),
      ),
      if (bar.description.isNotEmpty)
        Tooltip(
          message: bar.description,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 6),
            child: Icon(
              Icons.info_outline,
              size: 16,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ),
      if (bar.tabs != null) ...[
        const SizedBox(width: 8),
        bar.tabs!,
      ],
    ]);
  }
}

/// The page's counters, scrolling sideways rather than wrapping when the
/// line is short (4.11: the line never grows a second row for them).
class Phase2PageCounters extends StatelessWidget {
  const Phase2PageCounters({super.key, required this.bar});

  final Phase2PageBar bar;

  @override
  Widget build(BuildContext context) => ValueListenableBuilder<List<Widget>>(
        valueListenable: bar.counters,
        builder: (context, counters, _) => counters.isEmpty
            ? const SizedBox.shrink()
            : SingleChildScrollView(
                key: const ValueKey('phase2-counters'),
                scrollDirection: Axis.horizontal,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    for (final Widget counter in counters) ...[
                      const SizedBox(width: 4),
                      counter,
                    ],
                  ],
                ),
              ),
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
    if (Phase2Scope.of(context)) return _phase2(context, workspaceTabs);
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

  /// Phase 2 (UI_PHASE_2_DESIGN.md 4.5): the title, its description behind
  /// an (i), the screen's own tabs and its counters join the list's one line
  /// ([Phase2PageBar]). The breadcrumb goes: the menu bar's open area and the
  /// open-screen tab already say where you are, and phase 1 said it three
  /// times over about 120 px.
  Widget _phase2(BuildContext context, List<WorkspaceTab> workspaceTabs) =>
      phase2Frame(
        title: title,
        description: description,
        tabs: workspaceTabs.isEmpty
            ? null
            : SegmentedButton<int>(
                style: const ButtonStyle(
                  visualDensity: VisualDensity.compact,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
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
        child: child,
        status: status,
      );
}

/// Every phase 2 page frame, whichever phase 1 frame it replaces: a
/// [Phase2PageBar] for the list below to draw the one line with, and -- when
/// nothing below claims that line -- a compact title line of its own, with
/// the counters on it and [actions] at its end.
Widget phase2Frame({
  required String title,
  required String description,
  Widget? tabs,
  required Widget child,
  Widget? status,
  List<Widget> actions = const [],
}) =>
    Builder(builder: (context) {
      // A frame inside another frame (a resource list inside its module's
      // frame) defers to the outer one: the list claims the outer line, so
      // the window shows one title rather than two.
      final Phase2PageBar? outer = Phase2PageBar.of(context);
      if (tabs == null && outer != null) {
        // Its buttons go on the outer line too, unless a list has that line.
        if (actions.isNotEmpty) outer.publishTools(actions);
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(child: child),
            if (status != null) status,
          ],
        );
      }
      return _phase2FrameHost(
        title: title,
        description: description,
        tabs: tabs,
        status: status,
        actions: actions,
        child: child,
      );
    });

Widget _phase2FrameHost({
  required String title,
  required String description,
  Widget? tabs,
  required Widget child,
  Widget? status,
  List<Widget> actions = const [],
}) =>
    Phase2PageBarHost(
      title: title,
      description: description,
      tabs: tabs,
      builder: (context, bar, claimed) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (!claimed || actions.isNotEmpty)
            // The same white band and line as a list's page bar.
            DecoratedBox(
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surfaceContainerLowest,
                border: Border(
                  bottom: BorderSide(
                    color: Theme.of(context).colorScheme.outlineVariant,
                  ),
                ),
              ),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 6, 12, 6),
                child: Phase2ButtonTheme(
                  child: Row(children: [
                    if (!claimed) Phase2PageTitle(bar: bar),
                    // The counters take the room the tools leave; the tools
                    // sit at the right. (A Flexible beside a Spacer split
                    // the room and left the tools mid-line.)
                    Expanded(
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: claimed
                            ? const SizedBox.shrink()
                            : Phase2PageCounters(bar: bar),
                      ),
                    ),
                    if (!claimed)
                      ValueListenableBuilder<List<Widget>>(
                        valueListenable: bar.tools,
                        builder: (context, tools, _) => Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            for (final Widget tool in tools) ...[
                              const SizedBox(width: 6),
                              tool,
                            ],
                          ],
                        ),
                      ),
                    if (actions.isNotEmpty) const SizedBox(width: 6),
                    ...actions,
                  ]),
                ),
              ),
            ),
          Expanded(child: child),
          if (status != null) status,
        ],
      ),
    );

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

/// A screen's own action -- Approve, Hold, Print challan -- that the shared
/// [ToolbarAction] set cannot express. Phase 2 draws it as a compact button
/// on the page line and, when the line has no room, folds it into "..."
/// (UI_PHASE_2_DESIGN.md 4.11), so a document list never overflows.
class ToolbarCommand {
  const ToolbarCommand({
    required this.id,
    required this.label,
    required this.icon,
    this.onPressed,
    this.tooltip,
    this.menuOnly = false,
  });

  /// Keys the button `toolbar-command-<id>` and its menu entry
  /// `toolbar-command-<id>-menu`.
  final String id;
  final String label;
  final IconData icon;

  /// Null draws it disabled.
  final VoidCallback? onPressed;
  final String? tooltip;

  /// Set up now and then (print settings, sales stages): always behind
  /// "...", never a button on the line.
  final bool menuOnly;
}

class WorkspaceToolbar extends StatelessWidget {
  const WorkspaceToolbar({
    super.key,
    required this.onAction,
    required this.isEnabled,
    this.isVisible,
    this.actions = ToolbarAction.values,
    this.trailing = const [],
    this.commands = const [],
    this.newLabel = '+ New',
  });

  final ValueChanged<ToolbarAction> onAction;
  final bool Function(ToolbarAction) isEnabled;
  final bool Function(ToolbarAction)? isVisible;
  final List<ToolbarAction> actions;

  /// Resource-specific actions the standard set cannot express, rendered after
  /// it. `ToolbarAction` is a closed enum shared by every workspace, so a
  /// one-resource action like "provision storage" has nowhere else to go.
  final List<Widget> trailing;

  /// The screen's own actions, drawn after the everyday icons; phase 2 folds
  /// the ones that do not fit into "...".
  final List<ToolbarCommand> commands;

  /// What the one filled button says in phase 2.
  final String newLabel;

  @override
  Widget build(BuildContext context) {
    if (Phase2Scope.of(context)) {
      if (commands.isEmpty) return _phase2(context, const []);
      return LayoutBuilder(
        builder: (context, constraints) =>
            _phase2(context, _fitting(context, constraints.maxWidth)),
      );
    }
    return _phase1(context);
  }

  /// The commands that fit beside everything else in [available], from the
  /// left; the rest go behind "...". All of them where there is no limit.
  List<ToolbarCommand> _fitting(BuildContext context, double available) {
    if (!available.isFinite) {
      return commands.where((command) => !command.menuOnly).toList();
    }
    final TextStyle style =
        (Theme.of(context).textTheme.bodyMedium ?? const TextStyle())
            .copyWith(fontSize: 13);
    final TextScaler scaler = MediaQuery.textScalerOf(context);
    double text(String value) {
      final TextPainter painter = TextPainter(
        text: TextSpan(text: value, style: style),
        textDirection: TextDirection.ltr,
        textScaler: scaler,
        maxLines: 1,
      )..layout();
      final double width = painter.width;
      painter.dispose();
      return width;
    }

    final List<ToolbarAction> shown =
        actions.where((action) => isVisible?.call(action) ?? true).toList();
    double used = 36.0 * _everyDay.where(shown.contains).length +
        // "..." is always there once anything folds.
        46 +
        (shown.contains(ToolbarAction.newItem) ? text(newLabel) + 36 : 0) +
        // Trailing widgets cannot be measured before they are laid out.
        120.0 * trailing.length;
    final List<ToolbarCommand> fitting = [];
    for (final ToolbarCommand command in commands) {
      if (command.menuOnly) continue;
      used += text(command.label) + 18 + 6 + 24 + 6;
      if (used > available) break;
      fitting.add(command);
    }
    return fitting;
  }

  /// Phase 2 (the wireframe): the screen's own buttons (Groups), then
  /// everything else behind "…", then "+ New" last and the only filled one --
  /// six icon buttons in a row read as decoration, not as choices.
  /// The actions taken all day, shown as icons on the line rather than
  /// behind "…" (owner, 2026-09-26: there is room, and a hidden Edit costs a
  /// click every time).
  static const List<ToolbarAction> _everyDay = [
    ToolbarAction.view,
    ToolbarAction.edit,
    ToolbarAction.delete,
    ToolbarAction.refresh,
  ];

  Widget _phase2(BuildContext context, List<ToolbarCommand> fitting) {
    final List<ToolbarCommand> folded =
        commands.where((command) => !fitting.contains(command)).toList();
    final List<ToolbarAction> shown =
        actions.where((action) => isVisible?.call(action) ?? true).toList();
    final bool hasNew = shown.contains(ToolbarAction.newItem);
    final List<ToolbarAction> icons = _everyDay.where(shown.contains).toList();
    final List<ToolbarAction> rest = shown
        .where((action) =>
            action != ToolbarAction.newItem && !_everyDay.contains(action))
        .toList();
    return Row(mainAxisSize: MainAxisSize.min, children: [
      for (final Widget widget in trailing) ...[
        widget,
        const SizedBox(width: 6),
      ],
      for (final ToolbarAction action in icons) ...[
        _Phase2IconAction(
          key: ValueKey('toolbar-${action.name}'),
          action: action,
          onPressed: isEnabled(action) ? () => onAction(action) : null,
        ),
        const SizedBox(width: 4),
      ],
      if (icons.isNotEmpty) const SizedBox(width: 2),
      for (final ToolbarCommand command in fitting) ...[
        Tooltip(
          message: command.tooltip ?? command.label,
          child: OutlinedButton.icon(
            key: ValueKey('toolbar-command-${command.id}'),
            onPressed: command.onPressed,
            icon: Icon(command.icon, size: 16),
            label: Text(command.label),
          ),
        ),
        const SizedBox(width: 6),
      ],
      if (rest.isNotEmpty || folded.isNotEmpty)
        PopupMenuButton<VoidCallback>(
          key: const ValueKey('toolbar-more'),
          tooltip: 'More actions',
          onSelected: (run) => run(),
          itemBuilder: (context) => [
            for (final ToolbarCommand command in folded)
              PopupMenuItem<VoidCallback>(
                key: ValueKey('toolbar-command-${command.id}-menu'),
                value: command.onPressed,
                enabled: command.onPressed != null,
                child: Row(children: [
                  Icon(command.icon, size: 18),
                  const SizedBox(width: 10),
                  Text(command.label),
                ]),
              ),
            if (folded.isNotEmpty && rest.isNotEmpty) const PopupMenuDivider(),
            for (final ToolbarAction action in rest)
              PopupMenuItem<VoidCallback>(
                value: () => onAction(action),
                enabled: isEnabled(action),
                child: Row(children: [
                  Icon(action.icon, size: 18),
                  const SizedBox(width: 10),
                  Text(action.label),
                ]),
              ),
          ],
          child: const _Phase2Button(child: Text('…')),
        ),
      if (hasNew) ...[
        const SizedBox(width: 6),
        FilledButton(
          key: const ValueKey('toolbar-new'),
          onPressed: isEnabled(ToolbarAction.newItem)
              ? () => onAction(ToolbarAction.newItem)
              : null,
          child: Text(newLabel),
        ),
      ],
    ]);
  }

  Widget _phase1(BuildContext context) => Wrap(
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
          for (final ToolbarCommand command in commands)
            OutlinedButton.icon(
              key: ValueKey('toolbar-command-${command.id}'),
              onPressed: command.onPressed,
              icon: Icon(command.icon, size: 18),
              label: Text(command.label),
            ),
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

  /// The same box with [node] as its focus, so the list around it can put
  /// the keyboard there ("/" and Ctrl+F).
  SearchFilterPanel withFocusNode(FocusNode node) => SearchFilterPanel(
        key: key,
        controller: controller,
        onSearch: onSearch,
        filters: filters,
        hintText: hintText,
        focusNode: node,
        onChanged: onChanged,
        onClear: onClear,
      );

  /// The same box without its filters, which phase 2 shows in the side
  /// panel instead.
  SearchFilterPanel withoutFilters() => SearchFilterPanel(
        key: key,
        controller: controller,
        onSearch: onSearch,
        hintText: hintText,
        focusNode: focusNode,
        onChanged: onChanged,
        onClear: onClear,
      );

  /// Fires on every keystroke so the caller can debounce a request.
  final ValueChanged<String>? onChanged;
  final VoidCallback? onClear;

  @override
  Widget build(BuildContext context) {
    if (Phase2Scope.of(context) && (filters == null || filters!.isEmpty)) {
      return _phase2(context);
    }
    return _phase1(context);
  }

  /// Phase 2 (the wireframe): a small box that says "/ search ...", with no
  /// icon of its own -- "/" is the key that reaches it.
  Widget _phase2(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final OutlineInputBorder edge = OutlineInputBorder(
      borderRadius: BorderRadius.circular(5),
      borderSide: BorderSide(color: theme.colorScheme.outlineVariant),
    );
    return SizedBox(
      height: 32,
      child: ValueListenableBuilder<TextEditingValue>(
        valueListenable: controller,
        builder: (context, value, _) => TextField(
          focusNode: focusNode,
          controller: controller,
          onSubmitted: onSearch,
          onChanged: onChanged,
          style: theme.textTheme.bodyMedium?.copyWith(fontSize: 13),
          decoration: InputDecoration(
            isDense: true,
            hintText: '/  ${hintText.toLowerCase()}',
            hintStyle: theme.textTheme.bodyMedium?.copyWith(
              fontSize: 13,
              color: theme.colorScheme.onSurfaceVariant,
            ),
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            enabledBorder: edge,
            border: edge,
            focusedBorder: edge.copyWith(
              borderSide: BorderSide(color: theme.colorScheme.primary),
            ),
            suffixIconConstraints:
                const BoxConstraints(minWidth: 28, minHeight: 28),
            suffixIcon: value.text.isEmpty
                ? null
                : IconButton(
                    tooltip: 'Clear search',
                    iconSize: 16,
                    padding: EdgeInsets.zero,
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
    );
  }

  Widget _phase1(BuildContext context) => Wrap(
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
  Widget build(BuildContext context) {
    if (Phase2Scope.of(context)) return _phase2(context);
    return _tile(context);
  }

  /// Phase 2: the fields themselves, one per line, for the side panel that
  /// [ManagementWorkspaceLayout] opens from its Filters button (4.5). No tile
  /// to expand: the panel is already the thing somebody opened on purpose.
  Widget _phase2(BuildContext context) => Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (final Widget field in children)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.md),
                child: field,
              ),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(
                  onPressed: activeFilterCount == 0 ? null : onClear,
                  child: const Text('Clear'),
                ),
                const SizedBox(width: AppSpacing.sm),
                FilledButton.tonal(
                  onPressed: onApply,
                  child: const Text('Apply'),
                ),
              ],
            ),
          ],
        ),
      );

  Widget _tile(BuildContext context) => ExpansionTile(
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
            // Room above the first row so a floating label does not sit
            // against the tile's title.
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.lg,
              AppSpacing.sm,
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
    this.viewBar,
    this.lineChips = const [],
  });

  final Widget toolbar;
  final Widget searchPanel;

  /// Phase 2: chips drawn after "+ filter" on the page line -- the
  /// wireframe's "Views" menu of saved and recent searches. Phase 1, which
  /// has no such line, ignores them.
  final List<Widget> lineChips;
  final Widget primaryContent;
  final Widget? detailsPanel;
  final Widget statusBar;
  final double detailsWidth;
  final Widget? filterPanel;

  /// A row of named views over the same list, above the grid.
  ///
  /// For a list whose records fall into a handful of states somebody switches
  /// between all day — a purchase order being draft, open, cancelled or
  /// closed. Those are *views of one screen*, and the alternative to a slot
  /// here was a sidebar entry each, which is what Purchases had: five menu
  /// items that opened the same workspace with one filter preset.
  ///
  /// Distinct from [filterPanel], which is the collapsible advanced filters. A
  /// view is one click and always visible; a filter is a form.
  final Widget? viewBar;

  /// The most of the workspace's height an expanded [filterPanel] may take.
  ///
  /// Unbounded, a panel with a dozen fields on a short or highly scaled
  /// display took nearly all of it, and the grid below was left a sliver with
  /// no reachable rows (D-QA-15). Past this share the panel scrolls itself.
  static const double filterPanelMaxShare = 0.45;

  @override
  Widget build(BuildContext context) {
    if (Phase2Scope.of(context)) return _Phase2ManagementLayout(layout: this);
    return LayoutBuilder(
      builder: (context, outer) => _build(
        outer.hasBoundedHeight
            ? outer.maxHeight * filterPanelMaxShare
            : double.infinity,
      ),
    );
  }

  Widget _build(double filterMaxHeight) => Column(children: [
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
        if (filterPanel != null)
          ConstrainedBox(
            constraints: BoxConstraints(maxHeight: filterMaxHeight),
            child: SingleChildScrollView(child: filterPanel!),
          ),
        if (viewBar != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 12, 24, 0),
            child: Align(alignment: Alignment.centerLeft, child: viewBar!),
          ),
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

/// [ManagementWorkspaceLayout] in the phase 2 app (UI_PHASE_2_DESIGN.md 4.5).
///
/// Search, a Filters button and the actions share **one** line; the filters
/// open in a panel beside the grid rather than a tile above it, so opening
/// them never pushes the rows down; margins are 12 px, not 24. The panel is
/// inline rather than a dialog on purpose: a screen's filter fields live in
/// its own state, and a dialog would keep showing the values it was opened
/// with while that state moved on.
class _Phase2ManagementLayout extends StatefulWidget {
  const _Phase2ManagementLayout({required this.layout});

  final ManagementWorkspaceLayout layout;

  @override
  State<_Phase2ManagementLayout> createState() =>
      _Phase2ManagementLayoutState();
}

class _Phase2ManagementLayoutState extends State<_Phase2ManagementLayout> {
  bool _filtersOpen = false;

  /// The line this list took, so it can be given back when the list goes.
  Phase2PageBar? _bar;

  /// The search box's focus, when the screen gave it none.
  final FocusNode _ownSearchFocus = FocusNode(debugLabel: 'list-search');

  /// The search box's focus as last built: the screen's own, or ours.
  FocusNode? _searchFocus;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _bar = Phase2PageBar.of(context);
  }

  @override
  void initState() {
    super.initState();
    // At the window, not on a Focus around the list: a click on a grid row
    // takes no focus, and a screen's own shortcuts above the list would see
    // the key first. Only the list on show answers (see [_onKey]).
    HardwareKeyboard.instance.addHandler(_onKey);
  }

  @override
  void dispose() {
    HardwareKeyboard.instance.removeHandler(_onKey);
    _bar?.release(this);
    _ownSearchFocus.dispose();
    super.dispose();
  }

  /// The keys of 4.10, the same on every list whatever the screen wired
  /// itself: Ctrl+N new, F2 edit, F5 refresh, Delete delete, and "/" or
  /// Ctrl+F to the search box. A key typed into a text box is the box's --
  /// "/" in a remark is a slash.
  bool _onKey(KeyEvent event) {
    if (event is! KeyDownEvent || !mounted) return false;
    // Only the list on show: not one kept alive in another tab (its ticker
    // is off), not one behind a dialog or a document.
    if (!TickerMode.valuesOf(context).enabled) return false;
    if (!(ModalRoute.of(context)?.isCurrent ?? true)) return false;
    final BuildContext? focused = FocusManager.instance.primaryFocus?.context;
    final bool typing = focused != null &&
        (focused.widget is EditableText ||
            focused.findAncestorWidgetOfExactType<EditableText>() != null);
    final HardwareKeyboard keys = HardwareKeyboard.instance;
    final bool control = keys.isControlPressed;
    final bool plain = !control && !keys.isAltPressed && !keys.isMetaPressed;
    final LogicalKeyboardKey key = event.logicalKey;
    if ((plain && !typing && event.character == '/') ||
        (control && key == LogicalKeyboardKey.keyF)) {
      final FocusNode? search = _searchFocus;
      if (search == null) return false;
      search.requestFocus();
      return true;
    }
    if (typing) return false;
    final ToolbarAction? action = control && key == LogicalKeyboardKey.keyN
        ? ToolbarAction.newItem
        : plain && key == LogicalKeyboardKey.f2
            ? ToolbarAction.edit
            : plain && key == LogicalKeyboardKey.f5
                ? ToolbarAction.refresh
                : plain && key == LogicalKeyboardKey.delete
                    ? ToolbarAction.delete
                    : null;
    if (action == null) return false;
    return _run(action);
  }

  /// Run [action] as the screen's toolbar would, if it offers it and it is
  /// enabled. A screen with its own row of buttons has its filled one --
  /// its "New" -- run for Ctrl+N.
  bool _run(ToolbarAction action) {
    final Widget toolbar = widget.layout.toolbar;
    if (toolbar is WorkspaceToolbar) {
      final bool offered = toolbar.actions.contains(action) &&
          (toolbar.isVisible?.call(action) ?? true);
      if (!offered || !toolbar.isEnabled(action)) return false;
      toolbar.onAction(action);
      return true;
    }
    if (toolbar is Wrap && action == ToolbarAction.newItem) {
      for (final Widget child in toolbar.children) {
        if (child is FilledButton && child.onPressed != null) {
          child.onPressed!();
          return true;
        }
      }
    }
    return false;
  }

  static const double _filterWidth = 300;

  @override
  Widget build(BuildContext context) {
    final ManagementWorkspaceLayout layout = widget.layout;
    final int active = layout.filterPanel is FilterPanel
        ? (layout.filterPanel! as FilterPanel).activeFilterCount
        : 0;
    // A search that carries its own filters (area, status, include deleted)
    // stacked them beside the box and made the line three rows tall. Phase 2
    // keeps the box on the line and moves the filters into the side panel
    // "+ filter" opens, with any the screen already had there.
    Widget searchPanel = layout.searchPanel;
    Widget? filters = layout.filterPanel;
    Widget ownSearch = layout.searchPanel;
    _searchFocus = null;
    if (ownSearch is SearchFilterPanel) {
      _searchFocus = ownSearch.focusNode ?? _ownSearchFocus;
      if (ownSearch.focusNode == null) {
        ownSearch = ownSearch.withFocusNode(_ownSearchFocus);
      }
      searchPanel = ownSearch;
    }
    if (ownSearch is SearchFilterPanel &&
        (ownSearch.filters?.isNotEmpty ?? false)) {
      searchPanel = ownSearch.withoutFilters();
      final Widget moved = FilterPanel(children: ownSearch.filters!);
      filters = filters == null
          ? moved
          : Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: [filters, moved],
            );
    }
    final ColorScheme scheme = Theme.of(context).colorScheme;
    // The frame above hands over its title and counters; this draws them on
    // the same line as the search and the actions (4.5).
    final Phase2PageBar? bar = Phase2PageBar.of(context);
    bar?.claim(this);
    // Filters, search and actions. The search box is a fixed, modest width
    // on the one line -- the wireframe's "/ search" -- so the counters get
    // the room; on a line of its own it takes what is left.
    // The toolbar is told how wide it may be, so a screen's own commands
    // fold into "..." instead of pushing the line past the window.
    List<Widget> working({
      required bool fixedSearch,
      required double toolbarWidth,
    }) =>
        [
          if (fixedSearch)
            SizedBox(width: 260, child: searchPanel)
          else
            Expanded(child: searchPanel),
          const SizedBox(width: 8),
          ConstrainedBox(
            constraints: BoxConstraints(
              maxWidth: toolbarWidth < 120 ? 120 : toolbarWidth,
            ),
            child: _newLast(layout.toolbar),
          ),
        ];
    // The wireframe's "+ filter" chip sits with the counters, at the left.
    final List<Widget> filterChip = [
      if (filters != null) ...[
        const SizedBox(width: 6),
        _filtersButton(active, scheme),
      ],
      for (final Widget chip in layout.lineChips) ...[
        const SizedBox(width: 6),
        chip,
      ],
    ];
    // Rebuilt when the counters arrive: how much room the actions get
    // depends on them.
    final Widget line = ValueListenableBuilder<List<Widget>>(
      valueListenable: bar?.counters ?? ValueNotifier(const []),
      builder: (context, _, __) => Padding(
        padding: const EdgeInsets.fromLTRB(12, 6, 12, 6),
        child: LayoutBuilder(builder: (context, constraints) {
          if (bar == null) {
            return Row(children: [
              ...filterChip,
              const SizedBox(width: 8),
              ...working(
                fixedSearch: false,
                toolbarWidth:
                    constraints.maxWidth - 200 - 110 * filterChip.length,
              ),
            ]);
          }
          // Everything the one line holds besides the toolbar: the title, the
          // counters, the chips and the search.
          final double beside = _titleWidth(context, bar) +
              _countersWidth(context, bar) +
              110.0 * (filters == null ? 0 : 1) +
              110.0 * layout.lineChips.length +
              260 +
              8;
          // 4.11: on a narrow window, or where the line cannot hold the
          // screen's actions, it becomes two -- title and counters, then the
          // work -- rather than squeezing either.
          final bool twoLines = constraints.maxWidth < 1100 ||
              constraints.maxWidth - beside < 260;
          if (twoLines) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(children: [
                  Phase2PageTitle(bar: bar),
                  Flexible(child: Phase2PageCounters(bar: bar)),
                  ...filterChip,
                ]),
                const SizedBox(height: 4),
                Row(
                  children: working(
                    fixedSearch: false,
                    toolbarWidth: constraints.maxWidth - 208,
                  ),
                ),
              ],
            );
          }
          // The counters and the filter chip take what the search and the
          // actions leave; only what they do not need is the gap. (A Flexible
          // beside a Spacer split the spare width, and five counters were cut
          // off in half of it.)
          return Row(children: [
            Phase2PageTitle(bar: bar),
            Expanded(
              child: Align(
                alignment: Alignment.centerLeft,
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Flexible(child: Phase2PageCounters(bar: bar)),
                  ...filterChip,
                ]),
              ),
            ),
            const SizedBox(width: 8),
            ...working(
              fixedSearch: true,
              toolbarWidth: constraints.maxWidth - beside,
            ),
          ]);
        }),
      ),
    );
    return KeyedSubtree(
      child: Column(children: [
        // Every button on the line in the wireframe's one small, square-
        // cornered style, whichever screen built it -- on a white band with a
        // line beneath, so the page bar reads apart from the grey heading row
        // of the table under it (it sat on the page's grey and ran into it).
        ColoredBox(
          color: scheme.surfaceContainerLowest,
          child: Phase2ButtonTheme(child: line),
        ),
        Divider(height: 1, thickness: 1, color: scheme.outlineVariant),
        if (layout.viewBar != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 4),
            child:
                Align(alignment: Alignment.centerLeft, child: layout.viewBar),
          ),
        Expanded(
          // Edge to edge, as the wireframe's grid: the cells pad themselves.
          child: Padding(
            padding: EdgeInsets.zero,
            child: LayoutBuilder(builder: (context, constraints) {
              final double detailsWidth = layout.detailsWidth
                  .clamp(240, constraints.maxWidth * .36)
                  .toDouble();
              return Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Expanded(child: layout.primaryContent),
                  if (layout.detailsPanel != null) ...[
                    const SizedBox(width: 12),
                    SizedBox(width: detailsWidth, child: layout.detailsPanel),
                  ],
                  if (filters != null && _filtersOpen) ...[
                    const SizedBox(width: 12),
                    SizedBox(
                      width: _filterWidth,
                      child: _filterPanel(filters, scheme),
                    ),
                  ],
                ],
              );
            }),
          ),
        ),
        layout.statusBar,
      ]),
    );
  }

  /// A screen's own row of buttons with its filled one -- its "New" --
  /// moved to the end, where every list keeps "+ New" (4.7). The toolbar is
  /// the screen's own widget; only its order changes, and only here.
  static Widget _newLast(Widget toolbar) {
    if (toolbar is! Wrap) return toolbar;
    final List<Widget> children = toolbar.children;
    final List<Widget> filled = [
      for (final Widget child in children)
        if (child is FilledButton) child,
    ];
    if (filled.isEmpty || identical(children.last, filled.last)) {
      return toolbar;
    }
    return Wrap(
      key: toolbar.key,
      spacing: toolbar.spacing,
      runSpacing: toolbar.runSpacing,
      crossAxisAlignment: toolbar.crossAxisAlignment,
      children: [
        for (final Widget child in children)
          if (child is! FilledButton) child,
        ...filled,
      ],
    );
  }

  static double _measure(BuildContext context, String text, TextStyle style) {
    final TextPainter painter = TextPainter(
      text: TextSpan(text: text, style: style),
      textDirection: TextDirection.ltr,
      textScaler: MediaQuery.textScalerOf(context),
      maxLines: 1,
    )..layout();
    final double width = painter.width;
    painter.dispose();
    return width;
  }

  /// About how wide the page title is, with its (i).
  static double _titleWidth(BuildContext context, Phase2PageBar bar) =>
      _measure(
        context,
        Phase2ScreenTitle.of(context) ?? bar.title,
        const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
      ) +
      40;

  /// About how wide the counters are: each is its label and figure in a
  /// pill.
  static double _countersWidth(BuildContext context, Phase2PageBar bar) {
    double width = 0;
    for (final Widget counter in bar.counters.value) {
      width += counter is SummaryCount
          ? _measure(context, '${counter.label} ${counter.value}',
                  const TextStyle(fontSize: 13)) +
              30
          : 90;
    }
    return width;
  }

  /// The wireframe's "+ filter" chip; with filters on it says how many and
  /// is tinted, so a narrowed list is never mistaken for the whole.
  Widget _filtersButton(int active, ColorScheme scheme) {
    final String label = active == 0 ? '+ filter' : 'Filters ($active)';
    final bool on = _filtersOpen || active > 0;
    return ActionChip(
      key: const ValueKey('phase2-filters'),
      label: Text(label),
      labelStyle: Theme.of(context)
          .textTheme
          .bodyMedium
          ?.copyWith(fontSize: 13, color: scheme.onSurface),
      onPressed: () => setState(() => _filtersOpen = !_filtersOpen),
      backgroundColor: on ? scheme.primary.withValues(alpha: .12) : null,
      side: BorderSide(color: on ? scheme.primary : scheme.outlineVariant),
      shape: const StadiumBorder(),
      visualDensity: VisualDensity.compact,
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
    );
  }

  Widget _filterPanel(Widget filters, ColorScheme scheme) => Material(
        color: scheme.surfaceContainerLowest,
        shape: RoundedRectangleBorder(
          borderRadius: AppRadius.medium,
          side: BorderSide(color: scheme.outlineVariant),
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 6, 4, 0),
            child: Row(children: [
              Expanded(
                child: Text(
                  'Filters',
                  style: Theme.of(context).textTheme.titleSmall,
                ),
              ),
              IconButton(
                tooltip: 'Close filters',
                icon: const Icon(Icons.close, size: 18),
                onPressed: () => setState(() => _filtersOpen = false),
              ),
            ]),
          ),
          Expanded(child: SingleChildScrollView(child: filters)),
        ]),
      );
}

/// The phase 2 page line's buttons, whoever built them: the wireframe's
/// small square-cornered buttons (5 px), a grey edge and dark text on the
/// outlined ones, the accent only on the filled one (+ New).
class Phase2ButtonTheme extends StatelessWidget {
  const Phase2ButtonTheme({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final RoundedRectangleBorder shape =
        RoundedRectangleBorder(borderRadius: BorderRadius.circular(5));
    const EdgeInsets padding =
        EdgeInsets.symmetric(horizontal: 12, vertical: 6);
    const Size size = Size(0, 32);
    final TextStyle? text = theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    return Theme(
      data: theme.copyWith(
        outlinedButtonTheme: OutlinedButtonThemeData(
          style: OutlinedButton.styleFrom(
            foregroundColor: scheme.onSurface,
            side: BorderSide(color: scheme.outlineVariant),
            textStyle: text,
            shape: shape,
            padding: padding,
            minimumSize: size,
            visualDensity: VisualDensity.compact,
            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          ),
        ),
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            textStyle: text,
            shape: shape,
            padding: padding,
            minimumSize: size,
            visualDensity: VisualDensity.compact,
            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          ),
        ),
        textButtonTheme: TextButtonThemeData(
          style: TextButton.styleFrom(
            textStyle: text,
            shape: shape,
            padding: padding,
            minimumSize: size,
            visualDensity: VisualDensity.compact,
          ),
        ),
      ),
      child: child,
    );
  }
}

/// An everyday action on the page line: a small square button with a grey
/// edge and the action's icon, its name on hover; greyed while it has no row
/// to act on, and Delete in the danger colour so it is not taken by mistake.
class _Phase2IconAction extends StatelessWidget {
  const _Phase2IconAction({
    super.key,
    required this.action,
    required this.onPressed,
  });

  final ToolbarAction action;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final bool danger = action == ToolbarAction.delete;
    return Tooltip(
      message: action.label,
      child: IconButton(
        onPressed: onPressed,
        icon: Icon(action.icon, size: 18),
        style: IconButton.styleFrom(
          fixedSize: const Size(32, 32),
          minimumSize: const Size(32, 32),
          padding: EdgeInsets.zero,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          visualDensity: VisualDensity.compact,
          foregroundColor: danger ? scheme.error : scheme.onSurface,
          disabledForegroundColor:
              scheme.onSurfaceVariant.withValues(alpha: .45),
          backgroundColor: scheme.surfaceContainerLowest,
          side: BorderSide(color: scheme.outlineVariant),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(5)),
        ),
      ),
    );
  }
}

/// A plain bordered box the size of the line's other buttons -- the child of
/// a menu button such as the toolbar's "more".
class _Phase2Button extends StatelessWidget {
  const _Phase2Button({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Container(
      height: 32,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(5),
        border: Border.all(color: scheme.outlineVariant),
        color: scheme.surfaceContainerLowest,
      ),
      child: DefaultTextStyle.merge(
        style: TextStyle(color: scheme.onSurface),
        child: child,
      ),
    );
  }
}

class GridColumn {
  const GridColumn({
    required this.key,
    required this.label,
    this.onSort,
    this.visible = true,
    this.tooltip,
    this.numeric = false,
    this.priority,
  });
  final String key;
  final String label;
  final void Function(bool ascending)? onSort;
  final bool visible;
  final String? tooltip;

  /// An amount or a count. Phase 2 right-aligns it and groups its digits the
  /// Indian way (1,12,050.00), as the wireframe's Credit limit and Balance.
  final bool numeric;

  /// How much the column matters when the window is narrow (design 4.11):
  /// 1 always stays, 2 goes next, 3 goes first. Phase 2 drops columns from 3
  /// up, rightmost first, until the table fits, and scrolls sideways only
  /// when even the 1s do not. Null takes [effectivePriority]'s reading of
  /// the heading.
  final int? priority;

  /// Columns a narrow window can spare first: tax numbers, audit dates,
  /// contact details and notes -- the wireframe's p3 (GST, HSN, MRP).
  static const Set<String> _spareFirst = {
    'created',
    'created at',
    'created on',
    'updated',
    'updated at',
    'modified',
    'gst',
    'gstin',
    'gst number',
    'gst no',
    'pan',
    'hsn',
    'hsn code',
    'hsn/sac',
    'mrp',
    'email',
    'e-mail',
    'remarks',
    'notes',
    'description',
    'reference',
    'ref',
    'credit limit',
    'barcode',
  };

  /// Columns that go next: the wireframe's p2 (Phone, Brand).
  static const Set<String> _spareNext = {
    'phone',
    'mobile',
    'contact',
    'brand',
    'type',
    'group',
    'territory',
    'route',
    'branch',
    'warehouse',
    'owner',
    'salesperson',
    'sales person',
    'created by',
    'due date',
  };

  /// The priority phase 2 uses: the one given, else read from the heading.
  /// The leading column -- the code or number a row is known by -- always
  /// stays.
  int effectivePriority({required bool leading}) {
    if (priority != null) return priority!;
    if (leading) return 1;
    final String name = label.trim().toLowerCase();
    if (_spareFirst.contains(name)) return 3;
    if (_spareNext.contains(name)) return 2;
    return 1;
  }

  /// A heading that names an amount or a count. Phase 2 treats such a
  /// column as [numeric] when every value in it is a number, so a screen
  /// that never said so still right-aligns its totals.
  bool get looksNumeric => RegExp(
        r'(total|amount|balance|price|value|qty|quantity|outstanding|'
        r'advance|limit|cost|paid|discount|points|stock|on hand|available|'
        r'reserved|mrp|selling|debit|credit|opening|closing|tax|payable|'
        r'receivable|net|gross|factor)',
        caseSensitive: false,
      ).hasMatch(label);

  /// A count of goods rather than money: shown without the store's trailing
  /// zeros (876, 2.5), where money keeps two places.
  bool get isQuantity => RegExp(
        r'(qty|quantity|stock|on hand|available|reserved|points|factor)',
        caseSensitive: false,
      ).hasMatch(label);

  /// A status column: phase 2 writes its value as plain words ("On hold"),
  /// as the wireframe does, rather than as a code in capitals.
  bool get isStatus =>
      label.trim().toLowerCase() == 'status' || key.toLowerCase() == 'status';
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
    this.alertCell,
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

  /// Phase 2: a cell that needs attention -- the wireframe's low stock --
  /// drawn in the error colour and bold. Applies to the grid's own cells,
  /// amounts included, so a screen need not build one to colour it.
  final bool Function(int columnIndex, T item)? alertCell;

  @override
  State<EnterpriseDataGrid<T>> createState() => _EnterpriseDataGridState<T>();
}

class _EnterpriseDataGridState<T> extends State<EnterpriseDataGrid<T>> {
  /// Owned here so the visible scrollbar and the scroll view share one
  /// controller; a `Scrollbar` with `thumbVisibility` needs a controller that
  /// survives rebuilds, which a stateless widget cannot give it.
  final ScrollController _horizontal = ScrollController();

  /// The row under the pointer, so phase 2 can light the whole row as the
  /// wireframe does -- each cell is its own tap target, and left to itself
  /// the pointer lit only the cell (the column) it was over.
  String? _hovered;

  @override
  void dispose() {
    _horizontal.dispose();
    super.dispose();
  }

  /// Phase 2 (the wireframe's grid): edge to edge, no card; a soft header;
  /// compact rows; no Actions column -- a row opens on double-click or Enter,
  /// and its actions are on right-click -- and amounts right-aligned.
  bool get _phase2 => Phase2Scope.of(context);

  bool get _showActionsColumn =>
      !_phase2 &&
      (widget.onOpen != null ||
          widget.contextActions.isNotEmpty ||
          widget.contextActionsFor != null ||
          widget.onContextAction != null);

  bool get _multiSelection => widget.onSelectionChanged != null;

  int get _page => widget.rowsPerPage <= 0
      ? 1
      : (widget.pageOffset ~/ widget.rowsPerPage) + 1;

  List<MapEntry<int, GridColumn>> get _visibleColumns => widget.columns
      .asMap()
      .entries
      .where((entry) => entry.value.visible && !_dropped.contains(entry.key))
      .toList();

  /// The widest a phase 2 cell grows.
  static const double _maxCellWidth = 260;

  /// Columns phase 2 has left out because the window is too narrow for them
  /// (design 4.11), by index into `widget.columns`. Worked out afresh on
  /// every layout from the width the grid is given.
  Set<int> _dropped = const {};

  /// Each column's natural width, measured from its heading and this page's
  /// values. Cached per page, because the grid rebuilds on every hover.
  List<double>? _widths;
  Object? _widthsFor;

  /// Columns phase 2 draws as figures: those declared [GridColumn.numeric],
  /// and those whose heading names an amount and whose values on this page
  /// are all numbers. Worked out with the widths, per page.
  Set<int> _numericColumns = const {};

  bool _isNumeric(int index) => _numericColumns.contains(index);

  /// A figure as phase 2 shows it: money grouped the Indian way with two
  /// places, a quantity without trailing zeros.
  String _figure(GridColumn column, String raw) {
    if (!column.isQuantity) return _grouped(raw);
    final double? number = double.tryParse(raw.replaceAll(',', '').trim());
    if (number == null) return raw;
    if (number == number.roundToDouble()) {
      final String text = indianAmount(number, full: true);
      return text.substring(0, text.length - 3);
    }
    return raw.trim().replaceFirst(RegExp(r'0+$'), '');
  }

  /// Plain words for a status code: ON_HOLD becomes "On hold".
  static String _statusWords(String value) {
    final String trimmed = value.trim();
    if (!RegExp(r'^[A-Z][A-Z0-9_ ]*$').hasMatch(trimmed)) return value;
    final String words = trimmed.replaceAll('_', ' ').toLowerCase();
    return words[0].toUpperCase() + words.substring(1);
  }

  /// The width each column would like, its heading and values measured in
  /// the grid's own type (13 px cells, 12 px bold headings); a long value is
  /// capped so one address cannot hold a column open.
  List<double> _naturalWidths(BuildContext context) {
    final TextScaler scaler = MediaQuery.textScalerOf(context);
    final Object key = Object.hashAll([
      identityHashCode(widget.items),
      widget.items.length,
      for (final GridColumn column in widget.columns) column.label,
      scaler.scale(13),
    ]);
    final List<double>? cached = _widths;
    if (cached != null && _widthsFor == key) return cached;
    final TextTheme text = Theme.of(context).textTheme;
    final TextStyle cell =
        (text.bodyMedium ?? const TextStyle()).copyWith(fontSize: 13);
    final TextStyle heading = (text.labelMedium ?? const TextStyle())
        .copyWith(fontSize: 12, fontWeight: FontWeight.w600);
    double measure(String value, TextStyle style) {
      final TextPainter painter = TextPainter(
        text: TextSpan(text: value, style: style),
        textDirection: TextDirection.ltr,
        textScaler: scaler,
        maxLines: 1,
      )..layout();
      final double width = painter.width;
      painter.dispose();
      return width;
    }

    final List<List<String>> rows = [
      for (final T item in widget.items) widget.cells(item),
    ];
    bool allNumbers(int i) {
      bool any = false;
      for (final List<String> values in rows) {
        final String raw = i < values.length ? values[i].trim() : '';
        if (raw.isEmpty || raw == '-') continue;
        if (double.tryParse(raw.replaceAll(',', '')) == null) return false;
        any = true;
      }
      return any;
    }

    _numericColumns = {
      for (int i = 0; i < widget.columns.length; i++)
        if (widget.columns[i].numeric ||
            (widget.columns[i].looksNumeric && allNumbers(i)))
          i,
    };
    final List<double> widths = [];
    for (int i = 0; i < widget.columns.length; i++) {
      final GridColumn column = widget.columns[i];
      double width =
          measure(column.label, heading) + (column.onSort == null ? 0 : 18);
      for (final List<String> values in rows) {
        if (i >= values.length) continue;
        final String raw = values[i];
        final String shown = _isNumeric(i)
            ? _figure(column, raw)
            : column.isStatus
                ? _statusWords(raw)
                : raw;
        final double value = measure(shown, cell);
        if (value > width) width = value;
      }
      widths.add(width.clamp(0, _maxCellWidth).toDouble());
    }
    _widths = widths;
    _widthsFor = key;
    return widths;
  }

  /// Phase 2: which columns to leave out so the table fits [available] --
  /// lowest priority first and, among equals, rightmost first. The column a
  /// row is known by is never dropped.
  Set<int> _columnsToDrop(BuildContext context, double available) {
    if (!_phase2) return const {};
    final List<double> widths = _naturalWidths(context);
    if (!available.isFinite) return const {};
    final List<int> shown = [
      for (int i = 0; i < widget.columns.length; i++)
        if (widget.columns[i].visible) i,
    ];
    if (shown.isEmpty) return const {};
    const double spacing = 20;
    double total = 2 * 10 +
        (_multiSelection ? 44 : 0) +
        (widget.showRowNumbers ? 40 + spacing : 0) +
        spacing * (shown.length - 1);
    for (final int i in shown) {
      total += widths[i];
    }
    if (total <= available) return const {};
    int priorityOf(int i) =>
        widget.columns[i].effectivePriority(leading: i == shown.first);
    final List<int> candidates = [
      for (final int i in shown)
        if (priorityOf(i) > 1) i,
    ]..sort((a, b) {
        final int byPriority = priorityOf(b).compareTo(priorityOf(a));
        return byPriority != 0 ? byPriority : b.compareTo(a);
      });
    final Set<int> dropped = {};
    for (final int i in candidates) {
      if (total <= available) break;
      dropped.add(i);
      total -= widths[i] + spacing;
    }
    return dropped;
  }

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
      // Phase 2: the wireframe's row colours, across the whole row -- soft
      // blue selected, light grey under the pointer.
      color: _phase2
          ? WidgetStatePropertyAll(isSelected
              ? _selectedRow(context)
              : itemId == _hovered
                  ? Theme.of(context).colorScheme.surfaceContainerLow
                  : null)
          : null,
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
          final String raw = entry.key < values.length ? values[entry.key] : '';
          final bool amount = _phase2 && _isNumeric(entry.key);
          final bool status = _phase2 && entry.value.isStatus;
          final String value = amount
              ? _figure(entry.value, raw)
              : status
                  ? _statusWords(raw)
                  : raw;
          return _dataCell(
            context,
            item: item,
            // An amount is drawn here, right-aligned in Indian digits, even
            // on a screen that builds its own cells -- or its heading moves
            // right and its figures stay left.
            content: (amount || status
                    ? null
                    : widget.cellBuilder?.call(entry.key, raw, item)) ??
                Tooltip(
                  message: value,
                  child: SizedBox(
                    width: double.infinity,
                    child: Text(
                      value,
                      overflow: TextOverflow.ellipsis,
                      textAlign: amount ? TextAlign.right : TextAlign.start,
                      style: _phase2 &&
                              (widget.alertCell?.call(entry.key, item) ?? false)
                          ? TextStyle(
                              color: Theme.of(context).colorScheme.error,
                              fontWeight: FontWeight.w600,
                            )
                          : null,
                    ),
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
    // Phase 2 caps a cell at the width the column priority measured with, so
    // one long name ends in "..." rather than holding the column open.
    Widget cell = _phase2
        ? ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: _maxCellWidth),
            child: content,
          )
        : content;
    if (isLeading) {
      // A marker on the row's leading edge, so the selection is not signalled
      // by colour alone -- the tint is easy to lose in high contrast, and
      // `DataRow` has no border of its own to use.
      cell = Container(
        // Phase 2 keeps the first column under its heading, as the wireframe;
        // the marker is the row's left edge rather than an indent.
        padding: EdgeInsets.only(left: _phase2 ? 0 : AppSpacing.sm),
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
    if (_phase2) {
      final String itemId = widget.id(item);
      cell = MouseRegion(
        onEnter: (_) {
          if (_hovered != itemId) setState(() => _hovered = itemId);
        },
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

  /// An amount's digits grouped the Indian way; anything that is not a
  /// number is left as it came.
  static String _grouped(String value) {
    final double? number = double.tryParse(value.replaceAll(',', '').trim());
    if (number == null) return value;
    final bool fraction = value.contains('.');
    final String text = indianAmount(number, full: true);
    return fraction ? text : text.substring(0, text.length - 3);
  }

  /// The wireframe's selected row: the accent at a tenth over the card, a
  /// soft blue (#e7ecff there).
  static Color _selectedRow(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Color.alphaBlend(
      scheme.primary.withValues(alpha: .10),
      scheme.surfaceContainerLowest,
    );
  }

  /// Phase 2: the table as the wireframe draws it -- 13 px cells, 12 px bold
  /// grey headings on a light ground, 34 px rows each with a light line under
  /// it, and no ink of its own (the row colour says where the pointer is).
  Widget _table(BuildContext context) {
    if (!_phase2) return _dataTable(context);
    final ThemeData theme = Theme.of(context);
    return Theme(
      data: theme.copyWith(
        hoverColor: Colors.transparent,
        splashColor: Colors.transparent,
        highlightColor: Colors.transparent,
        splashFactory: NoSplash.splashFactory,
        dividerTheme: DividerThemeData(
          color: theme.colorScheme.surfaceContainerHighest,
          space: 1,
          thickness: 1,
        ),
      ),
      child: MouseRegion(
        onExit: (_) => setState(() => _hovered = null),
        // The heading's own line, in the stronger grey: DataTable draws one
        // light line under every row, the heading's included, so the heading
        // did not stand apart from the first row. Drawn along its bottom
        // edge, which is fixed at 34 px.
        // `passthrough`: the table must keep the width the grid gives it; a
        // default Stack loosens it and the table shrank to its columns.
        child: Stack(fit: StackFit.passthrough, children: [
          _dataTable(context),
          Positioned(
            key: const ValueKey('grid-heading-line'),
            top: 33,
            left: 0,
            right: 0,
            height: 1,
            child: ColoredBox(color: theme.colorScheme.outlineVariant),
          ),
        ]),
      ),
    );
  }

  DataTable _dataTable(BuildContext context) => DataTable(
        horizontalMargin: _phase2 ? 10 : null,
        columnSpacing: _phase2 ? 20 : null,
        headingRowColor: _phase2
            ? WidgetStatePropertyAll(
                Theme.of(context).colorScheme.surfaceContainerLow)
            : null,
        headingTextStyle: _phase2
            ? Theme.of(context).textTheme.labelMedium?.copyWith(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                )
            : null,
        dataTextStyle: _phase2
            ? Theme.of(context).textTheme.bodyMedium?.copyWith(fontSize: 13)
            : null,
        dividerThickness: _phase2 ? 1 : null,
        dataRowMinHeight: _phase2 ? 34 : null,
        dataRowMaxHeight: _phase2 ? 34 : null,
        headingRowHeight: _phase2 ? 34 : null,
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
              numeric: _phase2 && _isNumeric(entry.key),
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
    final Widget body = Column(
      children: [
        Expanded(
          child: LayoutBuilder(
            builder: (context, constraints) {
              // A minimum, not a fixed width: a bare `DataTable` cannot shrink
              // below the width its columns need and would overflow instead.
              // Phase 2 fits the table to the window by leaving out its
              // least important columns first (design 4.11); only what is
              // still too wide scrolls sideways.
              _dropped = _columnsToDrop(context, constraints.maxWidth);
              final double minWidth = _phase2
                  ? constraints.maxWidth
                  : constraints.maxWidth < 720
                      ? 720
                      : constraints.maxWidth;
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
                        child: _table(context),
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
    );
    if (_phase2) {
      return ColoredBox(
        color: Theme.of(context).colorScheme.surfaceContainerLowest,
        child: body,
      );
    }
    return Card(clipBehavior: Clip.antiAlias, child: body);
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
  Widget build(BuildContext context) {
    if (Phase2Scope.of(context)) return _counter(context);
    return _card(context);
  }

  /// Phase 2 (4.5): a figure is a counter on one line, not a 100 px card --
  /// cards with charts belong on Home, where somebody goes to look at
  /// numbers, not on the list where they go to work.
  Widget _counter(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerLow,
        borderRadius: AppRadius.medium,
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Text(
          label,
          style: theme.textTheme.bodySmall
              ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
        const SizedBox(width: 6),
        Text(
          value,
          style:
              theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
        ),
      ]),
    );
  }

  Widget _card(BuildContext context) => SizedBox(
        width: width,
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Row(children: [
              Icon(icon,
                  size: 32, color: Theme.of(context).colorScheme.primary),
              const SizedBox(width: 16),
              // Bounded, because the card is a fixed width and the text is
              // not: a long label — or a purchase value with enough digits —
              // overflowed the row rather than eliding inside it.
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      value,
                      style: Theme.of(context).textTheme.headlineSmall,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    Text(label, maxLines: 2, overflow: TextOverflow.ellipsis),
                  ],
                ),
              ),
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
  Widget build(BuildContext context) {
    // Phase 2: the window has one bottom bar (the wireframe's), and this
    // list's line goes into it rather than making a second bar above it.
    final Phase2StatusScope? bar =
        Phase2Scope.of(context) ? Phase2StatusScope.of(context) : null;
    if (bar != null) {
      bar.publish(Row(mainAxisSize: MainAxisSize.min, children: [
        Text('$total record${total == 1 ? '' : 's'}'),
        if (selected) ...[
          const SizedBox(width: 18),
          Text('${selectedCount ?? 1} selected'),
        ],
        if (message != null) ...[
          const SizedBox(width: 18),
          Text(message!),
        ],
      ]));
      return const SizedBox.shrink();
    }
    return _bar(context);
  }

  Widget _bar(BuildContext context) => Material(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        child: Padding(
          // Phase 2 without the window's bar (a page on its own) keeps it
          // to one thin line.
          padding: Phase2Scope.of(context)
              ? const EdgeInsets.symmetric(horizontal: 12, vertical: 4)
              : const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
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
        // Phase 2: a thin bar along the top while a screen loads, rather
        // than greying the whole screen -- which flashed on every refresh
        // and read as a modal the user had to wait out.
        if (loading && Phase2Scope.of(context))
          const Positioned(
            key: ValueKey('loading-bar'),
            top: 0,
            left: 0,
            right: 0,
            child: LinearProgressIndicator(minHeight: 2),
          )
        else if (loading)
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

/// Phase 2: a chip on the page line that opens a menu -- the wireframe's
/// "Views" beside "+ filter". Drawn like that chip, so the line reads as one
/// row of chips rather than chips and buttons.
class Phase2MenuChip<T> extends StatelessWidget {
  const Phase2MenuChip({
    super.key,
    required this.label,
    required this.itemBuilder,
    required this.onSelected,
    this.icon,
    this.tooltip,
  });

  final String label;
  final IconData? icon;
  final String? tooltip;
  final PopupMenuItemBuilder<T> itemBuilder;
  final PopupMenuItemSelected<T> onSelected;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final TextStyle? style = Theme.of(context)
        .textTheme
        .bodyMedium
        ?.copyWith(fontSize: 13, color: scheme.onSurface);
    return PopupMenuButton<T>(
      tooltip: tooltip ?? label,
      position: PopupMenuPosition.under,
      itemBuilder: itemBuilder,
      onSelected: onSelected,
      child: Container(
        height: 32,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        decoration: ShapeDecoration(
          shape: StadiumBorder(side: BorderSide(color: scheme.outlineVariant)),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          if (icon != null) ...[
            Icon(icon, size: 16, color: scheme.onSurfaceVariant),
            const SizedBox(width: 4),
          ],
          Text(label, style: style),
          Icon(Icons.arrow_drop_down, size: 18, color: scheme.onSurfaceVariant),
        ]),
      ),
    );
  }
}

/// Phase 2: a screen's own search box and buttons, for a screen that builds
/// its own header rather than using [ManagementWorkspaceLayout]. Inside a
/// page frame they go on the frame's one line, at the right, and nothing is
/// drawn here -- so the screen loses its second header line. Elsewhere they
/// are drawn here, in a row.
class Phase2LineTools extends StatelessWidget {
  const Phase2LineTools({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final Phase2PageBar? bar = Phase2PageBar.of(context);
    if (bar != null) {
      bar.publishTools(children);
      return const SizedBox.shrink();
    }
    // No frame above: draw the line here, with the menu's name for the
    // screen as its title, in the same white band a frame draws.
    final ThemeData theme = Theme.of(context);
    final String? title = Phase2ScreenTitle.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerLowest,
        border: Border(
          bottom: BorderSide(color: theme.colorScheme.outlineVariant),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 6, 12, 6),
        child: Phase2ButtonTheme(
          child: Row(children: [
            if (title != null)
              Text(
                title,
                style: theme.textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
            const Spacer(),
            for (final Widget child in children) ...[
              const SizedBox(width: 6),
              child,
            ],
          ]),
        ),
      ),
    );
  }
}

/// A screen's own Refresh button: phase 1 draws [child], the button it
/// always drew; phase 2 draws the page line's refresh icon, as every list
/// has, rather than a word.
class Phase2Refresh extends StatelessWidget {
  const Phase2Refresh({
    super.key,
    required this.onPressed,
    required this.child,
  });

  final VoidCallback? onPressed;
  final Widget child;

  @override
  Widget build(BuildContext context) => Phase2Scope.of(context)
      ? _Phase2IconAction(
          key: const ValueKey('line-refresh'),
          action: ToolbarAction.refresh,
          onPressed: onPressed,
        )
      : child;
}

/// Phase 2: a screen with its own tabs (Rules | Priority Manager) draws them
/// small, on the title line, rather than as a band of large icon tabs above
/// the page -- the same one line every other screen has (4.5).
class Phase2TabsLine extends StatelessWidget {
  const Phase2TabsLine({
    super.key,
    required this.controller,
    required this.labels,
  });

  final TabController controller;
  final List<String> labels;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    // Inside a page frame the tabs join the frame's own line, which already
    // carries the title; otherwise this is the line.
    final Phase2PageBar? bar = Phase2PageBar.of(context);
    if (bar != null) {
      bar.publishTools([_tabs(theme, scheme, height: 32)]);
      return const SizedBox.shrink();
    }
    final String? title = Phase2ScreenTitle.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLowest,
        border: Border(bottom: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 0),
        child: Row(children: [
          if (title != null) ...[
            Text(
              title,
              style: theme.textTheme.titleMedium
                  ?.copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(width: 16),
          ],
          Flexible(child: _tabs(theme, scheme, height: 44)),
        ]),
      ),
    );
  }

  Widget _tabs(ThemeData theme, ColorScheme scheme, {required double height}) =>
      TabBar(
        controller: controller,
        isScrollable: true,
        tabAlignment: TabAlignment.start,
        dividerHeight: 0,
        labelPadding: const EdgeInsets.symmetric(horizontal: 12),
        labelStyle: theme.textTheme.bodyMedium
            ?.copyWith(fontSize: 13, fontWeight: FontWeight.w600),
        unselectedLabelStyle:
            theme.textTheme.bodyMedium?.copyWith(fontSize: 13),
        labelColor: scheme.primary,
        unselectedLabelColor: scheme.onSurfaceVariant,
        indicatorColor: scheme.primary,
        tabs: [
          for (final String label in labels) Tab(height: height, text: label),
        ],
      );
}

/// A screen's own table (trial balance, profit and loss, ledger, ...).
///
/// Phase 1 draws exactly what those screens always drew: [table] in a
/// sideways scroll. Phase 2 draws it as the lists' grid is drawn -- the full
/// width of the screen, 13 px cells on 34 px rows under a light 12 px
/// heading -- and writes the figures in its numeric columns in Indian
/// digits (1,58,117.39).
class Phase2WideTable extends StatelessWidget {
  const Phase2WideTable({super.key, required this.table});

  final DataTable table;

  @override
  Widget build(BuildContext context) {
    if (!Phase2Scope.of(context)) {
      return SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: table,
      );
    }
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final List<bool> numeric = [
      for (final DataColumn column in table.columns) column.numeric,
    ];
    DataCell figure(DataCell cell, int index) {
      final Widget child = cell.child;
      if (index >= numeric.length || !numeric[index] || child is! Text) {
        return cell;
      }
      final String? data = child.data;
      final double? number =
          data == null ? null : double.tryParse(data.replaceAll(',', ''));
      if (data == null || number == null) return cell;
      final String grouped = indianAmount(number, full: true);
      return DataCell(
        Text(
          data.contains('.')
              ? grouped
              : grouped.substring(0, grouped.length - 3),
          style: child.style,
        ),
        onTap: cell.onTap,
      );
    }

    final DataTable styled = DataTable(
      columns: table.columns,
      sortColumnIndex: table.sortColumnIndex,
      sortAscending: table.sortAscending,
      showCheckboxColumn: table.showCheckboxColumn,
      onSelectAll: table.onSelectAll,
      horizontalMargin: 10,
      columnSpacing: 20,
      dividerThickness: 1,
      dataRowMinHeight: 34,
      dataRowMaxHeight: 34,
      headingRowHeight: 34,
      headingRowColor: WidgetStatePropertyAll(scheme.surfaceContainerLow),
      headingTextStyle: theme.textTheme.labelMedium?.copyWith(
        fontSize: 12,
        fontWeight: FontWeight.w600,
        color: scheme.onSurfaceVariant,
      ),
      dataTextStyle: theme.textTheme.bodyMedium?.copyWith(fontSize: 13),
      rows: [
        for (final DataRow row in table.rows)
          DataRow(
            key: row.key,
            selected: row.selected,
            onSelectChanged: row.onSelectChanged,
            color: row.color,
            cells: [
              for (int i = 0; i < row.cells.length; i++)
                figure(row.cells[i], i),
            ],
          ),
      ],
    );
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: ConstrainedBox(
          constraints: BoxConstraints(
            minWidth: constraints.maxWidth.isFinite ? constraints.maxWidth : 0,
          ),
          child:
              ColoredBox(color: scheme.surfaceContainerLowest, child: styled),
        ),
      ),
    );
  }
}
