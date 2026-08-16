// A route must be creatable, editable and assignable from the screen.
//
// Raised from manual testing: "we have territory to identify sales route,
// collection route — where is that screen", then "we need ui also to add edit
// or assign routes".
//
// Two things were missing, both of them server capabilities with no client
// path:
//
//   * `TerritoryCreate` has accepted a `route_profile` since the module was
//     written, but the editor sent only code/name/level/parent/status. So you
//     could create a node at the Route level and never say whether it was a
//     sales beat or a collection round, nor how often it ran. The grid has a
//     "Route type" and a "Frequency" column, and both were permanently blank.
//   * Both assignment dialogs asked for **comma-separated UUIDs**. Nobody
//     knows a customer's id, so the feature existed and could not be used.
//
// The third case below is the one with teeth: the API replaces the whole
// salesman list, so re-sending an assignment without its `is_primary` flag
// silently demotes the primary salesperson for that route.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/models/sales_territory.dart';
import 'package:agency_desktop/ui/sales/sales_territory_management_page.dart';
import 'package:agency_desktop/ui/sales/territory_detail_dialog.dart';
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
      'TERRITORY_ASSIGN_CUSTOMERS',
      'TERRITORY_ASSIGN_SALESMEN',
    ],
  }));

Json _territoryJson({
  required String id,
  required String code,
  required String name,
  Json? routeProfile,
}) =>
    <String, dynamic>{
      'id': id,
      'firm_id': 'firm-1',
      'hierarchy_level_id': 'lvl-route',
      'hierarchy_level_name': 'Route',
      'code': code,
      'name': name,
      'status': 'ACTIVE',
      'path': name,
      'sort_order': 0,
      'customer_count': 0,
      'salesman_count': 0,
      'route_profile': routeProfile,
    };

class _TerritoryApi extends ApiClient {
  _TerritoryApi({
    required this.territory,
    this.routeTypes = const <Json>[
      <String, dynamic>{
        'id': 'rt-sales',
        'code': 'SALES',
        'name': 'Sales Route',
      },
      <String, dynamic>{
        'id': 'rt-collect',
        'code': 'COLLECTION',
        'name': 'Collection Route',
      },
    ],
    this.customerPages = const <List<Json>>[],
    this.customerTotal = 0,
    this.assignedSalesmen = const <Json>[],
    this.geoRows = const <GeoLevel, List<Json>>{},
  }) : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json territory;
  final List<Json> routeTypes;
  final List<List<Json>> customerPages;
  final int customerTotal;
  final List<Json> assignedSalesmen;
  final Map<GeoLevel, List<Json>> geoRows;

  Json? created;
  Json? updated;
  TerritoryQuery? lastQuery;
  List<String>? assignedCustomerIds;
  List<TerritoryCustomerAssignmentRecord>? sentAssignments;
  List<TerritoryCustomerAssignmentRecord> assignedCustomers =
      const <TerritoryCustomerAssignmentRecord>[];
  List<Json>? sentSalesmen;

  @override
  Future<TerritoryHierarchyRecord> territoryHierarchy() async =>
      TerritoryHierarchyRecord.fromJson(<String, dynamic>{
        'levels': <Json>[
          <String, dynamic>{
            'id': 'lvl-route',
            'code': 'ROUTE',
            'name': 'Route',
            'display_name': 'Route',
            'level_order': 3,
          },
        ],
      });

  @override
  Future<List<TerritoryTreeNodeRecord>> territoryTree({
    bool includeDeleted = false,
  }) async =>
      const <TerritoryTreeNodeRecord>[];

  @override
  Future<PagedResult<SalesTerritory>> territories({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    TerritoryQuery filters = const TerritoryQuery(),
  }) async {
    lastQuery = filters;
    return PagedResult<SalesTerritory>(
      items: <SalesTerritory>[SalesTerritory.fromJson(territory)],
      total: 1,
    );
  }

