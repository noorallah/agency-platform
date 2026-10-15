// A Draft supplier bill can be changed from the desktop (D-UI-39).
//
// A Draft offered Open, Approve, Cancel and Record IRN and no Edit, so a
// wrong quantity could only be put right by cancelling the bill and typing
// it again -- while `PUT /api/v1/purchase-invoices/{id}` had been there all
// along. That route replaces the bill with what it is sent, so these pin
// both halves: the bill window opens holding the draft, and what it sends
// back loses nothing the draft held and overrides nothing nobody typed.
//
// The bill every test edits is the server's own answer, kept in
// `test/fixtures/server_pricing`: ten at 100.00 less 10%, with a charge of
// 50.00 on the line, 1,121.00 in all.

import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/access_token.dart';
import 'support/server_pricing.dart';

const String _number = 'PI-CHAIN-BR-CHAIN-2026-2027-000001';

/// The draft as `GET /purchase-invoices/{id}` answers it: the server's own
/// pricing, with the header fields the bill window has no box for.
Json _draft([Json changes = const {}]) => {
      ...serverPricing('purchase_invoice_preview')['invoice'] as Json,
      'payment_terms': 'Net 30',
      'due_date': '2026-09-03',
      'reference_number': 'REF-9',
      'notes': [
        {'id': 'note-1', 'note_type': 'INTERNAL', 'note': 'Check the freight'},
      ],
      ...changes,
    };

/// The receipt the draft bills: ten at 100.00, received at 10% off, which
/// is where the bill line's discount comes from.
Json _receipt({
  String status = 'COMPLETED',
  String unitPrice = '100',
  String discountPercent = '10',
  String free = '0',
}) =>
    {
      'id': 'id-7',
      'grn_number': 'GRN-0007',
      'receipt_date': '2026-08-03',
      'status': status,
      'vendor_id': 'id-4',
      'vendor_name': 'Vendor',
      'branch_id': 'id-5',
      'purchase_order_id': 'po-1',
      'purchase_order_number': 'PO-0001',
      'left_to_bill_quantity': '10',
      'lines': [
        {
          'id': 'id-8',
          'line_number': 1,
          'product_id': 'id-9',
          'description': 'Product',
          'accepted_quantity': '10',
          'free_quantity': free,
          'unit_price': unitPrice,
          'discount_percent': discountPercent,
          'discount_amount': discountPercent == '0' ? '0' : '100',
          'gross_amount': '1000',
          'purchase_uom_id': 'uom-box',
          'warehouse_id': 'wh-1',
          'tax_profile_id': 'id-10',
        },
      ],
    };

final Product _product = Product.fromJson({
  'id': 'id-9',
  'code': 'SKU-1',
  'name': 'Amoxicillin 500mg',
  'purchase_price': '100',
  'itc_eligibility': 'ELIGIBLE',
});

const PurchaseWorkflowSettings _direct = PurchaseWorkflowSettings(
  purchaseOrderStage: false,
  goodsReceiptStage: false,
  isConfigured: true,
);

const PurchaseWorkflowSettings _ordersOnly = PurchaseWorkflowSettings(
  purchaseOrderStage: true,
  goodsReceiptStage: false,
  isConfigured: true,
);

/// The server, as far as the bill list and the bill window ask it.
class _Api extends ApiClient {
  _Api({Json? bill, Json? receipt, this.order, this.refusal})
      : bill = bill ?? _draft(),
        receipt = receipt ?? _receipt(),
        super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json bill;
  final Json receipt;

  /// The order behind the receipt, as `GET /purchases/{id}` answers it.
  final Json? order;

  /// What the server answers the save with, when it refuses.
  final ApiException? refusal;

  /// An approved bill listed beside the draft.
  static const Json approved = {
    'id': 'pi-2',
    'invoice_number': 'PI-0002',
    'invoice_date': '2026-08-02',
    'supplier_invoice_number': 'S-2',
    'status': 'APPROVED',
    'grand_total': '590.00',
    'lines': <Json>[],
  };

  Json? sent;
  int? sentVersion;
  String? sentTo;
  int listReads = 0;
  final List<Json> previews = <Json>[];

