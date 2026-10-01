import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/expense.dart';
import 'package:agency_desktop/models/gst_payment.dart';
import 'package:agency_desktop/ui/sales/gst_payment_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Paying the month's GST (backlog 63): the set-off shown head by head, and
/// the challan recorded with what the person typed.

PermissionService _permissions(List<String> codes) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode({'permissions': codes})));
  return PermissionService()..applyAccessToken('h.$payload.s');
}

Json _head(String head, String owed, String cash, {String rcm = '0.00'}) => {
      'head': head,
      'liability': owed,
      'credit_brought_forward': '0.00',
      'credit_available': '0.00',
      'paid_by_credit': '0.00',
      'cash': cash,
      'credit_used': '0.00',
      'carried_forward': '0.00',
      'reverse_charge': rcm,
    };

class _Api extends ApiClient {
  _Api({this.previousSettled = true, this.reverseCharge = '0.00'})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool previousSettled;

  /// CGST owed under reverse charge on purchases (backlog 68 row 8).
  final String reverseCharge;
  Json? recorded;
  final List<String> previews = [];

  @override
  Future<GstPaymentPreview> gstPaymentPreview({
    required String returnPeriod,
    String? paymentDate,
    Map<String, String> openingCredit = const {},
  }) async {
    previews.add(returnPeriod);
    return GstPaymentPreview.fromJson({
      'return_period': returnPeriod,
      'due_date': '2026-09-20',
      'previous_settled': previousSettled,
      'days_late': 0,
      'suggested_interest': '0.00',
      'cash_total': '8000.00',
      'heads': [
        _head('IGST', '18000.00', '8000.00'),
        _head('CGST', '0.00', '0.00', rcm: reverseCharge),
        _head('SGST', '0.00', '0.00'),
        _head('CESS', '0.00', '0.00'),
      ],
      'utilisation': [
        {'credit_head': 'IGST', 'liability_head': 'IGST', 'amount': '10000.00'},
      ],
    });
  }

  @override
  Future<List<GstPaymentRecord>> gstPayments() async => const [];

  @override
  Future<ExpenseAccountChoices> expenseAccountChoices() async =>
      ExpenseAccountChoices.fromJson({
        'expense_accounts': [
          {'id': 'a-6500', 'code': '6500', 'name': 'Office and General'},
        ],
        'paid_from_accounts': [
          {'id': 'a-1010', 'code': '1010', 'name': 'Bank'},
        ],
      });

  @override
  Future<GstPaymentRecord> recordGstPayment(Json data) async {
    recorded = data;
    return GstPaymentRecord.fromJson({
      'id': 'g-1',
      'return_period': data['return_period'],
      'payment_date': data['payment_date'],
      'status': 'POSTED',
      'cash_total': '8000.00',
      'heads': <Object>[],
    });
  }
}

Future<void> _pump(WidgetTester tester, _Api api,
    {List<String> codes = const ['SALES_VIEW', 'JOURNAL_POST']}) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: GstPaymentPage(
        api: api,
        permissions: _permissions(codes),
        hasActiveFirm: true,
        today: DateTime(2026, 9, 10),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('last month is worked out head by head with the cash to pay',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    expect(api.previews.single, '2026-08');
    expect(find.textContaining('Cash to pay: 8000.00'), findsOneWidget);
    expect(find.text('18000.00'), findsOneWidget);
    expect(find.textContaining('IGST credit -> IGST: 10000.00'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('reverse charge on purchases shows as cash, head by head',
      (tester) async {
    final _Api api = _Api(reverseCharge: '360.00');
    await _pump(tester, api);

    expect(find.text('Reverse charge (cash)'), findsOneWidget);
    expect(
        tester
            .widget<Text>(find.byKey(const ValueKey('gst-pay-rcm-CGST')))
            .data,
        '360.00');
    expect(
        tester
            .widget<Text>(find.byKey(const ValueKey('gst-pay-rcm-IGST')))
            .data,
        '0.00');
    expect(tester.takeException(), isNull);
  });

  testWidgets('recording sends the month, the bank and the challan',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await tester.enterText(
        find.byKey(const ValueKey('gst-pay-cpin')), '26080000000001');
    await tester.ensureVisible(find.byKey(const ValueKey('gst-pay-record')));
    await tester.tap(find.byKey(const ValueKey('gst-pay-record')));
    await tester.pumpAndSettle();

    expect(api.recorded?['return_period'], '2026-08');
    expect(api.recorded?['money_account_id'], 'a-1010');
    expect(api.recorded?['challan_cpin'], '26080000000001');
    expect(api.recorded?.containsKey('interest_amount'), isFalse);
    expect(find.textContaining('GST for 2026-08 recorded'), findsOneWidget);
  });

  testWidgets('a first month asks for the opening credit from the portal',
      (tester) async {
    await _pump(tester, _Api(previousSettled: false));
    expect(find.byKey(const ValueKey('gst-pay-opening-igst')), findsOneWidget);
    expect(find.textContaining('electronic credit ledger'), findsOneWidget);
  });

  testWidgets('without JOURNAL_POST the challan cannot be recorded',
      (tester) async {
    await _pump(tester, _Api(), codes: const ['SALES_VIEW']);
    expect(find.byKey(const ValueKey('gst-pay-record')), findsNothing);
  });
}
