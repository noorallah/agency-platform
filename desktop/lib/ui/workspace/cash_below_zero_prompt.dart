// Save, and ask first when cash would go below zero.
//
// Paying out of Cash or Petty Cash more than it holds is not refused by the
// server: it answers a question (`ApiException.isCashBelowZero`) and saves
// nothing, and saves when the same request arrives confirmed. Written once
// because an expense, a payment to a supplier and a refund all ask it, and a
// screen that showed the question as a refusal would leave the person with a
// save they are allowed to make and no way to make it.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';

/// Run [save], asking *Save anyway?* when the server asks it.
///
/// [save] is called with `false` first; where the server answers that a cash
/// account would stand below zero, its own sentence is shown and, on yes,
/// [save] runs again with `true` -- the caller sends
/// `cash_below_zero_confirmed` then and only then. Returns what was saved, or
/// null when the person went back. Any other refusal is rethrown.
Future<T?> saveAskingAboutCash<T>(
  BuildContext context,
  Future<T> Function(bool confirmed) save,
) async {
  try {
    return await save(false);
  } on ApiException catch (error) {
    if (!error.isCashBelowZero || !context.mounted) rethrow;
    final bool? anyway = await showDialog<bool>(
      context: context,
      // Selectable, as every dialog's text (backlog 83).
      builder: (BuildContext dialogContext) => SelectionArea(
        child: AlertDialog(
          title: const Text('Cash would go below zero'),
          content: SizedBox(width: 420, child: Text(error.message)),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('Go back'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('Save anyway'),
            ),
          ],
        ),
      ),
    );
    if (anyway != true) return null;
    return save(true);
  }
}
