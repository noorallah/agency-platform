import 'package:flutter/material.dart';

import '../design/design_tokens.dart';

enum AppNotificationKind { success, warning, error, information }

abstract interface class NotificationPresenter {
  void present(
    BuildContext context,
    String message, {
    AppNotificationKind kind = AppNotificationKind.information,
  });
}

class NotificationService implements NotificationPresenter {
  const NotificationService();

  static const NotificationService instance = NotificationService();

  static void show(
    BuildContext context,
    String message, {
    AppNotificationKind kind = AppNotificationKind.information,
  }) =>
      instance.present(context, message, kind: kind);

  @override
  void present(
    BuildContext context,
    String message, {
    AppNotificationKind kind = AppNotificationKind.information,
  }) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    final AppSemanticColors semantic = context.semanticColors;
    final (IconData, Color, Color) presentation = switch (kind) {
      AppNotificationKind.success => (
          Icons.check_circle_outline,
          semantic.success,
          semantic.onSuccess,
        ),
      AppNotificationKind.warning => (
          Icons.warning_amber_outlined,
          semantic.warning,
          semantic.onWarning,
        ),
      AppNotificationKind.error => (
          Icons.error_outline,
          colors.error,
          colors.onError,
        ),
      AppNotificationKind.information => (
          Icons.info_outline,
          semantic.information,
          semantic.onInformation,
        ),
    };
    final ScaffoldMessengerState messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Row(children: [
          Icon(presentation.$1, color: presentation.$3),
          const SizedBox(width: 12),
          Expanded(
            child: SelectableText(
              message,
              style: TextStyle(color: presentation.$3),
            ),
          ),
        ]),
        backgroundColor: presentation.$2,
        behavior: SnackBarBehavior.floating,
      ),
    );
  }
}
