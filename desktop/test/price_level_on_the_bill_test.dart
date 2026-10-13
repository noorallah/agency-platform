// Backlog 131 (M13): retail and wholesale. A customer carries his usual price
// level; one box on a sales order, and on a sales bill typed directly, prices
// the whole document at another. Done when the switch reprices every line and
// a new bill starts from the customer's choice.
//
// The server's own unit-prices answer is faked here (`_Api.unitPrices`), the
// way `price_levels_test.dart` fakes it.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/pricing.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/sales/sales_order_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/first_line.dart';

const List<PriceLevelRecord> _firmLevels = [
  PriceLevelRecord(id: 'wh', code: 'WHOLESALE', name: 'Wholesale'),
  PriceLevelRecord(id: 'rt', code: 'RETAIL', name: 'Retail', sortOrder: 2),
  PriceLevelRecord(
    id: 'old',
    code: 'OLD',
    name: 'Old scheme',
    sortOrder: 3,
    isActive: false,
  ),
];

/// What each level charges for each product; a product with no row at the
/// level is charged its own selling price.
const Map<String, Map<String, String>> _levelRates = {
  'wh': {'p1': '80', 'p2': '40'},
  'rt': {'p1': '100', 'p2': '50'},
};

class _Asked {
  const _Asked(this.productIds, this.customerId, this.levelId);
  final List<String> productIds;
  final String customerId;
  final String levelId;
}

class _Api extends ApiClient {
  _Api({
    this.levels = _firmLevels,
    this.levelsRefused = false,
    this.rateIncludesTax = false,
    this.existingOrder,
  }) : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<PriceLevelRecord> levels;
  final bool levelsRefused;
  final bool rateIncludesTax;
  final Json? existingOrder;

  final List<_Asked> asked = [];
  int levelReads = 0;
  Json? createdOrder;
  Json? createdInvoice;

  @override
  Future<List<PriceLevelRecord>> priceLevels() async {
    levelReads += 1;
    if (levelsRefused) throw const ApiException('refused', statusCode: 403);
    return levels;
  }

  @override
  Future<Map<String, UnitPriceQuote>> unitPrices({
    required List<String> productIds,
    required String on,
    String customerId = '',
    String territoryId = '',
    String priceLevelId = '',
    void Function(String? customerPriceLevelId)? onCustomerLevel,
  }) async {
    asked.add(_Asked(productIds, customerId, priceLevelId));
    // c1 is a wholesale customer; c2 and the cash customer have no level.
    final String? usual = customerId == 'c1' ? 'wh' : null;
    onCustomerLevel?.call(usual);
    final String? level = priceLevelId.isNotEmpty ? priceLevelId : usual;
    return {
      for (final String id in productIds)
        id: UnitPriceQuote(
          productId: id,
          unitPrice: '${_levelRates[level]?[id] ?? (id == 'p1' ? '100' : '50')}'
              '.0000',
          source: _levelRates[level]?[id] == null ? 'PRODUCT' : 'PRICE_LEVEL',
        ),
    };
  }

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
        for (final (String id, String name, String? level) in [
          ('c1', 'Anand Agencies', 'wh'),
          ('c2', 'Bright Stores', null),
        ])
          <String, dynamic>{
            'id': id,
            'code': id.toUpperCase(),
            'name': name,
            'display_name': name,
            'customer_type': 'BUSINESS',
            'currency_code': 'INR',
            'status': 'ACTIVE',
            if (level != null) 'price_level_id': level,
          },
      ]);
    }
    if (path == '/api/v1/products') {
      return _paged(<Json>[
        for (final (String id, String name, String price) in [
          ('p1', 'Shampoo 180ml', '100'),
          ('p2', 'Soap bar', '50'),
        ])
          <String, dynamic>{
            'id': id,
            'code': id.toUpperCase(),
            'name': name,
            'selling_price': price,
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
    if (path.contains('workflow-settings')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'quotation_stage': false,
          'sales_order_stage': false,
          'delivery_note_stage': false,
          'rate_includes_tax': rateIncludesTax,
          'is_configured': true,
        },
      };
    }
    if (path.endsWith('/batch-serial/sale-settings')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'price_from_batch': false},
      };
    }
    if (method == 'GET' && path == '/api/v1/sales-orders/so-1') {
      return <String, dynamic>{'data': existingOrder};
    }
    if (method == 'POST' && path == '/api/v1/sales-orders') {
      createdOrder = body;
      return <String, dynamic>{
        'data': <String, dynamic>{'id': 'so-9', 'order_number': 'SO-9'},
      };
    }
    if (method == 'PUT' && path == '/api/v1/sales-orders/so-1') {
      createdOrder = body;
      return <String, dynamic>{'data': existingOrder};
    }
    if (method == 'POST' && path == '/api/v1/sales-invoices') {
      createdInvoice = body;
      return <String, dynamic>{
        'data': <String, dynamic>{
          'id': 'inv-1',
          'invoice_number': 'SI-1',
          'status': 'DRAFT',
          'version': 1,
        },
      };
    }
    if (method == 'POST' && path.endsWith('/preview')) {
      // Not what is under test: keep the last figures.
      throw const ApiException('not priced in this test');
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

Json _savedOrder({String? level}) => <String, dynamic>{
      'id': 'so-1',
      'order_number': 'SO-1',
      'status': 'DRAFT',
      'version': 3,
      'customer_id': 'c1',
      'branch_id': 'b1',
      'warehouse_id': 'w1',
      'order_date': '2026-08-14',
      'rate_includes_tax': false,
      if (level != null) 'price_level_id': level,
      'lines': <Json>[
        <String, dynamic>{
          'line_number': 1,
          'product_id': 'p1',
          'quantity': '2',
          'unit_price': '90',
          'discount_percent': '0',
          'discount_source': 'none',
        },
      ],
    };

Future<void> _settle(WidgetTester tester) async {
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _pumpOrder(
  WidgetTester tester,
  _Api api, {
  String? orderId,
  Size size = const Size(1600, 900),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: SalesOrderEditorDialog(
          api: api,
          today: DateTime(2026, 8, 14),
          orderId: orderId,
        ),
      ),
    ),
  ));
  await _settle(tester);
}

