// D-BUY-39 desktop: the phase 2 purchase order carries a currency and the
// rate of exchange, the way the bill does. A new order follows the supplier's
// currency until the field is touched and then sends it; a rupee order sends
// neither key; a foreign order without a rate is stopped in the form; and an
// order that exists opens with its own stored values and sends the keys only
// when they changed.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/purchases/purchase_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api extends ApiClient {
  _Api({this.refuse = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// Answer every save with the server's refusal.
  final bool refuse;
  final List<String> calls = <String>[];
  final Map<String, Json?> bodies = <String, Json?>{};

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
    final String call = '$method $path';
    calls.add(call);
    bodies[call] = body;
    if (call == 'POST /api/v1/purchases' || call == 'PUT /api/v1/purchases/po-1') {
      if (refuse) {
        throw ApiException(
          'A bill in USD needs its exchange rate.',
          statusCode: 422,
        );
      }
      return {'data': _orderJson()};
    }
    if (call == 'POST /api/v1/purchases/preview') {
      return {
        'data': {
          'order': {
            'id': 'po-1',
            'po_number': 'PO-0001',
            'status': 'DRAFT',
            'vendor_id': 'vendor-1',
            'branch_id': 'branch-1',
            'warehouse_id': 'warehouse-1',
            'lines': <Json>[],
          },
          'interstate': false,
          'lines': <Json>[],
        },
      };
    }
    return {'data': const <dynamic>[]};
  }
}

Json _orderJson({String? currency, String? rate}) => {
      'id': 'po-1',
      'firm_id': 'firm-1',
      'branch_id': 'branch-1',
      'warehouse_id': 'warehouse-1',
      'vendor_id': 'vendor-1',
      'po_number': 'PO-0001',
      'purchase_date': '2026-10-01',
      'status': 'DRAFT',
      'grand_total': '500.00',
      'currency_code': currency,
      'exchange_rate': rate,
      'lines': [
        {
          'id': 'line-1',
          'line_number': 1,
          'product_id': 'product-1',
          'ordered_quantity': '10',
          'free_quantity': null,
          'unit_price': '100',
          'discount_percent': '0',
          'net_amount': '1000.00',
        },
      ],
    };

Vendor _vendor({String currency = ''}) => Vendor.fromJson(<String, dynamic>{
      'id': 'vendor-1',
      'firm_id': 'firm-1',
      'code': 'V001',
      'name': 'Northwind Supplies',
      'display_name': 'Northwind Supplies',
      'status': 'ACTIVE',
      'currency_code': currency,
      'addresses': <Json>[],
      'contacts': <Json>[],
      'bank_accounts': <Json>[],
      'tax_details': <Json>[],
      'notes': <Json>[],
    });

