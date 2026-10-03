// The post-dated cheque register (ACC-2).
//
// The grid lists the cheques with their status; a new cheque posts the keys
// the server declares to the received register; banking posts to /deposit; the
// bounce dialog offers a charge to the customer on the received screen only.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/settlement.dart';
import 'package:agency_desktop/models/settlement_direction.dart';
import 'package:agency_desktop/ui/finance/post_dated_cheque_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({
  List<String> perms = const [
    'RECEIPT_VIEW',
    'RECEIPT_CREATE',
    'PAYMENT_VIEW',
    'PAYMENT_CREATE',
  ],
}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

Json _cheque(String id, String number, String status, {bool due = false}) =>
    <String, dynamic>{
      'id': id,
      'direction': 'RECEIVED',
      'party_id': 'c-1',
      'party_code': 'C1',
      'party_name': 'Mehta Traders',
      'cheque_number': number,
      'cheque_date': '2026-10-20',
      'drawn_on_bank': 'HDFC',
      'amount': '12500.0000',
      'received_on': '2026-10-01',
      'status': status,
      'is_due': due,
      'settlement_number': status == 'HELD' ? null : 'RCT-0001',
      'version': 2,
    };

class _Api extends ApiClient {
  _Api({this.rows = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;
  final List<String> requested = <String>[];
  final List<Map<String, String>?> queries = [];
  Json? created;
  Json? deposited;
  Json? bounced;

  @override
  Future<List<PartyOption>> settlementParties({
    required SettlementDirection direction,
    String search = '',
  }) async =>
      const [PartyOption(id: 'c-1', code: 'C1', name: 'Mehta Traders')];

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
    if (method == 'POST' && path.endsWith('/post-dated-cheques/received')) {
      created = body;
      return <String, dynamic>{'data': _cheque('n-1', '000123', 'HELD')};
    }
    if (path.endsWith('/deposit')) {
      deposited = body;
      return <String, dynamic>{'data': _cheque('h-1', '000123', 'DEPOSITED')};
    }
    if (path.endsWith('/bounce')) {
      bounced = body;
      return <String, dynamic>{'data': _cheque('d-1', '000124', 'BOUNCED')};
    }
    if (method == 'GET' && path.contains('/post-dated-cheques/')) {
      queries.add(query);
      return <String, dynamic>{
        'data': rows,
        'pagination': <String, dynamic>{'total_records': rows.length},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('post-dated-cheques'),
    );

Future<void> _pump(
  WidgetTester tester,
  _Api api, {
  bool issued = false,
  PermissionService? permissions,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: PostDatedChequePage(
        api: api,
        preferences: _preferences(),
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
        issued: issued,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester, String number) async {
  await tester.tap(find.text(number).first);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the grid lists the register with status and amount',
      (tester) async {
    final _Api api = _Api(rows: <Json>[
      _cheque('h-1', '000123', 'HELD', due: true),
      _cheque('d-1', '000124', 'DEPOSITED'),
    ]);
    await _pump(tester, api);

    expect(api.requested.first,
        'GET /api/v1/post-dated-cheques/received');
    expect(find.text('000123'), findsOneWidget);
    expect(find.text('000124'), findsOneWidget);
    expect(find.text('Mehta Traders'), findsWidgets);
    expect(find.text('Held'), findsOneWidget);
    expect(find.text('Deposited'), findsOneWidget);
    expect(find.textContaining('12,500'), findsWidgets);
    expect(find.text('RCT-0001'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Due to deposit asks for the cheques due today',
      (tester) async {
    final _Api api = _Api(rows: <Json>[_cheque('h-1', '000123', 'HELD')]);
    await _pump(tester, api);
    await tester.tap(find.byKey(const ValueKey('pdc-status-filter')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('pdc-due-filter')));
    await tester.pumpAndSettle();

    expect(api.queries.last!['due_on'], isNotNull);
    expect(api.queries.last!['due_on'], hasLength(10));
  });

  testWidgets('a new cheque posts the declared keys to the received register',
      (tester) async {
    final _Api api = _Api(rows: <Json>[_cheque('h-1', '000123', 'HELD')]);
    await _pump(tester, api);
    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(const ValueKey('pdc-party')), 'Mehta');
    await tester.pumpAndSettle();
    await tester.tap(find.text('C1  Mehta Traders').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('pdc-number')), '000123');
    await tester.enterText(find.byKey(const ValueKey('pdc-amount')), '12500');
    await tester.enterText(find.byKey(const ValueKey('pdc-bank')), 'HDFC');
    await tester.tap(find.byKey(const ValueKey('pdc-save')));
    await tester.pumpAndSettle();

    expect(api.requested,
        contains('POST /api/v1/post-dated-cheques/received'));
    expect(api.created, <String, dynamic>{
      'party_id': 'c-1',
      'cheque_number': '000123',
      'cheque_date': api.created!['cheque_date'],
      'drawn_on_bank': 'HDFC',
      'amount': '12500',
      'received_on': api.created!['received_on'],
    });
    expect(tester.takeException(), isNull);
  });

  testWidgets('a cheque with no party is refused before the server',
      (tester) async {
    final _Api api = _Api(rows: <Json>[_cheque('h-1', '000123', 'HELD')]);
    await _pump(tester, api);
    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('pdc-save')));
    await tester.pumpAndSettle();

    expect(api.created, isNull);
    expect(find.byKey(const ValueKey('pdc-problem')), findsOneWidget);
  });

  testWidgets('depositing a held cheque posts to /deposit', (tester) async {
    final _Api api = _Api(rows: <Json>[_cheque('h-1', '000123', 'HELD')]);
    await _pump(tester, api);
    await _select(tester, '000123');
    await tester.tap(find.byKey(const ValueKey('selection-deposit')));
    await tester.pumpAndSettle();
    expect(find.textContaining('stays on account'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('pdc-deposit-save')));
    await tester.pumpAndSettle();

    expect(api.requested,
        contains('POST /api/v1/post-dated-cheques/received/h-1/deposit'));
    expect(api.deposited!.keys, contains('deposited_on'));
    expect(tester.takeException(), isNull);
  });

  testWidgets('bounce is offered only on a deposited cheque, and the '
      'received screen offers a charge to the customer', (tester) async {
    final _Api api = _Api(rows: <Json>[
      _cheque('h-1', '000123', 'HELD'),
      _cheque('d-1', '000124', 'DEPOSITED'),
    ]);
    await _pump(tester, api);

    await _select(tester, '000123');
    // The selection bar offers only what the row can do.
    expect(find.byKey(const ValueKey('selection-bounce')), findsNothing);
    expect(find.byKey(const ValueKey('selection-deposit')), findsOneWidget);

    await _select(tester, '000124');
    await tester.tap(find.byKey(const ValueKey('selection-bounce')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('pdc-customer-charge')), findsOneWidget);
    expect(find.textContaining('is reversed'), findsOneWidget);

    await tester.enterText(
        find.byKey(const ValueKey('pdc-bounce-reason')), 'Insufficient funds');
    await tester.enterText(
        find.byKey(const ValueKey('pdc-customer-charge')), '250');
    await tester.tap(find.byKey(const ValueKey('pdc-bounce-save')));
    await tester.pumpAndSettle();

    expect(api.requested,
        contains('POST /api/v1/post-dated-cheques/received/d-1/bounce'));
    expect(api.bounced, <String, dynamic>{
      'bounced_on': api.bounced!['bounced_on'],
      'reason': 'Insufficient funds',
      'customer_charge_amount': '250',
    });
  });

  testWidgets('the issued screen reads the issued register and has no '
      'customer charge', (tester) async {
    final _Api api =
        _Api(rows: <Json>[_cheque('d-1', '000124', 'DEPOSITED')]);
    await _pump(tester, api, issued: true);

    expect(api.requested.first, 'GET /api/v1/post-dated-cheques/issued');
    await _select(tester, '000124');
    expect(find.byKey(const ValueKey('selection-deposit')), findsNothing);
    expect(find.byKey(const ValueKey('selection-mark-cleared')),
        findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('selection-bounce')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('pdc-customer-charge')), findsNothing);
    expect(find.byKey(const ValueKey('pdc-bank-charges')), findsOneWidget);
  });

  testWidgets('without the create permission there is no way to write',
      (tester) async {
    final _Api api = _Api(rows: <Json>[_cheque('h-1', '000123', 'HELD')]);
    await _pump(
      tester,
      api,
      permissions: _permissions(perms: const ['RECEIPT_VIEW']),
    );
    expect(find.byKey(const ValueKey('toolbar-new')), findsNothing);
    await _select(tester, '000123');
    expect(find.byKey(const ValueKey('selection-deposit')), findsNothing);
  });

  testWidgets('a user with no view permission sees nothing', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, permissions: _permissions(perms: const []));
    expect(find.text('You cannot see post-dated cheques'), findsOneWidget);
    expect(api.requested, isEmpty);
  });

  testWidgets('the page and its bounce dialog fit the 800x600 window',
      (tester) async {
    final _Api api =
        _Api(rows: <Json>[_cheque('d-1', '000124', 'DEPOSITED', due: true)]);
    await _pump(tester, api);
    tester.view.physicalSize = const Size(800, 600);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull, reason: 'the page');
    await _select(tester, '000124');
    expect(tester.takeException(), isNull, reason: 'the selection bar');
    await tester.tap(find.byKey(const ValueKey('selection-bounce')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('pdc-customer-charge')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
