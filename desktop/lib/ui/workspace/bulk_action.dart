// Approve or cancel several documents at once, and say what happened to each.
//
// Rows are acted on one by one on the server, so a batch can end half done:
// the result dialog names every refused row and why, and offers to send just
// those again. Written once for the sales and purchase order lists.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/bulk_action.dart';

/// Send [rows] through [send], show the result, and on "Retry the refused"
/// send only the refused ids again -- with no version, because the person has
/// now seen the current state in the result.
///
/// [verb] is the past tense the result heading uses ("Approved",
/// "Cancelled"). The caller reloads its list afterwards.
Future<void> runBulkAction(
  BuildContext context, {
  required String verb,
  required List<BulkRow> rows,
  required Future<BulkActionResult> Function(List<BulkRow> rows) send,
}) async {
  List<BulkRow> pending = rows;
  while (true) {
    final BulkActionResult result;
    try {
      result = await send(pending);
    } on ApiException catch (error) {
      if (!context.mounted) return;
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
      return;
    }
    if (!context.mounted) return;
    final bool retry = await showDialog<bool>(
          context: context,
          builder: (_) => BulkResultDialog(
            verb: verb,
            attempted: pending.length,
            result: result,
          ),
        ) ??
        false;
    if (!retry) return;
    pending = [
      for (final BulkRowResult row in result.refusedRows)
        (id: row.id, version: null),
    ];
    if (pending.isEmpty) return;
  }
}

/// "Approved 9 of 12", then the refused rows with their number and message.
class BulkResultDialog extends StatelessWidget {
  const BulkResultDialog({
    super.key,
    required this.verb,
    required this.attempted,
    required this.result,
  });

  final String verb;
  final int attempted;
  final BulkActionResult result;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<BulkRowResult> refused = result.refusedRows;
    return AlertDialog(
      key: const ValueKey('bulk-result-dialog'),
      title: Text('$verb ${result.done} of $attempted'),
      content: SizedBox(
        // A width, because an AlertDialog gives its content unbounded height.
        width: 480,
        child: refused.isEmpty
            ? const Text('Every selected row went through.')
            : Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${refused.length} refused:',
                    style: theme.textTheme.titleSmall,
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  Flexible(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxHeight: 280),
                      child: ListView(
                        shrinkWrap: true,
                        children: [
                          for (final BulkRowResult row in refused)
                            Padding(
                              padding: const EdgeInsets.only(
                                bottom: AppSpacing.sm,
                              ),
                              child: Text.rich(TextSpan(children: [
                                TextSpan(
                                  text: row.number ?? row.id,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                                TextSpan(text: '  ${row.message ?? 'Refused.'}'),
                              ])),
                            ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
      ),
      actions: [
        if (refused.isNotEmpty)
          OutlinedButton(
            key: const ValueKey('bulk-retry'),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Retry the refused'),
          ),
        FilledButton(
          key: const ValueKey('bulk-close'),
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Close'),
        ),
      ],
    );
  }
}
