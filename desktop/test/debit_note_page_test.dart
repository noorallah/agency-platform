// Debit notes: a claim on a supplier without goods going back.
//
// Phase 2 only. The screen lists the notes, raises one against one approved
// bill of one supplier with the tax priced as it is typed, approves it, and
// cancels it only once a reason is given.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/purchases/debit_note_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show ColumnsButton, Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({
  List<String> perms = const [
    'DEBIT_NOTE_VIEW',
    'DEBIT_NOTE_MANAGE',
    'DEBIT_NOTE_APPROVE',
  ],
}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

/// One draft note against a bill, claiming 100 and taking 18 of tax off.
Json _note({String status = 'DRAFT'}) => <String, dynamic>{
      'id': 'dn-1',
      'debit_note_number': 'DN-2026-0001',
      'debit_note_date': '2026-09-02',
      'vendor_id': 'ven-1',
      'vendor_name': 'Patel Traders',
      'purchase_invoice_id': 'bill-1',
      'purchase_invoice_number': 'PI-2026-0009',
      'supplier_invoice_number': 'PT-77',
      'reason': 'PRICE_DIFFERENCE',
      'status': status,
      'taxable_amount': '100.0000',
      'tax_amount': '18.0000',
      'total_amount': '118.0000',
      'reference_number': null,
      'remarks': null,
      'cancel_reason': null,
      'journal_entry_id': null,
      'version': 4,
      'lines': const <Json>[],
    };

