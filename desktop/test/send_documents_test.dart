// MSG-4: the other documents go out by hand, by email.
//
// One dialog serves them all, so these pin what is sent for each document
// type (the exact body, and EMAIL), that the channel picker offers only Email
// for anything but an invoice, that a refusal stays on screen with the
// server's words, that the sales order and the receipt print from their own
// paths, and that the sales order screen offers Send to a person who holds
// `DOCUMENT_SEND` and not to one who does not.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/phase2/phase2_scope.dart';
import 'package:agency_desktop/ui/sales/sales_order_management_page.dart';
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

class _Api extends ApiClient {
  _Api({this.refuse = false, this.rows = const <Json>[]})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool refuse;
  final List<Json> rows;
  Json? sent;
  final List<String> downloaded = <String>[];

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
    if (path == '/api/v1/messaging/send') {
      if (refuse) throw ApiException('Email is not switched on.');
      sent = body;
      return <String, dynamic>{
        'data': <String, dynamic>{'id': 'msg-1'}
      };
    }
    if (path.endsWith('/summary')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'total': rows.length, 'draft': rows.length},
      };
    }
    return <String, dynamic>{
      'data': rows,
      'pagination': <String, dynamic>{'total_records': rows.length},
    };
  }

  @override
  Future<List<int>> downloadBytes(
    String path, {
    Map<String, String>? query,
    String method = 'GET',
    Json? body,
    bool retrying = false,
  }) async {
    downloaded.add(path);
    return <int>[1, 2, 3];
  }
}

Future<void> _open(WidgetTester tester, _Api api, String type) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: SendMessageDialog(
        api: api,
        invoiceId: 'doc-1',
        invoiceNumber: 'DOC-0001',
        documentType: type,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  for (final String type in const <String>[
    'SALES_QUOTATION',
    'SALES_ORDER',
    'CUSTOMER_STATEMENT',
    'RECEIPT',
    'PURCHASE_ORDER',
  ]) {
    testWidgets('$type is sent by email with the exact body', (tester) async {
      final _Api api = _Api();
      await _open(tester, api, type);
      await tester.enterText(
          find.byKey(const ValueKey('send-message-recipient')), 'x@y.com');
      await tester.enterText(
          find.byKey(const ValueKey('send-message-body')), 'Please find it');
      await tester.tap(find.byKey(const ValueKey('send-message-send')));
      await tester.pumpAndSettle();
      expect(api.sent, {
        'document_type': type,
        'document_id': 'doc-1',
        'channel': 'EMAIL',
        'recipient': 'x@y.com',
        'message': 'Please find it',
      });
    });

    testWidgets('$type offers only the Email channel', (tester) async {
      await _open(tester, _Api(), type);
      await tester.tap(find.byKey(const ValueKey('send-message-channel')));
      await tester.pumpAndSettle();
      expect(find.text('Email'), findsWidgets);
      expect(find.text('WhatsApp'), findsNothing);
      expect(find.text('SMS'), findsNothing);
    });
  }

  testWidgets('an invoice still offers all three channels', (tester) async {
    await _open(tester, _Api(), 'SALES_INVOICE');
    await tester.tap(find.byKey(const ValueKey('send-message-channel')));
    await tester.pumpAndSettle();
    expect(find.text('WhatsApp'), findsWidgets);
    expect(find.text('SMS'), findsWidgets);
  });

  testWidgets('a refusal stays open with the server message', (tester) async {
    await _open(tester, _Api(refuse: true), 'RECEIPT');
    await tester.tap(find.byKey(const ValueKey('send-message-send')));
    await tester.pumpAndSettle();
    expect(find.text('Email is not switched on.'), findsOneWidget);
    expect(find.byKey(const ValueKey('send-message-send')), findsOneWidget);
  });

  test('the sales order and the receipt print from their own paths', () async {
    final _Api api = _Api();
    await api.salesOrderPdf('so-9');
    await api.receiptPdf('rc-9');
    expect(api.downloaded, [
      '/api/v1/sales-orders/so-9/print',
      '/api/v1/receipts/rc-9/print',
    ]);
  });

  for (final bool allowed in const <bool>[true, false]) {
    testWidgets(
        'the sales order screen ${allowed ? 'offers' : 'withholds'} Send',
        (tester) async {
      tester.view.physicalSize = const Size(1366, 768);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final Directory temp = Directory.systemTemp.createTempSync('send-docs');
      addTearDown(() => temp.deleteSync(recursive: true));
      final _Api api = _Api(rows: [
        <String, dynamic>{
          'id': 'so-1',
          'order_number': 'SO-0001',
          'order_date': '2026-08-23',
          'reference_number': '',
          'status': 'APPROVED',
          'grand_total': '1000.00',
          'customer_id': 'cus-1',
        },
      ]);
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: SalesOrderManagementPage(
            api: api,
            preferences: DesktopPreferencesService(directory: temp),
            permissions: _permissions([
              'SALES_VIEW',
              if (allowed) 'DOCUMENT_SEND',
            ]),
            hasActiveFirm: true,
          ),
        ),
      ));
      await tester.pumpAndSettle();
      await tester.tap(find.text('SO-0001'));
      // Past the double-click window, which is when a click is a selection.
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('selection-print')), findsOneWidget);
      if (!allowed) {
        expect(find.byKey(const ValueKey('selection-send')), findsNothing);
        return;
      }
      await tester.tap(find.byKey(const ValueKey('selection-send')));
      await tester.pumpAndSettle();
      expect(find.text('Send SO-0001'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('send-message-send')));
      await tester.pumpAndSettle();
      expect(api.sent?['document_type'], 'SALES_ORDER');
      expect(api.sent?['document_id'], 'so-1');
      expect(tester.takeException(), isNull);
    });
  }
}
