import 'package:flutter/material.dart';

enum AppNotificationKind { success, warning, error, information }

abstract final class NotificationService {
  static void show(
    BuildContext context,
    String message, {
    AppNotificationKind kind = AppNotificationKind.information,
  }) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    final (IconData, Color) presentation = switch (kind) {
      AppNotificationKind.success => (Icons.check_circle_outline, Colors.green),
      AppNotificationKind.warning => (
          Icons.warning_amber_outlined,
          Colors.orange
        ),
      AppNotificationKind.error => (Icons.error_outline, colors.error),
      AppNotificationKind.information => (Icons.info_outline, colors.primary),
    };
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Row(children: [
          Icon(presentation.$1, color: colors.onInverseSurface),
          const SizedBox(width: 12),
          Expanded(child: Text(message)),
        ]),
        backgroundColor: presentation.$2,
      ),
    );
  }
}
