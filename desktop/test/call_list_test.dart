// Who is called today — the screen that closes "sales on that route".
//
// A route could be drawn, ordered and scheduled, and nothing anywhere turned
// that into a day's work. The server computes the answer from the recurrence
// rule and the assignments, so these tests are about what the screen does with
// that answer — in particular that it never shows the same blank list for "no
// calls today" and "this plan cannot be computed", which are different facts.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/sales_territory.dart';
import 'package:agency_desktop/ui/sales/call_list_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['TERRITORY_VIEW'],
  }));

Json _entry({
  required String code,
  required bool occurs,
  String reason = '',
  List<Json> stops = const <Json>[],
}) =>
    <String, dynamic>{
      'beat_plan_id': 'bp-$code',
      'beat_plan_code': code,
      'beat_plan_name': '$code plan',
      'territory_id': 'ter-1',
      'territory_code': 'RT01',
      'territory_name': 'RT01 round',
      'salesman_id': null,
      'occurs': occurs,
      'reason': reason.isEmpty ? null : reason,
      'stops': stops,
    };

Json _stop(String code, String name, int order) => <String, dynamic>{
      'customer_id': 'cus-$code',
      'customer_code': code,
      'customer_name': name,
      'stop_order': order,
      'planned_duration_minutes': null,
    };

class _CallListApi extends ApiClient {
  _CallListApi({this.entries = const <Json>[]})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> entries;
  final List<String> requestedDates = <String>[];
  String? requestedSalesman;

  @override
  Future<CallListRecord> callLists({
    required String date,
    String salesmanId = '',
  }) async {
    requestedDates.add(date);
    requestedSalesman = salesmanId;
    return CallListRecord.fromJson(<String, dynamic>{
      'on_date': date,
      'entries': entries,
    });
  }

  @override
  Future<List<TerritorySalesmanCandidate>> territorySalesmanCandidates() async =>
      <TerritorySalesmanCandidate>[
        const TerritorySalesmanCandidate(
          userId: 'user-1',
          fullName: 'Ravi Kumar',
          email: 'ravi@example.local',
        ),
      ];
}

Future<void> _pump(WidgetTester tester, _CallListApi api) async {
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: CallListPage(api: api, permissions: _permissions()),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a round that runs today lists its outlets in call order',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final api = _CallListApi(entries: <Json>[
      _entry(code: 'MON', occurs: true, stops: <Json>[
        _stop('C2', 'Second Stores', 1),
        _stop('C1', 'First Stores', 2),
      ]),
    ]);
    await _pump(tester, api);

    expect(find.text('Runs today'), findsOneWidget);
    expect(find.text('Second Stores'), findsOneWidget);
    expect(find.text('First Stores'), findsOneWidget);
    // The order the round is walked in, not alphabetical or by id.
    final Offset second = tester.getTopLeft(find.text('Second Stores'));
    final Offset first = tester.getTopLeft(find.text('First Stores'));
    expect(second.dy, lessThan(first.dy));
  });

  testWidgets('a plan that cannot be computed says why, not nothing',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final api = _CallListApi(entries: <Json>[
      _entry(
        code: 'FORT',
        occurs: false,
        reason: 'A fortnightly plan needs a start date to count from.',
      ),
    ]);
    await _pump(tester, api);

    expect(find.text('Not today'), findsOneWidget);
    expect(
      find.text('A fortnightly plan needs a start date to count from.'),
      findsOneWidget,
    );
  });

  testWidgets('a round that runs today with nobody on it says so',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final api = _CallListApi(entries: <Json>[_entry(code: 'MON', occurs: true)]);
    await _pump(tester, api);

    expect(
      find.text('This round runs today but has no outlets on it yet.'),
      findsOneWidget,
    );
  });

  testWidgets('stepping to the next day asks the server for that day',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final api = _CallListApi(entries: <Json>[_entry(code: 'MON', occurs: true)]);
    await _pump(tester, api);
    final String firstDate = api.requestedDates.single;

    await tester.tap(find.byTooltip('Next day'));
    await tester.pumpAndSettle();

    expect(api.requestedDates.length, 2);
    expect(api.requestedDates.last, isNot(firstDate));
  });

  testWidgets('picking a salesperson narrows the list to their rounds',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final api = _CallListApi(entries: <Json>[_entry(code: 'MON', occurs: true)]);
    await _pump(tester, api);
    expect(api.requestedSalesman, '');

    await tester.tap(find.text('Everyone'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ravi Kumar').last);
    await tester.pumpAndSettle();

    expect(api.requestedSalesman, 'user-1');
  });

  testWidgets('a firm with no beat plans is told where to make one',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await _pump(tester, _CallListApi());

    expect(find.text('No beat plans to call from'), findsOneWidget);
  });
}
