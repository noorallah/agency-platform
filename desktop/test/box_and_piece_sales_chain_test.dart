// L5 step 10, sales side: boxes and pieces on the delivery note, the sales
// return and the sales bill's rows billed from delivery notes
// (BOX_AND_PIECE_LINE_DESIGN section 4, "Continuing documents"). The
// editable quantity becomes the two boxes; Ordered, Delivered, Sent and Left
// to bill read "3 x 12 + 5". No new server call: the switch and the
// customer's mark ride on reads each editor already makes.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/inventory.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/sales_invoice.dart';
import 'package:agency_desktop/models/sales_return.dart';
import 'package:agency_desktop/ui/delivery_notes/delivery_note_editor_dialog.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/sales_returns/sales_return_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _customerRow({required bool marked}) => <String, dynamic>{
      'id': 'c1',
      'code': 'C1',
      'name': 'Box Mart',
      'display_name': 'Box Mart',
      'customer_type': 'BUSINESS',
      'status': 'ACTIVE',
      'box_and_piece_entry': marked,
      'addresses': const <Json>[],
    };

EditableText _cell(WidgetTester tester, String key) =>
    tester.widget<EditableText>(find.descendant(
      of: find.byKey(ValueKey<String>(key)),
      matching: find.byType(EditableText),
    ));

String _text(WidgetTester tester, String key) =>
    tester.widget<Text>(find.byKey(ValueKey<String>(key))).data ?? '';

Json _line(Json body, int index) =>
    (body['lines'] as List<dynamic>)[index] as Json;

// ---------------------------------------------------------------------------
// Delivery note
// ---------------------------------------------------------------------------

/// An approved order: 82 shampoo in boxes of 12 with 30 reserved (41 went
/// out on an earlier note), and 7 rice, which has no pack.
Json _order() => <String, dynamic>{
      'id': 'so-1',
      'order_number': 'SO-2026-000001',
      'order_date': '2026-08-01',
      'customer_id': 'c1',
      'warehouse_id': 'wh-1',
      'status': 'APPROVED',
      'lines': <Json>[
        <String, dynamic>{
          'id': 'so-line-1',
          'line_number': 1,
          'product_id': 'p1',
          'description': 'Shampoo 180ml',
          'quantity': '82',
          'reserved_quantity': '30',
          'unit_price': '10',
          'warehouse_id': 'wh-1',
          'pack_size': '12.0000',
        },
        <String, dynamic>{
          'id': 'so-line-2',
          'line_number': 2,
          'product_id': 'p2',
          'description': 'Rice 5kg',
          'quantity': '7',
          'reserved_quantity': '7',
          'unit_price': '250',
          'warehouse_id': 'wh-1',
        },
      ],
    };

class _NoteApi extends ApiClient {
  _NoteApi({required this.boxSwitch, required this.marked})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool boxSwitch;
  final bool marked;
  Json? sent;

  @override
  Future<SalesWorkflowSettings> salesWorkflowSettings() async =>
      SalesWorkflowSettings.fromJson(<String, dynamic>{
        'quotation_stage': true,
        'sales_order_stage': true,
        'delivery_note_stage': true,
        'is_configured': true,
        'box_and_piece_entry': boxSwitch,
      });

  @override
  Future<Customer> customer(String id) async =>
      Customer.fromJson(_customerRow(marked: marked));

  /// One earlier note took 41 shampoo off the order.
  @override
  Future<Json> documentPage(
    String resource, {
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> additionalQuery = const {},
  }) async =>
      <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'status': 'DISPATCHED',
            'lines': <Json>[
              <String, dynamic>{
                'sales_order_line_id': 'so-line-1',
                'current_delivery_quantity': '41',
              },
            ],
          },
        ],
      };

  @override
  Future<PagedResult<InventoryRecord>> inventory({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    InventoryQuery filters = const InventoryQuery(),
  }) async =>
      const PagedResult<InventoryRecord>(items: [], total: 0);

  @override
  Future<Json> create(String resource, Json body) async {
    sent = body;
    return <String, dynamic>{
      'data': <String, dynamic>{
        'id': 'dn-1',
        'delivery_note_number': 'DN-1',
        'status': 'DRAFT',
      },
    };
  }
}

