// D-BUY-22: a goods receipt could not be completed from its own window. The
// phase 2 receipt editor offered only *Save receipt*; Complete -- which moves
// the stock and posts the ledger -- was a command on the list toolbar alone,
// so the owner saved two receipts, took them for completed, and both were
// drafts. Every document window now carries its own next steps through the
// shared strip, from the same definitions as the toolbar.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/ui/document_framework/document_steps.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_editor_dialog.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_steps.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_view_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

PurchaseOrder _order() => PurchaseOrder.fromJson({
      'id': 'po-1',
      'po_number': 'PO-2026-000001',
      'purchase_date': '2026-08-01',
      'warehouse_id': 'wh-1',
      'status': 'APPROVED',
      'lines': [
        {
          'id': 'po-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'description': 'Amoxicillin 500mg',
          'ordered_quantity': '10',
          'unit_price': '25',
        },
      ],
    });

GoodsReceiptRecord _draft({String status = 'DRAFT', int version = 1}) =>
    GoodsReceiptRecord.fromJson({
      'id': 'grn-9',
      'grn_number': 'GRN-9',
      'purchase_order_id': 'po-1',
      'purchase_order_number': 'PO-2026-000001',
      'status': status,
      'version': version,
      'lines': [
        {
          'id': 'grn-line-1',
          'purchase_order_line_id': 'po-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'current_receipt_quantity': '6',
        },
      ],
    });

