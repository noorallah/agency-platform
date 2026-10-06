import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/quotations/quotation_editor_dialog.dart';
import 'package:agency_desktop/ui/sales/sales_order_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// D-UI-22: a new order opened with the first product and a quantity of 1 on
/// line 1, so choosing only a customer and saving drafted an order for a
/// product nobody chose. A new sales order and a new quotation start with an
/// empty first line and no customer, and Save names what is missing.
class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json _paged(List<Json> rows) => <String, dynamic>{
        'data': rows,
        'pagination': <String, dynamic>{'total_records': rows.length},
      };

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
    if (path == '/api/v1/customers') {
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'c1',
          'code': 'C1',
          'name': 'Anand Agencies',
          'display_name': 'Anand Agencies',
          'customer_type': 'BUSINESS',
          'currency_code': 'INR',
          'status': 'ACTIVE',
        },
      ]);
    }
    if (path == '/api/v1/products') {
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'p1',
          'code': 'P1',
          'name': 'Shampoo 180ml',
          'selling_price': '100',
          'mrp': '120',
          'status': 'ACTIVE',
        },
      ]);
    }
    if (path == '/api/v1/branches') {
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'b1',
          'code': 'HO',
          'name': 'Head Office',
          'display_name': 'Head Office',
          'is_default': true,
        },
      ]);
    }
    if (path == '/api/v1/warehouses') {
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'w1',
          'code': 'WH1',
          'name': 'Main Store',
          'display_name': 'Main Store',
          'is_default': true,
          'branch_id': 'b1',
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

Finder _lineBoxes(String key) => find.descendant(
      of: find.byKey(ValueKey<String>(key)),
      matching: find.byType(EditableText),
    );

void main() {
  testWidgets('a new sales order has no product and no quantity on line 1',
      (tester) async {
    await _open(
      tester,
      SalesOrderEditorDialog(api: _Api(), today: DateTime(2026, 8, 14)),
    );
    // The quantity box (second in the row, after the product picker) is blank.
    expect(
      tester.widget<EditableText>(_lineBoxes('sales-order-line-0').at(1))
          .controller
          .text,
      isEmpty,
    );
    expect(
      tester.widget<EditableText>(_lineBoxes('sales-order-line-0').at(0))
          .controller
          .text,
      isEmpty,
    );
  });

  testWidgets('choosing only a customer and saving says a product is missing',
      (tester) async {
    await _open(
      tester,
      SalesOrderEditorDialog(api: _Api(), today: DateTime(2026, 8, 14)),
    );
    await tester.tap(find.byKey(const ValueKey('sales-order-customer')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Anand Agencies').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('sales-order-save')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Choose a product on line 1.'), findsOneWidget);
  });

  testWidgets('a new quotation has no customer and an empty first line',
      (tester) async {
    await _open(
      tester,
      QuotationEditorDialog(
        customers: [
          Customer.fromJson({
            'id': 'c1',
            'code': 'C-1',
            'name': 'Sri Murugan Stores',
            'display_name': 'Sri Murugan Stores',
          }),
        ],
        products: [
          Product.fromJson({
            'id': 'p1',
            'code': 'P-1',
            'name': 'Tata Salt 1kg',
            'selling_price': '26.00',
          }),
        ],
        branches: [
          BranchRecord.fromJson({
            'id': 'ho',
            'code': 'HO',
            'name': 'Head office',
            'display_name': 'Head office',
            'is_default': true,
          }),
        ],
        warehouses: [
          WarehouseRecord.fromJson({
            'id': 'w1',
            'code': 'MAIN',
            'name': 'Main',
            'display_name': 'Main',
            'branch_id': 'ho',
            'is_default': true,
          }),
        ],
        today: DateTime(2026, 9, 26),
        preview: (draft) async => throw StateError('nothing to price yet'),
      ),
    );
    String boxText(Finder box) => tester.widget<EditableText>(box).controller.text;
    // The pickers' own boxes say nothing: no customer, no product.
    expect(
      boxText(find.descendant(
        of: find.byKey(const ValueKey('quotation-customer')),
        matching: find.byType(EditableText),
      )),
      isEmpty,
    );
    expect(boxText(_lineBoxes('quotation-line-0').at(0)), isEmpty);
    expect(
      tester.widget<EditableText>(_lineBoxes('quotation-line-0').at(1))
          .controller
          .text,
      isEmpty,
    );
  });
}
