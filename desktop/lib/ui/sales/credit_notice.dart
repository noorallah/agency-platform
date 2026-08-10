import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/customer.dart';

/// Tell the user a customer is close to their credit limit, then get out of
/// the way.
///
/// The firm's policy decides whether a document is actually refused, and that
/// decision belongs to the server: a client that blocked on its own would be
/// enforcing a rule the firm may not have chosen, and could be bypassed by any
/// other client anyway. So this reports and returns -- the caller proceeds
/// either way.
///
/// It stays quiet when the server is going to refuse the document. In that
/// case the refusal carries the same sentence, and warning first would print
/// it twice: once as a caution and again as the error that actually happened.
/// The rule is to warn when nothing is going to stop you, and to let the stop
/// speak for itself when something is.
Future<void> warnOnCreditExposure(
  BuildContext context,
  ApiClient api, {
  required String? customerId,
  required String amount,
}) async {
  if (customerId == null || customerId.isEmpty) return;
  final CustomerCreditStatus status;
  try {
    status = await api.customerCreditStatus(customerId, amount: amount);
  } on ApiException {
    // An advisory check that cannot run is not a reason to hold up work. The
    // server applies the policy on approval regardless of what this call did.
    return;
  }
  if (!status.isWarning || !status.hasNotice || !context.mounted) return;
  NotificationService.show(
    context,
    status.message,
    kind: AppNotificationKind.warning,
  );
}
