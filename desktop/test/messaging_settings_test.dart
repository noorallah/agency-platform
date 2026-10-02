// Backlog 51, desktop half: Settings > Messaging.
//
// These pin: the schedule tab sends the three settings and warns when the
// server has no key; each channel shows its health and "Switch on" stays
// disabled until a test passes; the account form is drawn from the
// provider's own field list, never prefills a secret, and saves exactly
// `{provider, settings}`; the event editor sends its channels in the order
// shown; the log pages and resends; and the invoice Send dialog posts to
// `/send` and keeps the server's refusal on screen.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/settings/messaging_settings_dialog.dart';
import 'package:agency_desktop/ui/settings/send_message_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

Json _channel(
  String channel, {
  String? provider,
  bool enabled = false,
  String health = 'NOT_CONFIGURED',
  Map<String, String> settings = const {},
  List<String> secretsSet = const [],
  String? lastError,
}) =>
    <String, dynamic>{
      'channel': channel,
      'provider': provider,
      'is_enabled': enabled,
      'health': health,
      'is_configured': provider != null,
      'settings': settings,
      'secrets_set': secretsSet,
      'last_tested_at': null,
      'last_error': lastError,
    };

final List<Json> _providers = <Json>[
  {
    'provider': 'SMTP',
    'channel': 'EMAIL',
    'label': 'Your own email (SMTP)',
    'supports_status': false,
    'fields': [
      {
        'name': 'host',
        'label': 'Server',
        'secret': false,
        'required': true,
        'kind': 'text',
        'choices': <String>[],
      },
      {
        'name': 'port',
        'label': 'Port',
        'secret': false,
        'required': true,
        'kind': 'number',
        'choices': <String>[],
        'default': '587',
      },
      {
        'name': 'security',
        'label': 'Security',
        'secret': false,
        'required': true,
        'kind': 'choice',
        'choices': ['STARTTLS', 'SSL'],
        'default': 'STARTTLS',
      },
      {
        'name': 'password',
        'label': 'Password',
        'secret': true,
        'required': true,
        'kind': 'password',
        'choices': <String>[],
      },
    ],
  },
  {
    'provider': 'META_CLOUD',
    'channel': 'WHATSAPP',
    'label': 'WhatsApp Business (Meta)',
    'supports_status': true,
    'fields': [
      {
        'name': 'access_token',
        'label': 'Access token',
        'secret': true,
        'required': true,
        'kind': 'password',
        'choices': <String>[],
      },
    ],
  },
  {
    'provider': 'MSG91',
    'channel': 'SMS',
    'label': 'MSG91',
    'supports_status': false,
    'fields': [
      {
        'name': 'auth_key',
        'label': 'Auth key',
        'secret': true,
        'required': true,
        'kind': 'password',
        'choices': <String>[],
      },
    ],
  },
];

class _MessagingApi extends ApiClient {
  _MessagingApi({
    this.canStoreCredentials = true,
    this.refuseSend = false,
    List<Json>? channels,
  })  : channels = channels ??
            [
              _channel('EMAIL',
                  provider: 'SMTP',
                  health: 'UNTESTED',
                  settings: {'host': 'smtp.example.com', 'port': '465'},
                  secretsSet: ['password']),
              _channel('WHATSAPP'),
              _channel('SMS'),
            ],
        super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool canStoreCredentials;
  final bool refuseSend;
  final List<Json> channels;
  final List<String> calls = <String>[];
  final List<Json?> bodies = <Json?>[];
  Json? savedSettings;
  Json? savedAccount;
  Json? savedEvent;
  Json? sent;

