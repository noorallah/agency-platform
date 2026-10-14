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

List<MenuItemSpec> _itemsOf(String section) => MenuLayout.settings.groups
    .singleWhere((group) => group.label == section)
    .items;

List<MenuItemSpec> _taxItems() => _itemsOf('Tax');

/// What the test saw the page ask for.
class _Seen {
  int reads = 0;
  final List<MenuItemSpec> windows = [];
  bool fail = false;
}

Future<_Seen> _pump(
  WidgetTester tester, {
  SettingsSubject subject = _tax,
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
        subject: subject,
        visible: visible ?? _itemsOf(subject.section),
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
    expect(SettingsSubjects.forSection('Stock'), isNull);
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

  // Row T2: Firm, Selling and Buying, on the same piece as Tax.
  group('Firm, Selling and Buying', () {
    /// A state for [subject] with every step as [state], except [todo].
    SettingsSectionState stateOf(
      SettingsSubject subject, {
      String state = 'OPTIONAL',
      Set<String> todo = const {},
    }) =>
        SettingsSectionState.fromJson({
          'section': subject.sectionCode,
          'todo_count': todo.length,
          'steps': [
            for (final SubjectStep step in subject.steps)
              {
                'code': step.code,
                'state': todo.contains(step.code) ? 'TODO' : state,
                'detail': '',
              },
          ],
        });

    const Map<SettingsSubject, List<String>> numbered = {
      SettingsSubjects.firm: [
        '1 Firm settings',
        '2 Financial years',
        '3 Numbering',
        '4 Goods types',
        '5 Custom fields',
        '6 Custom field rules',
        '7 Messaging',
        '8 Approval levels',
      ],
      SettingsSubjects.selling: [
        '1 Sales stages',
        '2 Salesmen',
        '3 Credit control',
        '4 Price floor',
        '5 Discount limits',
        '6 Loyalty scheme',
        '7 TCS',
      ],
      SettingsSubjects.buying: [
        '1 Purchase settings',
        '2 Approval limits',
        '3 Purchase budgets',
      ],
    };

    test('each names the items of its section, and the codes are fixed', () {
      for (final SettingsSubject subject in numbered.keys) {
        expect(
          {for (final SubjectStep step in subject.entries) step.path},
          {
            for (final MenuItemSpec item in _itemsOf(subject.section))
              item.path,
          },
          reason: subject.section,
        );
        expect(SettingsSubjects.forSection(subject.section), same(subject));
        expect(SettingsSubjects.forRoute(subject.route), same(subject));
        for (final SubjectStep tool in subject.tools) {
          expect(tool.code, isNull, reason: tool.path);
        }
      }
      // The server's codes, which a server branch answers for.
      expect([for (final SubjectStep s in SettingsSubjects.firm.steps) s.code],
          [
            'firm-profile',
            'financial-years',
            'numbering-series',
            'goods-types',
            'custom-fields',
            'custom-field-rules',
            'messaging',
            'approval-levels',
          ]);
      expect(
          [for (final SubjectStep s in SettingsSubjects.selling.steps) s.code],
          [
            'sales-stages',
            'salesmen',
            'credit-control',
            'price-floor',
            'discount-limits',
            'loyalty-scheme',
            'tcs',
          ]);
      expect(
          [for (final SubjectStep s in SettingsSubjects.buying.steps) s.code],
          ['purchase-settings', 'approval-limits', 'purchase-budgets']);
      expect(SettingsSubjects.firm.route, 'settings/subject/firm');
      expect(SettingsSubjects.selling.route, 'settings/subject/selling');
      expect(SettingsSubjects.buying.route, 'settings/subject/buying');
      expect(SettingsSubjects.firm.page.label, 'Firm settings');
      expect(SettingsSubjects.selling.page.label, 'Selling settings');
      expect(SettingsSubjects.buying.page.label, 'Buying settings');
      expect(SettingsSubjects.selling.tools, isEmpty);
      expect(SettingsSubjects.buying.tools, isEmpty);
    });

    for (final MapEntry<SettingsSubject, List<String>> entry
        in numbered.entries) {
      final SettingsSubject subject = entry.key;
      testWidgets(
          '${subject.section} opens on Start here, numbers its steps and '
          'reads once', (tester) async {
        final _Seen seen = await _pump(
          tester,
          subject: subject,
          state: () => stateOf(subject),
        );

        expect(_key('subject-start').hitTestable(), findsOneWidget);
        expect(find.text(subject.readyNote), findsOneWidget);
        for (final String label in entry.value) {
          expect(find.text(label), findsOneWidget, reason: label);
        }
        double left(String path) =>
            tester.getTopLeft(_key('subject-tab-$path')).dx;
        final List<double> order = [
          left('start'),
          for (final SubjectStep step in subject.entries) left(step.path),
        ];
        expect(order, [...order]..sort());

        for (final SubjectStep step in subject.entries) {
          await _tapTab(tester, step.path);
          expect(find.text(step.topLine).hitTestable(), findsOneWidget,
              reason: step.path);
        }
        await _tapTab(tester, 'start');
        expect(seen.reads, 1);
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets('Firm: no open year is the step to do', (tester) async {
      await _pump(
        tester,
        subject: SettingsSubjects.firm,
        // Tall enough that all eight rows and the links below are built.
        size: const Size(1366, 1400),
        state: () => stateOf(SettingsSubjects.firm,
            state: 'DONE', todo: {'financial-years'}),
      );

      expect(find.text('1 step to do.'), findsOneWidget);
      expect(_chip(tester, 'financial-years'), 'To do');
      expect(_chip(tester, 'firm-profile'), 'Done');
      expect(
        find.text('Business profile → Financial year → Numbering → '
            'Documents'),
        findsOneWidget,
      );
    });

    testWidgets("Firm: the person's own branch and warehouse sits apart",
        (tester) async {
      final _Seen seen = await _pump(
        tester,
        subject: SettingsSubjects.firm,
        state: () => stateOf(SettingsSubjects.firm),
      );
      const String tool = MenuLayout.workDefaultsRoute;

      expect(find.text('Yours: My branch and warehouse'), findsWidgets);
      // No row on Start here and no number: it is not a step of the firm.
      expect(_key('subject-row-$tool'), findsNothing);
      final double lastStepRight = tester
          .getTopRight(_key('subject-tab-${MenuLayout.approvalRulesRoute}'))
          .dx;
      expect(
        tester.getTopLeft(_key('subject-tab-$tool')).dx - lastStepRight,
        greaterThanOrEqualTo(24),
      );

      // It is a window, opened the way the menu opens it.
      await _tapTab(tester, tool);
      await tester.tap(_key('subject-window-$tool'));
      await tester.pumpAndSettle();
      expect([for (final MenuItemSpec item in seen.windows) item.path],
          [tool]);
      expect(seen.reads, 1);
    });

    testWidgets('Selling: a step that is a screen shows it, a window opens',
        (tester) async {
      final _Seen seen = await _pump(
        tester,
        subject: SettingsSubjects.selling,
        state: () =>
            stateOf(SettingsSubjects.selling, todo: {'salesmen'}),
      );

      expect(find.text('1 step to do.'), findsOneWidget);
      expect(_chip(tester, 'salesmen'), 'To do');
      await _tapTab(tester, 'sales/salesmen');
      expect(_key('screen-sales/salesmen').hitTestable(), findsOneWidget);
      await _tapTab(tester, MenuLayout.salesStagesRoute);
      await tester.tap(_key('subject-window-${MenuLayout.salesStagesRoute}'));
      await tester.pumpAndSettle();
      expect([for (final MenuItemSpec item in seen.windows) item.path],
          [MenuLayout.salesStagesRoute]);
    });

    testWidgets('a step the person may not open has no tab and no row',
        (tester) async {
      await _pump(
        tester,
        subject: SettingsSubjects.buying,
        state: () => stateOf(SettingsSubjects.buying),
        visible: [
          for (final MenuItemSpec item in _itemsOf('Buying'))
            if (item.path != MenuLayout.purchaseBudgetsRoute) item,
        ],
      );

      expect(_key('subject-tab-${MenuLayout.purchaseBudgetsRoute}'),
          findsNothing);
      expect(_key('subject-row-${MenuLayout.purchaseBudgetsRoute}'),
          findsNothing);
      expect(find.text('1 Purchase settings'), findsOneWidget);
      expect(find.text('2 Approval limits'), findsOneWidget);
    });

    testWidgets('Settings shows each section as one card', (tester) async {
      tester.view.physicalSize = const Size(1366, 768);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final List<SettingsSubject> subjects = [];
      final List<MenuItemSpec> opened = [];
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: SetUpPage(
            settings: MenuLayout.settings,
            section: 'Firm',
            onOpen: opened.add,
            onOpenSubject: subjects.add,
          ),
        ),
      ));
      await tester.pumpAndSettle();

      for (final SettingsSubject subject in numbered.keys) {
        await tester.tap(_key('setup-section-${subject.section}'));
        await tester.pumpAndSettle();
        for (final MenuItemSpec item in _itemsOf(subject.section)) {
          expect(_key('setup-card-${item.path}'), findsNothing,
              reason: item.path);
        }
        await tester.tap(_key('setup-subject-${subject.sectionCode}'));
        await tester.pumpAndSettle();
      }
      expect(subjects, numbered.keys.toList());
      expect(opened, isEmpty);

      // Search still finds each old item by its own name and opens it.
      await tester.enterText(_key('setup-search'), 'Credit Control');
      await tester.pumpAndSettle();
      await tester.tap(_key('setup-card-${MenuLayout.creditControlRoute}'));
      await tester.pumpAndSettle();
      expect([for (final MenuItemSpec item in opened) item.path],
          [MenuLayout.creditControlRoute]);
    });
  });
}