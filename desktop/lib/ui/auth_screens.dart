import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/auth/session_controller.dart';
import '../core/branding/branding_config.dart';
import '../core/preferences/desktop_preferences_service.dart';
import '../core/theme/theme_manager.dart';
import 'theme_selector.dart';

const String _buildNumber =
    String.fromEnvironment('BUILD_NUMBER', defaultValue: 'Unknown');

class LoginScreen extends StatefulWidget {
  const LoginScreen({
    super.key,
    required this.session,
    required this.preferences,
    required this.branding,
    required this.themes,
    this.error,
    this.notice,
    this.capsLockEnabled,
  });

  final SessionController session;
  final DesktopPreferencesService preferences;
  final BrandingConfig branding;
  final ThemeManager themes;
  final String? error;
  final String? notice;
  final bool Function()? capsLockEnabled;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _username = TextEditingController();
  final _password = TextEditingController();
  final _usernameFocus = FocusNode();
  final _passwordFocus = FocusNode();

  bool _obscure = true;
  late bool _rememberUsername;
  late bool _rememberMe;
  bool _errorVisible = true;
  bool _capsLockOn = false;

  @override
  void initState() {
    super.initState();
    final DesktopPreferences stored = widget.preferences.current;
    _rememberUsername = stored.rememberUsername;
    _rememberMe = stored.rememberMe;
    _username.text = _rememberUsername
        ? stored.cachedUsername ??
            (stored.recentUsernames.isNotEmpty ? stored.recentUsernames.first : '')
        : widget.session.attemptedUsername ?? '';
    _errorVisible = widget.error != null;
    _usernameFocus.addListener(_handleFocusChanged);
    _passwordFocus.addListener(_handleFocusChanged);
    _syncCapsLockState();
  }