class _DebitNoteApi extends ApiClient {
  _DebitNoteApi({this.notes = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> notes;
  final List<String> requested = <String>[];
  final List<Map<String, String>> queries = <Map<String, String>>[];
  int? sentVersion;
  Json? cancelBody;
  final List<Json> previews = <Json>[];
  Json? raised;
  Json? updated;
  String? updatedId;
  int? updatedVersion;

  /// The status the server answers a fresh read of the note with.
  String detailStatus = 'DRAFT';

  /// Fields the fresh read adds to the note, such as a supplier's credit note.
  Json detailExtra = const <String, dynamic>{};

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
    queries.add(query ?? const <String, String>{});
    if (path == '/api/v1/vendors') {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'ven-1',
            'name': 'Patel Traders',
            'display_name': 'Patel Traders',
          },
        ],
        'pagination': <String, dynamic>{'total_records': 1},
      };
    }
    if (path == '/api/v1/purchase-invoices') {
      // Only the supplier's own approved bill is answered, so a filter the
      // screen forgets to send shows up as a missing or extra bill.
      if (query?['vendor_id'] != 'ven-1' || query?['status'] != 'APPROVED') {
        return <String, dynamic>{'data': const <Json>[]};
      }
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'bill-1',
            'invoice_number': 'PI-2026-0009',
            'supplier_invoice_number': 'PT-77',
            'invoice_date': '2026-09-01',
            'status': 'APPROVED',
            'vendor_id': 'ven-1',
          },
        ],
      };
    }
    if (path == '/api/v1/debit-notes/claimable-lines') {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'purchase_invoice_line_id': 'bill-1-line-1',
            'line_number': 1,
            'product_id': 'prod-1',
            'product_name': 'Toothpaste 100g',
            'quantity': '7.0000',
            'unit_price': '84.0000',
            'billed_taxable': '588.0000',
            'already_claimed': '0.0000',
            'already_returned': '0.0000',
            'claimable': '588.0000',
            'tax_rate_percent': '18.00',
          },
        ],
      };
    }
    if (method == 'POST' && path == '/api/v1/debit-notes/preview') {
      previews.add(body!);
      final List<dynamic> lines = body['lines'] as List<dynamic>;
      final double taxable =
          double.parse('${(lines.first as Json)['taxable_amount']}');
      return <String, dynamic>{
        'data': <String, dynamic>{
          ..._note(),
          'taxable_amount': taxable.toStringAsFixed(2),
          'tax_amount': (taxable * .18).toStringAsFixed(2),
          'total_amount': (taxable * 1.18).toStringAsFixed(2),
          'lines': [
            <String, dynamic>{
              'line_number': 1,
              'purchase_invoice_line_id':
                  (lines.first as Json)['purchase_invoice_line_id'],
              'product_name': 'Toothpaste 100g',
              'taxable_amount': taxable.toStringAsFixed(2),
              'tax_amount': (taxable * .18).toStringAsFixed(2),
              'total_amount': (taxable * 1.18).toStringAsFixed(2),
              'tax_rate_percent': '18.00',
            },
          ],
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/debit-notes') {
      raised = body;
      return <String, dynamic>{'data': _note()};
    }
    if (method == 'GET' && path == '/api/v1/debit-notes/dn-1') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          ..._note(status: detailStatus),
          ...detailExtra,
          'remarks': 'Rate was 84, billed 91',
          'lines': <Json>[
            <String, dynamic>{
              'id': 'dnl-1',
              'line_number': 1,
              'purchase_invoice_line_id': 'bill-1-line-1',
              'product_name': 'Toothpaste 100g',
              'quantity': '0.0000',
              'taxable_amount': '100.0000',
              'tax_amount': '18.0000',
              'total_amount': '118.0000',
              'tax_rate_percent': '18.00',
            },
          ],
        },
      };
    }
    if (method == 'PUT' && path == '/api/v1/debit-notes/dn-1') {
      updated = body;
      updatedId = 'dn-1';
      updatedVersion = expectedVersion;
      return <String, dynamic>{'data': _note()};
    }
    if (path.contains('/debit-notes')) {
      if (path.endsWith('/approve') || path.endsWith('/cancel')) {
        sentVersion = expectedVersion;
        if (path.endsWith('/cancel')) cancelBody = body;
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

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('debit-notes'),
    );

Future<void> _pump(
  WidgetTester tester,
  _DebitNoteApi api, {
  PermissionService? permissions,
  Size size = const Size(1600, 900),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  // Above the navigator, as in the app, so the screen it opens sees it.
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: DebitNotePage(
        api: api,
        preferences: _preferences(),
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the list shows the tax, the bill and the reason',
      (tester) async {
    final _DebitNoteApi api = _DebitNoteApi(notes: <Json>[_note()]);
    await _pump(tester, api);

    expect(find.text('DN-2026-0001'), findsOneWidget);
    expect(find.text('Patel Traders'), findsWidgets);
    expect(find.text('PI-2026-0009'), findsOneWidget);
    expect(find.text('Price difference'), findsOneWidget);
    expect(find.text('18.00'), findsOneWidget);
    expect(find.text('118.00'), findsOneWidget);
    expect(find.byType(ColumnsButton), findsOneWidget);
  });

  testWidgets('the bar approves the picked note, sending its version',
      (tester) async {
    final _DebitNoteApi api = _DebitNoteApi(notes: <Json>[_note()]);
    await _pump(tester, api);

    await tester.tap(find.text('DN-2026-0001').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('selection-approve')));
    await tester.pumpAndSettle();
    expect(api.requested, contains('POST /api/v1/debit-notes/dn-1/approve'));
    expect(api.sentVersion, 4);
  });

  testWidgets('cancelling asks why and sends the reason', (tester) async {
    final _DebitNoteApi api = _DebitNoteApi(notes: <Json>[_note()]);
    await _pump(tester, api);

    await tester.tap(find.text('DN-2026-0001').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('selection-cancel')));
    await tester.pumpAndSettle();

    // Nothing is sent until a reason is typed.
    expect(api.requested, isNot(contains('POST /api/v1/debit-notes/dn-1/cancel')));
    await tester.enterText(find.byType(TextField).last, 'Supplier agreed');
    await tester.pump();
    await tester.tap(find.text('Cancel note'));
    await tester.pumpAndSettle();

    expect(api.requested, contains('POST /api/v1/debit-notes/dn-1/cancel'));
    expect(api.cancelBody, <String, dynamic>{'reason': 'Supplier agreed'});
    expect(api.sentVersion, 4);
  });

  testWidgets('without DEBIT_NOTE_APPROVE nothing can be approved or cancelled',
      (tester) async {
    final _DebitNoteApi api = _DebitNoteApi(notes: <Json>[_note()]);
    await _pump(
      tester,
      api,
      permissions: _permissions(
        perms: const ['DEBIT_NOTE_VIEW', 'DEBIT_NOTE_MANAGE'],
      ),
    );

    await tester.tap(find.text('DN-2026-0001').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('selection-approve')), findsNothing);
    expect(find.byKey(const ValueKey('selection-cancel')), findsNothing);
  });

  testWidgets('a firm with no debit note permission sees nothing',
      (tester) async {
    final _DebitNoteApi api = _DebitNoteApi(notes: <Json>[_note()]);
    await _pump(tester, api, permissions: _permissions(perms: const []));

    expect(find.text('You cannot see debit notes'), findsOneWidget);
    expect(api.requested, isEmpty);
  });

  testWidgets('the screen fits the smallest supported windows',
      (tester) async {
    final _DebitNoteApi api = _DebitNoteApi(notes: <Json>[_note()]);
    await _pump(tester, api, size: const Size(1366, 768));
    expect(tester.takeException(), isNull);

    tester.view.physicalSize = const Size(800, 600);
    await tester.pump();
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('raising one: supplier, then bill, then the claim priced as typed',
      (tester) async {
    final _DebitNoteApi api = _DebitNoteApi(notes: <Json>[_note()]);
    await _pump(tester, api, size: const Size(1366, 768));
    await tester.tap(find.textContaining('New').last);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    // Nothing is offered until a supplier is chosen.
    expect(find.text('Choose the supplier.'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('debit-note-vendor')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Patel Traders').last);
    await tester.pumpAndSettle();
    // The bills asked for are that supplier's approved ones.
    expect(
      api.queries.any((q) =>
          q['vendor_id'] == 'ven-1' && q['status'] == 'APPROVED'),
      isTrue,
    );

    await tester.tap(find.byKey(const ValueKey('debit-note-bill-ven-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('PI-2026-0009').last);
    await tester.pumpAndSettle();
    expect(
      api.requested,
      contains('GET /api/v1/debit-notes/claimable-lines'),
    );
    expect(find.text('Toothpaste 100g'), findsWidgets);

    await tester.enterText(
      find.byKey(const ValueKey<String>('debit-note-amount-bill-1-0')),
      '100',
    );
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(api.previews.last['lines'][0]['taxable_amount'], '100');
    expect(find.text('18.00'), findsWidgets);
    expect(find.textContaining('118.00', findRichText: true), findsWidgets);

    await tester.tap(find.byKey(const ValueKey('debit-note-save')));
    await tester.pumpAndSettle();
    expect(api.raised?['purchase_invoice_id'], 'bill-1');
    expect(api.raised?['reason'], 'PRICE_DIFFERENCE');
    expect(api.raised?['lines'][0]['purchase_invoice_line_id'], 'bill-1-line-1');
    // Only fields the server declares are sent.
    expect(
      (api.raised!.keys.toSet()).difference(const {
        'purchase_invoice_id',
        'debit_note_date',
        'reason',
        'debit_note_number',
        'reference_number',
        'remarks',
        'lines',
      }),
      isEmpty,
    );
  });

  testWidgets('opening a note reads it fresh and shows its detail',
      (tester) async {
    final _DebitNoteApi api = _DebitNoteApi(notes: <Json>[_note()]);
    await _pump(tester, api);

    await tester.tap(find.text('DN-2026-0001').first);
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tap(find.text('DN-2026-0001').first);
    await tester.pumpAndSettle();

    expect(api.requested, contains('GET /api/v1/debit-notes/dn-1'));
    expect(find.textContaining('Toothpaste 100g'), findsOneWidget);
    expect(find.textContaining('18.00%'), findsOneWidget);
    expect(find.text('Rate was 84, billed 91'), findsOneWidget);
    expect(find.textContaining('118.00 claimed'), findsOneWidget);
  });

  testWidgets('Edit is offered only for a draft and needs the manage code',
      (tester) async {
    final _DebitNoteApi api = _DebitNoteApi(
      notes: <Json>[_note(status: 'APPROVED')],
    );
    await _pump(tester, api);
    await tester.tap(find.text('DN-2026-0001').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('selection-edit')), findsNothing);

    final _DebitNoteApi draft = _DebitNoteApi(notes: <Json>[_note()]);
    await _pump(
      tester,
      draft,
      permissions: _permissions(
        perms: const ['DEBIT_NOTE_VIEW', 'DEBIT_NOTE_APPROVE'],
      ),
    );
    await tester.tap(find.text('DN-2026-0001').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('selection-edit')), findsNothing);
  });

  testWidgets('editing a draft prefills it and saves through the update',
      (tester) async {
    final _DebitNoteApi api = _DebitNoteApi(notes: <Json>[_note()]);
    await _pump(tester, api, size: const Size(1366, 768));
    await tester.tap(find.text('DN-2026-0001').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('selection-edit')));
    await tester.pumpAndSettle();

    expect(api.requested, contains('GET /api/v1/debit-notes/dn-1'));
    // The note's own claim is not counted against the bill line.
    expect(
      api.queries.any((q) => q['excluding_note_id'] == 'dn-1'),
      isTrue,
    );
    expect(find.text('Save changes'), findsOneWidget);
    final TextFormField amount = tester.widget<TextFormField>(
      find.byKey(const ValueKey<String>('debit-note-amount-bill-1-0')),
    );
    expect(amount.initialValue, '100.0000');

    await tester.enterText(
      find.byKey(const ValueKey<String>('debit-note-amount-bill-1-0')),
      '50',
    );
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('debit-note-save')));
    await tester.pumpAndSettle();

    expect(api.updatedId, 'dn-1');
    expect(api.updatedVersion, 4);
    expect(api.updated?['lines'][0]['purchase_invoice_line_id'], 'bill-1-line-1');
    expect(api.updated?['lines'][0]['taxable_amount'], '50');
    expect(api.updated?['reason'], 'PRICE_DIFFERENCE');
    expect(api.raised, isNull);
    // Only fields the update schema declares are sent.
    expect(
      api.updated!.keys.toSet().difference(const {
        'debit_note_date',
        'reason',
        'reference_number',
        'supplier_credit_note_number',
        'supplier_credit_note_date',
        'remarks',
        'lines',
      }),
      isEmpty,
    );
    // Nothing recorded, so an edit sends the pair cleared.
    expect(api.updated?['supplier_credit_note_number'], isNull);
    expect(api.updated?['supplier_credit_note_date'], isNull);
  });

  testWidgets(
      "raising one records the supplier's credit note number and date "
      '(68 row 10)', (tester) async {
    final _DebitNoteApi api = _DebitNoteApi(notes: <Json>[_note()]);
    await _pump(tester, api, size: const Size(1366, 768));
    await tester.tap(find.textContaining('New').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('debit-note-vendor')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Patel Traders').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('debit-note-bill-ven-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('PI-2026-0009').last);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('debit-note-reason')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Discount after billing').last);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('debit-note-supplier-credit-note')),
      'PT-CN-12',
    );
    await tester.tap(
      find.byKey(const ValueKey('debit-note-supplier-credit-note-date')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey<String>('debit-note-amount-bill-1-0')),
      '40',
    );
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('debit-note-save')));
    await tester.pumpAndSettle();

    expect(api.raised?['reason'], 'DISCOUNT');
    expect(api.raised?['supplier_credit_note_number'], 'PT-CN-12');
    final DateTime now = DateTime.now();
    expect(
      api.raised?['supplier_credit_note_date'],
      DateTime(now.year, now.month, now.day)
          .toIso8601String()
          .split('T')
          .first,
    );
  });

  testWidgets("a supplier's credit note reads as one in the list and the detail",
      (tester) async {
    final _DebitNoteApi api = _DebitNoteApi(notes: <Json>[
      <String, dynamic>{
        ..._note(),
        'reason': 'DISCOUNT',
        'supplier_credit_note_number': 'PT-CN-12',
        'supplier_credit_note_date': '2026-09-01',
      },
    ]);
    api.detailExtra = <String, dynamic>{
      'supplier_credit_note_number': 'PT-CN-12',
      'supplier_credit_note_date': '2026-09-01',
    };
    await _pump(tester, api);
    expect(find.text('Discount after billing'), findsOneWidget);

    await tester.tap(find.text('DN-2026-0001').first);
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tap(find.text('DN-2026-0001').first);
    await tester.pumpAndSettle();
    expect(
      find.text("Supplier's credit note PT-CN-12 dated 2026-09-01"),
      findsOneWidget,
    );
  });
}
