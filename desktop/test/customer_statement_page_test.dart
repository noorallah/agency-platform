// The two things this screen must not do: fold an advance into the balance,
// and leave one customer's account on screen under another customer's name.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/customers/customer_statement_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({
  List<String> perms = const ['CUSTOMER_VIEW'],
}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

class _StatementApi extends ApiClient {
  _StatementApi({
    this.ageing = const [],
    this.statement,
    this.failStatementWith,
  }) : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> ageing;
  final Json? statement;
  final String? failStatementWith;
  final List<String> requested = <String>[];

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
    requested.add(path);
    if (path.endsWith('/statement')) {
      if (failStatementWith != null) {
        throw ApiException(failStatementWith!, statusCode: 400);
      }
      return <String, dynamic>{'data': statement};
    }
    return <String, dynamic>{'data': ageing};
  }
}

Json _ageingRow() => <String, dynamic>{
      'customer_id': 'cust-1',
      'customer_code': 'C1',
      'customer_name': 'Kumar Stores',
      'as_of': '2026-06-01',
      'total_outstanding': '1500.00',
      'account_balance': '1200.00',
      'unapplied_credits': '300.00',
      'charges_not_billed': '0.00',
      'buckets': <Json>[
        <String, dynamic>{'from_days': 0, 'to_days': 29, 'amount': '100.00'},
        <String, dynamic>{'from_days': 30, 'to_days': 59, 'amount': '200.00'},
        <String, dynamic>{'from_days': 60, 'to_days': 89, 'amount': '400.00'},
        <String, dynamic>{'from_days': 90, 'to_days': null, 'amount': '800.00'},
      ],
      'invoices': <Json>[],
    };

Json _statement() => <String, dynamic>{
      'customer_id': 'cust-1',
      'customer_code': 'C1',
      'customer_name': 'Kumar Stores',
      'from_date': '2026-04-01',
      'to_date': '2026-04-30',
      'opening_balance': '2000.00',
      'closing_balance': '3000.00',
      'unapplied_advance': '750.00',
      'lines': <Json>[
        <String, dynamic>{
          'transaction_date': '2026-04-10',
          'transaction_type': 'INVOICE',
          'reference_number': 'SI-1',
          'debit': '1000.00',
          'credit': '0.00',
          'balance': '3000.00',
        },
      ],
    };

Future<void> _pump(
  WidgetTester tester,
  _StatementApi api, {
  PermissionService? permissions,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: CustomerStatementPage(
        api: api,
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the ageing shows every band, including the open-ended one',
      (tester) async {
    await _pump(tester, _StatementApi(ageing: <Json>[_ageingRow()]));

    // Every band, in the same shape every time, so the eye can compare down
    // a column. The last one is open-ended and has to say so.
    expect(find.textContaining('0-29: 100.00'), findsOneWidget);
    expect(find.textContaining('90+: 800.00'), findsOneWidget);
    expect(find.text('1500.00'), findsOneWidget);
  });

  testWidgets('an advance is reported beside the balance, not inside it',
      (tester) async {
    final _StatementApi api = _StatementApi(
      ageing: <Json>[_ageingRow()],
      statement: _statement(),
    );
    await _pump(tester, api);
    await tester.tap(find.textContaining('Kumar Stores'));
    await tester.pumpAndSettle();

    // Netting them would hide money the customer can have applied.
    expect(find.textContaining('closed at 3000.00'), findsOneWidget);
    expect(find.textContaining('750.00 held on account'), findsOneWidget);
  });

  testWidgets('the statement lists the movement with its running balance',
      (tester) async {
    await _pump(
      tester,
      _StatementApi(ageing: <Json>[_ageingRow()], statement: _statement()),
    );
    await tester.tap(find.textContaining('Kumar Stores'));
    await tester.pumpAndSettle();

    expect(find.text('SI-1'), findsOneWidget);
    expect(find.text('1000.00'), findsOneWidget);
    expect(find.textContaining('opened at 2000.00'), findsOneWidget);
  });

  testWidgets('a refused statement reports the refusal, not an account',
      (tester) async {
    final _StatementApi api = _StatementApi(
      ageing: <Json>[_ageingRow()],
      failStatementWith: 'That period is not open.',
    );
    await _pump(tester, api);
    await tester.tap(find.textContaining('Kumar Stores'));
    await tester.pumpAndSettle();

    expect(find.textContaining('That period is not open.'), findsOneWidget);
    expect(find.text('SI-1'), findsNothing);
  });

  testWidgets('a firm with nothing outstanding says so', (tester) async {
    await _pump(tester, _StatementApi());

    expect(find.textContaining('settled in full'), findsOneWidget);
  });

  testWidgets('someone without the view permission sees nothing',
      (tester) async {
    await _pump(
      tester,
      _StatementApi(ageing: <Json>[_ageingRow()]),
      permissions: _permissions(perms: const <String>['PRODUCT_VIEW']),
    );

    expect(find.textContaining('view customers permission'), findsOneWidget);
    expect(find.textContaining('Kumar Stores'), findsNothing);
  });

  testWidgets('the ageing says how the bills differ from the account',
      (tester) async {
    await _pump(tester, _StatementApi(ageing: <Json>[_ageingRow()]));

    // Two reports about one customer that disagree, with nothing to explain
    // the gap, is a bug report waiting to be filed.
    expect(find.textContaining('less 300.00 credit = 1200.00'), findsOneWidget);
  });
}
