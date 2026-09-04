import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/document_framework.dart';
import 'package:agency_desktop/models/finance.dart';
import 'package:agency_desktop/ui/settings/financial_years_page.dart';
import 'package:agency_desktop/ui/settings/numbering_series_page.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:agency_desktop/ui/workspace/workspace_templates.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The two configuration screens that had working endpoints and no UI.
///
/// Both were greyed-out tabs. Financial years decide whether a document can be
/// posted at all — the refusal "no open accounting period" had nowhere to send
/// anybody — and numbering rules decide what every document is called.
PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

FinancialYear _year({
  String id = 'fy-1',
  String code = 'FY2026',
  bool isActive = true,
  bool isLocked = false,
}) =>
    FinancialYear.fromJson({
      'id': id,
      'code': code,
      'name': '2026-2027',
      'starts_on': '2026-04-01',
      'ends_on': '2027-03-31',
      'description': null,
      'is_active': isActive,
      'is_locked': isLocked,
    });

AccountingPeriod _period({
  String id = 'p-1',
  int number = 1,
  String status = 'OPEN',
  String yearId = 'fy-1',
}) =>
    AccountingPeriod.fromJson({
      'id': id,
      'financial_year_id': yearId,
      'period_number': number,
      'code': 'P$number',
      'name': 'Period $number',
      'starts_on': '2026-04-01',
      'ends_on': '2026-04-30',
      'status': status,
    });

NumberingRule _rule({
  String id = 'r-1',
  int next = 8,
  bool autoReset = true,
  bool manualAllowed = false,
  bool isActive = true,
}) =>
    NumberingRule.fromJson({
      'id': id,
      'document_type_id': 'dt-1',
      'code': 'SALES_INVOICE',
      'name': 'Sales Invoice numbering',
      'prefix': 'SI',
      'suffix': null,
      'separator': '-',
      'include_financial_year': true,
      'include_branch_code': false,
      'include_company_code': false,
      'auto_reset': autoReset,
      'manual_allowed': manualAllowed,
      'sequence_padding': 6,
      'next_sequence': next,
      'is_default': true,
      'is_active': isActive,
    });

class _ConfigApi extends ApiClient {
  _ConfigApi({
    this.years = const [],
    this.periods = const [],
    this.rules = const [],
    this.types = const [],
  }) : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<FinancialYear> years;
  final List<AccountingPeriod> periods;
  final List<NumberingRule> rules;
  final List<DocumentTypeRecord> types;
  final List<String> statusCalls = [];
  String? previewedId;
  final List<Json> created = [];
  final List<MapEntry<String, Json>> updated = [];
  final List<String> deleted = [];

  @override
  Future<List<FinancialYear>> financialYears() async => years;

  @override
  Future<List<AccountingPeriod>> accountingPeriods({
    String? financialYearId,
  }) async =>
      periods;

  @override
  Future<AccountingPeriod> setPeriodStatus(String id, String status) async {
    statusCalls.add('$id:$status');
    return _period(status: status);
  }

  @override
  Future<List<NumberingRule>> numberingRules() async => rules;

  @override
  Future<String> previewNumber(String ruleId) async {
    previewedId = ruleId;
    return 'SI-2026-2027-000008';
  }

  @override
  Future<List<DocumentTypeRecord>> documentTypes() async => types;

  @override
  Future<NumberingRule> createNumberingRule(Json body) async {
    created.add(body);
    return _rule();
  }

  @override
  Future<NumberingRule> updateNumberingRule(String id, Json body) async {
    updated.add(MapEntry(id, body));
    return _rule(id: id);
  }

  @override
  Future<void> deleteNumberingRule(String id) async => deleted.add(id);
}

