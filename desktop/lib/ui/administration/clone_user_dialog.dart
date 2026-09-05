import 'package:flutter/material.dart';

/// The three things that do not cross over when somebody is hired like
/// somebody else.
class CloneUserDetails {
  const CloneUserDetails({
    required this.email,
    required this.fullName,
    required this.password,
  });

  final String email, fullName, password;
}

/// Ask who the new person is.
///
/// The dialog owns its controllers. A caller that creates them, awaits
/// `showDialog` and then disposes them disposes them *mid-animation*, and the
/// field rebuilding during the exit throws "A TextEditingController was used
/// after being disposed" -- written twice in this repo in one afternoon before
/// `askForReason` existed.
///
/// Returns null for a dismissal.
Future<CloneUserDetails?> askForCloneDetails(
  BuildContext context, {
  required String sourceName,
}) =>
    showDialog<CloneUserDetails>(
      context: context,
      builder: (_) => _CloneUserDialog(sourceName: sourceName),
    );

class _CloneUserDialog extends StatefulWidget {
  const _CloneUserDialog({required this.sourceName});

  final String sourceName;

  @override
  State<_CloneUserDialog> createState() => _CloneUserDialogState();
}

class _CloneUserDialogState extends State<_CloneUserDialog> {
  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  final TextEditingController _email = TextEditingController();
  final TextEditingController _name = TextEditingController();
  final TextEditingController _password = TextEditingController();

  @override
  void dispose() {
    _email.dispose();
    _name.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: const Text('Hire like this person'),
      // An AlertDialog gives its content unbounded height, so a stretched
      // Column with no width overflows by tens of thousands of pixels instead
      // of laying out. Both dimensions are bounded on purpose.
      content: SizedBox(
        width: 460,
        child: Form(
          key: _form,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'The new user gets the same roles and firms as '
                '${widget.sourceName}, and none of their personal details, '
                'password or history. You can edit their roles afterwards '
                'like any other user.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _name,
                decoration: const InputDecoration(labelText: 'Full name'),
                validator: (value) => (value ?? '').trim().isEmpty
                    ? 'Give the new person a name.'
                    : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _email,
                decoration: const InputDecoration(labelText: 'Email'),
                validator: (value) {
                  final String email = (value ?? '').trim();
                  if (email.isEmpty) return 'An email is required.';
                  if (!email.contains('@')) return 'That is not an email.';
                  return null;
                },
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _password,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: 'Initial password',
                  // A password somebody else chose is not a password. Saying
                  // so here is what stops an administrator handing it over as
                  // though it were permanent.
                  helperText: 'They must change it when they first sign in.',
                ),
                validator: (value) => (value ?? '').isEmpty
                    ? 'An initial password is required.'
                    : null,
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            if (!(_form.currentState?.validate() ?? false)) return;
            Navigator.of(context).pop(
              CloneUserDetails(
                email: _email.text.trim(),
                fullName: _name.text.trim(),
                password: _password.text,
              ),
            );
          },
          child: const Text('Create'),
        ),
      ],
    );
  }
}
