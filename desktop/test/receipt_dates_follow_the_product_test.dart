// Backlog 89, step 4: a receipt line offers an expiry date and a manufacturing
// date where its *product* tracks them. The firm's business profile used to
// decide, so a firm on a profile without expiry could not date a medicine it
// had started to carry, and a paint was offered an expiry box it has no use
// for.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/business/business_features.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );
}

PurchaseOrder _order() => PurchaseOrder.fromJson({
      'id': 'po-1',
      'po_number': 'PO-1',
      'purchase_date': '2026-08-01',
      'warehouse_id': 'wh-1',
      'status': 'APPROVED',
      'lines': [
        {
          'id': 'po-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'description': 'Goods',
          'ordered_quantity': '3',
          'unit_price': '10',
        },
      ],
    });

Future<void> _openReceipt(
  WidgetTester tester, {
  required Map<String, dynamic> product,
  required BusinessFeatures features,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Widget editor = GoodsReceiptEditorDialog(
    api: _Api(),
    features: features,
    purchaseOrders: [_order()],
    warehouses: [
      WarehouseRecord.fromJson({'id': 'wh-1', 'code': 'MAIN', 'name': 'Main'}),
    ],
    products: [
      Product.fromJson({'id': 'prod-1', 'code': 'P1', 'name': 'Goods', ...product}),
    ],
  );
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(body: Phase2Scope(child: editor)),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('goods-receipt-order')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('PO-1').last);
  await tester.pumpAndSettle();
}

const ValueKey<String> _expiry = ValueKey<String>('goods-receipt-expiry-po-1-0');
const ValueKey<String> _made = ValueKey<String>('goods-receipt-mfg-po-1-0');

void main() {
  testWidgets('a product that tracks both dates is offered both, whatever the profile',
      (tester) async {
    await _openReceipt(
      tester,
      product: {'track_expiry': true, 'track_manufacturing_date': true},
      // The firm's profile enables neither feature; it is no longer asked.
      features: const BusinessFeatures(<String>{}),
    );

    expect(find.byKey(_expiry), findsOneWidget);
    expect(find.byKey(_made), findsOneWidget);
  });

  testWidgets('a product that tracks neither is offered neither, whatever the profile',
      (tester) async {
    await _openReceipt(
      tester,
      product: {'track_expiry': false, 'track_manufacturing_date': false},
      features: const BusinessFeatures({'ATTACHMENTS', 'COMMISSION'}),
    );

    expect(find.byKey(_expiry), findsNothing);
    expect(find.byKey(_made), findsNothing);
  });

  testWidgets('each date follows its own switch', (tester) async {
    await _openReceipt(
      tester,
      product: {'track_expiry': true, 'track_manufacturing_date': false},
      features: const BusinessFeatures.unknown(),
    );

    expect(find.byKey(_expiry), findsOneWidget);
    expect(find.byKey(_made), findsNothing);
  });
}