Future<void> _pumpYears(
  WidgetTester tester,
  _ConfigApi api, {
  List<String> perms = const ['accounting', 'financial_year'],
  bool hasActiveFirm = true,
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: FinancialYearsPage(
          api: api,
          permissions: _permissionsFor(perms),
          hasActiveFirm: hasActiveFirm,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _pumpRules(
  WidgetTester tester,
  _ConfigApi api, {
  List<String> perms = const ['SETTINGS_VIEW'],
  bool hasActiveFirm = true,
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: NumberingSeriesPage(
          api: api,
          permissions: _permissionsFor(perms),
          hasActiveFirm: hasActiveFirm,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('financial years', () {
    testWidgets('a year says how many of its periods are open', (tester) async {
      // The fact that decides whether anything can be posted. The year's own
      // dates do not say it.
      await _pumpYears(
        tester,
        _ConfigApi(
          years: [_year()],
          periods: [
            _period(id: 'p-1', number: 1),
            _period(id: 'p-2', number: 2, status: 'CLOSED'),
          ],
        ),
      );

      expect(find.textContaining('1 period(s) open'), findsOneWidget);
      expect(find.text('ACTIVE'), findsOneWidget);
    });

    testWidgets('a period can be closed and reopened', (tester) async {
      final _ConfigApi api = _ConfigApi(
        years: [_year()],
        periods: [_period(id: 'p-1')],
      );
      await _pumpYears(tester, api);

      await tester.tap(find.widgetWithText(TextButton, 'Close'));
      await tester.pumpAndSettle();

      expect(api.statusCalls, ['p-1:CLOSED']);
    });

    testWidgets('a locked year offers no open or close', (tester) async {
      // Whatever its periods say, a locked year admits no more postings.
      await _pumpYears(
        tester,
        _ConfigApi(
          years: [_year(isLocked: true)],
          periods: [_period(id: 'p-1')],
        ),
      );

      expect(find.text('LOCKED'), findsOneWidget);
      expect(find.widgetWithText(TextButton, 'Close'), findsNothing);
    });

    testWidgets('without the financial-year permission it is read-only',
        (tester) async {
      await _pumpYears(
        tester,
        _ConfigApi(years: [_year()], periods: [_period()]),
        perms: const ['accounting'],
      );

      expect(find.text('OPEN'), findsOneWidget);
      expect(find.widgetWithText(TextButton, 'Close'), findsNothing);
    });

    testWidgets('a year with no periods says why that matters',
        (tester) async {
      await _pumpYears(tester, _ConfigApi(years: [_year()]));

      expect(
        find.textContaining('cannot take a posting'),
        findsOneWidget,
      );
    });

    testWidgets('no years at all explains what one is for', (tester) async {
      await _pumpYears(tester, _ConfigApi());
      expect(find.text('No financial year yet'), findsOneWidget);
      expect(find.textContaining('nothing can be booked'), findsOneWidget);
    });

    testWidgets('without permission there is nothing to show', (tester) async {
      await _pumpYears(tester, _ConfigApi(), perms: const ['SALES_VIEW']);
      expect(find.textContaining('do not have permission'), findsOneWidget);
    });
  });

  group('numbering series', () {
    testWidgets('a rule is described in words, not in flags', (tester) async {
      await _pumpRules(tester, _ConfigApi(rules: [_rule()]));

      expect(find.text('SI-financial year-######'), findsOneWidget);
      expect(
        find.textContaining('next #8 · restarts each financial year'),
        findsOneWidget,
      );
      expect(find.text('DEFAULT'), findsOneWidget);
    });

    testWidgets('the preview comes from the server', (tester) async {
      // The pattern involves the financial year, the branch and a counter
      // under a lock; a client that guessed would disagree with the document
      // that eventually gets made.
      final _ConfigApi api = _ConfigApi(rules: [_rule()]);
      await _pumpRules(tester, api);

      await tester.tap(find.widgetWithText(TextButton, 'Preview next'));
      await tester.pumpAndSettle();

      expect(api.previewedId, 'r-1');
      expect(find.text('Next: SI-2026-2027-000008'), findsOneWidget);
    });

    testWidgets('an inactive rule says so', (tester) async {
      await _pumpRules(tester, _ConfigApi(rules: [_rule(isActive: false)]));
      expect(find.text('INACTIVE'), findsOneWidget);
    });

    testWidgets('no rules yet explains when one appears', (tester) async {
      await _pumpRules(tester, _ConfigApi());
      expect(find.text('No numbering rules yet'), findsOneWidget);
    });

    testWidgets('without SETTINGS_VIEW there is nothing to show',
        (tester) async {
      await _pumpRules(tester, _ConfigApi(), perms: const ['SALES_VIEW']);
      expect(find.textContaining('do not have permission'), findsOneWidget);
    });
  });

  group('the catalog no longer advertises what it cannot open', () {
    test('every tab is available', () {
      // A tab greyed out for a year reads as broken, not as roadmap. Each of
      // the fourteen removed here had no endpoints behind it, or duplicated a
      // module with its own place in the sidebar.
      expect(
        [
          for (final ModuleDefinition module in ModuleCatalog.modules)
            for (final ModuleTabDefinition tab in module.tabs)
              if (!tab.available) '${module.label} / ${tab.label}',
        ],
        isEmpty,
      );
    });

    test('the two that had a backend kept their place', () {
      // Deleting these would have hidden a working capability rather than
      // stopped advertising a missing one.
      expect(
        ModuleCatalog.byId(AppModule.masters).tabs.map((tab) => tab.id),
        contains('financial-years'),
      );
      expect(
        ModuleCatalog.byId(AppModule.administration).tabs.map((tab) => tab.id),
        contains('numbering-series'),
      );
    });

    test('no navigation node points at a tab its module does not have', () {
      // A node whose path is not a tab id lands the reader on the first tab
      // instead, silently -- which is what `numbering-series` did.
      for (final ModuleDefinition module in ModuleCatalog.modules) {
        final Set<String> tabIds = {for (final tab in module.tabs) tab.id};
        final List<WorkspaceNavigationNode> nodes =
            ModuleCatalog.navigationChildren(module.id, tabIds);
        for (final String path in _paths(nodes)) {
          expect(
            tabIds,
            contains(path),
            reason: '${module.label} draws "$path" but has no such tab',
          );
        }
      }
    });
  });

  group('numbering series, editing', () {
    DocumentTypeRecord type() => DocumentTypeRecord.fromJson({
          'id': 'dt-1',
          'code': 'SALES_INVOICE',
          'name': 'Sales Invoice',
        });

    testWidgets('a reader sees no way to change anything', (tester) async {
      // The server enforces SETTINGS_UPDATE, so this only decides whether the
      // controls are worth showing -- but a button that always answers 403 is
      // worse than no button.
      await _pumpRules(
        tester,
        _ConfigApi(rules: [_rule()], types: [type()]),
        perms: const ['SETTINGS_VIEW'],
      );

      expect(find.text('New series'), findsNothing);
      expect(find.byTooltip('Edit'), findsNothing);
      expect(find.byTooltip('Retire'), findsNothing);
      // And the thing they came for is still there.
      expect(find.text('Preview next'), findsOneWidget);
    });

    testWidgets('an administrator gets all three', (tester) async {
      await _pumpRules(
        tester,
        _ConfigApi(rules: [_rule()], types: [type()]),
        perms: const ['SETTINGS_VIEW', 'SETTINGS_UPDATE'],
      );

      expect(find.text('New series'), findsOneWidget);
      expect(find.byTooltip('Edit'), findsOneWidget);
      expect(find.byTooltip('Retire'), findsOneWidget);
    });

    testWidgets('the counter cannot be moved on an existing series',
        (tester) async {
      // `next_sequence` is advanced by the server under a lock. Setting it
      // back would hand out a number a document already holds, which the
      // per-firm uniqueness key then refuses on somebody else's save.
      final _ConfigApi api = _ConfigApi(rules: [_rule()], types: [type()]);
      await _pumpRules(
        tester,
        api,
        perms: const ['SETTINGS_VIEW', 'SETTINGS_UPDATE'],
      );

      await tester.tap(find.byTooltip('Edit'));
      await tester.pumpAndSettle();

      expect(find.text('Next number: 8'), findsOneWidget);
      expect(find.text('Start numbering at'), findsNothing);

      await tester.tap(find.text('Save'));
      await tester.pumpAndSettle();

      expect(api.updated, hasLength(1));
      expect(
        api.updated.single.value.containsKey('next_sequence'),
        isFalse,
        reason: 'an edit must not carry the counter',
      );
    });

    testWidgets('a new series may say where its counter starts',
        (tester) async {
      final _ConfigApi api = _ConfigApi(rules: const [], types: [type()]);
      await _pumpRules(
        tester,
        api,
        perms: const ['SETTINGS_VIEW', 'SETTINGS_UPDATE'],
      );

      await tester.tap(find.text('New series'));
      await tester.pumpAndSettle();

      expect(find.text('Start numbering at'), findsOneWidget);
      await tester.enterText(find.byType(TextField).at(0), 'PURCHASE');
      await tester.enterText(find.byType(TextField).at(1), 'Purchase numbers');
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save'));
      await tester.pumpAndSettle();

      expect(api.created, hasLength(1));
      expect(api.created.single['code'], 'PURCHASE');
      expect(api.created.single['next_sequence'], 1);
    });

    testWidgets('a series that would repeat itself says so before saving',
        (tester) async {
      // The server refuses this pairing. Saying it here means the person
      // choosing finds out while they are choosing, rather than reading a
      // refusal after the fact.
      await _pumpRules(
        tester,
        _ConfigApi(rules: [_rule()], types: [type()]),
        perms: const ['SETTINGS_VIEW', 'SETTINGS_UPDATE'],
      );

      await tester.tap(find.byTooltip('Edit'));
      await tester.pumpAndSettle();
      expect(find.textContaining('would repeat one issued in March'),
          findsNothing);

      await tester.tap(find.text('Include the financial year'));
      await tester.pumpAndSettle();

      expect(
        find.textContaining('would repeat one issued in March'),
        findsOneWidget,
      );
    });

    testWidgets('retiring asks first, and says what survives', (tester) async {
      final _ConfigApi api = _ConfigApi(rules: [_rule()], types: [type()]);
      await _pumpRules(
        tester,
        api,
        perms: const ['SETTINGS_VIEW', 'SETTINGS_UPDATE'],
      );

      await tester.tap(find.byTooltip('Retire'));
      await tester.pumpAndSettle();
      expect(find.textContaining('keep the numbers they have'), findsOneWidget);

      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(api.deleted, isEmpty);

      await tester.tap(find.byTooltip('Retire'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Retire').last);
      await tester.pumpAndSettle();
      expect(api.deleted, ['r-1']);
    });
  });
}

List<String> _paths(List<WorkspaceNavigationNode> nodes) => [
      for (final WorkspaceNavigationNode node in nodes) ...[
        if (node.path != null) node.path!,
        ..._paths(node.children),
      ],
    ];
