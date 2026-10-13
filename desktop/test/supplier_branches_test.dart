// A supplier company is one main-office supplier with a supplier record per
// branch under it (backlog 127). A branch keeps its own GST number or takes its main office's.
//
// What the screens owe: a "Branch of" field that sends only
// `parent_vendor_id`, a Branches panel fed by one family call (and none for
// a supplier on its own), a "Received from" choice on a goods receipt only
// for a supplier company, and a payment to a main office that lists its
// branches' bills.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/settlement.dart';
import 'package:agency_desktop/models/settlement_direction.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/finance/record_settlement_dialog.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_editor_dialog.dart';
import 'package:agency_desktop/ui/vendors/vendor_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['VENDOR_VIEW', 'VENDOR_CREATE', 'VENDOR_UPDATE'],
  }));

Json _vendorJson({
  String id = 'v-1',
  String code = 'V001',
  String name = 'Supplier One',
  String? parentId,
  String? parentCode,
  String? parentName,
  int branches = 0,
  String gstin = '',
  bool gstinFromParent = false,
}) =>
    <String, dynamic>{
      'gstin': gstin,
      'gstin_from_parent': gstinFromParent,
      'id': id,
      'firm_id': 'firm-1',
      'code': code,
      'name': name,
      'display_name': name,
      'status': 'ACTIVE',
      'addresses': <dynamic>[],
      'contacts': <dynamic>[],
      'parent_vendor_id': parentId,
      'parent_code': parentCode,
      'parent_name': parentName,
      'branch_count': branches,
    };

final VendorFamily _family = VendorFamily.fromJson(<String, dynamic>{
  'parent_id': 'v-main',
  'members': <Json>[
    <String, dynamic>{
      'id': 'v-main',
      'code': 'HQ',
      'name': 'Sundaram Pharma',
      'is_parent': true,
      'gstin': '33AAAAA0000A1Z5',
      'status': 'ACTIVE',
      'place': null,
      'balance': '100.00',
    },
    <String, dynamic>{
      'id': 'v-blr',
      'code': 'HQ-BLR',
      'name': 'Sundaram Pharma Bengaluru',
      'is_parent': false,
      'gstin': '29AAAAA0000A1Z5',
      'status': 'ACTIVE',
      'place': 'Indiranagar, Bengaluru',
      'balance': '-20.50',
    },
  ],
  'total_balance': '79.50',
});

// The same company when the Bengaluru branch left its GSTIN blank and the
// server copied the main office's onto it.
final VendorFamily _takingFamily = VendorFamily.fromJson(<String, dynamic>{
  'parent_id': 'v-main',
  'members': <Json>[
    <String, dynamic>{
      'id': 'v-main',
      'code': 'HQ',
      'name': 'Sundaram Pharma',
      'is_parent': true,
      'gstin': '33AAAAA0000A1Z5',
      'gstin_from_parent': false,
      'status': 'ACTIVE',
      'balance': '100.00',
    },
    <String, dynamic>{
      'id': 'v-blr',
      'code': 'HQ-BLR',
      'name': 'Sundaram Pharma Bengaluru',
      'is_parent': false,
      'gstin': '33AAAAA0000A1Z5',
      'gstin_from_parent': true,
      'status': 'ACTIVE',
      'balance': '0.00',
    },
  ],
  'total_balance': '100.00',
});

class _VendorApi extends ApiClient {
  _VendorApi({this.rows = const <Json>[], this.family})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;
  final VendorFamily? family;
  Json? saved;
  final List<String> familyCalls = <String>[];

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async =>
      PagedResult<Vendor>(
        items: <Vendor>[for (final Json row in rows) Vendor.fromJson(row)],
        total: rows.length,
      );

  @override
  Future<VendorFamily> vendorFamily(String id) async {
    familyCalls.add(id);
    return family ?? _family;
  }

  @override
  Future<Vendor> createVendor(Json data) async {
    saved = data;
    return Vendor.fromJson(_vendorJson());
  }

