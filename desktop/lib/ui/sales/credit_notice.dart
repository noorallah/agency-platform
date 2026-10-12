import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../models/customer.dart';

/// Ask before a customer close to their credit limit is given one more
/// document, and say whether to go on (backlog 107).
///
/// The firm's policy decides whether a document is actually refused, and that
/// decision belongs to the server: a client that blocked on its own would be
/// enforcing a rule the firm may not have chosen, and could be bypassed by any
/// other client anyway. So this only ever asks -- the person who answers
/// "Approve anyway" goes on, in either mode. It was a notice that passed by
/// while the approval ran, which nobody had to read.
///
/// It stays quiet when the server is going to refuse the document. In that
/// case the refusal carries the same sentence, and asking first would print
/// it twice: once as a question and again as the error that actually happened.
/// The rule is to ask when nothing is going to stop you, and to let the stop
/// speak for itself when something is.
Future<bool> confirmCreditExposure(
  BuildContext context,
  ApiClient api, {
  required String? customerId,
  required String amount,
}) async {
  if (customerId == null || customerId.isEmpty) return true;
  final CustomerCreditStatus status;
  try {
    status = await api.customerCreditStatus(customerId, amount: amount);
  } on ApiException {
    // An advisory check that cannot run is not a reason to hold up work. The
    // server applies the policy on approval regardless of what this call did.
    return true;
  }
  if (!status.isWarning || !status.hasNotice || !context.mounted) return true;
  return AppDialogs.confirm(
    context,
    title: 'Credit limit',
    message: status.message,
    confirmLabel: 'Approve anyway',
  );
}