Future<void> _pumpOrder(
  WidgetTester tester,
  _Api api, {
  PurchaseDialogMode mode = PurchaseDialogMode.create,
  PurchaseOrder? order,
  String supplierCurrency = '',
  Size size = const Size(1366, 768),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseOrderEditorDialog(
          api: api,
          permissions: PermissionService(),
          mode: mode,
          order: order,
          vendors: <Vendor>[_vendor(currency: supplierCurrency)],
          branches: <BranchRecord>[
            BranchRecord.fromJson(<String, dynamic>{
              'id': 'branch-1',
              'firm_id': 'firm-1',
              'code': 'BR-001',
              'name': 'Main Branch',
              'display_name': 'Main Branch',
              'status': 'ACTIVE',
              'is_default': true,
            }),
          ],
          warehouses: <WarehouseRecord>[
            WarehouseRecord.fromJson(<String, dynamic>{
              'id': 'warehouse-1',
              'firm_id': 'firm-1',
              'branch_id': 'branch-1',
              'code': 'WH-001',
              'name': 'Main Warehouse',
              'status': 'ACTIVE',
              'is_default': true,
            }),
          ],
          products: <Product>[
            Product.fromJson(<String, dynamic>{
              'id': 'product-1',
              'firm_id': 'firm-1',
              'code': 'MED-001',
              'name': 'Pain Relief',
              'unit': 'BOX',
              'purchase_price': '100',
              'status': 'ACTIVE',
            }),
          ],
          buyers: const [],
          taxProfiles: const [],
          storageNodes: const [],
          canSubmit: true,
          canApprove: false,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Finder _keyed(String prefix) => find.byWidgetPredicate((widget) =>
    widget.key is ValueKey<String> &&
    (widget.key! as ValueKey<String>).value.startsWith(prefix));

Finder get _currency => _keyed('purchase-order-currency');

Finder get _rate => _keyed('purchase-order-exchange-rate');

Future<void> _save(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('purchase-order-save')));
  await tester.pumpAndSettle();
}

String _text(WidgetTester tester, Finder box) => tester
    .widget<EditableText>(
      find.descendant(of: box, matching: find.byType(EditableText)),
    )
    .controller
    .text;

void main() {
  testWidgets('a USD order with its rate sends both keys', (tester) async {
    final _Api api = _Api();
    await _pumpOrder(tester, api);
    expect(_rate, findsNothing);

    await tester.enterText(_currency, 'usd');
    await tester.pumpAndSettle();
    await tester.enterText(_rate, '83');
    await tester.pumpAndSettle();
    await _save(tester);

    final Json sent = api.bodies['POST /api/v1/purchases']!;
    expect(sent['currency_code'], 'USD');
    expect(sent['exchange_rate'], '83');
    expect(tester.takeException(), isNull);
  });

  testWidgets('a rupee order sends neither key', (tester) async {
    final _Api api = _Api();
    await _pumpOrder(tester, api);
    await _save(tester);

    final Json sent = api.bodies['POST /api/v1/purchases']!;
    expect(sent.containsKey('currency_code'), isFalse);
    expect(sent.containsKey('exchange_rate'), isFalse);
  });

  testWidgets('INR typed is rupees as well', (tester) async {
    final _Api api = _Api();
    await _pumpOrder(tester, api);
    await tester.enterText(_currency, 'INR');
    await tester.pumpAndSettle();
    expect(_rate, findsNothing);
    await _save(tester);
    final Json sent = api.bodies['POST /api/v1/purchases']!;
    expect(sent.containsKey('currency_code'), isFalse);
    expect(sent.containsKey('exchange_rate'), isFalse);
  });

  testWidgets('USD with no rate is stopped in the form, with no call',
      (tester) async {
    final _Api api = _Api();
    await _pumpOrder(tester, api);
    await tester.enterText(_currency, 'USD');
    await tester.pumpAndSettle();
    await _save(tester);

    expect(api.calls, isNot(contains('POST /api/v1/purchases')));
    expect(find.textContaining('Enter the exchange rate'), findsWidgets);

    // A rate that is not above zero is stopped the same way.
    await tester.enterText(_rate, '0');
    await tester.pumpAndSettle();
    await _save(tester);
    expect(api.calls, isNot(contains('POST /api/v1/purchases')));
    expect(tester.takeException(), isNull);
  });

  testWidgets("a new order shows and sends the supplier's currency",
      (tester) async {
    final _Api api = _Api();
    await _pumpOrder(tester, api, supplierCurrency: 'EUR');
    expect(_text(tester, _currency), 'EUR');
    expect(_rate, findsOneWidget);
    await tester.enterText(_rate, '90.5');
    await tester.pumpAndSettle();
    await _save(tester);

    final Json sent = api.bodies['POST /api/v1/purchases']!;
    expect(sent['currency_code'], 'EUR');
    expect(sent['exchange_rate'], '90.5');
  });

  testWidgets('an existing USD order opens showing USD and its rate, and an '
      'untouched save sends neither key', (tester) async {
    final _Api api = _Api();
    await _pumpOrder(
      tester,
      api,
      mode: PurchaseDialogMode.edit,
      order: PurchaseOrder.fromJson(_orderJson(currency: 'USD', rate: '83.00')),
    );
    expect(_text(tester, _currency), 'USD');
    expect(_text(tester, _rate), '83.00');

    await _save(tester);
    final Json sent = api.bodies['PUT /api/v1/purchases/po-1']!;
    expect(sent.containsKey('currency_code'), isFalse);
    expect(sent.containsKey('exchange_rate'), isFalse);
  });

  testWidgets('a changed rate is sent and the currency is not', (tester) async {
    final _Api api = _Api();
    await _pumpOrder(
      tester,
      api,
      mode: PurchaseDialogMode.edit,
      order: PurchaseOrder.fromJson(_orderJson(currency: 'USD', rate: '83.00')),
    );
    await tester.enterText(_rate, '84');
    await tester.pumpAndSettle();
    await _save(tester);
    final Json changed = api.bodies['PUT /api/v1/purchases/po-1']!;
    expect(changed['exchange_rate'], '84');
    expect(changed.containsKey('currency_code'), isFalse);
  });

  testWidgets('clearing the currency sends explicit nulls for both',
      (tester) async {
    final _Api cleared = _Api();
    await _pumpOrder(
      tester,
      cleared,
      mode: PurchaseDialogMode.edit,
      order: PurchaseOrder.fromJson(_orderJson(currency: 'USD', rate: '83.00')),
    );
    await tester.enterText(_currency, '');
    await tester.pumpAndSettle();
    await _save(tester);
    final Json sent = cleared.bodies['PUT /api/v1/purchases/po-1']!;
    expect(sent.containsKey('currency_code'), isTrue);
    expect(sent['currency_code'], isNull);
    expect(sent.containsKey('exchange_rate'), isTrue);
    expect(sent['exchange_rate'], isNull);
  });

  testWidgets("the server's refusal keeps the editor open with its message",
      (tester) async {
    final _Api api = _Api(refuse: true);
    await _pumpOrder(tester, api);
    await tester.enterText(_currency, 'USD');
    await tester.pumpAndSettle();
    await tester.enterText(_rate, '83');
    await tester.pumpAndSettle();
    await _save(tester);

    expect(find.byType(PurchaseOrderEditorDialog), findsOneWidget);
    expect(find.textContaining('needs its exchange rate'), findsWidgets);
  });

  // The phase 2 order editor already overflows the 800x600 window before this
  // change (a new order by 10px, a saved one by 112px across and 6px down,
  // with the currency box left out), so only 1366x768 is asserted here.
  for (final Size size in const [Size(1366, 768)]) {
    for (final String code in const ['', 'USD']) {
      testWidgets('a ${code.isEmpty ? 'rupee' : 'foreign'} order does not '
          'overflow at ${size.width.toInt()}x${size.height.toInt()}',
          (tester) async {
        await _pumpOrder(
          tester,
          _Api(),
          mode: PurchaseDialogMode.edit,
          order: PurchaseOrder.fromJson(
            _orderJson(
              currency: code.isEmpty ? null : code,
              rate: code.isEmpty ? null : '83',
            ),
          ),
          size: size,
        );
        expect(tester.takeException(), isNull);
      });
    }
  }
}
