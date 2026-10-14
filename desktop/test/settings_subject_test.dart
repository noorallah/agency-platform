// Settings: one screen per subject (the owner's wireframe, 2026-10-13;
// backlog 148, row T1). Settings > Tax is one screen: a Start here tab that
// says how far the firm has got, the steps in order, the checking tools set
// apart -- and one read of the server for all of it.

import 'package:agency_desktop/models/settings_sections.dart';
import 'package:agency_desktop/phase2/menu_layout.dart';
import 'package:agency_desktop/phase2/set_up_page.dart';
import 'package:agency_desktop/phase2/settings_subject.dart';
import 'package:agency_desktop/phase2/settings_subject_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const SettingsSubject _tax = SettingsSubjects.tax;

const String _rates = 'administration/tax-configuration';
const String _rules = 'administration/tax-rules-page';
const String _settings = 'administration/tax-settings';
const String _simulator = 'administration/tax-rule-simulator';
const String _log = 'administration/tax-execution-log';

/// A firm set up from the GST template, as the server answers for it.
SettingsSectionState _templateFirm() => SettingsSectionState.fromJson({
      'section': 'tax',
      'todo_count': 0,
      'steps': [
        {
          'code': 'rates-and-profiles',
          'state': 'DONE',
          'detail': '5 profiles, from the GST template',
        },
        {'code': 'tax-rules', 'state': 'DONE', 'detail': '12 rules'},
        {'code': 'tax-settings', 'state': 'OPTIONAL', 'detail': 'As it came'},
        {'code': 'gst-documents', 'state': 'OPTIONAL', 'detail': 'Off'},
        {'code': 'tds-purchases', 'state': 'OPTIONAL', 'detail': 'Off'},
      ],
    });

SettingsSectionState _emptyFirm() => SettingsSectionState.fromJson({
      'section': 'tax',
      'todo_count': 2,
      'steps': [
        {'code': 'rates-and-profiles', 'state': 'TODO', 'detail': 'None yet'},
        {'code': 'tax-rules', 'state': 'TODO', 'detail': 'No rule yet'},
        {'code': 'tax-settings', 'state': 'OPTIONAL', 'detail': 'As it came'},
        {'code': 'gst-documents', 'state': 'OPTIONAL', 'detail': 'Off'},
        {'code': 'tds-purchases', 'state': 'OPTIONAL', 'detail': 'Off'},
      ],
    });

List<MenuItemSpec> _taxItems() => MenuLayout.settings.groups
    .singleWhere((group) => group.label == 'Tax')
    .items;

/// What the test saw the page ask for.
class _Seen {
  int reads = 0;
  final List<MenuItemSpec> windows = [];
  bool fail = false;
}