  @override
  void didUpdateWidget(covariant LoginScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.error != oldWidget.error) {
      _errorVisible = widget.error != null;
      if (widget.error != null) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) {
            _passwordFocus.requestFocus();
          }
        });
      }
    }
  }

  @override
  void dispose() {
    _usernameFocus.removeListener(_handleFocusChanged);
    _passwordFocus.removeListener(_handleFocusChanged);
    _usernameFocus.dispose();
    _passwordFocus.dispose();
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  bool get _isSubmitting => widget.session.status == SessionStatus.authenticating;
  bool get _showEnvironment => !kReleaseMode;

  void _handleFocusChanged() {
    if (!mounted) return;
    _syncCapsLockState();
    setState(() {});
  }

  void _syncCapsLockState() {
    final bool capsLock = widget.capsLockEnabled?.call() ??
        HardwareKeyboard.instance.lockModesEnabled.contains(
          KeyboardLockMode.capsLock,
        );
    if (_capsLockOn != capsLock && mounted) {
      setState(() => _capsLockOn = capsLock);
    } else {
      _capsLockOn = capsLock;
    }
  }

  void _dismissError() {
    if (_errorVisible) {
      setState(() => _errorVisible = false);
    }
  }

  void _focusPassword() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        _passwordFocus.requestFocus();
      }
    });
  }

  void _applySavedUsername(String username) {
    _username.text = username;
    _focusPassword();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: widget.branding.loginBackgroundColor,
      body: SafeArea(
        child: Stack(
          children: [
            const Positioned.fill(child: _LoginBackdrop()),
            Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    final bool wide = constraints.maxWidth >= 980;
                    final Widget intro = ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 420),
                      child: _LoginIntroPanel(branding: widget.branding),
                    );
                    final Widget form = ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 540),
                      child: _LoginCard(
                        formKey: _formKey,
                        branding: widget.branding,
                        preferences: widget.preferences,
                        errorVisible: _errorVisible,
                        error: widget.error,
                        notice: widget.notice,
                        usernameController: _username,
                        usernameFocus: _usernameFocus,
                        passwordController: _password,
                        passwordFocus: _passwordFocus,
                        obscurePassword: _obscure,
                        capsLockOn: _capsLockOn,
                        rememberUsername: _rememberUsername,
                        rememberMe: _rememberMe,
                        isSubmitting: _isSubmitting,
                        showEnvironment: _showEnvironment,
                        onDismissError: _dismissError,
                        onUsernameSelected: _applySavedUsername,
                        onUsernameRememberChanged: (value) =>
                            setState(() => _rememberUsername = value),
                        onRememberMeChanged: (value) =>
                            setState(() => _rememberMe = value),
                        onTogglePasswordVisibility: () =>
                            setState(() => _obscure = !_obscure),
                        onSubmit: _submit,
                        onShowPasswordHelp: _showForgotPassword,
                        onPasswordCapsLockChanged: _syncCapsLockState,
                      ),
                    );
                    if (wide) {
                      return Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          intro,
                          const SizedBox(width: 28),
                          form,
                        ],
                      );
                    }
                    return Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        intro,
                        const SizedBox(height: 20),
                        form,
                      ],
                    );
                  },
                ),
              ),
            ),
            Positioned(
              top: 12,
              right: 12,
              child: Material(
                color: Colors.transparent,
                child: _Toolbar(
                  children: [
                    ThemeSelector(manager: widget.themes),
                    IconButton(
                      icon: const Icon(Icons.settings_outlined),
                      tooltip: 'Application Settings',
                      onPressed: _showApplicationSettings,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _showApplicationSettings() async {
    final TextEditingController apiUrl =
        TextEditingController(text: widget.session.baseUrl);
    String? error;
    AppTheme selectedTheme = widget.themes.current;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Application Settings'),
          content: SizedBox(
            width: 520,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  DropdownButtonFormField<AppTheme>(
                    value: selectedTheme,
                    decoration: const InputDecoration(labelText: 'Theme'),
                    items: AppTheme.values
                        .map(
                          (theme) => DropdownMenuItem(
                            value: theme,
                            child: Text(theme.label),
                          ),
                        )
                        .toList(),
                    onChanged: (value) {
                      if (value == null) return;
                      setDialogState(() => selectedTheme = value);
                      unawaited(widget.themes.select(value));
                    },
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: apiUrl,
                    keyboardType: TextInputType.url,
                    decoration: const InputDecoration(
                      labelText: 'API URL',
                      hintText: 'https://api.example.com',
                    ),
                  ),
                  if (widget.preferences.current.recentServers.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      value: widget.preferences.current.recentServers.first,
                      decoration:
                          const InputDecoration(labelText: 'Recent Servers'),
                      items: widget.preferences.current.recentServers
                          .map(
                            (url) => DropdownMenuItem(
                              value: url,
                              child: Text(url),
                            ),
                          )
                          .toList(),
                      onChanged: (value) {
                        if (value != null) {
                          apiUrl.text = value;
                        }
                      },
                    ),
                  ],
                  const SizedBox(height: 16),
                  InputDecorator(
                    decoration:
                        const InputDecoration(labelText: 'Language (future)'),
                    child: const Text('Coming soon'),
                  ),
                  const SizedBox(height: 16),
                  InputDecorator(
                    decoration: const InputDecoration(labelText: 'Font Size'),
                    child: const Text('Default'),
                  ),
                  const SizedBox(height: 16),
                  _AboutBlock(
                    branding: widget.branding,
                    showEnvironment: _showEnvironment,
                  ),
                  if (error != null) ...[
                    const SizedBox(height: 16),
                    _ErrorBanner(
                      message: error!,
                      onDismiss: () => setDialogState(() => error = null),
                    ),
                  ],
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () async {
                try {
                  await widget.session.updateServerUrl(apiUrl.text);
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
    apiUrl.dispose();
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
    if (_isSubmitting) {
      return;
    }
    if (_formKey.currentState!.validate()) {
      unawaited(
        widget.session.login(
          _username.text.trim(),
          _password.text.trim(),
          rememberUsername: _rememberUsername,
          rememberMe: _rememberMe,
        ),
      );
    }
  }
}

class _LoginBackdrop extends StatelessWidget {
  const _LoginBackdrop();

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            theme.colorScheme.surface,
            theme.colorScheme.surfaceVariant.withOpacity(.25),
            theme.colorScheme.background,
          ],
        ),
      ),
      child: Stack(
        children: [
          Positioned(
            top: -40,
            right: -20,
            child: Opacity(
              opacity: .05,
              child: Icon(
                Icons.account_balance_outlined,
                size: 320,
                color: theme.colorScheme.primary,
              ),
            ),
          ),
          Positioned(
            bottom: -80,
            left: -30,
            child: Opacity(
              opacity: .04,
              child: Icon(
                Icons.apartment_outlined,
                size: 280,
                color: theme.colorScheme.primary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Toolbar extends StatelessWidget {
  const _Toolbar({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Material(
        color: Theme.of(context).colorScheme.surface.withOpacity(.92),
        elevation: 2,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
          child: Row(mainAxisSize: MainAxisSize.min, children: children),
        ),
      );
}

class _LoginIntroPanel extends StatelessWidget {
  const _LoginIntroPanel({required this.branding});

  final BrandingConfig branding;

  @override
  Widget build(BuildContext context) {
      final ThemeData theme = Theme.of(context);
      return Container(
        padding: const EdgeInsets.all(28),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(24),
          color: theme.colorScheme.surface.withValues(alpha: 0.74),
          border: Border.all(color: theme.dividerColor.withValues(alpha: 0.4)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            _BrandMark(branding: branding),
            const SizedBox(height: 18),
            Text(
              branding.appName,
              style: theme.textTheme.headlineMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Fast sign-in, remembered usernames, and a cleaner desktop workflow.',
              style: theme.textTheme.bodyLarge,
            ),
            const SizedBox(height: 20),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: const [
                _FeatureChip(icon: Icons.speed_rounded, label: 'Fast access'),
                _FeatureChip(icon: Icons.group_work_outlined, label: 'Multi-firm'),
                _FeatureChip(icon: Icons.shield_outlined, label: 'Secure login'),
                _FeatureChip(icon: Icons.touch_app_outlined, label: 'Easy to use'),
              ],
            ),
            const SizedBox(height: 20),
            _InfoCard(
              title: 'Remembered usernames',
              body: 'Pick a saved username directly from the username field.',
              icon: Icons.badge_outlined,
            ),
            const SizedBox(height: 12),
            _InfoCard(
              title: 'Smarter session handling',
              body: 'Keep your session active without storing your password.',
              icon: Icons.lock_clock_outlined,
            ),
            const SizedBox(height: 12),
            _InfoCard(
              title: 'Enterprise ready',
              body: 'Designed for firm-scoped work, role-based access, and desktop use.',
              icon: Icons.apartment_outlined,
            ),
          ],
        ),
      );
  }
}

class _FeatureChip extends StatelessWidget {
  const _FeatureChip({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
      final ThemeData theme = Theme.of(context);
      return Chip(
        avatar: Icon(icon, size: 18, color: theme.colorScheme.primary),
        label: Text(label),
        side: BorderSide(color: theme.dividerColor.withValues(alpha: 0.4)),
        backgroundColor: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.6),
      );
  }
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({
      required this.title,
      required this.body,
      required this.icon,
  });

  final String title;
  final String body;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
      final ThemeData theme = Theme.of(context);
      return Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.6),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: theme.dividerColor.withValues(alpha: 0.35)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: theme.colorScheme.primary),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: theme.textTheme.titleSmall),
                  const SizedBox(height: 4),
                  Text(body, style: theme.textTheme.bodySmall),
                ],
              ),
            ),
          ],
        ),
      );
  }
}

