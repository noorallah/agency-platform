import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/inventory/stock_action_dialog.dart';
import 'package:flutter_test/flutter_test.dart';

/// Moving, condemning and holding stock.
///
/// The endpoints existed and nothing in the client could reach them: a firm
/// could transfer stock between warehouses only by calling the API by hand.
void main() {
  group('what is refused before the server sees it', () {
    test('more than the location holds', () {
      expect(
        validateStockAction(
          action: StockAction.writeOff,
          quantity: '50',
          available: 10,
          reference: 'WO-1',
        ),
        contains('holds 10.0000'),
      );
    });

    test('a transfer to where the stock already is', () {
      expect(
        validateStockAction(
          action: StockAction.transfer,
          quantity: '5',
          available: 10,
          reference: 'TRF-1',
          destinationWarehouseId: 'w-1',
          sourceWarehouseId: 'w-1',
        ),
        contains('somewhere else'),
      );
    });

    test('a transfer with nowhere to go', () {
      expect(
        validateStockAction(
          action: StockAction.transfer,
          quantity: '5',
          available: 10,
          reference: 'TRF-1',
          destinationWarehouseId: '',
          sourceWarehouseId: 'w-1',
        ),
        contains('going to'),
      );
    });

    test('no reference, because the movement has to be findable later', () {
      expect(
        validateStockAction(
          action: StockAction.writeOff,
          quantity: '5',
          available: 10,
          reference: '',
        ),
        contains('reference'),
      );
    });

    test('a quantity of nothing', () {
      expect(
        validateStockAction(
          action: StockAction.writeOff,
          quantity: '',
          available: 10,
          reference: 'WO-1',
        ),
        contains('how much'),
      );
    });

    test('exactly what is there passes', () {
      // Writing off the last of something is normal, and a rounding-shy
      // comparison would refuse it.
      expect(
        validateStockAction(
          action: StockAction.writeOff,
          quantity: '10',
          available: 10,
          reference: 'WO-1',
        ),
        isNull,
      );
    });
  });

  group('building the request', () {
    test('a transfer names the warehouse it leaves', () {
      // The transfer endpoint takes from_warehouse_id; the other two take
      // warehouse_id, because only one of them moves stock between places.
      final Json body = stockActionBody(
        action: StockAction.transfer,
        draft: const {'quantity': '5', 'to_warehouse_id': 'w-2'},
        branchId: 'b-1',
        warehouseId: 'w-1',
        productId: 'p-1',
      );
      expect(body['from_warehouse_id'], 'w-1');
      expect(body.containsKey('warehouse_id'), isFalse);
      expect(body['to_warehouse_id'], 'w-2');
    });

    test('a write-off names the warehouse it is in', () {
      final Json body = stockActionBody(
        action: StockAction.writeOff,
        draft: const {'quantity': '5', 'reason': 'EXPIRY'},
        branchId: 'b-1',
        warehouseId: 'w-1',
        productId: 'p-1',
      );
      expect(body['warehouse_id'], 'w-1');
      expect(body['reason'], 'EXPIRY');
    });

    test('the batch is carried when the row has one', () {
      // So a batch stays traceable through the move, which is the point of
      // batch tracking for anyone answering a recall.
      final Json body = stockActionBody(
        action: StockAction.transfer,
        draft: const {'quantity': '5', 'to_warehouse_id': 'w-2'},
        branchId: 'b-1',
        warehouseId: 'w-1',
        productId: 'p-1',
        batchId: 'batch-9',
      );
      expect(body['batch_id'], 'batch-9');
    });

    test('an empty batch is left out rather than sent as blank', () {
      final Json body = stockActionBody(
        action: StockAction.writeOff,
        draft: const {'quantity': '5', 'reason': 'DAMAGE'},
        branchId: 'b-1',
        warehouseId: 'w-1',
        productId: 'p-1',
        batchId: '',
      );
      expect(body.containsKey('batch_id'), isFalse);
    });
  });
}
