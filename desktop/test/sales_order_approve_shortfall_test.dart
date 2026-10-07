import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/document_framework/document_steps.dart';
import 'package:agency_desktop/ui/sales/sales_document_steps.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// D-UI-24, D-UI-48: approving an order for more than the stock on hand said
/// nothing. The server approves it and leaves the shortfall on back order.
///
/// The first fix read the shortfall off the approve response, as
/// `reservable_quantity - reserved_quantity`, and its test fed a response
/// whose `reserved_quantity` was 82 of 500. The server never sends that: it
/// reserves the whole line, back order included, so the two are always equal
/// and the screen said nothing (SC-SO-020). The approve response below is
/// shaped as the server shapes it, and the shortfall comes from where the
/// server keeps it: the back-order report.
Json _approved() => <String, dynamic>{
      'data': <String, dynamic>{
        'id': 'so-1',
        'status': 'APPROVED',
        'lines': <Json>[
          <String, dynamic>{
            'description': 'Shampoo 180ml',
            'quantity': '500',
            'reservable_quantity': '500.0000',
            'reserved_quantity': '500.0000',
          },
        ],
      },
    };

Json _backOrder({
  String orderId = 'so-1',
  String product = 'Shampoo 180ml',
  String requested = '500.0000',
  String short = '418.0000',
}) =>
    <String, dynamic>{
      'order_id': orderId,
      'order_number': 'SO-1',
      'product_name': product,
      'requested_quantity': requested,
      'delivered_quantity': '0.0000',
      'reserved_quantity': requested,
      'available_stock': '82.0000',
      'back_order_quantity': short,
    };

class _Api extends ApiClient {
  _Api(this.backOrders, {this.reportRefused = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> backOrders;
  final bool reportRefused;
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
    if (path.endsWith('/approve')) return _approved();
    if (path == '/api/v1/sales-orders/reports/back-orders' && !reportRefused) {
      return <String, dynamic>{'data': backOrders};
    }
    // Every advisory check (licences, price floors) cannot run: approval goes on.
    throw const ApiException('not here', statusCode: 404);
  }
}

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(
    'h.${base64Url.encode(utf8.encode(jsonEncode(<String, dynamic>{
          'roles': <String>['user'],
          'permissions': <String>['SALES_APPROVE'],
        }))).replaceAll('=', '')}.s',
  );

Future<DocumentStepDone?> _run(
  WidgetTester tester,
  List<DocumentStep<Json>> steps,
) async {
  final DocumentStep<Json> approve =
      steps.firstWhere((step) => step.id == 'approve');
  late BuildContext context;
  await tester.pumpWidget(MaterialApp(
    home: Builder(builder: (c) {
      context = c;
      return const SizedBox();
    }),
  ));
  return approve.run(
    context,
    <String, dynamic>{'id': 'so-1', 'status': 'DRAFT', 'grand_total': '0'},
  );
}

void main() {
  test('names what is short and how much of the line it is', () {
    expect(
      approvedShortfallNotice(<Json>[_backOrder()], 'so-1'),
      'Approved. 418 of 500 of Shampoo 180ml are not in stock and stay on '
      'back order.',
    );
  });

  test('reads only the order that was approved', () {
    expect(
      approvedShortfallNotice(
        <Json>[
          _backOrder(orderId: 'so-0', product: 'Soap', short: '9.0000'),
          _backOrder(short: '18.0000', requested: '100.0000'),
          _backOrder(product: 'Detergent 1kg', short: '5.0000'),
        ],
        'so-1',
      ),
      'Approved. 18 of 100 of Shampoo 180ml; 5 of 500 of Detergent 1kg are '
      'not in stock and stay on back order.',
    );
  });

  test('says nothing where every line was covered, or nothing is known', () {
    expect(approvedShortfallNotice(const <Json>[], 'so-1'), isNull);
    expect(
      approvedShortfallNotice(<Json>[_backOrder(orderId: 'so-9')], 'so-1'),
      isNull,
    );
    expect(approvedShortfallNotice(null, 'so-1'), isNull);
  });

  testWidgets('the Approve step comes back with the warning', (tester) async {
    // The approve response says 500 of 500 reserved, as the server's does.
    final _Api api = _Api(<Json>[_backOrder()]);
    final DocumentStepDone? done =
        await _run(tester, salesOrderSteps(api, _permissions()));
    expect(done, isNotNull);
    expect(done!.warning, isTrue);
    expect(
      done.message,
      'Approved. 418 of 500 of Shampoo 180ml are not in stock and stay on '
      'back order.',
    );
    // One read more, and only once the order is approved.
    expect(
      api.calls.skipWhile((String call) => !call.endsWith('/approve')).toList(),
      <String>[
        'POST /api/v1/sales-orders/so-1/approve',
        'GET /api/v1/sales-orders/reports/back-orders',
      ],
    );
  });

  testWidgets('a fully covered order approves without a message',
      (tester) async {
    final DocumentStepDone? done = await _run(
      tester,
      salesOrderSteps(_Api(const <Json>[]), _permissions()),
    );
    expect(done!.message, isEmpty);
    expect(done.warning, isFalse);
  });

  testWidgets('an unreadable report costs the notice, not the approval',
      (tester) async {
    final DocumentStepDone? done = await _run(
      tester,
      salesOrderSteps(
        _Api(<Json>[_backOrder()], reportRefused: true),
        _permissions(),
      ),
    );
    expect(done, isNotNull, reason: 'the order is approved all the same');
    expect(done!.message, isEmpty);
  });

  testWidgets('approving a sales bill reads no back-order report',
      (tester) async {
    final _Api api = _Api(<Json>[_backOrder()]);
    await _run(tester, salesInvoiceSteps(api, _permissions()));
    expect(api.calls, contains(endsWith('/approve')));
    expect(api.calls, isNot(contains(endsWith('/reports/back-orders'))));
  });
}
