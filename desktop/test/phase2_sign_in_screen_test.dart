// The phase 2 sign-in: the showcase on the left, the standard form on the
// right, the agency's own identity from the server with the package's as the
// fallback, and one line of help that opens into the support details.

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/app.dart';
import 'package:agency_desktop/core/auth/refresh_token_store.dart';
import 'package:agency_desktop/core/auth/session_controller.dart';
import 'package:agency_desktop/core/branding/agency_branding_cache.dart';
import 'package:agency_desktop/core/branding/branding_config.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:agency_desktop/models/agency_branding.dart';
import 'package:agency_desktop/phase2/sign_in_screen.dart';
import 'package:agency_desktop/ui/auth_screens.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

class _MemoryTokenStore implements RefreshTokenStore {
  @override
  Future<void> clear() async {}

  @override
  Future<String?> read() async => null;

  @override
  Future<void> write(String value) async {}
}

class _Preferences extends DesktopPreferencesService {
  _Preferences(Directory directory) : super(directory: directory);

  @override
  DesktopPreferences get current => const DesktopPreferences();

  @override
  bool get hasStoredPreferences => true;
}

class _Session extends SessionController {
  _Session(_Preferences preferences)
      : super(
          baseUrl: 'http://192.168.1.20:8000',
          preferences: preferences,
          tokenStore: _MemoryTokenStore(),
        );

  @override
  SessionStatus get status => SessionStatus.signedOut;

  @override
  Future<void> restore() async {}
}

BrandingStrength _strength(String headline) => BrandingStrength(
      kicker: 'TAX',
      title: 'Tax $headline',
      summary: 'Summary',
      headline: headline,
      text: 'Text for $headline',
      points: <String>['Point for $headline'],
      examples: const <BrandingStrengthExample>[
        BrandingStrengthExample(label: 'Taxable value', value: '1,000.00'),
      ],
      findIt: 'Accounts > GST returns',
    );

BrandingConfig _branding({
  List<BrandingStrength> strengths = const <BrandingStrength>[],
  String supportPhone = '',
  String supportEmail = '',
  String supportWebsite = '',
  String tagline = '',
}) =>
    BrandingConfig(
      appName: 'Ledger Desk',
      windowName: 'Ledger Desk Window',
      productName: 'Ledger Desk',
      companyName: 'Example Co',
      logoPath: '',
      splashPath: '',
      version: '2.0.0',
      copyright: 'c',
      loginBackgroundColor: const Color(0xfff0f0f0),
      loginAccentColor: const Color(0xff001122),
      tagline: tagline,
      supportPhone: supportPhone,
      supportEmail: supportEmail,
      supportWebsite: supportWebsite,
      strengths: strengths,
    );

const AgencyBranding _serverBranding = AgencyBranding(
  isSet: true,
  agencyName: 'Sri Lakshmi Agencies',
  tagline: 'Wholesale distribution',
  version: 3,
);

// A 1x1 PNG.
final Uint8List _png = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA'
  '60e6kgAAAABJRU5ErkJggg==',
);

late Directory _directory;
late _Preferences _preferences;
late _Session _session;
late ThemeManager _themes;
int _brandingCalls = 0;
int _logoCalls = 0;

