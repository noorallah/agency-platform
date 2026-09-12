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
}
