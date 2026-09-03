// The e-invoice screen listed registrations and could not make one.
//
// `registerEInvoice` had a route, a client method and no control anywhere, so
// from the desktop no invoice had ever been registered with the tax authority
// -- the module could not do the one thing it exists for. Its own empty state
// said to register "from the invoice itself", describing a button nobody had
// built.
//
// These pin the control, and the two things about it that are easy to get
// wrong: a refusal is not an exception, and a refusal is not final.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/einvoice_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

class _Api extends ApiClient {
  _Api({this.registrations = const <Json>[], this.invoices = const <Json>[], this.answer})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> registrations;
  final List<Json> invoices;

  /// What the portal answers. A refusal comes back as a FAILED row, not an
  /// exception, which is the case this screen has to report honestly.
  final Json? answer;

  final List<String> registered = <String>[];

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
    if (method == 'POST' && path.contains('/register')) {
      registered.add(path);
      return <String, dynamic>{'data': answer};
    }
    if (path.contains('einvoice/registrations')) {
      return <String, dynamic>{
        'data': registrations,
        'pagination': <String, dynamic>{'total_records': registrations.length},
      };
    }
    if (path.contains('sales-invoices')) {
      return <String, dynamic>{
        'data': invoices,
        'pagination': <String, dynamic>{'total_records': invoices.length},
      };
    }
    return <String, dynamic>{'data': null};
  }
}

Json _registration({
  required String invoiceId,
  String status = 'REGISTERED',
  String error = '',
}) =>
    <String, dynamic>{
      'id': 'reg-$invoiceId',
      'sales_invoice_id': invoiceId,
      'sales_invoice_number': 'SI-0001',
      'mode': 'SANDBOX',
      'status': status,
      'irn': status == 'REGISTERED' ? 'SBX-IRN-1' : '',
      'acknowledgement_number': '',
      'signed_qr_code': '',
      'error_code': '',
      'error_message': error,
      'attempts': 1,
      'cancellation_reason': '',
    };

Json _invoice(String id, String number, String status) => <String, dynamic>{
      'id': id,
      'invoice_number': number,
      'status': status,
      'grand_total': '1000.00',
    };

Future<void> _open(WidgetTester tester, _Api api, List<String> codes) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: EInvoicePage(
        api: api,
        permissions: _permissions(codes),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('an approved invoice can be registered', (tester) async {
    final _Api api = _Api(
      invoices: <Json>[
        _invoice('inv-1', 'SI-0001', 'APPROVED'),
        // A draft is refused by the payload builder, so offering it spends a
        // round trip to be told so.
        _invoice('inv-2', 'SI-0002', 'DRAFT'),
      ],
      answer: _registration(invoiceId: 'inv-1'),
    );
    await _open(tester, api, const ['EINVOICE_VIEW', 'EINVOICE_MANAGE']);

    await tester.tap(find.widgetWithText(FilledButton, 'Register an invoice'));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();

    expect(find.textContaining('SI-0001'), findsWidgets);
    expect(find.textContaining('SI-0002'), findsNothing);
  });

  testWidgets('an invoice already registered is not offered again',
      (tester) async {
    final _Api api = _Api(
      registrations: <Json>[_registration(invoiceId: 'inv-1')],
      invoices: <Json>[
        _invoice('inv-1', 'SI-0001', 'APPROVED'),
        _invoice('inv-3', 'SI-0003', 'APPROVED'),
      ],
      answer: _registration(invoiceId: 'inv-3'),
    );
    await _open(tester, api, const ['EINVOICE_VIEW', 'EINVOICE_MANAGE']);

    await tester.tap(find.widgetWithText(FilledButton, 'Register an invoice'));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();

    // Registering it twice is refused by the service; the picker should not
    // walk somebody into that.
    expect(find.textContaining('SI-0003'), findsWidgets);
    expect(find.textContaining('SI-0001'), findsNothing);
  });

  testWidgets('a refusal is reported as a refusal, not as a success',
      (tester) async {
    final _Api api = _Api(
      invoices: <Json>[_invoice('inv-1', 'SI-0001', 'APPROVED')],
      // No exception -- the portal answered, and the answer was no.
      answer: _registration(
        invoiceId: 'inv-1',
        status: 'FAILED',
        error: 'The buyer GSTIN is not registered.',
      ),
    );
    await _open(tester, api, const ['EINVOICE_VIEW', 'EINVOICE_MANAGE']);

    await tester.tap(find.widgetWithText(FilledButton, 'Register an invoice'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Register'));
    await tester.pumpAndSettle();

    expect(api.registered, hasLength(1));
    // Telling somebody their invoice is filed when the portal refused it is
    // the one failure this screen must not have.
    expect(find.textContaining('refused'), findsOneWidget);
    expect(find.textContaining('The buyer GSTIN is not registered.'),
        findsOneWidget);
  });

  testWidgets('a refused registration can be tried again', (tester) async {
    final _Api api = _Api(
      registrations: <Json>[
        _registration(
          invoiceId: 'inv-1',
          status: 'FAILED',
          error: 'The buyer GSTIN is not registered.',
        ),
      ],
      answer: _registration(invoiceId: 'inv-1'),
    );
    await _open(tester, api, const ['EINVOICE_VIEW', 'EINVOICE_MANAGE']);

    // The service keeps the row and counts the attempt, so a refusal is a
    // state to correct and retry rather than a dead end.
    await tester.tap(find.widgetWithText(TextButton, 'Try again'));
    await tester.pumpAndSettle();

    expect(api.registered.single, contains('inv-1'));
  });

  testWidgets('reading registrations is not authority to make one',
      (tester) async {
    await _open(tester, _Api(), const ['EINVOICE_VIEW']);

    expect(
      tester
          .widget<FilledButton>(
              find.widgetWithText(FilledButton, 'Register an invoice'))
          .onPressed,
      isNull,
    );
  });
}
