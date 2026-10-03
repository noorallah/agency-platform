// Early-payment discount and interest on overdue bills (SEL-14).
//
// The customer's own terms must reach the server as typed (blank as null),
// a receipt must offer the discount without taking it until Apply is pressed,
// and the statement must raise the interest debit note with exactly the body
// the server declares.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/settlement.dart';
import 'package:agency_desktop/models/settlement_direction.dart';
import 'package:agency_desktop/ui/customers/credit_settings_dialog.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/customers/customer_statement_page.dart';
import 'package:agency_desktop/ui/finance/record_settlement_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

PermissionService _permissions(List<String> perms) {
  final String payload = base64Url.encode(utf8.encode(jsonEncode({
    'roles': <String>['user'],
    'permissions': perms,
  }))).replaceAll('=', '');
  return PermissionService()..applyAccessToken('h.$payload.s');
}

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? recorded;
  Json? raised;
  String? raiseRefusal;
  CreditControlSettings? savedPolicy;
  final List<Map<String, String>> offerQueries = [];

  @override
  Future<List<PartyOption>> settlementParties({
    required SettlementDirection direction,
    String search = '',
  }) async =>
      const [PartyOption(id: 'c-1', code: 'C1', name: 'Kumar Stores')];

  @override
  Future<List<OutstandingInvoice>> outstandingInvoices({
    required SettlementDirection direction,
    required String partyId,
  }) async =>
      [
        OutstandingInvoice.fromJson({
          'invoice_id': 'inv-1',
          'invoice_number': 'SI-1',
          'invoice_date': '2026-04-10',
          'invoice_total': '1000.00',
          'allocated_amount': '0.00',
          'outstanding_amount': '1000.00',
        }),
      ];

  @override
  Future<List<Json>> cashDiscountOffers({
    required String customerId,
    required String on,
  }) async {
    offerQueries.add({'customer_id': customerId, 'on': on});
    return [
      {
        'invoice_id': 'inv-1',
        'invoice_number': 'SI-1',
        'invoice_date': '2026-04-10',
        'outstanding': '1000.00',
        'percent': '2.00',
        'discount_until': '2026-04-30',
        'amount': '20.00',
      },
    ];
  }

  @override
  Future<Settlement> recordSettlement({
    required SettlementDirection direction,
    required Json data,
  }) async {
    recorded = data;
    return Settlement.fromJson({
      'id': 'st-1',
      'direction': 'RECEIPT',
      'party_id': 'c-1',
      'party_code': 'C1',
      'party_name': 'Kumar Stores',
      'settlement_number': 'RC-1',
      'settlement_date': '2026-04-20',
      'amount': '980.00',
      'allocated_amount': '980.00',
      'unallocated_amount': '0.00',
      'method': 'BANK',
      'ledger_account_name': 'Bank',
    });
  }

  @override
  Future<CreditControlSettings> creditControlSettings() async =>
      const CreditControlSettings(
        enforcement: 'WARN',
        warnAtPercent: '80.00',
        blockAtPercent: '100.00',
        isConfigured: true,
      );

  @override
  Future<CreditControlSettings> updateCreditControlSettings(
    CreditControlSettings settings,
  ) async {
    savedPolicy = settings;
    return settings;
  }

  @override
  Future<Json> raiseOverdueInterestDebitNote(
    String customerId, {
    required String invoiceId,
    required String asOf,
  }) async {
    if (raiseRefusal != null) {
      throw ApiException(raiseRefusal!, statusCode: 400);
    }
    raised = {'customer': customerId, 'invoice_id': invoiceId, 'as_of': asOf};
    return {'id': 'dn-1', 'debit_note_number': 'CDN-7'};
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
    if (path.endsWith('/statement')) {
      return {
        'data': {
          'customer_id': 'cust-1',
          'customer_name': 'Kumar Stores',
          'opening_balance': '0.00',
          'closing_balance': '1000.00',
          'unapplied_advance': '0.00',
          'lines': <Json>[],
          'interest_accrued': '12.50',
          'overdue_interest': [
            {
              'invoice_id': 'inv-1',
              'invoice_number': 'SI-1',
              'due_date': '2026-03-31',
              'outstanding': '1000.00',
              'days': 15,
              'rate': '18.00',
              'interest': '12.50',
            },
          ],
        },
      };
    }
    return {
      'data': [
        {
          'customer_id': 'cust-1',
          'customer_code': 'C1',
          'customer_name': 'Kumar Stores',
          'as_of': '2026-04-30',
          'total_outstanding': '1000.00',
          'account_balance': '1000.00',
          'unapplied_credits': '0.00',
          'charges_not_billed': '0.00',
          'buckets': <Json>[],
          'invoices': <Json>[],
        },
      ],
    };
  }
}

