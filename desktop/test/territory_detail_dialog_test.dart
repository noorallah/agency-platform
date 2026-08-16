// One territory, full screen — and a round drawn one stop at a time.
//
// The right-hand card on Geography had 300 pixels for a summary, the tree
// controls and the tree itself, and the two things you actually do to a route
// — put shops on it, then decide the order — lived in two separate dialogs.
//
// The behaviour worth protecting is the path. Clicking an outlet appends it as
// the next stop, so the order *is* the act of choosing: first click is START,
// last is END, and removing one closes the gap rather than leaving a hole in
// the numbering. And because saving replaces the whole round, a read that
// failed must refuse to save rather than offer an empty path that looks like a
// round waiting to be filled.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/sales_territory.dart';
import 'package:agency_desktop/ui/sales/territory_detail_dialog.dart';
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
      if (canAssign) 'TERRITORY_ASSIGN_SALESMEN',
    ],
  }));

SalesTerritory _territory() => SalesTerritory.fromJson(<String, dynamic>{
      'id': 'rt-1',
      'firm_id': 'firm-1',
      'hierarchy_level_id': 'lvl-route',
      'hierarchy_level_name': 'Route',
      'code': 'RT01',
      'name': 'North Beat',
      'status': 'ACTIVE',
      'path': 'RGN/NORTH/RT01',
      'sort_order': 0,
      'customer_count': 2,
      'salesman_count': 0,
      'route_profile': <String, dynamic>{
        'route_type_name': 'Sales Route',
        'visit_frequency': 'WEEKLY',
        'working_days': <int>[1, 3],
        'effective_from': '2026-01-01',
        'effective_to': '2026-12-31',
      },
    });

Json _outlet({
  required String id,
  required String code,
  bool onThisRoute = false,
  int? sequence,
  List<String> otherRoutes = const <String>[],
}) =>
    <String, dynamic>{
      'customer_id': id,
      'code': code,
      'name': '$code Stores',
      'address_line': '1 Big Street',
      'area': 'Parrys',
      'city': 'Chennai',
      'postal_code': '600001',
      'on_this_route': onThisRoute,
      'visit_sequence': sequence,
      'other_routes': otherRoutes,
    };

