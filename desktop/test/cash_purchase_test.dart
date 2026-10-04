// PG-3 (backlog 86 #19): a cash purchase is approved and paid in one step.
//
// The bill's Approve step opens a dialog with a "Paid now" section for
// somebody holding PAYMENT_CREATE; ticking it sends the payment block with
// the approval, leaving it unticked sends the approval exactly as before.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/document_framework/document_steps.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_steps.dart';
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
  _Api({this.refusal})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String? refusal;
  final List<({String path, Json? body})> posts = [];

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
    // Reads (the TDS proposal, PG-5) are not what these cases are about.
    if (method != 'POST') {
      return <String, dynamic>{'success': true, 'data': <String, dynamic>{}};
    }
    posts.add((path: path, body: body));
    if (refusal != null) throw ApiException(refusal!, statusCode: 400);
    return <String, dynamic>{'success': true, 'data': <String, dynamic>{}};
  }
}

Future<void> _open(
  WidgetTester tester,
  _Api api,
  List<String> codes,
  Size size,
) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: DocumentStepStrip<DocumentRef>(
        record: const DocumentRef(id: 'pi-1', number: 'PI-1', status: 'DRAFT'),
        steps: purchaseInvoiceSteps(api, _permissions(codes)),
      ),
    ),
  ));
  await tester.tap(find.byKey(const ValueKey('document-step-approve')));
  await tester.pumpAndSettle();
}

const List<String> _payer = ['PURCHASE_APPROVE', 'PAYMENT_CREATE'];

void main() {
  testWidgets('approving with Paid now sends the payment block', (
    tester,
  ) async {
    final _Api api = _Api();
    await _open(tester, api, _payer, const Size(1366, 768));
    await tester.tap(find.byKey(const ValueKey('paid-now')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('approve-bill-confirm')));
    await tester.pumpAndSettle();
    expect(api.posts.single.path, '/api/v1/purchase-invoices/pi-1/approve');
    final Map payment = api.posts.single.body!['payment'] as Map;
    expect(payment['method'], 'CASH');
    expect(payment['payment_mode'], 'CASH');
    // Blank means the full bill and the bill's date; never prefilled.
    expect(payment['amount'], isNull);
    expect(payment['payment_date'], isNull);
  });

  testWidgets('unticked sends no payment block', (tester) async {
    final _Api api = _Api();
    await _open(tester, api, _payer, const Size(1366, 768));
    await tester.tap(find.byKey(const ValueKey('approve-bill-confirm')));
    await tester.pumpAndSettle();
    expect(api.posts.single.body, isEmpty);
  });

  testWidgets('the section is hidden without PAYMENT_CREATE', (tester) async {
    final _Api api = _Api();
    await _open(tester, api, const ['PURCHASE_APPROVE'], const Size(1366, 768));
    expect(find.byKey(const ValueKey('paid-now')), findsNothing);
    await tester.tap(find.byKey(const ValueKey('approve-bill-confirm')));
    await tester.pumpAndSettle();
    expect(api.posts.single.body, isEmpty);
  });

  testWidgets('a refusal stays on screen with what was typed', (tester) async {
    final _Api api = _Api(refusal: 'Payment exceeds what the bill owes.');
    await _open(tester, api, _payer, const Size(1366, 768));
    await tester.tap(find.byKey(const ValueKey('paid-now')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('paid-now-amount')), '999999');
    await tester.tap(find.byKey(const ValueKey('approve-bill-confirm')));
    await tester.pumpAndSettle();
    expect(find.text('Payment exceeds what the bill owes.'), findsOneWidget);
    expect(find.text('999999'), findsOneWidget);
    expect(find.byKey(const ValueKey('approve-bill-confirm')), findsOneWidget);
  });

  for (final Size size in const [Size(1366, 768), Size(800, 600)]) {
    testWidgets('nothing overflows at ${size.width.toInt()}x'
        '${size.height.toInt()}', (tester) async {
      await _open(tester, _Api(refusal: 'Refused.'), _payer, size);
      await tester.tap(find.byKey(const ValueKey('paid-now')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('paid-now-method')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Bank').last);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('approve-bill-confirm')));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  }
}