Future<void> _pumpBill(
  WidgetTester tester,
  _Api api, {
  Size size = const Size(1600, 900),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: SalesInvoiceEditorDialog(
          api: api,
          today: DateTime(2026, 8, 14),
        ),
      ),
    ),
  ));
  await _settle(tester);
}

Future<void> _chooseCustomer(
  WidgetTester tester,
  String key,
  String name,
) async {
  await tester.tap(find.byKey(ValueKey<String>(key)));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining(name).last);
  await _settle(tester);
}

Future<void> _chooseLevel(WidgetTester tester, String key, String words) async {
  await tester.tap(find.byKey(ValueKey<String>(key)));
  await tester.pumpAndSettle();
  await tester.tap(find.text(words).last);
  await _settle(tester);
}

/// The box the price is typed in, on line [line] of an order.
Finder _orderPriceBox(int line) => find
    .descendant(
      of: find.byKey(ValueKey<String>('sales-order-line-$line')),
      matching: find.byType(EditableText),
    )
    .at(3);

String _orderPrice(WidgetTester tester, int line) =>
    tester.widget<EditableText>(_orderPriceBox(line)).controller.text;

Finder _billPriceBox(int line) => find
    .descendant(
      of: find.byKey(ValueKey<String>('sales-invoice-direct-$line')),
      matching: find.byType(EditableText),
    )
    .at(2);

String _billPrice(WidgetTester tester, int line) =>
    tester.widget<EditableText>(_billPriceBox(line)).controller.text;

Future<void> _pickBillProduct(WidgetTester tester, int line, String name) async {
  await tester.tap(
    find.byKey(ValueKey<String>('sales-invoice-direct-product-$line')),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining(name).last);
  await _settle(tester);
}

Future<void> _addOrderLine(WidgetTester tester, int line, String name) async {
  await tester.tap(find.textContaining('add a product'));
  await tester.pumpAndSettle();
  await tester.tap(
    find.byKey(ValueKey<String>('sales-order-line-product-$line')),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining(name).last);
  await tester.pumpAndSettle();
  await tester.enterText(
    find
        .descendant(
          of: find.byKey(ValueKey<String>('sales-order-line-$line')),
          matching: find.byType(EditableText),
        )
        .at(1),
    '1',
  );
  await _settle(tester);
}

