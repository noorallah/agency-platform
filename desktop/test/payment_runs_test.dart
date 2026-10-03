// Payment runs (BUY-11): the new-run dialog loads the proposal for its due-by
// date and posts the ticked bills; approve and cancel go to the right paths;
// a bank-file refusal is shown in the server's words.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/settlement.dart';
import 'package:agency_desktop/models/settlement_direction.dart';
import 'package:agency_desktop/ui/finance/payment_runs_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>[
      'PAYMENT_VIEW',
      'PAYMENT_CREATE',
      'PAYMENT_RUN_APPROVE',
    ],
  }));

Json _run(String id, String status) => <String, dynamic>{
      'id': id,
      'run_number': 'PR-0001',
      'payment_date': '2026-10-05',
      'due_by': '2026-10-10',
      'status': status,
      'total': '3000.0000',
      'version': 1,
      'lines': [
        {
          'id': 'l-1',
          'vendor_id': 'v-1',
          'vendor_name': 'Shah Foods',
          'invoice_id': 'i-1',
          'invoice_number': 'PI-1',
          'amount': '3000.0000',
        },
      ],
    };

class _Api extends ApiClient {
  _Api({this.runs = const [], this.bankRefusal})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> runs;
  final String? bankRefusal;
  final List<String> requested = <String>[];
  final List<Map<String, String>?> queries = [];
  Json? created;
  Json? cancelBody;

  @override
  Future<List<PartyOption>> settlementParties({
    required SettlementDirection direction,
    String search = '',
  }) async =>
      const [PartyOption(id: 'v-1', code: 'V1', name: 'Shah Foods')];

  @override
  Future<List<int>> downloadBytes(
    String path, {
    Map<String, String>? query,
    String method = 'GET',
    Json? body,
    bool retrying = false,
  }) async {
    requested.add('$method $path');
    if (bankRefusal != null) throw ApiException(bankRefusal!);
    return utf8.encode('a,b');
  }

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
    if (path.endsWith('/proposal')) {
      queries.add(query);
      return <String, dynamic>{
        'data': [
          for (final String n in ['1', '2'])
            {
              'invoice_id': 'i-$n',
              'invoice_number': 'PI-$n',
              'invoice_date': '2026-09-01',
              'invoice_total': '2000',
              'allocated_amount': '0',
              'outstanding_amount': '2000.0000',
              'party_id': 'v-1',
              'due_date': '2026-10-05',
              'is_opening_bill': false,
            },
        ],
      };
    }
    if (method == 'POST' && path == '/api/v1/payment-runs') {
      created = body;
      return <String, dynamic>{'data': _run('r-new', 'DRAFT')};
    }
    if (path.endsWith('/approve')) {
      return <String, dynamic>{'data': _run('r-1', 'APPROVED')};
    }
    if (path.endsWith('/cancel')) {
      cancelBody = body;
      return <String, dynamic>{'data': _run('r-1', 'CANCELLED')};
    }
    if (method == 'GET' && path == '/api/v1/payment-runs') {
      return <String, dynamic>{'data': runs};
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('payment-runs'),
    );

Future<void> _pump(
  WidgetTester tester,
  _Api api, {
  Future<void> Function(String, List<int>)? save,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: PaymentRunsPage(
        api: api,
        preferences: _preferences(),
        permissions: _permissions(),
        hasActiveFirm: true,
        saveBytesOverride: save,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester) async {
  await tester.tap(find.text('PR-0001').first);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the dialog loads the proposal and posts only ticked bills',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();
    expect(api.requested, contains('GET /api/v1/payment-runs/proposal'));
    expect(api.queries.single!['due_by'], isNotEmpty);
    expect(find.text('Shah Foods'), findsOneWidget);
    expect(find.text('Owes 2000.00'), findsNWidgets(2));

    await tester.tap(find.byKey(const ValueKey('run-bill-i-2')));
    await tester.enterText(
        find.byKey(const ValueKey('run-amount-i-1')), '1500');
    await tester.tap(find.byKey(const ValueKey('run-save')));
    await tester.pumpAndSettle();

    expect(api.created!['lines'], [
      {'invoice_id': 'i-1', 'amount': '1500'},
    ]);
    expect(api.created!.containsKey('payment_date'), isTrue);
  });

  testWidgets('approve and cancel hit their own paths', (tester) async {
    final _Api api = _Api(runs: [_run('r-1', 'DRAFT')]);
    await _pump(tester, api);
    await _select(tester);
    await tester.tap(find.byKey(const ValueKey('selection-approve')));
    await tester.pumpAndSettle();
    expect(api.requested, contains('POST /api/v1/payment-runs/r-1/approve'));

    await tester.tap(find.byKey(const ValueKey('selection-cancel')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Wrong date');
    await tester.tap(find.text('Cancel run'));
    await tester.pumpAndSettle();
    expect(api.requested, contains('POST /api/v1/payment-runs/r-1/cancel'));
    expect(api.cancelBody, {'reason': 'Wrong date'});
  });

  testWidgets('a bank-file refusal is shown; success saves the file',
      (tester) async {
    final _Api refusing = _Api(
      runs: [_run('r-1', 'APPROVED')],
      bankRefusal: 'Shah Foods has no bank account.',
    );
    await _pump(tester, refusing);
    await _select(tester);
    await tester.tap(find.byKey(const ValueKey('selection-bank-file')));
    await tester.pumpAndSettle();
    expect(find.text('Shah Foods has no bank account.'), findsOneWidget);
    expect(refusing.requested,
        contains('GET /api/v1/payment-runs/r-1/bank-file'));

    String? savedName;
    final _Api ok = _Api(runs: [_run('r-1', 'APPROVED')]);
    await _pump(tester, ok, save: (name, bytes) async => savedName = name);
    await _select(tester);
    await tester.tap(find.byKey(const ValueKey('selection-bank-file')));
    await tester.pumpAndSettle();
    expect(savedName, 'Payment run PR-0001.csv');
  });
}