  @override
  Future<Json> territoryDashboard() async => <String, dynamic>{};

  /// The cities/pin codes/localities a round can be tagged with.
  @override
  Future<List<GeoPlaceRecord>> geoPlaces(
    GeoLevel level, {
    String parentId = '',
  }) async =>
      <GeoPlaceRecord>[
        for (final Json row in (geoRows[level] ?? const <Json>[]))
          GeoPlaceRecord.fromJson(level, row),
      ];

  @override
  Future<List<TerritoryRouteTypeRecord>> territoryRouteTypes() async =>
      <TerritoryRouteTypeRecord>[
        for (final Json row in routeTypes)
          TerritoryRouteTypeRecord.fromJson(row),
      ];

  @override
  Future<SalesTerritory> createTerritory(Json data) async {
    created = data;
    return SalesTerritory.fromJson(territory);
  }

  @override
  Future<SalesTerritory> updateTerritory(String id, Json data) async {
    updated = data;
    return SalesTerritory.fromJson(territory);
  }

  @override
  Future<PagedResult<Customer>> customers({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    CustomerQuery filters = const CustomerQuery(),
  }) async {
    final List<Json> rows =
        page <= customerPages.length ? customerPages[page - 1] : const <Json>[];
    return PagedResult<Customer>(
      items: <Customer>[for (final Json row in rows) Customer.fromJson(row)],
      total: customerTotal,
    );
  }

  @override
  Future<List<TerritoryCustomerAssignmentRecord>> territoryCustomers(
    String territoryId,
  ) async =>
      assignedCustomers;

  @override
  Future<List<TerritoryCustomerAssignmentRecord>> setTerritoryCustomers(
    String territoryId,
    List<TerritoryCustomerAssignmentRecord> assignments, {
    bool includePotential = false,
  }) async {
    sentAssignments = assignments;
    assignedCustomerIds = [for (final row in assignments) row.customerId];
    return assignments;
  }

  @override
  Future<List<TerritorySalesmanCandidate>>
      territorySalesmanCandidates() async => <TerritorySalesmanCandidate>[
            TerritorySalesmanCandidate.fromJson(<String, dynamic>{
              'user_id': 'user-1',
              'full_name': 'Ravi Kumar',
              'email': 'ravi@agency.local',
            }),
          ];

  @override
  Future<List<Json>> territorySalesmen(String territoryId) async =>
      assignedSalesmen;

  @override
  Future<List<Json>> setTerritorySalesmen(
    String territoryId,
    List<Json> assignments,
  ) async {
    sentSalesmen = assignments;
    return assignments;
  }
}

