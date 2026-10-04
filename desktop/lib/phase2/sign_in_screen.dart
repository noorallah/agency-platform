import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:window_manager/window_manager.dart';

import '../core/auth/session_controller.dart';
import '../core/branding/agency_branding_cache.dart';
import '../core/branding/branding_config.dart';
import '../core/design/design_tokens.dart';
import '../core/preferences/desktop_preferences_service.dart';
import '../core/theme/theme_manager.dart';
import '../models/agency_branding.dart';
import '../ui/auth_screens.dart';

/// Below this the showcase is dropped and the card stands alone.
const double _showcaseBreakpoint = 900;

const double _cardWidth = 440;

/// The strengths move on this often until the user starts to type.
const Duration _cycleEvery = Duration(seconds: 8);

enum _ServerState { checking, answers, silent }

/// The phase 2 sign-in: a night-blue showcase of the product's strengths on
/// the left, the sign-in card on the right (docs/BRANDING_AND_NAMES.md, option
/// S2 of the sign-in wireframes).
///
/// The form is the standard [LoginScreen]'s own -- every behaviour of it --
/// placed by [LoginScreen.layoutBuilder]; what is new is only what surrounds
/// it. The screen asks the server for the agency's branding **once** when it
/// opens: one `GET /api/v1/branding`, and one `GET /api/v1/branding/logo` only
/// when the agency has a logo that is not already cached. It never polls.
class Phase2SignInScreen extends StatefulWidget {
  const Phase2SignInScreen({
    super.key,
    required this.session,
    required this.preferences,
    required this.branding,
    required this.themes,
    this.error,
    this.notice,
    this.lockedUntil,
    this.capsLockEnabled,
    this.loadBranding,
    this.loadLogo,
    this.cache,
    this.computerName,
    this.cycleEvery = _cycleEvery,
    this.setWindowTitle = true,
  });

  final SessionController session;
  final DesktopPreferencesService preferences;
  final BrandingConfig branding;
  final ThemeManager themes;
  final String? error;
  final String? notice;
  final DateTime? lockedUntil;
  final bool Function()? capsLockEnabled;

  /// Replace the server calls, for tests. The defaults use the session's own
  /// client.
  final Future<AgencyBranding> Function()? loadBranding;
  final Future<Uint8List?> Function()? loadLogo;
  final AgencyBrandingCache? cache;

  /// This PC's name for "Copy details for support"; the real one by default.
  final String? computerName;
  final Duration cycleEvery;

  /// Title the window "Product - Sign in" while this screen is open.
  final bool setWindowTitle;

  @override
  State<Phase2SignInScreen> createState() => _Phase2SignInScreenState();
}

class _Phase2SignInScreenState extends State<Phase2SignInScreen> {
  late final AgencyBrandingCache _cache = widget.cache ?? AgencyBrandingCache();
  AgencyBranding _agency = AgencyBranding.notSet;
  Uint8List? _logo;
  _ServerState _server = _ServerState.checking;
  late final String _serverAtOpen = widget.session.baseUrl;

  @override
  void initState() {
    super.initState();
    final CachedAgencyBranding? cached = _cache.readSync(_serverAtOpen);
    if (cached != null) {
      _agency = cached.branding;
      _logo = cached.logo;
    }
    unawaited(_refresh());
    if (widget.setWindowTitle) {
      unawaited(_titleWindow('${widget.branding.productName} - Sign in'));
    }
  }

  @override
  void dispose() {
    if (widget.setWindowTitle) {
      unawaited(_titleWindow(widget.branding.windowName));
    }
    super.dispose();
  }

  /// Best effort: there is no window to title in a test or on a phone.
  Future<void> _titleWindow(String title) async {
    try {
      await windowManager.setTitle(title);
    } on Object {
      // Nothing to title.
    }
  }

