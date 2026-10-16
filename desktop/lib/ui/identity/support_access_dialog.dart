import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_refusal.dart';
import '../../models/entities.dart';

/// The customer's administrator switches the support account off or on.
///
/// Backlog 29s. The vendor's support person reaches every firm through one
/// named account; the installation's own administrator decides whether it
/// works today. The reason is required and kept in the audit trail beside who
/// switched it. Switching it off signs the support person out everywhere.
///
/// Returns the account as the server left it, or null for a dismissal.
Future<PlatformUser?> switchSupportAccess(
  BuildContext context, {
  required ApiClient api,
  required PlatformUser user,
}) =>
    showDialog<PlatformUser>(
      context: context,
      barrierDismissible: false,
      builder: (_) => SupportAccessDialog(api: api, user: user),
    );

class SupportAccessDialog extends StatefulWidget {
  const SupportAccessDialog({super.key, required this.api, required this.user});

  final ApiClient api;
  final PlatformUser user;

  @override
  State<SupportAccessDialog> createState() => _SupportAccessDialogState();
}

class _SupportAccessDialogState extends State<SupportAccessDialog> {
  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  final TextEditingController _reason = TextEditingController();
  bool _saving = false;
  String? _error;

  /// What pressing the button will do: the opposite of how it is now.
  bool get _switchingOn => !widget.user.isActive;

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_form.currentState?.validate() ?? false)) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final PlatformUser saved = await widget.api.setSupportAccess(
        widget.user.id,
        active: _switchingOn,
        reason: _reason.text.trim(),
      );
      if (!mounted) return;
      Navigator.of(context).pop(saved);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _error = refusalMessage(error);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text(
          _switchingOn ? 'Switch support access on' : 'Switch support access off'),
      content: SizedBox(
        width: 440,
        child: SingleChildScrollView(
          child: Form(
            key: _form,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _switchingOn
                      ? 'The support account ${widget.user.email} will be able '
                          'to sign in and open every firm again.'
                      : 'The support account ${widget.user.email} will be '
                          'signed out everywhere and unable to sign in until '
                          'it is switched on again.',
                  style: theme.textTheme.bodySmall,
                ),
                const SizedBox(height: 12),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text(
                      _error!,
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.error),
                    ),
                  ),
                TextFormField(
                  controller: _reason,
                  autofocus: true,
                  maxLength: 500,
                  maxLines: 3,
                  minLines: 1,
                  decoration: const InputDecoration(
                    labelText: 'Reason',
                    helperText: 'Kept in the audit trail with your name.',
                  ),
                  validator: (value) => (value ?? '').trim().isEmpty
                      ? 'Say why support access is being changed.'
                      : null,
                ),
              ],
            ),
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _saving ? null : _submit,
          child: Text(_switchingOn ? 'Switch on' : 'Switch off'),
        ),
      ],
    );
  }
}