void _bigScreen(WidgetTester tester) {
  tester.view.physicalSize = const Size(1400, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

String _boxText(WidgetTester tester, String key) => tester
    .widget<TextField>(find.byKey(ValueKey(key)))
    .controller!
    .text;

void main() {
  testWidgets('the customer editor sends the cash discount terms',
      (tester) async {
    tester.view.physicalSize = const Size(1700, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    Json? saved;
    final Json stored = {
      'id': 'cust-1',
      'code': 'C001',
      'name': 'Zone Unit',
      'display_name': 'Zone Unit',
      'customer_type': 'BUSINESS',
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'credit_limit': '0',
      'default_discount_percent': '0',
      'addresses': const <Json>[],
      'contacts': const <Json>[],
    };
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: CustomerWorkspaceDialog(
          mode: CustomerDialogMode.edit,
          customer: Customer.fromJson(stored),
          loadPlaces: (level, {parentId = ''}) async => const [],
          onSave: (payload) async {
            saved = payload;
            return Customer.fromJson(stored);
          },
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Financial'));
    await tester.pumpAndSettle();
    expect(find.text("Blank: the firm's terms; 0 days: none"), findsOneWidget);
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Cash discount (days)'), '10');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Cash discount %'), '2');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(saved!['cash_discount_days'], 10);
    expect(saved!['cash_discount_percent'], '2');
  });

  testWidgets('the credit policy saves the discount and interest terms',
      (tester) async {
    _bigScreen(tester);
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: CreditSettingsDialog(
          api: api,
          permissions:
              _permissions(['CUSTOMER_VIEW', 'CUSTOMER_MANAGE_SETTINGS']),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('credit-cash-days')), '15');
    await tester.enterText(
        find.byKey(const ValueKey('credit-cash-percent')), '1.5');
    await tester.enterText(
        find.byKey(const ValueKey('credit-interest-rate')), '18');
    await tester.enterText(
        find.byKey(const ValueKey('credit-interest-grace')), '7');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.savedPolicy!.cashDiscountDays, 15);
    expect(api.savedPolicy!.cashDiscountPercent, '1.5');
    expect(api.savedPolicy!.overdueInterestRate, '18');
    expect(api.savedPolicy!.interestGraceDays, 7);
  });

  testWidgets('a receipt offers the discount and fills it only on Apply',
      (tester) async {
    _bigScreen(tester);
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: RecordSettlementDialog(
          api: api,
          direction: SettlementDirection.receipt,
          parties: const [
            PartyOption(id: 'c-1', code: 'C1', name: 'Kumar Stores'),
          ],
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(TextFormField).first);
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Kumar Stores').last);
    await tester.pumpAndSettle();
    expect(api.offerQueries.single['customer_id'], 'c-1');

    await tester.enterText(find.widgetWithText(TextField, 'Amount'), '1000');
    await tester.pumpAndSettle();
    // Not applied to a bill yet, so nothing is offered.
    expect(find.textContaining('Cash discount available'), findsNothing);
    await tester.tap(find.text('Oldest first'));
    await tester.pumpAndSettle();

    expect(
      find.textContaining('Cash discount available: ₹20.00 (2% until 30 Apr)'),
      findsOneWidget,
    );
    expect(_boxText(tester, 'settlement-discount-amount'), isEmpty);

    await tester
        .tap(find.byKey(const ValueKey('settlement-cash-discount-apply')));
    await tester.pumpAndSettle();
    expect(_boxText(tester, 'settlement-discount-amount'), '20.00');
    await tester.tap(find.text('Record receipt'));
    await tester.pumpAndSettle();
    expect(api.recorded?['discount_amount'], '20.00');
  });

  group('statement interest', () {
    Future<void> open(
      WidgetTester tester,
      _Api api,
      List<String> perms,
    ) async {
      _bigScreen(tester);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: CustomerStatementPage(
            api: api,
            permissions: _permissions(perms),
            hasActiveFirm: true,
          ),
        ),
      ));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('Kumar Stores'));
      await tester.pumpAndSettle();
    }

    testWidgets('lists the rows and posts the exact body', (tester) async {
      final _Api api = _Api();
      await open(tester, api, ['CUSTOMER_VIEW', 'CUSTOMER_DEBIT_NOTE_MANAGE']);

      expect(find.textContaining('Interest on overdue bills: 12.50'),
          findsOneWidget);
      expect(find.textContaining('SI-1  due 2026-03-31'), findsOneWidget);
      await tester.tap(find.text('Raise interest debit note'));
      await tester.pumpAndSettle();

      expect(api.raised!['invoice_id'], 'inv-1');
      expect(api.raised!['as_of'], isNotEmpty);
      expect(find.textContaining('CDN-7'), findsOneWidget);
    });

    testWidgets('a refusal shows the server message', (tester) async {
      final _Api api = _Api()..raiseRefusal = 'Already raised for this bill.';
      await open(tester, api, ['CUSTOMER_VIEW', 'CUSTOMER_DEBIT_NOTE_MANAGE']);
      await tester.tap(find.text('Raise interest debit note'));
      await tester.pumpAndSettle();

      expect(find.textContaining('Already raised for this bill.'),
          findsOneWidget);
    });

    testWidgets('no debit note permission, no button', (tester) async {
      await open(tester, _Api(), ['CUSTOMER_VIEW']);

      expect(find.textContaining('Interest on overdue bills'), findsOneWidget);
      expect(find.text('Raise interest debit note'), findsNothing);
    });
  });
}
