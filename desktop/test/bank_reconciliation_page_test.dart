// Bank reconciliation (ACC-1): the screen loads a bank account's statement
// lines and uncleared book entries side by side, offers Match only when the
// chosen entries add up to the line, sends only the keys the server declares,
// says what the auto-matcher did, and shows the reconciliation statement.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/finance/bank_reconciliation_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({
  List<String> perms = const ['LEDGER_VIEW', 'JOURNAL_POST'],
}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

Json _line() => <String, dynamic>{
      'id': 'line-1',
      'statement_id': 'st-1',
      'line_number': 1,
      'line_date': '2026-09-03',
      'description': 'NEFT from Sharma Traders',
      'reference': 'UTR778',
      'withdrawal': '0.00',
      'deposit': '1500.00',
      'balance': '11500.00',
      'status': 'UNMATCHED',
      'matches': <Json>[],
    };

Json _entry(String id, String reference, String amount) => <String, dynamic>{
      'gl_posting_id': id,
      'journal_entry_id': 'je-$id',
      'journal_date': '2026-09-02',
      'reference_number': reference,
      'instrument_reference': null,
      'description': 'Receipt $reference',
      'source_module': 'RECEIPT',
      'amount': amount,
    };

Json _brs() => <String, dynamic>{
      'ledger_account_id': 'acc-bank',
      'ledger_account_code': '1010',
      'ledger_account_name': 'HDFC Current',
      'as_on': '2026-09-30',
      'reconciled_from': '2026-09-01',
      'book_balance': '12000.00',
      'deposits_not_cleared': <Json>[
        <String, dynamic>{
          'on': '2026-09-29',
          'reference': 'CHQ 5521',
          'description': 'Cheque deposited',
          'amount': '2000.00',
        },
      ],
      'deposits_not_cleared_total': '2000.00',
      'payments_not_presented': <Json>[],
      'payments_not_presented_total': '0.00',
      'bank_only': <Json>[],
      'bank_only_net': '0.00',
      'bank_balance_per_books': '10000.00',
      'statement_balance': '10250.00',
      'difference': '250.00',
    };

