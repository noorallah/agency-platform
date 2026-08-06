import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class WorkspaceShortcutBindings {
  const WorkspaceShortcutBindings({
    this.create,
    this.save,
    this.focusSearch,
    this.refresh,
    this.copy,
    this.cancel,
    this.delete,
    this.globalSearch,
    this.advancedSearch,
    this.edit,
    this.export,
    this.copyRow,
  });

  final VoidCallback? create;
  final VoidCallback? save;
  final VoidCallback? focusSearch;
  final VoidCallback? refresh;
  final VoidCallback? copy;
  final VoidCallback? cancel;
  final VoidCallback? delete;
  final VoidCallback? globalSearch;
  final VoidCallback? advancedSearch;
  final VoidCallback? edit;
  final VoidCallback? export;
  final VoidCallback? copyRow;

  Map<ShortcutActivator, VoidCallback> toCallbacks() => {
        if (create != null)
          const SingleActivator(LogicalKeyboardKey.keyN, control: true):
              create!,
        if (save != null)
          const SingleActivator(LogicalKeyboardKey.keyS, control: true): save!,
        if (focusSearch != null)
          const SingleActivator(LogicalKeyboardKey.keyF, control: true):
              focusSearch!,
        if (advancedSearch != null)
          const SingleActivator(
            LogicalKeyboardKey.keyF,
            control: true,
            shift: true,
          ): advancedSearch!,
        if (refresh != null) ...{
          const SingleActivator(LogicalKeyboardKey.keyR, control: true):
              refresh!,
          const SingleActivator(LogicalKeyboardKey.f5): refresh!,
        },
        if (edit != null) ...{
          const SingleActivator(LogicalKeyboardKey.f2): edit!,
          const SingleActivator(LogicalKeyboardKey.enter): edit!,
        },
        if (export != null)
          const SingleActivator(LogicalKeyboardKey.keyE, control: true):
              export!,
        if (copy != null)
          const SingleActivator(LogicalKeyboardKey.keyC, control: true): copy!,
        if (copyRow != null)
          const SingleActivator(
            LogicalKeyboardKey.keyC,
            control: true,
            shift: true,
          ): copyRow!,
        if (cancel != null)
          const SingleActivator(LogicalKeyboardKey.escape): cancel!,
        if (delete != null)
          const SingleActivator(LogicalKeyboardKey.delete): delete!,
        if (globalSearch != null)
          const SingleActivator(LogicalKeyboardKey.keyK, control: true):
              globalSearch!,
      };
}

class WorkspaceShortcuts extends StatelessWidget {
  const WorkspaceShortcuts({
    super.key,
    required this.bindings,
    required this.child,
    this.autofocus = true,
  });

  final WorkspaceShortcutBindings bindings;
  final Widget child;
  final bool autofocus;

  @override
  Widget build(BuildContext context) => CallbackShortcuts(
        bindings: bindings.toCallbacks(),
        child: Focus(autofocus: autofocus, child: child),
      );
}

enum WorkspaceContextAction {
  view,
  edit,
  delete,
  restore,
  copy,
  refresh,
  export,
}

extension WorkspaceContextActionDetails on WorkspaceContextAction {
  String get label => switch (this) {
        WorkspaceContextAction.view => 'View',
        WorkspaceContextAction.edit => 'Edit',
        WorkspaceContextAction.delete => 'Delete',
        WorkspaceContextAction.restore => 'Restore',
        WorkspaceContextAction.copy => 'Copy row',
        WorkspaceContextAction.refresh => 'Refresh',
        WorkspaceContextAction.export => 'Export',
      };

  IconData get icon => switch (this) {
        WorkspaceContextAction.view => Icons.visibility_outlined,
        WorkspaceContextAction.edit => Icons.edit_outlined,
        WorkspaceContextAction.delete => Icons.delete_outline,
        WorkspaceContextAction.restore => Icons.restore_from_trash_outlined,
        WorkspaceContextAction.copy => Icons.copy_outlined,
        WorkspaceContextAction.refresh => Icons.refresh,
        WorkspaceContextAction.export => Icons.file_download_outlined,
      };
}

Future<void> showWorkspaceContextMenu(
  BuildContext context, {
  required Offset position,
  required List<WorkspaceContextAction> actions,
  required ValueChanged<WorkspaceContextAction> onSelected,
  bool Function(WorkspaceContextAction action)? isEnabled,
}) async {
  final RenderBox overlay =
      Overlay.of(context).context.findRenderObject()! as RenderBox;
  final WorkspaceContextAction? selected =
      await showMenu<WorkspaceContextAction>(
    context: context,
    position: RelativeRect.fromRect(
      Rect.fromPoints(position, position),
      Offset.zero & overlay.size,
    ),
    items: [
      for (final WorkspaceContextAction action in actions)
        PopupMenuItem(
          value: action,
          enabled: isEnabled?.call(action) ?? true,
          child: Row(children: [
            Icon(action.icon, size: 20),
            const SizedBox(width: 12),
            Text(action.label),
          ]),
        ),
    ],
  );
  if (selected != null) onSelected(selected);
}

Future<void> copyTextToClipboard(String value) =>
    Clipboard.setData(ClipboardData(text: value));