  Future<void> _refresh() async {
    try {
      final AgencyBranding fresh = await (widget.loadBranding ??
          widget.session.api.getBranding)();
      Uint8List? logo = _logo;
      if (fresh.isSet && fresh.hasLogo) {
        final bool unchanged = logo != null &&
            _agency.isSet &&
            _agency.version != null &&
            _agency.version == fresh.version;
        if (!unchanged) {
          logo = await (widget.loadLogo ?? widget.session.api.getBrandingLogo)();
        }
      } else {
        logo = null;
      }
      unawaited(_cache.write(_serverAtOpen, fresh, logo));
      if (!mounted) return;
      setState(() {
        _agency = fresh;
        _logo = logo;
        _server = _ServerState.answers;
      });
    } on Object {
      // The package's own identity (or the cached one) stays.
      if (mounted) setState(() => _server = _ServerState.silent);
    }
  }

  bool get _fromServer => _agency.isSet && _agency.agencyName.isNotEmpty;

  String get _agencyName =>
      _fromServer ? _agency.agencyName : widget.branding.appName;

  String get _agencyTagline => _fromServer ? _agency.tagline : '';

  String get _serverHost {
    final Uri? uri = Uri.tryParse(widget.session.baseUrl);
    return uri != null && uri.hasAuthority ? uri.authority : widget.session.baseUrl;
  }

  @override
  Widget build(BuildContext context) => LoginScreen(
        session: widget.session,
        preferences: widget.preferences,
        branding: widget.branding,
        themes: widget.themes,
        error: widget.error,
        notice: widget.notice,
        lockedUntil: widget.lockedUntil,
        capsLockEnabled: widget.capsLockEnabled,
        cardMaxWidth: _cardWidth,
        cardHeader: _AgencyHead(
          name: _agencyName,
          tagline: _agencyTagline,
          logo: _logo,
          logoFile: widget.branding.logoFile,
        ),
        cardFooter: _ProductFoot(branding: widget.branding),
        layoutBuilder: _layout,
      );

  Widget _layout(BuildContext context, LoginScreenParts parts) {
    final ThemeData theme = Theme.of(context);
    return Scaffold(
      backgroundColor: theme.colorScheme.surface,
      body: SafeArea(
        child: Column(
          children: [
            _TopBar(
              name: _agencyName,
              tagline: _agencyTagline,
              logo: _logo,
              logoFile: widget.branding.logoFile,
              onSettings: parts.openSettings,
            ),
            Expanded(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final Widget right = _Right(
                    card: parts.card,
                    branding: widget.branding,
                    serverUrl: widget.session.baseUrl,
                    computerName:
                        widget.computerName ?? Platform.localHostname,
                  );
                  if (constraints.maxWidth < _showcaseBreakpoint) {
                    return right;
                  }
                  return Row(
                    children: [
                      Expanded(
                        flex: 115,
                        child: _Showcase(
                          branding: widget.branding,
                          typed: parts.typed,
                          interval: widget.cycleEvery,
                        ),
                      ),
                      Expanded(flex: 100, child: right),
                    ],
                  );
                },
              ),
            ),
            _StatusBar(
              branding: widget.branding,
              host: _serverHost,
              server: _server,
            ),
          ],
        ),
      ),
    );
  }
}

/// The agency's logo, or its logo file from the package, or its initials.
class _AgencyMark extends StatelessWidget {
  const _AgencyMark({
    required this.name,
    required this.logo,
    required this.logoFile,
    required this.size,
  });

  final String name;
  final Uint8List? logo;
  final File? logoFile;
  final double size;

  static String initials(String name) {
    final List<String> words = name
        .split(RegExp(r'\s+'))
        .where((String word) => word.isNotEmpty)
        .toList();
    if (words.isEmpty) return '?';
    final String first = String.fromCharCode(words.first.runes.first);
    if (words.length == 1) return first.toUpperCase();
    return (first + String.fromCharCode(words[1].runes.first)).toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    final Widget square = Container(
      key: const ValueKey<String>('agency-initials'),
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: colors.primary,
        borderRadius: BorderRadius.circular(size / 5),
      ),
      child: Text(
        initials(name),
        style: TextStyle(
          color: colors.onPrimary,
          fontWeight: FontWeight.w700,
          fontSize: size * 0.38,
        ),
      ),
    );
    final Uint8List? bytes = logo;
    if (bytes != null) {
      return Image.memory(
        bytes,
        height: size,
        fit: BoxFit.contain,
        errorBuilder: (_, __, ___) => square,
      );
    }
    final File? file = logoFile;
    if (file != null) {
      return Image.file(
        file,
        height: size,
        fit: BoxFit.contain,
        errorBuilder: (_, __, ___) => square,
      );
    }
    return square;
  }
}

