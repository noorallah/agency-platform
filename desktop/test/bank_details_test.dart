// Firm bank details printed on bills (ACC-4).
//
// The grid lists the kept details; a masked row is never sent back; a save
// sends exactly the keys the server declares; a refusal keeps the dialog open.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/finance/bank_details_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({
  List<String> perms = const ['ACCOUNT_VIEW', 'ACCOUNT_MANAGE'],
}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

Json _row(
  String id,
  String bank, {
  bool masked = false,
  bool printed = false,
  String number = '123456785678',
}) =>
    <String, dynamic>{
      'id': id,
      'ledger_account_id': 'la-$id',
      'ledger_account_code': '1020',
      'ledger_account_name': 'Bank $bank',
      'bank_name': bank,
      'account_name': 'Mehta Agencies',
      'account_number': masked ? 'XXXXXXXX5678' : number,
      'masked': masked,
      'ifsc': 'HDFC0001234',
      'branch': 'Fort',
      'account_kind': 'CURRENT',
      'swift_code': null,
      'upi_id': null,
      'print_on_documents': printed,
      'version': 1,
    };

class _Api extends ApiClient {
  _Api({this.rows = const [], this.refuse = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;
  final bool refuse;
  final List<String> requested = <String>[];
  Json? saved;

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
    if (method == 'PUT' && path.contains('/bank-details/')) {
      saved = body;
      if (refuse) {
        throw const ApiException(
          'Only an asset account can hold bank details.',
          statusCode: 422,
        );
      }
      return <String, dynamic>{'data': _row('n-1', 'HDFC')};
    }
    if (method == 'DELETE') return <String, dynamic>{};
    if (path.endsWith('/bank-details')) return <String, dynamic>{'data': rows};
    if (path.endsWith('/ledger-accounts')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'la-new',
            'account_group_id': 'g',
            'code': '1030',
            'name': 'Axis current',
            'account_type': 'ASSET',
            'is_active': true,
          },
          <String, dynamic>{
            'id': 'la-exp',
            'account_group_id': 'g',
            'code': '5000',
            'name': 'Rent',
            'account_type': 'EXPENSE',
            'is_active': true,
          },
        ],
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('bank-details'),
    );

Future<void> _pump(
  WidgetTester tester,
  _Api api, {
  PermissionService? permissions,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: BankDetailsPage(
        api: api,
        preferences: _preferences(),
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester, String text) async {
  await tester.tap(find.text(text).first);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

Future<void> _fillNew(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('toolbar-new')));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('bank-details-account')));
  await tester.pumpAndSettle();
  // Only the asset account is offered.
  expect(find.text('5000  Rent'), findsNothing);
  await tester.tap(find.text('1030  Axis current').last);
  await tester.pumpAndSettle();
  await tester.enterText(find.byKey(const ValueKey('bank-details-bank')), 'Axis');
  await tester.enterText(
      find.byKey(const ValueKey('bank-details-holder')), 'Mehta Agencies');
  await tester.enterText(
      find.byKey(const ValueKey('bank-details-number')), '9876543210');
  await tester.enterText(
      find.byKey(const ValueKey('bank-details-ifsc')), 'utib0000123');
  await tester.tap(find.byKey(const ValueKey('bank-details-print')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the grid lists the details with the printed one marked',
      (tester) async {
    final _Api api = _Api(rows: <Json>[
      _row('a', 'HDFC', printed: true),
      _row('b', 'ICICI'),
    ]);
    await _pump(tester, api);

    expect(api.requested.first, 'GET /api/v1/finance/bank-details');
    expect(find.text('HDFC'), findsOneWidget);
    expect(find.text('ICICI'), findsOneWidget);
    expect(find.text('123456785678'), findsWidgets);
    expect(find.text('Printed on bills'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a masked number is shown as returned', (tester) async {
    final _Api api =
        _Api(rows: <Json>[_row('a', 'HDFC', masked: true)]);
    await _pump(tester, api);
    expect(find.text('XXXXXXXX5678'), findsWidgets);
  });

  testWidgets('saving sends exactly the keys the server declares',
      (tester) async {
    final _Api api = _Api(rows: <Json>[_row('a', 'HDFC')]);
    await _pump(tester, api);
    await _fillNew(tester);
    await tester.tap(find.byKey(const ValueKey('bank-details-save')));
    await tester.pumpAndSettle();

    expect(api.requested,
        contains('PUT /api/v1/finance/bank-details/la-new'));
    expect(api.saved, <String, dynamic>{
      'bank_name': 'Axis',
      'account_name': 'Mehta Agencies',
      'account_number': '9876543210',
      'ifsc': 'UTIB0000123',
      'branch': null,
      'account_kind': null,
      'swift_code': null,
      'upi_id': null,
      'print_on_documents': true,
    });
    expect(find.byKey(const ValueKey('bank-details-save')), findsNothing);
  });

  testWidgets('a refusal keeps the dialog open with the server message',
      (tester) async {
    final _Api api = _Api(rows: <Json>[_row('a', 'HDFC')], refuse: true);
    await _pump(tester, api);
    await _fillNew(tester);
    await tester.tap(find.byKey(const ValueKey('bank-details-save')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('bank-details-save')), findsOneWidget);
    expect(find.text('Only an asset account can hold bank details.'),
        findsOneWidget);
    expect(find.text('Axis'), findsOneWidget);
  });

  testWidgets('editing a masked row asks for the number again',
      (tester) async {
    final _Api api = _Api(rows: <Json>[_row('a', 'HDFC', masked: true)]);
    await _pump(tester, api);
    await _select(tester, 'HDFC');
    await tester.tap(find.byKey(const ValueKey('selection-edit')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('bank-details-save')));
    await tester.pumpAndSettle();

    expect(api.saved, isNull);
    expect(find.byKey(const ValueKey('bank-details-problem')), findsOneWidget);

    await tester.enterText(
        find.byKey(const ValueKey('bank-details-number')), '123456785678');
    await tester.tap(find.byKey(const ValueKey('bank-details-save')));
    await tester.pumpAndSettle();
    expect(api.saved!['account_number'], '123456785678');
    expect(api.requested, contains('PUT /api/v1/finance/bank-details/la-a'));
  });

  testWidgets('removing asks first and then deletes', (tester) async {
    final _Api api = _Api(rows: <Json>[_row('a', 'HDFC')]);
    await _pump(tester, api);
    await _select(tester, 'HDFC');
    await tester.tap(find.byKey(const ValueKey('selection-delete')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('bank-details-remove-confirm')));
    await tester.pumpAndSettle();

    expect(api.requested,
        contains('DELETE /api/v1/finance/bank-details/la-a'));
  });

  testWidgets('without the manage permission there is no way to write',
      (tester) async {
    final _Api api = _Api(rows: <Json>[_row('a', 'HDFC')]);
    await _pump(tester, api,
        permissions: _permissions(perms: const ['ACCOUNT_VIEW']));
    expect(find.byKey(const ValueKey('toolbar-new')), findsNothing);
    expect(find.byKey(const ValueKey('toolbar-edit')), findsNothing);
    expect(find.byKey(const ValueKey('toolbar-delete')), findsNothing);
    expect(find.text('HDFC'), findsOneWidget);
  });

  testWidgets('a user with no view permission sees nothing', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, permissions: _permissions(perms: const []));
    expect(find.text('You cannot see bank details'), findsOneWidget);
    expect(api.requested, isEmpty);
  });

  testWidgets('the page and dialog fit the 800x600 window', (tester) async {
    final _Api api = _Api(rows: <Json>[_row('a', 'HDFC', printed: true)]);
    await _pump(tester, api);
    tester.view.physicalSize = const Size(800, 600);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull, reason: 'the page');
    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('bank-details-print')), findsOneWidget);
    expect(tester.takeException(), isNull, reason: 'the dialog');
  });
}
