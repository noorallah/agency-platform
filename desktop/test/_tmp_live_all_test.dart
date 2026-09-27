// Temporary: renders many phase 2 screens against the running backend in one
// run. Copied into desktop/test/ to run; never committed.
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:agency_desktop/core/auth/refresh_token_store.dart';
import 'package:agency_desktop/core/auth/session_controller.dart';
import 'package:agency_desktop/core/branding/branding_config.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

class _Real extends HttpOverrides {}

class _Memory implements RefreshTokenStore {
  String? token;
  @override
  Future<void> clear() async => token = null;
  @override
  Future<String?> read() async => token;
  @override
  Future<void> write(String value) async => token = value;
}

Future<void> _font(String family, String path) async {
  final FontLoader loader = FontLoader(family)
    ..addFont(Future.value(ByteData.view(File(path).readAsBytesSync().buffer)));
  await loader.load();
}

const String _out = r'C:\Users\SYEDNU~1\AppData\Local\Temp\claude\D--ws-agencyApp-agency-platform\dac4c0df-9918-4175-b7c6-d467ec8b1f32\scratchpad\all';

void main() {
  testWidgets('live all', (tester) async {
    Directory(_out).createSync(recursive: true);
    final List<String> labels =
        (Platform.environment['LABELS'] ?? 'Customers').split('|');
    final double width =
        double.parse(Platform.environment['WIDTH'] ?? '1348');
    final double height =
        double.parse(Platform.environment['HEIGHT'] ?? '740');
    tester.view.physicalSize = Size(width, height);
    tester.view.devicePixelRatio = 1;
    final List<String> problems = [];
    final FlutterExceptionHandler? original = FlutterError.onError;
    String current = '';
    FlutterError.onError = (details) {
      problems.add('$current: ${details.exceptionAsString().split('\n').first}');
    };
    late SessionController session;
    late PermissionService permissions;
    late DesktopPreferencesService prefs;
    await tester.runAsync(() async {
      await _font('Roboto', r'C:\Windows\Fonts\segoeui.ttf');
      await _font('MaterialIcons',
          r'D:\ws\agencyApp\agency-platform\desktop\build\windows\x64\runner\Debug\data\flutter_assets\fonts\MaterialIcons-Regular.otf');
      await HttpOverrides.runWithHttpOverrides(() async {
        final Directory temp = Directory.systemTemp.createTempSync('live');
        prefs = DesktopPreferencesService(directory: temp);
        permissions = PermissionService();
        session = SessionController(
          baseUrl: 'http://127.0.0.1:8000',
          tokenStore: _Memory(),
          preferences: prefs,
          onAccessTokenChanged: permissions.applyAccessToken,
          isPlatformAdmin: () => permissions.isPlatformAdmin,
        );
        await session.login('whole01.admin@agency.local', 'DemoAdmin@12345',
            rememberUsername: false, rememberMe: false);
        permissions.setActiveFirm(session.currentFirm?.id);
      }, _Real());
    });
    final String startScreen =
        session.serverPreferences?.defaultLandingPage ?? 'dashboard';
    final ThemeManager themes = ThemeManager(prefs);
    final GlobalKey key = GlobalKey();
    await tester.pumpWidget(RepaintBoundary(
      key: key,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: themes.lightTheme,
        home: DesktopShell(
          phase2: true,
          session: session,
          preferences: prefs,
          branding: BrandingConfig.defaults,
          themes: themes,
          permissions: permissions,
        ),
      ),
    ));
    Future<void> settle(int rounds) async {
      for (int i = 0; i < rounds; i++) {
        await tester.runAsync(
            () => Future<void>.delayed(const Duration(milliseconds: 200)));
        await tester.pump(const Duration(milliseconds: 50));
      }
    }

    await settle(8);
    final int rounds =
        int.parse(Platform.environment['SETTLE'] ?? '20');
    for (final String label in labels) {
      current = label;
      try {
        // Whatever the last screen left open -- a dialog, a menu -- is closed
        // first, and said, so one stuck screen does not fail every later one.
        for (int i = 0;
            i < 3 && find.byKey(const ValueKey('menu-search')).hitTestable().evaluate().isEmpty;
            i++) {
          problems.add('$label: something covered the menu before it; pressed Esc');
          await tester.sendKeyEvent(LogicalKeyboardKey.escape);
          await tester.pump(const Duration(milliseconds: 300));
        }
        await tester.tap(find.byKey(const ValueKey('menu-search')));
        await tester.pump(const Duration(milliseconds: 300));
        await tester.enterText(
            find.byKey(const ValueKey('command-box-input')), label);
        await tester.pump(const Duration(milliseconds: 100));
        await tester.testTextInput.receiveAction(TextInputAction.done);
        await tester.pump(const Duration(milliseconds: 300));
        await settle(rounds);
        final List<String> pagerFacts = [
          for (final Element e in find.byType(Text).evaluate())
            if (((e.widget as Text).data ?? '').contains(RegExp(r'\d+\s*[–-]\s*\d+ of \d+|\d+ records?|Page \d+')))
              (e.widget as Text).data!,
        ];
        File('$_out\\pager_${width.toInt()}.txt').writeAsStringSync(
          '$label\t${pagerFacts.join(' ; ')}\n',
          mode: FileMode.append,
        );
        final RenderRepaintBoundary b =
            key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
        await tester.runAsync(() async {
          final ui.Image image = await b.toImage(pixelRatio: 1);
          final data = await image.toByteData(format: ui.ImageByteFormat.png);
          File('$_out\\${label.replaceAll(RegExp(r'[^A-Za-z0-9]+'), '_')}_${width.toInt()}.png')
              .writeAsBytesSync(data!.buffer.asUint8List());
        });
        // Close the screen's tab so the strip does not fill up.
        final Finder close = find.byIcon(Icons.close);
        if (close.evaluate().length > 1) {
          await tester.tap(close.last, warnIfMissed: false);
          await tester.pump(const Duration(milliseconds: 200));
        }
      } catch (error) {
        problems.add('$label: failed $error'.split('\n').first);
      }
    }
    File('$_out\\problems_${width.toInt()}.txt')
        .writeAsStringSync(problems.join('\n'));
    FlutterError.onError = original;
    await tester.pumpWidget(const SizedBox());
    await tester.runAsync(() => HttpOverrides.runWithHttpOverrides(
          () => session.api
              .updateUserPreferences({'default_landing_page': startScreen}),
          _Real(),
        ));
  }, timeout: const Timeout(Duration(minutes: 40)));
}
