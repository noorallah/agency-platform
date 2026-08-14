import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/auth/session_controller.dart';
import '../core/branding/branding_config.dart';
import '../core/design/design_tokens.dart';
import '../core/diagnostics/crash_reporter.dart';
import '../core/diagnostics/diagnostics_share.dart';
import '../core/preferences/desktop_preferences_service.dart';
import '../core/theme/theme_manager.dart';
import 'theme_selector.dart';

const String _buildNumber =
    String.fromEnvironment('BUILD_NUMBER', defaultValue: 'Unknown');

/// Below this the introduction panel is dropped rather than stacked above the
/// form. Stacking put marketing copy between the user and the password field,
/// which is the one thing a sign-in screen must never do.
const double _introBreakpoint = 1200;

/// Below this much room between the toolbar and the footer, the card sheds its
/// brand mark and outer margin rather than starting to scroll.
const double _tightHeight = 580;

/// `LOGIN_SCREEN_GUIDELINES.md` asks for 500-560; the form was built at 620.
const double _cardWidth = 520;
const double _introWidth = 420;

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

  Future<void> _selectMode(ThemeMode mode) => widget.themes.selectMode(mode);

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: widget.branding.loginBackgroundColor,
        body: SafeArea(
          child: Stack(
            children: [
              const Positioned.fill(child: _LoginBackdrop()),
              Column(
                children: [
                  _TopBar(
                    themes: widget.themes,
                    onSelectMode: _selectMode,
                    onShowSettings: _showApplicationSettings,
                  ),
                  Expanded(
                    child: LayoutBuilder(
                      builder: (context, constraints) {
                        final bool showIntro =
                            constraints.maxWidth >= _introBreakpoint;
                        // At the 960x640 window minimum the card is taller
                        // than the space between the toolbar and the footer.
                        // Decoration is what gives way first, not a control.
                        final bool tight = constraints.maxHeight < _tightHeight;
                        return Center(
                          // A safety net for a window shorter than the content,
                          // not the normal state: the screen is sized to fit
                          // from the 960x640 window minimum upwards.
                          child: SingleChildScrollView(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.xl,
                              vertical: tight ? AppSpacing.sm : AppSpacing.lg,
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              crossAxisAlignment: CrossAxisAlignment.center,
                              children: [
                                if (showIntro) ...[
                                  _LoginIntroPanel(branding: widget.branding),
                                  const SizedBox(width: AppSpacing.xxl),
                                ],
                                _buildCard(showBrandMark: !showIntro && !tight),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                  _LoginFooter(
                    branding: widget.branding,
                    showEnvironment: _showEnvironment,
                  ),
                ],
              ),
            ],
          ),
        ),
      );

  Widget _buildCard({required bool showBrandMark}) => _LoginCard(
        formKey: _formKey,
        branding: widget.branding,
        preferences: widget.preferences,
        showBrandMark: showBrandMark,
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
        onRememberMeChanged: (value) => setState(() => _rememberMe = value),
        onTogglePasswordVisibility: () => setState(() => _obscure = !_obscure),
        onSubmit: _submit,
        onShowPasswordHelp: _showForgotPassword,
        onPasswordCapsLockChanged: _syncCapsLockState,
      );

  Future<void> _showApplicationSettings() async {
    final TextEditingController apiUrl =
        TextEditingController(text: widget.session.baseUrl);
    String? error;
    ThemeMode selectedMode = widget.themes.mode;
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
                  DropdownButtonFormField<ThemeMode>(
                    initialValue: selectedMode,
                    decoration: const InputDecoration(labelText: 'Appearance'),
                    items: ThemeMode.values
                        .map(
                          (mode) => DropdownMenuItem(
                            value: mode,
                            child: Text(mode.label),
                          ),
                        )
                        .toList(),
                    onChanged: (value) {
                      if (value == null) return;
                      setDialogState(() => selectedMode = value);
                      unawaited(widget.themes.selectMode(value));
                    },
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  TextField(
                    controller: apiUrl,
                    keyboardType: TextInputType.url,
                    decoration: const InputDecoration(
                      labelText: 'API URL',
                      hintText: 'http://192.168.1.20:8000',
                      helperText:
                          'https:// anywhere, or http:// on your own network',
                      helperMaxLines: 2,
                    ),
                  ),
                  if (widget.preferences.current.recentServers.isNotEmpty) ...[
                    const SizedBox(height: AppSpacing.md),
                    DropdownButtonFormField<String>(
                      initialValue:
                          widget.preferences.current.recentServers.first,
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
                  const SizedBox(height: AppSpacing.lg),
                  InputDecorator(
                    decoration:
                        const InputDecoration(labelText: 'Language (future)'),
                    child: const Text('Coming soon'),
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  InputDecorator(
                    decoration: const InputDecoration(labelText: 'Font Size'),
                    child: const Text('Default'),
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  // Reachable before sign-in on purpose: a client that crashes
                  // at startup never reaches the main shell, and that is
                  // precisely when someone needs to send a report.
                  OutlinedButton.icon(
                    onPressed: () => DiagnosticsReportDialog.show(
                      dialogContext,
                      appName: widget.branding.appName,
                      version: widget.branding.version,
                      buildNumber: _buildNumber,
                      serverUrl: widget.session.baseUrl,
                    ),
                    icon: const Icon(Icons.bug_report_outlined),
                    label: const Text('Diagnostics report'),
                  ),
                  if (CrashReporter.previousSessionEndedUnexpectedly)
                    Padding(
                      padding: const EdgeInsets.only(top: AppSpacing.sm),
                      child: Text(
                        'The previous session ended unexpectedly.',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: Theme.of(context).colorScheme.error,
                            ),
                      ),
                    ),
                  const SizedBox(height: AppSpacing.lg),
                  _AboutBlock(
                    branding: widget.branding,
                    showEnvironment: _showEnvironment,
                  ),
                  if (error != null) ...[
                    const SizedBox(height: AppSpacing.lg),
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

/// A quiet wash behind the sign-in surfaces.
///
/// This used to also draw two 300px watermark icons at 4-5% opacity, which on a
/// light ground read as grey blocks floating off the right and bottom edges
/// rather than as texture. A gradient alone is the "very low opacity" the login
/// guidelines ask for.
class _LoginBackdrop extends StatelessWidget {
  const _LoginBackdrop();

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            colors.surface,
            colors.surfaceContainerHighest.withValues(alpha: 0.35),
            colors.surface,
          ],
        ),
      ),
    );
  }
}

/// Appearance and settings, right-aligned above the content.
///
/// The three theme-mode shortcuts that used to sit here duplicated the first
/// section of the Appearance menu exactly, so five controls did the work of
/// three. What is left is the one-click light/dark flip people actually use,
/// plus the full menu and application settings.
class _TopBar extends StatelessWidget {
  const _TopBar({
    required this.themes,
    required this.onSelectMode,
    required this.onShowSettings,
  });

  final ThemeManager themes;
  final Future<void> Function(ThemeMode mode) onSelectMode;
  final VoidCallback onShowSettings;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool isDark = theme.brightness == Brightness.dark;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.md,
        AppSpacing.lg,
        0,
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          _Toolbar(
            children: [
              IconButton(
                tooltip:
                    isDark ? 'Switch to light theme' : 'Switch to dark theme',
                visualDensity: VisualDensity.compact,
                onPressed: () => unawaited(
                  onSelectMode(isDark ? ThemeMode.light : ThemeMode.dark),
                ),
                icon: Icon(
                  isDark ? Icons.light_mode_outlined : Icons.dark_mode_outlined,
                ),
              ),
              ThemeSelector(manager: themes),
              IconButton(
                tooltip: 'Application Settings',
                visualDensity: VisualDensity.compact,
                onPressed: onShowSettings,
                icon: const Icon(Icons.settings_outlined),
              ),
            ],
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
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Material(
      color: colors.surfaceContainerLowest,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: AppRadius.medium,
        side: BorderSide(color: colors.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.xs,
          vertical: AppSpacing.xs / 2,
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: children),
      ),
    );
  }
}

/// The brand half of the wide layout.
///
/// Trimmed from four bordered tiles plus a reassurance badge to three plain
/// rows: the tiles were cards inside a card inside a card, and together with the
/// badge they made this column taller than a 1080p viewport on its own.
class _LoginIntroPanel extends StatelessWidget {
  const _LoginIntroPanel({required this.branding});

  final BrandingConfig branding;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: _introWidth),
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.xl),
        decoration: BoxDecoration(
          borderRadius: AppRadius.large,
          color: theme.colorScheme.surfaceContainerLowest.withValues(
            alpha: 0.72,
          ),
          border: Border.all(color: theme.colorScheme.outlineVariant),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            _BrandMark(branding: branding, size: 44),
            const SizedBox(height: AppSpacing.md),
            Text(branding.appName, style: theme.textTheme.headlineMedium),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'Modern. Secure. Built for agencies.',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
            Container(
              width: 56,
              height: 3,
              decoration: BoxDecoration(
                color: theme.colorScheme.primary,
                borderRadius: AppRadius.small,
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
            const _IntroFeatureRow(
              icon: Icons.bolt_rounded,
              title: 'Fast access',
              body: 'Remembered usernames and quick session handling.',
            ),
            const SizedBox(height: AppSpacing.md),
            const _IntroFeatureRow(
              icon: Icons.shield_outlined,
              title: 'Secure by design',
              body: 'Role-based access with enterprise-grade protection.',
            ),
            const SizedBox(height: AppSpacing.md),
            const _IntroFeatureRow(
              icon: Icons.groups_2_outlined,
              title: 'Multi-firm ready',
              body: 'Switch between firms without signing in again.',
            ),
          ],
        ),
      ),
    );
  }
}

class _IntroFeatureRow extends StatelessWidget {
  const _IntroFeatureRow({
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
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 20, color: theme.colorScheme.primary),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: theme.textTheme.titleSmall),
              const SizedBox(height: 2),
              Text(body, style: theme.textTheme.bodySmall),
            ],
          ),
        ),
      ],
    );
  }
}

