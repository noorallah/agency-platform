// Building a beat the way a supervisor builds one: walk a pin code, tick the
// shops, put them in call order.
//
// The customer picker on Geography answers "which of my customers is this", by
// name — the wrong question for laying out a round, which follows a street.
// It also could not say which outlets were on no round at all.
//
// The behaviour that matters most here is the save: assigning and ordering are
// one request, because the API replaces the whole list and `visit_sequence` is
// position in it. Saving membership first and order second would leave a
// window where the round exists with no order.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/sales_territory.dart';
import 'package:agency_desktop/ui/sales/route_builder_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({bool canAssign = true}) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>[
      'TERRITORY_VIEW',
      if (canAssign) 'TERRITORY_ASSIGN_CUSTOMERS',
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
        'visit_frequency': 'WEEKLY',
        'working_days': <int>[1],
      },
    };

Json _outletJson({
  required String id,
  required String code,
  String area = 'Parrys',
  String postal = '600001',
  bool onThisRoute = false,
  int? sequence,
  List<String> otherRoutes = const <String>[],
}) =>
    <String, dynamic>{
      'customer_id': id,
      'code': code,
      'name': '$code Stores',
      'address_line': '1 Big Street',
      'area': area,
      'city': 'Chennai',
      'postal_code': postal,
      'on_this_route': onThisRoute,
      'visit_sequence': sequence,
      'other_routes': otherRoutes,
    };

class _BuilderApi extends ApiClient {
  _BuilderApi({this.outlets = const <Json>[], this.failRoundLoad = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> outlets;

  /// When set, the 500-row read that fills the round panel throws.
  final bool failRoundLoad;

  final List<Json> queries = <Json>[];
  List<TerritoryCustomerAssignmentRecord>? saved;
  String? savedTerritoryId;

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
          SalesTerritory.fromJson(_routeJson('rt-1', 'RT01')),
        ],
        total: 1,
      );

  @override
  Future<PagedResult<AssignableCustomerRecord>> assignableCustomers({
    int page = 1,
    int pageSize = 50,
    String territoryId = '',
    String search = '',
    String postalCode = '',
    String area = '',
    String city = '',
    bool unassignedOnly = false,
  }) async {
    if (failRoundLoad && pageSize == 500) {
      throw const ApiException('The round could not be read.');
    }
    queries.add(<String, dynamic>{
      'territory_id': territoryId,
      'search': search,
      'postal_code': postalCode,
      'area': area,
      'unassigned_only': unassignedOnly,
    });
    return PagedResult<AssignableCustomerRecord>(
      items: <AssignableCustomerRecord>[
        for (final Json row in outlets) AssignableCustomerRecord.fromJson(row),
      ],
      total: outlets.length,
    );
  }

  @override
  Future<List<TerritoryCustomerAssignmentRecord>> setTerritoryCustomers(
    String territoryId,
    List<TerritoryCustomerAssignmentRecord> assignments,
  ) async {
    savedTerritoryId = territoryId;
    saved = assignments;
    return assignments;
  }
}