Future<_Seen> _pump(
  WidgetTester tester, {
  Size size = const Size(1366, 768),
  List<MenuItemSpec>? visible,
  SettingsSectionState Function()? state,
  bool fail = false,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final _Seen seen = _Seen()..fail = fail;
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: SettingsSubjectPage(
        subject: _tax,
        visible: visible ?? _taxItems(),
        loadState: () async {
          seen.reads++;
          if (seen.fail) throw StateError('no server');
          return (state ?? _templateFirm)();
        },
        // Stands for today's screen: a box somebody may be half-way through.
        screenFor: (item) => Padding(
          padding: const EdgeInsets.all(8),
          child: TextField(key: ValueKey('screen-${item.path}')),
        ),
        openWindow: seen.windows.add,
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return seen;
}

Finder _key(String key) => find.byKey(ValueKey(key));

Future<void> _tapTab(WidgetTester tester, String path) async {
  await tester.ensureVisible(_key('subject-tab-$path'));
  await tester.tap(_key('subject-tab-$path'));
  await tester.pumpAndSettle();
}

String _chip(WidgetTester tester, String code) => tester
    .widget<Text>(find.descendant(
      of: _key('subject-chip-$code'),
      matching: find.byType(Text),
    ))
    .data!;

void main() {
  test('a step names an item of the Settings menu, never its own screen', () {
    for (final SubjectStep step in _tax.entries) {
      expect(MenuLayout.settings.item(step.path), isNotNull,
          reason: step.path);
    }
    // Every item of the section has a tab: none is left without a way in.
    expect(
      {for (final SubjectStep step in _tax.entries) step.path},
      {for (final MenuItemSpec item in _taxItems()) item.path},
    );
    expect(SettingsSubjects.forSection('Tax'), same(_tax));
    expect(SettingsSubjects.forRoute(MenuLayout.taxSubjectRoute), same(_tax));
    expect(SettingsSubjects.forSection('Selling'), isNull);
    expect(_tax.page.label, 'Tax settings');
  });

  testWidgets('opens on Start here, and a template firm reads ready',
      (tester) async {
    await _pump(tester);

    expect(_key('subject-start').hitTestable(), findsOneWidget);
    expect(find.text('Tax is ready for this firm.'), findsOneWidget);
    expect(_chip(tester, 'rates-and-profiles'), 'Done');
    expect(_chip(tester, 'tax-rules'), 'Done');
    expect(_chip(tester, 'tax-settings'), 'Optional');
    expect(_chip(tester, 'gst-documents'), 'Optional');
    expect(_chip(tester, 'tds-purchases'), 'Optional');
    expect(find.text('5 profiles, from the GST template'), findsOneWidget);
    expect(find.text('12 rules'), findsOneWidget);
    expect(
      find.text('Rate → Profile (GST 18%) → Rule picks the profile → '
          'Line on a bill'),
      findsOneWidget,
    );
  });

  testWidgets('a firm with steps left says how many', (tester) async {
    await _pump(tester, state: _emptyFirm);

    expect(find.text('2 steps to do.'), findsOneWidget);
    expect(_chip(tester, 'rates-and-profiles'), 'To do');
    expect(find.text('Tax is ready for this firm.'), findsNothing);
  });

  testWidgets('each Open button shows its step, under what the step is for',
      (tester) async {
    await _pump(tester);

    for (final SubjectStep step in _tax.steps) {
      await _tapTab(tester, 'start');
      await tester.ensureVisible(_key('subject-open-${step.path}'));
      await tester.tap(_key('subject-open-${step.path}'));
      await tester.pumpAndSettle();
      expect(_key('subject-body-${step.path}').hitTestable(), findsOneWidget,
          reason: step.path);
      expect(find.text(step.topLine).hitTestable(), findsOneWidget,
          reason: step.path);
      expect(_key('subject-start').hitTestable(), findsNothing);
    }
    // A step that is a screen shows that screen.
    await _tapTab(tester, _rules);
    expect(_key('screen-$_rules').hitTestable(), findsOneWidget);
  });

  testWidgets('a step that is a window opens it the way the menu does',
      (tester) async {
    final _Seen seen = await _pump(tester);

    await _tapTab(tester, MenuLayout.gstDocumentsRoute);
    expect(find.text('Open GST on documents'), findsOneWidget);
    expect(find.text('Now: Off').hitTestable(), findsOneWidget);
    await tester.tap(_key('subject-window-${MenuLayout.gstDocumentsRoute}'));
    await tester.pumpAndSettle();

    await _tapTab(tester, MenuLayout.tds194qSettingsRoute);
    expect(find.text('Open TDS on purchases'), findsOneWidget);
    await tester
        .tap(_key('subject-window-${MenuLayout.tds194qSettingsRoute}'));
    await tester.pumpAndSettle();

    expect(
      [for (final MenuItemSpec item in seen.windows) item.path],
      [MenuLayout.gstDocumentsRoute, MenuLayout.tds194qSettingsRoute],
    );
    // The window closing reads nothing by itself.
    expect(seen.reads, 1);
  });

  testWidgets('the steps are numbered in order and the tools come after',
      (tester) async {
    await _pump(tester);

    expect(find.text('1 Rates and profiles'), findsOneWidget);
    expect(find.text('2 Tax rules'), findsOneWidget);
    expect(find.text('3 Tax settings'), findsOneWidget);
    expect(find.text('4 GST on documents'), findsOneWidget);
    expect(find.text('5 TDS on purchases'), findsOneWidget);
    expect(find.text('Check: Rule simulator'), findsWidgets);
    expect(find.text('Check: Execution log'), findsWidgets);

    double left(String path) =>
        tester.getTopLeft(_key('subject-tab-$path')).dx;
    final List<double> order = [
      left('start'),
      for (final SubjectStep step in _tax.entries) left(step.path),
    ];
    expect(order, [...order]..sort());
    // Set apart: a gap before the first tool wider than any between steps.
    final double lastStepRight = tester
        .getTopRight(_key('subject-tab-${MenuLayout.tds194qSettingsRoute}'))
        .dx;
    expect(left(_simulator) - lastStepRight, greaterThanOrEqualTo(24));
  });

  testWidgets('the state is read once, however many tabs are opened',
      (tester) async {
    final _Seen seen = await _pump(tester);

    for (final SubjectStep step in _tax.entries) {
      await _tapTab(tester, step.path);
    }
    await _tapTab(tester, 'start');
    for (final SubjectStep step in _tax.entries) {
      await _tapTab(tester, step.path);
    }
    await _tapTab(tester, 'start');
    expect(seen.reads, 1);

    // Refresh is the one thing that asks again.
    await tester.tap(_key('subject-refresh'));
    await tester.pumpAndSettle();
    expect(seen.reads, 2);
  });

  testWidgets('a screen half typed in is still there after another tab',
      (tester) async {
    await _pump(tester);

    await _tapTab(tester, _rates);
    await tester.enterText(_key('screen-$_rates'), 'GST 18%');
    await _tapTab(tester, _rules);
    await _tapTab(tester, 'start');
    await _tapTab(tester, _rates);

    expect(find.text('GST 18%').hitTestable(), findsOneWidget);
    // A tab never opened has built nothing.
    expect(_key('screen-$_settings'), findsNothing);
  });

  testWidgets('a failed read still lists the steps, and Retry asks again',
      (tester) async {
    final _Seen seen = await _pump(tester, fail: true);

    expect(find.text('The states of these steps could not be read.'),
        findsOneWidget);
    expect(_key('subject-chip-rates-and-profiles'), findsNothing);
    for (final SubjectStep step in _tax.steps) {
      expect(_key('subject-row-${step.path}'), findsOneWidget);
    }
    expect(seen.reads, 1);

    seen.fail = false;
    await tester.tap(_key('subject-retry'));
    await tester.pumpAndSettle();
    expect(seen.reads, 2);
    expect(_key('subject-retry'), findsNothing);
    expect(_chip(tester, 'rates-and-profiles'), 'Done');
  });

  testWidgets('an item the person is not offered has no tab and no row',
      (tester) async {
    await _pump(
      tester,
      visible: [
        for (final MenuItemSpec item in _taxItems())
          if (item.path != _rules &&
              item.path != MenuLayout.tds194qSettingsRoute &&
              item.path != _log)
            item,
      ],
    );

    expect(_key('subject-tab-$_rules'), findsNothing);
    expect(_key('subject-row-$_rules'), findsNothing);
    expect(_key('subject-tab-${MenuLayout.tds194qSettingsRoute}'),
        findsNothing);
    expect(_key('subject-tab-$_log'), findsNothing);
    // The numbering is that of the full list.
    expect(find.text('1 Rates and profiles'), findsOneWidget);
    expect(find.text('3 Tax settings'), findsOneWidget);
    expect(find.text('4 GST on documents'), findsOneWidget);
    expect(find.text('Check: Rule simulator'), findsWidgets);
  });

  testWidgets('nothing overflows in a small window', (tester) async {
    await _pump(tester, size: const Size(800, 600), state: _emptyFirm);
    expect(tester.takeException(), isNull);

    for (final SubjectStep step in _tax.entries) {
      await _tapTab(tester, step.path);
      expect(tester.takeException(), isNull, reason: step.path);
    }
    await _tapTab(tester, 'start');
    expect(tester.takeException(), isNull);

    // Narrower still, as beside the classic sidebar.
    tester.view.physicalSize = const Size(560, 600);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('Settings shows Tax as one card, and search finds each item',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final List<SettingsSubject> subjects = [];
    final List<MenuItemSpec> opened = [];
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SetUpPage(
          settings: MenuLayout.settings,
          section: 'Tax',
          onOpen: opened.add,
          onOpenSubject: subjects.add,
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(_key('setup-subject-tax'), findsOneWidget);
    expect(find.text('GST rates and rules, GST on documents, TDS'),
        findsOneWidget);
    expect(find.text('Opens one screen'), findsOneWidget);
    for (final MenuItemSpec item in _taxItems()) {
      expect(_key('setup-card-${item.path}'), findsNothing);
    }
    await tester.tap(_key('setup-subject-tax'));
    await tester.pumpAndSettle();
    expect(subjects, [_tax]);
    expect(opened, isEmpty);

    // A section with no subject is cards as before.
    await tester.tap(_key('setup-section-Stock'));
    await tester.pumpAndSettle();
    expect(_key('setup-card-inventory/inventory-settings'), findsOneWidget);

    // Search still names each item, and opens it as it always did.
    await tester.enterText(_key('setup-search'), 'Tax Rules');
    await tester.pumpAndSettle();
    expect(_key('setup-subject-tax'), findsNothing);
    await tester.tap(_key('setup-card-$_rules'));
    await tester.pumpAndSettle();
    expect([for (final MenuItemSpec item in opened) item.path], [_rules]);
  });
}
