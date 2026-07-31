import 'package:flutter/material.dart';

enum ConfirmationType {
  delete,
  logout,
  discardChanges,
  resetPassword,
  lockUser,
  unlockUser,
  custom,
}

extension ConfirmationTypeDetails on ConfirmationType {
  String get confirmLabel => switch (this) {
        ConfirmationType.delete => 'Delete',
        ConfirmationType.logout => 'Sign out',
        ConfirmationType.discardChanges => 'Discard changes',
        ConfirmationType.resetPassword => 'Reset password',
        ConfirmationType.lockUser => 'Lock user',
        ConfirmationType.unlockUser => 'Unlock user',
        ConfirmationType.custom => 'Confirm',
      };

  IconData get icon => switch (this) {
        ConfirmationType.delete => Icons.delete_outline,
        ConfirmationType.logout => Icons.logout,
        ConfirmationType.discardChanges => Icons.undo,
        ConfirmationType.resetPassword => Icons.password_outlined,
        ConfirmationType.lockUser => Icons.lock_outline,
        ConfirmationType.unlockUser => Icons.lock_open_outlined,
        ConfirmationType.custom => Icons.help_outline,
      };

  bool get destructive => switch (this) {
        ConfirmationType.delete ||
        ConfirmationType.logout ||
        ConfirmationType.discardChanges ||
        ConfirmationType.resetPassword ||
        ConfirmationType.lockUser =>
          true,
        ConfirmationType.unlockUser || ConfirmationType.custom => false,
      };
}

abstract final class AppDialogs {
  static Future<bool> confirm(
    BuildContext context, {
    required String title,
    required String message,
    String confirmLabel = 'Confirm',
    ConfirmationType type = ConfirmationType.custom,
  }) async =>
      await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          icon: Icon(type.icon),
          title: Text(title),
          content: SelectableText(message),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              style: type.destructive
                  ? FilledButton.styleFrom(
                      backgroundColor:
                          Theme.of(dialogContext).colorScheme.error,
                      foregroundColor:
                          Theme.of(dialogContext).colorScheme.onError,
                    )
                  : null,
              onPressed: () => Navigator.pop(dialogContext, true),
              child: Text(
                confirmLabel == 'Confirm' ? type.confirmLabel : confirmLabel,
              ),
            ),
          ],
        ),
      ) ??
      false;

  static Future<void> error(
    BuildContext context, {
    required String title,
    required String message,
  }) =>
      showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          icon: const Icon(Icons.error_outline),
          title: Text(title),
          content: SelectableText(message),
          actions: [
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Close'),
            ),
          ],
        ),
      );

  static Future<T> whileLoading<T>(
    BuildContext context,
    Future<T> operation, {
    String message = 'Please wait...',
  }) async {
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => AlertDialog(
        content: Row(children: [
          const CircularProgressIndicator(),
          const SizedBox(width: 20),
          Expanded(child: Text(message)),
        ]),
      ),
    );
    try {
      return await operation;
    } finally {
      if (context.mounted) Navigator.of(context, rootNavigator: true).pop();
    }
  }
}
