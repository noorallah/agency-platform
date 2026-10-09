import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:printing/printing.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';

/// The most documents one print run takes: the server's own limit
/// (`MAX_PRINT_RUN`), stated here so a screen can say so by the number
/// before asking.
const int maxPrintRun = 100;

/// Send a rendered document to the printer, through the system print dialog.
///
/// Print means print. This used to save a PDF and hand it to whatever opens
/// one, which made a Print button behave like Save As -- the user then had to
/// find the file, open it, and print it from there.
///
/// `layoutPdf` shows the operating system's own dialog: the preview, the
/// printer list, page range, and the Print button people already know. Nothing
/// is written to disk unless the user chooses a PDF printer themselves.
///
/// The bytes come from the backend, already laid out. **How many labelled
/// copies to print is baked into them** -- Original, Duplicate and Triplicate
/// are separate page sets in the document, set in Print settings, and quite
/// separate from the dialog's own copy count, which repeats the whole thing.
Future<void> printDocument(
  BuildContext context, {
  required List<int> bytes,
  required String documentName,
}) async {
  final bool printed = await Printing.layoutPdf(
    onLayout: (_) async => Uint8List.fromList(bytes),
    name: documentName,
  );
  if (!context.mounted) return;
  // A user who closes the dialog has not printed anything, and telling them
  // it was sent would be a lie they only discover at the printer.
  NotificationService.show(
    context,
    printed ? '$documentName sent to the printer.' : 'Printing cancelled.',
    kind: printed ? AppNotificationKind.success : AppNotificationKind.information,
  );
}

/// Fetch a document's PDF, offering a reference copy when the server refuses
/// because the bill has no IRN yet (GST backlog 77.6).
///
/// Returns the bytes, or null when the person cancelled the offer. Any other
/// refusal is rethrown for the caller to show as it always did.
Future<List<int>?> fetchPrintablePdf(
  BuildContext context,
  Future<List<int>> Function({bool referenceCopy}) fetch,
) async {
  try {
    return await fetch(referenceCopy: false);
  } on ApiException catch (error) {
    if (!error.isIrnRequired || !context.mounted) rethrow;
    final bool? reference = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: const Text('No IRN yet'),
        content: Text(error.message),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Print reference copy'),
          ),
        ],
      ),
    );
    if (reference != true) return null;
    return fetch(referenceCopy: true);
  }
}
