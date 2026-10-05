// Purchase order amendment (BUY-8): an approved or received order is changed
// through Amend, which asks why and posts to /amend with the order's body --
// not a PUT -- and keeps what the order said before as a revision.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/document_preview.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/purchases/purchase_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _orderJson({int revision = 0, String status = 'APPROVED'}) => {
      'id': 'po-1',
      'firm_id': 'firm-1',
      'branch_id': 'branch-1',
      'warehouse_id': 'warehouse-1',
      'vendor_id': 'vendor-1',
      'po_number': 'PO-0001',
      'purchase_date': '2026-10-01',
      'status': status,
      'revision_number': revision,
      'grand_total': '500.00',
      'lines': [
        {
          'id': 'line-1',
          'line_number': 1,
          'product_id': 'product-1',
          'ordered_quantity': '5',
          'free_quantity': '0',
          'unit_price': '100',
          'discount_percent': '0',
          'net_amount': '500.00',
        },
      ],
    };

class _Api extends ApiClient {
  _Api({this.refuse = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool refuse;
  PurchaseOrder? amended;
  String? reason;
  bool updated = false;

  @override
  Future<PurchaseOrderPreviewRecord> previewPurchaseOrder(
    PurchaseOrder order,
  ) async =>
      PurchaseOrderPreviewRecord(
        order: order,
        interstate: false,
        lines: const <DocumentPreviewLine>[],
      );

  @override
  Future<PurchaseOrder> amendPurchaseOrder(
    PurchaseOrder order,
    String reason,
  ) async {
    if (refuse) {
      throw const ApiException('Raising the total needs approval rights.');
    }
    amended = order;
    this.reason = reason;
    return order.copyWith(id: 'po-1');
  }

  @override
  Future<List<PurchaseOrderHistoryRecord>> purchaseOrderHistory(
    String id,
  ) async =>
      const <PurchaseOrderHistoryRecord>[];

  @override
  Future<PurchaseOrder> updatePurchaseOrder(PurchaseOrder order) async {
    updated = true;
    return order;
  }

  @override
  Future<List<PurchaseOrderRevision>> purchaseOrderRevisions(
    String id,
  ) async =>
      [
        PurchaseOrderRevision.fromJson({
          'id': 'rev-1',
          'revision_number': 1,
          'grand_total': '400.00',
          'reason': 'Quantity cut',
          'amended_at': '2026-10-02T09:00:00Z',
          'snapshot': {
            'lines': [
              {
                'line_number': 1,
                'description': 'Pain Relief earlier',
                'ordered_quantity': '4',
                'unit_price': '100',
                'net_amount': '400.00',
              },
            ],
          },
        }),
      ];
}

Future<void> _pump(
  WidgetTester tester,
  _Api api, {
  required PurchaseDialogMode mode,
  int revision = 0,
  String status = 'APPROVED',
  Size size = const Size(1600, 900),
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
          order: PurchaseOrder.fromJson(
            _orderJson(revision: revision, status: status),
          ),
          vendors: <Vendor>[
            Vendor.fromJson(<String, dynamic>{
              'id': 'vendor-1',
              'firm_id': 'firm-1',
              'code': 'V001',
              'name': 'Northwind Supplies',
              'display_name': 'Northwind Supplies',
              'status': 'ACTIVE',
              'addresses': <Json>[],
              'contacts': <Json>[],
              'bank_accounts': <Json>[],
              'tax_details': <Json>[],
              'notes': <Json>[],
            }),
          ],
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

Future<void> _saveWithReason(WidgetTester tester, String reason) async {
  await tester.tap(find.byKey(const ValueKey('purchase-order-save')));
  await tester.pumpAndSettle();
  await tester.enterText(find.byType(TextField).last, reason);
  await tester.tap(find.widgetWithText(FilledButton, 'Amend'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('amending asks why and posts to amend, not update',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api,
        mode: PurchaseDialogMode.amend, status: 'RECEIVED');
    expect(find.text('Save amendment'), findsOneWidget);

    await _saveWithReason(tester, 'Supplier cut the quantity');

    expect(api.updated, isFalse);
    expect(api.reason, 'Supplier cut the quantity');
    expect(api.amended?.lines.single.productId, 'product-1');
    expect(tester.takeException(), isNull);
  });

  testWidgets('a refusal keeps the editor open with the message',
      (tester) async {
    final _Api api = _Api(refuse: true);
    await _pump(tester, api, mode: PurchaseDialogMode.amend);

    await _saveWithReason(tester, 'Raise the price');

    expect(find.text('Raising the total needs approval rights.'),
        findsOneWidget);
    expect(find.byKey(const ValueKey('purchase-order-save')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  // D-UI-11: the section strip ran 112px past the right edge of a window
  // 800 wide, in every mode. 1366x768 is the smallest screen supported.
  for (final PurchaseDialogMode mode in <PurchaseDialogMode>[
    PurchaseDialogMode.view,
    PurchaseDialogMode.amend,
  ]) {
    for (final Size size in const <Size>[Size(800, 900), Size(1366, 768)]) {
      testWidgets(
          'the editor fits a ${size.width.toInt()}x${size.height.toInt()} '
          'window (${mode.name})', (tester) async {
        await _pump(tester, _Api(), mode: mode, revision: 1, size: size);
        expect(tester.takeException(), isNull);
      });
    }
  }

  testWidgets('an amended order says which amendment it is', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, mode: PurchaseDialogMode.view, revision: 1);
    expect(find.text('Amendment 1'), findsOneWidget);
    expect(PurchaseOrder.fromJson(_orderJson(revision: 2)).numberLabel,
        'PO-0001 (Amendment 2)');
    expect(PurchaseOrder.fromJson(_orderJson()).numberLabel, 'PO-0001');
  });

  testWidgets('the revisions list shows a version and its lines',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, mode: PurchaseDialogMode.view, revision: 1);
    await tester.tap(find.byKey(const ValueKey('purchase-order-section-4')));
    await tester.pumpAndSettle();

    expect(find.textContaining('Version 1'), findsOneWidget);
    expect(find.textContaining('Quantity cut'), findsOneWidget);

    await tester.tap(
      find.byKey(const ValueKey('purchase-order-revision-rev-1')),
    );
    await tester.pumpAndSettle();
    expect(find.text('Pain Relief earlier'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
