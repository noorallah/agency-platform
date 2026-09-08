import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';

/// Change your own password, from My profile.
///
/// `POST /auth/change-password` existed for a year and was reachable from
/// exactly one place: the screen a *forced* change lands on. A person who
/// simply wanted a new password had no way to set one. This is the ordinary
/// way, and it ends the same as the forced one: the server revokes every
/// session on a password change, so the caller signs the person out and the
/// login screen says why.
///
/// The policy is checked here as well as on the server -- twelve characters
/// with an uppercase letter, a lowercase letter, a digit and a symbol -- so
/// somebody gets the rule named beside the box rather than a 422 rendered as
/// a failure. The server still decides: it also refuses the last five
/// passwords, which only it can check.
///
/// Returns true when the password was changed, false for a dismissal.
Future<bool> changeOwnPassword(BuildContext context,
        {required ApiClient api}) =>
    showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (_) => ChangePasswordDialog(api: api),
    ).then((changed) => changed ?? false);

/// The server's password policy, named rule by rule.
///
/// Checked client-side so the rule appears beside the box; the server still
/// decides, and it alone can refuse one of the last five passwords.
abstract final class ChangePasswordPolicy {
  static String? check(String? value) {
    final String text = value ?? '';
    if (text.length < 12) return 'Use at least 12 characters.';
    if (!text.contains(RegExp('[A-Z]'))) return 'Include an uppercase letter.';
    if (!text.contains(RegExp('[a-z]'))) return 'Include a lowercase letter.';
    if (!text.contains(RegExp('[0-9]'))) return 'Include a digit.';
    if (!text.contains(RegExp('[^A-Za-z0-9]'))) return 'Include a symbol.';
    return null;
  }
}

class ChangePasswordDialog extends StatefulWidget {
  const ChangePasswordDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<ChangePasswordDialog> createState() => _ChangePasswordDialogState();
}

class _ChangePasswordDialogState extends State<ChangePasswordDialog> {
  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  final TextEditingController _current = TextEditingController();
  final TextEditingController _next = TextEditingController();
  final TextEditingController _confirm = TextEditingController();
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _current.dispose();
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
      await widget.api.changePassword(_current.text, _next.text);
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      // The server's own refusal -- a wrong current password, or one of the
      // last five reused -- shown where it can be acted on.
      setState(() {
        _saving = false;
        _error = error.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: const Text('Change password'),
      content: SizedBox(
        width: 420,
        // Scrolls rather than overflows on a short screen.
        child: SingleChildScrollView(
          child: Form(
            key: _form,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Changing it signs you out everywhere, including here. '
                  'Sign in again with the new password.',
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
                  controller: _current,
                  obscureText: true,
                  autofocus: true,
                  decoration:
                      const InputDecoration(labelText: 'Current password'),
                  validator: (value) => (value ?? '').isEmpty
                      ? 'Enter your current password.'
                      : null,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _next,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: 'New password',
                    helperText: 'At least 12 characters, with an uppercase '
                        'letter, a lowercase letter, a digit and a symbol. Not '
                        'one of your last five.',
                    helperMaxLines: 3,
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
          child: const Text('Change password'),
        ),
      ],
    );
  }
}
