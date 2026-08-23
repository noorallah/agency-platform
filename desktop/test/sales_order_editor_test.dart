// A firm can take a sales order from the desktop.
//
// Until now it could not. The only way an order appeared was by converting a
// quotation, so a phone order had to be typed as an offer and accepted in the
// same breath — two documents, and an acceptance the customer never gave.
// `POST /api/v1/sales-orders` had worked all along with nothing in
// `desktop/lib` calling it.
//
// Three behaviours carry the weight here.
//
// 1. **A blank discount is not a zero.** Absent from the payload is what lets
//    the server apply the firm's price list for this customer and product, or
//    failing that the customer's standing rate. A typed zero is somebody
//    saying "not this time" and has to arrive as a zero. Coercing blank to
//    zero would switch every standing arrangement off silently, on every
//    order, and nothing downstream would report it.
// 2. **A price is prefilled and then left alone.** A line starts at what the
//    product sells for; once somebody types a rate, changing the product must
//    not rewrite it.
// 3. **A correction carries the version it read.** The update replaces the
//    whole line collection, so a lost race costs every line somebody entered
//    rather than a single field.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/sales_order_editor_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _customer(String id, String name, {String discount = '0'}) =>
    <String, dynamic>{
      'id': id,
      'code': id.toUpperCase(),
      'name': name,
      'display_name': name,
      'customer_type': 'BUSINESS',
      'currency_code': 'INR',
      'default_discount_percent': discount,
      'status': 'ACTIVE',
    };

Json _product(String id, String code, String name, String price, String mrp) =>
    <String, dynamic>{
      'id': id,
      'code': code,
      'name': name,
      'selling_price': price,
      'mrp': mrp,
      'status': 'ACTIVE',
    };

/// A draft as `GET /api/v1/sales-orders/{id}` answers with it.
Json _draft({String status = 'DRAFT', int version = 6}) => <String, dynamic>{
      'id': 'so-1',
      'version': version,
      'order_number': 'SO-2026-2027-000012',
      'order_date': '2026-08-11',
      'status': status,
      'customer_id': 'c1',
      'branch_id': 'b1',
      'warehouse_id': 'w1',
      'customer_reference': 'PO-771',
      'bill_discount_percent': '0',
      'bill_discount_amount': '0',
      'lines': <Json>[
        <String, dynamic>{
          'line_number': 1,
          'product_id': 'p1',
          'quantity': '3',
          'free_quantity': '0',
          'unit_price': '95',
          'discount_percent': '0',
          'discount_amount': '0',
        },
      ],
    };

class _OrderApi extends ApiClient {
  _OrderApi({
    this.customerRows = const [],
    this.productRows = const [],
  }) : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> customerRows;
  final List<Json> productRows;

  /// The order an edit reads back, when one is being corrected.
  Json? existing;

  Json? created;
  Json? updated;
  int? sentVersion;
  ApiException? refuseWith;

