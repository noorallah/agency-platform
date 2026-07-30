import 'package:flutter/material.dart';

abstract final class AppDialogs {
  static Future<bool> confirm(
    BuildContext context, {
    required String title,
    required String message,
    String confirmLabel = 'Confirm',
  }) async =>
      await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text(title),
          content: Text(message),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton.tonal(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: Text(confirmLabel),
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
