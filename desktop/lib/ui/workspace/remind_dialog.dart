import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/messaging.dart' show HandShare;
import 'save_in_dialog.dart';
import 'whatsapp_share.dart';

/// Reminds a customer to pay by sending them their statement (MSG-3).
///
/// By email through the firm's account -- the statement with the unpaid bills
/// attached -- or from the person's own WhatsApp, as an invoice is shared. A
/// customer marked *no reminders*, or one who owes nothing, is refused by the
/// server by name, and the refusal is shown here.
class RemindDialog extends StatefulWidget {
  const RemindDialog({
    super.key,
    required this.api,
    required this.customerId,
    required this.customerName,
    this.whatsApp = const WhatsAppSharer(),
  });

  final ApiClient api;
  final String customerId;
  final String customerName;

  /// How WhatsApp reaches the machine; a test stands in for it.
  final WhatsAppSharer whatsApp;

  @override
  State<RemindDialog> createState() => _RemindDialogState();
}

class _RemindDialogState extends State<RemindDialog>
    with SaveInDialog<RemindDialog> {
  final TextEditingController _recipient = TextEditingController();
  final TextEditingController _message = TextEditingController();
  String _channel = 'EMAIL';

  @override
  void dispose() {
    _recipient.dispose();
    _message.dispose();
    super.dispose();
  }

  Future<void> _remind() => saveAndClose<bool>(() async {
        if (_channel == 'EMAIL') {
          await widget.api.remindCustomer(
            widget.customerId,
            recipient: _recipient.text.trim(),
            message: _message.text.trim(),
          );
          if (mounted) {
            NotificationService.show(
              context,
              'Reminder queued: the statement goes by email.',
              kind: AppNotificationKind.success,
            );
          }
          return true;
        }
        final HandShare share =
            await widget.api.customerStatementShare(widget.customerId);
        final List<int> pdf =
            await widget.api.customerStatementPdf(widget.customerId);
        if (!mounted) return false;
        return widget.whatsApp.share(
          context,
          share: share,
          pdf: pdf,
          record: () => widget.api.recordHandShare(
            widget.customerId,
            documentType: 'CUSTOMER_STATEMENT',
            recipient: share.phone,
          ),
        );
      });

  @override
  Widget build(BuildContext context) => AlertDialog(
        scrollable: true,
        icon: const Icon(Icons.notifications_active_outlined),
        title: Text('Remind ${widget.customerName}'),
        content: SizedBox(
          width: 440,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              Text(
                'Sends the customer their statement of account, with the '
                'bills still unpaid and how long each is overdue.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              SegmentedButton<String>(
                key: const ValueKey('remind-channel'),
                segments: const [
                  ButtonSegment(
                    value: 'EMAIL',
                    icon: Icon(Icons.email_outlined),
                    label: Text('Email'),
                  ),
                  ButtonSegment(
                    value: 'WHATSAPP',
                    icon: Icon(Icons.chat_outlined),
                    label: Text('WhatsApp, by hand'),
                  ),
                ],
                selected: {_channel},
                onSelectionChanged: saving
                    ? null
                    : (value) => setState(() => _channel = value.first),
              ),
              const SizedBox(height: AppSpacing.md),
              if (_channel == 'EMAIL') ...[
                TextField(
                  key: const ValueKey('remind-recipient'),
                  controller: _recipient,
                  enabled: !saving,
                  decoration: const InputDecoration(
                    labelText: 'Send to',
                    helperText: "Blank sends to the customer's own email",
                  ),
                ),
                const SizedBox(height: AppSpacing.md),
                TextField(
                  key: const ValueKey('remind-message'),
                  controller: _message,
                  enabled: !saving,
                  minLines: 3,
                  maxLines: 6,
                  decoration: const InputDecoration(
                    labelText: 'Message',
                    helperText: 'Blank sends the balance and the overdue bills',
                  ),
                ),
              ] else
                Text(
                  'WhatsApp opens at the customer\'s number with the reminder '
                  'typed in, and the statement is saved and its folder opened '
                  'for you to attach. No messaging account is needed.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: cancelHandler,
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey('remind-send'),
            onPressed: saving ? null : _remind,
            child: Text(
              saving
                  ? 'Working…'
                  : _channel == 'EMAIL'
                      ? 'Send'
                      : 'Open WhatsApp',
            ),
          ),
        ],
      );
}
