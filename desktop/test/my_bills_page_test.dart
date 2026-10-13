// My Bills to Collect (backlog 123): the collector's list shows the bills
// handed to him and, marked apart, the other unpaid bills of the same
// customers; the totals keep the two apart; every page is read; a user
// without COLLECTION_OWN_VIEW sees nothing and calls nothing; and the page
// has no action that writes.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/finance/my_bills_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({bool allowed = true}) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>[if (allowed) 'COLLECTION_OWN_VIEW'],
  }));

Json _bill(String n, String customer,
        {required bool mine, String outstanding = '800.00'}) =>
    <String, dynamic>{
      'invoice_id': 'i-$n',
      'invoice_number': 'INV-$n',
      'invoice_date': '2026-09-01',
      'due_date': '2026-09-30',
      'days_overdue': 5,
      'is_opening_bill': false,
      'customer_id': 'c-$customer',
      'customer_code': 'C-$customer',
      'customer_name': 'Customer $customer',
      'customer_place': customer == '1' ? 'Hosur' : '',
      'invoice_total': 1200,
      'outstanding': outstanding,
      'handed_to_me': mine,
      'handover_id': mine ? 'h-$n' : null,
      'handed_on': mine ? '2026-10-12' : null,
    };

/// Three bills over two pages of two: A and B are mine, C is the same
/// customer's other bill.
final List<List<Json>> _pages = [
  [
    _bill('A', '1', mine: true),
    _bill('C', '1', mine: false, outstanding: '500.00'),
  ],
  [
    _bill('B', '2', mine: true, outstanding: '300.00'),
  ],
];

class _Api extends ApiClient {
  _Api({this.empty = false, this.refusal})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool empty;
  final String? refusal;
  final List<String> requested = <String>[];
  final List<String?> pageAsked = <String?>[];

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
    if (path == '/api/v1/collections/my-bills') {
      if (refusal != null) throw ApiException(refusal!);
      pageAsked.add(query?['page']);
      if (empty) {
        return <String, dynamic>{
          'data': const <Json>[],
          'pagination': {'total_records': 0},
        };
      }
      final int page = int.parse(query?['page'] ?? '1');
      return <String, dynamic>{
        'data': page <= _pages.length ? _pages[page - 1] : const <Json>[],
        'pagination': {'page': page, 'total_records': 3},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('my-bills'),
    );

Future<void> _pump(WidgetTester tester, _Api api,
    {bool allowed = true, bool firm = true}) async {
  tester.view.physicalSize = const Size(1200, 800);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: MyBillsPage(
        api: api,
        preferences: _preferences(),
        permissions: _permissions(allowed: allowed),
        hasActiveFirm: firm,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('every page is read and every row shown', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    expect(api.pageAsked, ['1', '2']);
    expect(find.textContaining('Customer 1 · Hosur'), findsNWidgets(2));
    expect(find.text('Customer 2'), findsOneWidget);
    expect(find.text('INV-A'), findsOneWidget);
    expect(find.text('INV-B'), findsOneWidget);
    expect(find.text('INV-C'), findsOneWidget);
    // Dates are written in the person's format, not as stored.
    expect(find.text('01-09-2026'), findsNWidgets(3));
    expect(find.text('2026-09-01'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the two kinds of bill are marked apart', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    expect(find.text('With me, 12-10-2026'), findsNWidgets(2));
    expect(find.text('Not handed to me'), findsOneWidget);
  });

  testWidgets('the totals keep mine and the others apart', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    expect(
        tester
            .widget<Text>(find.byKey(const ValueKey('my-bills-mine')))
            .data,
        'Handed to me: 2 bills, 1,100.00 outstanding');
    expect(
        tester
            .widget<Text>(find.byKey(const ValueKey('my-bills-others')))
            .data,
        'Other unpaid bills of the same customers: 1 bill, '
        '500.00 outstanding');
  });

  testWidgets('with nothing handed over the page says so in plain words',
      (tester) async {
    final _Api api = _Api(empty: true);
    await _pump(tester, api);
    expect(find.text('No bills handed to you'), findsOneWidget);
    expect(find.byKey(const ValueKey('my-bills-mine')), findsNothing);
  });

  testWidgets('a refusal shows the server message', (tester) async {
    final _Api api = _Api(refusal: 'You cannot see this.');
    await _pump(tester, api);
    expect(find.text('You cannot see this.'), findsOneWidget);
  });

  testWidgets('without COLLECTION_OWN_VIEW nothing is shown or called',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, allowed: false);
    expect(find.text('You cannot see the bills to collect'), findsOneWidget);
    expect(find.text('INV-A'), findsNothing);
    expect(api.requested, isEmpty);
  });

  testWidgets('with no firm chosen nothing is called', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, firm: false);
    expect(find.text('Choose a firm'), findsOneWidget);
    expect(api.requested, isEmpty);
  });

  testWidgets('Refresh reads the list again and nothing is written',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    expect(find.byType(FilledButton), findsNothing);
    expect(find.byType(Checkbox), findsNothing);
    await tester.tap(find.byIcon(Icons.refresh).first);
    await tester.pumpAndSettle();
    expect(api.pageAsked, ['1', '2', '1', '2']);
    expect(api.requested.every((r) => r.startsWith('GET ')), isTrue);
  });
}
