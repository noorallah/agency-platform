import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/sales_order_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

// D-UI-62: Esc on a drop-down picker whose list is closed reaches the editor.
//
// A DropdownMenu's anchor turned Esc into a dismissal whether or not its list
// was open, so the key stopped there and the editor did not ask to close
// until the focus was elsewhere. With the list open Esc still closes the list.
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

void main() {
  late DocumentTabsController tabs;

  Future<void> open(WidgetTester tester) async {
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
      builder: (context) => Phase2Scope(
        child: SalesOrderEditorDialog(
          api: _Api(),
          today: DateTime(2026, 8, 14),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tabs.documents, hasLength(1));
  }

  Future<void> esc(WidgetTester tester) async {
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
  }

  // A customer chosen (so the order is touched), then the picker holds the
  // focus with its list closed.
  Future<void> pickedAndFocused(WidgetTester tester) async {
    await tester.tap(find.byKey(const ValueKey('sales-order-customer')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Anand Agencies').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('sales-order-customer')));
    await tester.pumpAndSettle();
    // Close the list without touching the focus.
    await tester.tap(find.byKey(const ValueKey('sales-order-customer')));
    await tester.pumpAndSettle();
  }

  testWidgets('Esc on a picker whose list is closed asks to close',
      (tester) async {
    await open(tester);
    await pickedAndFocused(tester);
    await esc(tester);
    expect(find.text('Close without saving?'), findsOneWidget);
  });

  testWidgets('Esc with the list open closes the list, the next Esc asks',
      (tester) async {
    await open(tester);
    await tester.tap(find.byKey(const ValueKey('sales-order-customer')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Anand Agencies').last);
    await tester.pumpAndSettle();
    // Open the list again.
    await tester.tap(find.byIcon(Icons.arrow_drop_down).first);
    await tester.pumpAndSettle();
    expect(find.textContaining('Anand Agencies'), findsWidgets);
    await esc(tester);
    expect(find.text('Close without saving?'), findsNothing);
    expect(tabs.documents, hasLength(1));
    await esc(tester);
    expect(find.text('Close without saving?'), findsOneWidget);
  });
}
