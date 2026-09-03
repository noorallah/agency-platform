// A beat plan could not show its own round.
//
// `beatPlanCallList` had a route and a client method and nothing calling it.
// The Call List workspace asks the other question -- who is called across
// every active plan on a date -- so a plan's own calls could not be read from
// the plan, which is what somebody opening a plan wants to know.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/beat_plan_management_page.dart';
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
  _Api({this.callList})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json? callList;
  final List<String> asked = <String>[];

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
    if (path.contains('/call-list')) {
      asked.add(path);
      return <String, dynamic>{'data': callList};
    }
    if (path.contains('beat-plans')) {
      return <String, dynamic>{
        'data': <Json>[_plan()],
        'pagination': <String, dynamic>{'total_records': 1},
      };
    }
    return <String, dynamic>{
      'data': const <Json>[],
      'pagination': <String, dynamic>{'total_records': 0},
    };
  }
}

Json _plan() => <String, dynamic>{
      'id': 'bp-1',
      'territory_id': 't-1',
      'code': 'MON-N',
      'name': 'Monday North',
      'plan_type': 'WEEKLY',
      'weekday': 1,
      'is_active': true,
    };

Json _calls({required bool occurs, List<Json> stops = const <Json>[]}) =>
    <String, dynamic>{
      'on_date': '2026-09-03',
      'entries': <Json>[
        <String, dynamic>{
          'beat_plan_id': 'bp-1',
          'beat_plan_code': 'BP-1',
          'beat_plan_name': 'Monday North',
          'territory_id': 't-1',
          'territory_code': 'N',
          'territory_name': 'North Round',
          'salesman_id': 'u-1',
          'occurs': occurs,
          'reason': occurs ? '' : 'The plan does not run on a Thursday.',
          'stops': stops,
        },
      ],
    };

Json _stop(int order, String name) => <String, dynamic>{
      'customer_id': 'c-$order',
      'customer_code': 'C$order',
      'customer_name': name,
      'stop_order': order,
    };

Future<void> _open(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: BeatPlanManagementPage(
        api: api,
        permissions: _permissions(const ['TERRITORY_VIEW', 'TERRITORY_MANAGE']),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a plan shows the shops it calls on today', (tester) async {
    final _Api api = _Api(
      callList: _calls(
        occurs: true,
        stops: <Json>[_stop(1, 'Kumar Stores'), _stop(2, 'Vijaya Super')],
      ),
    );
    await _open(tester, api);

    await tester.tap(find.text('MON-N').first);
    // The grid settles a beat before the selection reaches the toolbar; the
    // sibling test for this page pumps the same way.
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(
      tester
          .widget<OutlinedButton>(
              find.widgetWithText(OutlinedButton, "Today's calls"))
          .onPressed,
      isNotNull,
      reason: 'the plan should be selected',
    );
    await tester.tap(find.widgetWithText(OutlinedButton, "Today's calls"));
    await tester.pumpAndSettle();

    expect(api.asked.single, contains('beat-plans/bp-1/call-list'));
    expect(find.textContaining('1. Kumar Stores'), findsOneWidget);
    expect(find.textContaining('2. Vijaya Super'), findsOneWidget);
  });

  testWidgets('a plan that does not run today says why', (tester) async {
    // `occurs` false and no stops are different answers from a round that
    // runs and happens to be empty, and only one of them is somebody's
    // problem to fix.
    final _Api api = _Api(callList: _calls(occurs: false));
    await _open(tester, api);

    await tester.tap(find.text('MON-N').first);
    // The grid settles a beat before the selection reaches the toolbar; the
    // sibling test for this page pumps the same way.
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OutlinedButton, "Today's calls"));
    await tester.pumpAndSettle();

    expect(
      find.textContaining('does not run on a Thursday'),
      findsOneWidget,
    );
  });

  testWidgets('a round that runs with nobody on it says that instead',
      (tester) async {
    final _Api api = _Api(callList: _calls(occurs: true));
    await _open(tester, api);

    await tester.tap(find.text('MON-N').first);
    // The grid settles a beat before the selection reaches the toolbar; the
    // sibling test for this page pumps the same way.
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OutlinedButton, "Today's calls"));
    await tester.pumpAndSettle();

    expect(find.textContaining('no shops on the round'), findsOneWidget);
  });

  testWidgets('nothing is asked for until a plan is chosen', (tester) async {
    final _Api api = _Api(callList: _calls(occurs: true));
    await _open(tester, api);

    expect(
      tester
          .widget<OutlinedButton>(
              find.widgetWithText(OutlinedButton, "Today's calls"))
          .onPressed,
      isNull,
    );
    expect(api.asked, isEmpty);
  });
}