  Json _ok(Object? data, {String message = ''}) =>
      {'success': true, 'data': data, 'message': message};

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
    bodies.add(body);
    if (path == '/api/v1/messaging/settings') {
      if (method == 'PUT') {
        savedSettings = body;
        return _ok({
          ...?body,
          'is_configured': true,
          'can_store_credentials': canStoreCredentials,
        });
      }
      return _ok({
        'is_enabled': false,
        'due_soon_days': 3,
        'overdue_every_days': 7,
        'is_configured': false,
        'can_store_credentials': canStoreCredentials,
      });
    }
    if (path == '/api/v1/messaging/providers') return _ok(_providers);
    if (path == '/api/v1/messaging/channels') return _ok(channels);
    if (path.startsWith('/api/v1/messaging/channels/')) {
      final List<String> parts = path.split('/');
      final String code = parts[5];
      final int index = channels.indexWhere((c) => c['channel'] == code);
      if (parts.length == 6 && method == 'PUT') {
        savedAccount = body;
        channels[index] = _channel(code,
            provider: body!['provider'] as String, health: 'UNTESTED');
        return _ok(channels[index],
            message: 'Account saved. Test it before switching the channel on.');
      }
      switch (parts.last) {
        case 'test':
          channels[index] = {...channels[index], 'health': 'OK'};
          return _ok(channels[index], message: 'Test passed.');
        case 'enable':
          channels[index] = {...channels[index], 'is_enabled': true};
          return _ok(channels[index]);
        case 'disable':
          channels[index] = {...channels[index], 'is_enabled': false};
          return _ok(channels[index]);
      }
    }
    if (path == '/api/v1/messaging/events') {
      return _ok([
        {
          'code': 'INVOICE_ISSUED',
          'label': 'Invoice issued',
          'document_type': 'SALES_INVOICE',
          'variables': ['customer_name', 'invoice_number'],
          'is_reminder': false,
          'attaches_pdf': true,
          'default_subject': 'Invoice {{invoice_number}}',
          'default_body': 'Dear {{customer_name}}',
        },
      ]);
    }
    if (path == '/api/v1/messaging/event-configs') {
      return _ok([
        {
          'event_code': 'INVOICE_ISSUED',
          'label': 'Invoice issued',
          'is_enabled': true,
          'channels': [
            {'channel': 'WHATSAPP', 'is_enabled': true, 'priority': 1},
            {'channel': 'EMAIL', 'is_enabled': true, 'priority': 2},
          ],
        },
      ]);
    }
    if (path.startsWith('/api/v1/messaging/event-configs/')) {
      savedEvent = body;
      return _ok({
        'event_code': 'INVOICE_ISSUED',
        'label': 'Invoice issued',
        'is_enabled': true,
        'channels': body!['channels'],
      });
    }
    if (path == '/api/v1/messaging/messages' && method == 'GET') {
      return {
        'success': true,
        'data': [
          {
            'id': 'msg-1',
            'event_code': 'INVOICE_ISSUED',
            'document_number': 'INV-0001',
            'channel': 'EMAIL',
            'recipient': 'a@example.com',
            'status': 'FAILED',
            'reason': 'Mailbox full',
            'attempts': 3,
            'created_at': '2026-10-01T10:00:00Z',
          },
        ],
        'pagination': {'total_records': 1},
      };
    }
    if (path.endsWith('/resend')) {
      return _ok({'id': 'msg-2'});
    }
    if (path == '/api/v1/messaging/send') {
      if (refuseSend) throw ApiException('Email is not switched on.');
      sent = body;
      return _ok({'id': 'msg-3'});
    }
    throw StateError('unexpected $method $path');
  }
}

