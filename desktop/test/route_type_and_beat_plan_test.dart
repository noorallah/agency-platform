// The two screens that had no client at all, and the call order that had no UI.
//
// All three were server capabilities with nobody to reach them:
//
//   * `POST /route-types` has existed since the module was written and nothing
//     called it, so the only route types a firm ever had were the two the demo
//     seeder made. `PUT` and `DELETE` did not exist at all until this change.
//   * Beat plans have had complete CRUD from the start — list, create, read,
//     update, delete — and there was no model, no client method and no screen.
//   * `visit_sequence` was writable from the first migration and the `GET`
//     returned bare ids, so no screen could read back the order it saved.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/sales_territory.dart';
import 'package:agency_desktop/ui/sales/beat_plan_management_page.dart';
import 'package:agency_desktop/ui/sales/call_order_dialog.dart';
import 'package:agency_desktop/ui/sales/route_type_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>[
      'TERRITORY_VIEW',
      'TERRITORY_CREATE',
      'TERRITORY_UPDATE',
      'TERRITORY_DELETE',
    ],
  }));

Json _routeJson(String id, String code) => <String, dynamic>{
      'id': id,
      'firm_id': 'firm-1',
      'hierarchy_level_id': 'lvl-route',
      'hierarchy_level_name': 'Route',
      'code': code,
      'name': '$code round',
      'status': 'ACTIVE',
      'path': code,
      'sort_order': 0,
      'customer_count': 0,
      'salesman_count': 0,
      'route_profile': <String, dynamic>{
        'route_type_id': 'rt-sales',
        'route_type_name': 'Sales Route',
        'visit_frequency': 'WEEKLY',
        'working_days': <int>[1],
      },
    };

class _SalesApi extends ApiClient {
  _SalesApi({
    this.routeTypes = const <Json>[],
    this.plans = const <Json>[],
    this.territoryRows = const <Json>[],
  }) : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> routeTypes;
  final List<Json> plans;
  final List<Json> territoryRows;

  Json? created;
  Json? updated;
  /// What the screen sent as `If-Match`.
  int? sentVersion;

  String? deletedId;

  @override
  Future<List<TerritoryRouteTypeRecord>> territoryRouteTypes() async =>
      <TerritoryRouteTypeRecord>[
        for (final Json row in routeTypes) TerritoryRouteTypeRecord.fromJson(row),
      ];

  @override
  Future<Json> create(String resource, Json body) async {
    created = <String, dynamic>{'resource': resource, ...body};
    return <String, dynamic>{'data': body};
  }

  @override
  Future<Json> update(
    String resource,
    String id,
    Json body, {
    bool partial = false,
    int? expectedVersion,
  }) async {
    updated = <String, dynamic>{'resource': resource, 'id': id, ...body};
    return <String, dynamic>{'data': body};
  }

  @override
  Future<void> delete(String resource, String id) async {
    deletedId = '$resource/$id';
  }

  @override
  Future<PagedResult<SalesTerritory>> territories({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    TerritoryQuery filters = const TerritoryQuery(),
  }) async =>
      PagedResult<SalesTerritory>(
        items: <SalesTerritory>[
          for (final Json row in territoryRows) SalesTerritory.fromJson(row),
        ],
        total: territoryRows.length,
      );

  @override
  Future<PagedResult<BeatPlanRecord>> beatPlans({
    int page = 1,
    int pageSize = 20,
    String search = '',
    bool includeDeleted = false,
  }) async =>
      PagedResult<BeatPlanRecord>(
        items: <BeatPlanRecord>[
          for (final Json row in plans) BeatPlanRecord.fromJson(row),
        ],
        total: plans.length,
      );

  @override
  Future<BeatPlanRecord> createBeatPlan(Json data) async {
    created = data;
    return BeatPlanRecord.fromJson(<String, dynamic>{...data, 'id': 'bp-new'});
  }

  @override
  Future<BeatPlanRecord> updateBeatPlan(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    updated = data;
    sentVersion = expectedVersion;
    return BeatPlanRecord.fromJson(<String, dynamic>{...data, 'id': id});
  }
}

Future<void> _pump(WidgetTester tester, Widget child) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(home: Scaffold(body: child)));
  await tester.pumpAndSettle();
}

Finder _inDialog(Finder matching) =>
    find.descendant(of: find.byType(AlertDialog), matching: matching);