  @override
  Future<Vendor> updateVendor(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    saved = data;
    return Vendor.fromJson(_vendorJson());
  }
}

Future<void> _pumpVendors(WidgetTester tester, _VendorApi api) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: VendorManagementPage(
        api: api,
        permissions: _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _editRow(WidgetTester tester, String code) async {
  await tester.tap(find.text(code).first);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
  await tester.tap(find.byTooltip('Edit').first);
  await tester.pumpAndSettle();
}

Future<void> _save(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('vendor-save')));
  await tester.pumpAndSettle();
}

// ---- Record Payment ----------------------------------------------------

class _PayApi extends ApiClient {
  _PayApi(this.bills)
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<OutstandingInvoice> bills;
  final List<({SettlementDirection direction, bool withBranches})> asked = [];
  Json? recorded;

  @override
  Future<List<OutstandingInvoice>> outstandingInvoices({
    required SettlementDirection direction,
    required String partyId,
    bool withShops = false,
    bool withBranches = false,
  }) async {
    asked.add((direction: direction, withBranches: withBranches));
    return bills;
  }

  @override
  Future<Settlement> recordSettlement({
    required SettlementDirection direction,
    required Json data,
  }) async {
    recorded = data;
    return Settlement.fromJson({
      'id': 'st-1',
      'direction': direction.name.toUpperCase(),
      'party_id': 'v-main',
    });
  }
}

OutstandingInvoice _bill(
  String id,
  String number,
  String owed, {
  String partyId = 'v-main',
  String partyCode = 'HQ',
  String partyName = 'Sundaram Pharma',
}) =>
    OutstandingInvoice.fromJson({
      'invoice_id': id,
      'invoice_number': number,
      'invoice_date': '2026-10-01',
      'invoice_total': owed,
      'allocated_amount': '0.00',
      'outstanding_amount': owed,
      'party_id': partyId,
      'party_code': partyCode,
      'party_name': partyName,
    });

Future<void> _openPayment(
  WidgetTester tester,
  _PayApi api,
  SettlementDirection direction,
) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: RecordSettlementDialog(
          api: api,
          direction: direction,
          parties: const [
            PartyOption(id: 'v-main', code: 'HQ', name: 'Sundaram Pharma'),
          ],
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.byType(TextFormField).first);
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Sundaram Pharma').last);
  await tester.pumpAndSettle();
}

// ---- Goods receipt -----------------------------------------------------