Future<void> _show(
  WidgetTester tester, {
  required BrandingConfig branding,
  Future<AgencyBranding> Function()? loadBranding,
  Future<Uint8List?> Function()? loadLogo,
  Size size = const Size(1366, 768),
  AgencyBrandingCache? cache,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(
    MaterialApp(
      theme: _themes.lightTheme,
      home: Phase2SignInScreen(
        session: _session,
        preferences: _preferences,
        branding: branding,
        themes: _themes,
        computerName: 'FRONT-DESK-PC',
        setWindowTitle: false,
        capsLockEnabled: () => false,
        cache: cache ?? AgencyBrandingCache(directory: _directory),
        loadBranding: loadBranding ??
            () async {
              _brandingCalls++;
              return _serverBranding;
            },
        loadLogo: loadLogo ??
            () async {
              _logoCalls++;
              return null;
            },
      ),
    ),
  );
  await tester.pump();
  await tester.pump();
}

void main() {
  setUp(() {
    _directory = Directory.systemTemp.createTempSync('sign_in_test');
    _preferences = _Preferences(_directory);
    _session = _Session(_preferences);
    _themes = ThemeManager(_preferences, wireframe: true);
    _brandingCalls = 0;
    _logoCalls = 0;
  });

  tearDown(() {
    _themes.dispose();
    try {
      _directory.deleteSync(recursive: true);
    } on Object {
      // A temp folder.
    }
  });

  for (final Size size in <Size>[
    const Size(1366, 768),
    const Size(800, 600),
  ]) {
    testWidgets('renders with no overflow at ${size.width}x${size.height}',
        (WidgetTester tester) async {
      await _show(
        tester,
        size: size,
        branding: _branding(
          strengths: <BrandingStrength>[_strength('One'), _strength('Two')],
          tagline: 'Many lights.',
          supportPhone: '+91 90000 00000',
          supportEmail: 'help@example.test',
        ),
      );
      expect(tester.takeException(), isNull);
      expect(find.text('Sign in'), findsOneWidget);
      expect(find.text('Forgot password?'), findsOneWidget);
      // Open the help too: the longest the screen gets.
      await tester.ensureVisible(find.text('More help'));
      await tester.tap(find.text('More help'));
      await tester.pump();
      expect(tester.takeException(), isNull);
      expect(find.text('Copy details for support'), findsOneWidget);
    });
  }

  testWidgets('a narrow window drops the showcase and keeps the card',
      (WidgetTester tester) async {
    await _show(
      tester,
      size: const Size(800, 600),
      branding: _branding(strengths: <BrandingStrength>[_strength('One')]),
    );
    expect(find.text('One'), findsNothing);
    expect(find.text('Password'), findsOneWidget);
  });

  testWidgets('shows the server agency name, one call each, no logo call',
      (WidgetTester tester) async {
    await _show(tester, branding: _branding());
    expect(find.text('Sri Lakshmi Agencies'), findsWidgets);
    expect(find.text('Wholesale distribution'), findsWidgets);
    expect(_brandingCalls, 1);
    expect(_logoCalls, 0);
    expect(find.text('Server 192.168.1.20:8000 answers'), findsOneWidget);
  });

  testWidgets('fetches the logo only when the agency has one',
      (WidgetTester tester) async {
    await _show(
      tester,
      branding: _branding(),
      loadBranding: () async {
        _brandingCalls++;
        return const AgencyBranding(
          isSet: true,
          agencyName: 'Sri Lakshmi Agencies',
          hasLogo: true,
          version: 1,
        );
      },
      loadLogo: () async {
        _logoCalls++;
        return _png;
      },
    );
    expect(_brandingCalls, 1);
    expect(_logoCalls, 1);
    expect(find.byKey(const ValueKey<String>('agency-initials')), findsNothing);
    expect(
      find.byWidgetPredicate(
        (Widget w) => w is Image && w.image is MemoryImage,
      ),
      findsWidgets,
    );
  });

  testWidgets('falls back to branding.json when the server cannot be read',
      (WidgetTester tester) async {
    await _show(
      tester,
      branding: _branding(),
      loadBranding: () async => throw const SocketException('down'),
    );
    expect(find.text('Ledger Desk'), findsWidgets);
    expect(find.text('Sri Lakshmi Agencies'), findsNothing);
    expect(
      find.text('Server 192.168.1.20:8000 is not answering'),
      findsOneWidget,
    );
  });

  testWidgets('falls back when the agency has not set its branding',
      (WidgetTester tester) async {
    await _show(
      tester,
      branding: _branding(),
      loadBranding: () async => AgencyBranding.notSet,
    );
    expect(find.text('Ledger Desk'), findsWidgets);
  });

  testWidgets('shows initials in a square when there is no logo',
      (WidgetTester tester) async {
    await _show(tester, branding: _branding());
    expect(find.byKey(const ValueKey<String>('agency-initials')), findsWidgets);
    expect(find.text('SL'), findsWidgets);
  });

  testWidgets('what was read last time shows before the server answers',
      (WidgetTester tester) async {
    final AgencyBrandingCache cache =
        AgencyBrandingCache(directory: _directory);
    await tester.runAsync(
      () => cache.write(_session.baseUrl, _serverBranding, null),
    );
    final Completer<AgencyBranding> never = Completer<AgencyBranding>();
    await _show(
      tester,
      branding: _branding(),
      cache: cache,
      loadBranding: () => never.future,
    );
    expect(find.text('Sri Lakshmi Agencies'), findsWidgets);
    expect(find.text('Checking server 192.168.1.20:8000'), findsOneWidget);
  });

  testWidgets('strengths cycle on a timer and stop once the user types',
      (WidgetTester tester) async {
    await _show(
      tester,
      branding: _branding(
        strengths: <BrandingStrength>[_strength('One'), _strength('Two')],
      ),
    );
    expect(find.text('One'), findsOneWidget);
    await tester.pump(const Duration(seconds: 8));
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('Two'), findsOneWidget);
    await tester.pump(const Duration(seconds: 8));
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('One'), findsOneWidget);

    await tester.enterText(find.byType(TextFormField).first, 'qa01');
    await tester.pump();
    await tester.pump(const Duration(seconds: 30));
    expect(find.text('One'), findsOneWidget);
    expect(find.text('Two'), findsNothing);

    // Still movable by hand.
    await tester.tap(find.byTooltip('Next'));
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('Two'), findsOneWidget);
  });

  testWidgets('no strengths means no carousel, only the product',
      (WidgetTester tester) async {
    await _show(
      tester,
      branding: _branding(tagline: 'Many lights.'),
    );
    expect(find.byTooltip('Next'), findsNothing);
    expect(find.textContaining(' OF '), findsNothing);
    expect(find.text('Many lights.'), findsWidgets);
    await tester.pump(const Duration(seconds: 20));
    expect(tester.takeException(), isNull);
  });

  testWidgets('empty support rows are hidden; password line and copy remain',
      (WidgetTester tester) async {
    await _show(tester, branding: _branding());
    await tester.ensureVisible(find.text('More help'));
    await tester.tap(find.text('More help'));
    await tester.pump();
    expect(find.byIcon(Icons.phone_outlined), findsNothing);
    expect(find.byIcon(Icons.mail_outline), findsNothing);
    expect(find.byIcon(Icons.language_outlined), findsNothing);
    expect(
      find.text('Forgot your password? Your administrator resets it.'),
      findsOneWidget,
    );
    expect(find.text('Copy details for support'), findsOneWidget);
  });

  testWidgets('support rows given by branding.json are shown',
      (WidgetTester tester) async {
    await _show(
      tester,
      branding: _branding(
        supportPhone: '+91 90000 00000',
        supportEmail: 'help@example.test',
        supportWebsite: 'www.example.test/help',
      ),
    );
    await tester.ensureVisible(find.text('More help'));
    await tester.tap(find.text('More help'));
    await tester.pump();
    expect(find.byIcon(Icons.phone_outlined), findsOneWidget);
    expect(find.byIcon(Icons.mail_outline), findsOneWidget);
    expect(find.text('www.example.test/help'), findsOneWidget);
  });

  testWidgets('copy details puts version, server and PC name on the clipboard',
      (WidgetTester tester) async {
    String? copied;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (MethodCall call) async {
        if (call.method == 'Clipboard.setData') {
          copied = (call.arguments as Map<dynamic, dynamic>)['text'] as String;
        }
        return null;
      },
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, null),
    );
    await _show(tester, branding: _branding());
    await tester.ensureVisible(find.text('More help'));
    await tester.tap(find.text('More help'));
    await tester.pump();
    await tester.ensureVisible(find.text('Copy details for support'));
    await tester.tap(find.text('Copy details for support'));
    await tester.pump();
    expect(copied, contains('2.0.0'));
    expect(copied, contains('http://192.168.1.20:8000'));
    expect(copied, contains('FRONT-DESK-PC'));
    expect(find.text('Details for support copied.'), findsOneWidget);
  });

  testWidgets('the card foot names the product, its company and tagline',
      (WidgetTester tester) async {
    await _show(tester, branding: _branding(tagline: 'Many lights.'));
    expect(find.text('Ledger Desk'), findsWidgets);
    expect(find.text('by Example Co'), findsOneWidget);
    expect(find.text('Many lights.'), findsWidgets);
    expect(find.text('Powered by Ledger Desk'), findsOneWidget);
    expect(find.text('Version 2.0.0'), findsOneWidget);
  });

  testWidgets('an empty tagline is not shown', (WidgetTester tester) async {
    await _show(tester, branding: _branding());
    expect(find.text('Many lights.'), findsNothing);
  });

  testWidgets('the app chooses by phase: phase 2 gets this screen, phase 1 '
      'keeps the standard one', (WidgetTester tester) async {
    Future<void> open({required bool phase2}) async {
      await tester.pumpWidget(
        AgencyApp(
          session: _Session(_preferences),
          preferences: _preferences,
          branding: _branding(),
          phase2: phase2,
        ),
      );
      await tester.pump();
    }

    await open(phase2: false);
    expect(find.byType(LoginScreen), findsOneWidget);
    expect(find.byType(Phase2SignInScreen), findsNothing);
    expect(find.text('Welcome back'), findsOneWidget);

    await tester.pumpWidget(const SizedBox());
    await open(phase2: true);
    expect(find.byType(Phase2SignInScreen), findsOneWidget);
    expect(find.text('Welcome back'), findsNothing);
    // Let the one failing request (tests have no network) settle.
    await tester.pump(const Duration(seconds: 1));
  });

  test('the cache keeps the last branding and logo, and only for its server',
      () async {
    final AgencyBrandingCache cache =
        AgencyBrandingCache(directory: _directory);
    expect(cache.readSync('http://a'), isNull);
    await cache.write(
      'http://a',
      const AgencyBranding(
        isSet: true,
        agencyName: 'A',
        hasLogo: true,
        version: 2,
      ),
      _png,
    );
    final CachedAgencyBranding? read = cache.readSync('http://a');
    expect(read?.branding.agencyName, 'A');
    expect(read?.logo, _png);
    expect(cache.readSync('http://b'), isNull);
    await cache.write('http://a', AgencyBranding.notSet, null);
    expect(cache.readSync('http://a'), isNull);
  });
}
