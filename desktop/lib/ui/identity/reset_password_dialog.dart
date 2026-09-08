import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/entities.dart';
import 'change_password_dialog.dart';

/// A platform administrator sets somebody else's password.
///
/// The self-service change on My profile needs the current password. This is
/// for the cases where nobody can supply it -- forgotten, locked out, or the
/// person has left and the account is being handed over. The server clears
/// any login lock and revokes every session; by default it also makes the
/// person choose their own password at the next sign-in, so a password an
/// administrator typed is a way in and not a password kept.
///
/// Returns true when the password was set, false for a dismissal.
Future<bool> resetUserPassword(
  BuildContext context, {
  required ApiClient api,
  required PlatformUser user,
}) =>
    showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (_) => ResetPasswordDialog(api: api, user: user),
    ).then((done) => done ?? false);

class ResetPasswordDialog extends StatefulWidget {
  const ResetPasswordDialog({super.key, required this.api, required this.user});

  final ApiClient api;
  final PlatformUser user;

  @override
  State<ResetPasswordDialog> createState() => _ResetPasswordDialogState();
}

class _ResetPasswordDialogState extends State<ResetPasswordDialog> {
  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  final TextEditingController _next = TextEditingController();
  final TextEditingController _confirm = TextEditingController();
  bool _forceChange = true;
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _next.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_form.currentState?.validate() ?? false)) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.resetUserPassword(
        widget.user.id,
        _next.text,
        forceChange: _forceChange,
      );
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _error = error.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String who = widget.user.fullName.isEmpty
        ? widget.user.email
        : '${widget.user.fullName} (${widget.user.email})';
    return AlertDialog(
      title: const Text('Reset password'),
      content: SizedBox(
        width: 440,
        // Scrolls rather than overflows: the body is taller than an 800x600
        // window by a few lines, and a 1366x768 screen with the taskbar is
        // not far behind it.
        child: SingleChildScrollView(
          child: Form(
            key: _form,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Sets a new password for $who without their current one. '
                  'Any login lock is cleared and they are signed out '
                  'everywhere. Tell them the password yourself; it is not sent '
                  'anywhere.',
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
                  controller: _next,
                  obscureText: true,
                  autofocus: true,
                  decoration: const InputDecoration(
                    labelText: 'New password',
                    helperText: 'At least 12 characters, with an uppercase '
                        'letter, a lowercase letter, a digit and a symbol.',
                    helperMaxLines: 2,
                  ),
                  validator: ChangePasswordPolicy.check,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _confirm,
                  obscureText: true,
                  decoration:
                      const InputDecoration(labelText: 'Confirm new password'),
                  validator: (value) =>
                      value != _next.text ? 'Passwords do not match.' : null,
                  onFieldSubmitted: (_) => _submit(),
                ),
                const SizedBox(height: 4),
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  controlAffinity: ListTileControlAffinity.leading,
                  value: _forceChange,
                  onChanged: (value) =>
                      setState(() => _forceChange = value ?? true),
                  title: const Text('Require a new password at next sign-in'),
                  // Off is for a handover: the account is being taken over by
                  // somebody who will use this password as theirs.
                  subtitle: const Text(
                    'On, unless this account is being handed to somebody who '
                    'will keep this password.',
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _saving ? null : _submit,
          child: const Text('Set password'),
        ),
      ],
    );
  }
}