/// The dark bar: the agency's mark and name on the left, settings on the right.
class _TopBar extends StatelessWidget {
  const _TopBar({
    required this.name,
    required this.tagline,
    required this.logo,
    required this.logoFile,
    required this.onSettings,
  });

  final String name;
  final String tagline;
  final Uint8List? logo;
  final File? logoFile;
  final VoidCallback onSettings;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final AppSemanticColors colors = context.semanticColors;
    return Material(
      color: colors.chrome,
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg,
          vertical: AppSpacing.sm,
        ),
        child: Row(
          children: [
            _AgencyMark(
              name: name,
              logo: logo,
              logoFile: logoFile,
              size: 30,
            ),
            const SizedBox(width: AppSpacing.md),
            Flexible(
              child: Text(
                name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.titleMedium?.copyWith(
                  color: colors.onChrome,
                ),
              ),
            ),
            if (tagline.isNotEmpty) ...[
              const SizedBox(width: AppSpacing.md),
              Flexible(
                child: Text(
                  tagline,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: colors.onChromeMuted,
                  ),
                ),
              ),
            ],
            const Spacer(),
            TextButton.icon(
              onPressed: onSettings,
              style: TextButton.styleFrom(foregroundColor: colors.onChrome),
              icon: const Icon(Icons.settings_outlined, size: 18),
              label: const Text('Application Settings'),
            ),
          ],
        ),
      ),
    );
  }
}

/// The card's head: the agency's mark, name and tagline.
class _AgencyHead extends StatelessWidget {
  const _AgencyHead({
    required this.name,
    required this.tagline,
    required this.logo,
    required this.logoFile,
  });

  final String name;
  final String tagline;
  final Uint8List? logo;
  final File? logoFile;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Row(
      children: [
        _AgencyMark(name: name, logo: logo, logoFile: logoFile, size: 40),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                name,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.titleLarge,
              ),
              if (tagline.isNotEmpty)
                Text(
                  tagline,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}

/// The product's own logo, or a small neutral placeholder.
class _ProductMark extends StatelessWidget {
  const _ProductMark({required this.branding, required this.size});

  final BrandingConfig branding;
  final double size;

  @override
  Widget build(BuildContext context) {
    final File? file = branding.productLogoFile;
    final Widget placeholder = Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(size / 4.5),
        border: Border.all(
          color: Theme.of(context).colorScheme.outline,
        ),
      ),
      child: Icon(Icons.inventory_2_outlined, size: size * 0.6),
    );
    if (file == null) return placeholder;
    return Image.file(
      file,
      height: size,
      width: size,
      fit: BoxFit.contain,
      errorBuilder: (_, __, ___) => placeholder,
    );
  }
}

/// The foot of the card: the product, who makes it, and its tagline.
class _ProductFoot extends StatelessWidget {
  const _ProductFoot({required this.branding});

  final BrandingConfig branding;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final TextStyle? muted = theme.textTheme.bodySmall?.copyWith(
      color: theme.colorScheme.onSurfaceVariant,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        const Divider(height: 1),
        const SizedBox(height: AppSpacing.md),
        Row(
          children: [
            _ProductMark(branding: branding, size: 24),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Wrap(
                spacing: AppSpacing.xs,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  Text(
                    branding.productName,
                    style: theme.textTheme.titleSmall,
                  ),
                  Text('by ${branding.companyName}', style: muted),
                ],
              ),
            ),
          ],
        ),
        if (branding.tagline.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.xs),
          Text(branding.tagline, style: muted),
        ],
      ],
    );
  }
}

/// The right half: the card, and one line of help under it.
class _Right extends StatelessWidget {
  const _Right({
    required this.card,
    required this.branding,
    required this.serverUrl,
    required this.computerName,
  });

  final Widget card;
  final BrandingConfig branding;
  final String serverUrl;
  final String computerName;

