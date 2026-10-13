// The account as rows (backlog 121, M3): the last entries, and a last row that
// adds a receipt -- for the customer, or against one bill. What it must not
// do: send a receipt the client can see is wrong, send one twice, or lose what
// was typed when the server says no.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/customers/customer_statement_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({bool mayReceive = true}) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>[
      'CUSTOMER_VIEW',
      if (mayReceive) 'RECEIPT_CREATE',
    ],
  }));

class _Call {
  _Call(this.method, this.path, this.query, this.body);

  final String method;
  final String path;
  final Map<String, String> query;
  final Json? body;
}

class _AccountApi extends ApiClient {
  _AccountApi({this.totalEntries = 143, this.refuseReceiptWith})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final int totalEntries;
  final String? refuseReceiptWith;
  final List<_Call> calls = <_Call>[];

  List<_Call> where(String method, String suffix) => [
        for (final _Call call in calls)
          if (call.method == method && call.path.endsWith(suffix)) call,
      ];

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
    calls.add(_Call(method, path, query ?? const <String, String>{}, body));
    if (path.endsWith('/account')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'customer_id': 'cust-1',
          'customer_name': 'Kumar Stores',
          'opening_balance': '500.00',
          'closing_balance': '1250.00',
          'total_entries': totalEntries,
          'lines': <Json>[
            <String, dynamic>{
              'transaction_date': '2026-04-10',
              'transaction_type': 'INVOICE',
              'reference_number': 'SI-1',
              'remarks': '',
              'debit': '1250.00',
              'credit': '0.00',
              'balance': '1750.00',
            },
            <String, dynamic>{
              'transaction_date': '2026-04-12',
              'transaction_type': 'PAYMENT',
              'reference_number': 'RCP-7',
              'remarks': 'part',
              'debit': '0.00',
              'credit': '500.00',
              'balance': '1250.00',
            },
          ],
        },
      };
    }
    if (path.endsWith('/receipts/outstanding')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'invoice_id': 'inv-12',
            'invoice_number': 'INV-0012',
            'invoice_date': '2026-04-10',
            'invoice_total': '1250.00',
            'allocated_amount': '0.00',
            'outstanding_amount': '1250.00',
          },
        ],
      };
    }
    if (method == 'POST' && path.endsWith('/receipts')) {
      if (refuseReceiptWith != null) {
        throw ApiException(refuseReceiptWith!, statusCode: 400);
      }
      return <String, dynamic>{
        'data': <String, dynamic>{'id': 's-1', 'settlement_number': 'RCP-8'},
      };
    }
    return <String, dynamic>{
      'data': <Json>[
        <String, dynamic>{
          'customer_id': 'cust-1',
          'customer_code': 'C1',
          'customer_name': 'Kumar Stores',
          'total_outstanding': '1250.00',
          'buckets': <Json>[],
        },
      ],
    };
  }
}

/// Open the page, pick Kumar Stores, and switch to Account.
Future<void> _openAccount(WidgetTester tester, _AccountApi api,
    {PermissionService? permissions}) async {
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
  await tester.tap(find.textContaining('Kumar Stores'));
  await tester.pumpAndSettle();
  api.calls.clear();
  await tester.tap(find.byKey(const ValueKey('view-account')));
  await tester.pumpAndSettle();
}

Future<void> _type(WidgetTester tester, String key, String text) async {
  await tester.enterText(find.byKey(ValueKey(key)), text);
  await tester.pump();
}

Future<void> _chooseBill(WidgetTester tester) async {
  // Typing in the amount box scrolls the table sideways at 800 wide.
  await tester.ensureVisible(find.byKey(const ValueKey('account-row-against')));
  await tester.pump();
  await tester.tap(find.byKey(const ValueKey('account-row-against')));
  await tester.pumpAndSettle();
  await tester.tap(find.text('INV-0012 · owes 1,250.00').last);
  await tester.pumpAndSettle();
}

Future<void> _add(WidgetTester tester) async {
  // At 800 wide the table scrolls sideways, and Add is at its right end.
  await tester.ensureVisible(find.byKey(const ValueKey('account-row-add')));
  await tester.pump();
  await tester.tap(find.byKey(const ValueKey('account-row-add')));
  await tester.pumpAndSettle();
}

String _amountBox(WidgetTester tester) => tester
    .widget<TextField>(find.byKey(const ValueKey('account-row-amount')))
    .controller!
    .text;