  /// The path each preview went to: a draft being edited is priced as
  /// replacing itself, at `/purchase-invoices/{id}/preview` (D-UI-99).
  final List<String> previewPaths = <String>[];

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
    final String tail = path.replaceFirst('/api/v1', '');
    if (method == 'PUT' && tail.startsWith('/purchase-invoices/')) {
      sent = body;
      sentVersion = expectedVersion;
      sentTo = tail;
      final ApiException? refused = refusal;
      if (refused != null) throw refused;
      return {
        'data': {...bill, 'version': 3},
      };
    }
    if (tail.startsWith('/purchase-invoices/') && tail.endsWith('/preview')) {
      previews.add(body!);
      previewPaths.add(tail);
      return {'data': serverPricing('purchase_invoice_preview')};
    }
    if (tail == '/purchase-invoices/summary') {
      return {'data': <String, dynamic>{}};
    }
    if (tail == '/purchase-invoices') {
      listReads += 1;
      return {
        'data': [bill, approved],
        'pagination': {'total_records': 2},
      };
    }
    if (tail == '/purchase-invoices/${bill['id']}') return {'data': bill};
    if (tail == '/goods-receipts') {
      return {
        'data': [receipt],
        'pagination': {'total_records': 1},
      };
    }
    if (tail == '/goods-receipts/id-7') return {'data': receipt};
    if (tail == '/purchases/po-1' && order != null) return {'data': order};
    if (tail == '/products') {
      return {
        'data': [
          {'id': 'id-9', 'code': 'SKU-1', 'name': 'Amoxicillin 500mg'},
        ],
        'pagination': {'total_records': 1},
      };
    }
    return {
      'data': const <Json>[],
      'pagination': {'total_records': 0},
    };
  }
}

