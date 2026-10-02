// Payment reminders by hand (MSG-3, backlog 51 A4).
//
// *Remind* sends the customer their statement of account: by email through
// the firm's account, or from the person's own WhatsApp the way an invoice is
// shared. The server refuses a customer marked "no reminders", or one who owes
// nothing, by name -- and the dialog stays open with the reason.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/workspace/remind_dialog.dart';
import 'package:agency_desktop/ui/workspace/whatsapp_share.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _RemindApi extends ApiClient {
  _RemindApi({this.refusal})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// What the server says instead of queueing, if anything.
  final String? refusal;
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
    if (refusal != null) throw ApiException(refusal!, statusCode: 422);
    if (path == '/api/v1/messaging/share/customer-statements/cust-1') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'document_type': 'CUSTOMER_STATEMENT',
          'document_id': 'cust-1',
          'document_number': 'Statement 03-Oct-2026',
          'phone': '+91 98765 43210',
          'whatsapp_number': '919876543210',
          'text': 'Dear Buyer, your balance with us is 1,180.00.',
          'file_name': 'statement-C001-2026-10-03.pdf',
        },
      };
    }
    return <String, dynamic>{'data': null};
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
  final List<String> opened = <String>[];

  WhatsAppSharer get sharer => WhatsAppSharer(
        savePdf: (name, bytes) async {
          saved.add(name);
          return 'C:/Users/me/Downloads/$name';
        },
        reveal: (_) async {},
        openLink: (url) async => opened.add(url),
      );
}

Future<void> _open(WidgetTester tester, _RemindApi api, _Machine machine) async {
  tester.view.physicalSize = const Size(1400, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => Center(
          child: FilledButton(
            onPressed: () => showDialog<bool>(
              context: context,
              builder: (_) => RemindDialog(
                api: api,
                customerId: 'cust-1',
                customerName: 'Buyer',
                whatsApp: machine.sharer,
              ),
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('by email, the reminder is queued for the customer',
      (tester) async {
    final _RemindApi api = _RemindApi();
    await _open(tester, api, _Machine());

    await tester.enterText(
        find.byKey(const ValueKey('remind-recipient')), 'accounts@buyer.in');
    await tester.tap(find.byKey(const ValueKey('remind-send')));
    await tester.pumpAndSettle();

    final (String, String, Json?) call = api.calls.single;
    expect((call.$1, call.$2), ('POST', '/api/v1/messaging/remind'));
    expect(call.$3, <String, dynamic>{
      'customer_id': 'cust-1',
      'recipient': 'accounts@buyer.in',
    });
    expect(find.byType(RemindDialog), findsNothing);
    expect(find.textContaining('Reminder queued'), findsOneWidget);
  });

  testWidgets('a customer who asked for no reminders is refused, by name, '
      'and nothing typed is lost', (tester) async {
    final _RemindApi api = _RemindApi(
      refusal: 'Buyer has asked for no reminders (on the customer record).',
    );
    await _open(tester, api, _Machine());

    await tester.enterText(
        find.byKey(const ValueKey('remind-message')), 'Please pay.');
    await tester.tap(find.byKey(const ValueKey('remind-send')));
    await tester.pumpAndSettle();

    expect(find.byType(RemindDialog), findsOneWidget);
    expect(find.textContaining('asked for no reminders'), findsOneWidget);
    expect(find.text('Please pay.'), findsOneWidget);
  });

  testWidgets('on WhatsApp, the statement is saved and the chat opened, '
      'and the reminder recorded', (tester) async {
    final _RemindApi api = _RemindApi();
    final _Machine machine = _Machine();
    await _open(tester, api, machine);

    await tester.tap(find.text('WhatsApp, by hand'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('remind-send')));
    await tester.pumpAndSettle();

    expect(machine.saved, ['statement-C001-2026-10-03.pdf']);
    expect(machine.opened.single,
        startsWith('https://wa.me/919876543210?text=Dear%20Buyer'));
    expect(
      api.calls.map((call) => call.$2),
      [
        '/api/v1/messaging/share/customer-statements/cust-1',
        '/api/v1/customers/cust-1/statement/print',
        '/api/v1/messaging/shared',
      ],
    );
    expect(api.calls.last.$3, <String, dynamic>{
      'document_type': 'CUSTOMER_STATEMENT',
      'document_id': 'cust-1',
      'channel': 'WHATSAPP',
      'recipient': '+91 98765 43210',
    });
    expect(find.byType(RemindDialog), findsNothing);
  });
}
