// Customer opening bills: what each customer owed the firm on day one,
// entered bill by bill at cutover so receipts can be set against the old
// bills and the ageing counts each from its own due date (backlog 36).
//
// The receivable twin of `vendor_opening_bills_test.dart`. The section lives
// on the phase 2 customer form: a nullable loader hides it for a new customer
// or somebody without `CUSTOMER_VIEW`, and "Add opening bill" and "Cancel"
// show only with `CUSTOMER_UPDATE`. Record Receipt marks an opening bill
// "Opening" beside the sales invoices it offers.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/customer_opening_bill.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/models/settlement.dart';
import 'package:agency_desktop/models/settlement_direction.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/finance/record_settlement_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Customer _customer() => Customer.fromJson(<String, dynamic>{
      'id': 'c-1',
      'firm_id': 'firm-1',
      'code': 'C001',
      'customer_type': 'BUSINESS',
      'name': 'Kumar Stores',
      'display_name': 'Kumar Stores',
      'status': 'ACTIVE',
      'currency_code': 'INR',
      'payment_terms_days': 30,
      'opening_balance': '0.00',
      'current_outstanding': '8000.00',
      'addresses': const <Json>[],
      'contacts': const <Json>[],
      'version': 1,
      'created_at': '2026-04-01T00:00:00Z',
      'updated_at': '2026-04-01T00:00:00Z',
    });

const Json _openBill = {
  'id': 'obc-1',
  'version': 1,
  'customer_id': 'c-1',
  'customer_code': 'C001',
  'customer_name': 'Kumar Stores',
  'bill_number': 'OBC-00001',
  'reference_number': 'SI-OLD-1',
  'bill_date': '2026-03-01',
  'due_date': '2026-03-31',
  'posting_date': '2026-04-01',
  'amount': '5000.00',
  'received_amount': '0.00',
  'outstanding_amount': '5000.00',
  'narration': 'Carried over',
  'status': 'POSTED',
  'cancellation_reason': null,
};

const Json _partReceived = {
  'id': 'obc-2',
  'version': 1,
  'customer_id': 'c-1',
  'customer_code': 'C001',
  'customer_name': 'Kumar Stores',
  'bill_number': 'OBC-00002',
  'reference_number': 'SI-OLD-2',
  'bill_date': '2026-03-05',
  'due_date': '2026-04-04',
  'posting_date': '2026-04-01',
  'amount': '3000.00',
  'received_amount': '1000.00',
  'outstanding_amount': '2000.00',
  'narration': null,
  'status': 'POSTED',
  'cancellation_reason': null,
};

/// What the form was asked to do, and the bills it holds.
class _Books {
  _Books([List<Json> bills = const <Json>[]]) : bills = [...bills];

  List<Json> bills;
  final List<Json> created = <Json>[];
  int reads = 0;
  String? cancelledId;
  String? cancelReason;

  Future<List<CustomerOpeningBill>> load() async {
    reads++;
    return [for (final Json row in bills) CustomerOpeningBill.fromJson(row)];
  }

  Future<CustomerOpeningBill> create(Json data) async {
    created.add(data);
    final Json row = {
      ..._openBill,
      'id': 'obc-new',
      'bill_number': 'OBC-00003',
      'reference_number': data['reference_number'],
      'amount': data['amount'],
      'outstanding_amount': data['amount'],
    };
    bills = [...bills, row];
    return CustomerOpeningBill.fromJson(row);
  }

  Future<CustomerOpeningBill> cancel(String id, String reason) async {
    cancelledId = id;
    cancelReason = reason;
    final Json updated = {
      ...bills.firstWhere((row) => row['id'] == id),
      'status': 'CANCELLED',
      'cancellation_reason': reason,
    };
    bills = [
      for (final Json row in bills)
        if (row['id'] == id) updated else row,
    ];
    return CustomerOpeningBill.fromJson(updated);
  }
}

Future<List<GeoPlaceRecord>> _noPlaces(GeoLevel level,
        {String parentId = ''}) async =>
    const <GeoPlaceRecord>[];

