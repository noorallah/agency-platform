// Backlog 36, desktop half: the opening trial balance -- cash, bank, loans
// and taxes carried over from another tool, entered whole on a cutover date.
// Customer balances, supplier bills and stock keep their own opening paths;
// this is for everything else, and whatever the lines leave unbalanced is
// credited or debited to Opening Balance Equity by the server.
//
// These pin: the standing statement loads into the grid; the totals and the
// difference to Opening Balance Equity update live as rows are typed; Save
// sends exactly `{as_of_date, lines: [{account_code, debit_amount,
// credit_amount, description}]}`; and a server refusal is shown verbatim.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/finance/opening_trial_balance_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

PermissionService _permissions(List<String> codes) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode({'permissions': codes})));
  return PermissionService()..applyAccessToken('h.$payload.s');
}

Json _standing({
  String? asOfDate,
  String? reference,
  List<Json> lines = const [],
}) =>
    {
      'as_of_date': asOfDate,
      'journal_entry_id': reference == null ? null : 'je-1',
      'reference_number': reference,
      'lines': lines,
      'total_debit': '5000.00',
      'total_credit': '0.00',
      'equity_difference': '-5000.00',
    };

const List<Json> _accounts = [
  {
    'id': 'a-cash',
    'firm_id': 'firm-1',
    'account_group_id': 'g-1',
    'code': '1001',
    'name': 'Cash',
    'account_type': 'ASSET',
    'is_active': true,
  },
  {
    'id': 'a-bank',
    'firm_id': 'firm-1',
    'account_group_id': 'g-1',
    'code': '1002',
    'name': 'Bank',
    'account_type': 'ASSET',
    'is_active': true,
  },
];

/// One standing opening trial balance, and a recording of what a save sent.
class _Api extends ApiClient {
  _Api({required this.standing, this.refuse})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json standing;
  final String? refuse;
  Json? lastPutBody;

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
    if (path == '/api/v1/finance/opening-trial-balance' && method == 'GET') {
      return {'success': true, 'data': standing};
    }
    if (path == '/api/v1/finance/opening-trial-balance' && method == 'PUT') {
      lastPutBody = body;
      if (refuse != null) throw ApiException(refuse!, statusCode: 422);
      return {
        'success': true,
        'message': 'Opening trial balance saved as OTB-2.',
        'data': _standing(
          asOfDate: body?['as_of_date'] as String?,
          reference: 'OTB-2',
          lines: (body?['lines'] as List? ?? const []).cast<Json>(),
        ),
      };
    }
    if (path == '/api/v1/finance/ledger-accounts') {
      return {'success': true, 'data': _accounts};
    }
    if (path == '/api/v1/finance/control-accounts') {
      return {'success': true, 'data': const <dynamic>[]};
    }
    return {'success': true, 'data': const <dynamic>[]};
  }
}

Future<void> _pump(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: OpeningTrialBalancePage(
        api: api,
        permissions: _permissions(['JOURNAL_VIEW', 'JOURNAL_POST']),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  final Json openingLine = {
    'ledger_account_id': 'a-cash',
    'account_code': '1001',
    'account_name': 'Cash',
    'account_type': 'ASSET',
    'debit_amount': '5000.00',
    'credit_amount': '0.00',
    'description': 'Opening cash',
  };

  testWidgets('loads the standing statement into the grid', (tester) async {
    final _Api api = _Api(
      standing: _standing(
        asOfDate: '2026-04-01',
        reference: 'OTB-1',
        lines: [openingLine],
      ),
    );
    await _pump(tester, api);

    expect(find.text('Standing as OTB-1, as of 2026-04-01.'), findsOneWidget);
    expect(
      tester
          .widget<TextFormField>(
              find.byKey(const ValueKey('opening-trial-balance-date')))
          .initialValue,
      '2026-04-01',
    );
    expect(
      tester
          .widget<TextFormField>(
              find.byKey(const ValueKey('opening-trial-balance-debit-0')))
          .initialValue,
      '5000.00',
    );
    expect(
      tester
          .widget<TextFormField>(
              find.byKey(const ValueKey('opening-trial-balance-note-0')))
          .initialValue,
      'Opening cash',
    );
    expect(
      tester
          .widget<DropdownButtonFormField<String>>(
              find.byKey(const ValueKey('opening-trial-balance-account-0')))
          .initialValue,
      'a-cash',
    );
  });

  testWidgets('totals and the difference to equity update as rows are typed',
      (tester) async {
    final _Api api = _Api(
      standing: _standing(
        asOfDate: '2026-04-01',
        reference: 'OTB-1',
        lines: [openingLine],
      ),
    );
    await _pump(tester, api);

    expect(find.textContaining('Debit 5,000.00'), findsOneWidget);
    expect(find.textContaining('Credit 0.00'), findsOneWidget);
    expect(
      find.textContaining(
          'Difference to Opening Balance Equity: 5,000.00 will be '
          'credited to Opening Balance Equity.'),
      findsOneWidget,
    );

    await tester
        .tap(find.byKey(const ValueKey('opening-trial-balance-add-row')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('opening-trial-balance-credit-1')),
      '5000',
    );
    await tester.pump();

    expect(find.textContaining('Debit 5,000.00'), findsOneWidget);
    expect(find.textContaining('Credit 5,000.00'), findsOneWidget);
    expect(
      find.textContaining(
          'Balanced -- nothing goes to Opening Balance Equity.'),
      findsOneWidget,
    );
  });

  testWidgets(
      'Save sends exactly as_of_date and the four fields on every line',
      (tester) async {
    final _Api api = _Api(
      standing: _standing(
        asOfDate: '2026-04-01',
        reference: 'OTB-1',
        lines: [openingLine],
      ),
    );
    await _pump(tester, api);

    await tester
        .tap(find.byKey(const ValueKey('opening-trial-balance-save')));
    await tester.pumpAndSettle();

    expect(api.lastPutBody, {
      'as_of_date': '2026-04-01',
      'lines': [
        {
          'account_code': '1001',
          'debit_amount': '5000.00',
          'credit_amount': '0.00',
          'description': 'Opening cash',
        },
      ],
    });
    expect(find.textContaining('Opening trial balance saved as OTB-2.'),
        findsOneWidget);
  });

  testWidgets('a server refusal is shown verbatim, naming the row',
      (tester) async {
    final _Api api = _Api(
      standing: _standing(
        asOfDate: '2026-04-01',
        reference: 'OTB-1',
        lines: [openingLine],
      ),
      refuse: 'row 1: 1001 Cash is kept by its own records -- enter customer '
          'balances on the customer, supplier bills on the supplier and '
          'stock as opening stock',
    );
    await _pump(tester, api);

    await tester
        .tap(find.byKey(const ValueKey('opening-trial-balance-save')));
    await tester.pumpAndSettle();

    expect(
      find.textContaining(
          'row 1: 1001 Cash is kept by its own records -- enter customer '
          'balances on the customer, supplier bills on the supplier and '
          'stock as opening stock'),
      findsOneWidget,
    );
  });
}