const ValueKey<String> _orderBox = ValueKey('sales-order-price-level');
const ValueKey<String> _billBox = ValueKey('sales-invoice-price-level');

void main() {
  group('on a sales order', () {
    testWidgets('a firm with no price levels sees no box and nothing changes',
        (tester) async {
      final _Api api = _Api(levels: const []);
      await _pumpOrder(tester, api);
      expect(find.byKey(_orderBox), findsNothing);
      await _chooseCustomer(tester, 'sales-order-customer', 'Anand');
      await fillFirstLine(tester, document: 'sales-order', product: 'Shampoo');
      await _settle(tester);
      await tester.tap(find.byKey(const ValueKey('sales-order-save')));
      await tester.pumpAndSettle();
      expect(api.createdOrder!.containsKey('price_level_id'), isFalse);
      expect(api.levelReads, 1);
    });

    testWidgets('a refused read of the levels leaves the order as it was',
        (tester) async {
      final _Api api = _Api(levelsRefused: true);
      await _pumpOrder(tester, api);
      expect(find.byKey(_orderBox), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a new order starts on the usual level and names it',
        (tester) async {
      final _Api api = _Api();
      await _pumpOrder(tester, api);
      // One extra read when the editor opens, and the box is there.
      expect(api.levelReads, 1);
      expect(find.byKey(_orderBox), findsOneWidget);
      expect(find.byKey(const ValueKey('price-level-helper')), findsNothing);

      await _chooseCustomer(tester, 'sales-order-customer', 'Anand');
      expect(
        find.text('Usual for this customer: Wholesale'),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byKey(_orderBox),
          matching: find.text("Customer's usual"),
        ),
        findsOneWidget,
      );

      // A customer with a level of his own is known without asking; one
      // without is known once a price has been asked.
      await _chooseCustomer(tester, 'sales-order-customer', 'Bright');
      expect(find.text('Usual for this customer: Wholesale'), findsNothing);
      await fillFirstLine(tester, document: 'sales-order', product: 'Shampoo');
      await _settle(tester);
      expect(
        find.text("This customer has no price level: the product's price"),
        findsOneWidget,
      );
      // Only active levels are offered.
      await tester.tap(find.byKey(_orderBox));
      await tester.pumpAndSettle();
      expect(find.text('Wholesale'), findsWidgets);
      expect(find.text('Retail'), findsWidgets);
      expect(find.text('Old scheme'), findsNothing);
    });

    testWidgets(
        'the switch reprices every line, a typed one too, in one request',
        (tester) async {
      final _Api api = _Api();
      await _pumpOrder(tester, api);
      await _chooseCustomer(tester, 'sales-order-customer', 'Anand');
      await fillFirstLine(tester, document: 'sales-order', product: 'Shampoo');
      await _settle(tester);
      await _addOrderLine(tester, 1, 'Soap');
      expect(_orderPrice(tester, 0), '80.00');
      expect(_orderPrice(tester, 1), '40.00');

      // Line 2 is typed by hand.
      await tester.enterText(_orderPriceBox(1), '37');
      await tester.pump(const Duration(milliseconds: 400));
      expect(_orderPrice(tester, 1), '37');

      final int before = api.asked.length;
      await _chooseLevel(tester, 'sales-order-price-level', 'Retail');
      expect(api.asked.length, before + 1);
      expect(api.asked.last.levelId, 'rt');
      expect(api.asked.last.customerId, 'c1');
      expect(api.asked.last.productIds, unorderedEquals(['p1', 'p2']));
      expect(_orderPrice(tester, 0), '100.00');
      expect(_orderPrice(tester, 1), '50.00');
      expect(find.text('from: Dealer level'), findsWidgets);

      // A product chosen afterwards is asked at the chosen level too.
      await _addOrderLine(tester, 2, 'Soap');
      expect(api.asked.last.levelId, 'rt');

      await tester.tap(find.byKey(const ValueKey('sales-order-save')));
      await tester.pumpAndSettle();
      expect(api.createdOrder!['price_level_id'], 'rt');
      final List<dynamic> lines = api.createdOrder!['lines'] as List<dynamic>;
      expect((lines.first as Json)['unit_price'], '100.00');
    });

    testWidgets('on the usual level the payload says null, and a new customer '
        'puts the box back', (tester) async {
      final _Api api = _Api();
      await _pumpOrder(tester, api);
      await _chooseCustomer(tester, 'sales-order-customer', 'Anand');
      await fillFirstLine(tester, document: 'sales-order', product: 'Shampoo');
      await _settle(tester);
      await _chooseLevel(tester, 'sales-order-price-level', 'Retail');
      expect(_orderPrice(tester, 0), '100.00');

      await _chooseCustomer(tester, 'sales-order-customer', 'Bright');
      expect(
        find.descendant(
          of: find.byKey(_orderBox),
          matching: find.text("Customer's usual"),
        ),
        findsOneWidget,
      );
      expect(api.asked.last.levelId, '');

      await tester.tap(find.byKey(const ValueKey('sales-order-save')));
      await tester.pumpAndSettle();
      expect(api.createdOrder!.containsKey('price_level_id'), isTrue);
      expect(api.createdOrder!['price_level_id'], isNull);
    });

    testWidgets('an existing order opens on its saved level and keeps it',
        (tester) async {
      final _Api api = _Api(existingOrder: _savedOrder(level: 'rt'));
      await _pumpOrder(tester, api, orderId: 'so-1');
      expect(
        find.descendant(
          of: find.byKey(_orderBox),
          matching: find.text('Retail'),
        ),
        findsOneWidget,
      );
      // Nothing was asked of the server just for opening it.
      expect(api.asked, isEmpty);
      await tester.tap(find.byKey(const ValueKey('sales-order-save')));
      await tester.pumpAndSettle();
      expect(api.createdOrder!['price_level_id'], 'rt');
    });

    testWidgets('an order saved on a level since switched off still shows it',
        (tester) async {
      final _Api api = _Api(existingOrder: _savedOrder(level: 'old'));
      await _pumpOrder(tester, api, orderId: 'so-1');
      expect(
        find.descendant(
          of: find.byKey(_orderBox),
          matching: find.text('Old scheme'),
        ),
        findsOneWidget,
      );
    });

    testWidgets('with GST in the rates the switch clears the price boxes '
        'instead of quoting', (tester) async {
      final _Api api = _Api(rateIncludesTax: true);
      await _pumpOrder(tester, api);
      await _chooseCustomer(tester, 'sales-order-customer', 'Anand');
      await fillFirstLine(tester, document: 'sales-order', product: 'Shampoo');
      await tester.enterText(_orderPriceBox(0), '118');
      await _settle(tester);
      expect(_orderPrice(tester, 0), '118');

      final int before = api.asked.length;
      await _chooseLevel(tester, 'sales-order-price-level', 'Retail');
      expect(api.asked.length, before);
      expect(_orderPrice(tester, 0), '');

      await tester.tap(find.byKey(const ValueKey('sales-order-save')));
      await tester.pumpAndSettle();
      expect(api.createdOrder!['price_level_id'], 'rt');
      final Json line = (api.createdOrder!['lines'] as List).first as Json;
      expect(line.containsKey('unit_price'), isFalse);
    });

    testWidgets('the header fits a 1366x768 window, helper line and all',
        (tester) async {
      final _Api api = _Api();
      await _pumpOrder(tester, api, size: const Size(1366, 768));
      await _chooseCustomer(tester, 'sales-order-customer', 'Anand');
      expect(find.byKey(_orderBox), findsOneWidget);
      expect(find.byKey(const ValueKey('price-level-helper')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  group('on a sales bill typed directly', () {
    testWidgets('a firm with no price levels sees no box', (tester) async {
      final _Api api = _Api(levels: const []);
      await _pumpBill(tester, api);
      expect(find.byKey(_billBox), findsNothing);
      await _chooseCustomer(tester, 'sales-invoice-customer', 'Anand');
      await _pickBillProduct(tester, 0, 'Shampoo');
      await tester.enterText(
        find
            .descendant(
              of: find.byKey(const ValueKey('sales-invoice-direct-0')),
              matching: find.byType(EditableText),
            )
            .at(1),
        '1',
      );
      await tester.pump(const Duration(milliseconds: 400));
      await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
      await tester.pumpAndSettle();
      expect(api.createdInvoice!.containsKey('price_level_id'), isFalse);
    });

    testWidgets('choosing a product fills the customer\'s level price',
        (tester) async {
      final _Api api = _Api();
      await _pumpBill(tester, api);
      expect(api.levelReads, 1);
      expect(find.byKey(_billBox), findsOneWidget);

      // No customer yet: the product's own price, nothing asked.
      await _pickBillProduct(tester, 0, 'Shampoo');
      expect(_billPrice(tester, 0), '100');
      expect(api.asked, isEmpty);

      // The customer's choice reprices a line nobody typed on.
      await _chooseCustomer(tester, 'sales-invoice-customer', 'Anand');
      expect(find.text('Usual for this customer: Wholesale'), findsOneWidget);
      expect(_billPrice(tester, 0), '80.00');

      // A product chosen with a customer already there starts at his level.
      await tester.tap(find.textContaining('add a product'));
      await tester.pumpAndSettle();
      await _pickBillProduct(tester, 1, 'Soap');
      expect(api.asked.last.customerId, 'c1');
      expect(api.asked.last.levelId, '');
      expect(_billPrice(tester, 1), '40.00');
    });

    testWidgets('the switch reprices every line and the payload carries it',
        (tester) async {
      final _Api api = _Api();
      await _pumpBill(tester, api);
      await _chooseCustomer(tester, 'sales-invoice-customer', 'Anand');
      await _pickBillProduct(tester, 0, 'Shampoo');
      await tester.tap(find.textContaining('add a product'));
      await tester.pumpAndSettle();
      await _pickBillProduct(tester, 1, 'Soap');
      for (final int line in [0, 1]) {
        await tester.enterText(
          find
              .descendant(
                of: find.byKey(ValueKey<String>('sales-invoice-direct-$line')),
                matching: find.byType(EditableText),
              )
              .at(1),
          '1',
        );
      }
      // Line 2's rate is typed by hand.
      await tester.enterText(_billPriceBox(1), '37');
      await tester.pump(const Duration(milliseconds: 400));
      expect(_billPrice(tester, 0), '80.00');
      expect(_billPrice(tester, 1), '37');

      final int before = api.asked.length;
      await _chooseLevel(tester, 'sales-invoice-price-level', 'Retail');
      expect(api.asked.length, before + 1);
      expect(api.asked.last.levelId, 'rt');
      expect(api.asked.last.productIds, unorderedEquals(['p1', 'p2']));
      expect(_billPrice(tester, 0), '100.00');
      expect(_billPrice(tester, 1), '50.00');

      await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
      await tester.pumpAndSettle();
      expect(api.createdInvoice!['price_level_id'], 'rt');
    });

    testWidgets('changing the customer puts the box back on the usual level',
        (tester) async {
      final _Api api = _Api();
      await _pumpBill(tester, api);
      await _chooseCustomer(tester, 'sales-invoice-customer', 'Anand');
      await _pickBillProduct(tester, 0, 'Shampoo');
      await _chooseLevel(tester, 'sales-invoice-price-level', 'Retail');
      expect(_billPrice(tester, 0), '100.00');

      await _chooseCustomer(tester, 'sales-invoice-customer', 'Bright');
      expect(
        find.descendant(
          of: find.byKey(_billBox),
          matching: find.text("Customer's usual"),
        ),
        findsOneWidget,
      );
      expect(api.asked.last.levelId, '');
      expect(api.asked.last.customerId, 'c2');
    });

    testWidgets('the header fits a 1366x768 window', (tester) async {
      final _Api api = _Api();
      await _pumpBill(tester, api, size: const Size(1366, 768));
      await _chooseCustomer(tester, 'sales-invoice-customer', 'Anand');
      expect(find.byKey(_billBox), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('with GST in the rates the switch clears the rate boxes',
        (tester) async {
      final _Api api = _Api(rateIncludesTax: true);
      await _pumpBill(tester, api);
      await _chooseCustomer(tester, 'sales-invoice-customer', 'Anand');
      await _pickBillProduct(tester, 0, 'Shampoo');
      await tester.enterText(_billPriceBox(0), '118');
      await tester.pump(const Duration(milliseconds: 400));
      expect(_billPrice(tester, 0), '118');

      final int before = api.asked.length;
      await _chooseLevel(tester, 'sales-invoice-price-level', 'Retail');
      expect(api.asked.length, before);
      expect(_billPrice(tester, 0), '');
    });
  });
}