/// The bill list in the phase 2 layout, with the named row clicked.
Future<void> _openList(
  WidgetTester tester,
  _Api api,
  List<String> codes, {
  String select = _number,
  Size? window = const Size(1600, 1100),
}) async {
  if (window != null) {
    tester.view.physicalSize = window;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
  }
  final Directory temp = Directory.systemTemp.createTempSync('bill-edit');
  addTearDown(() => temp.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    // Above the navigator, as in the app, so a window the list opens is in
    // the phase 2 layout too.
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: PurchaseInvoiceManagementPage(
        api: api,
        preferences: DesktopPreferencesService(directory: temp),
        permissions: PermissionService()
          ..applyAccessToken(accessTokenFor(codes)),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.text(select).first);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

/// The bill window on its own, holding the draft.
Future<void> _openWindow(
  WidgetTester tester,
  _Api api, {
  PurchaseWorkflowSettings stages = PurchaseWorkflowSettings.wholeChain,
  bool listed = true,
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseInvoiceEditorDialog(
          api: api,
          // A receipt the bill raised itself is a draft, so the list of
          // receipts waiting to be billed does not hold it.
          receipts: [if (listed) GoodsReceiptRecord.fromJson(api.receipt)],
          products: [_product],
          stages: stages,
          existing: api.bill,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Finder _key(String key) => find.byKey(ValueKey<String>(key));

Finder get _save => _key('purchase-invoice-save');

Future<void> _type(WidgetTester tester, String key, String text) async {
  await tester.enterText(_key(key), text);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _pressSave(WidgetTester tester) async {
  await tester.tap(_save);
  await tester.pumpAndSettle();
}

Json _line(_Api api) => (api.sent!['lines'] as List<dynamic>).single as Json;

/// The fields one request model declares, read from the server's own
/// schema file: it forbids unknown keys, so one stray key fails the save.
Set<String> _declared(String model) {
  final String source = File(
    '../backend/app/purchase_invoice/schemas/purchase_invoice.py',
  ).readAsStringSync().replaceAll('\r\n', '\n');
  final int start = source.indexOf('class $model(');
  expect(start, isNonNegative, reason: '$model is in the schema file');
  final int end = source.indexOf('\nclass ', start + 1);
  return {
    for (final RegExpMatch field in RegExp(r'^    (\w+): ', multiLine: true)
        .allMatches(source.substring(start, end < 0 ? source.length : end)))
      field.group(1)!,
  };
}

void _expectDeclared(Json sent) {
  expect(
    sent.keys.toSet().difference(_declared('PurchaseInvoiceCreate')),
    isEmpty,
    reason: 'every key of the bill is one PurchaseInvoiceCreate declares',
  );
  for (final dynamic line in sent['lines'] as List<dynamic>) {
    expect(
      (line as Json)
          .keys
          .toSet()
          .difference(_declared('PurchaseInvoiceLineWrite')),
      isEmpty,
      reason: 'every key of a line is one PurchaseInvoiceLineWrite declares',
    );
  }
}

void main() {
  group('the bill list', () {
    testWidgets('offers Edit on a Draft and not on an approved bill', (
      tester,
    ) async {
      final _Api api = _Api();
      await _openList(tester, api, const ['PURCHASE_VIEW', 'PURCHASE_UPDATE']);
      expect(_key('selection-edit'), findsOneWidget);

      await tester.tap(find.text('PI-0002').first);
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();
      expect(_key('selection-edit'), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('does not offer Edit without PURCHASE_UPDATE', (tester) async {
      final _Api api = _Api();
      await _openList(tester, api, const [
        'PURCHASE_VIEW',
        'PURCHASE_CREATE',
        'PURCHASE_APPROVE',
      ]);
      expect(_key('selection-edit'), findsNothing);
      expect(_key('toolbar-edit'), findsNothing);
    });

    testWidgets('stays inside an 800x600 window with Edit offered', (
      tester,
    ) async {
      final _Api api = _Api();
      await _openList(
        tester,
        api,
        const [
          'PURCHASE_VIEW',
          'PURCHASE_CREATE',
          'PURCHASE_UPDATE',
          'PURCHASE_APPROVE',
          'PURCHASE_CANCEL',
        ],
        window: null,
      );
      expect(_key('selection-edit'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('Edit opens the draft, saves it with a PUT and reloads', (
      tester,
    ) async {
      final _Api api = _Api();
      await _openList(tester, api, const ['PURCHASE_VIEW', 'PURCHASE_UPDATE']);
      await tester.tap(_key('selection-edit'));
      await tester.pumpAndSettle();

      // The band says it is editing, under the bill's own number.
      expect(find.text('Edit purchase invoice'), findsOneWidget);
      expect(
        tester.widget<Text>(_key('document-number')).data,
        _number,
      );
      expect(
        tester
            .widget<TextFormField>(_key('purchase-invoice-billing-id-7-0'))
            .initialValue,
        '10',
      );

      final int before = api.listReads;
      await _type(tester, 'purchase-invoice-billing-id-7-0', '8');
      await _pressSave(tester);

      expect(api.sentTo, '/purchase-invoices/id-2');
      // The version the bill was read at, so a stale save is refused.
      expect(api.sentVersion, 2);
      expect(_line(api)['current_invoice_quantity'], '8');
      // Closed, and the list read again.
      expect(find.text('Edit purchase invoice'), findsNothing);
      expect(api.listReads, greaterThan(before));
      expect(find.textContaining('saved'), findsWidgets);
      expect(tester.takeException(), isNull);
    });
  });

  group('a bill of goods receipts', () {
    testWidgets('opens holding the draft, with the figures the server saved', (
      tester,
    ) async {
      final _Api api = _Api();
      await _openWindow(tester, api);

      expect(find.text('Edit purchase invoice'), findsOneWidget);
      expect(find.text('against GRN-0007'), findsOneWidget);
      expect(find.text('Vendor'), findsWidgets);
      expect(
        tester
            .widget<TextFormField>(
              _key('purchase-invoice-supplier-number-0'),
            )
            .initialValue,
        'S-1',
      );
      // Its own quantity is not "billed by another bill": the list of
      // bills holds this draft, and the whole receipt is still its own.
      final Finder row = _key('purchase-invoice-line-0');
      expect(
        tester
            .widget<TextFormField>(_key('purchase-invoice-billing-id-7-0'))
            .initialValue,
        '10',
      );
      expect(
        find.descendant(of: row, matching: find.text('0')),
        findsOneWidget,
        reason: 'nothing billed by another bill',
      );
      // No rate in the box: the bill charges the receipt's price.
      expect(
        tester
            .widget<TextFormField>(_key('purchase-invoice-rate-id-7-0'))
            .initialValue,
        '',
      );
      // The saved bill's own figures, never a pricing of a new bill.
      expectLinesReconcile(tester,
          document: api.bill, rowKey: 'purchase-invoice-line-');
      expect(api.previews, isEmpty);
      expect(tester.takeException(), isNull);
    });

    testWidgets('saved unchanged, sends the bill back as it was', (
      tester,
    ) async {
      final _Api api = _Api();
      await _openWindow(tester, api);
      await _pressSave(tester);

      final Json sent = api.sent!;
      _expectDeclared(sent);
      // The bill's own dates and number, not today's.
      expect(sent['invoice_date'], '2026-08-04');
      expect(sent['supplier_invoice_date'], '2026-08-04');
      expect(sent['supplier_invoice_number'], 'S-1');
      expect(sent['source_documents'], [
        {'source_document_type': 'GOODS_RECEIPT', 'source_document_id': 'id-7'},
      ]);
      // What the window has no box for, which the server would clear.
      expect(sent['payment_terms'], 'Net 30');
      expect(sent['due_date'], '2026-09-03');
      expect(sent['reference_number'], 'REF-9');
      expect(sent['notes'], [
        {'note_type': 'INTERNAL', 'note': 'Check the freight'},
      ]);
      // Absent keeps: TCS, the currency and the firm's own fields.
      expect(sent.containsKey('tcs_rate_percent'), isFalse);
      expect(sent.containsKey('tcs_amount'), isFalse);
      expect(sent.containsKey('currency_code'), isFalse);
      expect(sent.containsKey('attributes'), isFalse);
      // The receipt's supplier and branch are the bill's.
      expect(sent.containsKey('vendor_id'), isFalse);
      expect(sent.containsKey('branch_id'), isFalse);

      final Json line = _line(api);
      expect(line['source_document_type'], 'GOODS_RECEIPT');
      expect(line['source_document_id'], 'id-7');
      expect(line['source_document_line_id'], 'id-8');
      expect(line['current_invoice_quantity'], '10');
      // The price and the 10% are the receipt line's. Nobody typed them, so
      // neither is sent: sent, each would become an override.
      expect(line.containsKey('unit_price'), isFalse);
      expect(line.containsKey('discount_percent'), isFalse);
      expect(line.containsKey('discount_amount'), isFalse);
      expect(line.containsKey('itc_eligibility'), isFalse);
      // The charge on the line has no box, and is sent back as held.
      expect(line['charges_amount'], '50.0000');
    });

    testWidgets('a changed quantity is sent with what the bill held', (
      tester,
    ) async {
      final _Api api = _Api();
      await _openWindow(tester, api);
      await _type(tester, 'purchase-invoice-billing-id-7-0', '6');

      // Priced again as it is typed, as replacing the draft (D-UI-99), and
      // nothing says the figures wait for the save any more.
      expect(api.previews, isNotEmpty);
      expect(_key('purchase-invoice-totals-owed'), findsNothing);
      expect(find.textContaining('worked out when the bill is saved'),
          findsNothing);

      await _pressSave(tester);
      final Json sent = api.sent!;
      _expectDeclared(sent);
      expect(_line(api)['current_invoice_quantity'], '6');
      expect(sent['payment_terms'], 'Net 30');
      expect(sent['reference_number'], 'REF-9');
      expect(_line(api).containsKey('discount_percent'), isFalse);
      expect(_line(api).containsKey('discount_amount'), isFalse);
      expect(_line(api)['charges_amount'], '50.0000');
    });

    testWidgets('a changed draft is priced as replacing itself', (
      tester,
    ) async {
      final _Api api = _Api();
      await _openWindow(tester, api);
      await _type(tester, 'purchase-invoice-billing-id-7-0', '6');

      // D-UI-99: the draft's own quantity and bill number do not count
      // against it, so the preview names it.
      expect(api.previewPaths, isNotEmpty);
      expect(
        api.previewPaths,
        everyElement('/purchase-invoices/${api.bill['id']}/preview'),
      );
      expect(api.previews.last['lines'], isNotEmpty);
    });

    testWidgets('a rate somebody typed is back in its box', (tester) async {
      // Received at 110.00 and billed at 100.00: the bill's price is not
      // the receipt's, so somebody typed it.
      final _Api api = _Api(receipt: _receipt(unitPrice: '110'));
      await _openWindow(tester, api);
      expect(
        tester
            .widget<TextFormField>(_key('purchase-invoice-rate-id-7-0'))
            .initialValue,
        '100',
      );
      await _pressSave(tester);
      expect(_line(api)['unit_price'], '100');
    });

    testWidgets('a discount typed by another route is sent back', (
      tester,
    ) async {
      // The receipt line gives no discount, so the bill line's 10% is not
      // inherited from it: left out, saving would take it off.
      final _Api api = _Api(receipt: _receipt(discountPercent: '0'));
      await _openWindow(tester, api);
      await _pressSave(tester);
      expect(_line(api)['discount_percent'], '10');
      _expectDeclared(api.sent!);
    });

    testWidgets('a bill moved to another day takes its due date again', (
      tester,
    ) async {
      final _Api api = _Api();
      await _openWindow(tester, api);
      await tester.tap(_key('purchase-invoice-date'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('20'));
      await tester.tap(find.text('OK'));
      await tester.pumpAndSettle();
      await _pressSave(tester);

      expect(api.sent!['invoice_date'], '2026-08-20');
      expect(api.sent!.containsKey('due_date'), isFalse);
      expect(api.sent!['payment_terms'], 'Net 30');
    });

    testWidgets('TCS is sent only once its boxes are touched', (tester) async {
      final _Api api = _Api(
        bill: _draft({'tcs_rate_percent': '0.1000', 'tcs_amount': '1.12'}),
      );
      await _openWindow(tester, api);
      expect(
        tester
            .widget<TextFormField>(_key('purchase-invoice-tcs-rate'))
            .initialValue,
        '0.1',
      );
      // 0.1% of 1,121.00 is the 1.12 on file: the rate gave it, so the
      // amount box is blank and follows the total.
      expect(
        tester
            .widget<TextFormField>(_key('purchase-invoice-tcs-amount'))
            .initialValue,
        '',
      );

      await _type(tester, 'purchase-invoice-tcs-rate', '');
      await _pressSave(tester);
      // Blanked, so cleared: absent would have kept it.
      expect(api.sent!.containsKey('tcs_rate_percent'), isTrue);
      expect(api.sent!['tcs_rate_percent'], isNull);
      expect(api.sent!['tcs_amount'], isNull);
    });

    testWidgets("a refusal keeps the window open with the server's sentence", (
      tester,
    ) async {
      final _Api api = _Api(
        refusal: const ApiException(
          'This record was changed by someone else. Reload it and try again.',
          statusCode: 409,
        ),
      );
      await _openWindow(tester, api);
      await _type(tester, 'purchase-invoice-billing-id-7-0', '7');
      await _pressSave(tester);

      expect(api.sent, isNotNull);
      expect(find.textContaining('changed by someone else'), findsOneWidget);
      expect(find.text('Edit purchase invoice'), findsOneWidget);
      // What was typed is still there to save again.
      expect(find.text('7'), findsWidgets);
      expect(_save, findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a line typed in another unit is not opened as boxes', (
      tester,
    ) async {
      final Json bill = _draft();
      final Json line = {
        ...(bill['lines'] as List<dynamic>).single as Json,
        'entered_quantity': '120.0000',
      };
      final _Api api = _Api(bill: {...bill, 'lines': [line]});
      await _openWindow(tester, api);

      expect(_key('purchase-invoice-edit-block'), findsOneWidget);
      expect(find.textContaining('typed in another unit'), findsOneWidget);
      expect(tester.widget<FilledButton>(_save).onPressed, isNull);
    });
  });

  group('a bill of products', () {
    // The firm types neither orders nor receipts, and the order behind the
    // bill's own draft receipt carries the bill's number and date: the bill
    // raised both, so its lines go back as products.
    const Json raisedOrder = {
      'id': 'po-1',
      'po_number': 'PO-0001',
      'vendor_id': 'id-4',
      'purchase_date': '2026-08-04',
      'reference_number': 'S-1',
      'status': 'APPROVED',
      'lines': <Json>[],
    };

    testWidgets('opens with what was typed back in its boxes', (tester) async {
      final _Api api = _Api(
        receipt: _receipt(status: 'DRAFT', free: '1.0000'),
        order: raisedOrder,
      );
      await _openWindow(tester, api, stages: _direct, listed: false);

      expect(find.text('Edit purchase invoice'), findsOneWidget);
      String box(String name) => tester
          .widget<TextFormField>(_key('purchase-invoice-$name-direct-0'))
          .initialValue!;
      expect(box('direct-quantity'), '10');
      expect(box('direct-free'), '1');
      // Blank would take the product's price as it is today.
      expect(box('direct-rate'), '100');
      // Nothing is inherited on a bill of products: its 10% was typed.
      expect(box('direct-discount'), '10');
      expectLinesReconcile(tester,
          document: api.bill, rowKey: 'purchase-invoice-direct-');
      expect(api.previews, isEmpty);
      expect(tester.takeException(), isNull);
    });

    testWidgets('sends product lines again, never the receipt it raised', (
      tester,
    ) async {
      final _Api api = _Api(
        receipt: _receipt(status: 'DRAFT', free: '1.0000'),
        order: raisedOrder,
      );
      await _openWindow(tester, api, stages: _direct, listed: false);
      await _type(tester, 'purchase-invoice-direct-quantity-direct-0', '12');
      // A bill of products is priced again as it is typed, as replacing
      // the draft (D-UI-99).
      expect(api.previews, isNotEmpty);
      expect(
        api.previewPaths,
        everyElement('/purchase-invoices/${api.bill['id']}/preview'),
      );
      await _pressSave(tester);

      final Json sent = api.sent!;
      _expectDeclared(sent);
      expect(api.sentVersion, 2);
      expect(sent['vendor_id'], 'id-4');
      expect(sent['branch_id'], 'id-5');
      expect(sent.containsKey('source_documents'), isFalse);
      expect(sent['payment_terms'], 'Net 30');
      expect(sent['reference_number'], 'REF-9');
      final Json line = _line(api);
      expect(line['product_id'], 'id-9');
      expect(line['current_invoice_quantity'], '12');
      expect(line['free_quantity'], '1');
      expect(line['unit_price'], '100');
      expect(line['discount_percent'], '10');
      expect(line['charges_amount'], '50.0000');
      // Naming the receipt line would keep the order and receipt as they
      // were; the server raises them again only for lines that name none.
      expect(line.containsKey('source_document_type'), isFalse);
      expect(line.containsKey('source_document_id'), isFalse);
      expect(line.containsKey('source_document_line_id'), isFalse);
    });

    testWidgets('the mode is read off the bill, not the firm\'s stages', (
      tester,
    ) async {
      // The firm types neither stage today, but this bill's receipt was
      // raised against an order somebody typed: its reference is their own.
      // Sent as products, that order would be left open and another raised.
      final _Api api = _Api(
        receipt: _receipt(status: 'DRAFT'),
        order: {...raisedOrder, 'reference_number': 'OUR-REF-1'},
      );
      await _openWindow(tester, api, stages: _direct, listed: false);
      await _pressSave(tester);

      expect(api.sent!.containsKey('source_documents'), isTrue);
      expect(_line(api)['source_document_line_id'], 'id-8');
      expect(_line(api).containsKey('product_id'), isFalse);
    });
  });

  group('a bill that received its own goods against an order', () {
    testWidgets('its quantity, batch and expiry can be changed', (
      tester,
    ) async {
      // D-UI-100: saving withdraws the draft receipt the bill raised and
      // raises it again from what the bill says, so nothing is locked.
      final _Api api = _Api(receipt: _receipt(status: 'DRAFT'));
      await _openWindow(tester, api, stages: _ordersOnly, listed: false);

      expect(find.text('against PO-0001'), findsOneWidget);
      expect(find.textContaining('cannot yet'), findsNothing);
      expect(
        tester
            .widget<TextField>(find.descendant(
              of: _key('purchase-invoice-billing-id-7-0'),
              matching: find.byType(TextField),
            ))
            .readOnly,
        isFalse,
      );
      expect(_key('purchase-invoice-batch-id-7-0'), findsOneWidget);
      expect(_key('purchase-invoice-expiry-id-7-0'), findsOneWidget);

      await _type(tester, 'purchase-invoice-billing-id-7-0', '8');
      await _type(tester, 'purchase-invoice-batch-id-7-0', 'B-NEW');
      // Priced as replacing the draft, its receipt included (D-UI-99).
      expect(
        api.previewPaths,
        everyElement('/purchase-invoices/${api.bill['id']}/preview'),
      );
      await _type(tester, 'purchase-invoice-rate-id-7-0', '98');
      await _pressSave(tester);
      final Json sent = api.sent!;
      _expectDeclared(sent);
      // The receipt the bill raised, which the server lets it name: an
      // order line here is refused.
      expect(sent['source_documents'], [
        {'source_document_type': 'GOODS_RECEIPT', 'source_document_id': 'id-7'},
      ]);
      expect(_line(api)['source_document_type'], 'GOODS_RECEIPT');
      expect(_line(api)['current_invoice_quantity'], '8');
      expect(_line(api)['batch_number'], 'B-NEW');
      expect(_line(api)['unit_price'], '98');
      expect(sent['payment_terms'], 'Net 30');
    });
  });
}
