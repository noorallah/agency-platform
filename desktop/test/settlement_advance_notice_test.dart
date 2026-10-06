// D-UI-16: money applied to no bill is said to be an advance, before and
// after saving. By design the excess is held as an advance; the person has to
// be told, not left to find a closed dialog.

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

Settlement _saved(String direction, String unallocated) =>
    Settlement.fromJson({
      'id': 'st-1',
      'direction': direction,
      'party_id': 'p-1',
      'party_code': 'P1',
      'party_name': 'Kumar Stores',
      'settlement_number': 'ST-000001',
      'settlement_date': '2027-03-15',
      'amount': '9999999.00',
      'allocated_amount': '0.00',
      'unallocated_amount': unallocated,
      'method': 'BANK',
      'ledger_account_name': 'Bank',
      'instrument_reference': '',
      'narration': '',
      'status': 'POSTED',
      'journal_entry_id': 'je-1',
      'reversal_reason': '',
      'allocations': const [],
    });

class _Api extends ApiClient {
  _Api(this.direction)
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final SettlementDirection direction;
  List<Settlement> rows = const [];

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
      PagedResult<Settlement>(items: rows, total: rows.length);

  @override
  Future<List<PartyOption>> settlementParties({
    required SettlementDirection direction,
    String search = '',
  }) async =>
      const [PartyOption(id: 'p-1', code: 'P1', name: 'Kumar Stores')];

  @override
  Future<List<OutstandingInvoice>> outstandingInvoices({
    required SettlementDirection direction,
    required String partyId,
  }) async =>
      const [];

  @override
  Future<Settlement> recordSettlement({
    required SettlementDirection direction,
    required Json data,
  }) async =>
      _saved(direction == SettlementDirection.payment ? 'PAYMENT' : 'RECEIPT',
          '9999999.00');
}

Future<void> _choose(WidgetTester tester) async {
  await tester.tap(find.byType(TextFormField).first);
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Kumar Stores').last);
  await tester.pumpAndSettle();
}

void main() {
  for (final (SettlementDirection d, String thing) in [
    (SettlementDirection.receipt, 'invoice'),
    (SettlementDirection.payment, 'bill'),
  ]) {
    testWidgets('${d.noun}: an amount applied to nothing says it is an advance',
        (tester) async {
      tester.view.physicalSize = const Size(1400, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: RecordSettlementDialog(
            api: _Api(d),
            direction: d,
            parties: const [
              PartyOption(id: 'p-1', code: 'P1', name: 'Kumar Stores'),
            ],
          ),
        ),
      ));
      await tester.pumpAndSettle();
      await _choose(tester);
      await tester.enterText(
          find.widgetWithText(TextField, 'Amount'), '9999999');
      await tester.pumpAndSettle();

      expect(
        find.textContaining(
            '9999999.00 will be held as an advance, not applied to any $thing'),
        findsOneWidget,
      );
    });
  }

  testWidgets('the saved notice names the advance', (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final String payload = base64Url.encode(utf8.encode(jsonEncode({
      'permissions': ['RECEIPT_VIEW', 'RECEIPT_CREATE'],
    })));
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SettlementsPage(
          api: _Api(SettlementDirection.receipt),
          preferences: DesktopPreferencesService(
            directory: Directory.systemTemp.createTempSync('advance'),
          ),
          permissions: PermissionService()..applyAccessToken('h.$payload.s'),
          hasActiveFirm: true,
          direction: SettlementDirection.receipt,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Record Receipt'));
    await tester.pumpAndSettle();
    await _choose(tester);
    await tester.enterText(find.widgetWithText(TextField, 'Amount'), '9999999');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Record receipt'));
    await tester.pumpAndSettle();

    expect(find.textContaining('9999999.00 is held as an advance'),
        findsOneWidget);
  });
}