void main() {
  group('route types', () {
    testWidgets('a firm can add a kind of round it did not have',
        (tester) async {
      final _SalesApi api = _SalesApi(routeTypes: <Json>[
        <String, dynamic>{
          'id': 'rt-1',
          'code': 'SALES',
          'name': 'Sales Route',
          'description': 'Selling round',
          'is_active': true,
        },
      ]);
      await _pump(
        tester,
        RouteTypeManagementPage(api: api, permissions: _permissions()),
      );

      expect(find.textContaining('SALES'), findsWidgets);

      await tester.tap(find.widgetWithText(FilledButton, 'New').first);
      await tester.pumpAndSettle();
      await tester.enterText(
          find.widgetWithText(TextField, 'Code').first, 'merch');
      await tester.enterText(find.widgetWithText(TextField, 'Name').first,
          'Merchandising Round');
      await tester.tap(find.widgetWithText(FilledButton, 'Save & Close').last);
      await tester.pumpAndSettle();

      expect(api.created, isNotNull,
          reason: 'the POST has existed all along and nothing called it');
      expect(api.created!['resource'], 'sales-territories/route-types');
      // Upper-cased client-side so the server does not have to reject a
      // lower-case code the user had no way to know about.
      expect(api.created!['code'], 'MERCH');
      expect(api.created!['name'], 'Merchandising Round');
      expect(api.created!['is_active'], isTrue);
    });

    testWidgets('an empty description is sent as null, not an empty string',
        (tester) async {
      final _SalesApi api = _SalesApi();
      await _pump(
        tester,
        RouteTypeManagementPage(api: api, permissions: _permissions()),
      );
      await tester.tap(find.widgetWithText(FilledButton, 'New').first);
      await tester.pumpAndSettle();
      await tester.enterText(
          find.widgetWithText(TextField, 'Code').first, 'VAN');
      await tester.enterText(
          find.widgetWithText(TextField, 'Name').first, 'Van Sales');
      await tester.tap(find.widgetWithText(FilledButton, 'Save & Close').last);
      await tester.pumpAndSettle();

      expect(api.created!['description'], isNull);
    });
  });

  group('beat plans', () {
    testWidgets('the grid says when each plan runs, in words', (tester) async {
      final _SalesApi api = _SalesApi(
        territoryRows: <Json>[_routeJson('t-1', 'RT01')],
        plans: <Json>[
          <String, dynamic>{
            'id': 'bp-1',
            'territory_id': 't-1',
            'code': 'MON-N',
            'name': 'Monday North',
            'plan_type': 'MONTHLY',
            'weekday': 2,
            'week_of_month': 3,
            'is_active': true,
          },
        ],
      );
      await _pump(
        tester,
        BeatPlanManagementPage(api: api, permissions: _permissions()),
      );

      expect(find.textContaining('MON-N'), findsWidgets);
      // A raw MONTHLY/2/3 tells the reader nothing.
      expect(find.textContaining('3rd Tuesday of the month'), findsWidgets);
      expect(find.textContaining('RT01'), findsWidgets);
    });

    testWidgets('a new plan carries its recurrence', (tester) async {
      final _SalesApi api = _SalesApi(
        territoryRows: <Json>[_routeJson('t-1', 'RT01')],
      );
      await _pump(
        tester,
        BeatPlanManagementPage(api: api, permissions: _permissions()),
      );

      await tester.tap(find.widgetWithText(FilledButton, 'New').first);
      await tester.pumpAndSettle();

      await tester.enterText(
          _inDialog(find.widgetWithText(TextField, 'Code')), 'MON-N');
      await tester.enterText(
          _inDialog(find.widgetWithText(TextField, 'Name')), 'Monday North');
      await tester.tap(_inDialog(find.byType(DropdownButtonFormField<String>))
          .first); // Route
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('RT01').last);
      await tester.pumpAndSettle();
      await tester.tap(_inDialog(find.byType(DropdownButtonFormField<int>)));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Monday').last);
      await tester.pumpAndSettle();
      await tester.tap(_inDialog(find.widgetWithText(FilledButton, 'Save')));
      await tester.pumpAndSettle();

      expect(api.created, isNotNull);
      expect(api.created!['code'], 'MON-N');
      expect(api.created!['territory_id'], 't-1');
      expect(api.created!['plan_type'], 'WEEKLY');
      expect(api.created!['weekday'], 1);
      // Not a monthly plan, so no week of month is claimed.
      expect(api.created!['week_of_month'], isNull);
    });

    testWidgets('switching a plan to Custom clears the weekday it had',
        (tester) async {
      // Carrying it would have the server store a day the form is no longer
      // showing, which is the worst of both: invisible and persisted.
      final _SalesApi api = _SalesApi(
        territoryRows: <Json>[_routeJson('t-1', 'RT01')],
        plans: <Json>[
          <String, dynamic>{
            'id': 'bp-1',
            'territory_id': 't-1',
            'code': 'MON-N',
            'name': 'Monday North',
            'plan_type': 'WEEKLY',
            'weekday': 1,
            'is_active': true,
          },
        ],
      );
      await _pump(
        tester,
        BeatPlanManagementPage(api: api, permissions: _permissions()),
      );
      await tester.tap(find.text('MON-N').first);
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Edit'));
      await tester.pumpAndSettle();

      await tester.tap(_inDialog(find.byType(DropdownButtonFormField<String>))
          .last); // Repeats
      await tester.pumpAndSettle();
      await tester.tap(find.text('Custom').last);
      await tester.pumpAndSettle();
      await tester.tap(_inDialog(find.widgetWithText(FilledButton, 'Save')));
      await tester.pumpAndSettle();

      expect(api.updated, isNotNull);
      expect(api.updated!['plan_type'], 'CUSTOM');
      expect(api.updated!['weekday'], isNull);
    });

    testWidgets('a fortnightly plan says it needs a start date',
        (tester) async {
      // Without an anchor there is no way to know which fortnight, so the
      // server treats it as never occurring. Say so on the form rather than
      // letting somebody save a plan that can never come round.
      final _SalesApi api = _SalesApi(
        territoryRows: <Json>[_routeJson('t-1', 'RT01')],
      );
      await _pump(
        tester,
        BeatPlanManagementPage(api: api, permissions: _permissions()),
      );
      await tester.tap(find.widgetWithText(FilledButton, 'New').first);
      await tester.pumpAndSettle();

      expect(find.textContaining('can never come round'), findsNothing);
      await tester.tap(
          _inDialog(find.byType(DropdownButtonFormField<String>)).last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Fortnightly').last);
      await tester.pumpAndSettle();

      expect(find.textContaining('can never come round'), findsOneWidget);
    });

    testWidgets('with no routes defined the editor explains rather than opens',
        (tester) async {
      final _SalesApi api = _SalesApi();
      await _pump(
        tester,
        BeatPlanManagementPage(api: api, permissions: _permissions()),
      );
      await tester.tap(find.widgetWithText(FilledButton, 'New').first);
      await tester.pumpAndSettle();

      expect(find.byType(AlertDialog), findsNothing);
      expect(find.textContaining('This is a route'), findsWidgets);
    });
  });

  group('call order', () {
    testWidgets('dragging renumbers the round from one', (tester) async {
      List<TerritoryCustomerAssignmentRecord>? saved;
      await _pump(
        tester,
        Builder(
          builder: (context) => TextButton(
            onPressed: () async {
              saved = await showDialog<List<TerritoryCustomerAssignmentRecord>>(
                context: context,
                builder: (context) => CallOrderDialog(
                  routeName: 'North Beat',
                  assignments: const <TerritoryCustomerAssignmentRecord>[
                    TerritoryCustomerAssignmentRecord(
                      customerId: 'c-1',
                      isPrimary: true,
                      visitSequence: 1,
                      isPotential: false,
                    ),
                    TerritoryCustomerAssignmentRecord(
                      customerId: 'c-2',
                      isPrimary: true,
                      visitSequence: 2,
                      isPotential: false,
                    ),
                    TerritoryCustomerAssignmentRecord(
                      customerId: 'c-3',
                      isPrimary: true,
                      visitSequence: null,
                      isPotential: false,
                    ),
                  ],
                  nameFor: (id) => 'Shop $id',
                ),
              );
            },
            child: const Text('open'),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      expect(find.text('Shop c-1'), findsOneWidget);
      await tester.tap(_inDialog(find.widgetWithText(FilledButton, 'Save order')));
      await tester.pumpAndSettle();

      // Saved untouched, every position numbered — including the one that had
      // no sequence at all, which is the point: the round has an order now.
      expect(saved, isNotNull);
      expect([for (final row in saved!) row.customerId],
          <String>['c-1', 'c-2', 'c-3']);
      expect([for (final row in saved!) row.visitSequence], <int>[1, 2, 3]);
    });

    testWidgets('a round with nobody on it says so', (tester) async {
      await _pump(
        tester,
        Builder(
          builder: (context) => TextButton(
            onPressed: () => showDialog<void>(
              context: context,
              builder: (context) => CallOrderDialog(
                routeName: 'Empty Beat',
                assignments: const <TerritoryCustomerAssignmentRecord>[],
                nameFor: (id) => id,
              ),
            ),
            child: const Text('open'),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      expect(find.textContaining('Nobody on this round'), findsOneWidget);
      expect(
        tester
            .widget<FilledButton>(
                find.widgetWithText(FilledButton, 'Save order'))
            .onPressed,
        isNull,
      );
    });
  });
}
