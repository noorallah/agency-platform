// Supplier statements: what the firm owes a supplier over a period, and the
// balance confirmation letters drawn for them.
//
// Phase 2 only. The balance is shown as the server states it (positive: the
// firm owes the supplier); a letter is asked for on the statement's end date;
// and the letters for everyone arrive as a zip that is saved, with the
// server's refusal shown when nobody has a balance.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/vendors/supplier_statement_page.dart';
import 'package:agency_desktop/ui/workspace/balance_confirmation.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({
  List<String> perms = const ['VENDOR_VIEW'],
}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

Json _statement() => <String, dynamic>{
      'vendor_id': 'ven-1',
      'vendor_code': 'V1',
      'vendor_name': 'Kumar Wholesale',
      'from_date': '2026-04-01',
      'to_date': '2026-04-30',
      'opening_balance': '2000.00',
      'closing_balance': '2500.00',
      'total_debit': '500.00',
      'total_credit': '1000.00',
      'lines': <Json>[
        <String, dynamic>{
          'transaction_date': '2026-04-10',
          'transaction_type': 'BILL',
          'reference_number': 'PI-1',
          'remarks': null,
          'debit': '0.00',
          'credit': '1000.00',
          'balance': '3000.00',
        },
        <String, dynamic>{
          'transaction_date': '2026-04-20',
          'transaction_type': 'PAYMENT',
          'reference_number': 'PAY-1',
          'remarks': null,
          'debit': '500.00',
          'credit': '0.00',
          'balance': '2500.00',
        },
      ],
    };

class _SupplierApi extends ApiClient {
  _SupplierApi({this.refuseEveryone})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String? refuseEveryone;
  final List<String> requested = <String>[];
  final List<Map<String, String>> queries = <Map<String, String>>[];

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
    queries.add(query ?? const <String, String>{});
    if (path.endsWith('/statement')) {
      return <String, dynamic>{'data': _statement()};
    }
    if (path == '/api/v1/vendors') {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'ven-1',
            'code': 'V1',
            'name': 'Kumar Wholesale',
            'display_name': 'Kumar Wholesale',
          },
        ],
        'pagination': <String, dynamic>{'total_records': 1},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }

  @override
  Future<List<int>> downloadBytes(
    String path, {
    Map<String, String>? query,
    bool retrying = false,
  }) async {
    requested.add(path);
    queries.add(query ?? const <String, String>{});
    if (refuseEveryone != null && path.endsWith('/balance-confirmations')) {
      throw ApiException(refuseEveryone!, statusCode: 422);
    }
    return <int>[1, 2, 3];
  }
}

class _Sink {
  final List<String> shown = <String>[];
  final List<String> saved = <String>[];

  BalanceConfirmationActions get actions => BalanceConfirmationActions(
        openPdfOverride: (name, bytes) async => shown.add(name),
        saveBytesOverride: (name, bytes) async => saved.add(name),
      );
}

Future<void> _pump(
  WidgetTester tester,
  _SupplierApi api,
  _Sink sink, {
  PermissionService? permissions,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: SupplierStatementPage(
        api: api,
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
        letters: sink.actions,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _choose(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('ss-vendor')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Kumar Wholesale').last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the statement shows the balances and the lines', (tester) async {
    final _SupplierApi api = _SupplierApi();
    await _pump(tester, api, _Sink());
    await _choose(tester);

    expect(api.requested, contains('/api/v1/vendors/ven-1/statement'));
    expect(find.text('PI-1'), findsOneWidget);
    expect(find.text('PAY-1'), findsOneWidget);
    expect(find.textContaining('2,500'), findsWidgets);
    expect(find.textContaining('3,000'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a balance confirmation is asked for on the period end',
      (tester) async {
    final _SupplierApi api = _SupplierApi();
    final _Sink sink = _Sink();
    await _pump(tester, api, sink);

    // Nothing chosen: the letter has no subject yet.
    await tester.tap(find.byKey(const ValueKey('toolbar-more')));
    await tester.pumpAndSettle();
    final Finder item = find
        .byKey(const ValueKey('toolbar-command-balance-confirmation-menu'));
    expect(tester.widget<PopupMenuItem<void Function()>>(item).enabled, isFalse);
    await tester.tapAt(const Offset(5, 5));
    await tester.pumpAndSettle();

    await _choose(tester);
    final String to = api.queries
        .firstWhere((q) => q.containsKey('to_date'))['to_date']!;
    await tester.tap(find.byKey(const ValueKey('toolbar-more')));
    await tester.pumpAndSettle();
    await tester.tap(item);
    await tester.pumpAndSettle();

    expect(
      api.requested,
      contains('/api/v1/vendors/ven-1/balance-confirmation'),
    );
    expect(api.queries.last, <String, String>{'as_of': to});
    expect(sink.shown, hasLength(1));
  });

  testWidgets('letters for everyone are saved as a zip', (tester) async {
    final _SupplierApi api = _SupplierApi();
    final _Sink sink = _Sink();
    await _pump(tester, api, sink);

    await tester.tap(find.byKey(const ValueKey('toolbar-more')));
    await tester.pumpAndSettle();
    await tester
        .tap(find.byKey(const ValueKey('toolbar-command-letters-everyone-menu')));
    await tester.pumpAndSettle();

    expect(api.requested, contains('/api/v1/vendors/balance-confirmations'));
    expect(api.queries.last.containsKey('as_of'), isTrue);
    expect(sink.saved.single, endsWith('.zip'));
  });

  testWidgets('a refusal when nobody has a balance is shown, nothing saved',
      (tester) async {
    final _SupplierApi api =
        _SupplierApi(refuseEveryone: 'No supplier has a balance on that day.');
    final _Sink sink = _Sink();
    await _pump(tester, api, sink);

    await tester.tap(find.byKey(const ValueKey('toolbar-more')));
    await tester.pumpAndSettle();
    await tester
        .tap(find.byKey(const ValueKey('toolbar-command-letters-everyone-menu')));
    await tester.pumpAndSettle();

    expect(sink.saved, isEmpty);
    expect(find.textContaining('No supplier has a balance'), findsOneWidget);
  });

  testWidgets('without the permission nothing is read', (tester) async {
    final _SupplierApi api = _SupplierApi();
    await _pump(tester, api, _Sink(), permissions: _permissions(perms: const []));

    expect(find.text('You cannot see this'), findsOneWidget);
    expect(api.requested, isEmpty);
  });
}
