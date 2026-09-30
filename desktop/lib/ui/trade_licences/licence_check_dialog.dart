import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/trade_licence.dart';
import '../workspace/reason_prompt.dart';

/// What confirming a licence check decided: whether the caller's action may
/// go ahead, and -- only when it went ahead over a block -- the reason it was
/// overridden with.
class LicenceCheckOutcome {
  const LicenceCheckOutcome({required this.proceed, this.overrideReason});

  /// Nothing found, the finding was only a warning and was accepted, or the
  /// signed-in user cannot even ask (no `TRADE_LICENCE_VIEW`) -- the caller
  /// runs the action exactly as it would have with no check at all.
  final bool proceed;

  /// Set only when a block was overridden. Carried as the
  /// `licence_override_reason` query parameter on the approve call.
  final String? overrideReason;

  static const LicenceCheckOutcome proceedResult =
      LicenceCheckOutcome(proceed: true);
  static const LicenceCheckOutcome cancelResult =
      LicenceCheckOutcome(proceed: false);
}

/// Ask the server what a document's lines need before approving it, and put
/// what comes back in front of the user.
///
/// Called before the approve/complete request, never after: the check is
/// advisory (the server enforces the real policy on the write itself), so a
/// caller that cannot even ask -- no `TRADE_LICENCE_VIEW`, or the check
/// itself fails -- proceeds exactly as it would with no check at all, and the
/// server's own refusal speaks for itself if the policy blocks. This mirrors
/// [warnOnCreditExposure]'s rule for the same reason: warn when nothing is
/// going to stop you, and let the stop speak for itself when something is.
///
/// [document] is one of SALES_ORDER, DELIVERY_NOTE, SALES_INVOICE,
/// PURCHASE_ORDER or GOODS_RECEIPT.
Future<LicenceCheckOutcome> confirmLicenceCheck(
  BuildContext context,
  ApiClient api,
  PermissionService permissions, {
  required String document,
  required String documentId,
}) async {
  if (!permissions.hasPermission('TRADE_LICENCE_VIEW')) {
    return LicenceCheckOutcome.proceedResult;
  }
  final LicenceCheckRecord check;
  try {
    check = await api.checkLicences(document, documentId);
  } on ApiException {
    return LicenceCheckOutcome.proceedResult;
  }
  if (check.findings.isEmpty || !context.mounted) {
    return LicenceCheckOutcome.proceedResult;
  }
  final LicenceCheckOutcome? outcome = await showDialog<LicenceCheckOutcome>(
    context: context,
    barrierDismissible: false,
    builder: (_) => LicenceCheckDialog(
      check: check,
      canOverride: permissions.hasPermission('TRADE_LICENCE_OVERRIDE'),
    ),
  );
  return outcome ?? LicenceCheckOutcome.cancelResult;
}

/// Lists what a licence check found and asks what to do about it.
///
/// Three shapes, one dialog: a warning offers "Approve anyway"; a block
/// offers "Override…" to whoever holds `TRADE_LICENCE_OVERRIDE`, asking for a
/// reason with [askForReason]; a block to anyone else offers only "Close",
/// naming what would let it through.
class LicenceCheckDialog extends StatelessWidget {
  const LicenceCheckDialog({
    super.key,
    required this.check,
    required this.canOverride,
  });

  final LicenceCheckRecord check;
  final bool canOverride;

  Future<void> _override(BuildContext context) async {
    final String? reason = await askForReason(
      context,
      title: 'Override the licence check',
      explanation: "Why this approval goes ahead without the licence it's "
          'missing. Recorded on the document\'s timeline.',
      confirmLabel: 'Override',
    );
    if (reason == null || !context.mounted) return;
    Navigator.of(context).pop(
      LicenceCheckOutcome(proceed: true, overrideReason: reason),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool blocked = check.wouldBlock;
    return AlertDialog(
      scrollable: true,
      icon: Icon(blocked ? Icons.block_outlined : Icons.warning_amber_outlined),
      title: Text(blocked ? 'A licence is missing' : 'Licence check'),
      content: SizedBox(
        width: 460,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (final LicenceFindingRecord finding in check.findings)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      Icons.circle,
                      size: 6,
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(child: Text(finding.message)),
                  ],
                ),
              ),
            if (blocked && !canOverride) ...[
              const SizedBox(height: AppSpacing.sm),
              Text(
                'Record the licence, or ask someone who can override a '
                'licence check to approve this.',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
              ),
            ],
          ],
        ),
      ),
      actions: [
        if (!blocked) ...[
          TextButton(
            onPressed: () => Navigator.of(context)
                .pop(LicenceCheckOutcome.cancelResult),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey('licence-check-approve-anyway'),
            onPressed: () => Navigator.of(context)
                .pop(LicenceCheckOutcome.proceedResult),
            child: const Text('Approve anyway'),
          ),
        ] else if (canOverride) ...[
          TextButton(
            onPressed: () => Navigator.of(context)
                .pop(LicenceCheckOutcome.cancelResult),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey('licence-check-override'),
            onPressed: () => _override(context),
            child: const Text('Override…'),
          ),
        ] else
          TextButton(
            onPressed: () => Navigator.of(context)
                .pop(LicenceCheckOutcome.cancelResult),
            child: const Text('Close'),
          ),
      ],
    );
  }
}
