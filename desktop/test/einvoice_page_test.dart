// The one thing this screen must never do is let a rehearsal read as a filing.
//
// A sandbox registration files nothing with the tax authority, and its
// reference means nothing outside this system. Somebody eventually prints a
// screen and carries it to a check post, so the mode travels with the
// reference everywhere it is shown.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/einvoice_page.dart';
import 'package:agency_desktop/phase2/phase2_scope.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({
  List<String> perms = const ['EINVOICE_VIEW', 'EINVOICE_MANAGE'],
}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

class _EInvoiceApi extends ApiClient {
  _EInvoiceApi({
    this.registrations = const [],
    this.bill,
    this.provider = 'SANDBOX',
    this.notes = const [],
    this.pending,
  })
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> registrations;
  final Json? bill;
  final String provider;
  List<String>? exportedIds;
  List<String>? exportedCreditIds;
  List<String>? exportedDebitIds;
  final List<Json> notes;

  /// The body of GET /einvoice/pending; null answers an empty one.
  final Json? pending;
  String? importedName;
  List<int>? importedBytes;
  final List<String> requested = <String>[];
  Json? sentBody;

  /// When set, the first e-way bill POST is refused with it (D-DLG-1).
  String? refuseEwayBill;

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
    if (path == '/api/v1/einvoice/settings') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'provider': provider,
          'available': <String>['SANDBOX', 'OFFLINE'],
        },
      };
    }
    if (path == '/api/v1/einvoice/pending') {
      return <String, dynamic>{'data': pending};
    }
    if (path.contains('/eway-bill')) {
      if (method == 'POST') {
        final String? refusal = refuseEwayBill;
        if (refusal != null) {
          refuseEwayBill = null;
          throw ApiException(refusal, statusCode: 422);
        }
        sentBody = body;
      }
      return <String, dynamic>{'data': bill};
    }
    if (path.contains('/einvoice/registrations')) {
      return <String, dynamic>{
        'data': registrations,
        'pagination': <String, dynamic>{'total_records': registrations.length},
      };
    }
    if (path.contains('/einvoice/invoices/')) {
      if (method == 'POST') sentBody = body;
      return <String, dynamic>{'data': registrations.firstOrNull};
    }
    if (path == '/api/v1/credit-notes' || path == '/api/v1/customer-debit-notes') {
      final String kind = path.contains('credit') ? 'CREDIT' : 'DEBIT';
      return <String, dynamic>{
        'data': [
          for (final Json n in notes)
            if (n['kind'] == kind) n,
        ],
      };
    }
    if (path == '/api/v1/sales-invoices') {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'inv-9',
            'invoice_number': 'SI-2026-2027-000008',
            'customer_name': 'Revise Check 2',
            'grand_total': '2554.1100',
            'status': 'APPROVED',
          },
        ],
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }

  @override
  Future<List<int>> downloadBytes(
    String path, {
    Map<String, String>? query,
    String method = 'GET',
    Json? body,
    bool retrying = false,
  }) async {
    requested.add('$method $path');
    exportedIds = List<String>.from(body?['invoice_ids'] as List);
    exportedCreditIds = body?['credit_note_ids'] == null
        ? null
        : List<String>.from(body!['credit_note_ids'] as List);
    exportedDebitIds = body?['debit_note_ids'] == null
        ? null
        : List<String>.from(body!['debit_note_ids'] as List);
    return utf8.encode('[]');
  }

  @override
  Future<Json> multipartRequest(
    String method,
    String path, {
    required Map<String, String> fields,
    String? fileField,
    String? fileName,
    List<int>? fileBytes,
    String? fileContentType,
    bool authenticated = true,
    bool retrying = false,
  }) async {
    requested.add('$method $path');
    importedName = fileName;
    importedBytes = fileBytes;
    return <String, dynamic>{
      'data': <String, dynamic>{
        'registered': <String>['SI-1', 'SI-2'],
        'failed': <String>['SI-3'],
        'unmatched': <String>['SI-X'],
        'already': <String>[],
      },
    };
  }
}

