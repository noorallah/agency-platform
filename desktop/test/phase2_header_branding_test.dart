// The phase 2 header (backlog 71, U6): the agency's mark leads the menu strip,
// the window carries "Agency > Firm", our product sits at the right of the
// status line -- all from the cache sign-in refreshed, with no request of its
// own.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:agency_desktop/core/auth/session_controller.dart';
import 'package:agency_desktop/core/branding/agency_branding_cache.dart';
import 'package:agency_desktop/core/branding/branding_config.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:agency_desktop/models/agency_branding.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const String _server = 'http://127.0.0.1:9';

// A 1x1 PNG.
final Uint8List _png = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA'
  '60e6kgAAAABJRU5ErkJggg==',
);

const BrandingConfig _branding = BrandingConfig(
  appName: 'Ledger Desk',
  windowName: 'Ledger Desk Window',
  productName: 'Ledger Desk',
  companyName: 'Example Co',
  logoPath: '',
  splashPath: '',
  version: '2.0.0',
  copyright: 'c',
  loginBackgroundColor: Color(0xfff0f0f0),
  loginAccentColor: Color(0xff001122),
);

/// Counts every URL the app's HTTP client is asked for, and refuses it.
class _Recorder extends HttpOverrides {
  final List<Uri> urls = <Uri>[];

  @override
  HttpClient createHttpClient(SecurityContext? context) =>
      _RecordingClient(urls);
}

class _RecordingClient implements HttpClient {
  _RecordingClient(this.urls);

