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
            (stored.recentUsernames.isNotEmpty
                ? stored.recentUsernames.first
                : '')
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

  bool get _isSubmitting =>
      widget.session.status == SessionStatus.authenticating;
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

  Future<void> _selectTheme(AppTheme theme) => widget.themes.select(theme);

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Scaffold(
      backgroundColor: widget.branding.loginBackgroundColor,
      body: SafeArea(
        child: Stack(
          children: [
            const Positioned.fill(child: _LoginBackdrop()),
            Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 12, 20, 8),
                  child: Row(
                    children: [
                      Icon(
                        Icons.account_balance_outlined,
                        color: theme.colorScheme.primary,
                        size: 28,
                      ),
                      const SizedBox(width: 10),
                      Text(
                        widget.branding.appName,
                        style: theme.textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const Spacer(),
                      _Toolbar(
                        children: [
                          _ThemeShortcutButton(
                            tooltip: 'Light Theme',
                            icon: Icons.light_mode_outlined,
                            onPressed: () =>
                                unawaited(_selectTheme(AppTheme.light)),
                          ),
                          _ThemeShortcutButton(
                            tooltip: 'Dark Theme',
                            icon: Icons.dark_mode_outlined,
                            onPressed: () =>
                                unawaited(_selectTheme(AppTheme.dark)),
                          ),
                          ThemeSelector(manager: widget.themes),
                          _ThemeShortcutButton(
                            tooltip: 'Application Settings',
                            icon: Icons.settings_outlined,
                            onPressed: _showApplicationSettings,
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: Center(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.fromLTRB(24, 10, 24, 16),
                      child: LayoutBuilder(
                        builder: (context, constraints) {
                          final bool wide = constraints.maxWidth >= 980;
                          final Widget intro = ConstrainedBox(
                            constraints: const BoxConstraints(maxWidth: 520),
                            child: _LoginIntroPanel(branding: widget.branding),
                          );
                          final Widget form = ConstrainedBox(
                            constraints: const BoxConstraints(maxWidth: 620),
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
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                intro,
                                const SizedBox(width: 24),
                                form,
                              ],
                            );
                          }
                          return Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              intro,
                              const SizedBox(height: 16),
                              form,
                            ],
                          );
                        },
                      ),
                    ),
                  ),
                ),
                _BottomStatusBar(
                  branding: widget.branding,
                  showEnvironment: _showEnvironment,
                ),
              ],
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
            theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.25),
            theme.colorScheme.surface,
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
        color: Theme.of(context).colorScheme.surface.withValues(alpha: 0.95),
        elevation: 4,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
          child: Row(mainAxisSize: MainAxisSize.min, children: children),
        ),
      );
}

class _ThemeShortcutButton extends StatelessWidget {
  const _ThemeShortcutButton({
    required this.tooltip,
    required this.icon,
    required this.onPressed,
  });

  final String tooltip;
  final IconData icon;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) => IconButton(
        tooltip: tooltip,
        visualDensity: VisualDensity.compact,
        onPressed: onPressed,
        icon: Icon(icon),
      );
}

class _LoginIntroPanel extends StatelessWidget {
  const _LoginIntroPanel({required this.branding});

