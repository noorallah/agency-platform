// Backlog 78 row 3, desktop half: GSTR-2B reconciliation.
//
// Pins: the import posts exactly the three keys the server declares; the
// grid shows each status, the counts and the in-books-only list; Match to bill
// posts the chosen bill and Undo match posts null; the GST documents settings
// send the two new keys; GSTR-3B shows credit held back.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/gst_return_page.dart';
import 'package:agency_desktop/ui/sales/gstr2b_page.dart';
import 'package:agency_desktop/ui/tax/gst_documents_settings_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

PermissionService _permissions(List<String> codes) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode({'permissions': codes})));
  return PermissionService()..applyAccessToken('h.$payload.s');
}

Json _doc(String id, String status, {String type = 'INVOICE'}) => {
      'id': id,
      'supplier_gstin': '29ABCDE1234F1Z5',
      'supplier_name': 'Acme Traders',
      'document_type': type,
      'document_number': 'INV-$id',
      'document_date': '2026-08-05',
      'taxable_value': '1000.00',
      'igst': '0.00',
      'cgst': '90.00',
      'sgst': '90.00',
      'cess': '0.00',
      'itc_available': true,
      'reverse_charge': false,
      'match_status': status,
      'match_note': 'note for $status',
      'purchase_invoice_id': null,
      'debit_note_id': null,
    };

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? imported;
  final List<List<String?>> matches = [];
  Json? savedSettings;
  Json summary3b = {};

  @override
  Future<Json> gstr2bReconciliation(String returnPeriod) async => {
        'return_period': returnPeriod,
        'imported': true,
        'import_id': 'i-1',
        'imported_at': '2026-09-02T10:00:00Z',
        'source_name': 'r2b.json',
        'skipped_sections': 'impg, b2ba',
        'counts': {'MATCHED': 1, 'DIFFERENT': 1, 'NOT_IN_BOOKS': 1, 'MANUAL': 1},
        'documents': [
          _doc('m', 'MATCHED'),
          _doc('d', 'DIFFERENT'),
          _doc('n', 'NOT_IN_BOOKS'),
          _doc('u', 'MANUAL'),
        ],
        'in_books_only': [
          {
            'purchase_invoice_id': 'pb-9',
            'invoice_number': 'PB-0009',
            'supplier_invoice_number': 'S-9',
            'supplier_invoice_date': '2026-08-07',
            'supplier_name': 'Other Supplier',
            'supplier_gstin': '27AAAAA0000A1Z5',
            'tax_total': '45.00',
          },
        ],
      };

  @override
  Future<Json> importGstr2b({
    required String returnPeriod,
    required String content,
    String? sourceName,
  }) async {
    imported = {
      'return_period': returnPeriod,
      'content': content,
      'source_name': sourceName,
    };
    return {'document_count': 4};
  }

  @override
  Future<Json> matchGstr2bDocument(String documentId, String? invoiceId) async {
    matches.add([documentId, invoiceId]);
    return {};
  }

  @override
  Future<Json> documentPage(
    String resource, {
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> additionalQuery = const {},
  }) async =>
      {
        'data': [
          {
            'id': 'bill-1',
            'invoice_number': 'PB-0001',
            'supplier_invoice_number': 'S-1',
            'vendor_name': 'Acme Traders',
            'grand_total': '1180.00',
            'status': 'APPROVED',
          },
        ],
      };

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
    if (path.endsWith('/gst-compliance-settings')) {
      if (method == 'PUT') {
        savedSettings = Map<String, dynamic>.from(body ?? const {});
        return {
          'data': {...?body, 'is_configured': true},
        };
      }
      return {
        'data': {
          'einvoice_applicable_from': null,
          'thirty_day_rule_from': null,
          'dispatch_without_invoice': 'OFF',
          'route_sale_needs_invoice': false,
          'is_configured': true,
          'itc_claim_basis': 'ALL',
          'gstr2b_tolerance': '1.00',
        },
      };
    }
    throw StateError('unexpected $method $path');
  }

  @override
  Future<Json> gstr1({required String fromDate, required String toDate}) async =>
      {'gstin': '29AAAAA0000A1Z5'};

  @override
  Future<Json> gstr3b({required String fromDate, required String toDate}) async =>
      summary3b;
}