PurchaseOrder _order({String vendorId = 'v-main'}) => PurchaseOrder.fromJson({
      'id': 'po-1',
      'po_number': 'PO-2026-000001',
      'purchase_date': '2026-08-01',
      'warehouse_id': 'wh-1',
      'vendor_id': vendorId,
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

class _ReceiptApi extends ApiClient {
  _ReceiptApi({this.family = true})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool family;
  final List<String> familyCalls = <String>[];
  Json? sent;

  @override
  Future<PagedResult<GoodsReceiptRecord>> goodsReceipts({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> filters = const {},
  }) async =>
      PagedResult<GoodsReceiptRecord>(items: const [], total: 0);

  @override
  Future<VendorFamily> vendorFamily(String id) async {
    familyCalls.add(id);
    if (family) return _family;
    return VendorFamily.fromJson(<String, dynamic>{
      'parent_id': id,
      'members': <Json>[
        <String, dynamic>{
          'id': id,
          'code': 'ALONE',
          'name': 'Alone Traders',
          'is_parent': true,
          'status': 'ACTIVE',
          'balance': '0.00',
        },
      ],
      'total_balance': '0.00',
    });
  }

  @override
  Future<GoodsReceiptRecord> createGoodsReceipt(Json data) async {
    sent = data;
    return GoodsReceiptRecord.fromJson({
      'id': 'grn-2',
      'grn_number': 'GRN-2',
      'status': 'DRAFT',
    });
  }
}

Future<void> _openReceipt(WidgetTester tester, _ReceiptApi api) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: GoodsReceiptEditorDialog(
            api: api,
            purchaseOrders: [_order()],
            warehouses: const [],
            products: const [],
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('goods-receipt-order')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('PO-2026-000001').last);
  await tester.pumpAndSettle();
}

void main() {
  group('the supplier form', () {
    testWidgets('choosing a main office sends its id and nothing derived',
        (tester) async {
      final _VendorApi api = _VendorApi(rows: [
        _vendorJson(id: 'v-main', code: 'HQ', name: 'Sundaram Pharma'),
        _vendorJson(id: 'v-1', code: 'BLR', name: 'Bengaluru'),
      ]);
      await _pumpVendors(tester, api);
      await _editRow(tester, 'BLR');

      expect(find.text('Branch of'), findsOneWidget);
      expect(
        find.text('The main office this supplier is a branch of. A branch '
            'takes its GST number unless it types its own. Leave blank for a '
            'supplier on its own.'),
        findsOneWidget,
      );
      final Finder box = find.byKey(const ValueKey('vendor-parent-box'));
      await tester.ensureVisible(box);
      await tester.enterText(box, 'Sund');
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('HQ - Sundaram Pharma').last);
      await tester.pumpAndSettle();
      await _save(tester);

      expect(api.saved!['parent_vendor_id'], 'v-main');
      for (final String key in const [
        'parent_code',
        'parent_name',
        'branch_count',
      ]) {
        expect(api.saved!.containsKey(key), isFalse);
      }
    });

    testWidgets('a branch, a main office and the one being edited are not '
        'offered', (tester) async {
      final _VendorApi api = _VendorApi(rows: [
        _vendorJson(id: 'v-1', code: 'SELF', name: 'Self Traders'),
        _vendorJson(
            id: 'v-br',
            code: 'BRANCH',
            name: 'Branch Traders',
            parentId: 'v-main',
            parentCode: 'HQ'),
        _vendorJson(id: 'v-main', code: 'HQ', name: 'Sundaram Pharma'),
      ]);
      await _pumpVendors(tester, api);
      await _editRow(tester, 'SELF');
      final Finder box = find.byKey(const ValueKey('vendor-parent-box'));
      await tester.ensureVisible(box);
      await tester.enterText(box, 'Sund');
      await tester.pumpAndSettle();

      expect(find.textContaining('HQ - Sundaram Pharma'), findsOneWidget);
      expect(find.textContaining('SELF - Self Traders'), findsNothing);
      expect(find.textContaining('BRANCH - Branch Traders'), findsNothing);
    });

    testWidgets('clearing the main office sends null', (tester) async {
      final _VendorApi api = _VendorApi(rows: [
        _vendorJson(
            id: 'v-blr',
            code: 'HQ-BLR',
            name: 'Bengaluru',
            parentId: 'v-main',
            parentCode: 'HQ',
            parentName: 'Sundaram Pharma'),
      ]);
      await _pumpVendors(tester, api);
      await _editRow(tester, 'HQ-BLR');
      expect(find.text('HQ - Sundaram Pharma'), findsOneWidget);

      final Finder clear = find.byKey(const ValueKey('vendor-parent-clear'));
      await tester.ensureVisible(clear);
      await tester.tap(clear);
      await tester.pumpAndSettle();
      await _save(tester);

      expect(api.saved!.containsKey('parent_vendor_id'), isTrue);
      expect(api.saved!['parent_vendor_id'], isNull);
    });

    testWidgets('a branch that takes its main office\'s GSTIN opens with the '
        'box empty, names the number, and saves blank', (tester) async {
      final _VendorApi api = _VendorApi(
        rows: [
          _vendorJson(
              id: 'v-blr',
              code: 'HQ-BLR',
              name: 'Bengaluru',
              parentId: 'v-main',
              parentCode: 'HQ',
              parentName: 'Sundaram Pharma',
              gstin: '33AAAAA0000A1Z5',
              gstinFromParent: true),
        ],
        family: _takingFamily,
      );
      await _pumpVendors(tester, api);
      await _editRow(tester, 'HQ-BLR');

      final Finder box = find.widgetWithText(TextField, 'GSTIN');
      expect(tester.widget<TextField>(box).controller!.text, isEmpty);
      expect(
        find.text("Blank takes the main office's GST number "
            '(33AAAAA0000A1Z5). Type one only for a branch registered in '
            'another state.'),
        findsOneWidget,
      );

      await _save(tester);
      expect(api.saved!['gstin'], isEmpty);
      expect(api.saved!['gstin'], isNot('33AAAAA0000A1Z5'));
    });

    testWidgets('the Branches panel marks a GSTIN the branch took from its '
        'main office', (tester) async {
      final _VendorApi api = _VendorApi(
        rows: [
          _vendorJson(id: 'v-main', code: 'HQ', name: 'Sundaram', branches: 1),
        ],
        family: _takingFamily,
      );
      await _pumpVendors(tester, api);
      await _editRow(tester, 'HQ');

      await tester.ensureVisible(find.byKey(const ValueKey('vendor-branches')));
      expect(find.textContaining("33AAAAA0000A1Z5 (main office's)"),
          findsOneWidget);
    });

    testWidgets('a main office with branches cannot become a branch',
        (tester) async {
      final _VendorApi api = _VendorApi(rows: [
        _vendorJson(id: 'v-main', code: 'HQ', name: 'Sundaram', branches: 2),
      ]);
      await _pumpVendors(tester, api);
      await _editRow(tester, 'HQ');

      expect(find.text('This supplier is the main office of 2 branches.'),
          findsOneWidget);
      expect(find.byKey(const ValueKey('vendor-parent-box')), findsNothing);
    });

    testWidgets('the Branches panel lists the offices and the total, in one '
        'call', (tester) async {
      final _VendorApi api = _VendorApi(rows: [
        _vendorJson(id: 'v-main', code: 'HQ', name: 'Sundaram', branches: 1),
      ]);
      await _pumpVendors(tester, api);
      await _editRow(tester, 'HQ');

      expect(api.familyCalls, ['v-main']);
      final Finder panel = find.byKey(const ValueKey('vendor-branches'));
      await tester.ensureVisible(panel);
      expect(find.text('Branches'), findsOneWidget);
      expect(find.textContaining('HQ  Sundaram Pharma  (main office)'),
          findsOneWidget);
      expect(find.textContaining('HQ-BLR  Sundaram Pharma Bengaluru'),
          findsOneWidget);
      expect(find.textContaining('29AAAAA0000A1Z5'), findsOneWidget);
      expect(find.textContaining('Indiranagar, Bengaluru'), findsOneWidget);
      expect(find.text('Total we owe'), findsOneWidget);
      expect(find.text('79.50'), findsOneWidget);
    });

    testWidgets('a supplier with no main office and no branches makes no '
        'family call', (tester) async {
      final _VendorApi api = _VendorApi(rows: [_vendorJson()]);
      await _pumpVendors(tester, api);
      await _editRow(tester, 'V001');

      expect(api.familyCalls, isEmpty);
      expect(find.text('Branches'), findsNothing);
      expect(find.text('Total we owe'), findsNothing);
    });

    testWidgets('the list says which rows are branches and which are main '
        'offices', (tester) async {
      final _VendorApi api = _VendorApi(rows: [
        _vendorJson(id: 'v-main', code: 'HQ', name: 'Sundaram', branches: 3),
        _vendorJson(
            id: 'v-blr',
            code: 'HQ-BLR',
            name: 'Bengaluru',
            parentId: 'v-main',
            parentCode: 'HQ'),
        _vendorJson(id: 'z-1', code: 'ZZ', name: 'Alone'),
      ]);
      await _pumpVendors(tester, api);

      expect(find.text('Main office / branches'), findsOneWidget);
      expect(find.text('3 branches'), findsOneWidget);
      expect(find.text('Branch of HQ'), findsOneWidget);
    });
  });

  group('the goods receipt', () {
    testWidgets('a supplier company offers Received from and sends the '
        'choice', (tester) async {
      final _ReceiptApi api = _ReceiptApi();
      await _openReceipt(tester, api);

      expect(api.familyCalls, ['v-main']);
      expect(find.text('Received from'), findsOneWidget);
      expect(find.text('The office of this supplier the goods came from'),
          findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('goods-receipt-received-from')));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('HQ-BLR  Sundaram Pharma Bengaluru')
          .last);
      await tester.pumpAndSettle();
      // The line quantity defaults to the whole order; save as a draft.
      await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
      await tester.pumpAndSettle();

      expect(api.sent, isNotNull);
      expect(api.sent!['vendor_id'], 'v-blr');
    });

    testWidgets('a supplier on its own shows nothing and sends nothing new',
        (tester) async {
      final _ReceiptApi api = _ReceiptApi(family: false);
      await _openReceipt(tester, api);

      // One read per order chosen, and no field for a family of one.
      expect(api.familyCalls, hasLength(1));
      expect(find.text('Received from'), findsNothing);
      await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
      await tester.pumpAndSettle();
      expect(api.sent, isNotNull);
      expect(api.sent!.containsKey('vendor_id'), isFalse);
    });
  });

  group('Record Payment', () {
    testWidgets('a payment to a main office lists the branches\' bills, '
        'labelled, with the hint', (tester) async {
      final _PayApi api = _PayApi([
        _bill('b-own', 'PB-OWN-1', '100.00'),
        _bill('b-blr', 'PB-BLR-1', '250.00',
            partyId: 'v-blr',
            partyCode: 'HQ-BLR',
            partyName: 'Sundaram Pharma Bengaluru'),
      ]);
      await _openPayment(tester, api, SettlementDirection.payment);

      expect(api.asked.single.withBranches, isTrue);
      expect(find.byKey(const ValueKey('receipt-shops-hint')), findsOneWidget);
      expect(
        find.textContaining('Bills of the branches under this supplier'),
        findsOneWidget,
      );
      expect(find.byKey(const ValueKey('bill-shop-b-blr')), findsOneWidget);
      expect(find.text('HQ-BLR Sundaram Pharma Bengaluru'), findsOneWidget);
      expect(find.byKey(const ValueKey('bill-shop-b-own')), findsNothing);
    });

    testWidgets('saving sends the ticked branch bill in the allocations',
        (tester) async {
      final _PayApi api = _PayApi([
        _bill('b-own', 'PB-OWN-1', '100.00'),
        _bill('b-blr', 'PB-BLR-1', '250.00',
            partyId: 'v-blr',
            partyCode: 'HQ-BLR',
            partyName: 'Sundaram Pharma Bengaluru'),
      ]);
      await _openPayment(tester, api, SettlementDirection.payment);

      await tester.enterText(find.widgetWithText(TextField, 'Amount'), '250');
      await tester.pumpAndSettle();
      await tester.enterText(
        find
            .descendant(
              of: find.byType(DataTable),
              matching: find.byType(TextField),
            )
            .last,
        '250',
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Record payment'));
      await tester.pumpAndSettle();

      expect(api.recorded, isNotNull);
      expect(api.recorded!['party_id'], 'v-main');
      expect(api.recorded!['allocations'], [
        {'invoice_id': 'b-blr', 'amount': '250'},
      ]);
    });

    testWidgets('a receipt asks for shops, never for branches',
        (tester) async {
      final _PayApi api = _PayApi([_bill('i-own', 'SI-1', '100.00')]);
      await _openPayment(tester, api, SettlementDirection.receipt);

      expect(api.asked.single.withBranches, isFalse);
    });
  });
}