  @override
  Widget build(BuildContext context) => Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: _cardWidth),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: [
                card,
                const SizedBox(height: AppSpacing.md),
                _MoreHelp(
                  branding: branding,
                  serverUrl: serverUrl,
                  computerName: computerName,
                ),
              ],
            ),
          ),
        ),
      );
}

/// One line of help that opens into the support details.
///
/// Every row is hidden while its value is empty -- they all are until the
/// package's `branding.json` gives them -- and what is always there is the
/// password line and the button that copies what support will ask for.
class _MoreHelp extends StatefulWidget {
  const _MoreHelp({
    required this.branding,
    required this.serverUrl,
    required this.computerName,
  });

  final BrandingConfig branding;
  final String serverUrl;
  final String computerName;

  @override
  State<_MoreHelp> createState() => _MoreHelpState();
}

class _MoreHelpState extends State<_MoreHelp> {
  bool _open = false;

  String get _summary {
    final BrandingConfig b = widget.branding;
    final List<String> given = <String>[
      if (b.supportPhone.isNotEmpty) b.supportPhone,
      if (b.supportEmail.isNotEmpty) b.supportEmail,
    ];
    return given.isEmpty
        ? 'Passwords, and what support will ask for'
        : given.join('  -  ');
  }

  Future<void> _copy() async {
    final String text = <String>[
      '${widget.branding.productName} support details',
      'Version: ${widget.branding.version}',
      'Server: ${widget.serverUrl}',
      'Computer: ${widget.computerName}',
    ].join('\n');
    await Clipboard.setData(ClipboardData(text: text));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Details for support copied.')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final BrandingConfig b = widget.branding;
    final TextStyle? muted = theme.textTheme.bodySmall?.copyWith(
      color: theme.colorScheme.onSurfaceVariant,
    );
    final List<(IconData, String, String?)> rows = <(IconData, String, String?)>[
      if (b.supportPhone.isNotEmpty)
        (
          Icons.phone_outlined,
          b.supportPhone,
          <String>[
            if (b.supportWhatsapp.isNotEmpty)
              'WhatsApp ${b.supportWhatsapp}'
            else
              'Call or WhatsApp',
            if (b.supportHours.isNotEmpty) b.supportHours,
          ].join('  -  '),
        ),
      if (b.supportEmail.isNotEmpty)
        (Icons.mail_outline, b.supportEmail, null),
      if (b.supportWebsite.isNotEmpty)
        (Icons.language_outlined, b.supportWebsite, null),
    ];
    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerLowest,
        borderRadius: AppRadius.medium,
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          InkWell(
            onTap: () => setState(() => _open = !_open),
            borderRadius: AppRadius.small,
            child: Row(
              children: [
                Icon(Icons.help_outline, color: theme.colorScheme.primary),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Need help?', style: theme.textTheme.titleSmall),
                      Text(
                        _summary,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: muted,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Text(
                  'More help',
                  style: theme.textTheme.labelLarge?.copyWith(
                    color: theme.colorScheme.primary,
                  ),
                ),
                Icon(
                  _open ? Icons.expand_less : Icons.chevron_right,
                  size: 18,
                  color: theme.colorScheme.primary,
                ),
              ],
            ),
          ),
          if (_open) ...[
            const SizedBox(height: AppSpacing.md),
            for (final (IconData, String, String?) row in rows)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(row.$1, size: 18),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(row.$2, style: theme.textTheme.titleSmall),
                          if (row.$3 != null && row.$3!.isNotEmpty)
                            Text(row.$3!, style: muted),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            Text(
              'Forgot your password? Your administrator resets it.',
              style: muted,
            ),
            const SizedBox(height: AppSpacing.md),
            OutlinedButton.icon(
              onPressed: _copy,
              icon: const Icon(Icons.copy_outlined, size: 18),
              label: const Text('Copy details for support'),
            ),
          ],
        ],
      ),
    );
  }
}

/// The night-blue half: the product, then one strength at a time.
///
/// Moves on every [interval] and stops for good the moment the user types.
/// With nothing in `strengths` there is no carousel -- only the product.
class _Showcase extends StatefulWidget {
  const _Showcase({
    required this.branding,
    required this.typed,
    required this.interval,
  });

