// Nothing is collected unless two things are true, and the screen has to say
// which one is missing.
//
// A firm that switched the section on, sees an empty register, and has no way
// to discover that its own stated turnover is what is holding it back will
// conclude the feature is broken. That is the case this screen exists for.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/tcs_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({
  List<String> perms = const ['TCS_VIEW', 'TCS_MANAGE'],
}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

class _TcsApi extends ApiClient {
  _TcsApi({required this.settings, this.collections = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json settings;
  final List<Json> collections;
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
    if (path.endsWith('/tcs/settings')) {
      if (method == 'PUT') saved = body;
      return <String, dynamic>{'data': settings};
    }
    return <String, dynamic>{
      'data': collections,
      'pagination': <String, dynamic>{'total_records': collections.length},
    };
  }
}

Json _settings({
  bool enabled = true,
  bool inScope = true,
}) =>
    <String, dynamic>{
      'section_code': '206C_1H',
      'is_enabled': enabled,
      'threshold_amount': '5000000',
      'rate_percent': '0.1',
      'rate_without_pan_percent': '1',
      'preceding_year_turnover': inScope ? '150000000' : '0',
      'seller_turnover_threshold': '100000000',
      'seller_in_scope': inScope,
    };

Json _collection() => <String, dynamic>{
      'id': 'tcs-1',
      'customer_id': 'cust-1',
      'customer_name': 'Kumar Stores',
      'settlement_id': 'rc-1',
      'settlement_number': 'RC-2026-2027-000008',
      'financial_year_start': '2026-04-01',
      'collected_on': '2026-09-01',
      'consideration_amount': '400000.00',
      'cumulative_before': '4800000.00',
      'taxable_amount': '200000.00',
      'rate_percent': '0.100',
      'without_pan': false,
      'tcs_amount': '200.00',
      'status': 'COLLECTED',
    };

Future<void> _pump(
  WidgetTester tester,
  _TcsApi api, {
  PermissionService? permissions,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: TcsPage(
        api: api,
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a firm in scope says so, with the rule beside it',
      (tester) async {
    await _pump(
      tester,
      _TcsApi(settings: _settings(), collections: <Json>[_collection()]),
    );

    expect(find.textContaining('Collecting under section 206C(1H)'),
        findsOneWidget);
    expect(find.textContaining('without a PAN'), findsOneWidget);
  });

  testWidgets('a firm below the turnover threshold is told which fact is missing',
      (tester) async {
    // The section is on, so "off" would be a lie and an empty register with
    // no explanation would look like a bug.
    await _pump(tester, _TcsApi(settings: _settings(inScope: false)));

    expect(find.textContaining('turnover is below'), findsOneWidget);
    expect(find.textContaining('switched off'), findsNothing);
  });

  testWidgets('a firm that has not switched it on is told that instead',
      (tester) async {
    await _pump(tester, _TcsApi(settings: _settings(enabled: false)));

    expect(find.textContaining('switched off'), findsOneWidget);
  });

  testWidgets('the register shows what the collected figure was worked out from',
      (tester) async {
    await _pump(
      tester,
      _TcsApi(settings: _settings(), collections: <Json>[_collection()]),
    );

    // Without what the buyer had already paid and what part was chargeable,
    // the collected amount is a number nobody can check.
    expect(find.text('4800000.00'), findsOneWidget);
    expect(find.text('200000.00'), findsOneWidget);
    expect(find.text('200.00'), findsOneWidget);
    expect(find.text('Kumar Stores'), findsOneWidget);
  });

  testWidgets('someone without the manage permission cannot open the settings',
      (tester) async {
    await _pump(
      tester,
      _TcsApi(settings: _settings()),
      permissions: _permissions(perms: const <String>['TCS_VIEW']),
    );

    final Finder button = find.widgetWithText(FilledButton, 'Settings');
    expect(button, findsOneWidget);
    expect(tester.widget<FilledButton>(button).onPressed, isNull);
  });

  testWidgets('someone without the view permission sees nothing at all',
      (tester) async {
    await _pump(
      tester,
      _TcsApi(settings: _settings(), collections: <Json>[_collection()]),
      permissions: _permissions(perms: const <String>['CUSTOMER_VIEW']),
    );

    expect(find.textContaining('view TCS permission'), findsOneWidget);
    expect(find.text('Kumar Stores'), findsNothing);
  });
}
