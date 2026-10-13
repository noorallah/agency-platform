// Bills with Collectors (backlog 122): the list shows a bill in the office and
// one with a collector, Hand over ticked and Hand over all matching post the
// right bodies, Take back ticked posts the handover ids, a user without
// COLLECTION_ASSIGN sees no action row, a refusal shows the server's message,
// and History lists and takes back.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/finance/bill_handover_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({bool assign = true}) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>[
      'RECEIPT_VIEW',
      if (assign) 'COLLECTION_ASSIGN',
    ],
  }));

Json _bill(String n, {String? handoverId, String? collector}) =>
    <String, dynamic>{
      'invoice_id': 'i-$n',
      'invoice_number': 'INV-$n',
      'invoice_date': '2026-09-01',
      'due_date': '2026-09-30',
      'days_overdue': 5,
      'is_opening_bill': false,
      'customer_id': 'c-$n',
      'customer_code': 'C-$n',
      'customer_name': 'Customer $n',
      'customer_place': n == '1' ? 'Hosur' : '',
      'invoice_total': 1200,
      'outstanding': '800.00',
      'handover_id': handoverId,
      'collector_id': collector == null ? null : 'u-2',
      'collector_name': collector,
      'handed_on': collector == null ? null : '2026-10-12',
    };

Json _handover(String id, String state) => <String, dynamic>{
      'id': id,
      'state': state,
      'invoice_id': 'i-$id',
      'invoice_number': 'INV-$id',
      'invoice_date': '2026-09-01',
      'is_opening_bill': false,
      'customer_id': 'c-$id',
      'customer_code': 'C-$id',
      'customer_name': 'Customer $id',
      'customer_place': '',
      'collector_id': 'u-2',
      'collector_name': 'Ravi',
      'handed_on': '2026-10-12',
      'handed_by': 'u-1',
      'handed_by_name': 'Asha',
      'outstanding_at_handover': '800.00',
      'outstanding': '300.00',
      'returned_at': state == 'RETURNED' ? '2026-10-13T09:00:00Z' : null,
      'returned_by_name': null,
      'return_note': null,
      'version': 1,
    };

