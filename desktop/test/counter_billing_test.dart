// SEL-12: fast counter billing -- a barcode scan field above the lines, a
// tender split under "Received now", and F9 to save, approve, print and open
// the next bill.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/document_framework/document_steps.dart';
import 'package:agency_desktop/ui/sales/sales_document_steps.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

class _CounterApi extends ApiClient {
  _CounterApi({
    this.grandTotal = '500',
    this.approveRefusal,
    this.walkInRefusal,
  })
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String grandTotal;
  final String? approveRefusal;
  final String? walkInRefusal;

  /// What the server was asked, in order: create, approve, pdf.
  final List<String> calls = <String>[];
  final List<Json> created = <Json>[];

  /// The codes the one barcode lookup was asked about, in order.
  final List<String> lookups = <String>[];

  @override
  Future<List<int>> salesInvoicePdf(String id, {bool referenceCopy = false}) {
    calls.add('pdf:$id');
    return Future<List<int>>.value(<int>[1, 2, 3]);
  }

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
    if (path.contains('workflow-settings')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'quotation_stage': false,
          'sales_order_stage': false,
          'delivery_note_stage': false,
          'default_warehouse_id': 'wh-main',
          'is_configured': true,
        },
      };
    }
    if (path.endsWith('/batch-serial/sale-settings')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'price_from_batch': false},
      };
    }
    if (method == 'GET' && path.startsWith('/api/v1/customers')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'cust-1',
            'code': 'C-1',
            'name': 'Walk-in Customer',
            'display_name': 'Walk-in Customer',
          },
        ],
      };
    }
    if (method == 'GET' && path.startsWith('/api/v1/products')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'prod-1',
            'code': 'P-1',
            'name': 'Soap',
            'barcode': '8901234567890',
            'selling_price': '50',
          },
          <String, dynamic>{
            'id': 'prod-2',
            'code': 'P-2',
            'name': 'Tea',
            'barcode': '8900000000017',
            'selling_price': '120',
          },
        ],
      };
    }
    if (path.contains('/uom-framework/barcode-lookup')) {
      final String code = Uri.parse(path).queryParameters['code'] ?? '';
      lookups.add(code);
      if (code == _cartonOfSoap) {
        return <String, dynamic>{
          'data': <String, dynamic>{
            'code': code,
            'product_id': 'prod-1',
            'product_code': 'P-1',
            'product_name': 'Soap',
            'packaging_level_id': 'level-1',
            'level_name': 'Carton',
            'base_quantity': '12.000000',
            'matched_field': 'barcode',
            'uom_code': 'CTN',
            'stock_uom_code': 'PCS',
          },
        };
      }
      if (code == _sharedCode) {
        throw const ApiException(
          '2 products or packaging levels carry the code 5550001. A code '
          'has to name one thing before it can be scanned.',
          statusCode: 409,
        );
      }
      if (code == _cartonOfUnlisted) {
        return <String, dynamic>{
          'data': <String, dynamic>{
            'code': code,
            'product_id': 'prod-9',
            'product_code': 'P-9',
            'product_name': 'Retired',
            'packaging_level_id': 'level-9',
            'level_name': 'Box',
            'base_quantity': '10',
            'matched_field': 'ean',
          },
        };
      }
      throw ApiException('Nothing in this firm carries the code $code.',
          statusCode: 404);
    }
    if (path.contains('billable')) return <String, dynamic>{'data': <Json>[]};
    if (method == 'GET' && path.startsWith('/api/v1/sales-invoices/inv-')) {
      // The saved draft, read back once a later step was refused.
      return <String, dynamic>{
        'data': <String, dynamic>{
          'id': 'inv-1',
          'status': 'DRAFT',
          'invoice_date': '2026-08-14',
          'customer_id': 'cust-1',
          'customer_name': 'Walk-in Customer',
          'branch_id': 'branch-1',
          'version': 1,
          'lines': <Json>[
            <String, dynamic>{
              'line_number': 1,
              'source_document_type': 'DELIVERY_NOTE',
              'source_document_id': 'dn-own',
              'source_document_number': 'DN-1',
              'source_document_line_id': 'dnl-1',
              'product_id': 'prod-1',
              'warehouse_id': 'wh-main',
              'description': 'Soap',
              'delivered_quantity': '1',
              'current_invoice_quantity': '1',
              'unit_price': '50',
              'discount_percent': '0',
            },
          ],
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/sales-invoices/preview') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'interstate': false,
          'invoice': <String, dynamic>{
            'invoice_number': 'SI-1',
            'subtotal': grandTotal,
            'tax_total': '0',
            'grand_total': grandTotal,
            'lines': const <Json>[],
          },
          'lines': const <Json>[],
        },
      };
    }
    if (method == 'POST' &&
        path == '/api/v1/sales-invoices/walk-in-customer') {
      calls.add('walk-in');
      if (walkInRefusal != null) {
        throw ApiException(walkInRefusal!, statusCode: 422);
      }
      return <String, dynamic>{
        'data': <String, dynamic>{
          'id': 'cust-cash',
          'code': 'CASH',
          'name': 'Cash sale',
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/sales-invoices') {
      calls.add('create');
      created.add(body!);
      return <String, dynamic>{
        'data': <String, dynamic>{
          'id': 'inv-${created.length}',
          'invoice_number': 'SI-${created.length}',
          'status': 'DRAFT',
          'version': 1,
        },
      };
    }
    if (method == 'POST' && path.endsWith('/approve')) {
      calls.add('approve');
      if (approveRefusal != null) {
        throw ApiException(approveRefusal!, statusCode: 422);
      }
      return <String, dynamic>{'data': <String, dynamic>{}};
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

Future<List<String>> _pump(
  WidgetTester tester,
  _CounterApi api, {
  bool mayApprove = true,
  Size size = const Size(1600, 900),
  List<DocumentStep<Json>> steps = const [],
}) async {
  final List<String> printed = <String>[];
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: SalesInvoiceEditorDialog(
          api: api,
          today: DateTime(2026, 8, 14),
          mayApprove: mayApprove,
          steps: steps,
          printer: (context, bytes, name) async {
            api.calls.add('print:$name');
            printed.add(name);
          },
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
  return printed;
}

/// A carton of twelve soaps: a code on a pack, not on the product.
const String _cartonOfSoap = '8901234567906';

/// A code two things carry, which the server refuses to guess between.
const String _sharedCode = '5550001';

/// A pack of a product this bill's list does not hold.
const String _cartonOfUnlisted = '5550009';

Future<void> _scan(WidgetTester tester, String code) async {
  await tester.enterText(
      find.byKey(const ValueKey('counter-scan-field')), code);
  await tester.testTextInput.receiveAction(TextInputAction.done);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _chooseCustomer(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('sales-invoice-customer')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Walk-in Customer').last);
  await tester.pumpAndSettle();
}

String _qty(WidgetTester tester, int line) => tester
    .widget<EditableText>(find
        .descendant(
          of: find.byKey(ValueKey<String>('sales-invoice-direct-$line')),
          matching: find.byType(EditableText),
        )
        .at(1))
    .controller
    .text;

/// What the product box of a direct line shows.
String _product(WidgetTester tester, int line) => tester
    .widget<EditableText>(find
        .descendant(
          of: find.byKey(ValueKey<String>('sales-invoice-direct-$line')),
          matching: find.byType(EditableText),
        )
        .first)
    .controller
    .text;

Future<void> _split(WidgetTester tester) async {
  await tester.ensureVisible(find.byKey(const ValueKey('received-now-split')));
  await tester.tap(find.byKey(const ValueKey('received-now-split')));
  await tester.pumpAndSettle();
}

Future<void> _enter(WidgetTester tester, String key, String text) async {
  final Finder box = find.byKey(ValueKey<String>(key));
  await tester.ensureVisible(box);
  await tester.enterText(box, text);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a bill of products says to choose a customer until one is',
      (tester) async {
    // D-UI-91: products typed before the customer showed no tax and no reason.
    const String hint =
        'Choose a customer, and the bill is priced with its tax.';
    await _pump(tester, _CounterApi());
    expect(find.text(hint), findsOneWidget);
    await _chooseCustomer(tester);
    expect(find.text(hint), findsNothing);
  });

  testWidgets('the scan field is focused and a scan adds, then increments',
      (tester) async {
    final _CounterApi api = _CounterApi();
    await _pump(tester, api);

    // Focused as the counter bill opens, before anything is clicked.
    final TextField field = tester.widget<TextField>(
        find.byKey(const ValueKey('counter-scan-field')));
    expect(field.focusNode!.hasFocus, isTrue);
    await _chooseCustomer(tester);

    await _scan(tester, '8901234567890');
    expect(_product(tester, 0), contains('Soap'));
    expect(_qty(tester, 0), '1');

    await _scan(tester, '8901234567890');
    expect(_qty(tester, 0), '2');
    expect(find.byKey(const ValueKey('sales-invoice-direct-1')), findsNothing);

    await _scan(tester, '8900000000017');
    expect(_qty(tester, 0), '2');
    expect(_qty(tester, 1), '1');
    // The field is ready for the next scan.
    expect(tester.widget<TextField>(
            find.byKey(const ValueKey('counter-scan-field'))).focusNode!
        .hasFocus, isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets('an unknown barcode says so and leaves the bill alone',
      (tester) async {
    final _CounterApi api = _CounterApi();
    await _pump(tester, api);

    await _scan(tester, '000');
    expect(find.byKey(const ValueKey('counter-scan-message')), findsOneWidget);
    expect(find.textContaining('No product has the barcode "000"'),
        findsOneWidget);
    final TextField field = tester.widget<TextField>(
        find.byKey(const ValueKey('counter-scan-field')));
    expect(field.controller!.text, isEmpty);
    expect(field.focusNode!.hasFocus, isTrue);
    expect(_qty(tester, 0), isEmpty);

    // A good scan clears the message.
    await _scan(tester, '8901234567890');
    expect(find.byKey(const ValueKey('counter-scan-message')), findsNothing);
  });

  testWidgets("a pack's barcode adds what the pack holds (backlog 89)",
      (tester) async {
    final _CounterApi api = _CounterApi();
    await _pump(tester, api);
    await _chooseCustomer(tester);

    // The product's own barcode is answered from the list already read.
    await _scan(tester, '8901234567890');
    expect(_qty(tester, 0), '1');
    expect(api.lookups, isEmpty);

    // A carton's label is not on the product: the lookup knows the pack.
    await _scan(tester, _cartonOfSoap);
    expect(api.lookups, <String>[_cartonOfSoap]);
    expect(_product(tester, 0), contains('Soap'));
    expect(_qty(tester, 0), '13');
    expect(find.byKey(const ValueKey('sales-invoice-direct-1')), findsNothing);
    expect(find.text('Carton (CTN) of P-1: 12 PCS added.'), findsOneWidget);
    expect(find.byKey(const ValueKey('counter-scan-message')), findsNothing);

    await _scan(tester, _cartonOfSoap);
    expect(_qty(tester, 0), '25');

    // A single piece again: the note about the carton goes.
    await _scan(tester, '8901234567890');
    expect(_qty(tester, 0), '26');
    expect(find.byKey(const ValueKey('counter-scan-note')), findsNothing);
    expect(tester.widget<TextField>(
            find.byKey(const ValueKey('counter-scan-field'))).focusNode!
        .hasFocus, isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets("a pack's barcode starts a line of its own when it is first",
      (tester) async {
    final _CounterApi api = _CounterApi();
    await _pump(tester, api);
    await _chooseCustomer(tester);

    await _scan(tester, _cartonOfSoap);
    expect(_product(tester, 0), contains('Soap'));
    expect(_qty(tester, 0), '12');
    expect(find.byKey(const ValueKey('counter-scan-note')), findsOneWidget);
  });

  testWidgets('a code two things carry is refused in the server\'s words',
      (tester) async {
    final _CounterApi api = _CounterApi();
    await _pump(tester, api);
    await _chooseCustomer(tester);

    await _scan(tester, _sharedCode);
    expect(find.textContaining('2 products or packaging levels carry'),
        findsOneWidget);
    expect(_qty(tester, 0), isEmpty);

    // A pack of a product the bill's list does not hold is named, not added.
    await _scan(tester, _cartonOfUnlisted);
    expect(find.textContaining('is P-9 Retired, which this bill cannot sell'),
        findsOneWidget);
    expect(_qty(tester, 0), isEmpty);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the tender split sends received_now_tenders with exact keys',
      (tester) async {
    final _CounterApi api = _CounterApi(grandTotal: '500');
    await _pump(tester, api);
    await _chooseCustomer(tester);
    await _scan(tester, '8901234567890');

    await _split(tester);
    expect(find.byKey(const ValueKey('tender-row-0')), findsOneWidget);
    await _enter(tester, 'tender-amount-0', '200');
    await tester.tap(find.byKey(const ValueKey('tender-add')));
    await tester.pumpAndSettle();
    await _enter(tester, 'tender-amount-1', '300');
    await _enter(tester, 'tender-reference-1', 'UTR1');

    expect(find.text('Balance 0.00'), findsOneWidget);
    expect(find.byKey(const ValueKey('tender-change')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
    await tester.pumpAndSettle();

    final Json body = api.created.single;
    expect(body.containsKey('received_now_amount'), isFalse);
    expect(body['received_now_tenders'], <Map<String, dynamic>>[
      <String, dynamic>{'mode': 'CASH', 'amount': '200'},
      <String, dynamic>{
        'mode': 'UPI',
        'amount': '300',
        'reference': 'UTR1',
      },
    ]);
  });

  testWidgets('cash over the bill is sent as the remainder and change shown',
      (tester) async {
    final _CounterApi api = _CounterApi(grandTotal: '500');
    await _pump(tester, api);
    await _chooseCustomer(tester);
    await _scan(tester, '8901234567890');

    await _split(tester);
    await tester.tap(find.byKey(const ValueKey('tender-add')));
    await tester.pumpAndSettle();
    // 300 by card, then 500 in cash handed over for the 200 still owed.
    await tester.tap(find.byKey(const ValueKey('tender-mode-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Card').last);
    await tester.pumpAndSettle();
    await _enter(tester, 'tender-amount-1', '300');
    await _enter(tester, 'tender-amount-0', '500');

    expect(find.text('Change to give 300.00'), findsOneWidget);
    expect(find.text('Balance 0.00'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
    await tester.pumpAndSettle();

    expect(api.created.single['received_now_tenders'],
        <Map<String, dynamic>>[
      <String, dynamic>{'mode': 'CASH', 'amount': '200.00'},
      <String, dynamic>{'mode': 'CARD', 'amount': '300'},
    ]);
  });

  testWidgets('without the split the single amount fields go as before',
      (tester) async {
    final _CounterApi api = _CounterApi();
    await _pump(tester, api);
    await _chooseCustomer(tester);
    await _scan(tester, '8901234567890');
    await _enter(tester, 'received-now-amount', '100');

    await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
    await tester.pumpAndSettle();

    final Json body = api.created.single;
    expect(body.containsKey('received_now_tenders'), isFalse);
    expect(body['received_now_amount'], '100');
    expect(body['received_now_method'], 'CASH');
  });

  testWidgets('Walk-in selects the cash customer, asks for the buyer, and '
      'defaults the amount received to the bill', (tester) async {
    final _CounterApi api = _CounterApi(grandTotal: '500');
    await _pump(tester, api);
    expect(find.byKey(const ValueKey('sales-invoice-buyer-name')),
        findsNothing);

    await tester.tap(find.byKey(const ValueKey('sales-invoice-walk-in')));
    await tester.pumpAndSettle();
    expect(api.calls, <String>['walk-in']);
    expect(find.textContaining('Cash sale'), findsWidgets);
    expect(find.byKey(const ValueKey('sales-invoice-buyer-name')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('sales-invoice-buyer-phone')),
        findsOneWidget);

    await _scan(tester, '8901234567890');
    expect(find.text('A walk-in bill is paid in full at the counter.'),
        findsOneWidget);
    expect(
        tester
            .widget<EditableText>(find.descendant(
                of: find.byKey(const ValueKey('received-now-amount')),
                matching: find.byType(EditableText)))
            .controller
            .text,
        '500');

    await _enter(tester, 'sales-invoice-buyer-name', 'Asha');
    await _enter(tester, 'sales-invoice-buyer-phone', '9876543210');
    await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
    await tester.pumpAndSettle();

    final Json body = api.created.single;
    expect(body['customer_id'], 'cust-cash');
    expect(body['buyer_name'], 'Asha');
    expect(body['buyer_phone'], '9876543210');
    expect(body['received_now_amount'], '500');
  });

  testWidgets('a typed amount is not overwritten and an emptied buyer is null',
      (tester) async {
    final _CounterApi api = _CounterApi(grandTotal: '500');
    await _pump(tester, api);
    await tester.tap(find.byKey(const ValueKey('sales-invoice-walk-in')));
    await tester.pumpAndSettle();
    await _enter(tester, 'received-now-amount', '200');
    await _scan(tester, '8901234567890');
    await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
    await tester.pumpAndSettle();

    final Json body = api.created.single;
    expect(body['received_now_amount'], '200');
    expect(body.containsKey('buyer_name'), isTrue);
    expect(body['buyer_name'], isNull);
    expect(body['buyer_phone'], isNull);
  });

  testWidgets('an ordinary customer has no buyer boxes and no buyer keys',
      (tester) async {
    final _CounterApi api = _CounterApi();
    await _pump(tester, api);
    await _chooseCustomer(tester);
    await _scan(tester, '8901234567890');
    expect(find.byKey(const ValueKey('sales-invoice-buyer-name')),
        findsNothing);
    expect(find.byKey(const ValueKey('sales-invoice-buyer-phone')),
        findsNothing);

    await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
    await tester.pumpAndSettle();
    final Json body = api.created.single;
    expect(body.containsKey('buyer_name'), isFalse);
    expect(body.containsKey('buyer_phone'), isFalse);
  });

  testWidgets('a refused walk-in shows the server message', (tester) async {
    final _CounterApi api = _CounterApi(walkInRefusal: 'No cash customer.');
    await _pump(tester, api);
    await tester.tap(find.byKey(const ValueKey('sales-invoice-walk-in')));
    await tester.pumpAndSettle();
    expect(find.textContaining('No cash customer.'), findsWidgets);
    expect(find.byKey(const ValueKey('sales-invoice-buyer-name')),
        findsNothing);
  });

  testWidgets('F9 saves, approves, prints, then opens a fresh bill',
      (tester) async {
    final _CounterApi api = _CounterApi();
    final List<String> printed = await _pump(tester, api);
    await _chooseCustomer(tester);
    await _scan(tester, '8901234567890');

    await tester.sendKeyEvent(LogicalKeyboardKey.f9);
    await tester.pumpAndSettle();

    expect(api.calls, <String>['create', 'approve', 'pdf:inv-1', 'print:SI-1']);
    expect(printed, <String>['SI-1']);
    // A fresh bill for the same counter: no lines, same customer, scanning.
    expect(_qty(tester, 0), isEmpty);
    expect(_product(tester, 0), isEmpty);
    expect(find.textContaining('Walk-in Customer'), findsWidgets);
    expect(tester.widget<TextField>(
            find.byKey(const ValueKey('counter-scan-field'))).focusNode!
        .hasFocus, isTrue);

    // The next customer is billed on a second invoice.
    await _scan(tester, '8900000000017');
    await tester.tap(find.byKey(const ValueKey('counter-save-print')));
    await tester.pumpAndSettle();
    expect(api.created, hasLength(2));
    expect(api.calls.last, 'print:SI-2');
  });

  testWidgets('a user who may not approve saves and prints only',
      (tester) async {
    final _CounterApi api = _CounterApi();
    await _pump(tester, api, mayApprove: false);
    await _chooseCustomer(tester);
    await _scan(tester, '8901234567890');

    await tester.sendKeyEvent(LogicalKeyboardKey.f9);
    await tester.pumpAndSettle();

    expect(api.calls, <String>['create', 'pdf:inv-1', 'print:SI-1']);
  });

  testWidgets('a refused approval shows the message and keeps the bill',
      (tester) async {
    final _CounterApi api =
        _CounterApi(approveRefusal: 'Stock is short for Soap.');
    final List<String> printed = await _pump(tester, api);
    await _chooseCustomer(tester);
    await _scan(tester, '8901234567890');

    await tester.sendKeyEvent(LogicalKeyboardKey.f9);
    await tester.pumpAndSettle();

    expect(api.calls, <String>['create', 'approve']);
    expect(printed, isEmpty);
    expect(find.textContaining('Stock is short for Soap.'), findsOneWidget);
    // Still the saved bill, not a blank one and not a second create.
    expect(api.created, hasLength(1));
    // The saved draft is what stays open, so another F9 mends it instead of
    // raising a second bill.
    expect(find.byKey(const ValueKey('sales-invoice-line-0')), findsOneWidget);
    expect(find.text('Soap'), findsWidgets);
  });

  testWidgets('the counter screen does not overflow at 1366x768 or 800x600',
      (tester) async {
    for (final Size size in const <Size>[Size(1366, 768), Size(800, 600)]) {
      final _CounterApi api = _CounterApi();
      // With the bill's own steps (D-BUY-22): Save & approve beside the
      // save buttons must still fit the narrowest window.
      final PermissionService approver = PermissionService()
        ..applyAccessToken(
          'header.${base64Url.encode(utf8.encode(jsonEncode({
                'roles': <String>['user'],
                'permissions': <String>['SALES_APPROVE', 'SALES_CANCEL'],
              }))).replaceAll('=', '')}.sig',
        );
      await _pump(
        tester,
        api,
        size: size,
        steps: salesInvoiceSteps(api, approver),
      );
      expect(
        find.byKey(const ValueKey('sales-invoice-save-approve')),
        findsOneWidget,
      );
      await _chooseCustomer(tester);
      await _scan(tester, '8901234567890');
      await _split(tester);
      await tester.tap(find.byKey(const ValueKey('tender-add')));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: '$size');
      await tester.pumpWidget(const SizedBox());
    }
  });
}
