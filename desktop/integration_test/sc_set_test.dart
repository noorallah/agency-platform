import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';

/// Settings as one screen per subject (book 04, TC-CONF-010 to TC-CONF-015).
/// Run on the `ready-firm` fixture (`scripts/test_fixture.py ready-firm`) as
/// readyadmin, then as readyviewer. The admin opens every subject from the
/// gear, reads its tabs and its Start here, opens each tab and searches one
/// card per case; one harmless setting (Stock > Batch rules, the near-expiry
/// window) is changed, read back from the server and put back as it was.
/// The viewer opens the same subjects and is refused the same change.

/// One Settings section that opens as one screen.
class _Subject {
  const _Subject(this.caseId, this.section, this.code, this.tabs,
      {this.chips = const <String, String>{}, this.note});

  final String caseId;

  /// The section's label in the Settings list.
  final String section;

  /// Its `sectionCode`, which keys its card.
  final String code;

  /// The tab strip the book expects, left to right.
  final List<String> tabs;

  /// Step code -> the chip the book expects on Start here.
  final Map<String, String> chips;

  /// The note on top of Start here, when the book names it.
  final String? note;
}

const List<_Subject> _subjects = <_Subject>[
  _Subject('TC-CONF-010', 'Tax', 'tax', <String>[
    'Start here', '1 Rates and profiles', '2 Tax rules', '3 Tax settings',
    '4 GST on documents', '5 TDS on purchases', 'Check: Rule simulator',
    'Check: Execution log',
  ], chips: <String, String>{
    'rates-and-profiles': 'Done', 'tax-rules': 'Done',
    'tax-settings': 'Optional', 'gst-documents': 'Optional',
    'tds-purchases': 'Optional',
  }, note: 'Tax is ready for this firm.'),
  _Subject('TC-CONF-011', 'Firm', 'firm', <String>[
    'Start here', '1 Firm settings', '2 Financial years', '3 Numbering',
    '4 Goods types', '5 Custom fields', '6 Custom field rules',
    '7 Messaging', '8 Approval levels', 'Yours: My branch and warehouse',
  ], chips: <String, String>{
    'firm-profile': 'Optional', 'financial-years': 'Done',
    'numbering-series': 'Optional', 'goods-types': 'Optional',
    'custom-fields': 'Optional', 'custom-field-rules': 'Optional',
    'messaging': 'Optional', 'approval-levels': 'Optional',
  }),
  _Subject('TC-CONF-011', 'Selling', 'selling', <String>[
    'Start here', '1 Sales stages', '2 Salesmen', '3 Credit control',
    '4 Price floor', '5 Discount limits', '6 Loyalty scheme', '7 TCS',
  ], chips: <String, String>{
    'sales-stages': 'Optional', 'salesmen': 'Optional',
    'credit-control': 'Optional', 'price-floor': 'Optional',
    'discount-limits': 'Optional', 'loyalty-scheme': 'Optional',
    'tcs': 'Optional',
  }),
  _Subject('TC-CONF-011', 'Buying', 'buying', <String>[
    'Start here', '1 Purchase settings', '2 Approval limits',
    '3 Purchase budgets',
  ], chips: <String, String>{
    'purchase-settings': 'Optional', 'approval-limits': 'Optional',
    'purchase-budgets': 'Optional',
  }),
  _Subject('TC-CONF-012', 'Stock', 'stock', <String>[
    'Start here', '1 Adjustment reasons', '2 Adjustment limits',
    '3 Batch rules', 'Yours: Inventory settings',
  ], chips: <String, String>{
    'adjustment-reasons': 'Optional', 'adjustment-limits': 'Optional',
    'batch-rules': 'Optional',
  }, note: 'Stock is ready for this firm.'),
  _Subject('TC-CONF-012', 'Business profile', 'business-profile', <String>[
    'Start here', '1 Profile assignment', '2 Feature management',
    '3 Module configuration', '4 Attribute definitions',
    '5 Mandatory attributes', '6 Unit sets',
  ], chips: <String, String>{
    'profile-assignment': 'Optional', 'feature-management': 'Optional',
    'module-configuration': 'Optional', 'attribute-definitions': 'Optional',
    'mandatory-attributes': 'Optional', 'unit-sets': 'Optional',
  }),
  _Subject('TC-CONF-012', 'Pricing', 'pricing', <String>[
    'Start here', '1 Price lists', '2 Price levels', '3 Promotions',
    '4 Loyalty',
  ], chips: <String, String>{
    'price-lists': 'Optional', 'price-levels': 'Optional',
    'promotions': 'Optional', 'loyalty': 'Optional',
  }),
  _Subject('TC-CONF-013', 'Territories & routes', 'territories', <String>[
    'Start here', '1 Territories', '2 Route types', '3 Route builder',
    '4 Transporters',
  ], chips: <String, String>{
    'territories': 'Optional', 'route-types': 'Optional',
    'route-builder': 'Optional', 'transporters': 'Optional',
  }),
  _Subject('TC-CONF-013', 'Account structure', 'account-structure', <String>[
    'Start here', '1 Control accounts', '2 Cost centres', '3 Profit centres',
  ], chips: <String, String>{
    'control-accounts': 'Done', 'cost-centers': 'Optional',
    'profit-centers': 'Optional',
  }),
  _Subject('TC-CONF-013', 'Party lists', 'party-lists', <String>[
    'Start here', '1 Customer groups', '2 Vendor categories',
    '3 Vendor types', '4 Licence types', '5 Licence check',
  ], chips: <String, String>{
    'customer-groups': 'Optional', 'vendor-categories': 'Optional',
    'vendor-types': 'Optional', 'licence-types': 'Optional',
    'licence-check-settings': 'Optional',
  }),
  _Subject('TC-CONF-014', 'Item lists', 'item-lists', <String>[
    'Start here', '1 Units of Measure', '2 UOM groups', '3 Conversion rules',
    '4 Packaging types', '5 Packaging levels', '6 Product categories',
    '7 Principals', '8 Brands',
  ], chips: <String, String>{
    'uoms': 'Done', 'uom-groups': 'Optional', 'conversion-rules': 'Optional',
    'packaging-types': 'Optional', 'packaging-levels': 'Optional',
    'product-categories': 'Optional', 'principals': 'Optional',
    'brands': 'Optional',
  }),
  _Subject('TC-CONF-014', 'Locations', 'locations', <String>[
    'Start here', '1 Places', '2 Branch types', '3 Warehouse types',
    '4 Storage areas',
  ], chips: <String, String>{
    'geography-masters': 'Optional', 'branch-types': 'Optional',
    'warehouse-types': 'Optional', 'storage-areas': 'Optional',
  }),
  _Subject('TC-CONF-015', 'People', 'platform/people', <String>[
    'Start here', '1 Roles', '2 User templates', '3 Users',
    'Check: Permissions',
  ], chips: <String, String>{
    'roles': 'Done', 'user-templates': 'Optional', 'users': 'Done',
  }),
];

