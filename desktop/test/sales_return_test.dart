import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/sales_return.dart';
import 'package:agency_desktop/ui/sales_returns/sales_return_management_page.dart';
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
}) =>
    SalesReturn.fromJson({
      'id': id,
      'customer_id': 'cust-1',
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

  @override
  Future<PagedResult<SalesReturn>> salesReturns({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? status,
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
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: SalesReturnManagementPage(
          api: api,
          permissions: _permissionsFor(perms),
          hasActiveFirm: hasActiveFirm,
          today: DateTime(2026, 8, 14),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
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
}
