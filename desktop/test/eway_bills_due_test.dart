// Backlog 77 rows 9 and 10, desktop half: e-way bills for a delivery note no
// invoice bills, a bill recorded by hand, the list of consignments above the
// firm's limit that have none, and the prompt after a dispatch or an approval.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/einvoice.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/phase2/phase2_scope.dart';
import 'package:agency_desktop/ui/sales/einvoice_page.dart';
import 'package:agency_desktop/ui/sales/eway_bill_actions.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['EINVOICE_VIEW', 'EINVOICE_MANAGE'],
  }));

Json _bill({
  String number = '123456789012',
  String status = 'GENERATED',
  bool byHand = false,
}) =>
    <String, dynamic>{
      'id': 'bill-1',
      'sales_invoice_id': null,
      'delivery_note_id': 'dn-1',
      'entered_by_hand': byHand,
      'mode': 'SANDBOX',
      'status': status,
      'eway_bill_number': number,
      'valid_until': '2026-10-09',
      'distance_km': '120.00',
      'transport_mode': 'ROAD',
      'transporter_id': null,
      'transporter_name': null,
      'vehicle_number': 'KA01AB1234',
      'error_code': null,
      'error_message': null,
    };

class _Api extends ApiClient {
  _Api({
    this.settingsReadable = true,
    this.existingBill,
    this.due = const <Json>[],
  }) : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool settingsReadable;
  final Json? existingBill;
  List<Json> due;
  final List<String> calls = <String>[];
  Json? lastBody;
  int settingsReads = 0;

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
    calls.add('$method $path');
    if (method != 'GET') lastBody = body;
    if (path == '/api/v1/tax-framework/gst-compliance-settings') {
      settingsReads++;
      if (!settingsReadable) throw ApiException('no', statusCode: 403);
      return <String, dynamic>{
        'data': <String, dynamic>{
          'einvoice_applicable_from': null,
          'thirty_day_rule_from': null,
          'dispatch_without_invoice': 'WARN',
          'route_sale_needs_invoice': false,
          'eway_bill_limit': '50000',
          'is_configured': true,
        },
      };
    }
    if (path == '/api/v1/einvoice/eway-bills/due') {
      return <String, dynamic>{
        'data': <String, dynamic>{'limit': '50000.00', 'items': due},
      };
    }
    if (path == '/api/v1/einvoice/eway-bills/record') {
      due = <Json>[];
      return <String, dynamic>{'data': _bill(byHand: true)};
    }
    if (path.startsWith('/api/v1/einvoice/delivery-notes/') &&
        path.endsWith('/eway-bill/cancel')) {
      return <String, dynamic>{
        'data': <String, dynamic>{..._bill(), 'status': 'CANCELLED'},
      };
    }
    if (path.startsWith('/api/v1/einvoice/delivery-notes/') &&
        path.endsWith('/eway-bill')) {
      if (method == 'POST') {
        due = <Json>[];
        return <String, dynamic>{'data': _bill()};
      }
      return <String, dynamic>{'data': existingBill};
    }
    if (path.startsWith('/api/v1/einvoice/invoices/') &&
        path.endsWith('/eway-bill')) {
      if (method == 'POST') {
        due = <Json>[];
        return <String, dynamic>{'data': _bill()};
      }
      return <String, dynamic>{'data': existingBill};
    }
    if (path == '/api/v1/einvoice/settings') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'provider': 'OFFLINE',
          'available': <String>['SANDBOX', 'OFFLINE'],
        },
      };
    }
    if (path.contains('/einvoice/registrations')) {
      return <String, dynamic>{
        'data': const <Json>[],
        'pagination': <String, dynamic>{'total_records': 0},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

Json _dueNote() => <String, dynamic>{
      'document_type': 'DELIVERY_NOTE',
      'document_id': 'dn-1',
      'number': 'DN-0001',
      'on': '2026-10-01',
      'value': '82000.00',
    };

Json _dueInvoice() => <String, dynamic>{
      'document_type': 'SALES_INVOICE',
      'document_id': 'inv-1',
      'number': 'SI-0001',
      'on': '2026-10-02',
      'value': '65000.00',
    };

/// A screen with a button that offers the prompt, standing for the
/// dispatch or approval that does so in the real ones.
Future<void> _pumpNudge(
  WidgetTester tester,
  EwayBillNudge nudge, {
  String grandTotal = '82000.00',
  bool invoice = false,
  VoidCallback? onDone,
}) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () => nudge.offer(
            context,
            invoiceId: invoice ? 'inv-1' : null,
            noteId: invoice ? null : 'dn-1',
            grandTotal: grandTotal,
            onDone: onDone,
          ),
          child: const Text('go'),
        ),
      ),
    ),
  ));
}

