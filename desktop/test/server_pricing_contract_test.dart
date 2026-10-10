import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/quotation.dart';
import 'package:agency_desktop/phase2/document_page.dart';
import 'package:agency_desktop/ui/quotations/quotation_editor_dialog.dart';
import 'package:agency_desktop/ui/sales/sales_order_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/first_line.dart';
import 'support/server_pricing.dart';

/// The document screens shown what the **server** priced, and checked line by
/// line against it.
///
/// D-UI-95: the quotation, sales order and sales invoice showed a line's
/// total with tax under *Taxable*, and D-UI-96: five more screens worked the
/// taxable value out as gross less the line's own discount. Every test of
/// those screens passed, because each fed the screen a stand-in written from
/// the screen's own idea of the answer. The answers here are the server's
/// (`support/server_pricing.dart`), each with a line discount, a discount on
/// the whole document and a delivery charge, so neither mistake survives.
Json _page(List<Json> rows) => <String, dynamic>{
      'data': rows,
      'pagination': <String, dynamic>{'total_records': rows.length},
    };

/// The firm the server priced the sales order for, answered from its file.
class _OrderApi extends ApiClient {
  _OrderApi(this.priced)
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json priced;
  int previews = 0;

  Json get _order => priced['order'] as Json;

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
    if (path == '/api/v1/sales-orders/preview') {
      previews += 1;
      return <String, dynamic>{'data': priced};
    }
    if (path == '/api/v1/customers') {
      return _page(<Json>[
        <String, dynamic>{
          'id': _order['customer_id'],
          'code': 'CUS-001',
          'name': 'Customer CUS-001',
          'display_name': 'Customer CUS-001',
          'customer_type': 'BUSINESS',
          'currency_code': 'INR',
          'status': 'ACTIVE',
        },
      ]);
    }
    if (path == '/api/v1/products') {
      final Json line = (_order['lines'] as List<dynamic>).first as Json;
      return _page(<Json>[
        <String, dynamic>{
          'id': line['product_id'],
          'code': 'SKU-001',
          'name': 'Product SKU-001',
          'selling_price': '100',
          'status': 'ACTIVE',
        },
      ]);
    }
    if (path == '/api/v1/branches') {
      return _page(<Json>[
        <String, dynamic>{
          'id': _order['branch_id'],
          'code': 'HO',
          'name': 'Head Office',
          'display_name': 'Head Office',
          'is_default': true,
        },
      ]);
    }
    if (path == '/api/v1/warehouses') {
      return _page(<Json>[
        <String, dynamic>{
          'id': _order['warehouse_id'],
          'code': 'WH1',
          'name': 'Main Store',
          'display_name': 'Main Store',
          'is_default': true,
          'branch_id': _order['branch_id'],
        },
      ]);
    }
    if (path == '/api/v1/sales-orders/workflow-settings') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'quotation_stage': true,
          'sales_order_stage': true,
          'delivery_note_stage': true,
          'is_configured': true,
        },
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

Future<void> _open(WidgetTester tester, Widget editor) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (BuildContext context) => TextButton(
          onPressed: () => Navigator.of(context).push<Object?>(
            MaterialPageRoute<Object?>(
              builder: (_) => Scaffold(body: Phase2Scope(child: editor)),
            ),
          ),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

/// Choose the one customer, then wait for the pricing to land.
Future<void> _choose(WidgetTester tester, String key, String name) async {
  await tester.tap(find.byKey(ValueKey<String>(key)));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining(name).last);
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a quotation shows each line as the server priced it',
      (tester) async {
    final Json priced = serverPricing('quotation_preview');
    final Json quotation = priced['quotation'] as Json;
    final Json line = (quotation['lines'] as List<dynamic>).first as Json;
    int previews = 0;
    await _open(
      tester,
      QuotationEditorDialog(
        customers: [
          Customer.fromJson({
            'id': quotation['customer_id'],
            'code': quotation['customer_code'],
            'name': quotation['customer_name'],
            'display_name': quotation['customer_name'],
          }),
        ],
        products: [
          Product.fromJson({
            'id': line['product_id'],
            'code': 'SKU-001',
            'name': line['description'],
            'selling_price': '100',
          }),
        ],
        branches: [
          BranchRecord.fromJson({
            'id': quotation['branch_id'],
            'code': 'HO',
            'name': 'Head office',
            'display_name': 'Head office',
            'is_default': true,
          }),
        ],
        warehouses: [
          WarehouseRecord.fromJson({
            'id': quotation['warehouse_id'],
            'code': 'MAIN',
            'name': 'Main',
            'display_name': 'Main',
            'branch_id': quotation['branch_id'],
            'is_default': true,
          }),
        ],
        today: DateTime(2026, 8, 4),
        preview: (draft) async {
          previews += 1;
          return QuotationPreviewRecord.fromJson(priced);
        },
      ),
    );
    await fillFirstLine(tester,
        document: 'quotation', product: 'Product SKU-001', quantity: '5');
    await _choose(tester, 'quotation-customer', 'Customer CUS-001');

    expect(previews, greaterThan(0));
    expectLinesReconcile(tester,
        document: quotation, rowKey: 'quotation-line-');
    // The figures themselves, so a change to the file is seen here too:
    // 500.00 less 10%, less 5% of the rest, plus 40.00 delivery is 467.50
    // taxable; 18% is 84.15; 551.65 in all.
    expect(find.text('467.50'), findsWidgets);
    expect(find.text('18%'), findsWidgets);
    expect(find.text('551.65'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a sales order shows each line as the server priced it',
      (tester) async {
    final Json priced = serverPricing('sales_order_preview');
    final _OrderApi api = _OrderApi(priced);
    await _open(
      tester,
      SalesOrderEditorDialog(api: api, today: DateTime(2026, 8, 4)),
    );
    await fillFirstLine(tester,
        document: 'sales-order', product: 'Product SKU-001', quantity: '5');
    await _choose(tester, 'sales-order-customer', 'Customer CUS-001');

    expect(api.previews, greaterThan(0));
    expectLinesReconcile(tester,
        document: priced['order'] as Json, rowKey: 'sales-order-line-');
    expect(find.text('467.50'), findsWidgets);
    expect(find.text('18%'), findsWidgets);
    expect(find.text('551.65'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  test("a purchase order line's taxable value is the server's, not the "
      "screen's own sum", () {
    // The purchase order screen is not pumped here; this holds the rule its
    // row and side panel read by (D-UI-96) to the server's own answer.
    final Json order = serverPricing('purchase_order_preview')['order'] as Json;
    expectDocumentAddsUp(order);
    final Json line = pricedLines(order).single;
    final double taxable =
        documentLineTaxable(line['net_amount'], line['tax_amount'])!;
    // Ten at 60.00 less the order's discount of 100.00: taxed on 500.00.
    expect(taxable, closeTo(500, .0001));
    expect(double.parse('${line['tax_amount']}') / taxable * 100,
        closeTo(18, .0001));
    final double own = double.parse('${line['gross_amount']}') -
        double.parse('${line['discount_amount']}');
    expect(own, closeTo(600, .0001), reason: 'what the screen used to show');
  });

  test('every kept answer adds up', () {
    for (final (String name, String key) in <(String, String)>[
      ('quotation_preview', 'quotation'),
      ('sales_order_preview', 'order'),
      ('purchase_order_preview', 'order'),
    ]) {
      expectDocumentAddsUp(serverPricing(name)[key] as Json);
    }
  });
}