class _Api extends ApiClient {
  _Api({this.refusal})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String? refusal;
  final List<String> requested = <String>[];
  final List<Map<String, String>?> billQueries = [];
  Json? given;
  Json? takenBack;

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
    if (path == '/api/v1/firm-members') {
      return <String, dynamic>{
        'data': [
          {'user_id': 'u-1', 'full_name': 'Asha', 'email': 'a@x.in'},
          {'user_id': 'u-2', 'full_name': 'Ravi', 'email': 'r@x.in'},
        ],
      };
    }
    if (path == '/api/v1/collections/handovers/bills') {
      billQueries.add(query);
      return <String, dynamic>{
        'data': [
          _bill('1'),
          _bill('2', handoverId: 'h-2', collector: 'Ravi'),
          _bill('3'),
        ],
        'pagination': {'total_records': 3},
      };
    }
    if (method == 'POST' && path == '/api/v1/collections/handovers') {
      given = body;
      if (refusal != null) throw ApiException(refusal!);
      return <String, dynamic>{
        'data': {'bills': 2, 'amount': '1600.00', 'already_out': 1},
      };
    }
    if (method == 'POST' && path.endsWith('/take-back')) {
      takenBack = body;
      return <String, dynamic>{
        'data': {'bills': 1, 'amount': '300.00', 'already_out': 0},
      };
    }
    if (path == '/api/v1/collections/handovers') {
      return <String, dynamic>{
        'data': [_handover('a', 'OUT'), _handover('b', 'RETURNED')],
        'pagination': {'total_records': 2},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('bill-handover'),
    );

Future<void> _pump(WidgetTester tester, _Api api,
    {bool assign = true, Size size = const Size(800, 600)}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: BillHandoverPage(
        api: api,
        preferences: _preferences(),
        permissions: _permissions(assign: assign),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _tap(WidgetTester tester, String key) async {
  final Finder finder = find.byKey(ValueKey(key));
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

Future<void> _chooseCollector(WidgetTester tester) async {
  await _tap(tester, 'handover-collector');
  await tester.tap(find.text('Ravi').last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the list shows a bill in the office and one with a collector',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    expect(find.textContaining('Customer 1 · Hosur'), findsOneWidget);
    expect(find.text('Customer 2'), findsOneWidget);
    expect(find.text('Ravi'), findsOneWidget);
    expect(find.text('Bills with Collectors'), findsNothing);
    expect(
        find.textContaining('changes no balance and no report'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('opening the page reads the bills once, not once per row',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    expect(api.requested.where((r) => r.endsWith('/handovers/bills')).length, 1);
    expect(api.requested.where((r) => r.endsWith('/firm-members')).length, 1);
    expect(api.requested.length, 2);
  });

  testWidgets('Hand over ticked sends only the ticked bills in the office',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    expect(
        tester
            .widget<FilledButton>(find.byKey(const ValueKey('handover-give')))
            .onPressed,
        isNull);
    await _chooseCollector(tester);
    await _tap(tester, 'handover-tick-i-1');
    await _tap(tester, 'handover-tick-i-2');
    await _tap(tester, 'handover-give');
    expect(api.given, {
      'collector_id': 'u-2',
      'invoice_ids': ['i-1'],
    });
    expect(
        find.textContaining('2 bills handed to Ravi, 1,600.00 in all. '
            '1 was already out and was left.'),
        findsOneWidget);
    // The list was read again and the ticks were cleared.
    expect(api.billQueries.length, 2);
    expect(
        tester
            .widget<Checkbox>(find.byKey(const ValueKey('handover-tick-i-1')))
            .value,
        isFalse);
  });

  testWidgets('Hand over all matching asks first and sends only set keys',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    await _chooseCollector(tester);
    expect(
        tester
            .widget<OutlinedButton>(
                find.byKey(const ValueKey('handover-give-matching')))
            .onPressed,
        isNull);
    await tester.enterText(
        find.byKey(const ValueKey('handover-area')), 'Hosur');
    await tester.pump();
    await _tap(tester, 'handover-give-matching');
    expect(find.text('Area or city: Hosur'), findsOneWidget);
    expect(api.given, isNull);
    await _tap(tester, 'handover-confirm');
    expect(api.given, {
      'collector_id': 'u-2',
      'matching': {'area': 'Hosur'},
    });
    expect(api.given!.containsKey('invoice_ids'), isFalse);
  });

  testWidgets('Take back ticked sends the handover ids', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    await _tap(tester, 'handover-tick-all');
    await _tap(tester, 'handover-take-back');
    expect(api.takenBack, {
      'handover_ids': ['h-2'],
    });
    expect(find.text('1 bill taken back.'), findsOneWidget);
  });

  testWidgets('without COLLECTION_ASSIGN the list shows and no actions do',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, assign: false);
    expect(find.text('Customer 2'), findsOneWidget);
    expect(find.byKey(const ValueKey('handover-give')), findsNothing);
    expect(find.byKey(const ValueKey('handover-give-matching')), findsNothing);
    expect(find.byKey(const ValueKey('handover-take-back')), findsNothing);
  });

  testWidgets('a refusal shows the server message', (tester) async {
    final _Api api =
        _Api(refusal: 'Bill INV-1 is already out with Ravi.');
    await _pump(tester, api);
    await _chooseCollector(tester);
    await _tap(tester, 'handover-tick-i-1');
    await _tap(tester, 'handover-give');
    expect(find.text('Bill INV-1 is already out with Ravi.'), findsOneWidget);
    expect(api.billQueries.length, 1);
  });

  testWidgets('History lists the handovers and takes back the ones out',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    await _tap(tester, 'handover-view-history');
    expect(find.text('Customer a'), findsOneWidget);
    expect(find.text('Customer b'), findsOneWidget);
    await _tap(tester, 'handover-tick-b');
    expect(
        tester
            .widget<OutlinedButton>(
                find.byKey(const ValueKey('handover-take-back')))
            .onPressed,
        isNull);
    await _tap(tester, 'handover-tick-a');
    await _tap(tester, 'handover-take-back');
    expect(api.takenBack, {
      'handover_ids': ['a'],
    });
    expect(tester.takeException(), isNull);
  });
}
