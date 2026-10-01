import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';

/// One mechanism for a dialog that saves before it closes (D-DLG-1).
///
/// A dialog that pops its typed values and leaves the create/update call to its
/// caller shows a server refusal as a toast after the dialog is gone, with
/// everything typed lost. Mix this into the dialog's `State`, pass the save in
/// as `Future<R> Function(...) onSave`, and call [saveAndClose]: the dialog
/// stays open, [saving] is true while the request runs (disable the buttons on
/// it), a refusal lands in [saveError] (render [saveErrorBanner]) with every
/// field kept, and the dialog pops with the saved record only on success.
mixin SaveInDialog<T extends StatefulWidget> on State<T> {
  bool saving = false;
  String? saveError;

  /// Runs [call]; closes with its result on success, keeps the dialog open
  /// with the refusal on an [ApiException].
  Future<void> saveAndClose<R>(Future<R> Function() call) async {
    if (saving) return;
    setState(() {
      saving = true;
      saveError = null;
    });
    try {
      final R result = await call();
      if (!mounted) return;
      Navigator.pop(context, result ?? true);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        saving = false;
        saveError = exception.message;
      });
    }
  }

  /// Closes with [value] after [onSave] accepts it. A null [onSave] closes at
  /// once, for a caller that has no call to make (a read-only use, a test).
  Future<void> submit<R>(
    R value,
    Future<void> Function(R value)? onSave,
  ) async {
    if (onSave == null) {
      Navigator.pop(context, value);
      return;
    }
    await saveAndClose<R>(() async {
      await onSave(value);
      return value;
    });
  }

  /// The refusal, inside the dialog, above the form. Empty when there is none.
  Widget saveErrorBanner() {
    final String? message = saveError;
    if (message == null) return const SizedBox.shrink();
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Container(
      key: const ValueKey<String>('save-error-banner'),
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colors.errorContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.error_outline, color: colors.onErrorContainer, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: TextStyle(color: colors.onErrorContainer),
            ),
          ),
        ],
      ),
    );
  }

  /// A Cancel handler that does nothing while a save is in flight.
  VoidCallback? get cancelHandler =>
      saving ? null : () => Navigator.pop(context);
}
