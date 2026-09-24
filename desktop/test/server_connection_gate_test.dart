import 'package:agency_desktop/app.dart';
import 'package:agency_desktop/core/branding/branding_config.dart';
import 'package:agency_desktop/ui/server_connection_gate.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The screen between starting the app and signing in. What it has to get
/// right: it keeps asking while the service comes up, it stops after a minute
/// and says what is wrong, it offers the two ways forward, and it fits the
/// smallest screen the product supports.

Future<void> _pumpGate(
  WidgetTester tester, {
  required Future<bool> Function() probe,
  required VoidCallback onConnected,
  VoidCallback? onContinue,
  Future<void> Function()? onOpenLogs,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: ServerConnectionGate(
        probe: probe,
        serverUrl: 'http://127.0.0.1:8000',
        onConnected: onConnected,
        onContinueAnyway: onContinue ?? () {},
        onOpenLogs: onOpenLogs,
      ),
    ),
  );
}

void main() {
  testWidgets('keeps asking every two seconds until the server answers',
      (tester) async {
    int asked = 0;
    bool connected = false;
    await _pumpGate(
      tester,
      probe: () async => ++asked >= 3,
      onConnected: () => connected = true,
    );

    expect(find.text('Connecting to server…'), findsOneWidget);
    expect(find.text('http://127.0.0.1:8000'), findsOneWidget);
    await tester.pump();
    expect(asked, 1);
    expect(connected, isFalse);

    await tester.pump(const Duration(seconds: 2));
    expect(asked, 2);
    await tester.pump(const Duration(seconds: 2));
    expect(asked, 3);
    expect(connected, isTrue);
  });

  testWidgets(
      'after a minute it says the service is not running, and Retry asks again',
      (tester) async {
    int asked = 0;
    bool answer = false;
    bool connected = false;
    bool openedLogs = false;
    await _pumpGate(
      tester,
      probe: () async {
        asked++;
        return answer;
      },
      onConnected: () => connected = true,
      onOpenLogs: () async => openedLogs = true,
    );

    for (int second = 0; second < 62; second += 2) {
      await tester.pump(const Duration(seconds: 2));
    }
    expect(asked, 30, reason: 'every 2 s for 60 s');
    expect(
      find.text('The Agency Platform Server service is not running'),
      findsOneWidget,
    );
    expect(find.text('Retry'), findsOneWidget);
    expect(find.text('Open logs folder'), findsOneWidget);
    expect(find.text('Continue to sign-in'), findsOneWidget);
    expect(tester.takeException(), isNull, reason: 'overflow-free at 1366x768');

    await tester.tap(find.text('Open logs folder'));
    await tester.pump();
    expect(openedLogs, isTrue);

    answer = true;
    await tester.tap(find.text('Retry'));
    await tester.pump();
    await tester.pump();
    expect(connected, isTrue);
  });

  testWidgets('a probe that never returns does not stall the countdown',
      (tester) async {
    int asked = 0;
    await _pumpGate(
      tester,
      probe: () {
        asked++;
        return Future<bool>.delayed(const Duration(hours: 1), () => true);
      },
      onConnected: () {},
    );
    // Five seconds of waiting per probe, then the two-second interval.
    await tester.pump(const Duration(seconds: 5));
    await tester.pump(const Duration(seconds: 2));
    expect(asked, 2);
    // Let the abandoned probes' timers finish so the test ends clean.
    await tester.pump(const Duration(hours: 2));
  });

  testWidgets('Continue to sign-in is the way past a wrong address',
      (tester) async {
    bool continued = false;
    await _pumpGate(
      tester,
      probe: () async => false,
      onConnected: () {},
      onContinue: () => continued = true,
    );
    for (int second = 0; second < 62; second += 2) {
      await tester.pump(const Duration(seconds: 2));
    }
    await tester.tap(find.text('Continue to sign-in'));
    expect(continued, isTrue);
  });

  test('the server address: the user, then Setup, then the build', () {
    expect(
      resolveServerUrl(
        saved: 'http://192.168.1.9:8000',
        installed: 'http://127.0.0.1:8000',
        compiled: 'http://localhost:8000',
      ),
      'http://192.168.1.9:8000',
    );
    // The preferences default means nobody chose; Setup's address wins.
    expect(
      resolveServerUrl(
        saved: 'http://localhost:8000',
        installed: 'http://192.168.1.50:8000',
        compiled: 'http://localhost:8000',
      ),
      'http://192.168.1.50:8000',
    );
    expect(
      resolveServerUrl(saved: '', installed: '', compiled: 'http://x:1'),
      'http://x:1',
    );
  });

  test('branding.json may name the server Setup pointed the app at', () {
    Map<String, dynamic> json(Map<String, dynamic> extra) => {
          'app_name': 'A',
          'window_name': 'A',
          'product_name': 'A',
          'company_name': 'A',
          'version': '1.0.0',
          'support_email': 'a@example.test',
          'support_website': 'https://example.test',
          'copyright': 'A',
          'login_background_color': '#FFFFFF',
          'login_accent_color': '#000000',
          ...extra,
        };
    expect(BrandingConfig.fromJson(json({})).serverUrl, '');
    expect(
      BrandingConfig.fromJson(json({'server_url': 'http://127.0.0.1:8000'}))
          .serverUrl,
      'http://127.0.0.1:8000',
    );
  });
}
