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
    expect(SettingsSubjects.forSection('System'), isNull);
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
    // The section list is built as it scrolls, and System is near its end.
    await tester.scrollUntilVisible(_key('setup-section-System'), 200,
        scrollable: find.byType(Scrollable).first);
    await tester.tap(_key('setup-section-System'));
    await tester.pumpAndSettle();
    expect(_key('setup-card-settings/audit-logs'), findsOneWidget);

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

  // Row T2: Stock, Business profile and Pricing, on the same piece.
  group('Stock, Business profile and Pricing', () {
    SettingsSectionState stateOf(SettingsSubject subject) =>
        SettingsSectionState.fromJson({
          'section': subject.sectionCode,
          'todo_count': 0,
          'steps': [
            for (final SubjectStep step in subject.steps)
              {'code': step.code, 'state': 'OPTIONAL', 'detail': ''},
          ],
        });

    const Map<SettingsSubject, List<String>> numbered = {
      SettingsSubjects.stock: [
        '1 Adjustment reasons',
        '2 Adjustment limits',
        '3 Batch rules',
      ],
      SettingsSubjects.businessProfile: [
        '1 Profile assignment',
        '2 Feature management',
        '3 Module configuration',
        '4 Attribute definitions',
        '5 Mandatory attributes',
        '6 Unit sets',
      ],
      SettingsSubjects.pricing: [
        '1 Price lists',
        '2 Price levels',
        '3 Promotions',
        '4 Loyalty',
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
        if (subject != SettingsSubjects.stock) {
          expect(subject.tools, isEmpty, reason: subject.section);
        }
      }
      // Inventory Settings is the person's own, so it stands apart.
      expect(SettingsSubjects.stock.toolsLabel, 'Yours');
      expect([for (final SubjectStep s in SettingsSubjects.stock.tools) s.path],
          ['inventory/inventory-settings']);
      // The server's codes, which a server branch answers for.
      expect([for (final SubjectStep s in SettingsSubjects.stock.steps) s.code],
          [
            'adjustment-reasons',
            'adjustment-limits',
            'batch-rules',
          ]);
      expect(
          [
            for (final SubjectStep s in SettingsSubjects.businessProfile.steps)
              s.code
          ],
          [
            'profile-assignment',
            'feature-management',
            'module-configuration',
            'attribute-definitions',
            'mandatory-attributes',
            'unit-sets',
          ]);
      expect(
          [for (final SubjectStep s in SettingsSubjects.pricing.steps) s.code],
          ['price-lists', 'price-levels', 'promotions', 'loyalty']);
      expect(SettingsSubjects.stock.route, 'settings/subject/stock');
      expect(SettingsSubjects.businessProfile.route,
          'settings/subject/business-profile');
      expect(SettingsSubjects.pricing.route, 'settings/subject/pricing');
      expect(SettingsSubjects.stock.page.label, 'Stock settings');
      expect(SettingsSubjects.businessProfile.page.label,
          'Business profile settings');
      expect(SettingsSubjects.pricing.page.label, 'Pricing settings');
      // In the order the menu lists the sections.
      expect([for (final SettingsSubject s in SettingsSubjects.all) s.section],
          [
            for (final MenuGroupSpec group in MenuLayout.settings.groups)
              if (SettingsSubjects.forSection(group.label) != null)
                group.label,
          ]);
      expect([for (final SettingsSubject s in SettingsSubjects.all) s.section],
          [
            'Firm',
            'Selling',
            'Buying',
            'Stock',
            'Tax',
            'Business profile',
            'Pricing',
            'Territories & routes',
            'Account structure',
            'Party lists',
            'Item lists',
            'Locations',
            'People',
            'Firms',
          ]);
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

    testWidgets('Stock: a step that is a screen shows it, a window opens',
        (tester) async {
      final _Seen seen = await _pump(
        tester,
        subject: SettingsSubjects.stock,
        state: () => stateOf(SettingsSubjects.stock),
      );

      await _tapTab(tester, 'inventory/adjustment-reasons');
      expect(_key('screen-inventory/adjustment-reasons').hitTestable(),
          findsOneWidget);
      await _tapTab(tester, MenuLayout.batchRulesRoute);
      await tester.tap(_key('subject-window-${MenuLayout.batchRulesRoute}'));
      await tester.pumpAndSettle();
      expect([for (final MenuItemSpec item in seen.windows) item.path],
          [MenuLayout.batchRulesRoute]);
      expect(seen.reads, 1);
    });

    testWidgets('Settings shows each section as one card, Set up included',
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
            section: 'Firm',
            onOpen: opened.add,
            onOpenSubject: subjects.add,
          ),
        ),
      ));
      await tester.pumpAndSettle();

      for (final SettingsSubject subject in numbered.keys) {
        await tester.ensureVisible(_key('setup-section-${subject.section}'));
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

      // Pricing is a Set up section: its card says so, and is still one.
      expect(
        find.text('${MenuPart.setUp.note} Everything here is on one screen, '
            'in the order it is set up in.'),
        findsOneWidget,
      );

      // Search still finds each old item by its own name and opens it.
      for (final String path in [
        MenuLayout.batchRulesRoute,
        'administration/unit-sets',
        'sales/price-lists',
      ]) {
        await tester.enterText(
            _key('setup-search'), MenuLayout.settings.item(path)!.label);
        await tester.pumpAndSettle();
        await tester.tap(_key('setup-card-$path'));
        await tester.pumpAndSettle();
      }
      expect([for (final MenuItemSpec item in opened) item.path], [
        MenuLayout.batchRulesRoute,
        'administration/unit-sets',
        'sales/price-lists',
      ]);
    });
  });

  // Row T2: Territories & routes, Account structure and Party lists, three
  // Set up sections on the same piece.
  group('Territories & routes, Account structure and Party lists', () {
    SettingsSectionState stateOf(SettingsSubject subject,
            {Map<String, String> states = const {}}) =>
        SettingsSectionState.fromJson({
          'section': subject.sectionCode,
          'todo_count': states.values.where((s) => s == 'TODO').length,
          'steps': [
            for (final SubjectStep step in subject.steps)
              {
                'code': step.code,
                'state': states[step.code] ?? 'OPTIONAL',
                'detail': '',
              },
          ],
        });

    const Map<SettingsSubject, List<String>> numbered = {
      SettingsSubjects.territories: [
        '1 Territories',
        '2 Route types',
        '3 Route builder',
        '4 Transporters',
      ],
      SettingsSubjects.accountStructure: [
        '1 Control accounts',
        '2 Cost centres',
        '3 Profit centres',
      ],
      SettingsSubjects.partyLists: [
        '1 Customer groups',
        '2 Vendor categories',
        '3 Vendor types',
        '4 Licence types',
        '5 Licence check',
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
        expect(subject.tools, isEmpty, reason: subject.section);
        // The step codes are the menu item keys.
        for (final SubjectStep step in subject.steps) {
          expect(step.path.split('/').last, step.code, reason: step.path);
        }
      }
      // The server's codes, which a server branch answers for.
      expect(
          [
            for (final SubjectStep s in SettingsSubjects.territories.steps)
              s.code
          ],
          ['territories', 'route-types', 'route-builder', 'transporters']);
      expect(
          [
            for (final SubjectStep s
                in SettingsSubjects.accountStructure.steps)
              s.code
          ],
          ['control-accounts', 'cost-centers', 'profit-centers']);
      expect(
          [
            for (final SubjectStep s in SettingsSubjects.partyLists.steps)
              s.code
          ],
          [
            'customer-groups',
            'vendor-categories',
            'vendor-types',
            'licence-types',
            'licence-check-settings',
          ]);
      expect(
          SettingsSubjects.territories.route, 'settings/subject/territories');
      expect(SettingsSubjects.accountStructure.route,
          'settings/subject/account-structure');
      expect(SettingsSubjects.partyLists.route, 'settings/subject/party-lists');
      expect(SettingsSubjects.territories.page.label,
          'Territories & routes settings');
      expect(SettingsSubjects.accountStructure.page.label,
          'Account structure settings');
      expect(SettingsSubjects.partyLists.page.label, 'Party lists settings');
      // Route Builder says it needs a territory.
      expect(SettingsSubjects.territories.steps[2].topLine,
          contains('Needs a territory'));
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
          // Every step here is a screen, Customer Groups included.
          expect(_key('screen-${step.path}').hitTestable(), findsOneWidget,
              reason: step.path);
        }
        await _tapTab(tester, 'start');
        expect(seen.reads, 1);
        expect(seen.windows, isEmpty);
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets('Account structure: unmapped purposes leave Control accounts '
        'To do', (tester) async {
      await _pump(
        tester,
        subject: SettingsSubjects.accountStructure,
        state: () => stateOf(
          SettingsSubjects.accountStructure,
          states: {'control-accounts': 'TODO'},
        ),
      );

      expect(find.text(SettingsSubjects.accountStructure.readyNote),
          findsNothing);
      expect(_chip(tester, 'control-accounts'),
          isNot(_chip(tester, 'cost-centers')));
      expect(tester.takeException(), isNull);
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
        await tester.ensureVisible(_key('setup-section-${subject.section}'));
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
      for (final String path in [
        'sales/route-builder',
        'accounting/control-accounts',
        MenuLayout.customerGroupsRoute,
      ]) {
        await tester.enterText(
            _key('setup-search'), MenuLayout.settings.item(path)!.label);
        await tester.pumpAndSettle();
        await tester.tap(_key('setup-card-$path'));
        await tester.pumpAndSettle();
      }
      expect([for (final MenuItemSpec item in opened) item.path], [
        'sales/route-builder',
        'accounting/control-accounts',
        MenuLayout.customerGroupsRoute,
      ]);
    });
  });

  // Row T2: Item lists and Locations, two more Set up sections on the same
  // piece.
  group('Item lists and Locations', () {
    SettingsSectionState stateOf(SettingsSubject subject,
            {Map<String, String> states = const {},
            Map<String, String> details = const {}}) =>
        SettingsSectionState.fromJson({
          'section': subject.sectionCode,
          'todo_count': states.values.where((s) => s == 'TODO').length,
          'steps': [
            for (final SubjectStep step in subject.steps)
              {
                'code': step.code,
                'state': states[step.code] ?? 'OPTIONAL',
                'detail': details[step.code] ?? '',
              },
          ],
        });

    const Map<SettingsSubject, List<String>> numbered = {
      SettingsSubjects.itemLists: [
        '1 Units of Measure',
        '2 UOM groups',
        '3 Conversion rules',
        '4 Packaging types',
        '5 Packaging levels',
        '6 Product categories',
        '7 Principals',
        '8 Brands',
      ],
      SettingsSubjects.locations: [
        '1 Places',
        '2 Branch types',
        '3 Warehouse types',
        '4 Storage areas',
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
        expect(subject.tools, isEmpty, reason: subject.section);
        // The step codes are the menu item keys.
        for (final SubjectStep step in subject.steps) {
          expect(step.path.split('/').last, step.code, reason: step.path);
        }
      }
      // The server's codes, which a server branch answers for.
      expect(
          [
            for (final SubjectStep s in SettingsSubjects.itemLists.steps)
              s.code
          ],
          [
            'uoms',
            'uom-groups',
            'conversion-rules',
            'packaging-types',
            'packaging-levels',
            'product-categories',
            'principals',
            'brands',
          ]);
      expect(
          [
            for (final SubjectStep s in SettingsSubjects.locations.steps)
              s.code
          ],
          [
            'geography-masters',
            'branch-types',
            'warehouse-types',
            'storage-areas',
          ]);
      expect(SettingsSubjects.itemLists.route, 'settings/subject/item-lists');
      expect(SettingsSubjects.locations.route, 'settings/subject/locations');
      expect(SettingsSubjects.itemLists.page.label, 'Item lists settings');
      expect(SettingsSubjects.locations.page.label, 'Locations settings');
      // Each step says what it needs from the step before.
      expect(SettingsSubjects.itemLists.steps[1].topLine,
          contains('Needs units'));
      expect(SettingsSubjects.itemLists.steps[2].topLine,
          contains('Needs two units'));
      expect(SettingsSubjects.itemLists.steps[4].topLine,
          contains('Needs a packaging type'));
      expect(SettingsSubjects.itemLists.steps[7].topLine,
          contains('Needs a principal'));
      expect(SettingsSubjects.locations.steps[3].topLine,
          contains('Needs a warehouse'));
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
          // Every step here is a screen.
          expect(_key('screen-${step.path}').hitTestable(), findsOneWidget,
              reason: step.path);
        }
        await _tapTab(tester, 'start');
        expect(seen.reads, 1);
        expect(seen.windows, isEmpty);
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets('Item lists: a firm with no unit leaves Units of Measure To do',
        (tester) async {
      await _pump(
        tester,
        subject: SettingsSubjects.itemLists,
        state: () => stateOf(
          SettingsSubjects.itemLists,
          states: {'uoms': 'TODO'},
          details: {'uoms': 'None yet'},
        ),
      );

      expect(find.text(SettingsSubjects.itemLists.readyNote), findsNothing);
      expect(_chip(tester, 'uoms'), isNot(_chip(tester, 'uom-groups')));
      expect(find.text('None yet'), findsOneWidget);
      expect(tester.takeException(), isNull);
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
        await tester.ensureVisible(_key('setup-section-${subject.section}'));
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
      for (final String path in [
        'masters/product-categories',
        'administration/uoms',
        'masters/storage-areas',
      ]) {
        await tester.enterText(
            _key('setup-search'), MenuLayout.settings.item(path)!.label);
        await tester.pumpAndSettle();
        await tester.tap(_key('setup-card-$path'));
        await tester.pumpAndSettle();
      }
      expect([for (final MenuItemSpec item in opened) item.path], [
        'masters/product-categories',
        'administration/uoms',
        'masters/storage-areas',
      ]);
    });
  });

  // Row T2: People and Firms, the two platform sections that set something
  // up. System stays as cards: every item there is a tool or a log.
  group('People and Firms', () {
    SettingsSectionState stateOf(SettingsSubject subject,
            {Map<String, String> states = const {},
            Map<String, String> details = const {}}) =>
        SettingsSectionState.fromJson({
          'section': subject.sectionCode,
          'todo_count': states.values.where((s) => s == 'TODO').length,
          'steps': [
            for (final SubjectStep step in subject.steps)
              {
                'code': step.code,
                'state': states[step.code] ?? 'OPTIONAL',
                'detail': details[step.code] ?? '',
              },
          ],
        });

    const Map<SettingsSubject, List<String>> numbered = {
      SettingsSubjects.people: [
        '1 Roles',
        '2 User templates',
        '3 Users',
        '4 User-firm assignments',
      ],
      SettingsSubjects.firms: [
        '1 Business profiles',
        '2 Firms',
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
        // The step codes are the menu item keys.
        for (final SubjectStep step in subject.steps) {
          expect(step.path.split('/').last, step.code, reason: step.path);
        }
      }
      // The server's sections and codes, which a server branch answers for.
      expect(SettingsSubjects.people.sectionCode, 'platform/people');
      expect(SettingsSubjects.firms.sectionCode, 'platform/firms');
      expect(
          [for (final SubjectStep s in SettingsSubjects.people.steps) s.code],
          ['roles', 'user-templates', 'users', 'user-firms']);
      expect(
          [for (final SubjectStep s in SettingsSubjects.firms.steps) s.code],
          ['business-profiles', 'firms']);
      // Permissions is a list to read, so it is a Check tool.
      expect(
          [for (final SubjectStep s in SettingsSubjects.people.tools) s.path],
          ['administration/permissions']);
      expect(SettingsSubjects.people.toolsLabel, 'Check');
      expect(SettingsSubjects.firms.tools, isEmpty);
      expect(SettingsSubjects.people.route, 'settings/subject/people');
      expect(SettingsSubjects.firms.route, 'settings/subject/firms');
      expect(SettingsSubjects.people.page.label, 'People settings');
      expect(SettingsSubjects.firms.page.label, 'Firms settings');
      // Each step says what it needs from the step before.
      expect(
          SettingsSubjects.people.steps[1].topLine, contains('Needs roles'));
      expect(SettingsSubjects.people.steps[2].topLine,
          contains('Needs a template'));
      expect(SettingsSubjects.people.steps[3].topLine,
          contains('Needs a user'));
      expect(SettingsSubjects.firms.steps[1].topLine,
          contains('Nothing works without a firm'));
      // System has no subject: nothing is set up there.
      expect(SettingsSubjects.forSection('System'), isNull);
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
          // Every step and tool here is a screen.
          expect(_key('screen-${step.path}').hitTestable(), findsOneWidget,
              reason: step.path);
        }
        await _tapTab(tester, 'start');
        expect(seen.reads, 1);
        expect(seen.windows, isEmpty);
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets('People: Permissions is a Check tool after the steps',
        (tester) async {
      await _pump(
        tester,
        subject: SettingsSubjects.people,
        state: () => stateOf(
          SettingsSubjects.people,
          states: {'roles': 'DONE', 'users': 'DONE'},
          details: {
            'roles': '16 ready-made, 2 your own',
            'users': '4 people',
          },
        ),
      );

      expect(find.text('Check: Permissions'), findsWidgets);
      expect(find.text('16 ready-made, 2 your own'), findsOneWidget);
      expect(find.text('4 people'), findsOneWidget);
      expect(find.text(SettingsSubjects.people.readyNote), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets(
        'People: a firm administrator has no User-firm assignments tab or row',
        (tester) async {
      const String userFirms = 'administration/user-firms';
      await _pump(
        tester,
        subject: SettingsSubjects.people,
        visible: [
          for (final MenuItemSpec item in _itemsOf('People'))
            if (item.path != userFirms) item,
        ],
        state: () => stateOf(SettingsSubjects.people),
      );

      expect(_key('subject-tab-$userFirms'), findsNothing);
      expect(_key('subject-row-$userFirms'), findsNothing);
      expect(find.text('4 User-firm assignments'), findsNothing);
      expect(find.text('3 Users'), findsOneWidget);
      expect(find.text('Check: Permissions'), findsWidgets);
      expect(tester.takeException(), isNull);
    });

    testWidgets('Firms: an installation with no firm leaves Firms To do',
        (tester) async {
      await _pump(
        tester,
        subject: SettingsSubjects.firms,
        state: () => stateOf(
          SettingsSubjects.firms,
          states: {'firms': 'TODO'},
          details: {'firms': 'None yet'},
        ),
      );

      expect(find.text(SettingsSubjects.firms.readyNote), findsNothing);
      expect(
          _chip(tester, 'firms'), isNot(_chip(tester, 'business-profiles')));
      expect(find.text('None yet'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('Settings shows each section as one card, System as cards',
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
            section: 'Firm',
            onOpen: opened.add,
            onOpenSubject: subjects.add,
          ),
        ),
      ));
      await tester.pumpAndSettle();

      for (final SettingsSubject subject in numbered.keys) {
        await tester.ensureVisible(_key('setup-section-${subject.section}'));
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

      await tester.scrollUntilVisible(_key('setup-section-System'), 200,
          scrollable: find.byType(Scrollable).first);
      await tester.tap(_key('setup-section-System'));
      await tester.pumpAndSettle();
      expect(_key('setup-card-settings/audit-logs'), findsOneWidget);

      // Search still finds each old item by its own name and opens it.
      for (final String path in [
        'administration/users',
        'administration/permissions',
        'administration/firms',
      ]) {
        await tester.enterText(
            _key('setup-search'), MenuLayout.settings.item(path)!.label);
        await tester.pumpAndSettle();
        await tester.tap(_key('setup-card-$path'));
        await tester.pumpAndSettle();
      }
      expect([for (final MenuItemSpec item in opened) item.path], [
        'administration/users',
        'administration/permissions',
        'administration/firms',
      ]);
    });
  });
}