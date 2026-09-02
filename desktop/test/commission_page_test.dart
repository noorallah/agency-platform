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
  List<String> perms = const [
    'COMMISSION_VIEW',
    'COMMISSION_MANAGE',
    'COMMISSION_PAY',
  ],
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
    this.payouts = const [],
    this.accounts = const [],
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

  /// What `GET /firm-members` answers with -- the firm's own people,
  /// which is what makes a rate for somebody who has never had one possible.
  final List<Json> salesmen;

  /// What `GET /commission/payouts` answers with.
  final List<Json> payouts;

  /// What `GET /finance/ledger-accounts` answers with -- deliberately
  /// including an income account, so the screen has something to filter out.
  final List<Json> accounts;

  final List<String> requested = <String>[];
  Json? created;
  Json? accrued;
  Json? paid;
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
    if (path.contains('/finance/ledger-accounts')) {
      return <String, dynamic>{'data': accounts};
    }
    if (path.contains('/commission/payouts')) {
      if (path.endsWith('/accrue')) {
        accrued = body;
        return <String, dynamic>{'data': const <Json>[]};
      }
      if (path.endsWith('/approve') || path.endsWith('/cancel')) {
        sentVersion = expectedVersion;
        return <String, dynamic>{'data': _draftPayout()};
      }
      if (path.endsWith('/pay')) {
        paid = body;
        sentVersion = expectedVersion;
        return <String, dynamic>{'data': _draftPayout()};
      }
      return <String, dynamic>{
        'data': payouts,
        'pagination': <String, dynamic>{'total_records': payouts.length},
      };
    }
    if (path.contains('/commission/report')) {
      return <String, dynamic>{'data': report ?? _emptyReport()};
    }
    if (path.contains('/firm-members')) {
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

/// One accrued period, still a draft: nothing has reached the ledger.
Json _draftPayout() => <String, dynamic>{
      'id': 'p-1',
      'salesman_id': 'user-1',
      'salesman_name': 'Asha Rao',
      'period_start': '2026-04-01',
      'period_end': '2026-04-30',
      'basis': 'COLLECTED',
      'measured_amount': '5000.00',
      'earned_amount': '500.00',
      'adjustment_amount': '0.00',
      'adjustment_reason': null,
      'payable_amount': '500.00',
      'status': 'DRAFT',
      'accrued_on': '2026-04-30',
      'paid_on': null,
      'money_account_id': null,
      'journal_entry_id': null,
      'payment_journal_entry_id': null,
      'notes': null,
      'version': 3,
    };

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

/// Move to the payouts part of the screen.
Future<void> _showPayouts(WidgetTester tester) async {
  await tester.tap(find.text('Payouts'));
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
    // members now, from one endpoint whose gate is membership of the firm --
    // there were three of these behind three different permissions, and the
    // sales-order form could call none of them.
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
      payouts: <Json>[_draftPayout()],
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
    await _showPayouts(tester);

    expect(tester.takeException(), isNull);
    // The row actions have to be reachable, not merely rendered. Eight
    // columns put Approve past the right edge at every window size, where a
    // test that only asked whether the widget existed said nothing was wrong.
    await tester.tap(find.text('Approve'));
    await tester.pumpAndSettle();
    expect(
      api.requested,
      contains('POST /api/v1/commission/payouts/p-1/approve'),
    );
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

  // --------------------------------------------------------------------
  // The ladder
  // --------------------------------------------------------------------

  testWidgets('a ladder is typed rung by rung and sent whole', (tester) async {
    final _CommissionApi api = _CommissionApi();
    await _pump(tester, api);
    await _openAddDialog(tester);

    await tester.enterText(find.widgetWithText(TextField, 'Rate'), '0');
    await tester.enterText(
        find.widgetWithText(TextField, 'In force from'), '2026-01-01');
    await tester.tap(find.widgetWithText(TextButton, 'Add slab'));
    await tester.pumpAndSettle();
    // A new rung starts where the previous one stopped, which is the only
    // shape the server accepts: the rungs have to meet exactly.
    expect(find.widgetWithText(TextField, 'From'), findsOneWidget);
    await tester.enterText(find.widgetWithText(TextField, 'To'), '100000');
    await tester.enterText(find.widgetWithText(TextField, 'Rate').last, '2');
    await tester.tap(find.widgetWithText(TextButton, 'Add slab'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Rate').last, '3');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    final List<dynamic> slabs = api.created!['slabs'] as List<dynamic>;
    expect(slabs.length, 2);
    expect((slabs.first as Map)['from_amount'], '0');
    expect((slabs.first as Map)['to_amount'], '100000');
    expect((slabs.first as Map)['percentage'], '2');
    // The top rung runs on, so it carries no ceiling at all.
    expect((slabs.last as Map).containsKey('to_amount'), isFalse);
    expect(api.created!['slab_mode'], 'MARGINAL');
  });

  testWidgets('a ladder with a gap is refused before sending', (tester) async {
    final _CommissionApi api = _CommissionApi();
    await _pump(tester, api);
    await _openAddDialog(tester);

    await tester.enterText(find.widgetWithText(TextField, 'Rate'), '0');
    await tester.enterText(
        find.widgetWithText(TextField, 'In force from'), '2026-01-01');
    await tester.tap(find.widgetWithText(TextButton, 'Add slab'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'To'), '100');
    await tester.enterText(find.widgetWithText(TextField, 'Rate').last, '2');
    await tester.tap(find.widgetWithText(TextButton, 'Add slab'));
    await tester.pumpAndSettle();
    // Break the join the form filled in for us: 100 does not continue at 200.
    await tester.enterText(find.widgetWithText(TextField, 'From').last, '200');
    await tester.enterText(find.widgetWithText(TextField, 'Rate').last, '3');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.created, isNull, reason: 'a gap never reaches the server');
    expect(find.textContaining('meet exactly'), findsOneWidget);
  });

  testWidgets('a ladder starting above zero is refused', (tester) async {
    final _CommissionApi api = _CommissionApi();
    await _pump(tester, api);
    await _openAddDialog(tester);

    await tester.enterText(find.widgetWithText(TextField, 'Rate'), '0');
    await tester.enterText(
        find.widgetWithText(TextField, 'In force from'), '2026-01-01');
    await tester.tap(find.widgetWithText(TextButton, 'Add slab'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'From'), '1000');
    await tester.enterText(find.widgetWithText(TextField, 'Rate').last, '2');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.created, isNull);
    expect(find.textContaining('must start at 0'), findsOneWidget);
  });

  testWidgets('a rule paid on invoiced value says so on the list',
      (tester) async {
    final _CommissionApi api = _CommissionApi(rules: <Json>[
      <String, dynamic>{
        ..._salesmanRule(),
        'basis': 'INVOICED',
      },
    ]);
    await _pump(tester, api);

    // Two firms can run the same percentage and mean different money by it,
    // so a list that showed only the number would be unreadable.
    expect(find.text('Invoiced value'), findsOneWidget);
  });

  testWidgets('a rule with slabs shows its shape, not the flat field it '
      'overrides', (tester) async {
    final _CommissionApi api = _CommissionApi(rules: <Json>[
      <String, dynamic>{
        ..._salesmanRule(),
        'percentage': '4.0000',
        'slab_mode': 'WHOLE_AMOUNT',
        'slabs': <Json>[
          <String, dynamic>{
            'sequence': 1,
            'from_amount': '0.00',
            'to_amount': '100000.00',
            'percentage': '2.0000',
          },
          <String, dynamic>{
            'sequence': 2,
            'from_amount': '100000.00',
            'to_amount': null,
            'percentage': '3.0000',
          },
        ],
      },
    ]);
    await _pump(tester, api);

    // 4% is on the record and is not what this rule pays; printing it would
    // be printing the one number nobody should read as the arrangement.
    expect(find.text('4%'), findsNothing);
    expect(find.text('2 slabs (whole amount)'), findsOneWidget);
  });

  testWidgets('the report shows what was billed beside what was collected',
      (tester) async {
    final _CommissionApi api = _CommissionApi(report: <String, dynamic>{
      'from_date': '2026-04-01',
      'to_date': '2026-04-30',
      'total_collected_amount': '12500.00',
      'total_invoiced_amount': '40000.00',
      'total_commission_amount': '1200.00',
      'rows': <Json>[
        <String, dynamic>{
          'salesman_id': 'user-1',
          'salesman_name': 'Priya Nair',
          'collected_amount': '12500.00',
          'invoiced_amount': '40000.00',
          'basis': 'INVOICED',
          'commission_amount': '1200.00',
          'invoice_count': 4,
        },
      ],
    });
    await _pump(tester, api);
    await _showCollected(tester);

    // A payout of 1,200 against 12,500 collected reads as an error until the
    // column says the rule is on invoiced value.
    expect(find.text('40000.00'), findsWidgets);
    expect(find.text('Invoiced value'), findsOneWidget);
  });

  // --------------------------------------------------------------------
  // Payouts
  // --------------------------------------------------------------------

  testWidgets('a draft payout offers approval and nothing else',
      (tester) async {
    final _CommissionApi api = _CommissionApi(payouts: <Json>[_draftPayout()]);
    await _pump(tester, api);
    await _showPayouts(tester);

    expect(find.text('Asha Rao'), findsOneWidget);
    expect(find.text('Approve'), findsOneWidget);
    // Paying an unapproved payout is refused by the server, and a button that
    // is going to be refused reads as a working action until somebody needs
    // it.
    expect(find.text('Pay'), findsNothing);
    expect(find.text('Cancel'), findsOneWidget);
  });

  testWidgets('an approved payout offers payment', (tester) async {
    final _CommissionApi api = _CommissionApi(
      payouts: <Json>[
        <String, dynamic>{..._draftPayout(), 'status': 'APPROVED'},
      ],
    );
    await _pump(tester, api);
    await _showPayouts(tester);

    expect(find.text('Pay'), findsOneWidget);
    expect(find.text('Approve'), findsNothing);
  });

  testWidgets('a paid payout offers nothing at all', (tester) async {
    final _CommissionApi api = _CommissionApi(
      payouts: <Json>[
        <String, dynamic>{..._draftPayout(), 'status': 'PAID'},
      ],
    );
    await _pump(tester, api);
    await _showPayouts(tester);

    expect(find.text('Approve'), findsNothing);
    expect(find.text('Pay'), findsNothing);
    expect(find.text('Cancel'), findsNothing);
  });

  testWidgets('without COMMISSION_PAY the Pay action is not offered',
      (tester) async {
    final _CommissionApi api = _CommissionApi(
      payouts: <Json>[
        <String, dynamic>{..._draftPayout(), 'status': 'APPROVED'},
      ],
    );
    await _pump(
      tester,
      api,
      // Whoever states a debt should not be the one who moves the cash.
      permissions: _permissions(
        perms: const ['COMMISSION_VIEW', 'COMMISSION_MANAGE'],
      ),
    );
    await _showPayouts(tester);

    expect(find.text('Pay'), findsNothing);
    expect(find.text('Cancel'), findsOneWidget);
  });

  testWidgets('approving carries the version the row was read at',
      (tester) async {
    final _CommissionApi api = _CommissionApi(payouts: <Json>[_draftPayout()]);
    await _pump(tester, api);
    await _showPayouts(tester);

    await tester.tap(find.text('Approve'));
    await tester.pumpAndSettle();

    expect(api.requested, contains('POST /api/v1/commission/payouts/p-1/approve'));
    expect(api.sentVersion, 3);
  });

  testWidgets('an accrual sends only the period', (tester) async {
    final _CommissionApi api = _CommissionApi();
    await _pump(tester, api);
    await _showPayouts(tester);

    await tester.tap(find.widgetWithText(FilledButton, 'Accrue period'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextField, 'From'), '2026-04-01');
    await tester.enterText(find.widgetWithText(TextField, 'To'), '2026-04-30');
    await tester.tap(find.widgetWithText(FilledButton, 'Accrue'));
    await tester.pumpAndSettle();

    // The amounts come from the report, not from anybody's typing.
    expect(api.accrued, <String, dynamic>{
      'period_start': '2026-04-01',
      'period_end': '2026-04-30',
    });
  });

  testWidgets('an accrual period that runs backwards is refused before sending',
      (tester) async {
    final _CommissionApi api = _CommissionApi();
    await _pump(tester, api);
    await _showPayouts(tester);

    await tester.tap(find.widgetWithText(FilledButton, 'Accrue period'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextField, 'From'), '2026-04-30');
    await tester.enterText(find.widgetWithText(TextField, 'To'), '2026-04-01');
    await tester.tap(find.widgetWithText(FilledButton, 'Accrue'));
    await tester.pumpAndSettle();

    expect(api.accrued, isNull);
    expect(find.textContaining('cannot end before it starts'), findsOneWidget);
  });

  testWidgets('the payment form offers only accounts money can leave from',
      (tester) async {
    final _CommissionApi api = _CommissionApi(
      payouts: <Json>[
        <String, dynamic>{..._draftPayout(), 'status': 'APPROVED'},
      ],
      accounts: <Json>[
        <String, dynamic>{
          'id': 'acct-cash',
          'firm_id': 'firm-1',
          'account_group_id': 'g1',
          'code': '1000',
          'name': 'Cash',
          'account_type': 'ASSET',
          'description': '',
          'is_balance_sheet': true,
          'is_profit_loss': false,
          'requires_cost_center': false,
          'requires_profit_center': false,
          'is_active': true,
        },
        <String, dynamic>{
          'id': 'acct-sales',
          'firm_id': 'firm-1',
          'account_group_id': 'g2',
          'code': '4000',
          'name': 'Sales Revenue',
          'account_type': 'INCOME',
          'description': '',
          'is_balance_sheet': false,
          'is_profit_loss': true,
          'requires_cost_center': false,
          'requires_profit_center': false,
          'is_active': true,
        },
      ],
    );
    await _pump(tester, api);
    await _showPayouts(tester);

    await tester.tap(find.text('Pay'));
    await tester.pumpAndSettle();

    // Offering the whole chart would invite a payment posted against revenue.
    expect(find.text('1000 — Cash'), findsOneWidget);
    expect(find.text('4000 — Sales Revenue'), findsNothing);

    await tester.tap(find.widgetWithText(FilledButton, 'Record payment'));
    await tester.pumpAndSettle();
    expect(api.paid!['money_account_id'], 'acct-cash');
  });
}
