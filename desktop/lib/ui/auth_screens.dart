import 'package:flutter/material.dart';

import '../core/auth/session_controller.dart';
import '../core/branding/branding_config.dart';
import '../core/preferences/desktop_preferences_service.dart';
import '../core/theme/theme_manager.dart';
import 'theme_selector.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({
    super.key,
    required this.session,
    required this.preferences,
    required this.branding,
    required this.themes,
    this.error,
    this.notice,
  });

  final SessionController session;
  final DesktopPreferencesService preferences;
  final BrandingConfig branding;
  final ThemeManager themes;
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
  late bool _rememberUsername;
  late bool _rememberMe;

  @override
  void initState() {
    super.initState();
    final DesktopPreferences stored = widget.preferences.current;
    _rememberUsername = stored.rememberUsername;
    _rememberMe = stored.rememberMe;
    if (_rememberUsername) {
      _email.text = stored.cachedUsername ?? '';
    }
  }

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Scaffold(
      backgroundColor: widget.branding.loginBackgroundColor,
      body: SafeArea(
        child: Stack(
          children: [
            Positioned(
              top: 8,
              right: 8,
              child: Row(
                children: [
                  ThemeSelector(manager: widget.themes),
                  IconButton(
                    icon: const Icon(Icons.settings_outlined),
                    tooltip: 'Server settings',
                    onPressed: _showServerSettings,
                  ),
                ],
              ),
            ),
            Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 440),
                  child: Card(
                    child: Padding(
                      padding: const EdgeInsets.all(32),
                      child: Form(
                        key: _formKey,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            _BrandMark(branding: widget.branding),
                            const SizedBox(height: 16),
                            Text(
                              'Sign in to ${widget.branding.productName}.',
                              style: theme.textTheme.bodyLarge,
                              textAlign: TextAlign.center,
                            ),
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
                              validator: (value) =>
                                  value == null || !value.contains('@')
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
                                  onPressed: () =>
                                      setState(() => _obscure = !_obscure),
                                  icon: Icon(_obscure
                                      ? Icons.visibility_outlined
                                      : Icons.visibility_off_outlined),
                                ),
                              ),
                              validator: (value) =>
                                  value == null || value.isEmpty
                                      ? 'Enter your password.'
                                      : null,
                            ),
                            CheckboxListTile(
                              value: _rememberUsername,
                              contentPadding: EdgeInsets.zero,
                              title: const Text('Remember username'),
                              onChanged: (value) => setState(
                                () => _rememberUsername = value ?? false,
                              ),
                            ),
                            CheckboxListTile(
                              value: _rememberMe,
                              contentPadding: EdgeInsets.zero,
                              title: const Text('Remember me on this device'),
                              subtitle: const Text(
                                'Keeps a secure refresh token; never stores your password.',
                              ),
                              onChanged: (value) =>
                                  setState(() => _rememberMe = value ?? false),
                            ),
                            const SizedBox(height: 12),
                            FilledButton(
                              onPressed: _submit,
                              child: const Padding(
                                padding: EdgeInsets.all(12),
                                child: Text('Sign in'),
                              ),
                            ),
                            TextButton(
                              onPressed: _showForgotPassword,
                              child: const Text('Forgot password?'),
                            ),
                            const Divider(height: 32),
                            Text(
                              '${widget.branding.companyName} • ${widget.branding.version}',
                              textAlign: TextAlign.center,
                              style: theme.textTheme.bodySmall,
                            ),
                            const SizedBox(height: 4),
                            Text(
                              '${widget.branding.supportEmail} • '
                              '${widget.branding.supportWebsite}',
                              textAlign: TextAlign.center,
                              style: theme.textTheme.bodySmall,
                            ),
                            const SizedBox(height: 4),
                            Text(
                              widget.branding.copyright,
                              textAlign: TextAlign.center,
                              style: theme.textTheme.bodySmall,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _showServerSettings() async {
    final TextEditingController server =
        TextEditingController(text: widget.session.baseUrl);
    String? error;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Server settings'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: server,
                keyboardType: TextInputType.url,
                decoration: const InputDecoration(
                  labelText: 'API server URL',
                  hintText: 'https://api.example.com',
                ),
              ),
              if (widget.preferences.current.recentServers.isNotEmpty)
                DropdownButton<String>(
                  isExpanded: true,
                  hint: const Text('Recent servers'),
                  items: widget.preferences.current.recentServers
                      .map(
                        (url) => DropdownMenuItem(value: url, child: Text(url)),
                      )
                      .toList(),
                  onChanged: (value) {
                    if (value != null) {
                      server.text = value;
                    }
                  },
                ),
              if (error != null) _ErrorBanner(message: error!),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () async {
                try {
                  await widget.session.updateServerUrl(server.text);
                  if (dialogContext.mounted) {
                    Navigator.of(dialogContext).pop();
                  }
                } on FormatException catch (exception) {
                  setDialogState(() => error = exception.message);
                }
              },
              child: const Text('Save'),
            ),
          ],
        ),
      ),
    );
    server.dispose();
  }

  Future<void> _showForgotPassword() => showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Password assistance'),
          content: const Text(
            'Password reset is not available in this desktop application. '
            'Contact your platform administrator for help resetting your password.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Close'),
            ),
          ],
        ),
      );

  void _submit() {
    if (_formKey.currentState!.validate()) {
      widget.session.login(
        _email.text.trim(),
        _password.text,
        rememberUsername: _rememberUsername,
        rememberMe: _rememberMe,
      );
    }
  }
}

class _BrandMark extends StatelessWidget {
  const _BrandMark({required this.branding});
  final BrandingConfig branding;

  @override
  Widget build(BuildContext context) {
    final logo = branding.logoFile;
    return Column(
      children: [
        if (logo != null)
          Image.file(logo, height: 64, fit: BoxFit.contain)
        else
          Icon(
            Icons.account_balance_outlined,
            size: 48,
            color: branding.loginAccentColor,
          ),
        const SizedBox(height: 8),
        Text(
          branding.appName,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineMedium,
        ),
      ],
    );
  }
}

class ChangeInitialPasswordScreen extends StatefulWidget {
  const ChangeInitialPasswordScreen({
    super.key,
    required this.session,
    required this.branding,
  });
  final SessionController session;
  final BrandingConfig branding;
  @override
  State<ChangeInitialPasswordScreen> createState() =>
      _ChangeInitialPasswordScreenState();
}

class _ChangeInitialPasswordScreenState
    extends State<ChangeInitialPasswordScreen> {
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
                    Text(
                      'Your ${widget.branding.companyName} administrator requires '
                      'a password change before continuing.',
                    ),
                    const SizedBox(height: 20),
                    if (widget.session.error != null)
                      _ErrorBanner(message: widget.session.error!),
                    if (widget.session.error != null)
                      const SizedBox(height: 16),
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
            style: TextStyle(
                color: Theme.of(context).colorScheme.onErrorContainer),
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
