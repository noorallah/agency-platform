import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/sales_return.dart';
import 'package:agency_desktop/models/uom_packaging.dart';
import 'package:agency_desktop/ui/sales_returns/sales_return_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Goods coming back from a customer.
///
/// Completing a return moves three books at once — the shelf, the customer's
/// account and the ledger — and none of them move before that. What the screen
/// has to get right is saying which of them have happened, and not letting
/// somebody book back more than went out.
PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

const List<String> _fullAccess = [
  'SALES_VIEW',
  'SALES_RETURN',
  'SALES_APPROVE',
  'SALES_CANCEL',
];

SalesReturn _return({
  String id = 'ret-1',
  String number = 'SR-2026-2027-000001',
  String status = 'DRAFT',
  String returned = '2.0000',
  String restocked = '1.0000',
  String grandTotal = '460.2000',
  String journalId = 'jrnl-1',
  String cancelReason = '',
  String? free,
  String? entered,
  String? returnUomId,
}) =>
    SalesReturn.fromJson({
      'id': id,
      'customer_id': 'cust-1',
      'customer_name': 'Anand Agencies',
      'branch_id': 'branch-1',
      'warehouse_id': 'wh-1',
      'return_number': number,
      'return_date': '2026-08-14',
      'customer_return_number': 'CRN-9',
      'return_reason': 'Damaged in transit',
      'status': status,
      'total_current_return_quantity': returned,
      'total_restock_quantity': restocked,
      'subtotal': '390.0000',
      'tax_total': '70.2000',
      'grand_total': grandTotal,
      'journal_entry_id': journalId,
      'cost_journal_entry_id': 'jrnl-2',
      'cancel_reason': cancelReason,
      'remarks': '',
      'lines': [
        {
          'id': 'line-1',
          'line_number': 1,
          'source_document_type': 'SALES_INVOICE',
          'source_document_number': 'SI-2026-2027-000008',
          'source_document_line_number': 1,
          'product_id': 'prod-1',
          'description': 'Shampoo Bottle 180ml',
          'dispatched_quantity': '12.0000',
          'already_returned_quantity': '0.0000',
          'current_return_quantity': returned,
          if (free != null) 'free_quantity': free,
          if (entered != null) 'entered_quantity': entered,
          if (returnUomId != null) 'return_uom_id': returnUomId,
          'restock_quantity': restocked,
          'damaged_quantity': '1.0000',
          'scrap_quantity': '0.0000',
          'reason_code': 'DAMAGED',
          'unit_price': '195.0000',
          'tax_amount': '70.2000',
          'net_amount': '460.2000',
          'batch_number': '',
          'remarks': '',
        }
      ],
    });

ReturnableDocument _invoice({String quantity = '12.0000'}) =>
    ReturnableDocument.fromSalesInvoice({
      'id': 'inv-1',
      'invoice_number': 'SI-2026-2027-000008',
      'invoice_date': '2026-08-04',
      'customer_id': 'cust-1',
      'lines': [
        {
          'id': 'line-a',
          'line_number': 1,
          'product_id': 'prod-1',
          'description': 'Shampoo Bottle 180ml',
          'current_invoice_quantity': quantity,
          'unit_price': '195.0000',
        }
      ],
    });

WarehouseRecord _warehouse() => WarehouseRecord.fromJson({
      'id': 'wh-1',
      'firm_id': 'firm-1',
      'branch_id': 'branch-1',
      'code': 'WH-001',
      'name': 'Main',
      'display_name': 'Main warehouse',
      'status': 'ACTIVE',
    });

