import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/settlement.dart';
import 'package:agency_desktop/models/settlement_direction.dart';
import 'package:agency_desktop/ui/finance/record_settlement_dialog.dart';
import 'package:agency_desktop/ui/finance/settlements_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Row P5: one customer pays another customer's bill.
class _PaidByApi extends ApiClient {
  _PaidByApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// Every request the screen made, by name, in order.
  final List<String> calls = [];
  final List<({String partyId, bool withShops})> billsAsked = [];
  Json? recorded;
  Json? allocated;

  final Map<String, List<OutstandingInvoice>> bills = {
    'c-1': [_bill('i-1', 'SI-1', '300.00', 'c-1')],
    'c-2': [_bill('i-2', 'SI-2', '500.00', 'c-2')],
  };

  /// The page's own list: one receipt holding money on account.
  @override
  Future<PagedResult<Settlement>> settlements({
    required SettlementDirection direction,
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? partyId,
    String? settlementFrom,
    String? settlementTo,
  }) async =>
      PagedResult<Settlement>(
        items: [_row(direction.name.toUpperCase())],
        total: 1,
      );

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
    calls.add('$method $path');
    throw ApiException('not in this test', statusCode: 404);
  }

  @override
  Future<List<PartyOption>> settlementParties({
    required SettlementDirection direction,
    String search = '',
  }) async {
    calls.add('parties');
    return _parties;
  }

  @override
  Future<List<OutstandingInvoice>> outstandingInvoices({
    required SettlementDirection direction,
    required String partyId,
    bool withShops = false,
    bool withBranches = false,
  }) async {
    calls.add('outstanding $partyId');
    billsAsked.add((partyId: partyId, withShops: withShops));
    return bills[partyId] ?? const [];
  }

  @override
  Future<Settlement> recordSettlement({
    required SettlementDirection direction,
    required Json data,
  }) async {
    calls.add('record');
    recorded = data;
    return Settlement.fromJson({
      'id': 'st-1',
      'direction': direction.name.toUpperCase(),
      'party_id': '${data['party_id']}',
    });
  }

  @override
  Future<Settlement> allocateReceipt({
    required String id,
    required String invoiceId,
    required String amount,
    String? paidForCustomerId,
  }) async {
    calls.add('allocate');
    allocated = <String, dynamic>{
      'id': id,
      'invoice_id': invoiceId,
      'amount': amount,
      if (paidForCustomerId != null) 'paid_for_customer_id': paidForCustomerId,
    };
    return _row();
  }
}

const List<PartyOption> _parties = [
  PartyOption(id: 'c-1', code: 'C1', name: 'Kumar Stores'),
  PartyOption(id: 'c-2', code: 'C2', name: 'Rao Traders'),
];

OutstandingInvoice _bill(String id, String number, String owed, String party) =>
    OutstandingInvoice.fromJson({
      'invoice_id': id,
      'invoice_number': number,
      'invoice_date': '2026-10-01',
      'invoice_total': owed,
      'allocated_amount': '0.00',
      'outstanding_amount': owed,
      'party_id': party,
    });

Settlement _row([String direction = 'RECEIPT']) => Settlement.fromJson({
      'id': 'st-1',
      'direction': direction,
      'party_id': 'c-1',
      'party_code': 'C1',
      'party_name': 'Kumar Stores',
      'settlement_number': 'RC-1',
      'settlement_date': '2026-10-02',
      'amount': '500.00',
      'allocated_amount': '0.00',
      'unallocated_amount': '500.00',
      'method': 'BANK',
      'status': 'POSTED',
      'allocations': <Json>[],
    });

Future<void> _open(
  WidgetTester tester,
  _PaidByApi api,
  SettlementDirection direction,
) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: RecordSettlementDialog(
          api: api,
          direction: direction,
          parties: _parties,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.byType(TextFormField).first);
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Rao Traders').last);
  await tester.pumpAndSettle();
}

/// Rao Traders is chosen as the customer; Kumar Stores will pay.
Future<void> _payByKumar(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('settlement-paid-by-change')));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('settlement-payer-c-1')));
  await tester.pumpAndSettle();
}