Json _sandboxRegistration() => <String, dynamic>{
      'id': 'reg-1',
      'sales_invoice_id': 'inv-1',
      'invoice_number': 'SI-2026-2027-000004',
      'customer_name': 'Vijaya Super Stores',
      'mode': 'SANDBOX',
      'status': 'REGISTERED',
      'irn': 'SBXa1b2c3',
      'acknowledgement_number': 'SBXA1B2C3D4',
      'acknowledged_at': null,
      'signed_qr_code': 'SANDBOX.abc',
      'error_code': null,
      'error_message': null,
      'attempts': 1,
      'cancellation_reason': null,
    };

Future<void> _pump(
  WidgetTester tester,
  _EInvoiceApi api, {
  PermissionService? permissions,
  bool phase2 = false,
  Future<XFile?> Function()? pickResultFile,
  Future<String?> Function(String, List<int>)? saveExportFile,
}) async {
  tester.view.physicalSize = const Size(1700, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    // Above the navigator, so a dialog the page opens is phase 2's too.
    builder: phase2 ? (context, child) => Phase2Scope(child: child!) : null,
    home: Scaffold(
      body: EInvoicePage(
        api: api,
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
        pickResultFile: pickResultFile,
        saveExportFile: saveExportFile,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a sandbox reference is never shown without saying so',
      (tester) async {
    final _EInvoiceApi api =
        _EInvoiceApi(registrations: <Json>[_sandboxRegistration()]);
    await _pump(tester, api);

    // The reference and the mode travel together. A screen showing only the
    // number is a document somebody carries to a check post.
    expect(
      find.text('SBXa1b2c3  (sandbox — nothing filed)'),
      findsOneWidget,
    );
    expect(find.textContaining('nothing was filed'), findsOneWidget);
  });

  testWidgets('a registration names the invoice and the customer it is for',
      (tester) async {
    // A grid of references alone could not be matched to a bill (mapping
    // section 12, 2026-09-13); the server now labels each row.
    final _EInvoiceApi api =
        _EInvoiceApi(registrations: <Json>[_sandboxRegistration()]);
    await _pump(tester, api);
    expect(find.text('Invoice'), findsWidgets);
    expect(find.text('SI-2026-2027-000004'), findsOneWidget);
    expect(find.text('Vijaya Super Stores'), findsOneWidget);
  });

  testWidgets('the register picker names whose invoice each one is',
      (tester) async {
    // Number and total alone could not find one customer's bill among every
    // approved invoice the firm holds (plan item 12.5).
    final _EInvoiceApi api = _EInvoiceApi(registrations: [_sandboxRegistration()]);
    await _pump(tester, api);

    await tester.tap(find.text('Register an invoice'));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();

    expect(
      find.text('SI-2026-2027-000008 — Revise Check 2 — 2554.1100'),
      findsWidgets,
    );
  });

  testWidgets('a failed registration shows what the portal said',
      (tester) async {
    final _EInvoiceApi api = _EInvoiceApi(registrations: <Json>[
      <String, dynamic>{
        ..._sandboxRegistration(),
        'status': 'FAILED',
        'irn': null,
        'error_code': '2150',
        'error_message': 'Document SI-1 is already registered.',
      },
    ]);
    await _pump(tester, api);

    // The person who has to fix the invoice is looking at this screen, so the
    // portal's own sentence is on the row rather than in a log.
    expect(
      find.textContaining('already registered'),
      findsOneWidget,
    );
  });

  testWidgets('a withdrawn registration is not offered again', (tester) async {
    // A cancelled IRN is never reissued for the same document number, and
    // the server refuses it (D-CMP-6); "Try again" is for a refusal only.
    final _EInvoiceApi api = _EInvoiceApi(registrations: <Json>[
      <String, dynamic>{
        ..._sandboxRegistration(),
        'status': 'CANCELLED',
        'cancellation_reason': 'Wrong customer',
      },
    ]);
    await _pump(tester, api);

    expect(find.widgetWithText(TextButton, 'Try again'), findsNothing);
  });

  testWidgets('an e-way bill by road will not send without a vehicle',
      (tester) async {
    final _EInvoiceApi api =
        _EInvoiceApi(registrations: <Json>[_sandboxRegistration()]);
    await _pump(tester, api);

    await tester.tap(find.text('Raise e-way bill'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextField, 'Distance (km)'), '450');
    await tester.tap(find.widgetWithText(FilledButton, 'Raise'));
    await tester.pumpAndSettle();

    expect(api.sentBody, isNull, reason: 'nothing reaches the server');
    expect(find.textContaining('vehicle number'), findsWidgets);
  });

  testWidgets('the selected row can raise its e-way bill from the toolbar',
      (tester) async {
    // With five columns the row's own buttons sit past the right edge of a
    // laptop screen, and "Raise e-way bill" could not be found (plan item
    // 12.6).
    final _EInvoiceApi api =
        _EInvoiceApi(registrations: <Json>[_sandboxRegistration()]);
    await _pump(tester, api);

    final Finder toolbarRaise =
        find.widgetWithText(OutlinedButton, 'Raise bill');
    expect(tester.widget<OutlinedButton>(toolbarRaise).onPressed, isNull,
        reason: 'nothing selected yet');

    await tester.tap(find.text('SI-2026-2027-000004'));
    await tester.pumpAndSettle();
    expect(tester.widget<OutlinedButton>(toolbarRaise).onPressed, isNotNull);

    await tester.tap(toolbarRaise);
    await tester.pumpAndSettle();
    expect(find.widgetWithText(TextField, 'Distance (km)'), findsOneWidget);
  });

  testWidgets('an e-way bill sends what the authority needs', (tester) async {
    final _EInvoiceApi api =
        _EInvoiceApi(registrations: <Json>[_sandboxRegistration()]);
    await _pump(tester, api);

    await tester.tap(find.text('Raise e-way bill'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextField, 'Distance (km)'), '450');
    await tester.enterText(
        find.widgetWithText(TextField, 'Vehicle number'), 'MH12AB1234');
    await tester.tap(find.widgetWithText(FilledButton, 'Raise'));
    await tester.pumpAndSettle();

    expect(api.sentBody!['distance_km'], '450');
    expect(api.sentBody!['transport_mode'], 'ROAD');
    expect(api.sentBody!['vehicle_number'], 'MH12AB1234');
  });

  testWidgets('a blank distance is left out and takes the delivery note\'s',
      (tester) async {
    // Backlog 67 row 5: the server fills what is blank from the notes billed.
    final _EInvoiceApi api =
        _EInvoiceApi(registrations: <Json>[_sandboxRegistration()]);
    await _pump(tester, api);

    await tester.tap(find.text('Raise e-way bill'));
    await tester.pumpAndSettle();
    expect(find.textContaining("Blank takes the delivery note's"),
        findsOneWidget);
    await tester.enterText(
        find.widgetWithText(TextField, 'Vehicle number'), 'MH12AB1234');
    await tester.tap(find.widgetWithText(FilledButton, 'Raise'));
    await tester.pumpAndSettle();

    expect(api.sentBody, isNotNull);
    expect(api.sentBody!.containsKey('distance_km'), isFalse);
    expect(api.sentBody!.containsKey('transporter_id'), isFalse);
    expect(api.sentBody!.containsKey('transporter_name'), isFalse);
  });

  testWidgets('a refused e-way bill keeps the dialog open with what was typed',
      (tester) async {
    // D-DLG-1: the dialog closed on Raise and the page made the call, so the
    // authority's refusal arrived as a toast and the vehicle number was lost.
    final _EInvoiceApi api =
        _EInvoiceApi(registrations: <Json>[_sandboxRegistration()])
          ..refuseEwayBill = 'The vehicle number is not valid.';
    await _pump(tester, api);

    await tester.tap(find.text('Raise e-way bill'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextField, 'Distance (km)'), '450');
    await tester.enterText(
        find.widgetWithText(TextField, 'Vehicle number'), 'BAD 1');
    await tester.tap(find.widgetWithText(FilledButton, 'Raise'));
    await tester.pumpAndSettle();

    expect(find.byType(EWayBillDialog), findsOneWidget);
    expect(find.text('The vehicle number is not valid.'), findsOneWidget);
    expect(find.text('450'), findsOneWidget);
    expect(find.text('BAD 1'), findsOneWidget);
    expect(api.sentBody, isNull);

    await tester.enterText(
        find.widgetWithText(TextField, 'Vehicle number'), 'MH12AB1234');
    await tester.tap(find.widgetWithText(FilledButton, 'Raise'));
    await tester.pumpAndSettle();
    expect(find.byType(EWayBillDialog), findsNothing);
    expect(api.sentBody!['vehicle_number'], 'MH12AB1234');
  });

  testWidgets('without EINVOICE_MANAGE nothing can be filed or withdrawn',
      (tester) async {
    final _EInvoiceApi api =
        _EInvoiceApi(registrations: <Json>[_sandboxRegistration()]);
    await _pump(
      tester,
      api,
      // Reading what was registered is part of running a sales desk; filing
      // with the authority is not.
      permissions: _permissions(perms: const ['EINVOICE_VIEW']),
    );

    expect(find.text('Raise e-way bill'), findsNothing);
    expect(find.text('Withdraw'), findsNothing);
  });

  testWidgets('a firm with no e-invoice permission sees nothing',
      (tester) async {
    final _EInvoiceApi api =
        _EInvoiceApi(registrations: <Json>[_sandboxRegistration()]);
    await _pump(tester, api, permissions: _permissions(perms: const []));

    expect(find.text('You cannot see registrations'), findsOneWidget);
    expect(api.requested, isEmpty);
  });

  testWidgets('the screen fits the smallest supported window', (tester) async {
    final _EInvoiceApi api =
        _EInvoiceApi(registrations: <Json>[_sandboxRegistration()]);
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: EInvoicePage(
          api: api,
          permissions: _permissions(),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    // Reachable, not merely rendered.
    await tester.tap(find.text('Raise e-way bill'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(FilledButton, 'Raise'), findsOneWidget);
  });

  testWidgets('an e-way bill shows its validity and its mode', (tester) async {
    final _EInvoiceApi api = _EInvoiceApi(
      registrations: <Json>[_sandboxRegistration()],
      bill: <String, dynamic>{
        'id': 'ewb-1',
        'sales_invoice_id': 'inv-1',
        'mode': 'SANDBOX',
        'status': 'GENERATED',
        'eway_bill_number': 'SBX123456789',
        'valid_until': '2026-09-05',
        'distance_km': '450.00',
        'transport_mode': 'ROAD',
        'transporter_id': null,
        'transporter_name': null,
        'vehicle_number': 'MH12AB1234',
        'error_code': null,
        'error_message': null,
      },
    );
    await _pump(tester, api);

    // The expiry is what a driver is stopped about, and the mode is what says
    // this one would not survive being stopped at all.
    expect(
      find.text('SBX123456789  ·  valid to 2026-09-05  (sandbox — nothing filed)'),
      findsOneWidget,
    );
    // A bill already raised is not offered again; withdrawing it is.
    expect(find.text('Raise e-way bill'), findsNothing);
    expect(find.text('Withdraw bill'), findsOneWidget);
  });

  testWidgets('a withdrawn e-way bill can be raised again from the screen',
      (tester) async {
    // The service raises a fresh bill over a withdrawn one, but the screen
    // offered Raise only where no bill row existed, so the second bill could
    // be had through the API alone (D-CMP-13).
    final _EInvoiceApi api = _EInvoiceApi(
      registrations: <Json>[_sandboxRegistration()],
      bill: <String, dynamic>{
        'id': 'ewb-1',
        'sales_invoice_id': 'inv-1',
        'mode': 'SANDBOX',
        'status': 'CANCELLED',
        'eway_bill_number': 'SBX123456789',
        'valid_until': '2026-09-05',
        'distance_km': '450.00',
        'transport_mode': 'ROAD',
        'transporter_id': null,
        'transporter_name': null,
        'vehicle_number': 'MH12AB1234',
        'error_code': null,
        'error_message': null,
      },
    );
    await _pump(tester, api);

    expect(find.text('Raise bill again'), findsOneWidget);
    expect(find.text('Withdraw bill'), findsNothing);

    await tester.tap(find.text('SI-2026-2027-000004'));
    await tester.pumpAndSettle();
    final Finder toolbarRaise =
        find.widgetWithText(OutlinedButton, 'Raise bill');
    expect(tester.widget<OutlinedButton>(toolbarRaise).onPressed, isNotNull);

    await tester.tap(find.text('Raise bill again'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(TextField, 'Distance (km)'), findsOneWidget);
  });

  testWidgets('phase 2 puts Withdraw on the selection bar, not a row column',
      (tester) async {
    // Review 2026-09-27: Withdraw and Try again were reachable only from
    // the row's own column.
    await _pump(
      tester,
      _EInvoiceApi(registrations: <Json>[_sandboxRegistration()]),
      phase2: true,
    );
    expect(find.widgetWithText(TextButton, 'Withdraw'), findsNothing);
    await tester.tap(find.text('SI-2026-2027-000004').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('selection-withdraw')), findsOneWidget);
  });

  testWidgets('the reason prompt is the shared one: Enter submits (D-DLG-10)',
      (tester) async {
    final _EInvoiceApi api =
        _EInvoiceApi(registrations: <Json>[_sandboxRegistration()]);
    await _pump(tester, api, phase2: true);
    await tester.tap(find.text('SI-2026-2027-000004').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('selection-withdraw')));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'Wrong customer');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();

    expect(api.sentBody, {'reason': 'Wrong customer'},
        reason: 'Enter sent the reason, and the prompt closed without the '
            'controller being used after disposal');
    expect(tester.takeException(), isNull);
  });

  testWidgets('each registration says how it reaches the portal',
      (tester) async {
    final _EInvoiceApi api = _EInvoiceApi(registrations: <Json>[
      <String, dynamic>{..._sandboxRegistration(), 'provider': 'OFFLINE'},
    ]);
    await _pump(tester, api);
    expect(find.text('Filing'), findsOneWidget);
    expect(find.text('Offline'), findsOneWidget);
  });

  testWidgets('a sandbox firm is not offered the offline steps',
      (tester) async {
    await _pump(tester, _EInvoiceApi());
    expect(find.text('Export for portal'), findsNothing);
    expect(find.text('Import portal result'), findsNothing);
  });

  testWidgets('offline: export sends the chosen invoices and saves the file',
      (tester) async {
    final _EInvoiceApi api = _EInvoiceApi(provider: 'OFFLINE');
    String? savedName;
    List<int>? savedBytes;
    await _pump(
      tester,
      api,
      saveExportFile: (name, bytes) async {
        savedName = name;
        savedBytes = bytes;
        return 'C:/out/$name';
      },
    );

    await tester.tap(find.text('Export for portal'));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(CheckboxListTile));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Export 1'));
    await tester.pumpAndSettle();

    expect(api.exportedIds, ['inv-9']);
    expect(savedName, startsWith('einvoice-'));
    expect(savedName, endsWith('.json'));
    expect(utf8.decode(savedBytes!), '[]');
  });

  testWidgets('offline: importing the portal result shows the counts',
      (tester) async {
    final _EInvoiceApi api = _EInvoiceApi(provider: 'OFFLINE');
    final Directory dir = Directory.systemTemp.createTempSync('einvoice');
    addTearDown(() => dir.deleteSync(recursive: true));
    final File result = File('${dir.path}/result.json')
      ..writeAsStringSync('[]');
    await _pump(
      tester,
      api,
      pickResultFile: () async => XFile(result.path),
    );

    await tester.tap(find.text('Import portal result'));
    // Reading the chosen file is real I/O outside the fake clock: wait for
    // the condition itself rather than a fixed delay (D-TEST-2).
    final Stopwatch elapsed = Stopwatch()..start();
    while (api.importedName == null &&
        elapsed.elapsed < const Duration(seconds: 20)) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 20)),
      );
      await tester.pump();
    }
    await tester.pumpAndSettle();

    expect(api.importedName, 'result.json');
    expect(find.textContaining('2 registered, 1 refused, 1 not matched'),
        findsOneWidget);
    expect(find.textContaining('Not matched: SI-X'), findsOneWidget);
    expect(find.textContaining('Refused: SI-3'), findsOneWidget);
  });

  testWidgets('a note registration shows its type and withdraws by note',
      (tester) async {
    final _EInvoiceApi api = _EInvoiceApi(registrations: <Json>[
      <String, dynamic>{
        ..._sandboxRegistration(),
        'sales_invoice_id': null,
        'document_type': 'CREDIT_NOTE',
        'credit_note_id': 'cn-1',
        'invoice_number': 'CN-2026-000001',
      },
    ]);
    await _pump(tester, api, phase2: true);

    expect(find.text('Credit note'), findsOneWidget);
    expect(find.text('CN-2026-000001'), findsOneWidget);
    await tester.tap(find.text('CN-2026-000001').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('selection-withdraw')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Wrong amount');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();

    expect(api.requested,
        contains('POST /api/v1/einvoice/credit-notes/cn-1/cancel'));
  });

  testWidgets('offline: approved notes are offered and sent in their own fields',
      (tester) async {
    final _EInvoiceApi api = _EInvoiceApi(provider: 'OFFLINE', notes: <Json>[
      <String, dynamic>{
        'kind': 'CREDIT',
        'id': 'cn-7',
        'credit_note_number': 'CN-7',
        'customer_name': 'Vijaya',
        'total_amount': '100.00',
        'status': 'APPROVED',
      },
      <String, dynamic>{
        'kind': 'DEBIT',
        'id': 'dn-8',
        'debit_note_number': 'DN-8',
        'customer_name': 'Vijaya',
        'total_amount': '50.00',
        'status': 'APPROVED',
      },
    ]);
    await _pump(
      tester,
      api,
      saveExportFile: (name, bytes) async => 'C:/out/$name',
    );

    await tester.tap(find.text('Export for portal'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Credit note CN-7'), findsOneWidget);
    expect(find.textContaining('Debit note DN-8'), findsOneWidget);
    await tester.tap(find.textContaining('Credit note CN-7'));
    await tester.tap(find.textContaining('Debit note DN-8'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Export 2'));
    await tester.pumpAndSettle();

    expect(api.exportedIds, isEmpty);
    expect(api.exportedCreditIds, ['cn-7']);
    expect(api.exportedDebitIds, ['dn-8']);
  });

  group('the To register list', () {
    Json item(String id, String number, String state, int? daysLeft,
            {String type = 'SALES_INVOICE', String? lastDay}) =>
        <String, dynamic>{
          'document_type': type,
          'document_id': id,
          'number': number,
          'on': '2026-09-01',
          'customer_name': 'Vijaya Super Stores',
          'amount': '1180.00',
          'registration_status': null,
          'registration_error': null,
          'last_day': lastDay ?? '2026-10-01',
          'days_left': daysLeft,
          'state': state,
        };

    Future<void> open(WidgetTester tester, _EInvoiceApi api) async {
      await _pump(tester, api, phase2: true);
      await tester.tap(find.byKey(const ValueKey('toolbar-more')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('To register'));
      await tester.pumpAndSettle();
    }

    testWidgets('shows each document with its badge', (tester) async {
      final _EInvoiceApi api = _EInvoiceApi(pending: <String, dynamic>{
        'thirty_day_rule_applies': true,
        'due_soon_days': 5,
        'items': [
          item('a', 'SI-1', 'LATE', -3),
          item('b', 'CN-2', 'DUE_SOON', 2, type: 'CREDIT_NOTE'),
          item('c', 'SI-3', 'OPEN', 20),
        ],
      });
      await open(tester, api);
      expect(find.text('Late'), findsOneWidget);
      expect(find.text('2 days left'), findsOneWidget);
      expect(find.text('Open'), findsOneWidget);
      expect(find.text('Credit note'), findsOneWidget);
      expect(find.textContaining('A late document cannot be registered'),
          findsOneWidget);
      expect(find.byKey(const ValueKey('to-register-not-applicable')),
          findsNothing);

      // A credit note is registered through its own endpoint.
      await tester.tap(find.widgetWithText(TextButton, 'Register').first);
      await tester.pumpAndSettle();
      expect(api.requested,
          contains('POST /api/v1/einvoice/credit-notes/b/register'));
    });

    testWidgets('a sales return is labelled and registered as a credit note',
        (tester) async {
      final _EInvoiceApi api = _EInvoiceApi(pending: <String, dynamic>{
        'thirty_day_rule_applies': true,
        'due_soon_days': 5,
        'items': [item('r1', 'SR-1', 'OPEN', 20, type: 'SALES_RETURN')],
      });
      await open(tester, api);
      expect(find.text('Sales return'), findsOneWidget);

      await tester.tap(find.widgetWithText(TextButton, 'Register'));
      await tester.pumpAndSettle();
      expect(api.requested,
          contains('POST /api/v1/einvoice/sales-returns/r1/register'));
    });

    testWidgets('says so where the 30-day limit does not apply',
        (tester) async {
      final _EInvoiceApi api = _EInvoiceApi(pending: <String, dynamic>{
        'thirty_day_rule_applies': false,
        'due_soon_days': 5,
        'items': [item('a', 'SI-1', 'OPEN', null, lastDay: '')],
      });
      await open(tester, api);
      expect(find.byKey(const ValueKey('to-register-not-applicable')),
          findsOneWidget);
      expect(find.text('Last day'), findsNothing);
      expect(find.text('SI-1'), findsOneWidget);
    });
  });
}
