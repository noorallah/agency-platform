// A draft goods receipt could not be corrected.
//
// `updateGoodsReceipt` had a route and a client method and nothing calling it,
// so a receipt entered with a wrong quantity or the wrong warehouse could only
// be cancelled and re-keyed line by line -- and the service takes the edit
// precisely so it need not.
//
// Only a draft: once a receipt is completed its lines are what stock was
// posted at, and the service refuses the change.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_editor_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<String> calls = <String>[];
  Json? sentBody;
  int? sentVersion;

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
    if (method == 'POST' || method == 'PUT') {
      calls.add('$method $path');
      sentBody = body;
      sentVersion = expectedVersion;
      return <String, dynamic>{'data': _receiptJson()};
    }
    // Earlier completed receipts against the order: none.
    return <String, dynamic>{
      'data': const <Json>[],
      'pagination': <String, dynamic>{'total_records': 0},
    };
  }
}

Json _orderJson() => <String, dynamic>{
      'id': 'po-1',
      'order_number': 'PO-0001',
      'vendor_id': 'v-1',
      'warehouse_id': 'wh-1',
      'status': 'APPROVED',
      'lines': <Json>[
        <String, dynamic>{
          'id': 'pol-1',
          'line_number': 1,
          'product_id': 'p-1',
          'description': 'Toothpaste 150g',
          'quantity': '100',
          'unit_price': '25',
        },
      ],
    };

Json _receiptJson({String receiptQuantity = '40'}) => <String, dynamic>{
      'id': 'gr-1',
      'receipt_number': 'GRN-0001',
      'purchase_order_id': 'po-1',
      'purchase_order_number': 'PO-0001',
      'receipt_date': '2026-09-01',
      'status': 'DRAFT',
      'invoice_reference': 'INV-77',
      'transport_details': 'Blue Dart',
      'vehicle_number': 'KA01AB1234',
      'remarks': 'left at the gate',
      'version': 4,
      'lines': <Json>[
        <String, dynamic>{
          'id': 'grl-1',
          'line_number': 1,
          'purchase_order_line_id': 'pol-1',
          'purchase_order_line_number': 1,
          'product_id': 'p-1',
          'description': 'Toothpaste 150g',
          'ordered_quantity': '100',
          'previously_received_quantity': '0',
          'current_receipt_quantity': receiptQuantity,
          'rejected_quantity': '0',
          'damaged_quantity': '0',
          'free_quantity': '0',
          'warehouse_id': 'wh-1',
          'batch_number': 'B-9',
          'expiry_date': '2027-01-31',
          'manufacturing_date': '',
          'remarks': '',
          'unit_price': '25',
        },
      ],
    };

Future<void> _openEditor(WidgetTester tester, _Api api,
    {GoodsReceiptRecord? existing}) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: GoodsReceiptEditorDialog(
        api: api,
        purchaseOrders: <PurchaseOrder>[PurchaseOrder.fromJson(_orderJson())],
        warehouses: const [],
        products: const [],
        existing: existing,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a draft opens with what was already counted', (tester) async {
    final _Api api = _Api();
    await _openEditor(
      tester,
      api,
      existing: GoodsReceiptRecord.fromJson(_receiptJson()),
    );

    // The order gives the line its ordered quantity and units; the receipt
    // gives what was counted. Both, or the editor would open showing the
    // whole order outstanding and quietly re-receive it.
    expect(find.text('40'), findsWidgets);
    expect(find.text('INV-77'), findsWidgets);
  });

  testWidgets('saving an edit puts, with the version it read', (tester) async {
    final _Api api = _Api();
    await _openEditor(
      tester,
      api,
      existing: GoodsReceiptRecord.fromJson(_receiptJson()),
    );

    await tester.tap(find.widgetWithText(FilledButton, 'Save Receipt'));
    await tester.pumpAndSettle();

    expect(api.calls.single, startsWith('PUT'));
    expect(api.calls.single, contains('goods-receipts/gr-1'));
    expect(api.sentVersion, 4);
  });

  testWidgets('the corrected quantity is what gets sent', (tester) async {
    // The overlay has to reach the payload, not just the screen: the order
    // derives each line and the receipt's own numbers are put back on top,
    // so a save that re-sent the order's outstanding quantity would quietly
    // re-receive the whole order.
    //
    // The create path is guarded by `goods_receipt_entry_test.dart`, which
    // overrides `createGoodsReceipt` and asserts the payload -- so this file
    // does not re-cover it.
    final _Api api = _Api();
    await _openEditor(
      tester,
      api,
      existing: GoodsReceiptRecord.fromJson(_receiptJson(receiptQuantity: '40')),
    );

    await tester.tap(find.widgetWithText(FilledButton, 'Save Receipt'));
    await tester.pumpAndSettle();

    final List<dynamic> lines = api.sentBody!['lines'] as List<dynamic>;
    expect(lines, hasLength(1));
    expect((lines.first as Json)['current_receipt_quantity'], '40');
    expect((lines.first as Json)['batch_number'], 'B-9');
  });
}
