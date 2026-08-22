import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/widgets.dart';

import '../../core/notifications/notification_service.dart';

/// Save a document the server rendered, and open it.
///
/// Shared by every screen that prints, because the alternative is one copy per
/// module of the same three lines -- and the platform already learned that
/// lesson with bulk operations, where a second implementation skipped the
/// audit rows and the delete guards its twin enforced.
///
/// The file is the point: what a customer or supplier receives is a PDF, and
/// the machine already has something that reads one. Nothing here renders.
Future<void> savePrintedDocument(
  BuildContext context, {
  required List<int> bytes,
  required String suggestedName,
}) async {
  final FileSaveLocation? location = await getSaveLocation(
    suggestedName: suggestedName,
  );
  if (location == null) return;
  await File(location.path).writeAsBytes(bytes, flush: true);
  await _open(location.path);
  if (!context.mounted) return;
  NotificationService.show(
    context,
    '$suggestedName saved.',
    kind: AppNotificationKind.success,
  );
}

/// Hand the file to whatever this operating system opens PDFs with.
Future<void> _open(String path) async {
  if (Platform.isWindows) {
    // The empty argument is the window title `start` expects first; without
    // it a path containing spaces is read as the title and nothing opens.
    await Process.run('cmd', ['/c', 'start', '', path]);
  } else if (Platform.isMacOS) {
    await Process.run('open', [path]);
  } else {
    await Process.run('xdg-open', [path]);
  }
}
