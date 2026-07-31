import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import 'workspace_interactions.dart';

class WorkspaceDialogTab {
  const WorkspaceDialogTab({required this.label, required this.child});

  final String label;
  final Widget child;
}

class WorkspaceDialog extends StatelessWidget {
  const WorkspaceDialog({
    super.key,
    required this.title,
    required this.body,
    this.subtitle,
    this.icon,
    this.tabs = const [],
    this.selectedTab = 0,
    this.onTabChanged,
    this.footer,
    this.loading = false,
    this.onClose,
    this.onSave,
  });

  final String title;
  final String? subtitle;
  final IconData? icon;
  final Widget body;
  final List<WorkspaceDialogTab> tabs;
  final int selectedTab;
  final ValueChanged<int>? onTabChanged;
  final Widget? footer;
  final bool loading;
  final VoidCallback? onClose;
  final VoidCallback? onSave;

  @override
  Widget build(BuildContext context) {
    final Size window = MediaQuery.sizeOf(context);
    final int safeSelectedTab =
        tabs.isEmpty ? 0 : selectedTab.clamp(0, tabs.length - 1);
    return Dialog(
      insetPadding: const EdgeInsets.all(AppDimensions.dialogInset),
      clipBehavior: Clip.antiAlias,
      child: SizedBox(
        width: window.width * AppDimensions.dialogScale,
        height: window.height * AppDimensions.dialogScale,
        child: WorkspaceShortcuts(
          bindings: WorkspaceShortcutBindings(
            save: loading ? null : onSave,
            cancel: loading ? null : onClose,
          ),
          child: Column(children: [
            Material(
              color: Theme.of(context).colorScheme.surfaceContainerHighest,
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.xl,
                  vertical: AppSpacing.lg,
                ),
                child: Row(children: [
                  if (icon != null) ...[
                    Icon(icon),
                    const SizedBox(width: AppSpacing.md),
                  ],
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(title,
                            style: Theme.of(context).textTheme.headlineSmall),
                        if (subtitle != null) Text(subtitle!),
                      ],
                    ),
                  ),
                  IconButton(
                    tooltip: 'Close',
                    onPressed: loading ? null : onClose,
                    icon: const Icon(Icons.close),
                  ),
                ]),
              ),
            ),
            if (tabs.isNotEmpty)
              Align(
                alignment: Alignment.centerLeft,
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(
                    AppSpacing.xl,
                    AppSpacing.md,
                    AppSpacing.xl,
                    0,
                  ),
                  scrollDirection: Axis.horizontal,
                  child: SegmentedButton<int>(
                    segments: [
                      for (int index = 0; index < tabs.length; index++)
                        ButtonSegment(
                            value: index, label: Text(tabs[index].label)),
                    ],
                    selected: {safeSelectedTab},
                    showSelectedIcon: false,
                    onSelectionChanged: onTabChanged == null
                        ? null
                        : (selection) => onTabChanged!(selection.first),
                  ),
                ),
              ),
            Expanded(
              child: Stack(children: [
                Positioned.fill(
                  child: AbsorbPointer(
                    absorbing: loading,
                    child: tabs.isEmpty
                        ? body
                        : IndexedStack(
                            index: safeSelectedTab,
                            children: [
                              for (final WorkspaceDialogTab tab in tabs)
                                tab.child,
                            ],
                          ),
                  ),
                ),
                if (loading)
                  Positioned.fill(
                    child: ColoredBox(
                      color: Theme.of(context)
                          .colorScheme
                          .scrim
                          .withValues(alpha: .2),
                      child: const Center(child: CircularProgressIndicator()),
                    ),
                  ),
              ]),
            ),
            if (footer != null)
              Material(
                color: Theme.of(context).colorScheme.surfaceContainerHighest,
                child: footer!,
              ),
          ]),
        ),
      ),
    );
  }
}
