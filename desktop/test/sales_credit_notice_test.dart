import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_management_page.dart';
import 'package:agency_desktop/ui/sales/sales_order_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Credit limits are enforced on the server, at approval. The client's job is
/// to make sure the user is not surprised by that — so it warns when the limit
/// is close, and never stands in the way of the document itself.
///
/// These tests pin the two halves of that: the warning appears and the approve
/// still runs, and a document the server is going to refuse gets no client
/// warning, because the refusal already carries the same sentence.

String _accessToken(Map<String, dynamic> claims) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '');
  return 'header.$payload.signature';
}

PermissionService _withPermissions(List<String> permissions) {
  final PermissionService service = PermissionService();
  service.applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': permissions,
  }));
  return service;
}

/// A backend that serves one draft order and whatever credit verdict the test
/// asks for, recording the calls the page makes.
class _CreditApi extends ApiClient {
  _CreditApi({required this.creditStatus, this.creditFails = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Map<String, dynamic> creditStatus;
  final bool creditFails;
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
    if (path.contains('/credit-status')) {
      if (creditFails) {
        throw const ApiException('Credit check unavailable.', statusCode: 500);
      }
      return <String, dynamic>{'success': true, 'data': creditStatus};
    }
    if (path.endsWith('/summary')) {
      return <String, dynamic>{
        'success': true,
        'data': <String, dynamic>{'total': 1, 'draft': 1},
      };
    }
    if (path.contains('/history') || path.contains('/timeline')) {
      return <String, dynamic>{'success': true, 'data': const <dynamic>[]};
    }
    if (method == 'POST') {
      return <String, dynamic>{'success': true, 'data': const <String, dynamic>{}};
    }
    return <String, dynamic>{
      'success': true,
      'data': <Map<String, dynamic>>[
        <String, dynamic>{
          'id': 'order-1',
          'order_number': 'SO-0001',
          'order_date': '2026-08-10',
          'invoice_number': 'SI-0001',
          'invoice_date': '2026-08-10',
          'status': 'DRAFT',
          'customer_id': 'customer-1',
          'grand_total': '190000.00',
          'lines': const <dynamic>[],
        },
      ],
      'pagination': <String, dynamic>{'total_records': 1},
    };
  }
}

Map<String, dynamic> _status({
  required String status,
  required bool wouldBlock,
  String message = 'Vijaya Super Stores would be at 88.6% of a 250000.00 '
      'credit limit, leaving 28584.00 available.',
}) =>
    <String, dynamic>{
      'customer_id': 'customer-1',
      'customer_name': 'Vijaya Super Stores',
      'enforcement': wouldBlock ? 'BLOCK' : 'WARN',
      'status': status,
      'limit': '250000.0000',
      'exposure': '221416.0000',
      'available': '28584.0000',
      'used_percent': '88.5664',
      'warn_at_percent': '80',
      'block_at_percent': '100',
      'would_block': wouldBlock,
      'message': message,
    };

Future<void> _pumpAndApprove(WidgetTester tester, _CreditApi api) async {
  final Directory temp = Directory.systemTemp.createTempSync('credit-notice');
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: SalesOrderManagementPage(
          api: api,
          preferences: DesktopPreferencesService(directory: temp),
          permissions: _withPermissions(['SALES_VIEW', 'SALES_APPROVE']),
          hasActiveFirm: true,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.widgetWithText(OutlinedButton, 'Approve').first);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a customer near their limit is warned, and the approve runs',
      (tester) async {
    final _CreditApi api = _CreditApi(
      creditStatus: _status(status: 'WARNING', wouldBlock: false),
    );

    await _pumpAndApprove(tester, api);

    expect(
      find.textContaining('88.6% of a 250000.00 credit limit'),
      findsOneWidget,
      reason: 'the user must see the warning before the document is committed',
    );
    expect(
      api.calls.any((call) => call.contains('/credit-status')),
      isTrue,
    );
    expect(
      api.calls.any((call) => call.contains('/approve')),
      isTrue,
      reason: 'warning must not block the document',
    );
  });

  testWidgets('the credit check runs before the approve, not after',
      (tester) async {
    final _CreditApi api = _CreditApi(
      creditStatus: _status(status: 'WARNING', wouldBlock: false),
    );

    await _pumpAndApprove(tester, api);

    final int checked =
        api.calls.indexWhere((call) => call.contains('/credit-status'));
    final int approved =
        api.calls.indexWhere((call) => call.contains('/approve'));
    expect(checked, greaterThanOrEqualTo(0));
    expect(
      checked,
      lessThan(approved),
      reason: 'asking afterwards would count the order twice — once in the '
          'outstanding balance it just created, and again as the amount',
    );
  });

  testWidgets('a document the server will refuse gets no client warning',
      (tester) async {
    final _CreditApi api = _CreditApi(
      creditStatus: _status(
        status: 'BREACH',
        wouldBlock: true,
        message: 'Vijaya Super Stores would be at 104.6% of a 250000.00 '
            'credit limit. Collect payment or raise the limit before '
            'continuing.',
      ),
    );

    await _pumpAndApprove(tester, api);

    expect(
      find.textContaining('104.6%'),
      findsNothing,
      reason: 'the refusal carries this sentence; warning first prints it twice',
    );
  });

  testWidgets('sales invoices warn on the same terms as sales orders',
      (tester) async {
    final _CreditApi api = _CreditApi(
      creditStatus: _status(status: 'WARNING', wouldBlock: false),
    );
    final Directory temp = Directory.systemTemp.createTempSync('credit-invoice');

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SalesInvoiceManagementPage(
            api: api,
            preferences: DesktopPreferencesService(directory: temp),
            permissions: _withPermissions(['SALES_VIEW', 'SALES_APPROVE']),
            hasActiveFirm: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OutlinedButton, 'Approve').first);
    await tester.pumpAndSettle();

    expect(
      find.textContaining('88.6% of a 250000.00 credit limit'),
      findsOneWidget,
      reason: 'approval posts the receivable, so it is a credit moment too',
    );
    expect(api.calls.any((call) => call.contains('/approve')), isTrue);
  });

  testWidgets('a credit check that fails does not hold up the document',
      (tester) async {
    final _CreditApi api = _CreditApi(
      creditStatus: const <String, dynamic>{},
      creditFails: true,
    );

    await _pumpAndApprove(tester, api);

    expect(
      api.calls.any((call) => call.contains('/approve')),
      isTrue,
      reason: 'an advisory check is not a gate',
    );
  });
}
