// A draft commission payout could not be adjusted.
//
// `updateCommissionPayout` had a route, a client method and no control, so a
// payout accrued at the wrong rate could only be cancelled and accrued again
// -- and the service takes an adjustment amount and a reason precisely so it
// need not be.
//
// These pin the control and the three rules the form has to respect: only a
// draft, an adjustment needs a reason, and a payout cannot go negative.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/commission.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/commission/commission_page.dart';
import 'package:agency_desktop/ui/commission/payout_dialogs.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

class _Api extends ApiClient {
  _Api({this.payouts = const <Json>[]})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> payouts;

  Json? sentBody;
  final List<String> calls = <String>[];

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
    if (method != 'GET') {
      calls.add('$method $path');
      sentBody = body;
      return <String, dynamic>{
        'data': payouts.isEmpty ? _payout() : payouts.first,
      };
    }
    if (path.contains('/payouts')) {
      return <String, dynamic>{
        'data': payouts,
        'pagination': <String, dynamic>{'total_records': payouts.length},
      };
    }
    return <String, dynamic>{
      'data': const <Json>[],
      'pagination': <String, dynamic>{'total_records': 0},
    };
  }
}

Json _payout({
  String id = 'po-1',
  String status = 'DRAFT',
  String earned = '1000.00',
  String adjustment = '0.00',
  String reason = '',
}) =>
    <String, dynamic>{
      'id': id,
      'salesman_id': 'u-1',
      'salesman_name': 'Ravi Kumar',
      'period_start': '2026-08-01',
      'period_end': '2026-08-31',
      'basis': 'COLLECTED',
      'measured_amount': '50000.00',
      'earned_amount': earned,
      'adjustment_amount': adjustment,
      'adjustment_reason': reason,
      'payable_amount': earned,
      'status': status,
      'accrued_on': '2026-09-01',
      'paid_on': '',
      'money_account_id': '',
      'journal_entry_id': '',
      'payment_journal_entry_id': '',
      'notes': '',
      'version': 4,
    };

Future<void> _openDialog(WidgetTester tester, _Api api, Json payout) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: CommissionAdjustmentDialog(
        api: api,
        payout: CommissionPayoutRecord.fromJson(payout),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _openPage(
  WidgetTester tester,
  _Api api,
  List<String> codes,
) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: CommissionPage(
        api: api,
        permissions: _permissions(codes),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

const List<String> _manager = <String>[
  'COMMISSION_VIEW',
  'COMMISSION_MANAGE',
];

void main() {
  testWidgets('an adjustment sends the amount, the reason and the version',
      (tester) async {
    final _Api api = _Api();
    await _openDialog(tester, api, _payout());

    await tester.enterText(
        find.widgetWithText(TextField, 'Adjustment'), '-100');
    await tester.enterText(
        find.widgetWithText(TextField, 'Reason'), 'rate corrected');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.calls.single, startsWith('PUT'));
    expect(api.sentBody?['adjustment_amount'], '-100');
    expect(api.sentBody?['adjustment_reason'], 'rate corrected');
  });

  testWidgets('an adjustment with no reason is refused before the round trip',
      (tester) async {
    final _Api api = _Api();
    await _openDialog(tester, api, _payout());

    await tester.enterText(
        find.widgetWithText(TextField, 'Adjustment'), '-100');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    // The server refuses it too, but losing the typing to a round trip is
    // worse than saying so here.
    expect(api.calls, isEmpty);
    expect(find.textContaining('Say why'), findsOneWidget);
  });

  testWidgets('a payout cannot be adjusted below nothing', (tester) async {
    final _Api api = _Api();
    await _openDialog(tester, api, _payout(earned: '500.00'));

    await tester.enterText(
        find.widgetWithText(TextField, 'Adjustment'), '-600');
    await tester.enterText(
        find.widgetWithText(TextField, 'Reason'), 'clawback');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    // A payout cannot take money back; clawing it off other sales is an
    // arrangement nobody asked for.
    expect(api.calls, isEmpty);
    expect(find.textContaining('negative'), findsOneWidget);
  });

  testWidgets('the payable total is shown, not just the correction',
      (tester) async {
    await _openDialog(tester, _Api(), _payout(earned: '1000.00'));

    await tester.enterText(
        find.widgetWithText(TextField, 'Adjustment'), '-250');
    await tester.pumpAndSettle();

    // The interesting number is what the firm ends up owing.
    expect(find.textContaining('750.00'), findsOneWidget);
  });

  // Two tests rather than one, deliberately: a second `pumpWidget` of the
  // same widget type reuses the State, so the first payout list survives and
  // the assertion passes for the wrong reason. That is what happened when
  // this was written as one test.
  testWidgets('a draft offers the control', (tester) async {
    await _openPage(tester, _Api(payouts: <Json>[_payout()]), _manager);
    await tester.tap(find.text('Payouts'));
    await tester.pumpAndSettle();

    expect(find.widgetWithText(TextButton, 'Adjust'), findsOneWidget);
  });

  testWidgets('an approved payout does not', (tester) async {
    // Its accrual journal already states the number, so the service refuses
    // a change and the screen must not offer one.
    await _openPage(
      tester,
      _Api(payouts: <Json>[_payout(status: 'APPROVED')]),
      _manager,
    );
    await tester.tap(find.text('Payouts'));
    await tester.pumpAndSettle();

    expect(find.widgetWithText(TextButton, 'Adjust'), findsNothing);
    // And the row is really there, or this passes on an empty list.
    expect(find.textContaining('Ravi Kumar'), findsWidgets);
  });

  testWidgets('reading payouts is not authority to change one', (tester) async {
    await _openPage(
      tester,
      _Api(payouts: <Json>[_payout()]),
      const <String>['COMMISSION_VIEW'],
    );
    await tester.tap(find.text('Payouts'));
    await tester.pumpAndSettle();

    expect(find.widgetWithText(TextButton, 'Adjust'), findsNothing);
  });
}