class _LoginCard extends StatelessWidget {
  const _LoginCard({
      required this.formKey,
      required this.branding,
      required this.preferences,
      required this.errorVisible,
      required this.error,
      required this.notice,
      required this.usernameController,
      required this.usernameFocus,
      required this.passwordController,
      required this.passwordFocus,
      required this.obscurePassword,
      required this.capsLockOn,
      required this.rememberUsername,
      required this.rememberMe,
      required this.isSubmitting,
      required this.showEnvironment,
      required this.onDismissError,
      required this.onUsernameSelected,
      required this.onUsernameRememberChanged,
      required this.onRememberMeChanged,
      required this.onTogglePasswordVisibility,
      required this.onSubmit,
      required this.onShowPasswordHelp,
      required this.onPasswordCapsLockChanged,
  });

  final GlobalKey<FormState> formKey;
  final BrandingConfig branding;
  final DesktopPreferencesService preferences;
  final bool errorVisible;
  final String? error;
  final String? notice;
  final TextEditingController usernameController;
  final FocusNode usernameFocus;
  final TextEditingController passwordController;
  final FocusNode passwordFocus;
  final bool obscurePassword;
  final bool capsLockOn;
  final bool rememberUsername;
  final bool rememberMe;
  final bool isSubmitting;
  final bool showEnvironment;
  final VoidCallback onDismissError;
  final ValueChanged<String> onUsernameSelected;
  final ValueChanged<bool> onUsernameRememberChanged;
  final ValueChanged<bool> onRememberMeChanged;
  final VoidCallback onTogglePasswordVisibility;
  final VoidCallback onSubmit;
  final VoidCallback onShowPasswordHelp;
  final VoidCallback onPasswordCapsLockChanged;