void main() {
  testWidgets('the rows, the caption, and the balance the hidden ones left',
      (tester) async {
    await _openAccount(tester, _AccountApi());

    expect(find.textContaining('The last 2 of 143 entries'), findsOneWidget);
    expect(find.text('Opening balance'), findsOneWidget);
    expect(find.text('500.00'), findsNWidgets(2)); // opening, and the credit
    expect(find.text('SI-1'), findsOneWidget);
    expect(find.text('RCP-7'), findsOneWidget);
    expect(find.text('1250.00'), findsNWidgets(2)); // the debit and a balance
    expect(tester.takeException(), isNull);
  });

  testWidgets('no opening balance row when nothing is hidden', (tester) async {
    await _openAccount(tester, _AccountApi(totalEntries: 2));

    expect(find.text('Opening balance'), findsNothing);
    expect(find.textContaining('All 2 entries'), findsOneWidget);
  });

  testWidgets('the chooser reads the account again with the new count',
      (tester) async {
    final _AccountApi api = _AccountApi();
    await _openAccount(tester, api);
    expect(api.where('GET', '/account').single.query['last'], '20');

    await tester.tap(find.byKey(const ValueKey('account-last-chooser')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Show 50').last);
    await tester.pumpAndSettle();

    expect(api.where('GET', '/account').map((c) => c.query['last']),
        ['20', '50']);
    // The bills did not change, so they are not read again.
    expect(api.where('GET', '/receipts/outstanding'), hasLength(1));
  });

  testWidgets('opening it is two reads, and nothing else', (tester) async {
    final _AccountApi api = _AccountApi();
    await _openAccount(tester, api);

    expect(api.calls.map((c) => '${c.method} ${c.path}'), [
      'GET /api/v1/customers/cust-1/account',
      'GET /api/v1/receipts/outstanding',
    ]);
    expect(api.calls.last.query, {'customer_id': 'cust-1'});
  });

  testWidgets('without the receipt permission there is no row and no bills read',
      (tester) async {
    final _AccountApi api = _AccountApi();
    await _openAccount(tester, api, permissions: _permissions(mayReceive: false));

    expect(find.byKey(const ValueKey('account-row-add')), findsNothing);
    expect(find.text('SI-1'), findsOneWidget);
    expect(api.calls.map((c) => c.path), [
      '/api/v1/customers/cust-1/account',
    ]);
  });

  testWidgets('a receipt against one bill sends that bill and nothing else',
      (tester) async {
    final _AccountApi api = _AccountApi();
    await _openAccount(tester, api);

    await _chooseBill(tester);
    // The amount was empty, so it takes what the bill owes.
    expect(_amountBox(tester), '1250.00');
    await _type(tester, 'account-row-reference', 'UTR-9');
    api.calls.clear();
    await _add(tester);

    final _Call post = api.where('POST', '/receipts').single;
    expect(post.body, {
      'party_id': 'cust-1',
      'settlement_date': DateTime.now().toIso8601String().substring(0, 10),
      'amount': '1250.00',
      'method': 'BANK',
      'payment_mode': 'BANK_TRANSFER',
      'instrument_reference': 'UTR-9',
      'allocations': [
        {'invoice_id': 'inv-12', 'amount': '1250.00'},
      ],
    });
    expect(find.textContaining('Receipt RCP-8 recorded'), findsOneWidget);
    // One post, then the account and the bills again.
    expect(api.calls.map((c) => '${c.method} ${c.path}'), [
      'POST /api/v1/receipts',
      'GET /api/v1/customers/cust-1/account',
      'GET /api/v1/receipts/outstanding',
    ]);
    // The row is clear again.
    expect(_amountBox(tester), '');
  });

  testWidgets('a typed amount is not overwritten by choosing a bill',
      (tester) async {
    await _openAccount(tester, _AccountApi());

    await _type(tester, 'account-row-amount', '300');
    await _chooseBill(tester);

    expect(_amountBox(tester), '300');
  });

  testWidgets('on account sends no allocation', (tester) async {
    final _AccountApi api = _AccountApi();
    await _openAccount(tester, api);

    await _type(tester, 'account-row-amount', '700');
    await _add(tester);

    final Json body = api.where('POST', '/receipts').single.body!;
    expect(body['allocations'], isEmpty);
    expect(body['amount'], '700');
    expect(body['party_id'], 'cust-1');
    expect(body.containsKey('instrument_reference'), isFalse);
  });

  testWidgets('more than the bill owes is refused without a request',
      (tester) async {
    final _AccountApi api = _AccountApi();
    await _openAccount(tester, api);

    await _chooseBill(tester);
    await _type(tester, 'account-row-amount', '1300');
    await _add(tester);

    expect(api.where('POST', '/receipts'), isEmpty);
    expect(find.byKey(const ValueKey('account-row-error')), findsOneWidget);
    expect(find.textContaining('INV-0012 owes 1,250.00'), findsOneWidget);
    expect(_amountBox(tester), '1300');
  });

  testWidgets('no amount is refused without a request', (tester) async {
    final _AccountApi api = _AccountApi();
    await _openAccount(tester, api);

    await _add(tester);

    expect(api.where('POST', '/receipts'), isEmpty);
    expect(find.textContaining('Enter how much was received'), findsOneWidget);
  });

  testWidgets('a refusal from the server is shown and what was typed stays',
      (tester) async {
    final _AccountApi api =
        _AccountApi(refuseReceiptWith: 'That period is closed.');
    await _openAccount(tester, api);

    await _type(tester, 'account-row-amount', '700');
    await _type(tester, 'account-row-reference', 'CHQ-1');
    api.calls.clear();
    await _add(tester);

    expect(find.byKey(const ValueKey('account-row-error')), findsOneWidget);
    expect(find.text('That period is closed.'), findsOneWidget);
    expect(_amountBox(tester), '700');
    expect(
      tester
          .widget<TextField>(find.byKey(const ValueKey('account-row-reference')))
          .controller!
          .text,
      'CHQ-1',
    );
    // The post and nothing after it.
    expect(api.calls, hasLength(1));
    expect(find.text('SI-1'), findsOneWidget);
  });

  testWidgets('two taps on Add send one receipt', (tester) async {
    final _AccountApi api = _AccountApi();
    await _openAccount(tester, api);

    await _type(tester, 'account-row-amount', '700');
    final Finder add = find.byKey(const ValueKey('account-row-add'));
    await tester.ensureVisible(add);
    await tester.pump();
    await tester.tap(add);
    await tester.tap(add);
    await tester.pumpAndSettle();

    expect(api.where('POST', '/receipts'), hasLength(1));
  });
}