class _ReturnApi extends ApiClient {
  _ReturnApi({this.rows = const [], this.documents = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<SalesReturn> rows;
  final List<ReturnableDocument> documents;
  Json? created;
  final List<String> actions = [];
  String? cancelReason;

  /// When set, the plain print is refused as the server refuses a return
  /// with no IRN; [referenceCopies] records each print asked for.
  bool irnRequired = false;
  final List<bool> referenceCopies = <bool>[];

  @override
  Future<List<int>> creditNotePdf(String id,
      {bool referenceCopy = false}) async {
    referenceCopies.add(referenceCopy);
    if (irnRequired && !referenceCopy) {
      throw const ApiException(
        'SR-1 has no IRN yet. Register it first.',
        statusCode: 422,
        code: 'business_rule_violation',
        details: <String, dynamic>{'reason': 'irn_required'},
      );
    }
    throw ApiException('The printer is offline.', statusCode: 503);
  }

  @override
  Future<List<UomRecord>> uoms({bool includeInactive = false}) async =>
      const <UomRecord>[
        UomRecord(
          id: 'u-pc',
          code: 'PIECE',
          name: 'Piece',
          symbol: 'pc',
          dimension: 'COUNT',
          status: 'ACTIVE',
          isDecimalAllowed: false,
        ),
      ];

  @override
  Future<PagedResult<SalesReturn>> salesReturns({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? status,
    String? returnFrom,
    String? returnTo,
  }) async =>
      PagedResult<SalesReturn>(items: rows, total: rows.length);

  @override
  Future<List<ReturnableDocument>> returnableDocuments({int limit = 50}) async =>
      documents;

  @override
  Future<PagedResult<WarehouseRecord>> warehouses({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    WarehouseQuery filters = const WarehouseQuery(),
  }) async =>
      PagedResult<WarehouseRecord>(items: [_warehouse()], total: 1);

  @override
  Future<SalesReturn> createSalesReturn(Json data) async {
    created = data;
    return _return();
  }

  @override
  Future<SalesReturn> salesReturnAction(
    String id,
    String action, {
    String? reason,
  }) async {
    actions.add(action);
    cancelReason = reason;
    return _return(status: action == 'approve' ? 'APPROVED' : 'COMPLETED');
  }
}

Future<void> _pump(
  WidgetTester tester,
  _ReturnApi api, {
  List<String> perms = _fullAccess,
  bool hasActiveFirm = true,
  bool phase2 = false,
}) async {
  final Widget page = SalesReturnManagementPage(
    api: api,
    preferences: DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('sales-returns'),
    ),
    permissions: _permissionsFor(perms),
    hasActiveFirm: hasActiveFirm,
    today: DateTime(2026, 8, 14),
  );
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: phase2 ? Phase2Scope(child: page) : page,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  test('an invoice line with no description is named by code and product', () {
    ReturnableLine read(Map<String, dynamic> extra) => ReturnableLine.fromJson(
          <String, dynamic>{
            'id': 'l-1',
            'line_number': 1,
            'product_id': 'p-1',
            'unit_price': '10',
            'current_invoice_quantity': '4',
            ...extra,
          },
          quantityKey: 'current_invoice_quantity',
        );

    expect(
      read({'product_code': 'P001', 'product_name': 'Rice 25kg'}).label,
      '1. P001  Rice 25kg  ·  4',
    );
    expect(read({'description': 'Loose rice', 'product_name': 'Rice'}).label,
        '1. Loose rice  ·  4');
    // Nothing known: "Line N" is the last resort, not the first.
    expect(read({}).label, '1. Line 1  ·  4');
  });

  group('reading a return', () {
    testWidgets('a draft says nothing has moved yet', (tester) async {
      await _pump(tester, _ReturnApi(rows: [_return()]));

      expect(find.text('SR-2026-2027-000001  ·  2026-08-14'), findsOneWidget);
      expect(find.textContaining('awaiting completion'), findsOneWidget);
      expect(find.text('DRAFT'), findsOneWidget);
    });

    testWidgets('a completed return says what it moved', (tester) async {
      await _pump(tester, _ReturnApi(rows: [_return(status: 'COMPLETED')]));

      // The list line carries both halves, because "COMPLETED" alone does not
      // say whether anything reached the shelf or the customer.
      expect(
        find.textContaining('1.0000 restocked · 460.2000 credited'),
        findsOneWidget,
      );
    });

    testWidgets('the detail names all three books', (tester) async {
      await _pump(tester, _ReturnApi(rows: [_return(status: 'COMPLETED')]));
      await tester.tap(find.text('SR-2026-2027-000001  ·  2026-08-14'));
      await tester.pumpAndSettle();

      expect(find.text('What this moves'), findsOneWidget);
      expect(find.text('Stock'), findsOneWidget);
      expect(find.text('Customer'), findsOneWidget);
      expect(find.text('Ledger'), findsOneWidget);
      expect(find.textContaining('credit and cost posted'), findsOneWidget);
    });

    testWidgets('a return worth nothing says so rather than looking broken',
        (tester) async {
      // Free samples and warranty replacements go out at no charge, so there
      // is no credit to post. That is a fact about the goods, not a failure.
      await _pump(
        tester,
        _ReturnApi(
          rows: [
            _return(status: 'COMPLETED', grandTotal: '0.0000', journalId: '')
          ],
        ),
      );
      await tester.tap(find.text('SR-2026-2027-000001  ·  2026-08-14'));
      await tester.pumpAndSettle();

      expect(
        find.textContaining('nothing to post — this return is worth nothing'),
        findsOneWidget,
      );
    });

    testWidgets('a line that brought free goods back says how many (D-PRC-8)',
        (tester) async {
      await _pump(tester, _ReturnApi(rows: [_return(free: '1.0000')]));
      await tester.tap(find.text('SR-2026-2027-000001  ·  2026-08-14'));
      await tester.pumpAndSettle();
      expect(find.textContaining('1.0000 of them free'), findsOneWidget);
    });

    testWidgets('a line with no free goods does not mention them',
        (tester) async {
      await _pump(tester, _ReturnApi(rows: [_return(free: '0.0000')]));
      await tester.tap(find.text('SR-2026-2027-000001  ·  2026-08-14'));
      await tester.pumpAndSettle();
      expect(find.textContaining('of them free'), findsNothing);
    });

    testWidgets('a line typed in another unit says what was typed (D-PRC-37)',
        (tester) async {
      // 7 PIECE against a line counted in boxes of 12: the server keeps
      // 0.5833 in the source unit and the 7 beside it.
      await _pump(
        tester,
        _ReturnApi(rows: [
          _return(returned: '0.5833', entered: '7.0000', returnUomId: 'u-pc'),
        ]),
      );
      tester.view.physicalSize = const Size(1366, 768);
      await tester.tap(find.text('SR-2026-2027-000001  ·  2026-08-14'));
      await tester.pumpAndSettle();

      expect(find.textContaining('7.0000 PIECE returned'), findsOneWidget);
      expect(find.textContaining('0.5833 returned'), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a line typed in the source unit is read as before',
        (tester) async {
      await _pump(tester, _ReturnApi(rows: [_return()]));
      await tester.tap(find.text('SR-2026-2027-000001  ·  2026-08-14'));
      await tester.pumpAndSettle();

      expect(find.textContaining('2.0000 returned'), findsOneWidget);
    });

    testWidgets('a line says what is still returnable', (tester) async {
      await _pump(tester, _ReturnApi(rows: [_return()]));
      await tester.tap(find.text('SR-2026-2027-000001  ·  2026-08-14'));
      await tester.pumpAndSettle();

      // 12 went out, 2 came back on this return, so 10 could still come back.
      expect(find.textContaining('10.0000 still returnable'), findsOneWidget);
      expect(find.textContaining('Shampoo Bottle 180ml'), findsWidgets);
    });
  });

  group('acting on one', () {
    testWidgets('a draft offers approve and not complete', (tester) async {
      await _pump(tester, _ReturnApi(rows: [_return()]));
      await tester.tap(find.text('SR-2026-2027-000001  ·  2026-08-14'));
      await tester.pumpAndSettle();

      expect(find.widgetWithText(FilledButton, 'Approve'), findsOneWidget);
      expect(find.widgetWithText(FilledButton, 'Complete'), findsNothing);
    });

    testWidgets('an approved return offers complete', (tester) async {
      final _ReturnApi api = _ReturnApi(rows: [_return(status: 'APPROVED')]);
      await _pump(tester, api);
      await tester.tap(find.text('SR-2026-2027-000001  ·  2026-08-14'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Complete'));
      await tester.pumpAndSettle();

      expect(api.actions, ['complete']);
    });

    testWidgets('cancelling asks why, and will not proceed without one',
        (tester) async {
      // Cancelling a completed return takes stock off the shelf again and puts
      // a balance back on a customer's account.
      final _ReturnApi api = _ReturnApi(rows: [_return(status: 'COMPLETED')]);
      await _pump(tester, api);
      await tester.tap(find.text('SR-2026-2027-000001  ·  2026-08-14'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
      await tester.pumpAndSettle();

      expect(find.text('Cancel SR-2026-2027-000001'), findsOneWidget);
      final FilledButton confirm = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Cancel return'),
      );
      expect(confirm.onPressed, isNull, reason: 'a reason is required');

      await tester.enterText(find.byType(TextField).last, 'raised in error');
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Cancel return'));
      await tester.pumpAndSettle();

      expect(api.actions, ['cancel']);
      expect(api.cancelReason, 'raised in error');
    });

    testWidgets('without SALES_APPROVE there is nothing to press',
        (tester) async {
      await _pump(
        tester,
        _ReturnApi(rows: [_return()]),
        perms: const ['SALES_VIEW'],
      );
      await tester.tap(find.text('SR-2026-2027-000001  ·  2026-08-14'));
      await tester.pumpAndSettle();

      expect(find.widgetWithText(FilledButton, 'Approve'), findsNothing);
      expect(find.widgetWithText(FilledButton, 'New Return'), findsNothing);
    });
  });

  group('raising one', () {
    testWidgets('it sends the source line and the condition split',
        (tester) async {
      final _ReturnApi api = _ReturnApi(documents: [_invoice()]);
      await _pump(tester, api);
      await tester.tap(find.widgetWithText(FilledButton, 'New Return'));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithText(TextFormField, 'Quantity returned'),
        '3',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Of which damaged'),
        '1',
      );
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
      await tester.pumpAndSettle();

      final Json? sent = api.created;
      expect(sent, isNotNull);
      expect(sent!['warehouse_id'], 'wh-1');
      expect(sent['return_date'], '2026-08-14');
      final Map<String, dynamic> line =
          Map<String, dynamic>.from((sent['lines'] as List).single as Map);
      expect(line['source_document_type'], 'SALES_INVOICE');
      expect(line['source_document_id'], 'inv-1');
      expect(line['source_document_line_id'], 'line-a');
      expect(line['current_return_quantity'], '3');
      expect(line['damaged_quantity'], '1');
    });

    testWidgets('it refuses more than went out', (tester) async {
      // The server refuses this too; saying it here means the refusal does not
      // arrive after the form has been filled in.
      final _ReturnApi api = _ReturnApi(documents: [_invoice(quantity: '4')]);
      await _pump(tester, api);
      await tester.tap(find.widgetWithText(FilledButton, 'New Return'));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithText(TextFormField, 'Quantity returned'),
        '5',
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
      await tester.pumpAndSettle();

      expect(find.textContaining('went out on this line'), findsOneWidget);
      expect(api.created, isNull);
    });

    testWidgets('it refuses more damaged than came back', (tester) async {
      final _ReturnApi api = _ReturnApi(documents: [_invoice()]);
      await _pump(tester, api);
      await tester.tap(find.widgetWithText(FilledButton, 'New Return'));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithText(TextFormField, 'Quantity returned'),
        '2',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Of which damaged'),
        '3',
      );
      await tester.pumpAndSettle();

      expect(find.text('That is more than came back.'), findsWidgets);
    });

    testWidgets('it says how much goes back on the shelf', (tester) async {
      final _ReturnApi api = _ReturnApi(documents: [_invoice()]);
      await _pump(tester, api);
      await tester.tap(find.widgetWithText(FilledButton, 'New Return'));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithText(TextFormField, 'Quantity returned'),
        '5',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Of which damaged'),
        '2',
      );
      await tester.pumpAndSettle();

      expect(
        find.textContaining('3.0 back on the shelf'),
        findsOneWidget,
        reason: 'the consequence of the three numbers, said in words',
      );
    });

    testWidgets('with nothing dispatched it says so rather than offering a form',
        (tester) async {
      await _pump(tester, _ReturnApi());
      await tester.tap(find.widgetWithText(FilledButton, 'New Return'));
      await tester.pumpAndSettle();

      expect(find.text('Nothing has gone out yet'), findsOneWidget);
    });
  });

  group('the empty and unauthorised states', () {
    testWidgets('no firm, no returns', (tester) async {
      await _pump(tester, _ReturnApi(), hasActiveFirm: false);
      expect(find.textContaining('Choose a firm'), findsOneWidget);
    });

    testWidgets('without SALES_VIEW there is nothing to show', (tester) async {
      await _pump(tester, _ReturnApi(), perms: const ['INVENTORY_VIEW']);
      expect(find.textContaining('do not have permission'), findsOneWidget);
    });

    testWidgets('an empty list explains what a return is', (tester) async {
      await _pump(tester, _ReturnApi());
      expect(find.text('Nothing has come back'), findsOneWidget);
    });
  });

  group('the source picker', () {
    test('a delivery note and an invoice read the same way', () {
      final ReturnableDocument note = ReturnableDocument.fromDeliveryNote({
        'id': 'dn-1',
        'delivery_note_number': 'DN-1',
        'delivery_date': '2026-08-04',
        'customer_id': 'cust-1',
        'customer_name': 'Classic Departmental Stores',
        'lines': [
          {
            'id': 'l1',
            'line_number': 1,
            'product_id': 'p1',
            'description': 'Soap',
            'current_delivery_quantity': '6.0000',
            'unit_price': '10',
          }
        ],
      });

      expect(note.sourceType, SalesReturnSource.deliveryNote);
      expect(note.number, 'DN-1');
      // Whose it is, because the list mixes every customer's documents and a
      // return raised against the wrong one credits the wrong customer.
      expect(note.label, 'DN-1  ·  2026-08-04  ·  Classic Departmental Stores');
      expect(_invoice().label, 'SI-2026-2027-000008  ·  2026-08-04');
      // Each document names its dispatched quantity differently; the picker
      // only cares that there is one.
      expect(note.lines.single.quantity, '6.0000');
      expect(_invoice().lines.single.quantity, '12.0000');
      expect(_invoice().sourceType, SalesReturnSource.salesInvoice);
    });

    test('a line is labelled by what it is, not by its id', () {
      expect(_invoice().lines.single.label, '1. Shampoo Bottle 180ml  ·  12.0000');
    });
  });

  // Phase 2 (owner, 2026-09-27): a grid like every other sales list, with
  // option C's bar carrying the steps and a double-click to read one.
  group('phase 2 grid', () {
    Future<void> select(WidgetTester tester) async {
      await tester.tap(find.text('SR-2026-2027-000001').first);
      // Past the double-click window, which is when a click is a selection.
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();
    }

    testWidgets('a grid naming each customer, and no side pane',
        (tester) async {
      await _pump(tester, _ReturnApi(rows: [_return()]), phase2: true);

      expect(find.byType(EnterpriseDataGrid<SalesReturn>), findsOneWidget);
      expect(find.text('Customer'), findsOneWidget);
      expect(find.text('Anand Agencies'), findsOneWidget);
      expect(find.text('What this moves'), findsNothing);
      expect(find.byType(ColumnsButton), findsOneWidget);
      expect(find.byType(DateRangeFilter), findsOneWidget);

      // And it fits the smallest screen the app supports.
      tester.view.physicalSize = const Size(1366, 768);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });

    testWidgets('the bar names the return and runs its step', (tester) async {
      final _ReturnApi api = _ReturnApi(rows: [_return()]);
      await _pump(tester, api, phase2: true);
      await select(tester);

      expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
      expect(find.textContaining('Anand Agencies ·'), findsOneWidget);
      // A draft is approved, not completed.
      expect(find.byKey(const ValueKey('selection-complete')), findsNothing);
      await tester.tap(find.byKey(const ValueKey('selection-approve')));
      await tester.pumpAndSettle();
      expect(api.actions, ['approve']);
    });

    testWidgets('no IRN: the refusal offers a reference copy, asked for '
        'with referenceCopy true', (tester) async {
      final _ReturnApi api = _ReturnApi(rows: [_return(status: 'COMPLETED')])
        ..irnRequired = true;
      await _pump(tester, api);
      await tester.tap(find.text('SR-2026-2027-000001  ·  2026-08-14'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Print credit note'));
      await tester.pumpAndSettle();

      expect(find.text('SR-1 has no IRN yet. Register it first.'),
          findsOneWidget);
      expect(api.referenceCopies, <bool>[false]);

      await tester.tap(find.text('Print reference copy'));
      await tester.pumpAndSettle();
      expect(api.referenceCopies, <bool>[false, true]);
    });

    testWidgets('double-clicking a return reads it', (tester) async {
      await _pump(tester, _ReturnApi(rows: [_return()]), phase2: true);

      final Finder row = find.text('SR-2026-2027-000001').first;
      await tester.tap(row);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(row);
      await tester.pumpAndSettle();

      expect(find.byType(AlertDialog), findsOneWidget);
      expect(find.text('What this moves'), findsOneWidget);
    });
  });
}