class _DetailApi extends ApiClient {
  _DetailApi({this.outlets = const <Json>[], this.failRead = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> outlets;
  final bool failRead;

  /// Every page size the screen asked for. The server refuses anything above
  /// 100, so a fake that ignores this would hide a screen that is broken
  /// against a real backend — which is exactly what happened.
  final List<int> requestedPageSizes = <int>[];

  List<TerritoryCustomerAssignmentRecord>? saved;
  String? savedTerritoryId;

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
    requestedPageSizes.add(pageSize);
    if (failRead) throw const ApiException('The round could not be read.');
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

  @override
  Future<List<Json>> territorySalesmen(String territoryId) async =>
      const <Json>[];

  @override
  Future<List<TerritorySalesmanCandidate>>
      territorySalesmanCandidates() async => const <TerritorySalesmanCandidate>[];
}

Future<void> _pump(
  WidgetTester tester,
  _DetailApi api, {
  bool canAssign = true,
}) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: TerritoryDetailDialog(
        api: api,
        permissions: _permissions(canAssign: canAssign),
        territory: _territory(),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _openCustomers(WidgetTester tester) async {
  // The tabs are a SegmentedButton, and every tab's child is built inside an
  // IndexedStack — so "Customers" also exists as a row label on the Details
  // tab. Aim at the segment.
  await tester.tap(
    find.descendant(
      of: find.byType(SegmentedButton<int>),
      matching: find.text('Customers'),
    ),
  );
  await tester.pumpAndSettle();
}

/// The stop number shown beside an outlet in the left-hand list.
String? _leadingNumber(WidgetTester tester, String outletName) {
  final Finder tile = find.ancestor(
    of: find.text(outletName),
    matching: find.byType(ListTile),
  );
  final Finder text = find.descendant(
    of: find.descendant(of: tile.first, matching: find.byType(CircleAvatar)),
    matching: find.byType(Text),
  );
  if (text.evaluate().isEmpty) return null;
  return tester.widget<Text>(text.first).data;
}

void main() {
  testWidgets('the details tab shows the route and its window', (tester) async {
    await _pump(tester, _DetailApi());

    expect(find.text('RT01 — North Beat'), findsOneWidget);
    expect(find.text('Sales Route'), findsOneWidget);
    expect(find.text('Weekly'), findsOneWidget);
    expect(find.text('Mon, Wed'), findsOneWidget);
    expect(find.text('2026-12-31'), findsOneWidget);
  });

  testWidgets('clicking outlets in turn lays out start to end', (tester) async {
    final api = _DetailApi(outlets: <Json>[
      _outlet(id: 'c1', code: 'C1'),
      _outlet(id: 'c2', code: 'C2'),
      _outlet(id: 'c3', code: 'C3'),
    ]);
    await _pump(tester, api);
    await _openCustomers(tester);

    for (final String code in <String>['C2', 'C3', 'C1']) {
      await tester.tap(find.text('$code Stores').first);
      await tester.pumpAndSettle();
    }

    // The order is the act of choosing, not a second sorting step.
    expect(_leadingNumber(tester, 'C2 Stores'), '1');
    expect(_leadingNumber(tester, 'C3 Stores'), '2');
    expect(_leadingNumber(tester, 'C1 Stores'), '3');
    expect(find.textContaining('START'), findsOneWidget);
    expect(find.textContaining('END'), findsOneWidget);
    expect(find.text('The path — 3 stop(s)'), findsOneWidget);
  });

  testWidgets('clicking a stop again removes it and closes the gap',
      (tester) async {
    final api = _DetailApi(outlets: <Json>[
      _outlet(id: 'c1', code: 'C1'),
      _outlet(id: 'c2', code: 'C2'),
      _outlet(id: 'c3', code: 'C3'),
    ]);
    await _pump(tester, api);
    await _openCustomers(tester);
    for (final String code in <String>['C1', 'C2', 'C3']) {
      await tester.tap(find.text('$code Stores').first);
      await tester.pumpAndSettle();
    }

    await tester.tap(find.text('C2 Stores').first);
    await tester.pumpAndSettle();

    expect(_leadingNumber(tester, 'C1 Stores'), '1');
    expect(_leadingNumber(tester, 'C3 Stores'), '2');
    expect(find.text('The path — 2 stop(s)'), findsOneWidget);
  });

  testWidgets('a round already built opens in its saved order', (tester) async {
    final api = _DetailApi(outlets: <Json>[
      _outlet(id: 'c1', code: 'C1', onThisRoute: true, sequence: 2),
      _outlet(id: 'c2', code: 'C2', onThisRoute: true, sequence: 1),
      _outlet(id: 'c3', code: 'C3'),
    ]);
    await _pump(tester, api);
    await _openCustomers(tester);

    expect(_leadingNumber(tester, 'C2 Stores'), '1');
    expect(_leadingNumber(tester, 'C1 Stores'), '2');
  });

  testWidgets('saving sends the path as stop numbers from one', (tester) async {
    final api = _DetailApi(outlets: <Json>[
      _outlet(id: 'c1', code: 'C1'),
      _outlet(id: 'c2', code: 'C2'),
    ]);
    await _pump(tester, api);
    await _openCustomers(tester);
    await tester.tap(find.text('C2 Stores').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('C1 Stores').first);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Save round and order'));
    await tester.pumpAndSettle();

    expect(api.savedTerritoryId, 'rt-1');
    expect(
      api.saved!.map((row) => row.customerId).toList(),
      <String>['c2', 'c1'],
    );
    expect(api.saved!.map((row) => row.visitSequence).toList(), <int>[1, 2]);
  });

  testWidgets('a round that could not be read cannot be saved over',
      (tester) async {
    // Saving replaces the whole round, so an unread path must refuse rather
    // than present itself as an empty one.
    await _pump(tester, _DetailApi(failRead: true));
    await _openCustomers(tester);

    expect(find.textContaining('could not be read'), findsWidgets);
    expect(find.text('Save round and order'), findsNothing);
  });

  testWidgets('a user who cannot assign gets the path read-only',
      (tester) async {
    final api = _DetailApi(
      outlets: <Json>[_outlet(id: 'c1', code: 'C1')],
    );
    await _pump(tester, api, canAssign: false);
    await _openCustomers(tester);

    await tester.tap(find.text('C1 Stores').first);
    await tester.pumpAndSettle();

    expect(find.text('The path — 0 stop(s)'), findsOneWidget);
    expect(
      find.text('Read-only — you cannot assign customers to a route.'),
      findsOneWidget,
    );
    expect(api.saved, isNull);
  });

  testWidgets('the outlets are read in pages the server will serve',
      (tester) async {
    // `MAX_PAGE_SIZE` is 100 and the routers that build their pagination by
    // hand answer 500 rather than a message naming the limit, so asking for
    // 500 broke this tab against every real backend while the fakes stayed
    // green.
    final api = _DetailApi(outlets: <Json>[_outlet(id: 'c1', code: 'C1')]);
    await _pump(tester, api);

    expect(api.requestedPageSizes, isNotEmpty);
    expect(api.requestedPageSizes.every((size) => size <= 100), isTrue);
  });
}
