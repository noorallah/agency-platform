// L2 step 11, the lot's page: one read of `/batches/{id}/trail`, the lot's
// own facts on top, every document it passed through below in plain words,
// an unprinted lot never showing its batch number, and cost only where the
// server sent it.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/inventory/lot_trail_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api extends ApiClient {
  _Api(this.data)
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json data;
  final List<String> paths = [];

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
    paths.add('$method $path');
    return {'success': true, 'data': data};
  }
}

Json _trail({required bool printed, required bool withCost}) =>
    <String, dynamic>{
      'batch': <String, dynamic>{
        'id': 'b-1',
        'product_code': 'SKU-1',
        'product_name': 'Amoxicillin 500mg',
        'batch_number': printed ? 'BN-77' : 'L-000123',
        'expiry_date': '2027-06-01',
        'mrp': '45.00',
        'quantity': '14.0000',
      },
      'lot_reference': 'L-000123',
      'has_printed_batch': printed,
      'received_on': '2026-07-02',
      'source_type': 'GOODS_RECEIPT',
      'unit_cost': withCost ? '31.2500' : null,
      'events': <Json>[
        <String, dynamic>{
          'document_type': 'GOODS_RECEIPT',
          'document_id': 'gr-1',
          'document_number': 'GRN-1',
          'document_date': '2026-07-02',
          'party_name': 'Cipla Distributors',
          'quantity': '20.0000',
          'cost_amount': withCost ? '625.00' : null,
          'line_number': 1,
        },
        <String, dynamic>{
          'document_type': 'PURCHASE_INVOICE',
          'document_id': 'pi-1',
          'document_number': 'PB-9',
          'document_date': '2026-07-03',
          'party_name': 'Cipla Distributors',
          'quantity': 0,
          'cost_amount': null,
          'line_number': 1,
        },
        <String, dynamic>{
          'document_type': 'DELIVERY_NOTE',
          'document_id': 'dn-1',
          'document_number': 'DN-4',
          'document_date': '2026-07-10',
          'party_name': 'Anand Agencies',
          'quantity': -6,
          'cost_amount': withCost ? '-187.50' : null,
          'line_number': 2,
        },
      ],
    };

Future<void> _open(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1366, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(body: LotTrailDialog(api: api, batchId: 'b-1')),
  ));
  await tester.pumpAndSettle();
}

String _text(WidgetTester tester, String key) =>
    tester.widget<Text>(find.byKey(ValueKey<String>(key))).data!;

void main() {
  testWidgets('one read; facts, then every document in plain words',
      (tester) async {
    final _Api api = _Api(_trail(printed: true, withCost: true));
    await _open(tester, api);

    expect(api.paths, ['GET /api/v1/batch-serial/batches/b-1/trail']);
    expect(_text(tester, 'lot-trail-item'), 'SKU-1 - Amoxicillin 500mg');
    expect(_text(tester, 'lot-trail-reference'), 'L-000123');
    expect(_text(tester, 'lot-trail-printed-batch'), 'BN-77');
    expect(_text(tester, 'lot-trail-quantity'), '14.0000');
    expect(_text(tester, 'lot-trail-unit-cost'), '31.25');

    expect(find.text('Goods received'), findsOneWidget);
    expect(find.text('Purchase bill'), findsOneWidget);
    expect(find.text('Delivery note'), findsOneWidget);
    expect(find.text('GRN-1'), findsOneWidget);
    expect(find.text('Anand Agencies'), findsOneWidget);
    // In and out in their own columns; the bill moved nothing.
    expect(find.text('20'), findsOneWidget);
    expect(find.text('6'), findsOneWidget);
    expect(find.text('Cost'), findsOneWidget);
    expect(find.text('625.00'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('an unprinted lot shows no batch, and no cost without one',
      (tester) async {
    final _Api api = _Api(_trail(printed: false, withCost: false));
    await _open(tester, api);

    expect(_text(tester, 'lot-trail-printed-batch'), '-');
    expect(_text(tester, 'lot-trail-reference'), 'L-000123');
    expect(find.byKey(const ValueKey('lot-trail-unit-cost')), findsNothing);
    expect(find.text('Cost'), findsNothing);
    expect(find.text('Delivery note'), findsOneWidget);
  });

  test('every document type has a plain-word label', () {
    for (final String type in const [
      'GOODS_RECEIPT',
      'OPENING_STOCK',
      'PURCHASE_INVOICE',
      'DELIVERY_NOTE',
      'SALES_INVOICE',
      'SALES_RETURN',
      'PURCHASE_RETURN',
      'STOCK_TRANSFER',
      'ADJUSTMENT',
      'REPACK',
      'COST_CORRECTION',
      'OTHER',
    ]) {
      expect(lotTrailDocumentLabel(type), isNot(contains('_')));
      expect(lotTrailDocumentLabel(type), isNot(type));
    }
  });
}
