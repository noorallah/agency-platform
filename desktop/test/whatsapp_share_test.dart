// Share a bill on WhatsApp by hand (MSG-1, backlog 51 A2).
//
// No account and no API: *WhatsApp* on the invoice list opens WhatsApp at the
// customer's number with the message typed in, saves the PDF and opens its
// folder, and puts the share on the bill's timeline. The machine's side --
// the file, the folder, the link -- is stood in for here.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:agency_desktop/ui/workspace/whatsapp_share.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(List<String> codes) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(<String, dynamic>{
          'roles': <String>['user'],
          'permissions': codes,
        }))).replaceAll('=', '')}.sig';

class _ShareApi extends ApiClient {
  _ShareApi({this.status = 'APPROVED', this.number = '919876543210'})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String status;
  final String? number;
  final List<(String, String, Json?)> calls = <(String, String, Json?)>[];

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
    calls.add((method, path, body));
    if (path.startsWith('/api/v1/messaging/share/sales-invoices/')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'document_type': 'SALES_INVOICE',
          'document_id': 'inv-1',
          'document_number': 'SI-26-27-000001',
          'phone': number == null ? null : '+91 98765 43210',
          'whatsapp_number': number,
          'text': 'Dear Buyer,\n\nPlease find attached invoice SI-26-27-000001 '
              'for 1,180.00 & more.',
          'file_name': 'SI-26-27-000001.pdf',
        },
      };
    }
    if (path == '/api/v1/messaging/shared') {
      return <String, dynamic>{'data': null};
    }
    if (method == 'GET' && path.endsWith('/summary')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'total': 1},
      };
    }
    if (method == 'GET' && path == '/api/v1/sales-invoices') {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'inv-1',
            'invoice_number': 'SI-26-27-000001',
            'invoice_date': '2026-10-03',
            'status': status,
            'grand_total': '1180.00',
            'customer_name': 'Buyer',
            'version': 2,
          },
        ],
        'pagination': <String, dynamic>{'total_records': 1},
      };
    }
    return <String, dynamic>{'data': <dynamic>[]};
  }

  @override
  Future<List<int>> downloadBytes(
    String path, {
    Map<String, String>? query,
    String method = 'GET',
    Json? body,
    bool retrying = false,
  }) async {
    calls.add(('GET', path, null));
    return utf8.encode('%PDF-1.4');
  }
}

class _Machine {
  final List<String> saved = <String>[];
  final List<String> revealed = <String>[];
  final List<String> opened = <String>[];

  WhatsAppSharer get sharer => WhatsAppSharer(
        savePdf: (name, bytes) async {
          saved.add(name);
          return 'C:/Users/me/Downloads/$name';
        },
        reveal: (path) async => revealed.add(path),
        openLink: (url) async => opened.add(url),
      );
}

Future<void> _open(
  WidgetTester tester,
  _ShareApi api,
  _Machine machine, {
  List<String> codes = const ['SALES_VIEW', 'DOCUMENT_SEND'],
}) async {
  tester.view.physicalSize = const Size(2400, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory dir = Directory.systemTemp.createTempSync('wa-share');
  addTearDown(() => dir.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: SalesInvoiceManagementPage(
          api: api,
          preferences: DesktopPreferencesService(directory: dir),
          permissions: PermissionService()
            ..applyAccessToken(_accessToken(codes)),
          hasActiveFirm: true,
          whatsApp: machine.sharer,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.text('SI-26-27-000001').first);
  // A second click would open the bill: the first selects once that window
  // has passed.
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

/// *WhatsApp* on the selected row's bar; only an enabled action is there.
final Finder _whatsApp = find.byKey(const ValueKey('selection-whatsapp'));

void main() {
  test('the link carries the number and the message, encoded', () {
    expect(
      WhatsAppSharer.link(number: '919876543210', text: 'Bill 1 & 2\nThanks'),
      'https://wa.me/919876543210?text=Bill%201%20%26%202%0AThanks',
    );
    expect(
      WhatsAppSharer.link(text: 'Hi'),
      'https://wa.me/?text=Hi',
    );
  });

  testWidgets('WhatsApp saves the bill, opens its folder and the chat, '
      'and puts the share on the timeline', (tester) async {
    final _ShareApi api = _ShareApi();
    final _Machine machine = _Machine();
    await _open(tester, api, machine);

    await tester.tap(_whatsApp);
    await tester.pumpAndSettle();

    expect(machine.saved, ['SI-26-27-000001.pdf']);
    expect(machine.revealed, ['C:/Users/me/Downloads/SI-26-27-000001.pdf']);
    expect(machine.opened, hasLength(1));
    expect(machine.opened.single, startsWith('https://wa.me/919876543210?text='));
    expect(
      Uri.parse(machine.opened.single).queryParameters['text'],
      contains('for 1,180.00 & more.'),
    );
    final (String, String, Json?) recorded = api.calls
        .singleWhere((call) => call.$2 == '/api/v1/messaging/shared');
    expect(recorded.$1, 'POST');
    expect(recorded.$3, <String, dynamic>{
      'document_type': 'SALES_INVOICE',
      'document_id': 'inv-1',
      'channel': 'WHATSAPP',
      'recipient': '+91 98765 43210',
    });
    expect(find.textContaining('Attach SI-26-27-000001.pdf'), findsOneWidget);
  });

  testWidgets('a customer with no number lets WhatsApp ask whom to send to',
      (tester) async {
    final _ShareApi api = _ShareApi(number: null);
    final _Machine machine = _Machine();
    await _open(tester, api, machine);

    await tester.tap(_whatsApp);
    await tester.pumpAndSettle();

    expect(machine.opened.single, startsWith('https://wa.me/?text='));
    expect(find.textContaining('no number: choose the chat'), findsOneWidget);
  });

  testWidgets('a draft cannot be shared', (tester) async {
    await _open(tester, _ShareApi(status: 'DRAFT'), _Machine());

    expect(_whatsApp, findsNothing);
  });

  testWidgets('without the right to send, there is no WhatsApp',
      (tester) async {
    final _ShareApi api = _ShareApi();
    final _Machine machine = _Machine();
    await _open(tester, api, machine, codes: const ['SALES_VIEW']);

    expect(_whatsApp, findsNothing);
    // The bar is there, with what the person may do.
    expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
  });
}