Future<void> _pump(
  WidgetTester tester,
  _Api api, {
  List<String> codes = const ['ACCOUNT_VIEW', 'JOURNAL_POST'],
  Size size = const Size(1366, 768),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Gstr2bPage(
        api: api,
        permissions: _permissions(codes),
        hasActiveFirm: true,
        today: DateTime(2026, 9, 10),
        pickFile: () async => (name: 'r2b.json', text: '{"data":{}}'),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('shows statuses, counts, skipped sections and the books-only list',
      (tester) async {
    await _pump(tester, _Api());

    expect(find.text('Matched'), findsWidgets);
    expect(find.text('Different'), findsWidgets);
    expect(find.text('Not in books'), findsWidgets);
    expect(find.text('Manual'), findsOneWidget);
    expect(find.text('note for DIFFERENT'), findsOneWidget);
    expect(find.text('Not read from this file: impg, b2ba'), findsOneWidget);
    expect(find.byKey(const ValueKey('gstr2b-count-MATCHED')), findsOneWidget);
    expect(find.byKey(const ValueKey('gstr2b-match-m')), findsNothing);

    await tester.tap(find.text('In books, not in 2B'));
    await tester.pumpAndSettle();
    expect(find.text('PB-0009'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('fits 800x600', (tester) async {
    await _pump(tester, _Api(), size: const Size(800, 600));
    expect(tester.takeException(), isNull);
  });

  testWidgets('import posts exactly the three keys', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    await tester.tap(find.byKey(const ValueKey('gstr2b-import')));
    await tester.pumpAndSettle();

    expect(api.imported, {
      'return_period': '2026-08',
      'content': '{"data":{}}',
      'source_name': 'r2b.json',
    });
    expect(find.textContaining('GSTR-2B for 2026-08: 4 documents.'),
        findsOneWidget);
  });

  testWidgets('import is disabled without JOURNAL_POST', (tester) async {
    await _pump(tester, _Api(), codes: ['ACCOUNT_VIEW']);
    final FilledButton button =
        tester.widget(find.byKey(const ValueKey('gstr2b-import')));
    expect(button.onPressed, isNull);
  });

  testWidgets('Match to bill posts the chosen bill; Undo posts null',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await tester.ensureVisible(find.byKey(const ValueKey('gstr2b-match-n')));
    await tester.tap(find.byKey(const ValueKey('gstr2b-match-n')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('gstr2b-bill-bill-1')));
    await tester.pumpAndSettle();
    expect(api.matches.single, ['n', 'bill-1']);

    await tester.ensureVisible(find.byKey(const ValueKey('gstr2b-undo-u')));
    await tester.tap(find.byKey(const ValueKey('gstr2b-undo-u')));
    await tester.pumpAndSettle();
    expect(api.matches.last, ['u', null]);
  });

  testWidgets('settings send the two new keys', (tester) async {
    final _Api api = _Api();
    tester.view.physicalSize = const Size(800, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: GstDocumentsSettingsDialog(
          api: api,
          permissions: _permissions(['TAX_VIEW', 'TAX_MANAGE_SETTINGS']),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const ValueKey('gst-itc-basis')));
    await tester.tap(find.byKey(const ValueKey('gst-itc-basis')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Only bills matched to GSTR-2B').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const ValueKey('gst-2b-tolerance')));
    await tester.enterText(
        find.byKey(const ValueKey('gst-2b-tolerance')), '2.50');
    await tester.tap(find.byKey(const ValueKey('gst-settings-save')));
    await tester.pumpAndSettle();

    expect(api.savedSettings?['itc_claim_basis'], 'MATCHED_ONLY');
    expect(api.savedSettings?['gstr2b_tolerance'], '2.50');
  });

  testWidgets('GSTR-3B shows credit held back until 2B lists it',
      (tester) async {
    final _Api api = _Api()
      ..summary3b = {
        'eligible_itc': {
          'integrated_tax': '0',
          'central_tax': '90.00',
          'state_tax': '90.00',
          'cess': '0',
        },
        'itc_awaiting_2b': {
          'integrated_tax': '0',
          'central_tax': '45.00',
          'state_tax': '45.00',
          'cess': '0',
        },
      };
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: GstReturnPage(
          api: api,
          permissions: _permissions(['SALES_VIEW']),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('GSTR-3B'));
    await tester.pumpAndSettle();
    expect(find.text('Held back — not yet in GSTR-2B'), findsOneWidget);
  });
}
