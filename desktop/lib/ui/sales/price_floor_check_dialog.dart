import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/price_floor.dart';
import '../workspace/reason_prompt.dart';

/// What confirming a price-floor check decided: whether the approval may go
/// ahead and, only when it goes ahead over a block, the reason to send as
/// `price_override_reason`.
class PriceFloorOutcome {
  const PriceFloorOutcome({required this.proceed, this.overrideReason});

  final bool proceed;
  final String? overrideReason;

  static const PriceFloorOutcome proceedResult =
      PriceFloorOutcome(proceed: true);
  static const PriceFloorOutcome cancelResult =
      PriceFloorOutcome(proceed: false);
}

/// Ask the server whether a document's prices are under their floor and put
/// what comes back in front of the user, before the approve call.
///
/// Advisory, like the licence check: a failed check proceeds, and the server
/// enforces the real policy on the approval itself.
Future<PriceFloorOutcome> confirmPriceFloor(
  BuildContext context,
  PermissionService permissions, {
  required Future<PriceFloorCheck> Function() check,
}) async {
  final PriceFloorCheck result;
  try {
    result = await check();
  } on ApiException {
    return PriceFloorOutcome.proceedResult;
  }
  if (result.findings.isEmpty || !context.mounted) {
    return PriceFloorOutcome.proceedResult;
  }
  final PriceFloorOutcome? outcome = await showDialog<PriceFloorOutcome>(
    context: context,
    barrierDismissible: false,
    builder: (_) => PriceFloorDialog(
      check: result,
      canOverride: permissions.hasPermission('SALES_PRICE_OVERRIDE'),
    ),
  );
  return outcome ?? PriceFloorOutcome.cancelResult;
}

/// Lists the lines under their floor. A warning offers "Approve anyway"; a
/// block offers "Override..." to whoever holds `SALES_PRICE_OVERRIDE` and asks
/// them for a reason; a block to anyone else says who can approve it.
class PriceFloorDialog extends StatelessWidget {
  const PriceFloorDialog({
    super.key,
    required this.check,
    required this.canOverride,
  });

  final PriceFloorCheck check;
  final bool canOverride;

  Future<void> _override(BuildContext context) async {
    final String? reason = await askForReason(
      context,
      title: 'Override the price floor',
      explanation: 'Why this approval goes ahead below the floor price. '
          "Recorded on the document's timeline.",
      confirmLabel: 'Override',
    );
    if (reason == null || !context.mounted) return;
    Navigator.of(context).pop(
      PriceFloorOutcome(proceed: true, overrideReason: reason),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool blocked = check.wouldBlock;
    return AlertDialog(
      scrollable: true,
      icon: Icon(blocked ? Icons.block_outlined : Icons.warning_amber_outlined),
      title: Text(blocked ? 'Below the price floor' : 'Price floor check'),
      content: SizedBox(
        width: 460,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (final PriceFloorFinding finding in check.findings)
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
                'Raise the price, or ask a manager who may override the price '
                'floor to approve this.',
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
            onPressed: () =>
                Navigator.of(context).pop(PriceFloorOutcome.cancelResult),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey('price-floor-approve-anyway'),
            onPressed: () =>
                Navigator.of(context).pop(PriceFloorOutcome.proceedResult),
            child: const Text('Approve anyway'),
          ),
        ] else if (canOverride) ...[
          TextButton(
            onPressed: () =>
                Navigator.of(context).pop(PriceFloorOutcome.cancelResult),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey('price-floor-override'),
            onPressed: () => _override(context),
            child: const Text('Override…'),
          ),
        ] else
          TextButton(
            onPressed: () =>
                Navigator.of(context).pop(PriceFloorOutcome.cancelResult),
            child: const Text('Close'),
          ),
      ],
    );
  }
}