class _Api extends ApiClient {
  _Api({this.refuseComplete = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool refuseComplete;
  final List<String> calls = <String>[];

  @override
  Future<PagedResult<GoodsReceiptRecord>> goodsReceipts({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> filters = const {},
  }) async =>
      const PagedResult<GoodsReceiptRecord>(items: [], total: 0);

  @override
  Future<GoodsReceiptRecord> createGoodsReceipt(Json data) async {
    calls.add('create');
    return _draft();
  }

  @override
  Future<GoodsReceiptRecord> updateGoodsReceipt(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    calls.add('update $id v$expectedVersion');
    return _draft(version: (expectedVersion ?? 1) + 1);
  }

  @override
  Future<GoodsReceiptRecord> completeGoodsReceipt(String id) async {
    calls.add('complete $id');
    if (refuseComplete) {
      throw const ApiException(
        'Batch B-1 has expired; it cannot be received.',
      );
    }
    return _draft(status: 'COMPLETED');
  }

  @override
  Future<GoodsReceiptRecord> cancelGoodsReceipt(
    String id, {
    String reason = '',
  }) async {
    calls.add('cancel $id');
    return _draft(status: 'CANCELLED');
  }

  // The licence check asks the server what the receipt needs; nothing.
  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async =>
      {'data': <String, dynamic>{}};
}

/// Open [window] the way a page does, keeping what it closed with.
Future<List<Object?>> _open(
  WidgetTester tester,
  Widget window, {
  Size size = const Size(1600, 900),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final List<Object?> closedWith = <Object?>[];
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: Builder(
          builder: (context) => TextButton(
            onPressed: () async {
              closedWith.add(await showDialog<Object>(
                context: context,
                builder: (_) => Phase2Scope(child: Dialog.fullscreen(
                  child: window,
                )),
              ));
            },
            child: const Text('open'),
          ),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  return closedWith;
}

GoodsReceiptEditorDialog _editor(
  _Api api,
  List<String> codes, {
  GoodsReceiptRecord? existing,
}) =>
    GoodsReceiptEditorDialog(
      api: api,
      purchaseOrders: [_order()],
      warehouses: [
        WarehouseRecord.fromJson({
          'id': 'wh-1',
          'code': 'MAIN',
          'name': 'Main Warehouse',
        }),
      ],
      products: [
        Product.fromJson({
          'id': 'prod-1',
          'code': 'SKU-1',
          'name': 'Amoxicillin 500mg',
        }),
      ],
      existing: existing,
      steps: goodsReceiptSteps(api, _permissions(codes)),
    );

Future<void> _pickOrder(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('goods-receipt-order')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('PO-2026-000001').last);
  await tester.pumpAndSettle();
}

const Key _saveComplete = ValueKey('goods-receipt-save-complete');

void main() {
  testWidgets('a receiver is offered Save & complete on a new receipt', (
    tester,
  ) async {
    final _Api api = _Api();
    await _open(tester, _editor(api, const ['PURCHASE_RECEIVE']));
    expect(find.byKey(_saveComplete), findsOneWidget);
    expect(find.text('Save & complete'), findsOneWidget);
  });

  testWidgets('saving is the coloured button, completing the outlined one', (
    tester,
  ) async {
    // The owner pressed the coloured button to save a draft and posted the
    // stock (D-UI-8): the button people press must only save.
    final _Api api = _Api();
    await _open(tester, _editor(api, const ['PURCHASE_RECEIVE']));
    expect(
      tester.widget(find.byKey(const ValueKey('goods-receipt-save'))),
      isA<FilledButton>(),
    );
    expect(tester.widget(find.byKey(_saveComplete)), isA<OutlinedButton>());
  });

  testWidgets('whoever cannot complete is not offered it', (tester) async {
    final _Api api = _Api();
    await _open(
      tester,
      _editor(api, const ['PURCHASE_VIEW', 'PURCHASE_APPROVE']),
    );
    expect(find.byKey(_saveComplete), findsNothing);
    expect(find.byKey(const ValueKey('goods-receipt-save')), findsOneWidget);
  });

  testWidgets('Save & complete saves, then completes what was saved', (
    tester,
  ) async {
    final _Api api = _Api();
    final List<Object?> closed =
        await _open(tester, _editor(api, const ['PURCHASE_RECEIVE']));
    await _pickOrder(tester);
    await tester.tap(find.byKey(_saveComplete));
    await tester.pumpAndSettle();

    expect(api.calls, ['create', 'complete grn-9']);
    expect(closed.single, isA<DocumentStepDone>());
    expect(
      (closed.single! as DocumentStepDone).message,
      contains('GRN-9 completed'),
    );
  });

  testWidgets('a refused completion keeps the window and the saved draft', (
    tester,
  ) async {
    final _Api api = _Api(refuseComplete: true);
    final List<Object?> closed =
        await _open(tester, _editor(api, const ['PURCHASE_RECEIVE']));
    await _pickOrder(tester);
    await tester.tap(find.byKey(_saveComplete));
    await tester.pumpAndSettle();

    expect(api.calls, ['create', 'complete grn-9']);
    // Still open, saying what was saved and why it did not complete.
    expect(closed, isEmpty);
    expect(find.textContaining('Saved as draft GRN-9'), findsOneWidget);
    expect(find.textContaining('Batch B-1 has expired'), findsOneWidget);

    // The next save corrects that draft rather than raising a second one.
    await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
    await tester.pumpAndSettle();
    expect(api.calls.last, 'update grn-9 v1');
    expect(closed.single, isA<GoodsReceiptRecord>());
  });

  testWidgets('a saved draft opened to edit offers Cancel under More', (
    tester,
  ) async {
    final _Api api = _Api();
    final List<Object?> closed = await _open(
      tester,
      _editor(
        api,
        const ['PURCHASE_RECEIVE', 'PURCHASE_CANCEL'],
        existing: _draft(),
      ),
    );
    expect(find.byKey(_saveComplete), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('document-steps-more')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('document-step-cancel')));
    await tester.pumpAndSettle();
    expect(api.calls, ['cancel grn-9']);
    expect(closed.single, isA<DocumentStepDone>());
  });

  // 1366x768, the smallest the shell supports, and the 800x600 test window:
  // there the line table scrolls sideways inside itself rather than running
  // off the window.
  testWidgets('the receipt window with its steps fits 1366x768 and 800x600', (
    tester,
  ) async {
    for (final Size size in const <Size>[Size(1366, 768), Size(800, 600)]) {
      final _Api api = _Api();
      await _open(
        tester,
        _editor(
          api,
          const ['PURCHASE_RECEIVE', 'PURCHASE_CANCEL', 'PURCHASE_APPROVE'],
          existing: _draft(),
        ),
        size: size,
      );
      expect(find.byKey(_saveComplete), findsOneWidget);
      expect(tester.takeException(), isNull, reason: '$size');
      await tester.pumpWidget(const SizedBox());
    }
  });

  testWidgets('the receipt view offers Complete on a draft to a receiver', (
    tester,
  ) async {
    final _Api api = _Api();
    final List<Object?> closed = await _open(
      tester,
      GoodsReceiptViewDialog(
        receipt: _draft(),
        history: const [],
        steps: goodsReceiptSteps(api, _permissions(const ['PURCHASE_RECEIVE'])),
      ),
    );
    await tester.tap(find.byKey(const ValueKey('document-step-complete')));
    await tester.pumpAndSettle();
    expect(api.calls, ['complete grn-9']);
    expect(closed.single, isA<DocumentStepDone>());
  });

  testWidgets('a reader sees no step on the receipt view', (tester) async {
    final _Api api = _Api();
    await _open(
      tester,
      GoodsReceiptViewDialog(
        receipt: _draft(),
        history: const [],
        steps: goodsReceiptSteps(api, _permissions(const ['PURCHASE_VIEW'])),
      ),
    );
    expect(find.byKey(const ValueKey('document-step-complete')), findsNothing);
    expect(find.byKey(const ValueKey('document-steps-more')), findsNothing);
  });

  testWidgets('a completed receipt is not offered Complete again', (
    tester,
  ) async {
    final _Api api = _Api();
    await _open(
      tester,
      GoodsReceiptViewDialog(
        receipt: _draft(status: 'COMPLETED'),
        history: const [],
        steps: goodsReceiptSteps(
          api,
          _permissions(const ['PURCHASE_RECEIVE', 'PURCHASE_CANCEL']),
        ),
      ),
    );
    expect(find.byKey(const ValueKey('document-step-complete')), findsNothing);
    expect(find.byKey(const ValueKey('document-steps-more')), findsOneWidget);
  });
}