  final List<Uri> urls;

  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) {
    urls.add(url);
    throw const SocketException('refused in test');
  }

  @override
  Future<HttpClientRequest> open(
      String method, String host, int port, String path) {
    urls.add(Uri(scheme: 'http', host: host, port: port, path: path));
    throw const SocketException('refused in test');
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _CountingCache extends AgencyBrandingCache {
  _CountingCache(Directory directory) : super(directory: directory);

  int reads = 0;

  @override
  CachedAgencyBranding? readSync(String server) {
    reads++;
    return super.readSync(server);
  }
}

class _Session extends SessionController {
  _Session(DesktopPreferencesService preferences)
      : super(
          baseUrl: _server,
          preferences: preferences,
          isPlatformAdmin: () => true,
        );

  AssignedFirm? firm;

  @override
  AssignedFirm? get currentFirm => firm;

  void choose(AssignedFirm? chosen) {
    firm = chosen;
    notifyListeners();
  }
}

String _token() {
  final Set<String> codes = {
    for (final ModuleDefinition module in ModuleCatalog.modules) ...[
      ...module.requiredPermissions,
      for (final ModuleTabDefinition tab in module.tabs)
        ...tab.requiredPermissions,
    ],
  };
  final String payload = base64Url.encode(utf8.encode(jsonEncode({
    'permissions': codes.toList(),
    'roles': const <String>[],
    'platform_admin': true,
    'platform_admin_scope': 'ALL_FIRMS',
    'firm_permissions': const <String, List<String>>{},
  })));
  return 'h.$payload.s';
}

class _Pumped {
  _Pumped(this.session, this.cache, this.titles);

  final _Session session;
  final _CountingCache cache;
  final List<String> titles;
}

Future<_Pumped> _pump(
  WidgetTester tester, {
  Size size = const Size(1366, 768),
  AgencyBranding? cached,
  Uint8List? logo,
  AssignedFirm? firm,
  BrandingConfig branding = _branding,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  late DesktopPreferencesService preferences;
  late Directory directory;
  await tester.runAsync(() async {
    directory = Directory.systemTemp.createTempSync('header_branding_');
    preferences = DesktopPreferencesService(directory: directory);
    await preferences.saveLastWorkspace('administration/users');
    // These tests are about the header, not first-run setup, which an
    // administrator with no branding given would otherwise be shown.
    await preferences
        .saveWorkspaceState('phase2.first_run', {'agency_skipped': true});
    if (cached != null) {
      await AgencyBrandingCache(directory: directory)
          .write(_server, cached, logo);
    }
  });
  addTearDown(() => directory.deleteSync(recursive: true));
  final PermissionService permissions = PermissionService()
    ..applyAccessToken(_token());
  final _Session session = _Session(preferences)..firm = firm;
  final _CountingCache cache = _CountingCache(directory);
  final List<String> titles = <String>[];
  final ThemeManager themes = ThemeManager(preferences);
  await tester.pumpWidget(MaterialApp(
    theme: themes.lightTheme,
    home: DesktopShell(
      phase2: true,
      session: session,
      preferences: preferences,
      branding: branding,
      themes: themes,
      permissions: permissions,
      agencyCache: cache,
      setWindowTitle: (title) async => titles.add(title),
    ),
  ));
  await tester.pump(const Duration(milliseconds: 100));
  return _Pumped(session, cache, titles);
}

Future<void> _unmount(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox());
  await tester.pump();
}

const AgencyBranding _agency = AgencyBranding(
  isSet: true,
  agencyName: 'Sri Lakshmi Agencies',
  tagline: 'Wholesale distribution',
  hasLogo: true,
  version: 3,
);

const AssignedFirm _qa01 = AssignedFirm(
  id: 'f1',
  code: 'QA01',
  name: 'QA01 Traders',
  isPrimary: true,
);

void main() {
  testWidgets('the agency from the cache leads the menu strip', (tester) async {
    final _Pumped p = await _pump(tester, cached: _agency, logo: _png);

    expect(find.byKey(const ValueKey('agency-header')), findsOneWidget);
    expect(find.text('Sri Lakshmi Agencies'), findsOneWidget);
    expect(find.text('Wholesale distribution'), findsOneWidget);
    // The logo is drawn, not the initials.
    expect(find.byKey(const ValueKey('agency-initials')), findsNothing);
    expect(find.byType(Image), findsWidgets);
    // Nothing selected: no firm text beside the agency.
    expect(find.byKey(const ValueKey('agency-header-firm')), findsNothing);
    // The mark adds no height: it fits the bar's own 44 px.
    final Rect mark = tester.getRect(find.byKey(const ValueKey('agency-header')));
    expect(mark.height, lessThanOrEqualTo(44));
    // Home is the first area after it.
    expect(
      tester.getTopLeft(find.byKey(const ValueKey('menu-area-home'))).dx,
      greaterThan(mark.right),
    );
    expect(p.titles.last, 'Sri Lakshmi Agencies');
    expect(tester.takeException(), isNull);
    await _unmount(tester);
  });

  testWidgets('no cache falls back to branding.json and then initials',
      (tester) async {
    final _Pumped p = await _pump(tester);

    expect(find.text('Ledger Desk'), findsWidgets);
    expect(find.byKey(const ValueKey('agency-initials')), findsOneWidget);
    expect(find.text('LD'), findsOneWidget);
    expect(find.byKey(const ValueKey('agency-header-tagline')), findsNothing);
    expect(p.titles.last, 'Ledger Desk');
    await _unmount(tester);
  });

  testWidgets('the firm is plain text beside the agency and in the title',
      (tester) async {
    final _Pumped p = await _pump(tester, cached: _agency, firm: _qa01);

    expect(
      tester
          .widget<Text>(find.byKey(const ValueKey('agency-header-firm')))
          .data,
      'QA01 Traders',
    );
    expect(p.titles.last, 'Sri Lakshmi Agencies > QA01 Traders');

    p.session.choose(null);
    await tester.pump();
    expect(find.byKey(const ValueKey('agency-header-firm')), findsNothing);
    expect(p.titles.last, 'Sri Lakshmi Agencies');
    expect(tester.takeException(), isNull);
    await _unmount(tester);
  });

  testWidgets('below 820 px only the logo shows', (tester) async {
    await _pump(
      tester,
      size: const Size(800, 600),
      cached: _agency,
      logo: _png,
      firm: _qa01,
    );

    expect(find.byKey(const ValueKey('agency-header')), findsOneWidget);
    expect(find.byKey(const ValueKey('agency-header-name')), findsNothing);
    expect(find.byKey(const ValueKey('agency-header-tagline')), findsNothing);
    expect(find.byKey(const ValueKey('agency-header-firm')), findsNothing);
    expect(tester.takeException(), isNull);
    await _unmount(tester);
  });

  testWidgets('the tagline gives way before 1280 px', (tester) async {
    await _pump(tester, size: const Size(1100, 700), cached: _agency);

    expect(find.byKey(const ValueKey('agency-header-name')), findsOneWidget);
    expect(find.byKey(const ValueKey('agency-header-tagline')), findsNothing);
    expect(tester.takeException(), isNull);
    await _unmount(tester);
  });

  testWidgets('clicking the agency goes Home', (tester) async {
    await _pump(tester, cached: _agency);
    expect(find.byKey(const ValueKey('open-screen-home')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('agency-header')));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byKey(const ValueKey('open-screen-home')), findsOneWidget);
    await _unmount(tester);
  });

  testWidgets('our product is at the right of the status line',
      (tester) async {
    await _pump(tester, cached: _agency);

    final Finder product = find.byKey(const ValueKey('status-product'));
    expect(product, findsOneWidget);
    expect(find.text('Ledger Desk 2.0.0 by Example Co'), findsOneWidget);
    // No product logo file: the neutral placeholder.
    expect(find.byIcon(Icons.inventory_2_outlined), findsOneWidget);
    // It is inside the status bar, left of the connection dot.
    final Rect bar =
        tester.getRect(find.byKey(const ValueKey('phase2-status-bar')));
    final Rect box = tester.getRect(product);
    expect(bar.contains(box.center), isTrue);
    expect(
      box.right,
      lessThanOrEqualTo(
          tester.getRect(find.byKey(const ValueKey('connection-dot'))).left),
    );
    // Hover says it in full; a click opens nothing.
    final TestGesture mouse =
        await tester.createGesture(kind: PointerDeviceKind.mouse);
    await mouse.addPointer(location: tester.getCenter(product));
    await tester.pump(const Duration(seconds: 2));
    expect(find.textContaining('Version 2.0.0'), findsOneWidget);
    await tester.tap(product);
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byType(Dialog), findsNothing);
    await mouse.removePointer();
    await _unmount(tester);
  });

  for (final Size size in const <Size>[Size(1366, 768), Size(800, 600)]) {
    testWidgets(
        'no overflow at ${size.width.toInt()}x${size.height.toInt()}'
        ' with a long agency and firm', (tester) async {
      await _pump(
        tester,
        size: size,
        cached: const AgencyBranding(
          isSet: true,
          agencyName: 'Sri Lakshmi Wholesale Distribution And Agencies Pvt',
          tagline: 'Wholesale distribution across the whole of the south',
          version: 1,
        ),
        firm: const AssignedFirm(
          id: 'f2',
          code: 'LONG',
          name: 'A Very Long Firm Name Trading As Something Else Entirely',
          isPrimary: true,
        ),
      );
      expect(tester.takeException(), isNull);
      await _unmount(tester);
    });
  }

  testWidgets('the header reads the cache once and asks the server nothing',
      (tester) async {
    final _Recorder recorder = _Recorder();
    late _Pumped p;
    await HttpOverrides.runZoned(() async {
      p = await _pump(tester, cached: _agency, logo: _png, firm: _qa01);
      final int before = p.cache.reads;
      await tester.tap(find.byKey(const ValueKey('agency-header')));
      await tester.pump(const Duration(milliseconds: 300));
      p.session.choose(null);
      await tester.pump();
      expect(p.cache.reads, before);
      await _unmount(tester);
    }, createHttpClient: recorder.createHttpClient);

    expect(p.cache.reads, 1);
    expect(
      recorder.urls.where((url) => url.path.contains('branding')),
      isEmpty,
    );
  });
}