  final BrandingConfig branding;
  final ValueListenable<bool> typed;
  final Duration interval;

  @override
  State<_Showcase> createState() => _ShowcaseState();
}

class _ShowcaseState extends State<_Showcase> {
  int _index = 0;
  Timer? _timer;

  List<BrandingStrength> get _slides => widget.branding.strengths;

  @override
  void initState() {
    super.initState();
    widget.typed.addListener(_onTyped);
    if (!widget.typed.value) _startCycling();
  }

  @override
  void dispose() {
    widget.typed.removeListener(_onTyped);
    _timer?.cancel();
    super.dispose();
  }

  void _startCycling() {
    _timer?.cancel();
    _timer = null;
    if (_slides.length < 2) return;
    _timer = Timer.periodic(widget.interval, (_) => _step(1, manual: false));
  }

  void _onTyped() {
    if (!widget.typed.value) return;
    _timer?.cancel();
    setState(() => _timer = null);
  }

  void _step(int by, {required bool manual}) {
    if (!mounted || _slides.isEmpty) return;
    setState(() => _index = (_index + by) % _slides.length);
    if (manual && _timer != null) _startCycling();
  }

  void _go(int to) {
    setState(() => _index = to);
    if (_timer != null) _startCycling();
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final AppSemanticColors colors = context.semanticColors;
    final bool still = MediaQuery.disableAnimationsOf(context);
    final List<BrandingStrength> slides = _slides;
    final int at = slides.isEmpty ? 0 : _index % slides.length;
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [colors.chrome, colors.chromeActive],
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.xxl,
          AppSpacing.xl,
          AppSpacing.xxl,
          AppSpacing.lg,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                _ProductMark(branding: widget.branding, size: 32),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        widget.branding.productName,
                        style: theme.textTheme.titleMedium?.copyWith(
                          color: colors.onChrome,
                        ),
                      ),
                      if (widget.branding.tagline.isNotEmpty)
                        Text(
                          widget.branding.tagline,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: colors.onChromeMuted,
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
            if (slides.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.lg),
              Expanded(
                child: ClipRect(
                  child: AnimatedSwitcher(
                    duration:
                        still ? Duration.zero : const Duration(milliseconds: 400),
                    child: SingleChildScrollView(
                      key: ValueKey<int>(at),
                      child: _Slide(strength: slides[at], index: at, of: slides.length),
                    ),
                  ),
                ),
              ),
              if (slides.length > 1)
                _SlideNav(
                  index: at,
                  count: slides.length,
                  titles: [for (final BrandingStrength s in slides) s.title],
                  cycling: _timer != null,
                  interval: widget.interval,
                  onStep: (int by) => _step(by, manual: true),
                  onGo: _go,
                ),
            ] else
              const Spacer(),
          ],
        ),
      ),
    );
  }
}

class _Slide extends StatelessWidget {
  const _Slide({required this.strength, required this.index, required this.of});

