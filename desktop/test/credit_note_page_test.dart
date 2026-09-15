// Credit notes: money credited without goods coming back.
//
// The one thing this screen has to make impossible to miss is which document
// does what. A sales return moves stock; a credit note does not, and it is the
// only path that reverses the output tax the invoice charged. Choosing wrong
// is silent, so the screen says so in words.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/credit_note_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({
  List<String> perms = const [
    'CREDIT_NOTE_VIEW',
    'CREDIT_NOTE_MANAGE',
    'CREDIT_NOTE_APPROVE',
  ],
}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

/// One document the picker might be offered, in the shape the list returns.
///
/// `description` is null on every one of them, because it is null on every
/// real document too -- nothing populates it. That is the premise of the
/// labelling test below rather than an omission here.
Json _document({
  required String id,
  required String number,
  required String status,
  String productName = 'Toothpaste 100g',
  bool withLines = true,
}) =>
    <String, dynamic>{
      'id': id,
      'invoice_number': number,
      'delivery_note_number': number,
      'invoice_date': '2026-09-01',
      'delivery_date': '2026-09-01',
      'customer_id': 'cust-1',
      'customer_name': 'Kumar Stores',
      'status': status,
      'lines': withLines
          ? <Json>[
              <String, dynamic>{
                'id': '$id-line-1',
                'line_number': 1,
                'product_id': 'prod-1',
                'product_name': productName,
                'description': null,
                'current_invoice_quantity': '7.0000',
                'current_delivery_quantity': '7.0000',
                'unit_price': '84.0000',
              },
            ]
          : const <Json>[],
    };

class _CreditNoteApi extends ApiClient {
  _CreditNoteApi({this.notes = const [], this.invoices, this.deliveryNotes})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> notes;

  /// What the two unfiltered document lists answer. Null means "the default
  /// set" -- an approved invoice, a cancelled one, an approved invoice with
  /// no lines, and a delivery note -- which is what the picker has to sort
  /// out. The fake used to answer an empty list for both, which is why no
  /// test here had ever populated the picker at all.
  final List<Json>? invoices;
  final List<Json>? deliveryNotes;
  final List<String> requested = <String>[];
  int? sentVersion;

  List<Json> get _invoices =>
      invoices ??
      <Json>[
        _document(id: 'inv-1', number: 'SI-2026-0009', status: 'APPROVED'),
        _document(id: 'inv-2', number: 'SI-2026-0010', status: 'CANCELLED'),
        _document(
            id: 'inv-3',
            number: 'SI-2026-0011',
            status: 'APPROVED',
            withLines: false),
      ];

