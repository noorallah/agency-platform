// The one thing this screen must never do is let a rehearsal read as a filing.
//
// A sandbox registration files nothing with the tax authority, and its
// reference means nothing outside this system. Somebody eventually prints a
// screen and carries it to a check post, so the mode travels with the
// reference everywhere it is shown.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/einvoice_page.dart';
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
  _EInvoiceApi({this.registrations = const [], this.bill})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> registrations;
  final Json? bill;
  final List<String> requested = <String>[];
  Json? sentBody;

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
    if (path.contains('/eway-bill')) {
      if (method == 'POST') sentBody = body;
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
    return <String, dynamic>{'data': const <Json>[]};
  }
}

Json _sandboxRegistration() => <String, dynamic>{
      'id': 'reg-1',
      'sales_invoice_id': 'inv-1',
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
}) async {
  tester.view.physicalSize = const Size(1700, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: EInvoicePage(
        api: api,
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
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
}