  final BrandingStrength strength;
  final int index;
  final int of;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final AppSemanticColors colors = context.semanticColors;
    final TextStyle? body = theme.textTheme.bodyMedium?.copyWith(
      color: colors.onChromeMuted,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (strength.kicker.isNotEmpty)
          Text(
            '${strength.kicker.toUpperCase()}  -  ${index + 1} OF $of',
            style: theme.textTheme.labelMedium?.copyWith(
              color: colors.chromeIndicator,
              letterSpacing: 1.2,
            ),
          ),
        const SizedBox(height: AppSpacing.sm),
        Text(
          strength.headline,
          style: theme.textTheme.headlineMedium?.copyWith(
            color: colors.onChrome,
          ),
        ),
        if (strength.text.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.md),
          Text(strength.text, style: body),
        ],
        if (strength.points.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.md),
          for (final String point in strength.points)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.xs),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.only(top: 3),
                    child: Icon(
                      Icons.check,
                      size: 16,
                      color: colors.chromeIndicator,
                    ),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      point,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: colors.onChrome,
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
        if (strength.examples.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.md),
          Container(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.sm,
            ),
            decoration: BoxDecoration(
              color: colors.chromeActive.withValues(alpha: 0.6),
              borderRadius: AppRadius.medium,
              border: Border.all(color: colors.onChromeMuted.withValues(alpha: 0.3)),
            ),
            child: Column(
              children: [
                for (int i = 0; i < strength.examples.length; i++)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 3),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Flexible(
                          child: Text(
                            strength.examples[i].label,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: colors.onChrome,
                            ),
                          ),
                        ),
                        const SizedBox(width: AppSpacing.md),
                        Text(
                          strength.examples[i].value,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: colors.onChrome,
                            fontWeight: i == strength.examples.length - 1
                                ? FontWeight.w700
                                : null,
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
        if (strength.findIt.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.md),
          Text(
            'Find it after sign-in: ${strength.findIt}',
            style: theme.textTheme.bodySmall?.copyWith(
              color: colors.onChromeMuted,
            ),
          ),
        ],
        const SizedBox(height: AppSpacing.md),
      ],
    );
  }
}

class _SlideNav extends StatelessWidget {
  const _SlideNav({
    required this.index,
    required this.count,
    required this.titles,
    required this.cycling,
    required this.interval,
    required this.onStep,
    required this.onGo,
  });

  final int index;
  final int count;
  final List<String> titles;
  final bool cycling;
  final Duration interval;
  final ValueChanged<int> onStep;
  final ValueChanged<int> onGo;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final AppSemanticColors colors = context.semanticColors;
    return Row(
      children: [
        IconButton(
          tooltip: 'Previous',
          visualDensity: VisualDensity.compact,
          color: colors.onChromeMuted,
          onPressed: () => onStep(-1 + count),
          icon: const Icon(Icons.chevron_left),
        ),
        Flexible(
          child: Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.sm,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              for (int i = 0; i < count; i++)
                Tooltip(
                  message: titles[i],
                  child: InkWell(
                    key: ValueKey<String>('strength-dot-$i'),
                    borderRadius: BorderRadius.circular(5),
                    onTap: () => onGo(i),
                    child: Container(
                      width: i == index ? 22 : 9,
                      height: 9,
                      decoration: BoxDecoration(
                        color: i == index
                            ? colors.chromeIndicator
                            : colors.onChromeMuted.withValues(alpha: 0.4),
                        borderRadius: BorderRadius.circular(5),
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
        IconButton(
          tooltip: 'Next',
          visualDensity: VisualDensity.compact,
          color: colors.onChromeMuted,
          onPressed: () => onStep(1),
          icon: const Icon(Icons.chevron_right),
        ),
        const Spacer(),
        if (cycling)
          Flexible(
            child: Text(
              'Changes every ${interval.inSeconds} seconds  -  '
              'stops while you type',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodySmall?.copyWith(
                color: colors.onChromeMuted,
              ),
            ),
          ),
      ],
    );
  }
}

/// Server state, version and who the product is, along the foot.
class _StatusBar extends StatelessWidget {
  const _StatusBar({
    required this.branding,
    required this.host,
    required this.server,
  });

  final BrandingConfig branding;
  final String host;
  final _ServerState server;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final AppSemanticColors colors = context.semanticColors;
    final (Color, String) state = switch (server) {
      _ServerState.checking => (
          theme.colorScheme.outline,
          'Checking server $host',
        ),
      _ServerState.answers => (colors.success, 'Server $host answers'),
      _ServerState.silent => (colors.warning, 'Server $host is not answering'),
    };
    final TextStyle? style = theme.textTheme.bodySmall;
    return Material(
      color: theme.colorScheme.surfaceContainerHighest,
      child: SizedBox(
        height: 32,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          child: Row(
            children: [
              Icon(Icons.circle, size: 9, color: state.$1),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  state.$2,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: style,
                ),
              ),
              const SizedBox(width: AppSpacing.lg),
              Text('Version ${branding.version}', style: style),
              const SizedBox(width: AppSpacing.lg),
              Flexible(
                child: Text(
                  'Powered by ${branding.productName}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: style,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