/// Version metadata, styled to match the shell's `ApplicationStatusBar`.
///
/// `ApplicationStatusBar` itself is not used here because it always renders the
/// API and database connection indicators, and before sign-in neither has been
/// probed -- they would sit at "checking" forever.
class _LoginFooter extends StatelessWidget {
  const _LoginFooter({
    required this.branding,
    required this.showEnvironment,
  });

  final BrandingConfig branding;
  final bool showEnvironment;

  @override
  Widget build(BuildContext context) => Material(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        child: SizedBox(
          height: 32,
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
              child: Row(
                children: [
                  _FooterItem(
                    icon: Icons.info_outline,
                    label: '${branding.appName} ${branding.version}',
                  ),
                  _FooterItem(
                    icon: Icons.tag_outlined,
                    label: 'Build $_buildNumber',
                  ),
                  if (showEnvironment)
                    const _FooterItem(
                      icon: Icons.dns_outlined,
                      label: 'Development',
                    ),
                ],
              ),
            ),
          ),
        ),
      );
}

class _FooterItem extends StatelessWidget {
  const _FooterItem({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(right: AppSpacing.lg),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon,
                size: 14,
                color: Theme.of(context).colorScheme.onSurfaceVariant),
            const SizedBox(width: AppSpacing.xs),
            Text(label, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      );
}

class _LoginCard extends StatelessWidget {
  const _LoginCard({
    required this.formKey,
    required this.branding,
    required this.preferences,
    required this.showBrandMark,
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

  /// Carried by the card only when the introduction panel is hidden, so the
  /// brand appears exactly once at every width.
  final bool showBrandMark;
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
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: _cardWidth),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.xl),
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
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (showBrandMark) ...[
                        Center(child: _BrandMark(branding: branding, size: 36)),
                        const SizedBox(height: AppSpacing.md),
                      ],
                      Text(
                        'Welcome back',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.headlineMedium,
                      ),
                      const SizedBox(height: AppSpacing.xs),
                      Text(
                        'Sign in to continue to ${branding.appName}.',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                      if (error != null && errorVisible) ...[
                        const SizedBox(height: AppSpacing.lg),
                        _ErrorBanner(
                            message: error!, onDismiss: onDismissError),
                      ],
                      if (notice != null) ...[
                        const SizedBox(height: AppSpacing.lg),
                        _NoticeBanner(message: notice!),
                      ],
                      const SizedBox(height: AppSpacing.xl),
                      _UsernameField(
                        controller: usernameController,
                        focusNode: usernameFocus,
                        preferences: preferences,
                        onSelected: onUsernameSelected,
                      ),
                      const SizedBox(height: AppSpacing.md),
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
                          suffixIcon: IconButton(
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
                        ),
                        validator: (value) {
                          if (value == null || value.trim().isEmpty) {
                            return 'Enter your password.';
                          }
                          return null;
                        },
                      ),
                      if (capsLockOn && passwordFocus.hasFocus) ...[
                        const SizedBox(height: AppSpacing.sm),
                        const _CapsLockNotice(),
                      ],
                      const SizedBox(height: AppSpacing.xs),
                      Align(
                        alignment: Alignment.centerRight,
                        child: TextButton(
                          onPressed: onShowPasswordHelp,
                          child: const Text('Forgot password?'),
                        ),
                      ),
                      const SizedBox(height: AppSpacing.sm),
                      _SignInOptions(
                        rememberUsername: rememberUsername,
                        rememberMe: rememberMe,
                        onRememberUsernameChanged: onUsernameRememberChanged,
                        onRememberMeChanged: onRememberMeChanged,
                      ),
                      const SizedBox(height: AppSpacing.lg),
                      _PrimarySignInButton(
                        isSubmitting: isSubmitting,
                        onPressed: onSubmit,
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

/// The username field with its remembered-username suggestions.
///
/// The permanent helper line -- "Supports username, email, and employee ID
/// (future)" -- is gone: the label already says Username / Email, and the rest
/// advertised a capability that does not exist while reserving a row of height
/// on every render.
class _UsernameField extends StatelessWidget {
  const _UsernameField({
    required this.controller,
    required this.focusNode,
    required this.preferences,
    required this.onSelected,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final DesktopPreferencesService preferences;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) => RawAutocomplete<String>(
        textEditingController: controller,
        focusNode: focusNode,
        optionsBuilder: (TextEditingValue textEditingValue) {
          final List<String> usernames = preferences.current.recentUsernames;
          final String query = textEditingValue.text.trim().toLowerCase();
          if (usernames.isEmpty) {
            return const Iterable<String>.empty();
          }
          if (query.isEmpty) {
            return usernames.take(6);
          }
          return usernames
              .where((username) => username.toLowerCase().contains(query))
              .take(6);
        },
        displayStringForOption: (value) => value,
        onSelected: onSelected,
        fieldViewBuilder: (context, field, node, onFieldSubmitted) =>
            TextFormField(
          controller: field,
          focusNode: node,
          autofocus: true,
          textInputAction: TextInputAction.next,
          keyboardType: TextInputType.text,
          autofillHints: const [
            AutofillHints.username,
            AutofillHints.email,
          ],
          decoration: InputDecoration(
            labelText: 'Username / Email',
            prefixIcon: const Icon(Icons.person_outline),
            suffixIcon: preferences.current.recentUsernames.isNotEmpty
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
        ),
        optionsViewBuilder: (context, onOptionSelected, options) {
          final ThemeData theme = Theme.of(context);
          return Align(
            alignment: Alignment.topLeft,
            child: Material(
              elevation: 4,
              borderRadius: AppRadius.medium,
              color: theme.colorScheme.surfaceContainerLowest,
              child: ConstrainedBox(
                constraints: const BoxConstraints(
                  maxWidth: _cardWidth,
                  maxHeight: 240,
                ),
                child: ListView.separated(
                  padding: EdgeInsets.zero,
                  shrinkWrap: true,
                  itemCount: options.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, index) {
                    final String username = options.elementAt(index);
                    return ListTile(
                      dense: true,
                      leading: const Icon(Icons.person_outline),
                      title: Text(username),
                      onTap: () => onOptionSelected(username),
                    );
                  },
                ),
              ),
            ),
          );
        },
      );
}

class _BrandMark extends StatelessWidget {
  const _BrandMark({required this.branding, required this.size});

  final BrandingConfig branding;
  final double size;

  @override
  Widget build(BuildContext context) {
    final File? logo = branding.logoFile;
    if (logo != null) {
      return Image.file(logo, height: size, fit: BoxFit.contain);
    }
    return Icon(
      Icons.account_balance_outlined,
      size: size,
      color: branding.loginAccentColor,
    );
  }
}

/// The two remembering choices.
///
/// The bordered panel around them is gone, and so are the subtitles that
/// restated each label in a second sentence. The labels now say what the option
/// does, which is what the subtitles were there to explain. Hit targets are
/// left at full size deliberately -- the login guidelines ask for larger
/// targets here, so this is the one place that does not take the app's compact
/// list density.
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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Sign-in options', style: theme.textTheme.labelMedium),
        const SizedBox(height: AppSpacing.xs),
        CheckboxListTile(
          value: rememberUsername,
          onChanged: (value) => onRememberUsernameChanged(value ?? false),
          title: const Text('Remember my username'),
          contentPadding: EdgeInsets.zero,
          controlAffinity: ListTileControlAffinity.leading,
        ),
        CheckboxListTile(
          value: rememberMe,
          onChanged: (value) => onRememberMeChanged(value ?? false),
          title: const Text('Keep me signed in on this device'),
          contentPadding: EdgeInsets.zero,
          controlAffinity: ListTileControlAffinity.leading,
        ),
      ],
    );
  }
}