Future<void> _pump(WidgetTester tester, _TerritoryApi api) async {
  // Physical size with an explicit ratio of 1. `setSurfaceSize` alone leaves
  // the test's default 3.0 device pixel ratio in place, which makes a 1600px
  // window 533 logical pixels wide — narrow enough that the layout drops the
  // details panel, and the assignment buttons live in it.
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: SalesTerritoryManagementPage(
        api: api,
        permissions: _permissions(),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _openNew(WidgetTester tester) async {
  await tester.tap(find.widgetWithText(FilledButton, 'New').first);
  await tester.pumpAndSettle();
}

/// Selecting a row is what reveals the details panel, and the assignment
/// buttons live there.
Future<void> _selectRow(WidgetTester tester, String code) async {
  await tester.tap(find.text(code).first);
  // The cell also carries `onDoubleTap`, so a single tap only resolves once
  // the double-tap window closes. `pumpAndSettle` alone stops before then,
  // because nothing has scheduled a frame.
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _openEdit(WidgetTester tester) async {
  await tester.tap(find.byTooltip('Edit'));
  await tester.pumpAndSettle();
}

Future<void> _tapAssign(WidgetTester tester, String label) async {
  await tester.tap(find.widgetWithText(OutlinedButton, label));
  await tester.pumpAndSettle();
}

/// Scoped to the dialog on purpose. The page underneath has a toolbar
/// `DropdownButtonFormField<String>` of its own, and it sits **earlier** in the
/// tree than the overlay, so an unscoped `.first` reaches for the widget behind
/// the modal barrier and the tap silently misses.
Finder _inDialog(Finder matching) =>
    find.descendant(of: find.byType(AlertDialog), matching: matching);

Future<void> _pickFromDropdown(
  WidgetTester tester,
  Finder dropdown,
  String optionText,
) async {
  // The editor scrolls once the route fields are showing, so a field can be
  // built and still be off the bottom of the dialog.
  await tester.ensureVisible(dropdown);
  await tester.pumpAndSettle();
  await tester.tap(dropdown);
  await tester.pumpAndSettle();
  await tester.tap(find.text(optionText).last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a new route can say what kind it is and when it runs',
      (tester) async {
    final _TerritoryApi api = _TerritoryApi(
      territory: _territoryJson(id: 't-1', code: 'RT01', name: 'North Beat'),
    );
    await _pump(tester, api);
    await _openNew(tester);

    await tester.enterText(
        _inDialog(find.widgetWithText(TextField, 'Code')), 'RT02');
    await tester.enterText(
        _inDialog(find.widgetWithText(TextField, 'Name')), 'South');
    await _pickFromDropdown(
      tester,
      _inDialog(find.byType(DropdownButtonFormField<String>)).first,
      'Route',
    );

    // Off by default: a region and a zone are territories too, and giving
    // every node a route profile is what "infer it from the fields" would do.
    expect(
        tester
            .widget<SwitchListTile>(_inDialog(find.byType(SwitchListTile)))
            .value,
        isFalse);
    final Finder routeSwitch = _inDialog(find.text('This is a route'));
    await tester.ensureVisible(routeSwitch);
    await tester.pumpAndSettle();
    await tester.tap(routeSwitch);
    await tester.pumpAndSettle();

    await _pickFromDropdown(
      tester,
      _inDialog(find.byType(DropdownButtonFormField<String?>)),
      'COLLECTION - Collection Route',
    );

    for (final String day in <String>['Mon', 'Thu']) {
      final Finder chip = _inDialog(find.widgetWithText(FilterChip, day));
      await tester.ensureVisible(chip);
      await tester.pumpAndSettle();
      await tester.tap(chip);
      await tester.pumpAndSettle();
    }

    await tester.tap(_inDialog(find.widgetWithText(FilledButton, 'Save')));
    await tester.pumpAndSettle();

    final Json? profile = api.created?['route_profile'] as Json?;
    expect(profile, isNotNull,
        reason: 'the editor never sent a route profile — the reported gap');
    expect(profile!['route_type_id'], 'rt-collect');
    expect(profile['visit_frequency'], 'ON_DEMAND');
    expect(profile['working_days'], <int>[1, 4]);
    // Sent as nulls rather than left out: the API replaces the profile whole.
    expect(profile['effective_from'], isNull);
    expect(profile['city_id'], isNull);
  });

  testWidgets('a firm with no route types can still save a route',
      (tester) async {
    // Nothing in this client creates route types — the API has a POST and no
    // screen calls it — so the helper text must not send anybody looking for
    // one, and the save must go through without a type.
    final _TerritoryApi api = _TerritoryApi(
      territory: _territoryJson(id: 't-1', code: 'RT01', name: 'North Beat'),
      routeTypes: const <Json>[],
    );
    await _pump(tester, api);
    await _openNew(tester);

    await tester.enterText(
        _inDialog(find.widgetWithText(TextField, 'Code')), 'RT03');
    await tester.enterText(
        _inDialog(find.widgetWithText(TextField, 'Name')), 'Untyped');
    await _pickFromDropdown(
      tester,
      _inDialog(find.byType(DropdownButtonFormField<String>)).first,
      'Route',
    );
    final Finder routeSwitch = _inDialog(find.text('This is a route'));
    await tester.ensureVisible(routeSwitch);
    await tester.pumpAndSettle();
    await tester.tap(routeSwitch);
    await tester.pumpAndSettle();

    expect(find.textContaining('a route saves without one'), findsOneWidget);
    expect(find.textContaining('Route Types'), findsNothing,
        reason: 'that screen does not exist');

    await tester.tap(_inDialog(find.widgetWithText(FilledButton, 'Save')));
    await tester.pumpAndSettle();

    final Json? profile = api.created?['route_profile'] as Json?;
    expect(profile, isNotNull);
    expect(profile!['route_type_id'], isNull);
  });

  testWidgets('a territory that is not a route sends no profile',
      (tester) async {
    final _TerritoryApi api = _TerritoryApi(
      territory: _territoryJson(id: 't-1', code: 'RT01', name: 'North Beat'),
    );
    await _pump(tester, api);
    await _openNew(tester);

    await tester.enterText(
        _inDialog(find.widgetWithText(TextField, 'Code')), 'ZN01');
    await tester.enterText(
        _inDialog(find.widgetWithText(TextField, 'Name')), 'Zone');
    await _pickFromDropdown(
      tester,
      _inDialog(find.byType(DropdownButtonFormField<String>)).first,
      'Route',
    );
    await tester.tap(_inDialog(find.widgetWithText(FilledButton, 'Save')));
    await tester.pumpAndSettle();

    expect(api.created, isNotNull);
    expect(api.created!.containsKey('route_profile'), isFalse);
  });

  testWidgets('an existing route opens with its profile shown', (tester) async {
    final _TerritoryApi api = _TerritoryApi(
      territory: _territoryJson(
        id: 't-1',
        code: 'RT01',
        name: 'North Beat',
        routeProfile: <String, dynamic>{
          'route_type_id': 'rt-sales',
          'route_type_name': 'Sales Route',
          'visit_frequency': 'WEEKLY',
          'working_days': <int>[2, 5],
        },
      ),
    );
    await _pump(tester, api);
    await _selectRow(tester, 'RT01');
    await _openEdit(tester);

    expect(
        tester
            .widget<SwitchListTile>(_inDialog(find.byType(SwitchListTile)))
            .value,
        isTrue);
    expect(find.text('Weekly'), findsWidgets);
    expect(
      tester
          .widget<FilterChip>(_inDialog(find.widgetWithText(FilterChip, 'Tue')))
          .selected,
      isTrue,
    );
    expect(
      tester
          .widget<FilterChip>(_inDialog(find.widgetWithText(FilterChip, 'Mon')))
          .selected,
      isFalse,
    );
  });

  testWidgets('a route keeps an area it was tagged with elsewhere',
      (tester) async {
    // The payload replaces the profile whole, so a value the reader cannot see
    // must still survive a save. `city-9` is deliberately absent from the
    // loaded cities -- a retired city, or a geography read that failed -- and
    // the dropdown must neither drop it nor assert on it.
    final _TerritoryApi api = _TerritoryApi(
      territory: _territoryJson(
        id: 't-1',
        code: 'RT01',
        name: 'North Beat',
        routeProfile: <String, dynamic>{
          'route_type_id': 'rt-sales',
          'route_type_name': 'Sales Route',
          'visit_frequency': 'WEEKLY',
          'effective_from': '2026-04-01',
          'effective_to': '2027-03-31',
          'city_id': 'city-9',
          'working_days': <int>[2],
        },
      ),
    );
    await _pump(tester, api);
    await _selectRow(tester, 'RT01');
    await _openEdit(tester);

    final Finder wed = _inDialog(find.widgetWithText(FilterChip, 'Wed'));
    await tester.ensureVisible(wed);
    await tester.pumpAndSettle();
    await tester.tap(wed);
    await tester.pumpAndSettle();
    await tester.tap(_inDialog(find.widgetWithText(FilledButton, 'Save')));
    await tester.pumpAndSettle();

    final Json? profile = api.updated?['route_profile'] as Json?;
    expect(profile, isNotNull);
    expect(profile!['working_days'], <int>[2, 3]);
    expect(profile['effective_from'], '2026-04-01');
    expect(profile['effective_to'], '2027-03-31');
    expect(profile['city_id'], 'city-9');
  });

  testWidgets('customers are picked from a list, not typed as UUIDs',
      (tester) async {
    // Two pages, because the API caps a page at 100 and a customer on the
    // second page is one you could neither find nor take off a round.
    final _TerritoryApi api = _TerritoryApi(
      territory: _territoryJson(id: 't-1', code: 'RT01', name: 'North Beat'),
      customerTotal: 2,
      customerPages: <List<Json>>[
        <Json>[
          <String, dynamic>{
            'id': 'cust-1',
            'code': 'C001',
            'name': 'Anand Stores',
            'display_name': 'Anand Stores',
          },
        ],
        <Json>[
          <String, dynamic>{
            'id': 'cust-2',
            'code': 'C002',
            'name': 'Bright Mart',
            'display_name': 'Bright Mart',
          },
        ],
      ],
    );
    await _pump(tester, api);
    await _selectRow(tester, 'RT01');
    await _tapAssign(tester, 'Assign customers');

    expect(find.text('Anand Stores'), findsOneWidget);
    expect(find.text('Bright Mart'), findsOneWidget,
        reason: 'the second page was never read');

    await tester.tap(find.text('Bright Mart'));
    await tester.pumpAndSettle();
    await tester.tap(_inDialog(find.widgetWithText(FilledButton, 'Save')));
    await tester.pumpAndSettle();

    expect(api.assignedCustomerIds, <String>['cust-2']);
  });

  testWidgets('re-saving salespeople keeps the primary flag', (tester) async {
    final _TerritoryApi api = _TerritoryApi(
      territory: _territoryJson(id: 't-1', code: 'RT01', name: 'North Beat'),
      assignedSalesmen: <Json>[
        <String, dynamic>{
          'user_id': 'user-1',
          'is_primary': true,
          'include_children': true,
        },
      ],
    );
    await _pump(tester, api);
    await _selectRow(tester, 'RT01');
    await _tapAssign(tester, 'Assign salesmen');

    // Save without touching anything: the list is a replace, so the flags
    // have to come back with it.
    await tester.tap(_inDialog(find.widgetWithText(FilledButton, 'Save')));
    await tester.pumpAndSettle();

    expect(api.sentSalesmen, isNotNull);
    expect(api.sentSalesmen!.single['user_id'], 'user-1');
    expect(api.sentSalesmen!.single['is_primary'], isTrue,
        reason: 'the primary salesperson was silently demoted');
    expect(api.sentSalesmen!.single['include_children'], isTrue);
  });

  testWidgets('a route can say when it runs, and keeps it on a re-save',
      (tester) async {
    // The effective window used to be carried through the payload and never
    // shown, so nobody could set it — and the server read it nowhere anyway.
    // It now decides whether a round is called at all, so it has to be
    // visible and editable.
    final api = _TerritoryApi(
      territory: _territoryJson(
        id: 't-1',
        code: 'RT01',
        name: 'North Beat',
        routeProfile: <String, dynamic>{
          'visit_frequency': 'WEEKLY',
          'working_days': <int>[1],
          'effective_from': '2026-01-01',
          'effective_to': '2026-06-30',
        },
      ),
    );
    await _pump(tester, api);
    await _selectRow(tester, 'RT01');
    await _openEdit(tester);

    expect(_inDialog(find.text('2026-01-01')), findsOneWidget);
    expect(_inDialog(find.text('2026-06-30')), findsOneWidget);

    await tester.tap(_inDialog(find.widgetWithText(FilledButton, 'Save')));
    await tester.pumpAndSettle();

    final Json profile = api.updated!['route_profile'] as Json;
    expect(profile['effective_from'], '2026-01-01');
    expect(profile['effective_to'], '2026-06-30');
  });

  testWidgets('the View action opens the territory full screen', (tester) async {
    // Selecting a row used to fill a 300px card on the right. The summary
    // moved into a dialog with room for it, plus the customers and the round.
    final api = _TerritoryApi(
      territory: _territoryJson(
        id: 't-1',
        code: 'RT01',
        name: 'North Beat',
        routeProfile: <String, dynamic>{
          'route_type_name': 'Sales Route',
          'visit_frequency': 'WEEKLY',
          'working_days': <int>[1],
        },
      ),
    );
    await _pump(tester, api);
    await _selectRow(tester, 'RT01');

    // Two: the toolbar button and the grid's row-action column, which offers
    // View whenever a row can be opened. The toolbar comes first in the tree.
    await tester.tap(find.byTooltip('View').first);
    await tester.pumpAndSettle();

    expect(find.byType(TerritoryDetailDialog), findsOneWidget);
    expect(find.text('RT01 — North Beat'), findsOneWidget);
  });

  testWidgets('a route can say which area it covers', (tester) async {
    // These three columns have been on the route profile since the first
    // migration and no screen ever set one, so the `city_id` filter on the
    // territory list -- implemented server-side all along -- could never match.
    final _TerritoryApi api = _TerritoryApi(
      territory: _territoryJson(id: 't-1', code: 'RT01', name: 'North Beat'),
      geoRows: <GeoLevel, List<Json>>{
        GeoLevel.city: <Json>[
          <String, dynamic>{'id': 'city-1', 'code': 'CHE', 'name': 'Chennai'},
        ],
        GeoLevel.postalCode: <Json>[
          <String, dynamic>{'id': 'pin-1', 'postal_code': '600001'},
        ],
      },
    );
    await _pump(tester, api);
    await _openNew(tester);

    await tester.enterText(
        _inDialog(find.widgetWithText(TextField, 'Code')), 'RT02');
    await tester.enterText(
        _inDialog(find.widgetWithText(TextField, 'Name')), 'South');
    await _pickFromDropdown(
      tester,
      _inDialog(find.byType(DropdownButtonFormField<String>)).first,
      'Route',
    );
    final Finder routeSwitch = _inDialog(find.text('This is a route'));
    await tester.ensureVisible(routeSwitch);
    await tester.pumpAndSettle();
    await tester.tap(routeSwitch);
    await tester.pumpAndSettle();

    // City first: the pin code list only means anything under one.
    await _pickFromDropdown(
      tester,
      _inDialog(find.widgetWithText(DropdownButtonFormField<String>, 'City')),
      'Chennai',
    );
    await _pickFromDropdown(
      tester,
      _inDialog(
          find.widgetWithText(DropdownButtonFormField<String>, 'Pin code')),
      '600001',
    );

    await tester.tap(_inDialog(find.widgetWithText(FilledButton, 'Save')));
    await tester.pumpAndSettle();

    final Json profile = api.created!['route_profile'] as Json;
    expect(profile['city_id'], 'city-1');
    expect(profile['postal_code_id'], 'pin-1');
  });

  testWidgets('the grid can be narrowed to one area', (tester) async {
    final _TerritoryApi api = _TerritoryApi(
      territory: _territoryJson(id: 't-1', code: 'RT01', name: 'North Beat'),
      geoRows: <GeoLevel, List<Json>>{
        GeoLevel.city: <Json>[
          <String, dynamic>{'id': 'city-1', 'code': 'CHE', 'name': 'Chennai'},
        ],
      },
    );
    await _pump(tester, api);

    await tester.tap(find.widgetWithText(
        DropdownButtonFormField<String>, 'Area (city)'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Chennai').last);
    await tester.pumpAndSettle();

    expect(api.lastQuery?.cityId, 'city-1');
  });
}