Future<void> _pump(
  WidgetTester tester,
  _BuilderApi api, {
  bool canAssign = true,
}) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: RouteBuilderPage(
        api: api,
        permissions: _permissions(canAssign: canAssign),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

/// Choose the only route in the dropdown, which loads the round and searches.
Future<void> _pickRoute(WidgetTester tester) async {
  await tester.tap(find.byType(DropdownButtonFormField<String>));
  await tester.pumpAndSettle();
  await tester.tap(find.text('RT01 - RT01 round').last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a pin code and a street reach the server', (tester) async {
    final api = _BuilderApi(outlets: <Json>[_outletJson(id: 'c1', code: 'C1')]);
    await _pump(tester, api);
    await _pickRoute(tester);

    await tester.enterText(
      find.widgetWithText(TextField, 'Pin code'),
      '600001',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Street / area'),
      'Parrys',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Find'));
    await tester.pumpAndSettle();

    expect(api.queries.last['postal_code'], '600001');
    expect(api.queries.last['area'], 'Parrys');
  });

  testWidgets('the on-no-route filter is sent', (tester) async {
    final api = _BuilderApi(outlets: <Json>[_outletJson(id: 'c1', code: 'C1')]);
    await _pump(tester, api);
    await _pickRoute(tester);

    await tester.tap(find.text('On no route yet'));
    await tester.pumpAndSettle();

    expect(api.queries.last['unassigned_only'], true);
  });

  testWidgets('an outlet already on another round says which', (tester) async {
    final api = _BuilderApi(outlets: <Json>[
      _outletJson(id: 'c1', code: 'C1', otherRoutes: <String>['COLL01']),
    ]);
    await _pump(tester, api);
    await _pickRoute(tester);

    // Information, not a warning: one shop on a sales beat and a collection
    // round is the ordinary case.
    expect(find.text('COLL01'), findsOneWidget);
  });

  testWidgets('adding outlets and saving sends them in list order',
      (tester) async {
    final api = _BuilderApi(outlets: <Json>[
      _outletJson(id: 'c1', code: 'C1'),
      _outletJson(id: 'c2', code: 'C2'),
    ]);
    await _pump(tester, api);
    await _pickRoute(tester);

    // Double-click adds, which is the fastest way to walk a result list.
    for (final String code in <String>['C2', 'C1']) {
      final Finder cell = find.text('$code Stores').first;
      await tester.tap(cell);
      await tester.pump(const Duration(milliseconds: 40));
      await tester.tap(cell);
      await tester.pumpAndSettle();
    }

    await tester.tap(find.widgetWithText(FilledButton, 'Save round and order'));
    await tester.pumpAndSettle();

    expect(api.savedTerritoryId, 'rt-1');
    expect(api.saved, isNotNull);
    // Order is position in the panel, numbered from one — C2 was added first.
    expect(
      api.saved!.map((row) => row.customerId).toList(),
      <String>['c2', 'c1'],
    );
    expect(api.saved!.map((row) => row.visitSequence).toList(), <int>[1, 2]);
  });

  testWidgets('a round already built loads in its saved call order',
      (tester) async {
    final api = _BuilderApi(outlets: <Json>[
      _outletJson(id: 'c1', code: 'C1', onThisRoute: true, sequence: 2),
      _outletJson(id: 'c2', code: 'C2', onThisRoute: true, sequence: 1),
    ]);
    await _pump(tester, api);
    await _pickRoute(tester);

    await tester.tap(find.widgetWithText(FilledButton, 'Save round and order'));
    await tester.pumpAndSettle();

    // Saved sequence, not the order the server happened to list them in.
    expect(
      api.saved!.map((row) => row.customerId).toList(),
      <String>['c2', 'c1'],
    );
  });

  testWidgets('a user who cannot assign cannot save', (tester) async {
    final api = _BuilderApi(outlets: <Json>[_outletJson(id: 'c1', code: 'C1')]);
    await _pump(tester, api, canAssign: false);
    await _pickRoute(tester);

    final FilledButton save = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Save round and order'),
    );
    expect(save.onPressed, isNull);
    expect(find.textContaining('cannot assign customers'), findsOneWidget);
  });

  testWidgets('a round that could not be read cannot be saved over',
      (tester) async {
    // Saving replaces the round with the panel, so the panel has to be the
    // truth about the selected route. If the read fails it holds nothing --
    // and it used to hold the *previous* route's shops, which one Save would
    // have written straight onto this one.
    final api = _BuilderApi(
      outlets: <Json>[_outletJson(id: 'c1', code: 'C1')],
      failRoundLoad: true,
    );
    await _pump(tester, api);
    await _pickRoute(tester);

    expect(
      find.text(
        'This round could not be read, so it cannot be saved over. '
        'Refresh to try again.',
      ),
      findsOneWidget,
    );
    final FilledButton save = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Save round and order'),
    );
    expect(save.onPressed, isNull);
    expect(api.saved, isNull);
  });
}
