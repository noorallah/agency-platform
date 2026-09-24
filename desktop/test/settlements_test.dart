import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/settlement.dart';
import 'package:agency_desktop/models/settlement_direction.dart';
import 'package:agency_desktop/ui/finance/record_settlement_dialog.dart';
import 'package:agency_desktop/ui/finance/settlements_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Receipts and payments.
///
/// Nothing in the product could record money arriving: two years of seeded
/// trading left Cash at 0.00 while receivables grew to 249,236.70, because
/// invoices were the only document that reached the ledger.
PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

class _SettlementApi extends ApiClient {
  _SettlementApi({this.rows = const [], this.outstanding = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Settlement> rows;
  final List<OutstandingInvoice> outstanding;
  Json? recorded;
  String? reversedId;
  String? reversedReason;
  Json? allocated;

  @override
  Future<PagedResult<Settlement>> settlements({
    required SettlementDirection direction,
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? partyId,
  }) async =>
      PagedResult<Settlement>(items: rows, total: rows.length);

  /// What the party picker asked for, and what it was told.
  ///
  /// Overriding `settlementParties` rather than `customers` is the whole
  /// point: the money screens have their own list now, gated on the
  /// settlement permissions. A fake that still answered `customers` would go
  /// green while a cashier was refused on the real thing.
  final List<SettlementDirection> partiesAskedFor = [];
  List<PartyOption> parties = const [
    PartyOption(id: 'c-1', code: 'C1', name: 'Kumar Stores'),
  ];

  @override
  Future<List<PartyOption>> settlementParties({
    required SettlementDirection direction,
    String search = '',
  }) async {
    partiesAskedFor.add(direction);
    return parties;
  }

  @override
  Future<List<OutstandingInvoice>> outstandingInvoices({
    required SettlementDirection direction,
    required String partyId,
  }) async =>
      outstanding;

  /// Every TCS preview asked for, so a test can see when the notice reloads.
  final List<({String customerId, String amount})> tcsAsked = [];

  @override
  Future<Json> tcsPreview({
    required String customerId,
    required String amount,
    required String on,
  }) async {
    tcsAsked.add((customerId: customerId, amount: amount));
    return <String, dynamic>{
      'applicable': true,
      'tcs_amount': '3.42',
      'taxable_amount': amount,
      'rate_percent': '1.000',
    };
  }

  @override
  Future<Settlement> reverseSettlement({
    required SettlementDirection direction,
    required String id,
    String? reason,
  }) async {
    reversedId = id;
    reversedReason = reason;
    return rows.first;
  }

  @override
  Future<Settlement> recordSettlement({
    required SettlementDirection direction,
    required Json data,
  }) async {
    recorded = data;
    return rows.first;
  }

  /// What `/payments/supplier-credits` answers, and what was applied.
  List<SupplierCredit> credits = const [];
  Json? appliedCredit;

  @override
  Future<List<SupplierCredit>> supplierCredits(String vendorId) async =>
      credits;

  @override
  Future<SupplierCredit> applySupplierCredit({
    required String returnId,
    required String invoiceId,
    required String amount,
  }) async {
    appliedCredit = <String, dynamic>{
      'return_id': returnId,
      'invoice_id': invoiceId,
      'amount': amount,
    };
    return credits.first;
  }

  @override
  Future<Settlement> allocateReceipt({
    required String id,
    required String invoiceId,
    required String amount,
  }) async {
    allocated = <String, dynamic>{
      'id': id,
      'invoice_id': invoiceId,
      'amount': amount,
    };
    return rows.first;
  }

  @override
  Future<Settlement> allocatePayment({
    required String id,
    required String invoiceId,
    required String amount,
  }) async {
    allocated = <String, dynamic>{
      'id': id,
      'invoice_id': invoiceId,
      'amount': amount,
      'direction': 'PAYMENT',
    };
    return rows.first;
  }
}

OutstandingInvoice _invoice(String id, String number, String outstanding) =>
    OutstandingInvoice.fromJson({
      'invoice_id': id,
      'invoice_number': number,
      'invoice_date': '2024-05-22',
      'invoice_total': outstanding,
      'allocated_amount': '0.00',
      'outstanding_amount': outstanding,
    });

Settlement _settlement({
  String number = 'RC-2026-2027-000001',
  String amount = '8429.63',
  String unallocated = '0.00',
  String status = 'POSTED',
  String salesOrderNumber = '',
  String direction = 'RECEIPT',
  List<Json> allocations = const [],
}) =>
    Settlement.fromJson({
      'id': 'st-1',
      'direction': direction,
      'party_id': 'c-1',
      'party_code': 'WHOLE01C03',
      'party_name': 'Third Customer',
      'settlement_number': number,
      'settlement_date': '2027-03-15',
      'sales_order_number': salesOrderNumber,
      'amount': amount,
      'allocated_amount': '8429.63',
      'unallocated_amount': unallocated,
      'method': 'BANK',
      'ledger_account_name': 'Bank',
      'instrument_reference': 'NEFT-9931',
      'narration': '',
      'status': status,
      'journal_entry_id': 'je-1',
      'reversal_reason': status == 'REVERSED' ? 'Keyed twice' : '',
      'allocations': allocations,
    });

/// Choose a party in the record dialog, by name.
///
/// The picker is a `RawAutocomplete` rather than a dropdown as of
/// 2026-09-15 -- a distributor with hundreds of customers was being handed a
/// scrollbar at the till. Tapping the field opens the whole list; each option
/// reads `CODE  Name` on one line, so match on a fragment.
Future<void> _chooseParty(WidgetTester tester, String name) async {
  await tester.tap(find.byType(TextFormField).first);
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining(name).last);
  await tester.pumpAndSettle();
}

Future<void> _pump(
  WidgetTester tester,
  _SettlementApi api, {
  SettlementDirection direction = SettlementDirection.receipt,
  List<String> perms = const ['RECEIPT_VIEW', 'RECEIPT_CREATE'],
}) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: SettlementsPage(
          api: api,
          permissions: _permissionsFor(perms),
          hasActiveFirm: true,
          direction: direction,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('spreading money over invoices', () {
    test('oldest first, and it stops when the money runs out', () {
      // What a cashier does by hand with a stack of invoices and a cheque.
      final Map<String, String> spread = allocateOldestFirst(
        [
          _invoice('a', 'SI-1', '100.00'),
          _invoice('b', 'SI-2', '100.00'),
          _invoice('c', 'SI-3', '100.00'),
        ],
        '150.00',
      );

      expect(spread, {'a': '100.00', 'b': '50.00'});
      expect(spread.containsKey('c'), isFalse);
    });

    test('more money than invoices leaves the rest unspread', () {
      // Not an error: a customer may pay more than they currently owe, and
      // the remainder is held on account.
      final Map<String, String> spread =
          allocateOldestFirst([_invoice('a', 'SI-1', '100.00')], '250.00');

      expect(spread, {'a': '100.00'});
    });
  });

  group('what is refused before the server sees it', () {
    test('applying more to an invoice than it owes', () {
      expect(
        validateSettlement(
          partyId: 'c-1',
          amount: '500.00',
          allocations: {'a': '400.00'},
          invoices: [_invoice('a', 'SI-1', '100.00')],
        ),
        contains('SI-1 owes 100.00'),
      );
    });

    test('applying more than arrived', () {
      expect(
        validateSettlement(
          partyId: 'c-1',
          amount: '50.00',
          allocations: {'a': '100.00'},
          invoices: [_invoice('a', 'SI-1', '100.00')],
        ),
        contains('more than the 50.00 that moved'),
      );
    });

    test('an amount of nothing', () {
      expect(
        validateSettlement(
          partyId: 'c-1',
          amount: '',
          allocations: const {},
          invoices: const [],
        ),
        contains('how much money moved'),
      );
    });

    test('rounding to the paisa does not fail a full settlement', () {
      // The seeded invoices carry four decimals; money moves in two.
      expect(
        validateSettlement(
          partyId: 'c-1',
          amount: '8429.63',
          allocations: {'a': '8429.63'},
          invoices: [_invoice('a', 'SI-1', '8429.63')],
        ),
        isNull,
      );
    });

    test('applying nothing at all is allowed', () {
      // Money can arrive before an invoice does. It still reaches the ledger.
      expect(
        validateSettlement(
          partyId: 'c-1',
          amount: '500.00',
          allocations: const {},
          invoices: const [],
        ),
        isNull,
      );
    });
  });

  group('the receipts list', () {
    testWidgets('a receipt says which invoice it cleared', (tester) async {
      final _SettlementApi api = _SettlementApi(rows: [
        _settlement(allocations: [
          {
            'id': 'al-1',
            'invoice_id': 'i-1',
            'invoice_number': 'SI-2024-2025-000004',
            'invoice_date': '2024-05-22',
            'invoice_total': '8429.63',
            'amount': '8429.63',
          },
        ]),
      ]);
      await _pump(tester, api);

      expect(find.textContaining('Cleared SI-2024-2025-000004'), findsOneWidget);
      expect(find.text('Applied'), findsOneWidget);
      expect(find.textContaining('BANK into Bank'), findsOneWidget);
    });

    testWidgets('money not applied to anything is flagged', (tester) async {
      // It reached the ledger and reduced the balance, but no document says
      // what it was for, and somebody has to apply it eventually.
      final _SettlementApi api =
          _SettlementApi(rows: [_settlement(unallocated: '5000.00')]);
      await _pump(tester, api);

      expect(find.text('On account 5000.00'), findsOneWidget);
      expect(find.textContaining('Not applied to any invoice'), findsOneWidget);
    });

    testWidgets('without RECEIPT_CREATE the button is not offered',
        (tester) async {
      final _SettlementApi api = _SettlementApi(rows: [_settlement()]);
      await _pump(tester, api, perms: const ['RECEIPT_VIEW']);

      expect(find.widgetWithText(FilledButton, 'Record Receipt'), findsNothing);
    });

    testWidgets('without RECEIPT_VIEW there is nothing to show', (tester) async {
      await _pump(tester, _SettlementApi(), perms: const ['PAYMENT_VIEW']);
      expect(find.textContaining('do not have permission'), findsOneWidget);
    });

    testWidgets('choosing a customer shows what they owe', (tester) async {
      // The dialog is where the allocation happens, so it has to show the
      // invoices before anybody can apply money to them.
      final _SettlementApi api = _SettlementApi(
        rows: [_settlement()],
        outstanding: [
          _invoice('i-1', 'SI-2024-2025-000004', '8429.63'),
          _invoice('i-2', 'SI-2024-2025-000005', '8429.63'),
        ],
      );
      tester.view.physicalSize = const Size(1400, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: RecordSettlementDialog(
              api: api,
              direction: SettlementDirection.receipt,
              parties: const [
                PartyOption(id: 'c-1', code: 'WHOLE01C03', name: 'Third Customer'),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('Choose a customer to see what they owe'),
          findsOneWidget);

      await _chooseParty(tester, 'Third Customer');

      expect(find.text('SI-2024-2025-000004'), findsOneWidget);
      expect(find.text('SI-2024-2025-000005'), findsOneWidget);
      // With no amount entered there is nothing to say about applying it.
      // "All of it applied" over an empty amount box reads as a tick against
      // a form nobody has filled in.
      expect(find.text('Enter the amount to apply it'), findsOneWidget);
    });

    testWidgets('the TCS notice appears when the customer is chosen last',
        (tester) async {
      // It was read only when the amount changed; choosing the customer
      // afterwards cleared it and nothing brought it back (plan item 9.19).
      final _SettlementApi api = _SettlementApi(rows: [_settlement()]);
      tester.view.physicalSize = const Size(1400, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: RecordSettlementDialog(
              api: api,
              direction: SettlementDirection.receipt,
              parties: const [
                PartyOption(id: 'c-1', code: 'WHOLE01C01', name: 'Vijaya'),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.enterText(
        find.ancestor(of: find.text('Amount'), matching: find.byType(TextField)),
        '341.61',
      );
      await tester.pumpAndSettle();
      await _chooseParty(tester, 'Vijaya');

      expect(api.tcsAsked.last, (customerId: 'c-1', amount: '341.61'));
      expect(find.textContaining('Tax collected at source: 3.42'), findsOneWidget);
    });

    testWidgets('a reversed receipt still names what it had cleared',
        (tester) async {
      // The first thing anybody asks about a correction is what it had been
      // applied to, so the reversed row keeps saying so.
      final _SettlementApi api = _SettlementApi(rows: [
        _settlement(status: 'REVERSED', allocations: [
          {
            'id': 'al-1',
            'invoice_id': 'i-1',
            'invoice_number': 'SI-2024-2025-000004',
            'invoice_date': '2024-05-22',
            'invoice_total': '8429.63',
            'amount': '8429.63',
          },
        ]),
      ]);
      await _pump(tester, api);

      expect(find.text('Reversed'), findsOneWidget);
      expect(find.textContaining('Had cleared SI-2024-2025-000004'), findsOneWidget);
      expect(find.byTooltip('Reverse'), findsNothing,
          reason: 'it cannot be reversed twice');
    });

    testWidgets('reversing asks why, and sends it', (tester) async {
      final _SettlementApi api = _SettlementApi(rows: [_settlement()]);
      await _pump(tester, api);

      await tester.tap(find.byTooltip('Reverse'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Nothing is deleted'), findsOneWidget);

      await tester.enterText(
        find.widgetWithText(TextField, 'Why is it being reversed?'),
        'Keyed against the wrong customer',
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Reverse'));
      await tester.pumpAndSettle();

      expect(api.reversedId, 'st-1');
      expect(api.reversedReason, 'Keyed against the wrong customer');
    });

    testWidgets('a refund applies to nothing, and says why', (tester) async {
      // A refund returns money held on account, which is the opposite of
      // settling a document. Offering an invoice table would invite somebody
      // to do the thing the server refuses.
      final _SettlementApi api = _SettlementApi(
        rows: const [],
        outstanding: [_invoice('i-1', 'SI-1', '100.00')],
      );
      tester.view.physicalSize = const Size(1400, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: RecordSettlementDialog(
              api: api,
              direction: SettlementDirection.refund,
              parties: const [
                PartyOption(id: 'c-1', code: 'WHOLE01C03', name: 'Third Customer'),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Record a refund'), findsOneWidget);
      expect(find.text('Refunded to'), findsOneWidget);
      expect(find.textContaining('not applied to an invoice'), findsOneWidget);
      expect(find.text('Apply to invoices'), findsNothing);
    });

    testWidgets('a refund reads the money-out permissions', (tester) async {
      // The person trusted to collect is not automatically the person trusted
      // to hand money back, and the server enforces the same split.
      final _SettlementApi api = _SettlementApi(rows: [_settlement()]);
      await _pump(
        tester,
        api,
        direction: SettlementDirection.refund,
        perms: const ['RECEIPT_VIEW', 'RECEIPT_CREATE'],
      );
      expect(find.textContaining('do not have permission'), findsOneWidget);

      await _pump(
        tester,
        api,
        direction: SettlementDirection.refund,
        perms: const ['PAYMENT_VIEW', 'PAYMENT_CREATE'],
      );
      expect(find.widgetWithText(FilledButton, 'Record Refund'), findsOneWidget);
    });

    testWidgets('the payments tab says payment everywhere it says receipt',
        (tester) async {
      final _SettlementApi api = _SettlementApi();
      await _pump(
        tester,
        api,
        direction: SettlementDirection.payment,
        perms: const ['PAYMENT_VIEW', 'PAYMENT_CREATE'],
      );

      expect(find.widgetWithText(FilledButton, 'Record Payment'), findsOneWidget);
      expect(find.textContaining('No payments yet'), findsOneWidget);
      expect(find.textContaining('owes the vendor'), findsOneWidget);
    });
  });

  group('supplier credit from returns (D-FIN-19)', () {
    SupplierCredit credit() => SupplierCredit.fromJson({
          'purchase_return_id': 'pr-1',
          'return_number': 'PR-2026-2027-000009',
          'return_date': '2026-09-19',
          'credit_amount': '236.00',
          'applied_amount': '0.00',
          'available_amount': '236.00',
          'applied_to': <String>[],
        });

    _SettlementApi vendorApi({List<Settlement> rows = const []}) =>
        _SettlementApi(
          rows: rows,
          outstanding: [_invoice('pi-1', 'PI-2026-2027-000012', '708.00')],
        )
          ..parties = const [
            PartyOption(id: 'v-1', code: 'V1', name: 'Fixture Supplier'),
          ]
          ..credits = [credit()];

    testWidgets('a supplier credit can be set against a bill', (tester) async {
      // A return raised from the goods receipt debited payables and named no
      // bill, and nothing on the desktop could set it against one.
      final _SettlementApi api = vendorApi();
      await _pump(
        tester,
        api,
        direction: SettlementDirection.payment,
        perms: const ['PAYMENT_VIEW', 'PAYMENT_CREATE'],
      );

      await tester.tap(find.widgetWithText(OutlinedButton, 'Supplier credits'));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('Fixture Supplier'));
      await tester.pumpAndSettle();

      expect(find.textContaining('Nothing moves in the ledger'), findsOneWidget);
      expect(find.textContaining('236.00 of credit'), findsOneWidget);
      await tester.tap(find.widgetWithText(FilledButton, 'Apply'));
      await tester.pumpAndSettle();

      expect(api.appliedCredit, <String, dynamic>{
        'return_id': 'pr-1',
        'invoice_id': 'pi-1',
        'amount': '236.00',
      });
    });

    testWidgets('recording a payment says the supplier holds a credit',
        (tester) async {
      // Paying the bill in full while the credit stands pays the supplier for
      // the goods that went back.
      final _SettlementApi api = vendorApi(rows: [_settlement()]);
      await _pump(
        tester,
        api,
        direction: SettlementDirection.payment,
        perms: const ['PAYMENT_VIEW', 'PAYMENT_CREATE'],
      );

      await tester.tap(find.widgetWithText(FilledButton, 'Record Payment'));
      await tester.pumpAndSettle();
      await _chooseParty(tester, 'Fixture Supplier');

      expect(
        find.textContaining('owes the firm 236.00 from returns '
            '(PR-2026-2027-000009)'),
        findsOneWidget,
      );
    });

    testWidgets('receipts offer no supplier credit', (tester) async {
      await _pump(tester, _SettlementApi());

      expect(find.text('Supplier credits'), findsNothing);
    });
  });

  testWidgets('a deposit says which order it came in against', (tester) async {
    await _pump(
      tester,
      _SettlementApi(
        rows: [_settlement(salesOrderNumber: 'SO-2026-2027-000004')],
      ),
    );

    // Without it a deposit is indistinguishable from a payment somebody made
    // for no stated reason.
    expect(find.textContaining('against SO-2026-2027-000004'), findsOneWidget);
  });

  testWidgets('money on account can be applied to an invoice', (tester) async {
    final _SettlementApi api = _SettlementApi(
      rows: [_settlement(amount: '5000.00', unallocated: '5000.00')],
      outstanding: [_invoice('inv-1', 'SI-2026-2027-000009', '3000.00')],
    );
    await _pump(tester, api);

    await tester.tap(find.byTooltip('Apply to an invoice'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, '3000.00');
    await tester.tap(find.widgetWithText(FilledButton, 'Apply'));
    await tester.pumpAndSettle();

    // The half that was missing entirely: `ADVANCE_APPLY` was a declared
    // transaction type nothing could reach.
    expect(api.allocated?['invoice_id'], 'inv-1');
    expect(api.allocated?['amount'], '3000.00');
  });

  testWidgets('the dialog says that nothing moves in the ledger',
      (tester) async {
    final _SettlementApi api = _SettlementApi(
      rows: [_settlement(amount: '5000.00', unallocated: '5000.00')],
      outstanding: [_invoice('inv-1', 'SI-9', '3000.00')],
    );
    await _pump(tester, api);

    await tester.tap(find.byTooltip('Apply to an invoice'));
    await tester.pumpAndSettle();

    // "Applying" money sounds like moving it, and it does not: the money
    // arrived when the receipt was recorded.
    expect(find.textContaining('Nothing moves in the ledger'), findsOneWidget);
  });

  testWidgets('a supplier advance can be applied to a bill that arrived since',
      (tester) async {
    final _SettlementApi api = _SettlementApi(
      rows: [
        _settlement(
          number: 'PY-2026-2027-000001',
          amount: '5000.00',
          unallocated: '5000.00',
          direction: 'PAYMENT',
        ),
      ],
      outstanding: [_invoice('bill-1', 'PI-2026-2027-000004', '3000.00')],
    );
    await _pump(
      tester,
      api,
      direction: SettlementDirection.payment,
      perms: const <String>['PAYMENT_VIEW', 'PAYMENT_CREATE'],
    );

    // The mirror of the customer's advance, and the same hole: a payment
    // recorded before the bill arrived could never be set against it
    // (D-BUY-8).
    await tester.tap(find.byTooltip('Apply to a bill'));
    await tester.pumpAndSettle();
    expect(find.textContaining('left when the payment'), findsOneWidget);
    await tester.enterText(find.byType(TextField).last, '3000.00');
    await tester.tap(find.widgetWithText(FilledButton, 'Apply'));
    await tester.pumpAndSettle();

    expect(api.allocated?['direction'], 'PAYMENT');
    expect(api.allocated?['invoice_id'], 'bill-1');
    expect(api.allocated?['amount'], '3000.00');
  });

  testWidgets('a fully applied receipt offers no Apply button',
      (tester) async {
    await _pump(tester, _SettlementApi(rows: [_settlement()]));

    expect(find.byTooltip('Apply to an invoice'), findsNothing);
  });

  testWidgets('a reversed receipt offers no Apply button', (tester) async {
    await _pump(
      tester,
      _SettlementApi(
        rows: [_settlement(unallocated: '5000.00', status: 'REVERSED')],
      ),
    );

    // It holds nothing: the money went back.
    expect(find.byTooltip('Apply to an invoice'), findsNothing);
  });

  testWidgets('somebody who cannot record receipts cannot apply one',
      (tester) async {
    await _pump(
      tester,
      _SettlementApi(rows: [_settlement(unallocated: '5000.00')]),
      perms: const <String>['RECEIPT_VIEW'],
    );

    expect(find.byTooltip('Apply to an invoice'), findsNothing);
  });

  testWidgets('a cashier can open the party picker without CUSTOMER_VIEW',
      (tester) async {
    // `CASHIER` holds `RECEIPT_CREATE`, `RECEIPT_VIEW`, `PAYMENT_CREATE` and
    // `PAYMENT_VIEW` -- and not `CUSTOMER_VIEW`. This screen read
    // `GET /api/v1/customers` to fill the picker, so recording a receipt was
    // refused at the party lookup, before the receipt the cashier was
    // authorised for was attempted. The role was blocked one step short of
    // the only thing it exists to do. Plan step 22.4, found 2026-09-15 by
    // signing in as one.
    final _SettlementApi api = _SettlementApi();
    await _pump(
      tester,
      api,
      perms: const [
        'RECEIPT_CREATE',
        'RECEIPT_VIEW',
        'PAYMENT_CREATE',
        'PAYMENT_VIEW',
      ],
    );

    await tester.tap(find.text('Record Receipt'));
    await tester.pumpAndSettle();

    // It asked the money screens' own route, and got the dialog rather than
    // the refusal the customer master would have answered with.
    expect(api.partiesAskedFor, [SettlementDirection.receipt]);
    expect(find.text('Amount'), findsOneWidget);
    expect(find.textContaining('permission'), findsNothing);
  });

  testWidgets('the party picker narrows as you type', (tester) async {
    // A firm with a handful of customers is fine in a dropdown. A distributor
    // with hundreds is handed a scrollbar and asked to find a name in it, at
    // the till, with somebody waiting. Reported by the owner at plan step
    // 22.4, 2026-09-15.
    //
    // Filtered in the dialog rather than by re-asking the server per
    // keystroke: the route caps at 200 and the list is already in hand.
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: RecordSettlementDialog(
            api: _SettlementApi(),
            direction: SettlementDirection.receipt,
            parties: const [
              PartyOption(id: 'c-1', code: 'WHOLE01C01', name: 'Vijaya Stores'),
              PartyOption(id: 'c-2', code: 'WHOLE01C02', name: 'Anand Agencies'),
              PartyOption(id: 'c-3', code: 'MEDI01C09', name: 'Classic Traders'),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Tapping with nothing typed offers everybody.
    await tester.tap(find.byType(TextFormField).first);
    await tester.pumpAndSettle();
    expect(find.textContaining('Vijaya Stores'), findsOneWidget);
    expect(find.textContaining('Anand Agencies'), findsOneWidget);

    // By name.
    await tester.enterText(find.byType(TextFormField).first, 'anand');
    await tester.pumpAndSettle();
    expect(find.textContaining('Anand Agencies'), findsOneWidget);
    expect(find.textContaining('Vijaya Stores'), findsNothing);

    // And by code, because either is what somebody has in front of them --
    // a code off a bill, a name off a cheque.
    await tester.enterText(find.byType(TextFormField).first, 'MEDI01');
    await tester.pumpAndSettle();
    expect(find.textContaining('Classic Traders'), findsOneWidget);
    expect(find.textContaining('Anand Agencies'), findsNothing);

    // A search matching nobody says so rather than showing an empty sheet.
    await tester.enterText(find.byType(TextFormField).first, 'zzzz');
    await tester.pumpAndSettle();
    expect(find.text('Nobody matches that.'), findsOneWidget);
  });
}
