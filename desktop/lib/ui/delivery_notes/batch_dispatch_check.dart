import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/batch_sale_settings.dart';
import '../workspace/reason_prompt.dart';

/// What the firm's batch rules decided about a dispatch: whether it may go
/// ahead and, when a rule asked why, the reason to send as `batch_reason`.
class BatchDispatchOutcome {
  const BatchDispatchOutcome({required this.proceed, this.reason});

  final bool proceed;
  final String? reason;

  static const BatchDispatchOutcome proceedResult =
      BatchDispatchOutcome(proceed: true);
  static const BatchDispatchOutcome cancelResult =
      BatchDispatchOutcome(proceed: false);
}

/// Ask the server what the firm's batch rules say about dispatching a
/// delivery note, and put it in front of the user before the dispatch call
/// (backlog 79 row 6).
///
/// No findings: proceeds untouched. Findings under a rule that needs a reason:
/// asks for one and cancels on a dismissal. Findings that only warn: shows the
/// message for a Continue or Cancel. A check that cannot be read proceeds, and
/// the server, which enforces the rules, answers on the dispatch itself.
Future<BatchDispatchOutcome> confirmBatchDispatch(
  BuildContext context,
  ApiClient api,
  String noteId,
) async {
  final DispatchBatchCheck check;
  try {
    check = await api.deliveryNoteBatchCheck(noteId);
  } on ApiException {
    return BatchDispatchOutcome.proceedResult;
  }
  if (check.findings.isEmpty || !context.mounted) {
    return BatchDispatchOutcome.proceedResult;
  }
  final String text = check.message ??
      check.findings.map((finding) => finding.message).join('\n');
  if (check.wouldBlock) {
    // Refused whatever reason is given, so there is nothing to confirm.
    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => AlertDialog(
        icon: const Icon(Icons.block_outlined),
        title: const Text('Batch rules'),
        content: SizedBox(width: 420, child: Text(text)),
        actions: [
          FilledButton(
            key: const ValueKey('batch-check-ok'),
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('OK'),
          ),
        ],
      ),
    );
    return BatchDispatchOutcome.cancelResult;
  }
  if (check.needsReason) {
    final String? reason = await askForReason(
      context,
      title: 'Batch rules',
      explanation: '$text\n\nWhy this goes ahead. Recorded on the '
          "document's timeline.",
      confirmLabel: 'Dispatch',
    );
    return reason == null
        ? BatchDispatchOutcome.cancelResult
        : BatchDispatchOutcome(proceed: true, reason: reason);
  }
  final bool? go = await showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (dialogContext) => AlertDialog(
      icon: const Icon(Icons.warning_amber_outlined),
      title: const Text('Batch rules'),
      content: SizedBox(width: 420, child: Text(text)),
      actions: [
        TextButton(
          key: const ValueKey('batch-check-cancel'),
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('batch-check-continue'),
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: const Text('Continue'),
        ),
      ],
    ),
  );
  return go == true
      ? BatchDispatchOutcome.proceedResult
      : BatchDispatchOutcome.cancelResult;
}
