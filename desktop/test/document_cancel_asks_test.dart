import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/phase2/document_page.dart';
import 'package:agency_desktop/ui/delivery_notes/delivery_note_editor_dialog.dart';
import 'package:agency_desktop/ui/purchase_returns/purchase_return_editor_dialog.dart';
import 'package:agency_desktop/ui/sales/sales_order_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// D-UI-21 / D-UI-29: a document editor's own Cancel (and Esc) discarded what
/// was typed without a question, because it popped the route directly and
/// the tab's unsaved-work guard only hears `maybePop`. Cancel and Esc now go
/// through the same question as the tab's X, and close at once when nothing
/// was changed.
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

Json _order() => <String, dynamic>{
      'id': 'so-1',
      'order_number': 'SO-2026-000001',
      'order_date': '2026-08-01',
      'warehouse_id': 'wh-1',
      'status': 'APPROVED',
      'lines': <Json>[
        <String, dynamic>{
          'id': 'so-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'description': 'Amoxicillin 500mg',
          'quantity': '10',
          'reserved_quantity': '10',
          'unit_price': '40',
        },
      ],
    };

void main() {
  late DocumentTabsController tabs;

  Future<void> open(WidgetTester tester, WidgetBuilder editor) async {
    tabs = DocumentTabsController();
    addTearDown(tabs.dispose);
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: DocumentTabsScope(
          controller: tabs,
          child: AnimatedBuilder(
            animation: tabs,
            builder: (context, _) => Stack(children: [
              const Text('the list'),
              for (final OpenDocument document in tabs.documents)
                DocumentNavigator(
                  key: ValueKey(document.id),
                  document: document,
                ),
            ]),
          ),
        ),
      ),
    ));
    final BuildContext context = tester.element(find.text('the list'));
    showDocument<Object?>(
      context,
      title: 'Editor',
      builder: (context) => Phase2Scope(child: editor(context)),
    );
    await tester.pumpAndSettle();
    expect(tabs.documents, hasLength(1));
  }

  Future<void> expectAsks(
    WidgetTester tester,
    Future<void> Function() leave,
  ) async {
    await leave();
    await tester.pumpAndSettle();
    expect(find.text('Close without saving?'), findsOneWidget);
    expect(tabs.documents, hasLength(1), reason: 'nothing closed yet');
    await tester.tap(find.byKey(const ValueKey('document-keep-editing')));
    await tester.pumpAndSettle();
    expect(tabs.documents, hasLength(1));
    await leave();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('document-discard')));
    await tester.pumpAndSettle();
    expect(tabs.documents, isEmpty);
  }

  Future<void> cancel(WidgetTester tester) async {
    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
  }

  Future<void> esc(WidgetTester tester) async {
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
  }

  Future<void> closesAtOnce(WidgetTester tester) async {
    await cancel(tester);
    await tester.pumpAndSettle();
    expect(find.text('Close without saving?'), findsNothing);
    expect(tabs.documents, isEmpty);
  }

  group('sales order', () {
    Widget editor(BuildContext context) => SalesOrderEditorDialog(
          api: _Api(),
          today: DateTime(2026, 8, 14),
        );

    Future<void> chooseCustomer(WidgetTester tester) async {
      await tester.tap(find.byKey(const ValueKey('sales-order-customer')));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('Anand Agencies').last);
      await tester.pumpAndSettle();
    }

    testWidgets('Cancel asks when a customer was chosen', (tester) async {
      await open(tester, editor);
      await chooseCustomer(tester);
      await expectAsks(tester, () => cancel(tester));
    });

    testWidgets('Esc asks once something was typed', (tester) async {
      await open(tester, editor);
      // A plain text box: the customer picker keeps Esc for itself.
      final Finder box = find.descendant(
        of: find.widgetWithText(DocumentField, 'Our reference'),
        matching: find.byType(TextFormField),
      );
      await tester.tap(box);
      await tester.enterText(box, 'PO-7');
      await tester.pump();
      await expectAsks(tester, () => esc(tester));
    });

    testWidgets('Cancel closes at once when nothing was touched',
        (tester) async {
      await open(tester, editor);
      await closesAtOnce(tester);
    });
  });

  group('delivery note', () {
    Widget editor(BuildContext context) => DeliveryNoteEditorDialog(
          api: _Api(),
          salesOrders: [_order()],
          warehouses: [
            WarehouseRecord.fromJson(
              {'id': 'wh-1', 'code': 'MAIN', 'name': 'Main Warehouse'},
            ),
          ],
          products: [
            Product.fromJson(
              {'id': 'prod-1', 'code': 'SKU-1', 'name': 'Amoxicillin 500mg'},
            ),
          ],
        );

    Future<void> chooseOrder(WidgetTester tester) async {
      await tester.tap(find.byKey(const ValueKey('delivery-note-order')));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('SO-2026-000001').last);
      await tester.pumpAndSettle();
    }

    testWidgets('Cancel asks once an order was chosen', (tester) async {
      await open(tester, editor);
      await chooseOrder(tester);
      await expectAsks(tester, () => cancel(tester));
    });

    testWidgets('Esc asks once an order was chosen and a quantity typed',
        (tester) async {
      await open(tester, editor);
      await chooseOrder(tester);
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const ValueKey<String>('delivery-note-delivering-so-1-0')),
        '6',
      );
      await tester.pump();
      await expectAsks(tester, () => esc(tester));
    });

    testWidgets('Cancel closes at once when nothing was touched',
        (tester) async {
      await open(tester, editor);
      await closesAtOnce(tester);
    });
  });

  group('purchase return (a buying editor)', () {
    Widget editor(BuildContext context) => PurchaseReturnEditorDialog(
          api: _Api(),
          receipts: [
            GoodsReceiptRecord.fromJson({
              'id': 'grn-1',
              'grn_number': 'GRN-2026-000001',
              'receipt_date': '2026-08-10',
              'status': 'COMPLETED',
              'lines': <Json>[],
            }),
          ],
          products: const [],
        );

    Future<void> typeReason(WidgetTester tester) async {
      await tester.tap(find.byKey(const ValueKey('purchase-return-receipt')));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('GRN-2026-000001').last);
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextFormField).first, 'damaged');
      await tester.pump();
    }

    testWidgets('Cancel asks once a reason was typed', (tester) async {
      await open(tester, editor);
      await typeReason(tester);
      await expectAsks(tester, () => cancel(tester));
    });

    testWidgets('Esc asks once a reason was typed', (tester) async {
      await open(tester, editor);
      await typeReason(tester);
      await expectAsks(tester, () => esc(tester));
    });

    testWidgets('Cancel closes at once when nothing was touched',
        (tester) async {
      await open(tester, editor);
      await closesAtOnce(tester);
    });
  });
}