Future<void> _pump(
  WidgetTester tester,
  _MessagingApi api, {
  List<String> codes = const ['SETTINGS_VIEW', 'SETTINGS_UPDATE'],
}) async {
  tester.view.physicalSize = const Size(1600, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: MessagingSettingsDialog(api: api, permissions: _permissions(codes)),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _openTab(WidgetTester tester, String name) async {
  await tester.tap(find.text(name));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the schedule tab saves the switch and the three day counts',
      (tester) async {
    final _MessagingApi api = _MessagingApi();
    await _pump(tester, api);
    expect(find.byKey(const ValueKey('messaging-key-warning')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('messaging-master-switch')));
    await tester.enterText(
        find.byKey(const ValueKey('messaging-due-soon-days')), '5');
    await tester.enterText(
        find.byKey(const ValueKey('messaging-overdue-days')), '10');
    // Decision A12: older bills are not reminded.
    expect(
        tester
            .widget<TextField>(
                find.byKey(const ValueKey('messaging-overdue-stop-after')))
            .controller!
            .text,
        '90');
    await tester.enterText(
        find.byKey(const ValueKey('messaging-overdue-stop-after')), '60');
    await tester.tap(find.byKey(const ValueKey('messaging-settings-save')));
    await tester.pumpAndSettle();

    expect(api.savedSettings, {
      'is_enabled': true,
      'due_soon_days': 5,
      'overdue_every_days': 10,
      'overdue_stop_after_days': 60,
    });
  });

  testWidgets('without a server key the page says so', (tester) async {
    await _pump(tester, _MessagingApi(canStoreCredentials: false));
    expect(find.byKey(const ValueKey('messaging-key-warning')), findsOneWidget);
    expect(find.textContaining('AGENCY_MESSAGING_KEY'), findsOneWidget);
  });

  testWidgets('a day count out of range is refused before it is sent',
      (tester) async {
    final _MessagingApi api = _MessagingApi();
    await _pump(tester, api);
    await tester.enterText(
        find.byKey(const ValueKey('messaging-due-soon-days')), '99');
    await tester.tap(find.byKey(const ValueKey('messaging-settings-save')));
    await tester.pumpAndSettle();
    expect(api.savedSettings, isNull);
    expect(find.byKey(const ValueKey('messaging-settings-error')),
        findsOneWidget);
  });

  testWidgets('Switch on stays disabled until the channel tests OK',
      (tester) async {
    final _MessagingApi api = _MessagingApi();
    await _pump(tester, api);
    await _openTab(tester, 'Channels');

    FilledButton enable() => tester.widget<FilledButton>(
        find.byKey(const ValueKey('messaging-enable-EMAIL')));
    expect(find.text('Your own email (SMTP)'), findsOneWidget);
    expect(find.text('Not tested yet'), findsOneWidget);
    expect(enable().onPressed, isNull);
    // A channel with no account cannot be tested or switched on.
    expect(
        tester
            .widget<OutlinedButton>(
                find.byKey(const ValueKey('messaging-test-WHATSAPP')))
            .onPressed,
        isNull);
    expect(find.text('Set up'), findsNWidgets(2));
    expect(find.text('Replace account'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('messaging-test-EMAIL')));
    await tester.pumpAndSettle();
    expect(find.text('Working'), findsOneWidget);
    expect(enable().onPressed, isNotNull);

    await tester.tap(find.byKey(const ValueKey('messaging-enable-EMAIL')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('POST /api/v1/messaging/channels/EMAIL/enable'));
    expect(find.text('Switched on'), findsOneWidget);
  });

  testWidgets('the account form is drawn from the provider and never '
      'prefills a secret', (tester) async {
    final _MessagingApi api = _MessagingApi();
    await _pump(tester, api);
    await _openTab(tester, 'Channels');
    await tester.tap(find.byKey(const ValueKey('messaging-setup-EMAIL')));
    await tester.pumpAndSettle();

    // Every field the provider lists, and no other.
    for (final String name in ['host', 'port', 'security', 'password']) {
      expect(find.byKey(ValueKey('messaging-field-$name')), findsOneWidget);
    }
    // Public fields prefill from what was saved; defaults fill the rest.
    expect(find.text('smtp.example.com'), findsOneWidget);
    expect(find.text('465'), findsOneWidget);
    // The secret is empty and says it is saved.
    expect(find.text('saved — leave blank to keep'), findsOneWidget);
    final TextField password = tester.widget<TextField>(find.descendant(
      of: find.byKey(const ValueKey('messaging-field-password')),
      matching: find.byType(TextField),
    ));
    expect(password.controller!.text, isEmpty);
    expect(password.obscureText, isTrue);

    await tester.tap(find.byKey(const ValueKey('messaging-account-save')));
    await tester.pumpAndSettle();

    // Exactly {provider, settings}; the blank secret is left out so the
    // saved one is kept.
    expect(api.savedAccount, {
      'provider': 'SMTP',
      'settings': {'host': 'smtp.example.com', 'port': '465', 'security': 'STARTTLS'},
    });
  });

  testWidgets('a typed secret is sent', (tester) async {
    final _MessagingApi api = _MessagingApi();
    await _pump(tester, api);
    await _openTab(tester, 'Channels');
    await tester.tap(find.byKey(const ValueKey('messaging-setup-WHATSAPP')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('messaging-field-access_token')), 'tok-1');
    await tester.tap(find.byKey(const ValueKey('messaging-account-save')));
    await tester.pumpAndSettle();
    expect(api.savedAccount, {
      'provider': 'META_CLOUD',
      'settings': {'access_token': 'tok-1'},
    });
  });

  testWidgets('the event editor sends its channels in the order shown',
      (tester) async {
    final _MessagingApi api = _MessagingApi();
    await _pump(tester, api);
    await _openTab(tester, 'Events');
    expect(find.text('WhatsApp  →  Email'), findsOneWidget);

    await tester.tap(
        find.byKey(const ValueKey('messaging-event-edit-INVOICE_ISSUED')));
    await tester.pumpAndSettle();
    expect(find.textContaining('{{1}} customer_name, {{2}} invoice_number'),
        findsOneWidget);
    await tester.enterText(
        find.byKey(const ValueKey('messaging-rule-template-0')), 'invoice_v1');
    // Move the email rule ahead of WhatsApp.
    await tester.tap(find.byTooltip('Try earlier').at(1));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('messaging-event-save')));
    await tester.pumpAndSettle();

    final List<dynamic> sent = api.savedEvent!['channels'] as List<dynamic>;
    expect(sent.map((rule) => (rule as Map)['channel']), ['EMAIL', 'WHATSAPP']);
    expect((sent[1] as Map)['template_name'], 'invoice_v1');
    expect((sent[1] as Map)['template_language'], 'en');
    expect((sent[0] as Map)['template_name'], isNull);
  });

  testWidgets('the log lists messages and resends the one selected',
      (tester) async {
    final _MessagingApi api = _MessagingApi();
    await _pump(tester, api, codes: const ['SETTINGS_VIEW', 'DOCUMENT_SEND']);
    await _openTab(tester, 'Message log');
    expect(find.text('INV-0001'), findsOneWidget);
    expect(find.text('Mailbox full'), findsOneWidget);

    FilledButton resend() => tester
        .widget<FilledButton>(find.byKey(const ValueKey('messaging-log-resend')));
    expect(resend().onPressed, isNull);
    await tester.tap(find.text('INV-0001'));
    await tester.pumpAndSettle();
    expect(resend().onPressed, isNotNull);
    await tester.tap(find.byKey(const ValueKey('messaging-log-resend')));
    await tester.pumpAndSettle();
    expect(
        api.calls, contains('POST /api/v1/messaging/messages/msg-1/resend'));
  });

  testWidgets('without the update permission nothing can be changed',
      (tester) async {
    await _pump(tester, _MessagingApi(), codes: const ['SETTINGS_VIEW']);
    expect(find.byKey(const ValueKey('messaging-settings-save')), findsNothing);
    await _openTab(tester, 'Channels');
    expect(
        tester
            .widget<OutlinedButton>(
                find.byKey(const ValueKey('messaging-setup-EMAIL')))
            .onPressed,
        isNull);
  });

  testWidgets('the Send dialog posts to /send and says it is queued',
      (tester) async {
    final _MessagingApi api = _MessagingApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () => showDialog<bool>(
              context: context,
              builder: (_) => SendMessageDialog(
                api: api,
                invoiceId: 'inv-1',
                invoiceNumber: 'INV-0001',
              ),
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('send-message-recipient')), 'b@example.com');
    await tester.tap(find.byKey(const ValueKey('send-message-send')));
    await tester.pumpAndSettle();
    expect(api.sent, {
      'document_type': 'SALES_INVOICE',
      'document_id': 'inv-1',
      'channel': 'EMAIL',
      'recipient': 'b@example.com',
    });
    expect(find.text('Queued to send.'), findsOneWidget);
  });

  testWidgets('a refused send stays open with the server\'s message',
      (tester) async {
    final _MessagingApi api = _MessagingApi(refuseSend: true);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SendMessageDialog(
          api: api,
          invoiceId: 'inv-1',
          invoiceNumber: 'INV-0001',
        ),
      ),
    ));
    await tester.tap(find.byKey(const ValueKey('send-message-send')));
    await tester.pumpAndSettle();
    expect(find.text('Email is not switched on.'), findsOneWidget);
    expect(find.byKey(const ValueKey('send-message-send')), findsOneWidget);
  });
}
