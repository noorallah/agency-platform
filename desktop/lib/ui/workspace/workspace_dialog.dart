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
    this.saveLabel = 'Save',
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
  /// What Cancel, the header cross and Escape all do.
  ///
  /// Optional, and **closing the dialog is what happens when it is omitted**.
  /// It used to be passed straight through, so a caller that forgot it got a
  /// Cancel button, a cross and an Escape key that were all disabled at once
  /// -- the quotation editor, the product editor and the sales return editor
  /// each shipped that way, and the only way out of a new quotation was to
  /// save it. Pass this only to do something *other* than pop, such as asking
  /// about unsaved work first.
  final VoidCallback? onClose;
  final VoidCallback? onSave;

  /// What the default save button is called. A dialog that records something
  /// rather than editing it reads better as "Record receipt" than "Save".
  final String saveLabel;

  @override
  Widget build(BuildContext context) {
    final Size window = MediaQuery.sizeOf(context);
    // `maybePop` rather than `pop`: a dialog shown some other way than as a
    // route should not throw when somebody presses Escape.
    final VoidCallback dismiss =
        onClose ?? () => Navigator.of(context).maybePop();
    final int safeSelectedTab =
        tabs.isEmpty ? 0 : selectedTab.clamp(0, tabs.length - 1);
    final Widget? effectiveFooter = footer ??
        (onSave == null
            ? null
            : Padding(
                padding: const EdgeInsets.all(AppSpacing.lg),
                child: Row(children: [
                  const Spacer(),
                  TextButton(
                    onPressed: loading ? null : dismiss,
                    child: const Text('Cancel'),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  FilledButton(
                    onPressed: loading ? null : onSave,
                    child: Text(saveLabel),
                  ),
                ]),
              ));
    return Dialog(
      insetPadding: const EdgeInsets.all(AppDimensions.dialogInset),
      clipBehavior: Clip.antiAlias,
      child: SizedBox(
        width: window.width * AppDimensions.dialogScale,
        height: window.height * AppDimensions.dialogScale,
        // A dialog is its own route, so the app-level SelectionArea wrapping
        // `home` does not reach it and none of this text could be copied --
        // labels, helper text, validation messages, read-only values. Safe
        // inside a route: SelectableRegion needs an Overlay ancestor and the
        // Navigator provides one.
        child: SelectionArea(
          child: WorkspaceShortcuts(
            bindings: WorkspaceShortcutBindings(
              save: loading ? null : onSave,
              cancel: loading ? null : dismiss,
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
                      onPressed: loading ? null : dismiss,
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
              // A dialog that can be saved gets a visible way to save it. The
              // callback was wired only to a keyboard shortcut, so a dialog
              // passing `onSave` and no footer offered no button at all --
              // which shipped in two of them before anybody noticed.
              if (effectiveFooter != null)
                Material(
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  child: effectiveFooter,
                ),
            ]),
          ),
        ),
      ),
    );
  }
}