  final BrandingConfig branding;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(30),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        color: theme.colorScheme.surface.withValues(alpha: 0.9),
        border: Border.all(color: theme.dividerColor.withValues(alpha: 0.35)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.06),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          _BrandMark(branding: branding),
          const SizedBox(height: 14),
          Text(
            branding.appName,
            style: theme.textTheme.displaySmall?.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Modern. Secure. Built for agencies.',
            style: theme.textTheme.titleMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 18),
          Container(
            width: 74,
            height: 4,
            decoration: BoxDecoration(
              color: theme.colorScheme.primary,
              borderRadius: BorderRadius.circular(12),
            ),
          ),
          const SizedBox(height: 22),
          const _IntroFeatureTile(
            icon: Icons.bolt_rounded,
            title: 'Fast access',
            body:
                'Quick sign-in with remembered usernames and smart session handling.',
          ),
          const SizedBox(height: 10),
          const _IntroFeatureTile(
            icon: Icons.shield_outlined,
            title: 'Secure by design',
            body:
                'Enterprise-grade security with role-based access and data protection.',
          ),
          const SizedBox(height: 10),
          const _IntroFeatureTile(
            icon: Icons.groups_2_outlined,
            title: 'Multi-firm ready',
            body: 'Seamlessly switch between firms without logging in again.',
          ),
          const SizedBox(height: 10),
          const _IntroFeatureTile(
            icon: Icons.corporate_fare_outlined,
            title: 'Designed for productivity',
            body: 'Clean interface, powerful workflows, better results.',
          ),
          const SizedBox(height: 20),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(14),
              color: theme.colorScheme.primaryContainer.withValues(alpha: 0.35),
            ),
            child: Row(
              children: [
                Icon(Icons.verified_user_outlined,
                    color: theme.colorScheme.primary),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Your data is protected. Your work stays yours.',
                    style: theme.textTheme.titleSmall,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _IntroFeatureTile extends StatelessWidget {
  const _IntroFeatureTile({
    required this.icon,
    required this.title,
    required this.body,
  });

  final IconData icon;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface.withValues(alpha: 0.84),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: theme.dividerColor.withValues(alpha: 0.35)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            height: 48,
            width: 48,
            decoration: BoxDecoration(
              color: theme.colorScheme.surfaceContainerHighest
                  .withValues(alpha: 0.6),
              borderRadius: BorderRadius.circular(12),
              border:
                  Border.all(color: theme.dividerColor.withValues(alpha: 0.45)),
            ),
            child: Icon(icon, color: theme.colorScheme.primary),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: theme.textTheme.titleLarge),
                const SizedBox(height: 4),
                Text(body, style: theme.textTheme.bodyMedium),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _BottomStatusBar extends StatelessWidget {
  const _BottomStatusBar({
    required this.branding,
    required this.showEnvironment,
  });

  final BrandingConfig branding;
  final bool showEnvironment;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final TextStyle? style = theme.textTheme.titleMedium?.copyWith(
      color: theme.colorScheme.onSurfaceVariant,
      fontWeight: FontWeight.w500,
    );
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(22, 10, 22, 14),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface.withValues(alpha: 0.65),
        border: Border(
            top: BorderSide(color: theme.dividerColor.withValues(alpha: 0.3))),
      ),
      child: Wrap(
        alignment: WrapAlignment.spaceBetween,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Wrap(
            spacing: 12,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text('Version ${branding.version}', style: style),
              Text('|', style: style),
              Text('Build $_buildNumber', style: style),
              if (showEnvironment) ...[
                Text('|', style: style),
                Text('Environment: Development', style: style),
              ],
            ],
          ),
          Wrap(
            spacing: 6,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Icon(Icons.language,
                  size: 20, color: theme.colorScheme.onSurfaceVariant),
              Text('English (India)', style: style),
              Icon(Icons.expand_more,
                  size: 18, color: theme.colorScheme.onSurfaceVariant),
            ],
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
      elevation: 10,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: theme.dividerColor.withValues(alpha: 0.25)),
        ),
        child: Padding(
          padding: const EdgeInsets.all(36),
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
                        'Welcome back',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.displaySmall?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 10),
                      Text(
                        'Sign in to continue to ${branding.appName}.',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.titleLarge?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
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
                            decoration: InputDecoration(
                              labelText: 'Username / Email',
                              helperText:
                                  'Supports username, email, and employee ID (future).',
                              prefixIcon: const Icon(Icons.person_outline),
                              suffixIcon:
                                  preferences.current.recentUsernames.isNotEmpty
                                      ? const Icon(Icons.expand_more)
                                      : null,
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
                              color: optionTheme
                                  .colorScheme.surfaceContainerHighest,
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
                        height: 54,
                        child: _PrimarySignInButton(
                          isSubmitting: isSubmitting,
                          onPressed: onSubmit,
                        ),
                      ),
                      const SizedBox(height: 14),
                      Row(
                        children: [
                          Expanded(child: Divider(color: theme.dividerColor)),
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 12),
                            child: Text(
                              'or',
                              style: theme.textTheme.titleMedium?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ),
                          Expanded(child: Divider(color: theme.dividerColor)),
                        ],
                      ),
                      const SizedBox(height: 24),
                      SizedBox(
                        height: 50,
                        child: OutlinedButton.icon(
                          onPressed: onShowPasswordHelp,
                          icon: const Icon(Icons.lock_outline),
                          label: const Text('Forgot password?'),
                        ),
                      ),
                      const SizedBox(height: 24),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            Icons.info_outline,
                            size: 18,
                            color: theme.colorScheme.primary,
                          ),
                          const SizedBox(width: 8),
                          Flexible(
                            child: Text(
                              'Need help? Contact your system administrator.',
                              textAlign: TextAlign.center,
                              style: theme.textTheme.bodyMedium,
                            ),
                          ),
                        ],
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
        color:
            theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.28),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: theme.dividerColor.withValues(alpha: 0.5)),
      ),
      padding: const EdgeInsets.all(18),
      child: Material(
        color: Colors.transparent,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Sign-in options',
              style: theme.textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 10),
            CheckboxListTile(
              value: rememberUsername,
              onChanged: (value) => onRememberUsernameChanged(value ?? false),
              title: const Text('Remember username'),
              subtitle: const Text('Prefill the username next time.'),
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
                'Keep me signed in securely on this device.',
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

class _PrimarySignInButton extends StatelessWidget {
  const _PrimarySignInButton({
    required this.isSubmitting,
    required this.onPressed,
  });

  final bool isSubmitting;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final BorderRadius borderRadius = BorderRadius.circular(14);
    return Material(
      color: Colors.transparent,
      child: Ink(
        decoration: BoxDecoration(
          borderRadius: borderRadius,
          gradient: LinearGradient(
            colors: [
              theme.colorScheme.primary,
              theme.colorScheme.primary.withValues(alpha: 0.86),
            ],
          ),
          boxShadow: [
            BoxShadow(
              color: theme.colorScheme.primary.withValues(alpha: 0.28),
              blurRadius: 14,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: InkWell(
          borderRadius: borderRadius,
          onTap: isSubmitting ? null : onPressed,
          child: Center(
            child: isSubmitting
                ? const Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      SizedBox(
                        height: 18,
                        width: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      ),
                      SizedBox(width: 12),
                      Text(
                        'Signing in...',
                        style: TextStyle(color: Colors.white),
                      ),
                    ],
                  )
                : const Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        'Sign in',
                        style: TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      SizedBox(width: 12),
                      Icon(Icons.arrow_forward, color: Colors.white),
                    ],
                  ),
          ),
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
        Icon(Icons.warning_amber_rounded,
            size: 18, color: theme.colorScheme.error),
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
        color:
            theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.24),
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
    this.message =
        'Unable to sign in.\nCheck your username or password and try again.',
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
          border: Border.all(
              color: theme.colorScheme.error.withValues(alpha: 0.25)),
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
                        _ErrorBanner(
                            message: widget.session.error!, onDismiss: () {}),
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
