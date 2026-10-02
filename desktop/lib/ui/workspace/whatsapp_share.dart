import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';

import '../../core/logging/app_log.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/messaging.dart' show HandShare;

/// Shares a document from the person's own WhatsApp, by hand (MSG-1, §51 A2).
///
/// No account and no API: WhatsApp opens at the party's number with the
/// message typed in, the PDF is saved and its folder opened, and the person
/// attaches it and presses send -- what Vyapar and most small-business
/// products do. Each step that touches the machine is a field, so a test can
/// stand in for the file system and the browser.
class WhatsAppSharer {
  const WhatsAppSharer({
    this.savePdf = _saveToDownloads,
    this.reveal = _reveal,
    this.openLink = _openLink,
  });

  /// Writes the PDF and returns where it went.
  final Future<String> Function(String fileName, List<int> bytes) savePdf;

  /// Shows the saved file in the file manager, so it is one drag to attach.
  final Future<void> Function(String path) reveal;

  /// Opens a link in whatever the machine opens links with.
  final Future<void> Function(String url) openLink;

  /// The `wa.me` link: WhatsApp's desktop app where it is installed, its web
  /// page where not. No number lets WhatsApp ask whom to send to.
  static String link({String? number, required String text}) =>
      'https://wa.me/${number ?? ''}?text=${Uri.encodeComponent(text)}';

  /// Saves [pdf], opens its folder and WhatsApp with [share]'s message, then
  /// [record]s it and says what to do next. Returns false when no PDF came
  /// (the person turned down a reference copy).
  Future<bool> share(
    BuildContext context, {
    required HandShare share,
    required List<int>? pdf,
    required Future<void> Function() record,
  }) async {
    if (pdf == null) return false;
    final String path = await savePdf(share.fileName, pdf);
    await reveal(path);
    await openLink(link(number: share.whatsappNumber, text: share.text));
    await record();
    if (context.mounted) {
      NotificationService.show(
        context,
        share.whatsappNumber == null
            ? 'WhatsApp is opening with the message typed. The customer has '
                'no number: choose the chat, attach ${share.fileName} from the '
                'folder that opened, then send.'
            : 'WhatsApp is opening at ${share.phone} with the message typed. '
                'Attach ${share.fileName} from the folder that opened, then '
                'send.',
        kind: AppNotificationKind.success,
      );
    }
    return true;
  }
}

/// The Downloads folder, where a person looks for a file they were just given;
/// the app's own folder where a machine has none.
Future<String> _saveToDownloads(String fileName, List<int> bytes) async {
  Directory? folder;
  try {
    folder = await getDownloadsDirectory();
  } on Object catch (error) {
    AppLog.warn('No Downloads folder: $error');
  }
  folder ??= await getApplicationDocumentsDirectory();
  final File file = File('${folder.path}${Platform.pathSeparator}$fileName');
  await file.writeAsBytes(bytes, flush: true);
  return file.path;
}

Future<void> _reveal(String path) async {
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

Future<void> _openLink(String url) async {
  if (Platform.isWindows) {
    // `start` would read the `&` in the link as a second command;
    // the URL handler takes it whole.
    await Process.run('rundll32', ['url.dll,FileProtocolHandler', url]);
  } else if (Platform.isMacOS) {
    await Process.run('open', [url]);
  } else {
    await Process.run('xdg-open', [url]);
  }
}
