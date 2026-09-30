import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/ui/inventory/stock_action_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The transfer dialog names its destinations the way every other warehouse
/// picker does: code first. Found on the 2026-09-12 manual pass (plan item
/// 8.3): the plan said "Move it to WHL_DC" and the list offered only
/// "Bulk Goods Warehouse1", the name the tester had edited earlier, so the
/// warehouse could not be recognised. The pure validator and body builder
/// had tests; the dialog itself had none, which is how a name-only list
/// shipped.
void main() {
  testWidgets('a transfer destination reads as code and name, source excluded',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: StockActionDialog(
            action: StockAction.transfer,
            productLabel: 'Detergent Powder 1kg',
            warehouseLabel: 'North Warehouse',
            sourceWarehouseId: 'wh-north',
            available: 12,
            quarantined: 0,
            warehouses: [
              WarehouseOption(
                id: 'wh-north',
                code: 'WH_NORTH',
                name: 'North Warehouse',
              ),
              WarehouseOption(
                id: 'wh-dc',
                code: 'WHL_DC',
                name: 'Bulk Goods Warehouse1',
              ),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Move it to'));
    await tester.pumpAndSettle();

    expect(find.text('WHL_DC - Bulk Goods Warehouse1'), findsWidgets);
    // The warehouse the stock is leaving is not somewhere it can go.
    expect(find.text('WH_NORTH - North Warehouse'), findsNothing);
    expect(find.text('Bulk Goods Warehouse1'), findsNothing);
  });

  testWidgets('a refusal is shown in a banner with the error icon',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: StockActionDialog(
            action: StockAction.transfer,
            productLabel: 'Detergent Powder 1kg',
            warehouseLabel: 'North Warehouse',
            sourceWarehouseId: 'wh-north',
            available: 4,
            quarantined: 0,
            warehouses: [
              WarehouseOption(id: 'wh-dc', code: 'WHL_DC', name: 'Bulk'),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Quantity'), '10');
    await tester.enterText(
        find.widgetWithText(TextField, 'Reference (optional)'), 'TRF-1');
    await tester.tap(find.text('Move it to'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('WHL_DC - Bulk').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Transfer'));
    await tester.pumpAndSettle();

    final Finder banner = find.widgetWithText(
      MaterialBanner,
      'This location holds 4.0000, so 10.0000 cannot be moved out of it.',
    );
    expect(banner, findsOneWidget);
    expect(
      find.descendant(of: banner, matching: find.byIcon(Icons.error_outline)),
      findsOneWidget,
    );
  });

  testWidgets('a refused stock action stays open with what was typed',
      (tester) async {
    // D-DLG-1: the dialog used to close on Save and the page made the call.
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    int calls = 0;
    Map<String, dynamic>? sent;
    Object? result;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () async => result = await showDialog<Object>(
              context: context,
              builder: (context) => Dialog(
                child: StockActionDialog(
                  action: StockAction.writeOff,
                  productLabel: 'Detergent Powder 1kg',
                  warehouseLabel: 'North Warehouse',
                  sourceWarehouseId: 'wh-north',
                  available: 12,
                  quarantined: 0,
                  warehouses: const [],
                  onSave: (Map<String, dynamic> values) async {
                    calls++;
                    if (calls == 1) {
                      throw const ApiException('The period is closed.');
                    }
                    sent = values;
                  },
                ),
              ),
            ),
            child: const Text('open'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Quantity'), '5');
    await tester.enterText(find.widgetWithText(TextField, 'Remarks'), 'cracked');
    await tester.tap(find.text('Write off'));
    await tester.pumpAndSettle();

    expect(find.byType(StockActionDialog), findsOneWidget);
    expect(find.text('The period is closed.'), findsOneWidget);
    expect(find.text('5'), findsOneWidget);
    expect(find.text('cracked'), findsOneWidget);
    expect(sent, isNull);

    await tester.tap(find.text('Write off'));
    await tester.pumpAndSettle();
    expect(find.byType(StockActionDialog), findsNothing);
    expect(sent!['quantity'], '5');
    expect(result, isNotNull);
  });
}
