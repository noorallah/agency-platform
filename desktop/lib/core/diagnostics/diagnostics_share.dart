import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../notifications/notification_service.dart';
import 'crash_reporter.dart';
import '../logging/app_log.dart';

/// Getting the report off the customer's machine and into a support ticket.
///
/// The report is only worth writing if it is easy to hand over. A file the user
/// has to be talked through finding in `%APPDATA%` over the phone is not — so
/// this offers a save dialog, a reveal-in-folder, and a clipboard copy for
/// pasting straight into a ticket.
abstract final class DiagnosticsShare {
  static String suggestedFileName() {
    final String stamp = DateTime.now()
        .toUtc()
        .toIso8601String()
        .replaceAll(RegExp('[:.]'), '-')
        .split('.')
        .first;
    return 'agency-platform-diagnostics-$stamp.txt';
  }

  /// Opens the platform's save dialog, defaulting to a dated file name.
  ///
  /// Returns the written path, or null if the user cancelled.
  static Future<String?> save(String report) async {
    final FileSaveLocation? location = await getSaveLocation(
      suggestedName: suggestedFileName(),
      acceptedTypeGroups: const [
        XTypeGroup(label: 'Text', extensions: ['txt']),
      ],
    );
    if (location == null) return null;
    await File(location.path).writeAsString(report, flush: true);
    return location.path;
  }

  /// Shows the file in the desktop's file manager, selected.
  static Future<void> reveal(String path) async {
    try {
      if (Platform.isWindows) {
        // The comma is part of the switch: `/select,<path>`.
        await Process.run('explorer', ['/select,$path']);
      } else if (Platform.isMacOS) {
        await Process.run('open', ['-R', path]);
      } else {
        await Process.run('xdg-open', [File(path).parent.path]);
      }
    } on Object catch (error) {
      AppLog.warn('Could not reveal $path: $error');
    }
  }

  static Future<void> copy(String report) =>
      Clipboard.setData(ClipboardData(text: report));
}

/// Shows the report, and the three ways to hand it over.
class DiagnosticsReportDialog extends StatelessWidget {
  const DiagnosticsReportDialog({super.key, required this.report});

  final String report;

  /// Builds the report for the current session and shows it.
  static Future<void> show(
    BuildContext context, {
    required String appName,
    required String version,
    required String buildNumber,
    String? firmCode,
    String? userId,
    String? serverUrl,
  }) {
    final String report = CrashReporter.buildReport(
      appName: appName,
      version: version,
      buildNumber: buildNumber,
      firmCode: firmCode,
      userId: userId,
      serverUrl: serverUrl,
    );
    return showDialog<void>(
      context: context,
      builder: (_) => DiagnosticsReportDialog(report: report),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: const Text('Diagnostics report'),
      content: SizedBox(
        width: 720,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (CrashReporter.previousSessionEndedUnexpectedly)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(
                  'The previous session ended unexpectedly. This report '
                  'includes what was happening at the time.',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: theme.colorScheme.error,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            Text(
              'Send this to your support contact. It contains no passwords or '
              'access tokens.',
              style: theme.textTheme.bodyMedium,
            ),
            const SizedBox(height: 12),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 320),
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: SingleChildScrollView(
                  child: SelectableText(
                    report,
                    style: const TextStyle(fontSize: 11, fontFamily: 'monospace'),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
        TextButton.icon(
          onPressed: () async {
            await DiagnosticsShare.copy(report);
            if (!context.mounted) return;
            NotificationService.show(
              context,
              'Diagnostics report copied to the clipboard.',
              kind: AppNotificationKind.success,
            );
          },
          icon: const Icon(Icons.copy_outlined),
          label: const Text('Copy'),
        ),
        FilledButton.icon(
          onPressed: () async {
            final String? path = await DiagnosticsShare.save(report);
            if (path == null || !context.mounted) return;
            NotificationService.show(
              context,
              'Saved to $path',
              kind: AppNotificationKind.success,
            );
            await DiagnosticsShare.reveal(path);
          },
          icon: const Icon(Icons.save_alt),
          label: const Text('Save report'),
        ),
      ],
    );
  }
}
