import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/settlement.dart';
import 'package:agency_desktop/models/settlement_direction.dart';
import 'package:agency_desktop/ui/finance/record_settlement_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// One receipt from a parent buyer may clear its shops' bills too.
class _ShopsApi extends ApiClient {
  _ShopsApi(this.bills)
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<OutstandingInvoice> bills;

  /// Every call to the outstanding list: direction and whether shops were asked.
  final List<({SettlementDirection direction, bool withShops})> asked = [];
  Json? recorded;

  @override
  Future<List<OutstandingInvoice>> outstandingInvoices({
    required SettlementDirection direction,
    required String partyId,
    bool withShops = false,
    bool withBranches = false,
  }) async {
    asked.add((direction: direction, withShops: withShops));
    return bills;
  }

  @override
  Future<Settlement> recordSettlement({
    required SettlementDirection direction,
    required Json data,
  }) async {
    recorded = data;
    return Settlement.fromJson({
      'id': 'st-1',
      'direction': direction.name.toUpperCase(),
      'party_id': 'p-1',
    });
  }
}

OutstandingInvoice _bill(
  String id,
  String number,
  String owed, {
  String partyId = 'p-1',
  String partyCode = 'P1',
  String partyName = 'Parent Traders',
}) =>
    OutstandingInvoice.fromJson({
      'invoice_id': id,
      'invoice_number': number,
      'invoice_date': '2026-10-01',
      'invoice_total': owed,
      'allocated_amount': '0.00',
      'outstanding_amount': owed,
      'party_id': partyId,
      'party_code': partyCode,
      'party_name': partyName,
    });

Future<void> _open(
  WidgetTester tester,
  _ShopsApi api,
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
          parties: const [
            PartyOption(id: 'p-1', code: 'P1', name: 'Parent Traders'),
          ],
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.byType(TextFormField).first);
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Parent Traders').last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a parent receipt lists the shops\' bills, labelled, with the hint',
      (tester) async {
    final _ShopsApi api = _ShopsApi([
      _bill('i-own', 'SI-OWN-1', '100.00'),
      _bill('i-shop', 'SI-SHOP-1', '250.00',
          partyId: 's-1', partyCode: 'S1', partyName: 'Corner Shop'),
    ]);
    await _open(tester, api, SettlementDirection.receipt);

    expect(api.asked.single.withShops, isTrue);
    expect(find.byKey(const ValueKey('receipt-shops-hint')), findsOneWidget);
    expect(find.byKey(const ValueKey('bill-shop-i-shop')), findsOneWidget);
    expect(find.text('S1 Corner Shop'), findsOneWidget);
    expect(find.byKey(const ValueKey('bill-shop-i-own')), findsNothing);
    expect(find.text('SI-OWN-1'), findsOneWidget);
    expect(find.text('SI-SHOP-1'), findsOneWidget);
  });

  testWidgets('a customer whose bills are all its own shows no hint or label',
      (tester) async {
    final _ShopsApi api = _ShopsApi([
      _bill('i-own', 'SI-OWN-1', '100.00'),
      _bill('i-own2', 'SI-OWN-2', '50.00'),
    ]);
    await _open(tester, api, SettlementDirection.receipt);

    expect(find.byKey(const ValueKey('receipt-shops-hint')), findsNothing);
    expect(find.byKey(const ValueKey('bill-shop-i-own')), findsNothing);
    expect(find.text('P1 Parent Traders'), findsNothing);
    expect(find.text('SI-OWN-1'), findsOneWidget);
  });

  testWidgets('saving sends the ticked shop bill in the allocations',
      (tester) async {
    final _ShopsApi api = _ShopsApi([
      _bill('i-own', 'SI-OWN-1', '100.00'),
      _bill('i-shop', 'SI-SHOP-1', '250.00',
          partyId: 's-1', partyCode: 'S1', partyName: 'Corner Shop'),
    ]);
    await _open(tester, api, SettlementDirection.receipt);

    await tester.enterText(find.widgetWithText(TextField, 'Amount'), '250');
    await tester.pumpAndSettle();
    await tester.enterText(
      find.descendant(
        of: find.byType(DataTable),
        matching: find.byType(TextField),
      ).last,
      '250',
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Record receipt'));
    await tester.pumpAndSettle();

    expect(api.recorded, isNotNull);
    expect(api.recorded!['party_id'], 'p-1');
    expect(api.recorded!['allocations'], [
      {'invoice_id': 'i-shop', 'amount': '250'},
    ]);
  });

  testWidgets('a payment never asks for the shops', (tester) async {
    final _ShopsApi api = _ShopsApi([_bill('i-own', 'PB-1', '100.00')]);
    await _open(tester, api, SettlementDirection.payment);

    expect(api.asked.single.direction, SettlementDirection.payment);
    expect(api.asked.single.withShops, isFalse);
    expect(find.byKey(const ValueKey('receipt-shops-hint')), findsNothing);
  });
}
