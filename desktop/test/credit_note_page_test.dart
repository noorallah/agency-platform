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

class _CreditNoteApi extends ApiClient {
  _CreditNoteApi({this.notes = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> notes;
  final List<String> requested = <String>[];
  int? sentVersion;

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
}
