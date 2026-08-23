// Commission: what a salesman earns, and what a period of collections earned
// them.
//
// Two things about the module surprise everybody, and both are asserted here
// rather than left to a reviewer's memory: a rule naming nobody is the
// firm-wide default, and commission is earned on money *collected* rather than
// on what was invoiced. The Unassigned bucket is the second one made visible —
// money collected against invoices that carried no salesman — and a report
// that hid it would produce totals nobody could reconcile against the cash
// book.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/commission/commission_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({
  List<String> perms = const ['COMMISSION_VIEW', 'COMMISSION_MANAGE'],
}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

class _CommissionApi extends ApiClient {
  _CommissionApi({
    this.rules = const [],
    this.report,
    this.refusal,
    this.salesmen = const [],
  })
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// What `GET /commission/rules` answers with.
  final List<Json> rules;

  /// What `GET /commission/report` answers with.
  final Json? report;

  /// A refusal the server raises on a write, if any.
  final ApiException? refusal;

  /// What `GET /commission/salesmen` answers with -- the firm's own people,
  /// which is what makes a rate for somebody who has never had one possible.
  final List<Json> salesmen;

  final List<String> requested = <String>[];
  Json? created;
  Json? updated;
  String? updatedPath;
  int? sentVersion;
  String? deleted;

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
    requested.add('$method $path');
    if (path.contains('/commission/report')) {
      return <String, dynamic>{'data': report ?? _emptyReport()};
    }
    if (path.contains('/commission/salesmen')) {
      return <String, dynamic>{'data': salesmen};
    }
    if (path.contains('/commission/rules')) {
      if (method == 'POST') {
        if (refusal != null) throw refusal!;
        created = body;
        return <String, dynamic>{'data': _firmWideRule()};
      }
      if (method == 'PUT') {
        if (refusal != null) throw refusal!;
        updated = body;
        updatedPath = path;
        sentVersion = expectedVersion;
        return <String, dynamic>{'data': _salesmanRule()};
      }
      if (method == 'DELETE') {
        deleted = path;
        return <String, dynamic>{'data': null};
      }
      return <String, dynamic>{
        'data': rules,
        'pagination': <String, dynamic>{'total_records': rules.length},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

/// The firm-wide default: a rate belonging to nobody in particular.
Json _firmWideRule() => <String, dynamic>{
      'id': 'rule-firm',
      'salesman_id': null,
      'salesman_name': '',
      'percentage': '2.5000',
      'effective_from': '2026-01-01',
      'effective_to': null,
      'status': 'ACTIVE',
      'version': 3,
    };

/// One person's own rate, which beats the default while it is in force.
Json _salesmanRule() => <String, dynamic>{
      'id': 'rule-priya',
      'salesman_id': 'user-1',
      'salesman_name': 'Priya Nair',
      'percentage': '4.0000',
      'effective_from': '2026-04-01',
      'effective_to': '2026-12-31',
      'status': 'ACTIVE',
      'version': 7,
    };

Json _emptyReport() => <String, dynamic>{
      'from_date': '2026-08-01',
      'to_date': '2026-08-23',
      'total_collected_amount': '0.00',
      'total_commission_amount': '0.00',
      'rows': const <Json>[],
    };

Json _report() => <String, dynamic>{
      'from_date': '2026-08-01',
      'to_date': '2026-08-31',
      'total_collected_amount': '18000.00',
      'total_commission_amount': '425.00',
      'rows': <Json>[
        <String, dynamic>{
          'salesman_id': 'user-1',
          'salesman_name': 'Priya Nair',
          'collected_amount': '12500.00',
          'commission_amount': '312.50',
          'invoice_count': 4,
        },
        <String, dynamic>{
          // Money collected against invoices that carried no salesman.
          'salesman_id': null,
          'salesman_name': 'Unassigned',
          'collected_amount': '5500.00',
          'commission_amount': '112.50',
          'invoice_count': 2,
        },
      ],
    };

Future<void> _pump(
  WidgetTester tester,
  _CommissionApi api, {
  PermissionService? permissions,
}) async {
  tester.view.physicalSize = const Size(1700, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: CommissionPage(
        api: api,
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

/// Move to the collections half of the screen, which reads the report.
Future<void> _showCollected(WidgetTester tester) async {
  await tester.tap(find.text('Collected'));
  await tester.pumpAndSettle();
}

Future<void> _openAddDialog(WidgetTester tester) async {
  await tester.tap(find.widgetWithText(FilledButton, 'Add rule'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the rates in force are listed', (tester) async {
    final _CommissionApi api =
        _CommissionApi(rules: <Json>[_firmWideRule(), _salesmanRule()]);
    await _pump(tester, api);

    expect(
      api.requested.where((call) => call.contains('/commission/rules')),
      isNotEmpty,
    );
    // The rate belonging to nobody says so, in words rather than by a blank
    // cell -- which is the whole point of the row.
    expect(find.text('Everyone (default)'), findsOneWidget);
    expect(find.text('Priya Nair'), findsOneWidget);
    expect(find.text('2.5%'), findsOneWidget);
    expect(find.text('4%'), findsOneWidget);
    expect(find.text('from 2026-01-01'), findsOneWidget);
    expect(find.text('2026-04-01 to 2026-12-31'), findsOneWidget);
    expect(
      find.textContaining('firm-wide default'),
      findsWidgets,
    );
  });

  testWidgets('a rate is recorded with its window and status', (tester) async {
    final _CommissionApi api = _CommissionApi();
    await _pump(tester, api);
    await _openAddDialog(tester);

    await tester.enterText(find.widgetWithText(TextField, 'Rate'), '2.5');
    await tester.enterText(
        find.widgetWithText(TextField, 'In force from'), '2026-01-01');
    await tester.enterText(
        find.widgetWithText(TextField, 'Until'), '2026-12-31');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.created!['percentage'], '2.5');
    expect(api.created!['effective_from'], '2026-01-01');
    expect(api.created!['effective_to'], '2026-12-31');
    expect(api.created!['status'], 'ACTIVE');
  });

  testWidgets('a rate can be agreed with somebody who has never had one',
      (tester) async {
    // The picker used to be built from the rules the screen had read, so the
    // only people it could offer were people who already had a rate: a new
    // salesman could never be given one from here. It reads the firm's own
    // members now, from an endpoint gated on COMMISSION_VIEW rather than on
    // the territory permission whoever sets commission need not hold.
    final _CommissionApi api = _CommissionApi(
      rules: <Json>[_firmWideRule()],
      salesmen: <Json>[
        <String, dynamic>{
          'user_id': 'user-9',
          'full_name': 'Ravi Menon',
          'email': 'ravi@firm.local',
        },
      ],
    );
    await _pump(tester, api);
    await _openAddDialog(tester);

    await tester.tap(find.text('Everyone (default)').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ravi Menon').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Rate'), '4');
    await tester.enterText(
        find.widgetWithText(TextField, 'In force from'), '2026-01-01');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.created!['salesman_id'], 'user-9');
    expect(api.created!['percentage'], '4');
  });

  testWidgets('somebody who has left is still shown on their own rule',
      (tester) async {
    // Their rule explains the payouts it made while it was in force, and a
    // stored id missing from the list makes DropdownButtonFormField assert --
    // which saves the rule as firm-wide, quietly paying everybody their rate.
    final _CommissionApi api = _CommissionApi(
      rules: <Json>[_salesmanRule()],
      salesmen: <Json>[
        <String, dynamic>{
          'user_id': 'user-9',
          'full_name': 'Ravi Menon',
          'email': 'ravi@firm.local',
        },
      ],
    );
    await _pump(tester, api);
    await _openAddDialog(tester);

    await tester.tap(find.text('Everyone (default)').last);
    await tester.pumpAndSettle();
    expect(find.text('Priya Nair'), findsWidgets);
    expect(find.text('Ravi Menon'), findsWidgets);
    await tester.tap(find.text('Everyone (default)').last);
    await tester.pumpAndSettle();
  });

  testWidgets('naming nobody records the firm-wide default', (tester) async {
    // Omitted rather than sent empty: the server reads a missing salesman as
    // the rate anybody with no rule of their own earns.
    final _CommissionApi api = _CommissionApi();
    await _pump(tester, api);
    await _openAddDialog(tester);

    // And the form says so, because a blank field explains nothing.
    expect(find.text('Everyone (default)'), findsOneWidget);
    expect(
      find.text('Leave as everyone for the firm-wide default.'),
      findsOneWidget,
    );

    await tester.enterText(find.widgetWithText(TextField, 'Rate'), '2.5');
    await tester.enterText(
        find.widgetWithText(TextField, 'In force from'), '2026-01-01');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.created!.containsKey('salesman_id'), isFalse);
    // An empty end date clears rather than being omitted, so a rule can be
    // made open-ended.
    expect(api.created!['effective_to'], isNull);
  });

  testWidgets('a rate above a hundred percent is refused before sending',
      (tester) async {
    final _CommissionApi api = _CommissionApi();
    await _pump(tester, api);
    await _openAddDialog(tester);

    await tester.enterText(find.widgetWithText(TextField, 'Rate'), '150');
    await tester.enterText(
        find.widgetWithText(TextField, 'In force from'), '2026-01-01');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(
      find.text('A commission rate must be between 0 and 100 percent.'),
      findsOneWidget,
    );
    expect(api.created, isNull);
    expect(
      api.requested.where((call) => call.startsWith('POST')),
      isEmpty,
    );
  });

  testWidgets('a window that closes before it opens is refused',
      (tester) async {
    final _CommissionApi api = _CommissionApi();
    await _pump(tester, api);
    await _openAddDialog(tester);

    await tester.enterText(find.widgetWithText(TextField, 'Rate'), '2.5');
    await tester.enterText(
        find.widgetWithText(TextField, 'In force from'), '2026-06-01');
    await tester.enterText(
        find.widgetWithText(TextField, 'Until'), '2026-01-01');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(find.text('The rate cannot end before it starts.'), findsOneWidget);
    expect(api.created, isNull);
  });

  testWidgets('an edit carries the version the row was read at',
      (tester) async {
    // Without it the save has no precondition at all, and a concurrent edit is
    // overwritten silently rather than refused.
    final _CommissionApi api = _CommissionApi(rules: <Json>[_salesmanRule()]);
    await _pump(tester, api);

    await tester.tap(find.widgetWithIcon(IconButton, Icons.edit_outlined));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Rate'), '5');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.sentVersion, 7);
    expect(api.updatedPath, '/api/v1/commission/rules/rule-priya');
    expect(api.updated!['percentage'], '5');
    // The person stays named. On an update the field is sent explicitly, so
    // clearing it can still move a rule back to the firm-wide scope.
    expect(api.updated!['salesman_id'], 'user-1');
  });

  testWidgets("a refused save shows the server's own sentence", (tester) async {
    final _CommissionApi api = _CommissionApi(
      refusal: const ApiException(
        'A rate already covers 2026-01-01 for this salesman.',
        statusCode: 400,
      ),
    );
    await _pump(tester, api);
    await _openAddDialog(tester);

    await tester.enterText(find.widgetWithText(TextField, 'Rate'), '2.5');
    await tester.enterText(
        find.widgetWithText(TextField, 'In force from'), '2026-01-01');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(
      find.text('A rate already covers 2026-01-01 for this salesman.'),
      findsOneWidget,
    );
  });

  testWidgets('the report shows each earner, the totals, and what earns them',
      (tester) async {
    final _CommissionApi api = _CommissionApi(report: _report());
    await _pump(tester, api);
    await _showCollected(tester);

    expect(
      api.requested.where((call) => call.contains('/commission/report')),
      isNotEmpty,
    );
    expect(find.text('Priya Nair'), findsOneWidget);
    expect(find.text('12500.00'), findsOneWidget);
    expect(find.text('312.50'), findsOneWidget);
    expect(find.text('4'), findsOneWidget);
    expect(find.text('18000.00'), findsOneWidget);
    expect(find.text('425.00'), findsOneWidget);
    // The single most surprising thing about commission, said on the screen
    // that reports it.
    expect(
      find.textContaining('money actually collected'),
      findsOneWidget,
    );
  });

  testWidgets('the bucket belonging to nobody is named, not hidden',
      (tester) async {
    final _CommissionApi api = _CommissionApi(report: _report());
    await _pump(tester, api);
    await _showCollected(tester);

    expect(
      find.text('Unassigned (no salesman on the invoice)'),
      findsOneWidget,
    );
    expect(find.text('5500.00'), findsOneWidget);
    expect(
      find.textContaining('carried no salesman'),
      findsOneWidget,
    );
  });

  testWidgets('a period that ends before it starts is refused',
      (tester) async {
    final _CommissionApi api = _CommissionApi(report: _report());
    await _pump(tester, api);
    await _showCollected(tester);

    await tester.enterText(
        find.widgetWithText(TextField, 'Collected from'), '2026-08-31');
    await tester.enterText(
        find.widgetWithText(TextField, 'Collected to'), '2026-08-01');
    await tester.tap(find.widgetWithText(FilledButton, 'Show'));
    await tester.pumpAndSettle();

    expect(find.text('The period cannot end before it starts.'), findsOneWidget);
  });

  testWidgets('without COMMISSION_MANAGE nothing can be added, and the '
      'report still reads', (tester) async {
    final _CommissionApi api = _CommissionApi(
      rules: <Json>[_firmWideRule()],
      report: _report(),
    );
    await _pump(
      tester,
      api,
      permissions: _permissions(perms: const ['COMMISSION_VIEW']),
    );

    expect(find.widgetWithText(FilledButton, 'Add rule'), findsNothing);
    expect(find.widgetWithIcon(IconButton, Icons.edit_outlined), findsNothing);
    // Reading what was earned needs no authority to change a rate.
    await _showCollected(tester);
    expect(find.text('Priya Nair'), findsOneWidget);
    expect(find.text('425.00'), findsOneWidget);
  });

  testWidgets('both halves and the form fit the smallest supported window',
      (tester) async {
    // 1366x768 is the floor every screen has to stay overflow-free at, and a
    // dropdown is the usual offender: its button row never constrains a long
    // label unless it is told to expand.
    final _CommissionApi api = _CommissionApi(
      rules: <Json>[_firmWideRule(), _salesmanRule()],
      report: _report(),
    );
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: CommissionPage(
          api: api,
          permissions: _permissions(),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await _openAddDialog(tester);
    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();
    await _showCollected(tester);

    expect(tester.takeException(), isNull);
  });

  testWidgets('a firm with no commission permission at all sees nothing',
      (tester) async {
    final _CommissionApi api = _CommissionApi(rules: <Json>[_firmWideRule()]);
    await _pump(
      tester,
      api,
      permissions: _permissions(perms: const ['CUSTOMER_VIEW']),
    );

    expect(find.text('You cannot see commission'), findsOneWidget);
    expect(api.requested, isEmpty);
  });
}