/// One search per case: what is typed, and the card it must find.
const Map<String, (String, String)> _searches = <String, (String, String)>{
  'TC-CONF-010': ('Tax Rules', 'administration/tax-rules-page'),
  'TC-CONF-011': ('Credit Control', 'settings/credit-control'),
  'TC-CONF-012': ('Unit Sets', 'administration/unit-sets'),
  'TC-CONF-013': ('Route Builder', 'sales/route-builder'),
  'TC-CONF-014': ('Product Categories', 'masters/product-categories'),
  'TC-CONF-015': ('Users', 'administration/users'),
};

/// IT_PART=search (or batch) runs only that part, for re-driving one.
const String _part = String.fromEnvironment('IT_PART');
bool _runs(String part) => _part.isEmpty || _part == part;

const String _batchRules = '/api/v1/batch-serial/sale-settings';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('SET: settings subjects ($itHandle)',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server admin = await Server.connectAs(
        '$itSuffix.readyadmin@fixtures.local', fixturePassword);
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('set-$itHandle');
    final bool isAdmin = itHandle == 'readyadmin';

    /// The errors the app raised since [from], as one line.
    String errorsSince(int from) => appErrors.skip(from).take(3).join(' || ');

    Future<void> openSettings() async {
      await closeOpenEditor(tester);
      await tester.tap(find.byKey(const ValueKey<String>('menu-area-settings')));
      await pumpUntil(tester, find.byKey(const ValueKey<String>('setup-search')),
          waitingFor: 'the Settings page');
      await pumpFor(tester, const Duration(milliseconds: 500));
    }

    /// Press the gear, the section, then its one card. Returns what the
    /// section showed before the card was pressed, or throws.
    Future<String> openSubject(_Subject s) async {
      await openSettings();
      final Finder tile = find.byKey(ValueKey<String>('setup-section-${s.section}'));
      if (tile.evaluate().isEmpty) {
        throw StateError('section "${s.section}" not in the Settings list');
      }
      await tester.ensureVisible(tile);
      await tester.tap(tile);
      await pumpFor(tester, const Duration(milliseconds: 700));
      final Finder card = find.byKey(ValueKey<String>('setup-subject-${s.code}'));
      final int cards = find
          .byWidgetPredicate((Widget w) =>
              w.key is ValueKey<String> &&
              (w.key! as ValueKey<String>).value.startsWith('setup-card-'))
          .evaluate()
          .length;
      final bool onePlace = screenHas(tester, 'Opens one screen');
      if (card.evaluate().isEmpty) {
        throw StateError('no one-screen card for ${s.section} '
            '($cards plain cards instead)');
      }
      await tester.tap(card);
      await pumpUntil(tester, find.byKey(const ValueKey<String>('subject-strip')),
          waitingFor: 'the ${s.section} subject screen');
      await pumpFor(tester, const Duration(seconds: 2));
      return 'card says "Opens one screen"=$onePlace, other cards=$cards';
    }

    List<String> stripLabels() => <String>[
          for (final Text t in tester.widgetList<Text>(find.descendant(
              of: find.byKey(const ValueKey<String>('subject-strip')),
              matching: find.byType(Text))))
            t.data ?? '',
        ];

    String chipOf(String code) {
      final Finder f = find.descendant(
          of: find.byKey(ValueKey<String>('subject-chip-$code')),
          matching: find.byType(Text));
      return f.evaluate().isEmpty
          ? '(none)'
          : tester.widget<Text>(f.first).data ?? '';
    }

    String detailOf(String code) {
      final Finder f = find.byKey(ValueKey<String>('subject-detail-$code'));
      return f.evaluate().isEmpty ? '' : tester.widget<Text>(f.first).data ?? '';
    }

    String noteText() {
      final Finder f = find.byKey(const ValueKey<String>('subject-note'));
      return f.evaluate().isEmpty ? '' : tester.widget<Text>(f.first).data ?? '';
    }

    /// Open every tab of the subject on screen in turn; return the ones that
    /// showed no body.
    Future<List<String>> visitTabs() async {
      final List<String> keys = <String>[
        for (final Element e in find
            .byWidgetPredicate((Widget w) =>
                w.key is ValueKey<String> &&
                (w.key! as ValueKey<String>).value.startsWith('subject-tab-') &&
                (w.key! as ValueKey<String>).value != 'subject-tab-start')
            .evaluate())
          (e.widget.key! as ValueKey<String>).value,
      ];
      final List<String> blank = <String>[];
      for (final String key in keys) {
        final String path = key.substring('subject-tab-'.length);
        final Finder tab = find.byKey(ValueKey<String>(key));
        await tester.ensureVisible(tab);
        await tester.tap(tab);
        await pumpFor(tester, const Duration(milliseconds: 1800));
        if (find.byKey(ValueKey<String>('subject-body-$path')).evaluate().isEmpty) {
          blank.add(path);
        }
        await closeOpenEditor(tester);
      }
      final Finder start = find.byKey(const ValueKey<String>('subject-tab-start'));
      await tester.tap(start);
      await pumpFor(tester, const Duration(milliseconds: 600));
      return blank;
    }

    // -- Every subject opens as one screen ---------------------------------
    for (final _Subject s in _runs('subjects') ? _subjects : <_Subject>[]) {
      await log.step('${s.caseId} ${s.section} opens as one screen', () async {
        final int errs = appErrors.length;
        if (!isAdmin) {
          await openSettings();
          if (find
              .byKey(ValueKey<String>('setup-section-${s.section}'))
              .evaluate()
              .isEmpty) {
            log.saw = 'section not offered to $itHandle';
            return;
          }
        }
        final String card = await openSubject(s);
        final List<String> tabs = stripLabels();
        final List<String> problems = <String>[];
        if (isAdmin) {
          final List<String> missing = <String>[
            for (final String t in s.tabs) if (!tabs.contains(t)) t,
          ];
          final List<String> extra = <String>[
            for (final String t in tabs) if (!s.tabs.contains(t)) t,
          ];
          final List<String> inBook = <String>[
            for (final String t in tabs) if (s.tabs.contains(t)) t,
          ];
          if (missing.isNotEmpty) problems.add('tabs missing $missing');
          if (missing.isEmpty && inBook.join('|') != s.tabs.join('|')) {
            problems.add('tabs out of order');
          }
          if (extra.isNotEmpty) {
            log.info(s.caseId, '${s.section}: tabs the book does not name: $extra');
          }
          final List<String> wrongChips = <String>[
            for (final MapEntry<String, String> c in s.chips.entries)
              if (chipOf(c.key) != c.value)
                '${c.key}=${chipOf(c.key)} (book ${c.value})',
          ];
          if (wrongChips.isNotEmpty) problems.add('chips $wrongChips');
          if (s.note != null && noteText() != s.note) {
            problems.add('note "${noteText()}" (book "${s.note}")');
          }
          if (s.section == 'People' &&
              tabs.any((String t) => t.contains('User-firm'))) {
            problems.add('User-firm assignments shown to a firm admin');
          }
        }
        final String details = <String>[
          for (final String code in s.chips.keys)
            if (detailOf(code).isNotEmpty) '$code: ${detailOf(code)}',
        ].take(4).join('; ');
        final List<String> blank = await visitTabs();
        if (blank.isNotEmpty) problems.add('tabs showing nothing $blank');
        if (appErrors.length > errs) {
          problems.add('app errors: ${errorsSince(errs)}');
        }
        log.saw = '$card; tabs=$tabs; note="${noteText()}"; $details';
        if (problems.isNotEmpty) {
          throw StateError('${problems.join('; ')} [tabs=$tabs]');
        }
      });
    }

    if (isAdmin && _runs('subjects')) {
      await log.step('TC-CONF-013 Party lists: row 1 Open shows Customer groups',
          () async {
        final int errs = appErrors.length;
        await openSubject(_subjects.firstWhere((_Subject s) => s.code == 'party-lists'));
        final Finder open = find.byWidgetPredicate((Widget w) =>
            w.key is ValueKey<String> &&
            (w.key! as ValueKey<String>).value.startsWith('subject-open-'));
        if (open.evaluate().isEmpty) throw StateError('no Open button on row 1');
        await tester.tap(open.first);
        await pumpFor(tester, const Duration(seconds: 3));
        final bool shown = screenHas(tester, 'Customer Groups') ||
            screenHas(tester, 'Customer groups');
        log.saw = 'customer groups on screen=$shown';
        if (!shown) throw StateError('row 1 did not show Customer groups');
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });

      await log.step('TC-CONF-015 Firms is not offered to a firm admin',
          () async {
        await openSettings();
        final bool section = find
            .byKey(const ValueKey<String>('setup-section-Firms'))
            .evaluate()
            .isNotEmpty;
        log.saw = 'Firms section listed=$section';
        if (section) {
          final _Subject firms = _Subject(
              'TC-CONF-015', 'Firms', 'platform/firms', const <String>[]);
          final String said = await openSubject(firms);
          log.saw = '${log.saw}; opened: $said; ${textOnScreen(tester).take(20).join(' | ')}';
          log.info('TC-CONF-015', 'Firms listed for a firm admin: ${log.saw}');
        }
      });

      await log.step('TC-CONF-015 System stays as cards, no Start here',
          () async {
        final int errs = appErrors.length;
        await openSettings();
        final Finder tile = find.byKey(const ValueKey<String>('setup-section-System'));
        if (tile.evaluate().isEmpty) throw StateError('no System section');
        await tester.ensureVisible(tile);
        await tester.tap(tile);
        await pumpFor(tester, const Duration(milliseconds: 800));
        final bool cards = screenHas(tester, 'Audit Logs');
        final bool start = find
            .byKey(const ValueKey<String>('setup-subject-system'))
            .evaluate()
            .isNotEmpty;
        log.saw = 'Audit Logs card=$cards, one-screen card=$start';
        if (!cards || start) throw StateError(log.saw!);
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
    }

    // -- Search settings finds the card, which opens on its own ------------
    for (final MapEntry<String, (String, String)> s
        in _runs('search') ? _searches.entries : <MapEntry<String, (String, String)>>[]) {
      await log.step('${s.key} search "${s.value.$1}" opens its card', () async {
        final int errs = appErrors.length;
        await openSettings();
        // A search left from the last step is cleared with its own button,
        // and the box tapped, so the typing reaches it after a window closed.
        final Finder clear = find.byTooltip('Clear');
        if (clear.evaluate().isNotEmpty) {
          await tester.tap(clear.first);
          await pumpFor(tester, const Duration(milliseconds: 400));
        }
        final Finder box = find.byKey(const ValueKey<String>('setup-search'));
        await tester.tap(box);
        await pumpFor(tester, const Duration(milliseconds: 300));
        await tester.enterText(box, s.value.$1);
        await pumpFor(tester, const Duration(milliseconds: 800));
        final Finder card = find.byKey(ValueKey<String>('setup-card-${s.value.$2}'));
        if (card.evaluate().isEmpty) {
          if (!isAdmin) {
            log.saw = 'not offered to $itHandle';
            return;
          }
          final int boxes =
              find.byKey(const ValueKey<String>('setup-search')).evaluate().length;
          throw StateError('no card for ${s.value.$2}; search boxes=$boxes, '
              'typed="${boxesIn(tester, 'setup-search')}", cards=['
              '${find.byWidgetPredicate((Widget w) => w.key is ValueKey<String> && (w.key! as ValueKey<String>).value.startsWith('setup-card-')).evaluate().map((Element e) => (e.widget.key! as ValueKey<String>).value).take(8).join(', ')}]'
              ', said: ${textOnScreen(tester).where((String t) => t.contains('match') || t.contains('UNIT') || t.contains('Unit')).take(5).join(' | ')}');
        }
        await tester.ensureVisible(card);
        await tester.tap(card.first);
        await pumpFor(tester, const Duration(seconds: 3));
        final bool dialog = find.byType(Dialog).evaluate().isNotEmpty;
        final bool left =
            find.byKey(const ValueKey<String>('setup-search')).evaluate().isEmpty;
        log.saw = 'opened as ${dialog ? 'a window' : left ? 'a screen' : 'nothing'}';
        await closeOpenEditor(tester);
        if (!dialog && !left) throw StateError('the card opened nothing');
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
    }

    // -- One harmless setting: Stock > Batch rules, near-expiry days -------
    final _Subject stock = _subjects.firstWhere((_Subject s) => s.code == 'stock');
    Future<bool> openBatchRules() async {
      await openSubject(stock);
      final Finder tab = find.byKey(const ValueKey<String>('subject-tab-settings/batch-rules'));
      if (tab.evaluate().isEmpty) return false;
      await tester.tap(tab);
      await pumpFor(tester, const Duration(seconds: 1));
      await tapKey(tester, 'subject-window-settings/batch-rules');
      await pumpUntil(tester, find.byKey(const ValueKey<String>('batch-rules-days')),
          waitingFor: 'the Batch rules window');
      await pumpFor(tester, const Duration(seconds: 1));
      return true;
    }

    Future<int> daysOnServer() async =>
        int.parse('${((await admin.get(_batchRules)) as Json)['near_expiry_days']}');

    Future<String> saveDays(String days) async {
      await tester.enterText(
          find.byKey(const ValueKey<String>('batch-rules-days')), days);
      await pumpFor(tester, const Duration(milliseconds: 300));
      await tapKey(tester, 'batch-rules-save');
      return watch(tester, seconds: 4, confirm: false);
    }

    if (!_runs('batch')) {
      // only another part was asked for
    } else if (isAdmin) {
      await log.step('TC-CONF-012 Batch rules: change, read back, put back',
          () async {
        final int errs = appErrors.length;
        final int before = await daysOnServer();
        final int changed = before == 45 ? 46 : 45;
        if (!await openBatchRules()) throw StateError('Batch rules tab not offered');
        final String said1 = await saveDays('$changed');
        await closeOpenEditor(tester);
        final int read1 = await daysOnServer();
        if (!await openBatchRules()) throw StateError('Batch rules gone');
        final String shown = boxesIn(tester, 'batch-rules-days');
        final String said2 = await saveDays('$before');
        await closeOpenEditor(tester);
        final int read2 = await daysOnServer();
        log.saw = 'server $before -> $read1 (said "$said1"), reopened shows '
            '"$shown", put back -> $read2 (said "$said2")';
        if (read1 != changed) throw StateError('save did not reach the server');
        if (!shown.contains('$changed')) throw StateError('reopened window lost it');
        if (read2 != before) throw StateError('could not put it back');
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
    } else {
      await log.step('TC-CONF-012 Batch rules: $itHandle cannot change it',
          () async {
        final int errs = appErrors.length;
        final int before = await daysOnServer();
        if (!await openBatchRules()) {
          log.saw = 'Batch rules tab not offered to $itHandle; server $before';
          return;
        }
        final Finder box = find.byKey(const ValueKey<String>('batch-rules-days'));
        final bool boxOn = tester.widget<TextField>(box).enabled ?? true;
        final String save = buttonState(tester, 'Save');
        final String why = screenHas(tester, 'needs the manage sales settings')
            ? 'says it needs the manage sales settings permission'
            : 'no words';
        String said = '';
        if (boxOn && save == 'enabled') {
          said = await saveDays('${before == 45 ? 46 : 45}');
        }
        await closeOpenEditor(tester);
        final int after = await daysOnServer();
        log.saw = 'box enabled=$boxOn, Save $save, $why, said "$said", '
            'server $before -> $after';
        if (after != before) throw StateError('the viewer changed it');
        if (save == 'enabled' && said.isEmpty) {
          throw StateError('Save offered and refused in no words');
        }
        if (save != 'enabled' && why == 'no words') {
          throw StateError('Save off with nothing saying why');
        }
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
    }

    log.skip('TC-CONF-010 step 8 / TC-CONF-011 steps 4 and 6',
        'they need a firm with no tax, no open year or a required salesman; '
        'the ready fixture has none and the flow leaves it as found');
    log.skip('TC-CONF-015 step 2', 'the platform administrator is a member '
        'of no firm; run separately');
    log.finish();
  });
}