Future<void> _openNote(
  WidgetTester tester,
  _NoteApi api, {
  Size size = const Size(1600, 1000),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: DeliveryNoteEditorDialog(
          api: api,
          salesOrders: [_order()],
          warehouses: [
            WarehouseRecord.fromJson(<String, dynamic>{
              'id': 'wh-1',
              'code': 'MAIN',
              'name': 'Main Warehouse',
            }),
          ],
          products: [
            Product.fromJson(<String, dynamic>{
              'id': 'p1',
              'code': 'P1',
              'name': 'Shampoo 180ml',
              'pack_size': '12.0000',
            }),
            Product.fromJson(<String, dynamic>{
              'id': 'p2',
              'code': 'P2',
              'name': 'Rice 5kg',
            }),
          ],
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('delivery-note-order')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('SO-2026-000001').last);
  await tester.pumpAndSettle();
}

// ---------------------------------------------------------------------------
// Sales bill of delivery notes
// ---------------------------------------------------------------------------

Json _billableNote({String? packSize}) => <String, dynamic>{
      'sales_order_number': 'SO-1',
      'source_document_type': 'DELIVERY_NOTE',
      'source_document_id': 'dn-1',
      'source_document_number': 'DN-000001',
      'document_date': '2026-08-04',
      'customer_id': 'c1',
      'customer_name': 'Box Mart',
      'branch_id': 'branch-1',
      'lines': <Json>[
        <String, dynamic>{
          'source_document_line_id': 'dn-1-l1',
          'line_number': 1,
          'product_id': 'p1',
          'description': 'Shampoo 180ml',
          'source_quantity': '41',
          'already_invoiced_quantity': '0',
          'remaining_quantity': '41',
          'unit_price': '10',
          'discount_percent': '0',
          'free_quantity': '0',
          if (packSize != null) 'pack_size': packSize,
        },
      ],
    };

class _BillApi extends ApiClient {
  _BillApi({
    required this.boxSwitch,
    this.marked = false,
    this.billable = const <Json>[],
  }) : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool boxSwitch;
  final bool marked;
  final List<Json> billable;
  Json? existing;
  Json? created;
  Json? updated;

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
          'quotation_stage': true,
          'sales_order_stage': true,
          'delivery_note_stage': true,
          'is_configured': true,
          'box_and_piece_entry': boxSwitch,
        },
      };
    }
    if (path.contains('billable')) {
      return <String, dynamic>{'data': billable};
    }
    if (method == 'GET' && path == '/api/v1/customers/c1') {
      return <String, dynamic>{'data': _customerRow(marked: marked)};
    }
    if (method == 'POST' && path == '/api/v1/sales-invoices/preview') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'interstate': false,
          'invoice': <String, dynamic>{
            'subtotal': '0',
            'tax_total': '0',
            'grand_total': '0',
            'lines': const <Json>[],
          },
          'lines': const <Json>[],
        },
      };
    }
    if (method == 'GET' && path.startsWith('/api/v1/sales-invoices/')) {
      return <String, dynamic>{'data': existing};
    }
    if (method == 'PUT' && path.startsWith('/api/v1/sales-invoices/')) {
      updated = body;
      return <String, dynamic>{'data': existing};
    }
    if (method == 'POST' && path.endsWith('/sales-invoices')) {
      created = body;
      return <String, dynamic>{
        'data': <String, dynamic>{'id': 'inv-1', 'invoice_number': 'SI-1'},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

Future<void> _openBill(
  WidgetTester tester,
  _BillApi api, {
  String? invoiceId,
  Size size = const Size(1600, 1000),
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
          invoiceId: invoiceId,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _chooseBillCustomer(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('sales-invoice-bill-customer')));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Box Mart').last);
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

/// A draft bill of one note line: 41 shampoo billed at boxes of 12.
Json _savedBill({required bool inBoxes}) => <String, dynamic>{
      'id': 'inv-1',
      'invoice_number': 'SI-1',
      'invoice_date': '2026-08-10',
      'customer_id': 'c1',
      'customer_name': 'Box Mart',
      'branch_id': 'branch-1',
      'status': 'DRAFT',
      'version': 3,
      'bill_discount_percent': '0',
      'box_and_piece_entry': inBoxes,
      'lines': <Json>[
        <String, dynamic>{
          'source_document_type': 'DELIVERY_NOTE',
          'source_document_id': 'dn-1',
          'source_document_number': 'DN-000001',
          'source_document_line_id': 'dn-1-l1',
          'line_number': 1,
          'product_id': 'p1',
          'description': 'Shampoo 180ml',
          'current_invoice_quantity': '41.0000',
          'unit_price': '10',
          'discount_percent': '0',
          'pack_uom_id': 'u-box',
          'pack_size': '12.0000',
        },
      ],
    };

// ---------------------------------------------------------------------------
// Sales return
// ---------------------------------------------------------------------------

/// A dispatched note: 41 shampoo in boxes of 12 with 2 free, and 7 rice,
/// which has no pack.
ReturnableDocument _returnable({required bool inBoxes}) =>
    ReturnableDocument.fromDeliveryNote(<String, dynamic>{
      'id': 'dn-1',
      'delivery_note_number': 'DN-2026-000001',
      'delivery_date': '2026-08-10',
      'customer_name': 'Box Mart',
      'status': 'DISPATCHED',
      'box_and_piece_entry': inBoxes,
      'lines': <Json>[
        <String, dynamic>{
          'id': 'dn-line-1',
          'line_number': 1,
          'product_id': 'p1',
          'product_name': 'Shampoo 180ml',
          'current_delivery_quantity': '41',
          'free_quantity': '2',
          'unit_price': '10',
          'pack_size': '12.0000',
        },
        <String, dynamic>{
          'id': 'dn-line-2',
          'line_number': 2,
          'product_id': 'p2',
          'product_name': 'Rice 5kg',
          'current_delivery_quantity': '7',
          'unit_price': '250',
        },
      ],
    });

Future<void> _openReturn(
  WidgetTester tester,
  List<Json?> saved, {
  required ReturnableDocument document,
  SalesReturn? editing,
  Size size = const Size(1600, 1000),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () async {
            saved.add(await Navigator.of(context).push<Json>(
              MaterialPageRoute<Json>(
                builder: (_) => Scaffold(
                  body: Phase2Scope(
                    child: SalesReturnEditorDialog(
                      documents: [document],
                      warehouses: [
                        WarehouseRecord.fromJson(<String, dynamic>{
                          'id': 'wh-1',
                          'code': 'MAIN',
                          'name': 'Main',
                          'is_default': true,
                        }),
                      ],
                      today: DateTime(2026, 8, 20),
                      editing: editing,
                    ),
                  ),
                ),
              ),
            ));
          },
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  if (editing == null) {
    await tester.tap(find.byKey(const ValueKey('sales-return-document')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('DN-2026-000001').last);
    await tester.pumpAndSettle();
  }
}

void main() {
  group('L5 step 10: the delivery note', () {
    testWidgets(
        'a marked customer with the switch on opens in boxes; Ordered and '
        'Delivered read as boxes; 3 boxes + 5 pcs sends 41 and the pack',
        (tester) async {
      final _NoteApi api = _NoteApi(boxSwitch: true, marked: true);
      await _openNote(tester, api);
      expect(find.byKey(const ValueKey('delivery-note-box-and-pieces')),
          findsOneWidget);
      expect(find.text('Free pcs'), findsOneWidget);
      expect(_text(tester, 'delivery-note-ordered-0'), '6 x 12 + 10');
      expect(_text(tester, 'delivery-note-delivered-0'), '3 x 12 + 5');
      // Starts at what is reserved, 30: 2 boxes and 6.
      expect(_cell(tester, 'delivery-note-line-0-box').controller.text, '2');
      expect(_cell(tester, 'delivery-note-line-0-pcs').controller.text, '6');
      // Rice has no pack: its box cells are closed.
      expect(find.byKey(const ValueKey('delivery-note-line-1-box-closed')),
          findsOneWidget);
      expect(
          find.byKey(const ValueKey('delivery-note-line-1-free-box-closed')),
          findsOneWidget);

      await tester.enterText(
          find.byKey(const ValueKey('delivery-note-line-0-box')), '3');
      await tester.pump();
      await tester.enterText(
          find.byKey(const ValueKey('delivery-note-line-0-pcs')), '5');
      await tester.pump();
      expect(find.byKey(const ValueKey('delivery-note-side-boxes')),
          findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('delivery-note-save')));
      await tester.pumpAndSettle();

      final Json sent = api.sent!;
      expect(sent['box_and_piece_entry'], isTrue);
      expect(_line(sent, 0)['current_delivery_quantity'], '41');
      expect(_line(sent, 0)['pack_size'], '12.0000');
      // Blank free cells say nothing: the order's free goods stand.
      expect(_line(sent, 0).containsKey('free_quantity'), isFalse);
      expect(_line(sent, 1)['current_delivery_quantity'], '7');
      expect(_line(sent, 1).containsKey('pack_size'), isFalse);
    });

    testWidgets(
        'an unmarked customer starts in pieces; the toggle changes the '
        'layout and no quantity', (tester) async {
      final _NoteApi api = _NoteApi(boxSwitch: true, marked: false);
      await _openNote(tester, api);
      expect(find.byKey(const ValueKey('delivery-note-box-and-pieces')),
          findsOneWidget);
      expect(find.text('Free pcs'), findsNothing);
      expect(find.text('Delivering'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('box-piece-toggle-on')));
      await tester.pumpAndSettle();
      expect(_cell(tester, 'delivery-note-line-0-box').controller.text, '2');
      expect(_cell(tester, 'delivery-note-line-0-pcs').controller.text, '6');
      await tester.tap(find.byKey(const ValueKey('box-piece-toggle-off')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('delivery-note-save')));
      await tester.pumpAndSettle();
      expect(api.sent!['box_and_piece_entry'], isFalse);
      expect(_line(api.sent!, 0)['current_delivery_quantity'], '30');
      expect(_line(api.sent!, 0).containsKey('pack_size'), isFalse);
    });

    testWidgets('with the switch off there is no toggle and nothing is said',
        (tester) async {
      final _NoteApi api = _NoteApi(boxSwitch: false, marked: true);
      await _openNote(tester, api);
      expect(find.byKey(const ValueKey('delivery-note-box-and-pieces')),
          findsNothing);
      expect(find.text('Free pcs'), findsNothing);
      await tester.tap(find.byKey(const ValueKey('delivery-note-save')));
      await tester.pumpAndSettle();
      expect(api.sent!.containsKey('box_and_piece_entry'), isFalse);
    });

    testWidgets('at 800x600 the boxes-and-pieces note draws without overflow',
        (tester) async {
      final _NoteApi api = _NoteApi(boxSwitch: true, marked: true);
      await _openNote(tester, api, size: const Size(800, 600));
      expect(tester.takeException(), isNull);
      expect(find.byKey(const ValueKey('delivery-note-box-and-pieces')),
          findsOneWidget);
    });
  });

  group('L5 step 10: the sales return', () {
    testWidgets(
        'a return against a note typed in boxes opens in boxes; Sent reads '
        'as boxes; 3 boxes + 5 pcs sends 41 and the pack', (tester) async {
      final List<Json?> saved = <Json?>[];
      await _openReturn(tester, saved,
          document: _returnable(inBoxes: true));
      expect(find.byKey(const ValueKey('sales-return-box-and-pieces')),
          findsOneWidget);
      expect(_text(tester, 'sales-return-sent-0'), '3 x 12 + 5');
      // Rice has no pack and sent nothing free.
      expect(find.byKey(const ValueKey('sales-return-line-1-box-closed')),
          findsOneWidget);
      expect(find.byKey(const ValueKey('sales-return-line-1-free-pcs')),
          findsNothing);

      await tester.enterText(
          find.byKey(const ValueKey('sales-return-line-0-box')), '3');
      await tester.pump();
      await tester.enterText(
          find.byKey(const ValueKey('sales-return-line-0-pcs')), '5');
      await tester.pump();
      expect(find.byKey(const ValueKey('sales-return-side-boxes')),
          findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('sales-return-save')));
      await tester.pumpAndSettle();

      final Json sent = saved.single!;
      expect(sent['box_and_piece_entry'], isTrue);
      final Json line = (sent['lines'] as List<dynamic>).single as Json;
      expect(line['current_return_quantity'], '41');
      expect(line['pack_size'], '12.0000');
      // Blank free cells say nothing: the charged units come back first.
      expect(line.containsKey('free_quantity'), isFalse);
    });

    testWidgets('a return against a note in pieces opens in pieces',
        (tester) async {
      final List<Json?> saved = <Json?>[];
      await _openReturn(tester, saved,
          document: _returnable(inBoxes: false));
      expect(find.byKey(const ValueKey('sales-return-box-and-pieces')),
          findsNothing);
      expect(find.text('Returning'), findsOneWidget);
      expect(_text(tester, 'sales-return-sent-0'), '41');
    });

    testWidgets('a saved return reopens as it was saved', (tester) async {
      final SalesReturn draft = SalesReturn.fromJson(<String, dynamic>{
        'id': 'ret-1',
        'customer_id': 'c1',
        'warehouse_id': 'wh-1',
        'return_number': 'SR-1',
        'return_date': '2026-08-15',
        'status': 'DRAFT',
        'version': 2,
        'box_and_piece_entry': true,
        'lines': <Json>[
          <String, dynamic>{
            'id': 'r-line-1',
            'line_number': 1,
            'source_document_type': 'DELIVERY_NOTE',
            'source_document_id': 'dn-1',
            'source_document_line_id': 'dn-line-1',
            'product_id': 'p1',
            'current_return_quantity': '17.0000',
            'free_quantity': '0',
            'damaged_quantity': '0',
            'scrap_quantity': '0',
            'unit_price': '10',
            'pack_size': '12.0000',
          },
        ],
      });
      final List<Json?> saved = <Json?>[];
      await _openReturn(tester, saved,
          document: _returnable(inBoxes: false), editing: draft);
      expect(find.byKey(const ValueKey('sales-return-box-and-pieces')),
          findsOneWidget);
      expect(_cell(tester, 'sales-return-line-0-box').controller.text, '1');
      expect(_cell(tester, 'sales-return-line-0-pcs').controller.text, '5');
      await tester.tap(find.byKey(const ValueKey('sales-return-save')));
      await tester.pumpAndSettle();
      final Json sent = saved.single!;
      expect(sent['box_and_piece_entry'], isTrue);
      final Json line = (sent['lines'] as List<dynamic>).single as Json;
      expect(line['current_return_quantity'], '17');
      expect(line['pack_size'], '12.0000');
    });

    testWidgets('at 800x600 the boxes-and-pieces return draws without '
        'overflow', (tester) async {
      await _openReturn(tester, <Json?>[],
          document: _returnable(inBoxes: true), size: const Size(800, 600));
      expect(tester.takeException(), isNull);
      expect(find.byKey(const ValueKey('sales-return-box-and-pieces')),
          findsOneWidget);
    });
  });

  group('L5 step 10: the sales bill of delivery notes', () {
    testWidgets(
        'a saved bill reopens in boxes; Left to bill reads as boxes; the '
        'boxes typed send pieces and the pack', (tester) async {
      final _BillApi api = _BillApi(boxSwitch: true)
        ..existing = _savedBill(inBoxes: true);
      await _openBill(tester, api, invoiceId: 'inv-1');
      expect(find.byKey(const ValueKey('sales-invoice-note-box-and-pieces')),
          findsOneWidget);
      expect(_text(tester, 'sales-invoice-line-left-0'), '3 x 12 + 5');
      expect(_cell(tester, 'sales-invoice-line-0-box').controller.text, '3');
      expect(_cell(tester, 'sales-invoice-line-0-pcs').controller.text, '5');
      // A note line has no free cell of its own.
      expect(find.byKey(const ValueKey('sales-invoice-line-0-free-pcs')),
          findsNothing);

      await tester.enterText(
          find.byKey(const ValueKey('sales-invoice-line-0-box')), '2');
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
      await tester.pumpAndSettle();
      final Json sent = api.updated!;
      expect(sent['box_and_piece_entry'], isTrue);
      expect(_line(sent, 0)['current_invoice_quantity'], '29');
      expect(_line(sent, 0)['pack_size'], '12.0000');
    });

    testWidgets('a saved bill in pieces reopens in pieces and sends no pack',
        (tester) async {
      final _BillApi api = _BillApi(boxSwitch: true)
        ..existing = _savedBill(inBoxes: false);
      await _openBill(tester, api, invoiceId: 'inv-1');
      expect(find.text('Bill qty'), findsOneWidget);
      expect(_text(tester, 'sales-invoice-line-left-0'), '41');
      await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
      await tester.pumpAndSettle();
      expect(api.updated!['box_and_piece_entry'], isFalse);
      expect(_line(api.updated!, 0).containsKey('pack_size'), isFalse);
    });

    testWidgets(
        'a new bill takes the note line\'s pack: the cells split it and the '
        'pack is sent', (tester) async {
      final _BillApi api = _BillApi(
        boxSwitch: true,
        marked: true,
        billable: <Json>[_billableNote(packSize: '12.0000')],
      );
      await _openBill(tester, api);
      await _chooseBillCustomer(tester);
      expect(_text(tester, 'sales-invoice-line-left-0'), '3 x 12 + 5');
      expect(_cell(tester, 'sales-invoice-line-0-box').controller.text, '3');
      expect(_cell(tester, 'sales-invoice-line-0-pcs').controller.text, '5');
      await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
      await tester.pumpAndSettle();
      expect(api.created!['box_and_piece_entry'], isTrue);
      expect(_line(api.created!, 0)['current_invoice_quantity'], '41');
      expect(_line(api.created!, 0)['pack_size'], '12.0000');
    });

    testWidgets(
        'a new bill follows its customer\'s mark; a note line with no pack '
        'has closed box cells and the pieces are sent alone', (tester) async {
      final _BillApi api = _BillApi(
        boxSwitch: true,
        marked: true,
        billable: <Json>[_billableNote()],
      );
      await _openBill(tester, api);
      await _chooseBillCustomer(tester);
      expect(find.byKey(const ValueKey('sales-invoice-note-box-and-pieces')),
          findsOneWidget);
      expect(find.byKey(const ValueKey('sales-invoice-line-0-box-closed')),
          findsOneWidget);
      expect(_cell(tester, 'sales-invoice-line-0-pcs').controller.text, '41');
      await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
      await tester.pumpAndSettle();
      expect(api.created!['box_and_piece_entry'], isTrue);
      expect(_line(api.created!, 0)['current_invoice_quantity'], '41');
      expect(_line(api.created!, 0).containsKey('pack_size'), isFalse);
    });

    testWidgets('an unmarked customer\'s new bill starts in pieces',
        (tester) async {
      final _BillApi api = _BillApi(
        boxSwitch: true,
        billable: <Json>[_billableNote()],
      );
      await _openBill(tester, api);
      await _chooseBillCustomer(tester);
      expect(find.byKey(const ValueKey('sales-invoice-note-box-and-pieces')),
          findsOneWidget);
      expect(find.text('Bill qty'), findsOneWidget);
    });

    testWidgets('at 800x600 the boxes-and-pieces bill draws without overflow',
        (tester) async {
      final _BillApi api = _BillApi(boxSwitch: true)
        ..existing = _savedBill(inBoxes: true);
      await _openBill(tester, api,
          invoiceId: 'inv-1', size: const Size(800, 600));
      expect(tester.takeException(), isNull);
      expect(find.byKey(const ValueKey('sales-invoice-line-0')),
          findsOneWidget);
    });
  });
}
