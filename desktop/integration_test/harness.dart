import 'package:agency_desktop/main_phase2.dart' as app;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Who the flows sign in as; override with `--dart-define=IT_EMAIL=...`.
const String itEmail = String.fromEnvironment('IT_EMAIL',
    defaultValue: 'whole01.admin@agency.local');
const String itPassword =
    String.fromEnvironment('IT_PASSWORD', defaultValue: 'DemoAdmin@12345');

/// Every piece of text on screen, in paint order.
///
/// A screenshot of this app comes out blank on Windows, so this is how a flow
/// says what it was looking at when it gave up.
List<String> textOnScreen(WidgetTester tester) => <String>[
      for (final Text text in tester.widgetList<Text>(find.byType(Text)))
        if ((text.data ?? text.textSpan?.toPlainText() ?? '').trim().isNotEmpty)
          (text.data ?? text.textSpan!.toPlainText()).trim(),
    ];

/// Pump real frames until [finder] matches, or fail naming what was on screen.
///
/// `pumpAndSettle` cannot be used against a live server: a spinner never
/// settles, and a request takes as long as it takes.
Future<void> pumpUntil(
  WidgetTester tester,
  Finder finder, {
  Duration timeout = const Duration(seconds: 30),
  String? waitingFor,
}) async {
  final DateTime deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    if (finder.evaluate().isNotEmpty) return;
  }
  fail('Timed out waiting for ${waitingFor ?? finder.describeMatch(Plurality.one)}.'
      '\nOn screen: ${textOnScreen(tester).take(80).join(' | ')}');
}

/// The field whose label reads [label].
Finder fieldLabelled(String label) => find.ancestor(
      of: find.text(label),
      matching: find.byType(TextField),
    );

/// Start the real phase 2 app and sign in through its own sign-in screen.
Future<void> startAndSignIn(WidgetTester tester) async {
  // The app installs its own error handlers at startup. The test framework
  // reports failures through these two and checks at the end that they are the
  // ones it set, so they go back as soon as the app is up.
  final FlutterExceptionHandler? reportError = FlutterError.onError;
  final ErrorWidgetBuilder errorWidget = ErrorWidget.builder;
  await app.main();
  await pumpUntil(tester, find.text('Username / Email'),
      waitingFor: 'the sign-in screen');
  FlutterError.onError = reportError;
  ErrorWidget.builder = errorWidget;
  await tester.enterText(fieldLabelled('Username / Email').first, itEmail);
  await tester.enterText(fieldLabelled('Password').first, itPassword);
  await tester.pump();
  await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
  await pumpUntil(tester, find.textContaining('Search or jump to'),
      waitingFor: 'the signed-in frame');
}