Future<void> _fill(WidgetTester tester) async {
  await tester.enterText(find.widgetWithText(TextField, 'Amount'), '500');
  await tester.pumpAndSettle();
  await tester.enterText(
    find.descendant(
      of: find.byType(DataTable),
      matching: find.byType(TextField),
    ).last,
    '500',
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('Paid by untouched sends the old payload and no new call',
      (tester) async {
    final _PaidByApi api = _PaidByApi();
    await _open(tester, api, SettlementDirection.receipt);

    expect(find.text('Paid by: Rao Traders'), findsOneWidget);
    await _fill(tester);
    final List<String> before = List.of(api.calls);
    await tester.tap(find.text('Record receipt'));
    await tester.pumpAndSettle();

    expect(api.recorded, isNotNull);
    expect(api.recorded!.containsKey('paid_for_customer_id'), isFalse);
    expect(api.recorded!['party_id'], 'c-2');
    // The save is the only call added, and no question was asked first.
    expect(api.calls.sublist(before.length), ['record']);
    expect(api.calls.where((c) => c == 'parties'), isEmpty);
    expect(api.billsAsked.single.withShops, isTrue);
  });

  testWidgets('another payer: bills stay the customer\'s, confirm, then send',
      (tester) async {
    final _PaidByApi api = _PaidByApi();
    await _open(tester, api, SettlementDirection.receipt);
    await _payByKumar(tester);

    expect(find.text('Paid by: Kumar Stores'), findsOneWidget);
    expect(find.byKey(const ValueKey('settlement-paid-by-note')),
        findsOneWidget);
    // Reloaded for Rao Traders' own bills, without the shops.
    expect(api.billsAsked.last, (partyId: 'c-2', withShops: false));
    expect(find.text('SI-2'), findsOneWidget);
    // The order picker is not offered.
    expect(find.text('Against order (optional)'), findsNothing);

    await _fill(tester);
    await tester.tap(find.text('Record receipt'));
    await tester.pumpAndSettle();

    expect(find.text('Paid by Kumar Stores for Rao Traders?'), findsOneWidget);
    expect(api.recorded, isNull);

    // Cancel sends nothing.
    await tester
        .tap(find.byKey(const ValueKey('settlement-paid-by-cancel')));
    await tester.pumpAndSettle();
    expect(api.recorded, isNull);

    await tester.tap(find.text('Record receipt'));
    await tester.pumpAndSettle();
    await tester
        .tap(find.byKey(const ValueKey('settlement-paid-by-confirm')));
    await tester.pumpAndSettle();

    expect(api.recorded!['party_id'], 'c-1');
    expect(api.recorded!['paid_for_customer_id'], 'c-2');
    expect(api.recorded!.containsKey('sales_order_id'), isFalse);
    expect(api.recorded!['allocations'], [
      {'invoice_id': 'i-2', 'amount': '500'},
    ]);
  });

  testWidgets('going back to the customer sends the old payload',
      (tester) async {
    final _PaidByApi api = _PaidByApi();
    await _open(tester, api, SettlementDirection.receipt);
    await _payByKumar(tester);
    await tester.tap(find.byKey(const ValueKey('settlement-paid-by-clear')));
    await tester.pumpAndSettle();

    expect(find.text('Paid by: Rao Traders'), findsOneWidget);
    expect(api.billsAsked.last, (partyId: 'c-2', withShops: true));
    await _fill(tester);
    await tester.tap(find.text('Record receipt'));
    await tester.pumpAndSettle();

    expect(api.recorded!.containsKey('paid_for_customer_id'), isFalse);
    expect(api.recorded!['party_id'], 'c-2');
  });

  testWidgets('no customer list is requested until the picker is opened',
      (tester) async {
    final _PaidByApi api = _PaidByApi();
    await _open(tester, api, SettlementDirection.receipt);
    final int before = api.calls.length;

    expect(find.byKey(const ValueKey('settlement-payer-search')),
        findsNothing);
    await tester.tap(find.byKey(const ValueKey('settlement-paid-by-change')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('settlement-payer-search')),
        findsOneWidget);
    // The customer being paid for is not offered as "another" customer.
    expect(find.byKey(const ValueKey('settlement-payer-c-2')), findsNothing);
    expect(api.calls.length, before);
    expect(api.calls.where((c) => c == 'parties'), isEmpty);
  });

  testWidgets('a payment never shows Paid by', (tester) async {
    final _PaidByApi api = _PaidByApi();
    await _open(tester, api, SettlementDirection.payment);

    expect(find.byKey(const ValueKey('settlement-paid-by')), findsNothing);
    expect(find.byKey(const ValueKey('settlement-paid-by-change')),
        findsNothing);
  });

  testWidgets('money on account can be set against another customer\'s bill',
      (tester) async {
    final _PaidByApi api = _PaidByApi();
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final String payload = base64Url.encode(utf8.encode(jsonEncode({
      'permissions': ['RECEIPT_VIEW', 'RECEIPT_CREATE'],
    })));
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SettlementsPage(
          api: api,
          preferences: DesktopPreferencesService(
            directory: Directory.systemTemp.createTempSync('paidby'),
          ),
          permissions: PermissionService()..applyAccessToken('h.$payload.s'),
          hasActiveFirm: true,
          direction: SettlementDirection.receipt,
        ),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Apply to an invoice'));
    await tester.pumpAndSettle();
    // Nothing about other customers was read yet.
    expect(api.calls.where((c) => c == 'parties'), isEmpty);
    expect(api.billsAsked.map((a) => a.partyId), ['c-1']);

    await tester.tap(find.byKey(const ValueKey('apply-other-customer')));
    await tester.pumpAndSettle();
    expect(api.calls.where((c) => c == 'parties').length, 1);
    await tester.tap(find.textContaining('Rao Traders').last);
    await tester.pumpAndSettle();
    expect(api.billsAsked.last, (partyId: 'c-2', withShops: false));
    expect(find.byKey(const ValueKey('apply-other-name')), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Apply'));
    await tester.pumpAndSettle();
    expect(find.text('Paid by Kumar Stores for Rao Traders?'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('apply-other-cancel')));
    await tester.pumpAndSettle();
    expect(api.allocated, isNull);

    await tester.tap(find.widgetWithText(FilledButton, 'Apply'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('apply-other-confirm')));
    await tester.pumpAndSettle();

    expect(api.allocated, {
      'id': 'st-1',
      'invoice_id': 'i-2',
      'amount': '500.00',
      'paid_for_customer_id': 'c-2',
    });
  });

  testWidgets('a payment\'s Apply dialog offers no other customer',
      (tester) async {
    final _PaidByApi api = _PaidByApi();
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final String payload = base64Url.encode(utf8.encode(jsonEncode({
      'permissions': ['PAYMENT_VIEW', 'PAYMENT_CREATE'],
    })));
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SettlementsPage(
          api: api,
          preferences: DesktopPreferencesService(
            directory: Directory.systemTemp.createTempSync('paidby'),
          ),
          permissions: PermissionService()..applyAccessToken('h.$payload.s'),
          hasActiveFirm: true,
          direction: SettlementDirection.payment,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Apply to a bill'));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('apply-other-customer')), findsNothing);
  });
}