  List<Json> get _deliveryNotes =>
      deliveryNotes ??
      <Json>[
        _document(id: 'dn-1', number: 'DN-2026-0004', status: 'COMPLETED'),
      ];

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
    requested.add('$method $path');
    if (path.contains('/credit-notes')) {
      if (path.endsWith('/approve') || path.endsWith('/cancel')) {
        sentVersion = expectedVersion;
        return <String, dynamic>{'data': _note()};
      }
      return <String, dynamic>{
        'data': notes,
        'pagination': <String, dynamic>{'total_records': notes.length},
      };
    }
    if (path.contains('/sales-invoices')) {
      return <String, dynamic>{'data': _invoices};
    }
    if (path.contains('/delivery-notes')) {
      return <String, dynamic>{'data': _deliveryNotes};
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

/// One draft note against an invoice, crediting 100 and reversing 18 of tax.
Json _note() => <String, dynamic>{
      'id': 'cn-1',
      'credit_note_number': 'CN-2026-0001',
      'credit_note_date': '2026-09-02',
      'customer_id': 'cust-1',
      'customer_name': 'Kumar Stores',
      'sales_invoice_id': 'inv-1',
      'sales_invoice_number': 'SI-2026-0009',
      'reason': 'RATE_DIFFERENCE',
      'status': 'DRAFT',
      'taxable_amount': '100.0000',
      'tax_amount': '18.0000',
      'total_amount': '118.0000',
      'remarks': null,
      'journal_entry_id': null,
      'version': 4,
      'lines': const <Json>[],
    };

Future<void> _pump(
  WidgetTester tester,
  _CreditNoteApi api, {
  PermissionService? permissions,
}) async {
  tester.view.physicalSize = const Size(1700, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: CreditNotePage(
        api: api,
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the list shows the tax beside what was credited',
      (tester) async {
    final _CreditNoteApi api = _CreditNoteApi(notes: <Json>[_note()]);
    await _pump(tester, api);

    expect(find.text('CN-2026-0001'), findsOneWidget);
    expect(find.text('DRAFT · Rate difference'), findsOneWidget);
    // The tax is the whole reason this document exists rather than a
    // receivable adjustment, so it is on the row and not behind a click.
    expect(find.text('118.00 (tax 18.00)'), findsOneWidget);
  });

  testWidgets('the screen says which document moves stock', (tester) async {
    final _CreditNoteApi api = _CreditNoteApi(notes: <Json>[_note()]);
    await _pump(tester, api);

    // Choosing the wrong document is silent: a sales return would move stock
    // that never came back, and the old receivable adjustment would leave the
    // tax standing. Saying so is the cheapest guard there is.
    expect(find.textContaining('reverses the tax'), findsOneWidget);
    expect(find.textContaining('sales return'), findsWidgets);
  });

  testWidgets('approving carries the version the row was read at',
      (tester) async {
    final _CreditNoteApi api = _CreditNoteApi(notes: <Json>[_note()]);
    await _pump(tester, api);

    await tester.tap(find.text('Approve'));
    await tester.pumpAndSettle();

    expect(api.requested, contains('POST /api/v1/credit-notes/cn-1/approve'));
    expect(api.sentVersion, 4);
  });

  testWidgets('without CREDIT_NOTE_APPROVE nothing can be approved',
      (tester) async {
    final _CreditNoteApi api = _CreditNoteApi(notes: <Json>[_note()]);
    await _pump(
      tester,
      api,
      // Approving reverses tax the firm has declared. Drafting one is
      // bookkeeping; approving it changes a return.
      permissions: _permissions(
        perms: const ['CREDIT_NOTE_VIEW', 'CREDIT_NOTE_MANAGE'],
      ),
    );

    expect(find.text('Approve'), findsNothing);
    expect(find.text('Cancel'), findsNothing);
    expect(find.widgetWithText(FilledButton, 'Raise credit note'),
        findsOneWidget);
  });

  testWidgets('a firm with no credit note permission sees nothing',
      (tester) async {
    final _CreditNoteApi api = _CreditNoteApi(notes: <Json>[_note()]);
    await _pump(tester, api, permissions: _permissions(perms: const []));

    expect(find.text('You cannot see credit notes'), findsOneWidget);
    expect(api.requested, isEmpty);
  });

  testWidgets('the screen fits the smallest supported window', (tester) async {
    final _CreditNoteApi api = _CreditNoteApi(notes: <Json>[_note()]);
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: CreditNotePage(
          api: api,
          permissions: _permissions(),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    // Reachable, not merely rendered: a row action past the right edge is one
    // nobody finds, which is how the payout grid shipped wrong once.
    await tester.tap(find.text('Approve'));
    await tester.pumpAndSettle();
    expect(api.requested, contains('POST /api/v1/credit-notes/cn-1/approve'));
  });

  testWidgets('the invoice picker offers only bills there is something to credit on',
      (tester) async {
    // The list behind this picker is the sales-return one: the 50 most recent
    // delivery notes and the 50 most recent invoices, unfiltered. A delivery
    // note is not a bill, a cancelled invoice charged nobody, and an invoice
    // with no lines has nothing to correct -- and choosing any of the three
    // gave an empty Line dropdown with no word about why, which is what made
    // the screen look broken on 2026-09-15.
    final _CreditNoteApi api = _CreditNoteApi(notes: <Json>[_note()]);
    await _pump(tester, api);

    await tester.tap(find.text('Raise credit note'));
    await tester.pumpAndSettle();

    // **Open the dropdown before asserting.** A closed
    // `DropdownButtonFormField` renders only its selected item, so
    // `findsNothing` on the others holds whatever the list contains -- the
    // first cut of this test passed with the filter reverted, which is no
    // test at all.
    await tester.tap(find.byType(DropdownButtonFormField<String>).first);
    await tester.pumpAndSettle();

    expect(find.textContaining('SI-2026-0009'), findsWidgets);
    expect(find.textContaining('SI-2026-0010'), findsNothing,
        reason: 'cancelled: it charged nobody');
    expect(find.textContaining('SI-2026-0011'), findsNothing,
        reason: 'no lines: nothing to credit');
    expect(find.textContaining('DN-2026-0004'), findsNothing,
        reason: 'a delivery note is not a bill');
  });

  testWidgets('a line is named by its product, not by "Line 1"',
      (tester) async {
    // `description` is null on every real document line, so the picker fell
    // back to "Line N" for all of them -- a dropdown of indistinguishable
    // rows on a screen whose whole job is choosing which supply to correct.
    // The server now sends `product_name` beside it.
    final _CreditNoteApi api = _CreditNoteApi(notes: <Json>[_note()]);
    await _pump(tester, api);

    await tester.tap(find.text('Raise credit note'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Toothpaste 100g'), findsWidgets);
    expect(find.text('Line 1'), findsNothing);
  });

  testWidgets('with nothing creditable it says so rather than showing an empty form',
      (tester) async {
    final _CreditNoteApi api = _CreditNoteApi(
      notes: <Json>[_note()],
      invoices: const <Json>[],
      deliveryNotes: const <Json>[],
    );
    await _pump(tester, api);

    await tester.tap(find.text('Raise credit note'));
    await tester.pumpAndSettle();

    expect(find.textContaining('No approved invoice to credit'), findsOneWidget);
  });
}