  @override
  Widget build(BuildContext context) {
      final ThemeData theme = Theme.of(context);
      return Card(
        elevation: 8,
        child: Padding(
          padding: const EdgeInsets.all(34),
          child: Shortcuts(
            shortcuts: const {
              SingleActivator(LogicalKeyboardKey.escape): _DismissErrorIntent(),
            },
            child: Actions(
              actions: {
                _DismissErrorIntent: CallbackAction<_DismissErrorIntent>(
                  onInvoke: (intent) {
                    onDismissError();
                    return null;
                  },
                ),
              },
              child: Form(
                key: formKey,
                child: AutofillGroup(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        branding.appName,
                        textAlign: TextAlign.center,
                        style: theme.textTheme.headlineMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Welcome back',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.headlineSmall,
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'Sign in with a remembered username or enter a new one.',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.bodyMedium,
                      ),
                      if (error != null && errorVisible) ...[
                        const SizedBox(height: 20),
                        _ErrorBanner(onDismiss: onDismissError),
                      ],
                      if (notice != null) ...[
                        const SizedBox(height: 20),
                        _NoticeBanner(message: notice!),
                      ],
                      const SizedBox(height: 24),
                      RawAutocomplete<String>(
                        textEditingController: usernameController,
                        focusNode: usernameFocus,
                        optionsBuilder: (TextEditingValue textEditingValue) {
                          final List<String> usernames =
                              preferences.current.recentUsernames;
                          final String query =
                              textEditingValue.text.trim().toLowerCase();
                          if (usernames.isEmpty) {
                            return const Iterable<String>.empty();
                          }
                          if (query.isEmpty) {
                            return usernames.take(6);
                          }
                          return usernames
                              .where(
                                (username) =>
                                    username.toLowerCase().contains(query),
                              )
                              .take(6);
                        },
                        displayStringForOption: (value) => value,
                        onSelected: onUsernameSelected,
                        fieldViewBuilder: (
                          context,
                          controller,
                          focusNode,
                          onFieldSubmitted,
                        ) {
                          return TextFormField(
                            controller: controller,
                            focusNode: focusNode,
                            autofocus: true,
                            textInputAction: TextInputAction.next,
                            keyboardType: TextInputType.text,
                            autofillHints: const [
                              AutofillHints.username,
                              AutofillHints.email,
                            ],
                            decoration: const InputDecoration(
                              labelText: 'Username / Email',
                              helperText:
                                  'Supports username, email, and employee ID (future).',
                              prefixIcon: Icon(Icons.badge_outlined),
                            ),
                            onFieldSubmitted: (_) => onFieldSubmitted(),
                            validator: (value) {
                              if (value == null || value.trim().isEmpty) {
                                return 'Enter your username or email.';
                              }
                              return null;
                            },
                          );
                        },
                        optionsViewBuilder: (context, onSelected, options) {
                          final ThemeData optionTheme = Theme.of(context);
                          return Align(
                            alignment: Alignment.topLeft,
                            child: Material(
                              elevation: 10,
                              borderRadius: BorderRadius.circular(12),
                              color: optionTheme.colorScheme.surfaceContainerHighest,
                              child: ConstrainedBox(
                                constraints: const BoxConstraints(
                                  maxWidth: 540,
                                  maxHeight: 240,
                                ),
                                child: ListView.separated(
                                  padding: EdgeInsets.zero,
                                  shrinkWrap: true,
                                  itemCount: options.length,
                                  separatorBuilder: (_, __) => Divider(
                                    height: 1,
                                    color: optionTheme.dividerColor,
                                  ),
                                  itemBuilder: (context, index) {
                                    final String username =
                                        options.elementAt(index);
                                    return ListTile(
                                      dense: true,
                                      leading: const Icon(Icons.person_outline),
                                      title: Text(username),
                                      onTap: () => onSelected(username),
                                    );
                                  },
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                      const SizedBox(height: 16),
                      TextFormField(
                        controller: passwordController,
                        focusNode: passwordFocus,
                        obscureText: obscurePassword,
                        onTap: onPasswordCapsLockChanged,
                        onChanged: (_) => onPasswordCapsLockChanged(),
                        onFieldSubmitted: (_) => onSubmit(),
                        autofillHints: const [AutofillHints.password],
                        decoration: InputDecoration(
                          labelText: 'Password',
                          prefixIcon: const Icon(Icons.lock_outline),
                          suffixIcon: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              if (capsLockOn && passwordFocus.hasFocus)
                                const Padding(
                                  padding: EdgeInsets.only(right: 4),
                                  child: Tooltip(
                                    message: 'Caps Lock is ON',
                                    child: Icon(
                                      Icons.warning_amber_rounded,
                                      size: 20,
                                    ),
                                  ),
                                ),
                              IconButton(
                                tooltip: obscurePassword
                                    ? 'Show password'
                                    : 'Hide password',
                                onPressed: onTogglePasswordVisibility,
                                icon: Icon(
                                  obscurePassword
                                      ? Icons.visibility_outlined
                                      : Icons.visibility_off_outlined,
                                ),
                              ),
                            ],
                          ),
                        ),
                        validator: (value) {
                          if (value == null || value.trim().isEmpty) {
                            return 'Enter your password.';
                          }
                          return null;
                        },
                      ),
                      if (capsLockOn && passwordFocus.hasFocus) ...[
                        const SizedBox(height: 8),
                        const _CapsLockNotice(),
                      ],
                      const SizedBox(height: 20),
                      _SignInOptions(
                        rememberUsername: rememberUsername,
                        rememberMe: rememberMe,
                        onRememberUsernameChanged: onUsernameRememberChanged,
                        onRememberMeChanged: onRememberMeChanged,
                      ),
                      const SizedBox(height: 24),
                      SizedBox(
                        height: 52,
                        child: FilledButton(
                          onPressed: isSubmitting ? null : onSubmit,
                          child: isSubmitting
                              ? const Row(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    SizedBox(
                                      height: 18,
                                      width: 18,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    ),
                                    SizedBox(width: 12),
                                    Text('Signing in...'),
                                  ],
                                )
                              : const Text('Sign in'),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Align(
                        alignment: Alignment.centerRight,
                        child: _SecondaryActionLink(
                          label: 'Forgot password?',
                          onTap: onShowPasswordHelp,
                        ),
                      ),
                      const SizedBox(height: 24),
                      const Divider(),
                      const SizedBox(height: 16),
                      _LoginFooter(
                        branding: branding,
                        showEnvironment: showEnvironment,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      );
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
          Image.file(logo, height: 80, fit: BoxFit.contain)
        else
          Icon(
            Icons.account_balance_outlined,
            size: 60,
            color: branding.loginAccentColor,
          ),
      ],
    );
  }
}

class _SignInOptions extends StatelessWidget {
  const _SignInOptions({
    required this.rememberUsername,
    required this.rememberMe,
    required this.onRememberUsernameChanged,
    required this.onRememberMeChanged,
  });

  final bool rememberUsername;
  final bool rememberMe;
  final ValueChanged<bool> onRememberUsernameChanged;
  final ValueChanged<bool> onRememberMeChanged;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceVariant.withOpacity(.28),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: theme.dividerColor.withOpacity(.5)),
      ),
      padding: const EdgeInsets.all(16),
      child: Material(
        color: Colors.transparent,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Sign-in Options', style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            CheckboxListTile(
              value: rememberUsername,
              onChanged: (value) => onRememberUsernameChanged(value ?? false),
              title: const Text('Remember username'),
              subtitle: const Text('Keeps the username on this device.'),
              contentPadding: EdgeInsets.zero,
              controlAffinity: ListTileControlAffinity.leading,
              dense: true,
              visualDensity: VisualDensity.compact,
            ),
            CheckboxListTile(
              value: rememberMe,
              onChanged: (value) => onRememberMeChanged(value ?? false),
              title: const Text('Remember me on this device'),
              subtitle: const Text(
                'Keeps a secure refresh token; never stores your password.',
              ),
              contentPadding: EdgeInsets.zero,
              controlAffinity: ListTileControlAffinity.leading,
              dense: true,
              visualDensity: VisualDensity.compact,
            ),
          ],
        ),
      ),
    );
  }
}

class _CapsLockNotice extends StatelessWidget {
  const _CapsLockNotice();

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Row(
      children: [
        Icon(Icons.warning_amber_rounded, size: 18, color: theme.colorScheme.error),
        const SizedBox(width: 8),
        Text(
          'Caps Lock is ON',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.error,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}

class _SecondaryActionLink extends StatefulWidget {
  const _SecondaryActionLink({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  State<_SecondaryActionLink> createState() => _SecondaryActionLinkState();
}

class _SecondaryActionLinkState extends State<_SecondaryActionLink> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: widget.onTap,
        child: Text(
          widget.label,
          style: theme.textTheme.labelLarge?.copyWith(
            color: theme.colorScheme.primary,
            decoration:
                _hovered ? TextDecoration.underline : TextDecoration.none,
          ),
        ),
      ),
    );
  }
}

class _LoginFooter extends StatelessWidget {
  const _LoginFooter({
    required this.branding,
    required this.showEnvironment,
  });

