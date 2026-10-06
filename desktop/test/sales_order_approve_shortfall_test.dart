import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/document_framework/document_steps.dart';
import 'package:agency_desktop/ui/sales/sales_document_steps.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// D-UI-24: approving an order for more than the stock on hand said nothing.
/// The server approves it and leaves the shortfall on back order; the screen
/// now says so from the approve response it already has.
Json _approved({String reservable = '500', String reserved = '82'}) =>
    <String, dynamic>{
      'data': <String, dynamic>{
        'id': 'so-1',
        'status': 'APPROVED',
        'lines': <Json>[
          <String, dynamic>{
            'description': 'Shampoo 180ml',
            'quantity': '500',
            'reservable_quantity': reservable,
            'reserved_quantity': reserved,
          },
        ],
      },
    };

class _Api extends ApiClient {
  _Api(this.response)
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json response;
  int calls = 0;

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
    calls += 1;
    if (path.endsWith('/approve')) return response;
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

void main() {
  test('names what is short and how much of the line it is', () {
    expect(
      approvedShortfallNotice(_approved()['data']),
      'Approved. 418 of 500 of Shampoo 180ml are not in stock and stay on '
      'back order.',
    );
  });

  test('says nothing where every line was covered, or nothing is known', () {
    expect(approvedShortfallNotice(_approved(reserved: '500')['data']), isNull);
    expect(approvedShortfallNotice(<String, dynamic>{'lines': <Json>[]}), isNull);
    expect(approvedShortfallNotice(null), isNull);
  });

  testWidgets('the Approve step comes back with the warning', (tester) async {
    final _Api api = _Api(_approved());
    final DocumentStep<Json> approve = salesOrderSteps(api, _permissions())
        .firstWhere((step) => step.id == 'approve');
    late BuildContext context;
    await tester.pumpWidget(MaterialApp(
      home: Builder(builder: (c) {
        context = c;
        return const SizedBox();
      }),
    ));
    final DocumentStepDone? done = await approve.run(
      context,
      <String, dynamic>{'id': 'so-1', 'status': 'DRAFT', 'grand_total': '0'},
    );
    expect(done, isNotNull);
    expect(done!.warning, isTrue);
    expect(done.message, startsWith('Approved. 418 of 500'));
  });

  testWidgets('a fully covered order approves without a message',
      (tester) async {
    final _Api api = _Api(_approved(reserved: '500'));
    final DocumentStep<Json> approve = salesOrderSteps(api, _permissions())
        .firstWhere((step) => step.id == 'approve');
    late BuildContext context;
    await tester.pumpWidget(MaterialApp(
      home: Builder(builder: (c) {
        context = c;
        return const SizedBox();
      }),
    ));
    final DocumentStepDone? done = await approve.run(
      context,
      <String, dynamic>{'id': 'so-1', 'status': 'DRAFT', 'grand_total': '0'},
    );
    expect(done!.message, isEmpty);
    expect(done.warning, isFalse);
  });
}
