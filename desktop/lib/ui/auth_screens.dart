import 'package:flutter/material.dart';

import '../core/auth/session_controller.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.session, this.error, this.notice});
  final SessionController session;
  final String? error;
  final String? notice;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _obscure = true;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(32),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text('Agency Platform',
                            style: Theme.of(context).textTheme.headlineMedium),
                        const SizedBox(height: 8),
                        const Text('Sign in to administer the platform.'),
                        if (widget.error != null) ...[
                          const SizedBox(height: 20),
                          _ErrorBanner(message: widget.error!),
                        ],
                        if (widget.notice != null) ...[
                          const SizedBox(height: 20),
                          _NoticeBanner(message: widget.notice!),
                        ],
                        const SizedBox(height: 24),
                        TextFormField(
                          controller: _email,
                          autofocus: true,
                          keyboardType: TextInputType.emailAddress,
                          decoration: const InputDecoration(
                            labelText: 'Email address',
                            prefixIcon: Icon(Icons.mail_outline),
                          ),
                          validator: (value) => value == null ||
                                  !value.contains('@')
                              ? 'Enter a valid email address.'
                              : null,
                        ),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: _password,
                          obscureText: _obscure,
                          onFieldSubmitted: (_) => _submit(),
                          decoration: InputDecoration(
                            labelText: 'Password',
                            prefixIcon: const Icon(Icons.lock_outline),
                            suffixIcon: IconButton(
                              onPressed: () => setState(() => _obscure = !_obscure),
                              icon: Icon(_obscure
                                  ? Icons.visibility_outlined
                                  : Icons.visibility_off_outlined),
                            ),
                          ),
                          validator: (value) => value == null || value.isEmpty
                              ? 'Enter your password.'
                              : null,
                        ),
                        const SizedBox(height: 24),
                        FilledButton(
                          onPressed: _submit,
                          child: const Padding(
                            padding: EdgeInsets.all(12),
                            child: Text('Sign in'),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      );

  void _submit() {
    if (_formKey.currentState!.validate()) {
      widget.session.login(_email.text.trim(), _password.text);
    }
  }
}

class ChangeInitialPasswordScreen extends StatefulWidget {
  const ChangeInitialPasswordScreen({super.key, required this.session});
  final SessionController session;
  @override
  State<ChangeInitialPasswordScreen> createState() =>
      _ChangeInitialPasswordScreenState();
}

class _ChangeInitialPasswordScreenState extends State<ChangeInitialPasswordScreen> {
  final _formKey = GlobalKey<FormState>();
  final _current = TextEditingController();
  final _next = TextEditingController();
  final _confirmation = TextEditingController();

  @override
  void dispose() {
    _current.dispose();
    _next.dispose();
    _confirmation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 440),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: Form(
                  key: _formKey,
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Text('Set a new password',
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(height: 8),
                    const Text(
                      'Your administrator requires a password change before continuing.',
                    ),
                    const SizedBox(height: 20),
                    if (widget.session.error != null)
                      _ErrorBanner(message: widget.session.error!),
                    if (widget.session.error != null) const SizedBox(height: 16),
                    _passwordField(_current, 'Current password'),
                    const SizedBox(height: 12),
                    _passwordField(_next, 'New password'),
                    const SizedBox(height: 12),
                    _passwordField(_confirmation, 'Confirm new password',
                        confirmation: true),
                    const SizedBox(height: 24),
                    FilledButton(
                      onPressed: _submit,
                      child: const Text('Update password'),
                    ),
                  ]),
                ),
              ),
            ),
          ),
        ),
      );

  Widget _passwordField(
    TextEditingController controller,
    String label, {
    bool confirmation = false,
  }) =>
      TextFormField(
        controller: controller,
        obscureText: true,
        decoration: InputDecoration(labelText: label),
        validator: (value) {
          if (value == null || value.length < 12) {
            return 'Use at least 12 characters.';
          }
          if (confirmation && value != _next.text) {
            return 'Passwords do not match.';
          }
          return null;
        },
      );

  void _submit() {
    if (_formKey.currentState!.validate()) {
      widget.session.completeInitialPasswordChange(_current.text, _next.text);
    }
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message});
  final String message;
  @override
  Widget build(BuildContext context) => Semantics(
        liveRegion: true,
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.errorContainer,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Text(
            message,
            style: TextStyle(color: Theme.of(context).colorScheme.onErrorContainer),
          ),
        ),
      );
}

class _NoticeBanner extends StatelessWidget {
  const _NoticeBanner({required this.message});
  final String message;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.primaryContainer,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Text(message),
      );
}
