// Balance confirmation letters: what the firm's books say a party owes (or is
// owed) on a day, sent to the party to confirm.
//
// One letter opens as a PDF to print; the letters for everyone with a balance
// arrive as a zip, one PDF per party, and are saved to a file the user picks.
// Shared by the customer and the supplier statement screens.

import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import 'master_import_dialog.dart' show SaveBytesOverride;
import 'printed_document.dart';

/// How a letter's PDF is shown. Tests inject one, because a widget test
/// cannot open a print dialog.
typedef OpenPdfOverride = Future<void> Function(
  String documentName,
  List<int> bytes,
);

/// Fetch, show and save balance confirmation letters, telling the user what
/// the server said when it refuses (for instance when nobody has a balance).
class BalanceConfirmationActions {
  const BalanceConfirmationActions({this.openPdfOverride, this.saveBytesOverride});

  final OpenPdfOverride? openPdfOverride;
  final SaveBytesOverride? saveBytesOverride;

  /// The one letter, shown for printing.
  Future<void> letter(
    BuildContext context, {
    required Future<List<int>> Function() fetch,
    required String documentName,
  }) async {
    try {
      final List<int> pdf = await fetch();
      if (!context.mounted) return;
      if (openPdfOverride != null) {
        await openPdfOverride!(documentName, pdf);
        return;
      }
      await printDocument(context, bytes: pdf, documentName: documentName);
    } on ApiException catch (error) {
      if (!context.mounted) return;
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  /// Every letter, zipped, saved where the user chooses.
  Future<void> everyone(
    BuildContext context, {
    required Future<List<int>> Function() fetch,
    required String suggestedName,
  }) async {
    try {
      final List<int> zip = await fetch();
      if (!context.mounted) return;
      if (saveBytesOverride != null) {
        await saveBytesOverride!(suggestedName, zip);
      } else {
        final FileSaveLocation? location = await getSaveLocation(
          suggestedName: suggestedName,
          acceptedTypeGroups: const [
            XTypeGroup(label: 'Zip archive', extensions: ['zip']),
          ],
        );
        if (location == null) return;
        await File(location.path).writeAsBytes(zip, flush: true);
      }
      if (!context.mounted) return;
      NotificationService.show(
        context,
        'The letters were saved.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (error) {
      if (!context.mounted) return;
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
    }
  }
}
