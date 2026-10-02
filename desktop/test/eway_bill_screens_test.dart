// Backlog 77 row 10, on the two screens that move a consignment: dispatching a
// delivery note and approving a sales invoice offer the e-way bill when the
// document is worth more than the firm's limit, and a delivery note has its
// own E-way bill action.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/delivery_notes/delivery_note_management_page.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>[
      'SALES_VIEW',
      'SALES_APPROVE',
      'EINVOICE_VIEW',
      'EINVOICE_MANAGE',
    ],
  }));

class _Api extends ApiClient {
  _Api({
    this.total = '82000.00',
    this.noteStatus = 'APPROVED',
    this.settingsReadable = true,
  }) : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String total;
  final String noteStatus;
  final bool settingsReadable;
  final List<String> calls = <String>[];

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
    if (path == '/api/v1/tax-framework/gst-compliance-settings') {
      if (!settingsReadable) throw ApiException('no', statusCode: 403);
      return <String, dynamic>{
        'data': <String, dynamic>{
          'einvoice_applicable_from': null,
          'thirty_day_rule_from': null,
          'dispatch_without_invoice': 'OFF',
          'route_sale_needs_invoice': false,
          'eway_bill_limit': '50000.00',
          'is_configured': true,
        },
      };
    }
    if (path.endsWith('/eway-bill')) {
      return <String, dynamic>{'data': null};
    }
    if (path.endsWith('/dispatch-check')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'enforcement': 'OFF',
          'message': null,
          'would_block': false,
        },
      };
    }
    if (method == 'GET' && path == '/api/v1/delivery-notes') {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'dn-1',
            'delivery_note_number': 'DN-0001',
            'customer_name': 'Customer 1',
            'delivery_date': '2026-10-01',
            'status': noteStatus,
            'grand_total': total,
            'version': 1,
          },
        ],
        'pagination': <String, dynamic>{'total_records': 1},
      };
    }
    if (method == 'GET' && path == '/api/v1/sales-invoices') {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'inv-1',
            'invoice_number': 'SI-0001',
            'invoice_date': '2026-10-02',
            'customer_name': 'Customer 1',
            'status': 'DRAFT',
            'grand_total': total,
            'version': 1,
          },
        ],
        'pagination': <String, dynamic>{'total_records': 1},
      };
    }
    if (method == 'POST') {
      return <String, dynamic>{'data': const <String, dynamic>{}};
    }
    return <String, dynamic>{'data': const <dynamic>[]};
  }
}

Future<void> _pumpNotes(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory dir = Directory.systemTemp.createTempSync('eway-screens');
  addTearDown(() => dir.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: DeliveryNoteManagementPage(
          api: api,
          preferences: DesktopPreferencesService(directory: dir),
          permissions: _permissions(),
          hasActiveFirm: true,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.text('DN-0001'));
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

void main() {
  group('delivery note', () {
    testWidgets('dispatching a note over the limit offers its e-way bill',
        (tester) async {
      final _Api api = _Api();
      await _pumpNotes(tester, api);
      await tester.tap(find.byKey(const ValueKey('selection-dispatch')));
      await tester.pumpAndSettle();
      expect(api.calls, contains('POST /api/v1/delivery-notes/dn-1/dispatch'));
      expect(find.byKey(const ValueKey('eway-nudge')), findsOneWidget);
      expect(find.text('Raise'), findsOneWidget);
      expect(find.text('Record'), findsOneWidget);
      expect(find.text('Later'), findsOneWidget);
    });

    testWidgets('a note under the limit is quiet',
        (tester) async {
      final _Api under = _Api(total: '1000.00');
      await _pumpNotes(tester, under);
      await tester.tap(find.byKey(const ValueKey('selection-dispatch')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('eway-nudge')), findsNothing);
    });

    testWidgets('unreadable settings are quiet, and the dispatch still ran',
        (tester) async {
      final _Api api = _Api(settingsReadable: false);
      await _pumpNotes(tester, api);
      await tester.tap(find.byKey(const ValueKey('selection-dispatch')));
      await tester.pumpAndSettle();
      expect(api.calls, contains('POST /api/v1/delivery-notes/dn-1/dispatch'));
      expect(find.byKey(const ValueKey('eway-nudge')), findsNothing);
    });

    testWidgets('an approved note has an E-way bill action', (tester) async {
      final _Api api = _Api();
      await _pumpNotes(tester, api);
      await tester.tap(find.byKey(const ValueKey('selection-eway-bill')));
      await tester.pumpAndSettle();
      expect(find.text('E-way bill: DN-0001'), findsOneWidget);
      expect(find.byKey(const ValueKey('note-eway-raise')), findsOneWidget);
      expect(
        api.calls,
        contains('GET /api/v1/einvoice/delivery-notes/dn-1/eway-bill'),
      );
    });

    testWidgets('a draft note is not offered one', (tester) async {
      await _pumpNotes(tester, _Api(noteStatus: 'DRAFT'));
      expect(find.byKey(const ValueKey('selection-eway-bill')), findsNothing);
    });
  });

  group('sales invoice', () {
    testWidgets('approving an invoice over the limit offers its e-way bill',
        (tester) async {
      final _Api api = _Api();
      tester.view.physicalSize = const Size(1700, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final Directory dir = Directory.systemTemp.createTempSync('eway-si');
      addTearDown(() => dir.deleteSync(recursive: true));
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: SalesInvoiceManagementPage(
            api: api,
            preferences: DesktopPreferencesService(directory: dir),
            permissions: _permissions(),
            hasActiveFirm: true,
          ),
        ),
      ));
      await tester.pumpAndSettle();
      await tester.tap(find.text('SI-0001'));
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(OutlinedButton, 'Approve').first);
      await tester.pumpAndSettle();
      expect(api.calls, contains('POST /api/v1/sales-invoices/inv-1/approve'));
      expect(find.byKey(const ValueKey('eway-nudge')), findsOneWidget);
      expect(
        api.calls,
        contains('GET /api/v1/einvoice/invoices/inv-1/eway-bill'),
      );
    });
  });
}
