// The agency's branding form (backlog 71, U5 and U7): Settings > Platform >
// Branding, the first-run "Set up your agency" dialog, and Home's "Finish
// setting up" card -- one shared form, saved with If-Match, and showing in the
// header at once with no read.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/auth/session_controller.dart';
import 'package:agency_desktop/core/branding/agency_branding_cache.dart';
import 'package:agency_desktop/core/branding/branding_config.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:agency_desktop/models/agency_branding.dart';
import 'package:agency_desktop/models/entities.dart' show Json;
import 'package:agency_desktop/phase2/agency_branding_form.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const String _server = 'http://127.0.0.1:9';

// A 1x1 PNG.
final Uint8List _png = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA'
  '60e6kgAAAABJRU5ErkJggg==',
);

const BrandingConfig _product = BrandingConfig(
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

/// The server's branding endpoints, and every call made to them.
class _BrandingApi extends ApiClient {
  _BrandingApi({AgencyBranding? record, this.logo})
      : record = record ?? AgencyBranding.notSet,
        super(
          baseUrl: _server,
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  AgencyBranding record;
  Uint8List? logo;
  final List<String> calls = <String>[];
  final List<int?> versions = <int?>[];
  Map<String, Object?>? lastBody;

  /// The next write is refused with this message.
  String? refuse;

  Json _answer() => {
        'data': {
          'is_set': record.isSet,
          'agency_name': record.agencyName,
          'tagline': record.tagline,
          'accent_color': record.accentColor,
          'has_logo': record.hasLogo,
          'version': record.version,
        },
      };

  void _write(String call, int? expectedVersion) {
    calls.add(call);
    versions.add(expectedVersion);
    if (refuse != null) throw ApiException(refuse!, statusCode: 422);
  }

  AgencyBranding _next({
    String? name,
    String? tagline,
    bool? hasLogo,
  }) =>
      record = AgencyBranding(
        isSet: true,
        agencyName: name ?? record.agencyName,
        tagline: tagline ?? record.tagline,
        accentColor: record.accentColor,
        hasLogo: hasLogo ?? record.hasLogo,
        version: (record.version ?? 0) + 1,
      );

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async {
    // The shell asks for its own things too (modules, stages, health); only
    // the branding calls are recorded, and the rest are refused as offline.
    if (!path.startsWith('/api/v1/branding')) {
      throw const ApiException('offline');
    }
    if (method == 'GET') {
      calls.add('GET $path');
      return _answer();
    }
    _write('$method $path', expectedVersion);
    if (method == 'DELETE') {
      logo = null;
      _next(hasLogo: false);
    }
    if (method == 'PUT') {
      lastBody = Map<String, Object?>.from(body!);
      _next(
        name: body['agency_name'] as String,
        tagline: (body['tagline'] as String?) ?? '',
      );
    }
    return _answer();
  }

  @override
  Future<List<int>> downloadBytes(
    String path, {
    Map<String, String>? query,
    String method = 'GET',
    Json? body,
    bool retrying = false,
  }) async {
    calls.add('GET $path');
    if (logo == null) throw const ApiException('none', statusCode: 404);
    return logo!;
  }

  @override
  Future<Json> multipartRequest(
    String method,
    String path, {
    required Map<String, String> fields,
    String? fileField,
    String? fileName,
    List<int>? fileBytes,
    String? fileContentType,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async {
    _write('$method $path', expectedVersion);
    logo = Uint8List.fromList(fileBytes!);
    _next(hasLogo: true);
    return _answer();
  }
}

const AgencyBranding _given = AgencyBranding(
  isSet: true,
  agencyName: 'Sri Lakshmi Agencies',
  tagline: 'Wholesale distribution',
  accentColor: '#112233',
  hasLogo: true,
  version: 3,
);

class _Session extends SessionController {
  _Session(DesktopPreferencesService preferences)
      : super(
          baseUrl: _server,
          preferences: preferences,
          isPlatformAdmin: () => false,
        );
}

String _token({bool platformSettings = true}) {
  // Every code the catalogue names, so the shell offers the whole app -- bar
  // PLATFORM_SETTINGS for somebody who may not give the branding.
  final Set<String> codes = {
    for (final ModuleDefinition module in ModuleCatalog.modules) ...[
      ...module.requiredPermissions,
      for (final ModuleTabDefinition tab in module.tabs)
        ...tab.requiredPermissions,
    ],
    'PLATFORM_SETTINGS',
  };
  if (!platformSettings) codes.remove('PLATFORM_SETTINGS');
  final String payload = base64Url.encode(utf8.encode(jsonEncode({
    'permissions': codes.toList(),
    'roles': const <String>[],
    'platform_admin': false,
    'firm_permissions': const <String, List<String>>{},
  })));
  return 'h.$payload.s';
}

class _Pumped {
  _Pumped(this.api, this.directory, this.preferences, this.titles);

  final _BrandingApi api;
  final Directory directory;
  final DesktopPreferencesService preferences;
  final List<String> titles;

  AgencyBrandingCache get cache => AgencyBrandingCache(directory: directory);
}

/// The phase 2 shell, signed in as somebody holding [platformSettings] or not,
/// with the server's record (and the cache sign-in would have left) as given.
Future<_Pumped> _pumpShell(
  WidgetTester tester, {
  AgencyBranding? record,
  bool cached = false,
  bool platformSettings = true,
  bool skipped = false,
  String? location,
  Size size = const Size(1366, 768),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  late DesktopPreferencesService preferences;
  late Directory directory;
  final _BrandingApi api = _BrandingApi(
    record: record,
    logo: record?.hasLogo == true ? _png : null,
  );
  await tester.runAsync(() async {
    directory = Directory.systemTemp.createTempSync('agency_branding_');
    preferences = DesktopPreferencesService(directory: directory);
    await preferences.saveLastWorkspace(location ?? 'administration/users');
    if (skipped) {
      await preferences
          .saveWorkspaceState('phase2.first_run', {'agency_skipped': true});
    }
    if (cached && record != null) {
      await AgencyBrandingCache(directory: directory)
          .write(_server, record, record.hasLogo ? _png : null);
    }
  });
  addTearDown(() => directory.deleteSync(recursive: true));
  final PermissionService permissions = PermissionService()
    ..applyAccessToken(_token(platformSettings: platformSettings));
  final _Session session = _Session(preferences)..api = api;
  final List<String> titles = <String>[];
  final ThemeManager themes = ThemeManager(preferences);
  await tester.pumpWidget(MaterialApp(
    theme: themes.lightTheme,
    home: DesktopShell(
      phase2: true,
      session: session,
      preferences: preferences,
      branding: _product,
      themes: themes,
      permissions: permissions,
      agencyCache: AgencyBrandingCache(directory: directory),
      setWindowTitle: (title) async => titles.add(title),
    ),
  ));
  await tester.pump(const Duration(milliseconds: 100));
  return _Pumped(api, directory, preferences, titles);
}

Future<void> _unmount(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox());
  await tester.pump();
}

Future<void> _settle(WidgetTester tester) async {
  await tester.pump(const Duration(milliseconds: 300));
  await tester.pump(const Duration(milliseconds: 300));
}

/// Waits for the real file writes the cache and preferences make: each step
/// of one is a real I/O completion followed by a fake-zone microtask.
Future<void> _io(WidgetTester tester) async {
  for (int i = 0; i < 6; i++) {
    await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pump();
  }
}

/// A chosen file held in memory: `XFile.fromData` ignores its name on the
/// desktop platforms, and a real file's read needs the real clock.
class _Picked implements XFile {
  _Picked(this.name, this.size);

  @override
  final String name;
  final int size;

  @override
  Future<Uint8List> readAsBytes() async => Uint8List(size);

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

XFile _file(String name, int size) => _Picked(name, size);

/// The form on its own, in a window, against [api].
Future<_Changes> _pumpForm(
  WidgetTester tester,
  _BrandingApi api, {
  AgencyBranding initial = AgencyBranding.notSet,
  Uint8List? logo,
  Future<XFile?> Function()? pickFile,
  Size size = const Size(1366, 768),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final _Changes changes = _Changes();
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: AgencyBrandingForm(
        api: api,
        product: _product,
        initial: initial,
        initialLogo: logo,
        pickFile: pickFile,
        onChanged: (saved, bytes) => changes.saved.add((saved, bytes)),
        onDone: () => changes.done++,
      ),
    ),
  ));
  await tester.pump();
  return changes;
}

class _Changes {
  final List<(AgencyBranding, Uint8List?)> saved = [];
  int done = 0;
}

Future<void> _type(WidgetTester tester, String key, String text) async {
  await tester.enterText(find.byKey(ValueKey(key)), text);
  await tester.pump();
}

Future<void> _tap(WidgetTester tester, String key) async {
  await tester.ensureVisible(find.byKey(ValueKey(key)));
  await tester.tap(find.byKey(ValueKey(key)));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

void main() {
  group('the form', () {
    testWidgets('a blank name is refused before anything is sent',
        (tester) async {
      final _BrandingApi api = _BrandingApi();
      await _pumpForm(tester, api);

      await _type(tester, 'branding-name', '   ');
      await _tap(tester, 'branding-save');

      expect(find.text('Give your agency a name.'), findsOneWidget);
      expect(api.calls, isEmpty);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a logo over 1 MB or of another type is refused with a message',
        (tester) async {
      final _BrandingApi api = _BrandingApi();
      final List<XFile> picks = [
        _file('big.png', agencyLogoLimitBytes + 1),
        _file('logo.gif', 100),
        _file('ok.jpg', 100),
      ];
      await _pumpForm(tester, api, pickFile: () async => picks.removeAt(0));

      await _tap(tester, 'branding-choose-logo');
      await tester.pump();
      expect(find.textContaining('the limit is 1 MB'), findsOneWidget);
      expect(find.byKey(const ValueKey('branding-remove-logo')), findsNothing);

      await _tap(tester, 'branding-choose-logo');
      await tester.pump();
      expect(find.text('Choose a PNG or JPG picture.'), findsOneWidget);

      await _tap(tester, 'branding-choose-logo');
      await tester.pump();
      expect(find.byKey(const ValueKey('branding-logo-error')), findsNothing);
      expect(find.byKey(const ValueKey('branding-remove-logo')),
          findsOneWidget);
      expect(api.calls, isEmpty);
    });

    testWidgets('the preview follows what is typed', (tester) async {
      await _pumpForm(tester, _BrandingApi());
      expect(find.text('Your agency'), findsWidgets);

      await _type(tester, 'branding-name', 'Blue Star Traders');
      await _type(tester, 'branding-tagline', 'Since 1980');

      for (final String key in const [
        'branding-preview-signin-name',
        'branding-preview-header-name',
      ]) {
        expect(tester.widget<Text>(find.byKey(ValueKey(key))).data,
            'Blue Star Traders');
      }
      for (final String key in const [
        'branding-preview-signin-tagline',
        'branding-preview-header-tagline',
      ]) {
        expect(
            tester.widget<Text>(find.byKey(ValueKey(key))).data, 'Since 1980');
      }
      // Initials stand in until a logo is chosen.
      expect(find.text('BS'), findsWidgets);
      // Our product is shown, read-only.
      expect(find.text('Ledger Desk by Example Co'), findsOneWidget);
      expect(find.textContaining('changed only by an update'), findsOneWidget);
    });

    testWidgets('save sends If-Match, the stored colour, then the logo',
        (tester) async {
      final _BrandingApi api = _BrandingApi(record: _given, logo: _png);
      final _Changes changes = await _pumpForm(
        tester,
        api,
        initial: _given,
        logo: _png,
        pickFile: () async => _file('new.png', 200),
      );
      // Pre-filled.
      expect(find.text('Sri Lakshmi Agencies'), findsWidgets);

      await _type(tester, 'branding-name', 'Sri Lakshmi Traders');
      await _tap(tester, 'branding-choose-logo');
      await tester.pump();
      await _tap(tester, 'branding-save');
      await tester.pump();

      expect(api.calls, ['PUT /api/v1/branding', 'PUT /api/v1/branding/logo']);
      // Each carries the version the last answer gave.
      expect(api.versions, [3, 4]);
      expect(api.lastBody!['accent_color'], '#112233');
      expect(api.lastBody!['agency_name'], 'Sri Lakshmi Traders');
      expect(changes.saved.last.$1.agencyName, 'Sri Lakshmi Traders');
      expect(changes.saved.last.$1.version, 5);
      expect(changes.saved.last.$2, isNotNull);
      expect(changes.done, 1);
      expect(find.byKey(const ValueKey('branding-saved')), findsOneWidget);
    });

    testWidgets('removing the logo deletes it; an untouched logo is not sent',
        (tester) async {
      final _BrandingApi api = _BrandingApi(record: _given, logo: _png);
      final _Changes changes =
          await _pumpForm(tester, api, initial: _given, logo: _png);

      await _tap(tester, 'branding-save');
      expect(api.calls, ['PUT /api/v1/branding']);
      expect(changes.saved.last.$2, _png);

      api.calls.clear();
      await _tap(tester, 'branding-remove-logo');
      await _tap(tester, 'branding-save');
      expect(api.calls,
          ['PUT /api/v1/branding', 'DELETE /api/v1/branding/logo']);
      expect(changes.saved.last.$1.hasLogo, isFalse);
      expect(changes.saved.last.$2, isNull);
    });

    testWidgets('a refusal keeps the form open, with what was typed',
        (tester) async {
      final _BrandingApi api = _BrandingApi()..refuse = 'Not allowed here.';
      final _Changes changes = await _pumpForm(tester, api);

      await _type(tester, 'branding-name', 'Blue Star');
      await _type(tester, 'branding-tagline', 'Since 1980');
      await _tap(tester, 'branding-save');
      await tester.pump();

      expect(find.text('Not allowed here.'), findsOneWidget);
      expect(find.byKey(const ValueKey('save-error-banner')), findsOneWidget);
      expect(tester.widget<TextField>(find.byKey(const ValueKey('branding-name')))
              .controller!
              .text,
          'Blue Star');
      expect(
          tester
              .widget<TextField>(find.byKey(const ValueKey('branding-tagline')))
              .controller!
              .text,
          'Since 1980');
      expect(changes.saved, isEmpty);
      expect(changes.done, 0);

      // Saving again, now accepted, works from the same form.
      api.refuse = null;
      await _tap(tester, 'branding-save');
      expect(changes.done, 1);
    });

    for (final Size size in const <Size>[Size(1366, 768), Size(800, 600)]) {
      testWidgets('no overflow at ${size.width.toInt()}x${size.height.toInt()}',
          (tester) async {
        await _pumpForm(
          tester,
          _BrandingApi(record: _given, logo: _png),
          initial: _given.copyLong(),
          logo: _png,
          size: size,
        );
        expect(tester.takeException(), isNull);
      });
    }
  });

  group('Settings > Platform > Branding', () {
    testWidgets('a holder of PLATFORM_SETTINGS finds it and opens it with '
        'two reads', (tester) async {
      final _Pumped p =
          await _pumpShell(tester, record: _given, cached: true);

      await tester.tap(find.byKey(const ValueKey('menu-area-settings')));
      await _settle(tester);
      await tester.tap(find.byKey(const ValueKey('setup-section-Agency')));
      await _settle(tester);
      await tester.tap(find.byKey(const ValueKey('setup-card-branding')));
      await _settle(tester);

      expect(find.byKey(const ValueKey('branding')), findsOneWidget);
      expect(find.byKey(const ValueKey('branding-name')), findsOneWidget);
      expect(p.api.calls, ['GET /api/v1/branding', 'GET /api/v1/branding/logo']);
      expect(tester.takeException(), isNull);
      await _unmount(tester);
    });

    testWidgets('without the permission it is not offered, and not opened',
        (tester) async {
      final _Pumped p = await _pumpShell(
        tester,
        record: _given,
        cached: true,
        platformSettings: false,
        location: 'branding',
      );

      expect(find.byKey(const ValueKey('branding')), findsNothing);
      await tester.tap(find.byKey(const ValueKey('menu-area-settings')));
      await _settle(tester);
      expect(find.byKey(const ValueKey('setup-card-branding')), findsNothing);
      expect(p.api.calls, isEmpty);
      await _unmount(tester);
    });

    testWidgets('saving updates the cache and the header with no read',
        (tester) async {
      final _Pumped p = await _pumpShell(
        tester,
        record: _given,
        cached: true,
        location: 'branding',
        skipped: true,
      );
      await _settle(tester);
      expect(find.byKey(const ValueKey('branding-name')), findsOneWidget);
      expect(
          tester
              .widget<Text>(find.byKey(const ValueKey('agency-header-name')))
              .data,
          'Sri Lakshmi Agencies');
      p.api.calls.clear();

      await _type(tester, 'branding-name', 'Blue Star Traders');
      await _tap(tester, 'branding-save');
      await _io(tester);

      // Only the writes: no GET of the record or of the logo.
      expect(p.api.calls, ['PUT /api/v1/branding']);
      expect(p.api.versions, [3]);
      expect(
          tester
              .widget<Text>(find.byKey(const ValueKey('agency-header-name')))
              .data,
          'Blue Star Traders');
      expect(p.titles.last, 'Blue Star Traders');
      final CachedAgencyBranding? cached = p.cache.readSync(_server);
      expect(cached!.branding.agencyName, 'Blue Star Traders');
      expect(cached.branding.version, 4);
      expect(cached.logo, _png);
      expect(tester.takeException(), isNull);
      await _unmount(tester);
    });
  });

  group('first-run setup', () {
    testWidgets('opens when nothing is given and the user may give it',
        (tester) async {
      final _Pumped p = await _pumpShell(tester);
      await _settle(tester);

      expect(find.byKey(const ValueKey('first-run-agency')), findsOneWidget);
      expect(find.text('Set up your agency'), findsWidgets);
      // This PC held no copy, so it asked once whether the server has one
      // before offering an empty form; then nothing until Save.
      expect(p.api.calls, ['GET /api/v1/branding']);
      expect(tester.takeException(), isNull);
      await _unmount(tester);
    });

    testWidgets('with no copy on this PC, a record the server holds is not '
        'offered as an empty form', (tester) async {
      final _Pumped p = await _pumpShell(tester, record: _given);
      await _settle(tester);

      expect(find.byKey(const ValueKey('first-run-agency')), findsNothing);
      expect(p.api.calls.first, 'GET /api/v1/branding');
      expect(p.api.calls.where((call) => call.startsWith('PUT')), isEmpty);
      expect(find.text(_given.agencyName), findsWidgets);
      await _unmount(tester);
    });

    testWidgets('does not open for somebody who may not give it',
        (tester) async {
      final _Pumped p = await _pumpShell(tester, platformSettings: false);
      await _settle(tester);

      expect(find.byKey(const ValueKey('first-run-agency')), findsNothing);
      expect(find.byKey(const ValueKey('home-finish-setup')), findsNothing);
      expect(p.api.calls, isEmpty);
      await _unmount(tester);
    });

    testWidgets('does not open once the branding is given', (tester) async {
      await _pumpShell(tester, record: _given, cached: true);
      await _settle(tester);

      expect(find.byKey(const ValueKey('first-run-agency')), findsNothing);
      await _unmount(tester);
    });

    testWidgets('Skip is remembered and Home shows the card, which opens the '
        'same form', (tester) async {
      final _Pumped p = await _pumpShell(tester, location: 'home');
      await _settle(tester);
      expect(find.byKey(const ValueKey('first-run-agency')), findsOneWidget);

      await _tap(tester, 'branding-secondary');
      await _settle(tester);
      await _io(tester);

      expect(find.byKey(const ValueKey('first-run-agency')), findsNothing);
      expect(
        p.preferences.workspaceState('phase2.first_run')['agency_skipped'],
        isTrue,
      );
      expect(find.byKey(const ValueKey('home-finish-setup')), findsOneWidget);
      // One read when the dialog first opened (no copy on this PC); none since.
      expect(p.api.calls, ['GET /api/v1/branding']);

      await _tap(tester, 'home-finish-setup-open');
      await _settle(tester);
      expect(find.byKey(const ValueKey('first-run-agency')), findsOneWidget);
      await _unmount(tester);
    });

    testWidgets('a skipped user is not asked again, but keeps the card',
        (tester) async {
      await _pumpShell(tester, skipped: true, location: 'home');
      await _settle(tester);

      expect(find.byKey(const ValueKey('first-run-agency')), findsNothing);
      expect(find.byKey(const ValueKey('home-finish-setup')), findsOneWidget);
      await _unmount(tester);
    });

    testWidgets('saving closes it, the header shows the agency, the card goes',
        (tester) async {
      final _Pumped p = await _pumpShell(tester, location: 'home');
      await _settle(tester);

      await _type(tester, 'branding-name', 'Blue Star Traders');
      await _tap(tester, 'branding-save');
      await _settle(tester);
      await _io(tester);

      // The first save has no version to send.
      expect(p.api.calls, ['GET /api/v1/branding', 'PUT /api/v1/branding']);
      expect(p.api.versions, [null]);
      expect(find.byKey(const ValueKey('first-run-agency')), findsNothing);
      expect(find.byKey(const ValueKey('home-finish-setup')), findsNothing);
      expect(
          tester
              .widget<Text>(find.byKey(const ValueKey('agency-header-name')))
              .data,
          'Blue Star Traders');
      expect(p.cache.readSync(_server)!.branding.agencyName,
          'Blue Star Traders');
      await _unmount(tester);
    });

    for (final Size size in const <Size>[Size(1366, 768), Size(800, 600)]) {
      testWidgets(
          'no overflow at ${size.width.toInt()}x${size.height.toInt()}, '
          'dialog and card', (tester) async {
        await _pumpShell(tester, location: 'home', size: size);
        await _settle(tester);
        expect(find.byKey(const ValueKey('first-run-agency')), findsOneWidget);
        expect(tester.takeException(), isNull);

        await _tap(tester, 'branding-secondary');
        await _settle(tester);
        expect(find.byKey(const ValueKey('home-finish-setup')), findsOneWidget);
        expect(tester.takeException(), isNull);
        await _unmount(tester);
      });
    }
  });
}

extension on AgencyBranding {
  AgencyBranding copyLong() => AgencyBranding(
        isSet: true,
        agencyName: 'A Very Long Agency Name ' * 5,
        tagline: 'An equally long tagline for the agency ' * 4,
        accentColor: accentColor,
        hasLogo: hasLogo,
        version: version,
      );
}