  /// Every page size asked for, so an oversized page — which a real backend
  /// refuses rather than clamps — fails the test instead of production.
  final List<String> pageSizes = <String>[];

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
    if (query != null && query['page_size'] != null) {
      pageSizes.add(query['page_size']!);
    }
    if (path == '/api/v1/customers') return _paged(customerRows);
    if (path == '/api/v1/products') return _paged(productRows);
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
        },
      ]);
    }
    if (method == 'GET' && path.startsWith('/api/v1/sales-orders/')) {
      return <String, dynamic>{'data': existing};
    }
    if (method == 'PUT' && path.startsWith('/api/v1/sales-orders/')) {
      if (refuseWith != null) throw refuseWith!;
      updated = body;
      sentVersion = expectedVersion;
      return <String, dynamic>{'data': existing};
    }
    if (method == 'POST' && path == '/api/v1/sales-orders') {
      if (refuseWith != null) throw refuseWith!;
      created = body;
      return <String, dynamic>{
        'data': <String, dynamic>{'id': 'so-1', 'order_number': 'SO-1'},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

_OrderApi _api() => _OrderApi(
      customerRows: <Json>[
        _customer('c1', 'Anand Agencies', discount: '7.5'),
        _customer('c2', 'Bright Stores'),
      ],
      productRows: <Json>[
        _product('p1', 'P1', 'Shampoo 180ml', '100', '120'),
        _product('p2', 'P2', 'Rice 5kg', '250', '300'),
      ],
    );

Future<bool?> _pump(
  WidgetTester tester,
  _OrderApi api, {
  String? orderId,
  Size window = const Size(1600, 1200),
}) async {
  tester.view.physicalSize = window;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  bool? popped;
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (BuildContext context) => TextButton(
          onPressed: () async {
            popped = await showDialog<bool>(
              context: context,
              builder: (_) => SalesOrderEditorDialog(
                api: api,
                today: DateTime(2026, 8, 14),
                orderId: orderId,
              ),
            );
          },
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  return popped;
}

/// Pick from one of the dialog's dropdowns. `.last` because the collapsed
/// button shows the chosen label too, and the menu item is the one on top.
Future<void> _choose(WidgetTester tester, String key, String label) async {
  await tester.tap(find.byKey(ValueKey<String>(key)));
  await tester.pumpAndSettle();
  await tester.tap(find.text(label).last);
  await tester.pumpAndSettle();
}

Future<void> _create(WidgetTester tester) async {
  await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
  await tester.pumpAndSettle();
}

Json _firstLine(Json payload) =>
    Map<String, dynamic>.from((payload['lines'] as List).first as Map);

void main() {
  testWidgets('an order is taken for a customer, a branch and a warehouse',
      (tester) async {
    final _OrderApi api = _api();
    await _pump(tester, api);
    await _choose(tester, 'sales-order-customer', 'Anand Agencies');
    await _create(tester);

    final Json sent = api.created!;
    expect(sent['customer_id'], 'c1');
    // The branch and warehouse the firm marked as its default, so the
    // ordinary order is savable without touching either picker.
    expect(sent['branch_id'], 'b1');
    expect(sent['warehouse_id'], 'w1');
    expect(sent['order_date'], '2026-08-14');
    // Nothing was promised, so nothing is claimed.
    expect(sent.containsKey('delivery_date'), isFalse);

    final Json line = _firstLine(sent);
    expect(line['line_number'], 1);
    expect(line['product_id'], 'p1');
    expect(line['quantity'], '1');
    expect(line['unit_price'], '100');
  });

  testWidgets('an order with nothing chosen to sell to is not sent',
      (tester) async {
    // The customer is deliberately not defaulted: it is the point of the
    // document, and defaulting it lets an order be raised for the wrong shop
    // by not touching the field.
    final _OrderApi api = _api();
    await _pump(tester, api);
    await _create(tester);

    expect(api.created, isNull);
    expect(find.text('Choose a customer.'), findsOneWidget);
  });

  testWidgets('several lines are ordered in the sequence they were typed',
      (tester) async {
    final _OrderApi api = _api();
    await _pump(tester, api);
    await _choose(tester, 'sales-order-customer', 'Anand Agencies');
    await tester.tap(find.widgetWithText(TextButton, 'Add line'));
    await tester.pumpAndSettle();
    await _choose(tester, 'sales-order-line-product-1', 'P2  Rice 5kg');
    await _create(tester);

    final List<dynamic> lines = api.created!['lines'] as List<dynamic>;
    expect(lines.length, 2);
    expect(Map<String, dynamic>.from(lines[1] as Map)['line_number'], 2);
    expect(Map<String, dynamic>.from(lines[1] as Map)['product_id'], 'p2');
  });

  group('a discount nobody typed is not a discount of zero', () {
    testWidgets('a blank discount is left out of the payload entirely',
        (tester) async {
      // Absent is what tells the server to apply the arrangement it holds —
      // the price list for this customer and product, or their standing rate.
      // A zero here would refuse both, silently, on every line of every order.
      final _OrderApi api = _api();
      await _pump(tester, api);
      await _choose(tester, 'sales-order-customer', 'Anand Agencies');
      await _create(tester);

      final Json line = _firstLine(api.created!);
      expect(line.containsKey('discount_percent'), isFalse);
      expect(line.containsKey('discount_amount'), isFalse);
    });

    testWidgets('a discount typed as zero is sent as zero', (tester) async {
      // "Not this time" for a customer who normally gets 7.5%. The server
      // keeps None and 0 apart, so the client must too.
      final _OrderApi api = _api();
      await _pump(tester, api);
      await _choose(tester, 'sales-order-customer', 'Anand Agencies');
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Discount %'),
        '0',
      );
      await tester.pumpAndSettle();
      await _create(tester);

      expect(_firstLine(api.created!)['discount_percent'], '0');
    });

    testWidgets("the customer's standing rate is said, not filled in",
        (tester) async {
      // Filling it in would turn an inherited rate into an explicit one, and
      // an explicit rate outranks the firm's price list for this product.
      final _OrderApi api = _api();
      await _pump(tester, api);
      await _choose(tester, 'sales-order-customer', 'Anand Agencies');

      expect(find.text("Blank takes this customer's 7.5%."), findsOneWidget);
      await _create(tester);
      expect(_firstLine(api.created!).containsKey('discount_percent'), isFalse);
    });
  });

  testWidgets('a line starts at what the product sells for', (tester) async {
    final _OrderApi api = _api();
    await _pump(tester, api);
    await _choose(tester, 'sales-order-customer', 'Anand Agencies');

    // The first product, priced from the master rather than typed again.
    expect(find.text('100'), findsOneWidget);
    expect(find.text('lists at 100, MRP 120'), findsOneWidget);

    await _choose(tester, 'sales-order-line-product-0', 'P2  Rice 5kg');
    expect(find.text('250'), findsOneWidget);
    await _create(tester);
    expect(_firstLine(api.created!)['unit_price'], '250');
  });

  testWidgets('a price somebody typed survives a change of product',
      (tester) async {
    // The rate was agreed with the customer; refilling it from the master
    // would overwrite what the salesman just said on the phone.
    final _OrderApi api = _api();
    await _pump(tester, api);
    await _choose(tester, 'sales-order-customer', 'Anand Agencies');
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Unit price'),
      '999',
    );
    await tester.pumpAndSettle();

    await _choose(tester, 'sales-order-line-product-0', 'P2  Rice 5kg');
    expect(find.text('999'), findsOneWidget);
    expect(find.text('250'), findsNothing);

    await _create(tester);
    final Json line = _firstLine(api.created!);
    expect(line['product_id'], 'p2');
    expect(line['unit_price'], '999');
  });

  testWidgets('a discount on the whole order reaches the payload',
      (tester) async {
    final _OrderApi api = _api();
    await _pump(tester, api);
    await _choose(tester, 'sales-order-customer', 'Anand Agencies');
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Discount on the whole order %'),
      '10',
    );
    await tester.pumpAndSettle();

    // One unit at a hundred, less a tenth of the order.
    expect(find.textContaining('Ordered before tax: 90.00'), findsOneWidget);
    await _create(tester);
    expect(api.created!['bill_discount_percent'], '10');
    // Nothing was typed as a flat figure, so nothing claims one.
    expect(api.created!.containsKey('bill_discount_amount'), isFalse);
  });

  testWidgets('goods given away are quantified separately from the price',
      (tester) async {
    // Free goods move stock and are outside the gross and the tax base, so
    // they cannot be expressed as a discount.
    final _OrderApi api = _api();
    await _pump(tester, api);
    await _choose(tester, 'sales-order-customer', 'Anand Agencies');
    await tester.enterText(find.widgetWithText(TextFormField, 'Free'), '2');
    await tester.pumpAndSettle();

    // Two given away against one sold; the order is still worth one unit.
    expect(find.textContaining('Ordered before tax: 100.00'), findsOneWidget);
    await _create(tester);
    expect(_firstLine(api.created!)['free_quantity'], '2');
  });

  testWidgets('no picker is ever asked for a page above the server cap',
      (tester) async {
    // `MAX_PAGE_SIZE` is 100 and a request above it is refused rather than
    // clamped — which surfaces as a 500 on the routers that build their
    // pagination by hand. Two screens shipped asking for 500.
    final _OrderApi api = _api();
    await _pump(tester, api);

    expect(api.pageSizes, isNotEmpty);
    for (final String size in api.pageSizes) {
      expect(int.parse(size) <= 100, isTrue, reason: 'asked for $size a page');
    }
  });

  group('correcting a draft', () {
    testWidgets('a draft opens on what it already orders', (tester) async {
      final _OrderApi api = _api()..existing = _draft();
      await _pump(tester, api, orderId: 'so-1');

      expect(find.text('Edit draft order'), findsOneWidget);
      expect(find.widgetWithText(FilledButton, 'Save order'), findsOneWidget);
      // The document's own figures, not the product master's: an order
      // records what was agreed on the day it was taken.
      expect(find.text('95'), findsOneWidget);
      expect(find.text('3'), findsOneWidget);
      expect(find.text('PO-771'), findsOneWidget);
      expect(find.textContaining('Ordered before tax: 285.00'), findsOneWidget);
    });

    testWidgets('a correction carries the version it read as the precondition',
        (tester) async {
      final _OrderApi api = _api()..existing = _draft(version: 6);
      await _pump(tester, api, orderId: 'so-1');
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Quantity'),
        '4',
      );
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Save order'));
      await tester.pumpAndSettle();

      expect(api.created, isNull);
      expect(api.sentVersion, 6);
      expect(_firstLine(api.updated!)['quantity'], '4');
      // Echoed back including the zero: the order is the record of what was
      // agreed, and saying nothing would let a rate introduced since apply to
      // a line that was priced without one.
      expect(_firstLine(api.updated!)['discount_percent'], '0');
    });

    testWidgets('a refused save keeps the typing and says so', (tester) async {
      // This dialog saves from inside itself, so the form is still on screen
      // holding every keystroke — and closing it is what throws them away.
      final _OrderApi api = _api()
        ..existing = _draft()
        ..refuseWith = const ApiException(
          'This record changed since you loaded it.',
          statusCode: 409,
        );
      await _pump(tester, api, orderId: 'so-1');
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Quantity'),
        '9',
      );
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Save order'));
      await tester.pumpAndSettle();

      expect(
        find.textContaining('Your changes are still here'),
        findsOneWidget,
      );
      expect(find.text('9'), findsOneWidget);
    });

    testWidgets('an approved order is shown but cannot be rewritten',
        (tester) async {
      // The server refuses anything but a draft, because an approved order
      // has committed credit and a delivered one has moved stock. Saying so
      // beats letting somebody retype the lines and be refused.
      final _OrderApi api = _api()..existing = _draft(status: 'APPROVED');
      await _pump(tester, api, orderId: 'so-1');

      expect(find.widgetWithText(FilledButton, 'Save order'), findsNothing);
      expect(find.widgetWithText(TextButton, 'Close'), findsOneWidget);
      expect(
        find.textContaining('APPROVED, so it can no longer be rewritten'),
        findsOneWidget,
      );
    });
  });

  testWidgets('the form fits a 1366 by 768 window with several lines',
      (tester) async {
    final _OrderApi api = _api();
    await _pump(tester, api, window: const Size(1366, 768));
    for (int index = 0; index < 3; index += 1) {
      // The button walks down the form as lines are added, so it has to be
      // scrolled to rather than assumed to be on screen.
      await tester.ensureVisible(find.widgetWithText(TextButton, 'Add line'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(TextButton, 'Add line'));
      await tester.pumpAndSettle();
    }

    expect(find.byType(SalesOrderEditorDialog), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