class _ReconApi extends ApiClient {
  _ReconApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<String> requested = <String>[];
  Json? matchBody;
  Json? autoBody;

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
    Json paged(List<Json> rows) => <String, dynamic>{
          'data': rows,
          'pagination': <String, dynamic>{'total_records': rows.length},
        };
    switch ('$method $path') {
      case 'GET /api/v1/bank-reconciliation/accounts':
        return <String, dynamic>{
          'data': <Json>[
            <String, dynamic>{
              'id': 'acc-bank',
              'code': '1010',
              'name': 'HDFC Current',
              'unmatched_lines': 1,
              'last_statement_date': '2026-09-30',
            },
          ],
        };
      case 'GET /api/v1/bank-reconciliation/statements':
        return paged(<Json>[
          <String, dynamic>{
            'id': 'st-1',
            'ledger_account_id': 'acc-bank',
            'ledger_account_code': '1010',
            'ledger_account_name': 'HDFC Current',
            'name': 'September',
            'from_date': '2026-09-01',
            'to_date': '2026-09-30',
            'line_count': 1,
            'matched_count': 0,
            'created_at': '2026-10-01T00:00:00Z',
            'version': 1,
          },
        ]);
      case 'GET /api/v1/bank-reconciliation/lines':
        return paged(<Json>[_line()]);
      case 'GET /api/v1/bank-reconciliation/book-entries':
        return paged(<Json>[
          _entry('gl-a', 'RCT-1', '1000.00'),
          _entry('gl-b', 'RCT-2', '500.00'),
          _entry('gl-c', 'RCT-3', '200.00'),
        ]);
      case 'POST /api/v1/bank-reconciliation/matches':
        matchBody = body;
        return <String, dynamic>{'data': _line()};
      case 'POST /api/v1/bank-reconciliation/auto-match':
        autoBody = body;
        return <String, dynamic>{
          'data': <String, dynamic>{'matched': 3, 'left_unmatched': 2},
        };
      case 'GET /api/v1/bank-reconciliation/statement':
        return <String, dynamic>{'data': _brs()};
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('bank-reconciliation'),
    );

Future<void> _pump(
  WidgetTester tester,
  _ReconApi api, {
  PermissionService? permissions,
  Size size = const Size(1366, 768),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: BankReconciliationPage(
        api: api,
        preferences: _preferences(),
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

FilledButton _matchButton(WidgetTester tester) => tester.widget<FilledButton>(
      find.byKey(const ValueKey('recon-match')),
    );

Future<void> _tapKey(WidgetTester tester, String key) async {
  await tester.tap(find.byKey(ValueKey(key)));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the account, its lines and its uncleared entries load',
      (tester) async {
    final _ReconApi api = _ReconApi();
    await _pump(tester, api);

    expect(find.textContaining('1010 · HDFC Current (1 unmatched)'),
        findsOneWidget);
    expect(find.text('NEFT from Sharma Traders'), findsOneWidget);
    expect(find.text('1500.00'), findsWidgets);
    expect(find.text('RCT-1'), findsOneWidget);
    expect(find.text('RCT-3'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Match is offered only when the entries add up to the line',
      (tester) async {
    final _ReconApi api = _ReconApi();
    await _pump(tester, api);

    await _tapKey(tester, 'recon-line-line-1');
    expect(_matchButton(tester).onPressed, isNull);

    await _tapKey(tester, 'recon-entry-gl-a');
    expect(_matchButton(tester).onPressed, isNull);
    expect(find.textContaining('Entries 1000.00 of line 1500.00'),
        findsOneWidget);

    await _tapKey(tester, 'recon-entry-gl-c');
    expect(_matchButton(tester).onPressed, isNull);

    await _tapKey(tester, 'recon-entry-gl-c');
    await _tapKey(tester, 'recon-entry-gl-b');
    expect(_matchButton(tester).onPressed, isNotNull);

    await _tapKey(tester, 'recon-match');
    expect(api.requested, contains('POST /api/v1/bank-reconciliation/matches'));
    expect(api.matchBody?['statement_line_id'], 'line-1');
    expect(api.matchBody?['gl_posting_ids'], ['gl-a', 'gl-b']);
    expect(
      api.matchBody!.keys.toSet().difference(const {
        'statement_line_id',
        'gl_posting_ids',
      }),
      isEmpty,
    );
  });

  testWidgets('auto-match says how many matched and how many are left',
      (tester) async {
    final _ReconApi api = _ReconApi();
    await _pump(tester, api);

    await tester.tap(find.byKey(const ValueKey('toolbar-command-auto-match')));
    await tester.pumpAndSettle();

    expect(api.autoBody, <String, dynamic>{'ledger_account_id': 'acc-bank'});
    expect(find.text('3 matched; 2 left to match.'), findsOneWidget);
  });

  testWidgets('the reconciliation statement shows totals and the difference',
      (tester) async {
    final _ReconApi api = _ReconApi();
    await _pump(tester, api);

    await tester.tap(find.text('Reconciliation statement'));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('recon-book-balance')), findsOneWidget);
    expect(find.text('12000.00'), findsOneWidget);
    expect(find.text('2000.00'), findsWidgets);
    expect(find.text('10000.00'), findsOneWidget);
    expect(find.text('10250.00'), findsOneWidget);
    expect(find.byKey(const ValueKey('recon-difference')), findsOneWidget);
    expect(find.text('250.00'), findsOneWidget);
    expect(
      api.requested,
      contains('GET /api/v1/bank-reconciliation/statement'),
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('it fits the smallest window', (tester) async {
    await _pump(tester, _ReconApi(), size: const Size(800, 600));
    await _tapKey(tester, 'recon-line-line-1');
    expect(tester.takeException(), isNull);
    await tester.tap(find.text('Reconciliation statement'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('a user with no permission sees nothing', (tester) async {
    final _ReconApi api = _ReconApi();
    await _pump(tester, api, permissions: _permissions(perms: const []));

    expect(find.text('You cannot see bank reconciliation'), findsOneWidget);
    expect(api.requested, isEmpty);
  });
}