void main() {
  test('the models read the new fields', () {
    final EWayBillRecord bill = EWayBillRecord.fromJson(_bill(byHand: true));
    expect(bill.salesInvoiceId, '');
    expect(bill.deliveryNoteId, 'dn-1');
    expect(bill.enteredByHand, isTrue);
    expect(bill.referenceLabel, contains('recorded by hand'));
    final EWayBillDueList list = EWayBillDueList.fromJson(<String, dynamic>{
      'limit': '50000.00',
      'items': <Json>[_dueNote()],
    });
    expect(list.items.single.isNote, isTrue);
    expect(list.items.single.typeLabel, 'Delivery note');
  });

  group('the e-way bills due list', () {
    Future<void> open(WidgetTester tester, _Api api) async {
      tester.view.physicalSize = const Size(1700, 1200);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: EInvoicePage(
            api: api,
            permissions: _permissions(),
            hasActiveFirm: true,
          ),
        ),
      ));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('toolbar-more')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('E-way bills due'));
      await tester.pumpAndSettle();
    }

    testWidgets('shows the limit and each consignment', (tester) async {
      final _Api api = _Api(due: [_dueNote(), _dueInvoice()]);
      await open(tester, api);
      expect(find.byKey(const ValueKey('eway-due-limit')), findsOneWidget);
      expect(find.textContaining('50,000.00'), findsOneWidget);
      expect(find.textContaining('DN-0001'), findsOneWidget);
      expect(find.textContaining('Delivery note'), findsOneWidget);
      expect(find.textContaining('SI-0001'), findsOneWidget);
      expect(find.textContaining('82,000.00'), findsOneWidget);
    });

    testWidgets('raising for a delivery note calls the note endpoint',
        (tester) async {
      final _Api api = _Api(due: [_dueNote()]);
      await open(tester, api);
      await tester.tap(find.text('Raise e-way bill'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).at(1), 'KA01AB1234');
      await tester.tap(find.text('Raise'));
      await tester.pumpAndSettle();
      expect(
        api.calls,
        contains('POST /api/v1/einvoice/delivery-notes/dn-1/eway-bill'),
      );
      // Refreshed: the consignment has left the list.
      expect(find.byKey(const ValueKey('eway-due-dn-1')), findsNothing);
      expect(find.text('Nothing is waiting for an e-way bill.'),
          findsOneWidget);
    });

    testWidgets('raising for an invoice calls the invoice endpoint',
        (tester) async {
      final _Api api = _Api(due: [_dueInvoice()]);
      await open(tester, api);
      await tester.tap(find.text('Raise e-way bill'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).at(1), 'KA01AB1234');
      await tester.tap(find.text('Raise'));
      await tester.pumpAndSettle();
      expect(
        api.calls,
        contains('POST /api/v1/einvoice/invoices/inv-1/eway-bill'),
      );
    });

    testWidgets('recording sends the number and what was typed, nothing else',
        (tester) async {
      final _Api api = _Api(due: [_dueNote()]);
      await open(tester, api);
      await tester.tap(find.text('Record e-way bill...'));
      await tester.pumpAndSettle();

      // Not twelve digits: refused on screen, nothing sent.
      await tester.enterText(
        find.byKey(const ValueKey('eway-record-number')),
        '1234',
      );
      await tester.tap(find.byKey(const ValueKey('eway-record-save')));
      await tester.pumpAndSettle();
      expect(find.text('An e-way bill number is 12 digits.'), findsOneWidget);
      expect(api.calls.where((c) => c.contains('/record')), isEmpty);

      await tester.enterText(
        find.byKey(const ValueKey('eway-record-number')),
        '1234 5678 9012',
      );
      await tester.enterText(
        find.byKey(const ValueKey('eway-record-distance')),
        '120',
      );
      await tester.enterText(
        find.byKey(const ValueKey('eway-record-vehicle')),
        'KA01AB1234',
      );
      await tester.tap(find.byKey(const ValueKey('eway-record-save')));
      await tester.pumpAndSettle();

      expect(api.calls, contains('POST /api/v1/einvoice/eway-bills/record'));
      expect(api.lastBody, {
        'delivery_note_id': 'dn-1',
        'eway_bill_number': '123456789012',
        'distance_km': '120',
        'vehicle_number': 'KA01AB1234',
      });
      expect(find.byKey(const ValueKey('eway-due-dn-1')), findsNothing);
    });
  });

  group("a delivery note's e-way bill", () {
    Future<void> open(WidgetTester tester, _Api api) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () => showNoteEwayBill(
                context,
                api,
                noteId: 'dn-1',
                noteNumber: 'DN-0001',
                mayManage: true,
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
    }

    testWidgets('shows its number where it has one, and offers no second',
        (tester) async {
      await open(tester, _Api(existingBill: _bill()));
      expect(find.textContaining('123456789012'), findsOneWidget);
      expect(find.byKey(const ValueKey('note-eway-raise')), findsNothing);
      expect(find.byKey(const ValueKey('note-eway-record')), findsNothing);
    });

    testWidgets('a live bill is withdrawn with a reason', (tester) async {
      final _Api api = _Api(existingBill: _bill());
      await open(tester, api);
      await tester.tap(find.byKey(const ValueKey('note-eway-withdraw')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).last, 'Vehicle broke down');
      await tester.tap(find.text('Withdraw').last);
      await tester.pumpAndSettle();

      expect(
        api.calls,
        contains('POST /api/v1/einvoice/delivery-notes/dn-1/eway-bill/cancel'),
      );
      expect(api.lastBody, {'reason': 'Vehicle broke down'});
    });

    testWidgets('offers Raise and Record where it has none', (tester) async {
      await open(tester, _Api());
      expect(find.byKey(const ValueKey('note-eway-raise')), findsOneWidget);
      expect(find.byKey(const ValueKey('note-eway-record')), findsOneWidget);
    });

    testWidgets("the server's refusal is shown, and the dialog stays",
        (tester) async {
      final _Api api = _RefusingApi();
      await open(tester, api);
      await tester.tap(find.byKey(const ValueKey('note-eway-raise')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).at(1), 'KA01AB1234');
      await tester.tap(find.text('Raise'));
      await tester.pumpAndSettle();
      expect(
        find.text('This delivery note is billed by SI-0001; raise the e-way '
            'bill on that invoice.'),
        findsOneWidget,
      );
      expect(find.text('Raise an e-way bill'), findsOneWidget);
    });
  });

  group('the prompt after a consignment moves', () {
    testWidgets('above the limit, with no bill: Raise / Record / Later',
        (tester) async {
      final _Api api = _Api();
      await _pumpNudge(tester, EwayBillNudge(api));
      await tester.tap(find.text('go'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('eway-nudge')), findsOneWidget);
      expect(
        find.textContaining('worth more than ₹50,000'),
        findsOneWidget,
      );
      expect(find.text('Raise'), findsOneWidget);
      expect(find.text('Record'), findsOneWidget);
      expect(find.text('Later'), findsOneWidget);
      await tester.tap(find.text('Later'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('eway-nudge')), findsNothing);
    });

    testWidgets('Raise opens the dialog and refreshes the screen after',
        (tester) async {
      final _Api api = _Api();
      int done = 0;
      await _pumpNudge(tester, EwayBillNudge(api), onDone: () => done++);
      await tester.tap(find.text('go'));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('eway-nudge-raise')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).at(1), 'KA01AB1234');
      await tester.tap(find.text('Raise').last);
      await tester.pumpAndSettle();
      expect(
        api.calls,
        contains('POST /api/v1/einvoice/delivery-notes/dn-1/eway-bill'),
      );
      expect(done, 1);
    });

    testWidgets('an invoice asks about its own bill', (tester) async {
      final _Api api = _Api();
      await _pumpNudge(tester, EwayBillNudge(api), invoice: true);
      await tester.tap(find.text('go'));
      await tester.pumpAndSettle();
      expect(api.calls, contains('GET /api/v1/einvoice/invoices/inv-1/eway-bill'));
      expect(find.byKey(const ValueKey('eway-nudge')), findsOneWidget);
    });

    testWidgets('under the limit says nothing', (tester) async {
      await _pumpNudge(tester, EwayBillNudge(_Api()), grandTotal: '49999.00');
      await tester.tap(find.text('go'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('eway-nudge')), findsNothing);
    });

    testWidgets('a consignment with a live bill says nothing', (tester) async {
      await _pumpNudge(tester, EwayBillNudge(_Api(existingBill: _bill())));
      await tester.tap(find.text('go'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('eway-nudge')), findsNothing);
    });

    testWidgets('settings that cannot be read say nothing', (tester) async {
      await _pumpNudge(tester, EwayBillNudge(_Api(settingsReadable: false)));
      await tester.tap(find.text('go'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('eway-nudge')), findsNothing);
    });

    testWidgets('the limit is read once per screen', (tester) async {
      final _Api api = _Api();
      await _pumpNudge(tester, EwayBillNudge(api), grandTotal: '10.00');
      await tester.tap(find.text('go'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('go'));
      await tester.pumpAndSettle();
      expect(api.settingsReads, 1);
    });
  });
}

class _RefusingApi extends _Api {
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
    if (method == 'POST') {
      throw ApiException(
        'This delivery note is billed by SI-0001; raise the e-way bill on '
        'that invoice.',
        statusCode: 422,
      );
    }
    return super.request(method, path);
  }
}