  final BrandingConfig branding;
  final bool showEnvironment;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final TextStyle? style = theme.textTheme.bodySmall;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Text(branding.appName, style: style),
        const SizedBox(height: 2),
        Text('Version ${branding.version}', style: style),
        const SizedBox(height: 2),
        Text('Build $_buildNumber', style: style),
        if (showEnvironment) ...[
          const SizedBox(height: 2),
          Text('Environment', style: style),
          const SizedBox(height: 2),
          Text('Development', style: style),
        ],
      ],
    );
  }
}

class _AboutBlock extends StatelessWidget {
  const _AboutBlock({
    required this.branding,
    required this.showEnvironment,
  });

  final BrandingConfig branding;
  final bool showEnvironment;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceVariant.withOpacity(.24),
        borderRadius: BorderRadius.circular(12),
      ),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('About', style: theme.textTheme.titleSmall),
          const SizedBox(height: 8),
          Text(branding.appName),
          Text('Version ${branding.version}'),
          Text('Build $_buildNumber'),
          if (showEnvironment) Text('Environment: Development'),
        ],
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({
    required this.onDismiss,
    this.message = 'Unable to sign in.\nCheck your username or password and try again.',
  });

  final VoidCallback onDismiss;
  final String message;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Semantics(
      liveRegion: true,
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: theme.colorScheme.errorContainer,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: theme.colorScheme.error.withOpacity(.25)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.error_outline, color: theme.colorScheme.error),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                message,
                style: TextStyle(color: theme.colorScheme.onErrorContainer),
              ),
            ),
            IconButton(
              tooltip: 'Dismiss',
              onPressed: onDismiss,
              icon: const Icon(Icons.close),
            ),
          ],
        ),
      ),
    );
  }
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

class _DismissErrorIntent extends Intent {
  const _DismissErrorIntent();
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
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        'Set a new password',
                        style: Theme.of(context).textTheme.headlineSmall,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Your ${widget.branding.companyName} administrator requires '
                        'a password change before continuing.',
                      ),
                      const SizedBox(height: 20),
                      if (widget.session.error != null) ...[
                        _ErrorBanner(message: widget.session.error!, onDismiss: () {}),
                        const SizedBox(height: 16),
                      ],
                      _passwordField(_current, 'Current password'),
                      const SizedBox(height: 12),
                      _passwordField(_next, 'New password'),
                      const SizedBox(height: 12),
                      _passwordField(
                        _confirmation,
                        'Confirm new password',
                        confirmation: true,
                      ),
                      const SizedBox(height: 24),
                      FilledButton(
                        onPressed: _submit,
                        child: const Text('Update password'),
                      ),
                    ],
                  ),
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
      unawaited(
        widget.session.completeInitialPasswordChange(_current.text, _next.text),
      );
    }
  }
}