Future<void> _pumpForm(
  WidgetTester tester, {
  required Customer? customer,
  _Books? books,
  bool canManage = true,
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: CustomerWorkspaceDialog(
          mode: customer == null
              ? CustomerDialogMode.create
              : CustomerDialogMode.edit,
          customer: customer,
          onSave: (payload) async => customer ?? _customer(),
          loadPlaces: _noPlaces,
          loadOpeningBills: customer == null ? null : books?.load,
          onCreateOpeningBill: customer == null ? null : books?.create,
          onCancelOpeningBill: books?.cancel,
          canManageOpeningBills: canManage,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _scrollTo(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
}

class _ReceiptApi extends ApiClient {
  _ReceiptApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  @override
  Future<List<OutstandingInvoice>> outstandingInvoices({
    required SettlementDirection direction,
    required String partyId,
  }) async =>
      [
        OutstandingInvoice.fromJson(const {
          'invoice_id': 'obc-1',
          'invoice_number': 'SI-OLD-1 (opening)',
          'invoice_date': '2026-03-01',
          'invoice_total': '5000.00',
          'allocated_amount': '0.00',
          'outstanding_amount': '5000.00',
          'is_opening_bill': true,
        }),
        OutstandingInvoice.fromJson(const {
          'invoice_id': 'si-1',
          'invoice_number': 'SI-2026-000001',
          'invoice_date': '2026-04-10',
          'invoice_total': '3000.00',
          'allocated_amount': '0.00',
          'outstanding_amount': '3000.00',
        }),
      ];

  @override
  Future<Json> tcsPreview({
    required String customerId,
    required String amount,
    required String on,
  }) async =>
      <String, dynamic>{'applicable': false};
}

void main() {
  testWidgets('the section is hidden while a customer is still being created',
      (tester) async {
    await _pumpForm(tester, customer: null);

    expect(find.byKey(const ValueKey('customer-section-Opening bills')),
        findsNothing);
    expect(find.text('Add opening bill'), findsNothing);
  });

  testWidgets('lists what the customer owed at cutover, and what is still '
      'owed', (tester) async {
    final _Books books = _Books(const [_openBill, _partReceived]);
    await _pumpForm(tester, customer: _customer(), books: books);

    expect(find.byKey(const ValueKey('customer-section-Opening bills')),
        findsOneWidget);
    final Finder first = find.text('OBC-00001');
    await _scrollTo(tester, first);
    expect(first, findsOneWidget);
    expect(find.text('OBC-00002'), findsOneWidget);
    expect(find.text('SI-OLD-1'), findsOneWidget);
    // Amount, received and owed differ on the part-received bill.
    expect(find.text('3000.00'), findsOneWidget);
    expect(find.text('1000.00'), findsOneWidget);
    expect(find.text('2000.00'), findsOneWidget);
    expect(books.reads, 1);
  });

  testWidgets('add posts only the fields the write schema declares',
      (tester) async {
    final _Books books = _Books();
    await _pumpForm(tester, customer: _customer(), books: books);

    final Finder addButton =
        find.widgetWithText(OutlinedButton, 'Add opening bill');
    await _scrollTo(tester, addButton);
    await tester.tap(addButton);
    await tester.pumpAndSettle();

    await tester.enterText(
        find.widgetWithText(TextField, 'Old bill number'), 'SI-OLD-9');
    await tester.enterText(
        find.widgetWithText(TextField, 'Amount owed'), '2500.00');
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(books.created, hasLength(1));
    final Json body = books.created.single;
    // Due date and posting date were left blank, so they are absent rather
    // than null: absent is what lets the server take the customer's terms
    // and today.
    expect(body.keys.toSet(), {'bill_date', 'reference_number', 'amount'});
    expect(body['reference_number'], 'SI-OLD-9');
    expect(body['amount'], '2500.00');
    expect(body['bill_date'], matches(RegExp(r'^\d{4}-\d{2}-\d{2}$')));
    // And the list is read again, showing the new bill.
    expect(books.reads, 2);
    expect(find.text('OBC-00003'), findsOneWidget);
  });

  testWidgets('cancel asks for a reason and sends it', (tester) async {
    final _Books books = _Books(const [_openBill]);
    await _pumpForm(tester, customer: _customer(), books: books);

    final Finder cancelButton =
        find.byKey(const ValueKey('customer-opening-bill-cancel-obc-1'));
    await _scrollTo(tester, cancelButton);
    await tester.tap(cancelButton);
    await tester.pumpAndSettle();

    expect(find.text('Cancel OBC-00001'), findsOneWidget);
    await tester.enterText(
      find.descendant(
        of: find.byType(AlertDialog),
        matching: find.byType(TextField),
      ),
      'Entered twice',
    );
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, 'Cancel bill'));
    await tester.pumpAndSettle();

    expect(books.cancelledId, 'obc-1');
    expect(books.cancelReason, 'Entered twice');
  });

  testWidgets('cancel is not offered once anything has been received',
      (tester) async {
    final _Books books = _Books(const [_partReceived]);
    await _pumpForm(tester, customer: _customer(), books: books);

    await _scrollTo(tester, find.text('OBC-00002'));
    expect(find.byKey(const ValueKey('customer-opening-bill-cancel-obc-2')),
        findsNothing);
  });

  testWidgets('without CUSTOMER_UPDATE the bills are read-only',
      (tester) async {
    final _Books books = _Books(const [_openBill]);
    await _pumpForm(
      tester,
      customer: _customer(),
      books: books,
      canManage: false,
    );

    await _scrollTo(tester, find.text('OBC-00001'));
    expect(find.text('Add opening bill'), findsNothing);
    expect(find.byKey(const ValueKey('customer-opening-bill-cancel-obc-1')),
        findsNothing);
  });

  testWidgets('Record Receipt marks an opening bill beside the invoices',
      (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: RecordSettlementDialog(
          api: _ReceiptApi(),
          direction: SettlementDirection.receipt,
          parties: const [
            PartyOption(id: 'c-1', code: 'C001', name: 'Kumar Stores'),
          ],
        ),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byType(TextFormField).first);
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Kumar Stores').last);
    await tester.pumpAndSettle();

    expect(find.text('SI-OLD-1 (opening)'), findsOneWidget);
    expect(find.text('SI-2026-000001'), findsOneWidget);
    // One badge: the opening bill carries it, the sales invoice does not.
    expect(find.widgetWithText(StatusBadge, 'Opening'), findsOneWidget);
  });
}
