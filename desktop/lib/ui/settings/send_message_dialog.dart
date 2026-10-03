import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../workspace/save_in_dialog.dart';

/// Sends an approved sales invoice to its customer, on a channel chosen now.
///
/// Needs `DOCUMENT_SEND`. The server queues it and refuses, by name, when the
/// firm has not switched messaging or that channel on, or the customer cannot
/// be reached on it; the refusal is shown here with everything kept.
class SendMessageDialog extends StatefulWidget {
  const SendMessageDialog({
    super.key,
    required this.api,
    required this.invoiceId,
    required this.invoiceNumber,
    this.documentType = 'SALES_INVOICE',
  });

  final ApiClient api;
  final String invoiceId;
  final String invoiceNumber;

  /// What is being sent (MSG-4); [invoiceId] is then that document's id (the
  /// customer's, for a statement). Anything but an invoice goes by email
  /// only, so the channel picker is not offered.
  final String documentType;

  bool get _invoice => documentType == 'SALES_INVOICE';

  @override
  State<SendMessageDialog> createState() => _SendMessageDialogState();
}

class _SendMessageDialogState extends State<SendMessageDialog>
    with SaveInDialog<SendMessageDialog> {
  final TextEditingController _recipient = TextEditingController();
  final TextEditingController _message = TextEditingController();
  String _channel = 'EMAIL';

  @override
  void dispose() {
    _recipient.dispose();
    _message.dispose();
    super.dispose();
  }

  Future<void> _send() => saveAndClose<bool>(() async {
        await widget.api.sendDocumentMessage(
          widget.documentType,
          widget.invoiceId,
          _channel,
          recipient: _recipient.text.trim(),
          message: _channel == 'EMAIL' ? _message.text.trim() : null,
        );
        if (mounted) {
          NotificationService.show(
            context,
            'Queued to send.',
            kind: AppNotificationKind.success,
          );
        }
        return true;
      });

  @override
  Widget build(BuildContext context) => AlertDialog(
        scrollable: true,
        icon: const Icon(Icons.send_outlined),
        title: Text('Send ${widget.invoiceNumber}'),
        content: SizedBox(
          width: 420,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              DropdownButtonFormField<String>(
                key: const ValueKey('send-message-channel'),
                isExpanded: true,
                initialValue: _channel,
                decoration: const InputDecoration(labelText: 'Channel'),
                items: [
                  const DropdownMenuItem(value: 'EMAIL', child: Text('Email')),
                  if (widget._invoice) ...const [
                    DropdownMenuItem(
                        value: 'WHATSAPP', child: Text('WhatsApp')),
                    DropdownMenuItem(value: 'SMS', child: Text('SMS')),
                  ],
                ],
                onChanged: saving
                    ? null
                    : (value) => setState(() => _channel = value ?? _channel),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('send-message-recipient'),
                controller: _recipient,
                enabled: !saving,
                decoration: InputDecoration(
                  labelText: 'Send to',
                  helperText: widget.documentType == 'PURCHASE_ORDER'
                      ? "Blank sends to the supplier's own address"
                      : widget._invoice
                          ? "Blank sends to the customer's own address "
                              'or number'
                          : "Blank sends to the customer's own address",
                ),
              ),
              if (_channel == 'EMAIL') ...[
                const SizedBox(height: AppSpacing.md),
                TextField(
                  key: const ValueKey('send-message-body'),
                  controller: _message,
                  enabled: !saving,
                  minLines: 3,
                  maxLines: 6,
                  decoration: const InputDecoration(
                    labelText: 'Message',
                    helperText: 'Blank sends the firm\'s standard wording',
                  ),
                ),
              ],
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: cancelHandler,
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey('send-message-send'),
            onPressed: saving ? null : _send,
            child: Text(saving ? 'Sending…' : 'Send'),
          ),
        ],
      );
}