/// The primary action.
///
/// This was a hand-built `Ink`/`InkWell` with a gradient and `Colors.white`
/// text. That gave it no focus ring, no keyboard activation, no disabled
/// appearance, and a label that assumed white is always legible on the primary
/// colour -- which the high-contrast and green palettes do not guarantee. A
/// `FilledButton` carries all of that from the theme; the only override is to
/// keep it looking like the primary action while it is disabled mid-submit,
/// rather than greying out under the user's cursor.
class _PrimarySignInButton extends StatelessWidget {
  const _PrimarySignInButton({
    required this.isSubmitting,
    required this.onPressed,
  });

  final bool isSubmitting;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return FilledButton(
      onPressed: isSubmitting ? null : onPressed,
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(48),
        disabledBackgroundColor: colors.primary.withValues(alpha: 0.6),
        disabledForegroundColor: colors.onPrimary,
      ),
      child: isSubmitting
          ? Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                SizedBox(
                  height: 16,
                  width: 16,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: colors.onPrimary,
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                const Text('Signing in...'),
              ],
            )
          : const Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text('Sign in'),
                SizedBox(width: AppSpacing.sm),
                Icon(Icons.arrow_forward, size: 18),
              ],
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
        Icon(
          Icons.warning_amber_rounded,
          size: 18,
          color: context.semanticColors.warning,
        ),
        const SizedBox(width: AppSpacing.sm),
        Text(
          'Caps Lock is ON',
          style: theme.textTheme.bodySmall?.copyWith(
            color: context.semanticColors.warning,
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
        borderRadius: AppRadius.medium,
      ),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('About', style: theme.textTheme.titleSmall),
          const SizedBox(height: AppSpacing.sm),
          Text(branding.appName),
          Text('Version ${branding.version}'),
          Text('Build $_buildNumber'),
          if (showEnvironment) const Text('Environment: Development'),
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
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.md,
          AppSpacing.sm,
          AppSpacing.sm,
          AppSpacing.sm,
        ),
        decoration: BoxDecoration(
          color: theme.colorScheme.errorContainer,
          borderRadius: AppRadius.medium,
          border: Border.all(
              color: theme.colorScheme.error.withValues(alpha: 0.25)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Icon(Icons.error_outline, color: theme.colorScheme.error),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
                child: Text(
                  message,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: theme.colorScheme.onErrorContainer,
                  ),
                ),
              ),
            ),
            IconButton(
              tooltip: 'Dismiss',
              visualDensity: VisualDensity.compact,
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
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: theme.colorScheme.primaryContainer,
        borderRadius: AppRadius.medium,
      ),
      child: Text(
        message,
        style: theme.textTheme.bodyMedium?.copyWith(
          color: theme.colorScheme.onPrimaryContainer,
        ),
      ),
    );
  }
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
                padding: const EdgeInsets.all(AppSpacing.xxl),
                child: Form(
                  key: _formKey,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        'Set a new password',
                        style: Theme.of(context).textTheme.headlineSmall,
                      ),
                      const SizedBox(height: AppSpacing.sm),
                      Text(
                        'Your ${widget.branding.companyName} administrator requires '
                        'a password change before continuing.',
                      ),
                      const SizedBox(height: AppSpacing.xl),
                      if (widget.session.error != null) ...[
                        _ErrorBanner(
                            message: widget.session.error!, onDismiss: () {}),
                        const SizedBox(height: AppSpacing.lg),
                      ],
                      _passwordField(_current, 'Current password'),
                      const SizedBox(height: AppSpacing.md),
                      _passwordField(_next, 'New password'),
                      const SizedBox(height: AppSpacing.md),
                      _passwordField(
                        _confirmation,
                        'Confirm new password',
                        confirmation: true,
                      ),
                      const SizedBox(height: AppSpacing.xl),
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
