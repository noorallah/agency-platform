// The app's own title bar (D-UI-6, decision B9 option 1): the agency and the
// selected firm are drawn once, in the window's title bar, and nothing is
// added where the window keeps the operating system's own.

import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:agency_desktop/phase2/agency_header.dart';
import 'package:agency_desktop/phase2/app_title_bar.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:window_manager/window_manager.dart';

const Key _page = ValueKey<String>('page');

Future<void> _pump(WidgetTester tester, {double width = 1366}) async {
  tester.view.physicalSize = Size(width, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    theme: ThemeRegistry.themeFor(
      palette: AppPalette.neutral,
      brightness: Brightness.light,
    ),
    builder: (context, child) =>
        AppTitleBar.wrap(context, child ?? const SizedBox.shrink()),
    home: Builder(
      builder: (context) => Scaffold(
        body: SizedBox.expand(
          key: _page,
          child: Text('${MediaQuery.sizeOf(context).height}'),
        ),
      ),
    ),
  ));
  await tester.pump();
}

void main() {
  setUp(() {
    AppTitleBar.enabled = false;
    AppTitleBar.content.value = const TitleBarContent();
  });
  tearDown(() => AppTitleBar.enabled = false);

  testWidgets('nothing is added while the window keeps its own title bar',
      (tester) async {
    await _pump(tester);
    expect(find.byType(AppTitleBarStrip), findsNothing);
    expect(tester.getTopLeft(find.byKey(_page)).dy, 0);
    expect(find.text('768.0'), findsOneWidget);
  });

  testWidgets('the strip sits above the page, which is told its real height',
      (tester) async {
    AppTitleBar.enabled = true;
    AppTitleBar.showText('Ledger Desk - Sign in');
    await _pump(tester);
    expect(find.byType(AppTitleBarStrip), findsOneWidget);
    expect(find.text('Ledger Desk - Sign in'), findsOneWidget);
    expect(tester.getTopLeft(find.byKey(_page)).dy, kWindowCaptionHeight);
    expect(find.text('${768 - kWindowCaptionHeight}'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the agency, its tagline and the firm are drawn once',
      (tester) async {
    AppTitleBar.enabled = true;
    AppTitleBar.showAgency(
      const AgencyIdentity(name: 'Trio Distributors', tagline: 'Wholesale'),
      'Head Office Firm',
    );
    await _pump(tester);
    expect(find.byKey(const ValueKey('agency-header-name')), findsOneWidget);
    expect(find.text('Trio Distributors'), findsOneWidget);
    expect(find.text('Wholesale'), findsOneWidget);
    expect(find.text('Head Office Firm'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('no firm is named when none is selected, and a change shows',
      (tester) async {
    AppTitleBar.enabled = true;
    const AgencyIdentity agency = AgencyIdentity(name: 'Trio Distributors');
    AppTitleBar.showAgency(agency, null);
    await _pump(tester);
    expect(find.byKey(const ValueKey('agency-header-firm')), findsNothing);
    expect(find.text('>'), findsNothing);
    AppTitleBar.showAgency(agency, 'Second Firm');
    await tester.pump();
    expect(find.text('Second Firm'), findsOneWidget);
  });

  testWidgets('long names are cut short, not overflowed, at the least width',
      (tester) async {
    AppTitleBar.enabled = true;
    AppTitleBar.showAgency(
      const AgencyIdentity(
        name: 'A Very Long Agency Name That Goes On And On Private Limited',
        tagline: 'A tagline that is also much longer than the bar has room for',
      ),
      'A Firm With A Name Nobody Could Fit In A Title Bar Private Limited',
    );
    await _pump(tester, width: 960);
    expect(tester.takeException(), isNull);
  });
}
