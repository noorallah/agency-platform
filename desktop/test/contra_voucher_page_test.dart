// Contra vouchers: money moved between the firm's own cash and bank accounts.
//
// Phase 2 only. The screen lists the vouchers, posts one from two money
// accounts (sending only the keys the server declares), says so when the
// From account would go below zero without treating it as a refusal, and
// cancels only once a reason is given.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/finance/contra_voucher_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({
  List<String> perms = const [
    'JOURNAL_VIEW',
    'JOURNAL_POST',
    'JOURNAL_REVERSE',
  ],
}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

Json _voucher({String? warning}) => <String, dynamic>{
      'id': 'cv-1',
      'voucher_number': 'CNTR-2026-0001',
      'voucher_date': '2026-09-02',
      'kind': 'DEPOSIT',
      'status': 'POSTED',
      'from_account_id': 'acc-cash',
      'from_account_code': '1000',
      'from_account_name': 'Cash in hand',
      'to_account_id': 'acc-bank',
      'to_account_code': '1010',
      'to_account_name': 'HDFC Current',
      'amount': '5000.00',
      'reference': 'Slip 42',
      'remarks': null,
      'cancel_reason': null,
      'balance_warning': warning,
      'version': 2,
    };

class _ContraApi extends ApiClient {
  _ContraApi({this.rows = const [], this.warning})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;
  final String? warning;
  final List<String> requested = <String>[];
  Json? created;
  Json? cancelBody;
  int? sentVersion;

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
    if (path == '/api/v1/contra-vouchers/money-accounts') {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'acc-cash',
            'code': '1000',
            'name': 'Cash in hand',
            'kind': 'CASH',
          },
          <String, dynamic>{
            'id': 'acc-bank',
            'code': '1010',
            'name': 'HDFC Current',
            'kind': 'BANK',
          },
        ],
      };
    }
    if (method == 'POST' && path == '/api/v1/contra-vouchers') {
      created = body;
      return <String, dynamic>{'data': _voucher(warning: warning)};
    }
    if (path.endsWith('/cancel')) {
      cancelBody = body;
      sentVersion = expectedVersion;
      return <String, dynamic>{'data': _voucher()};
    }
    if (path == '/api/v1/contra-vouchers') {
      return <String, dynamic>{
        'data': rows,
        'pagination': <String, dynamic>{'total_records': rows.length},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('contra-vouchers'),
    );

Future<void> _pump(
  WidgetTester tester,
  _ContraApi api, {
  PermissionService? permissions,
  Size size = const Size(1366, 768),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: ContraVoucherPage(
        api: api,
        preferences: _preferences(),
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _pick(WidgetTester tester, Key menu, String label) async {
  await tester.tap(find.byKey(menu));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining(label).last);
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester) async {
  await tester.tap(find.text('CNTR-2026-0001').first);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

Future<void> _fill(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('toolbar-new')));
  await tester.pumpAndSettle();
  await _pick(tester, const ValueKey('contra-from'), 'Cash in hand');
  await _pick(tester, const ValueKey('contra-to'), 'HDFC Current');
  await tester.enterText(find.byKey(const ValueKey('contra-amount')), '5000');
  await tester.enterText(
      find.byKey(const ValueKey('contra-reference')), 'Slip 42');
}

void main() {
  testWidgets('the list shows the number, the kind, both accounts and amount',
      (tester) async {
    final _ContraApi api = _ContraApi(rows: <Json>[_voucher()]);
    await _pump(tester, api);

    expect(find.text('CNTR-2026-0001'), findsOneWidget);
    expect(find.text('Deposit (cash to bank)'), findsOneWidget);
    expect(find.text('Cash in hand'), findsWidgets);
    expect(find.text('HDFC Current'), findsWidgets);
    expect(find.textContaining('5,000'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('posting sends only the declared keys and hints at the kind',
      (tester) async {
    final _ContraApi api = _ContraApi(rows: <Json>[_voucher()]);
    await _pump(tester, api);
    await _fill(tester);

    expect(find.byKey(const ValueKey('contra-kind-hint')), findsOneWidget);
    expect(find.textContaining('Deposit (cash to bank)'), findsWidgets);
    await tester.tap(find.byKey(const ValueKey('contra-save')));
    await tester.pumpAndSettle();

    expect(api.requested, contains('POST /api/v1/contra-vouchers'));
    expect(api.created?['from_account_id'], 'acc-cash');
    expect(api.created?['to_account_id'], 'acc-bank');
    expect(api.created?['amount'], '5000');
    expect(api.created?['reference'], 'Slip 42');
    expect(
      api.created!.keys.toSet().difference(const {
        'voucher_date',
        'from_account_id',
        'to_account_id',
        'amount',
        'reference',
        'remarks',
      }),
      isEmpty,
    );
    // Empty remarks are left out rather than sent blank.
    expect(api.created!.containsKey('remarks'), isFalse);
  });

  testWidgets('a below-zero warning is shown, and the voucher is still saved',
      (tester) async {
    final _ContraApi api = _ContraApi(
      rows: <Json>[_voucher()],
      warning: 'Cash in hand would be below zero on 2026-09-02.',
    );
    await _pump(tester, api);
    await _fill(tester);
    await tester.tap(find.byKey(const ValueKey('contra-save')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('contra-save')), findsNothing);
    expect(find.textContaining('would be below zero'), findsOneWidget);
  });

  testWidgets('the same account twice is refused before the server',
      (tester) async {
    final _ContraApi api = _ContraApi(rows: <Json>[_voucher()]);
    await _pump(tester, api);
    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();
    await _pick(tester, const ValueKey('contra-from'), 'HDFC Current');
    await _pick(tester, const ValueKey('contra-to'), 'HDFC Current');
    await tester.enterText(find.byKey(const ValueKey('contra-amount')), '10');
    await tester.tap(find.byKey(const ValueKey('contra-save')));
    await tester.pumpAndSettle();

    expect(api.created, isNull);
    expect(find.byKey(const ValueKey('contra-problem')), findsOneWidget);
  });

  testWidgets('cancelling asks why and sends the reason', (tester) async {
    final _ContraApi api = _ContraApi(rows: <Json>[_voucher()]);
    await _pump(tester, api);
    await _select(tester);
    await tester.tap(find.byKey(const ValueKey('selection-cancel')));
    await tester.pumpAndSettle();

    expect(
      api.requested,
      isNot(contains('POST /api/v1/contra-vouchers/cv-1/cancel')),
    );
    await tester.enterText(find.byType(TextField).last, 'Wrong account');
    await tester.tap(find.text('Cancel voucher'));
    await tester.pumpAndSettle();

    expect(api.requested, contains('POST /api/v1/contra-vouchers/cv-1/cancel'));
    expect(api.cancelBody, <String, dynamic>{'reason': 'Wrong account'});
    expect(api.sentVersion, 2);
  });

  testWidgets('a user with no permission sees nothing', (tester) async {
    final _ContraApi api = _ContraApi(rows: <Json>[_voucher()]);
    await _pump(tester, api, permissions: _permissions(perms: const []));

    expect(find.text('You cannot see contra vouchers'), findsOneWidget);
    expect(api.requested, isEmpty);
  });
}
