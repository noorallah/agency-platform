// The firm's own list of salesmen (P2): Settings > Selling > Salesmen.
//
// Every `salesman_id` on an order, a bill, a round, a target, a commission
// rule, a customer and a promotion names an entry of this list, not a user.
// The screen lists, adds, edits, deletes and restores entries; an entry may
// be tied to a user account, chosen from the firm's people. Deleting
// somebody a document names makes them inactive instead -- the server
// decides, and the screen says which happened.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/firm_member.dart';
import 'package:agency_desktop/models/salesman.dart';
import 'package:agency_desktop/ui/sales/firm_salesmen.dart';
import 'package:agency_desktop/ui/sales/salesmen_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken(<String, dynamic>{
    'roles': <String>['user'],
    'permissions': codes,
  }));

class _SalesmenApi extends ApiClient {
  _SalesmenApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// The list as the server holds it.
  final List<Json> rows = <Json>[
    <String, dynamic>{
      'id': 'sm-meera',
      'version': 3,
      'code': 'MR',
      'name': 'Meera Raghavan',
      'user_id': 'user-meera',
      'phone': '98450 00001',
      'earns_commission': true,
      'is_active': true,
      'notes': null,
    },
    <String, dynamic>{
      'id': 'sm-ravi',
      'version': 1,
      'code': null,
      'name': 'Ravi Kumar',
      'user_id': null,
      'phone': null,
      'earns_commission': false,
      'is_active': true,
      'notes': null,
    },
  ];

  /// Ids the server refuses to delete because a document names them; it
  /// makes them inactive instead.
  final Set<String> inUse = <String>{};

  /// What `GET /salesmen` was asked with, in order.
  final List<Map<String, Object?>> listed = <Map<String, Object?>>[];
  Json? created;
  Json? updated;
  int? sentVersion;
  final List<String> deleted = <String>[];
  final List<String> restored = <String>[];

  @override
  Future<List<FirmMember>> firmMembers() async => const <FirmMember>[
        FirmMember(userId: 'user-meera', fullName: 'Meera R (user)'),
        FirmMember(userId: 'user-asha', fullName: 'Asha Rao (user)'),
      ];

  @override
  Future<PagedResult<Salesman>> salesmenPage({
    int page = 1,
    int pageSize = 100,
    String search = '',
    String sortBy = 'name',
    bool descending = false,
    bool? active,
  }) async {
    listed.add(<String, Object?>{
      'sort_by': sortBy,
      'descending': descending,
      'active': active,
    });
    final List<Salesman> items = <Salesman>[
      for (final Json row in rows)
        if (active == null || row['is_active'] == active)
          Salesman.fromJson(row),
    ];
    return PagedResult<Salesman>(items: items, total: items.length);
  }

  @override
  Future<Json> create(String resource, Json body) async {
    created = <String, dynamic>{'resource': resource, ...body};
    rows.add(<String, dynamic>{'id': 'sm-new', 'version': 1, ...body});
    return <String, dynamic>{
      'data': <String, dynamic>{'id': 'sm-new', ...body},
    };
  }

  @override
  Future<Salesman> updateSalesman(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    updated = data;
    sentVersion = expectedVersion;
    return Salesman.fromJson(<String, dynamic>{'id': id, ...data});
  }

  @override
  Future<void> deleteSalesman(String id) async {
    deleted.add(id);
    if (inUse.contains(id)) {
      for (final Json row in rows) {
        if (row['id'] == id) row['is_active'] = false;
      }
      return;
    }
    rows.removeWhere((row) => row['id'] == id);
  }

  @override
  Future<Salesman> salesman(String id) async {
    for (final Json row in rows) {
      if (row['id'] == id) return Salesman.fromJson(row);
    }
    throw const ApiException('Salesman not found.', statusCode: 404);
  }

  @override
  Future<Salesman> restoreSalesman(String id) async {
    restored.add(id);
    final Json back = <String, dynamic>{
      'id': id,
      'version': 2,
      'name': 'Ravi Kumar',
      'is_active': true,
    };
    rows.add(back);
    return Salesman.fromJson(back);
  }
}

class _CountingApi extends ApiClient {
  _CountingApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  int reads = 0;

  @override
  Future<List<Salesman>> firmSalesmen() async {
    reads += 1;
    return const <Salesman>[Salesman(id: 'sm-1', name: 'Ravi Kumar')];
  }
}

Future<void> _pump(
  WidgetTester tester,
  _SalesmenApi api, {
  List<String> codes = const <String>['SALESMAN_MANAGE'],
}) async {
  tester.view.physicalSize = const Size(1600, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: SalesmenPage(api: api, permissions: _permissions(codes)),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester, String name) async {
  await tester.tap(find.text(name).first);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

Finder _inDialog(Finder matching) =>
    find.descendant(of: find.byType(Dialog), matching: matching);

void main() {
  testWidgets('the list reads by name and says who is tied to a user',
      (tester) async {
    final _SalesmenApi api = _SalesmenApi();
    await _pump(tester, api);

    expect(find.text('Meera Raghavan'), findsOneWidget);
    expect(find.text('Ravi Kumar'), findsOneWidget);
    // Tied to a user: their name from the firm's people; untied says so.
    expect(find.text('Meera R (user)'), findsOneWidget);
    expect(find.text('Not tied to a user'), findsOneWidget);
    expect(find.text('Does not earn'), findsOneWidget);
    expect(api.listed.first['sort_by'], 'name');
    expect(api.listed.first['descending'], isFalse);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a salesman is added, tied to a user account', (tester) async {
    final _SalesmenApi api = _SalesmenApi();
    await _pump(tester, api);

    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();
    await tester.enterText(
        _inDialog(find.widgetWithText(TextField, 'Name')), '  Asha Rao ');
    await tester.enterText(
        _inDialog(find.widgetWithText(TextField, 'Code')), 'ar');
    await tester.tap(_inDialog(find.text('Not tied to a user')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Asha Rao (user)').last);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save & Close').last);
    await tester.pumpAndSettle();

    expect(api.created, isNotNull);
    expect(api.created!['resource'], 'salesmen');
    expect(api.created!['name'], 'Asha Rao');
    expect(api.created!['code'], 'ar');
    expect(api.created!['user_id'], 'user-asha');
    expect(api.created!['earns_commission'], isTrue);
    expect(api.created!['is_active'], isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets('an edit is sent with the version it was read at',
      (tester) async {
    final _SalesmenApi api = _SalesmenApi();
    await _pump(tester, api);
    await _select(tester, 'Meera Raghavan');

    await tester.tap(find.byKey(const ValueKey('selection-edit')));
    await tester.pumpAndSettle();
    await tester.enterText(
        _inDialog(find.widgetWithText(TextField, 'Phone')), '98450 99999');
    await tester.tap(find.widgetWithText(FilledButton, 'Save & Close').last);
    await tester.pumpAndSettle();

    expect(api.updated?['phone'], '98450 99999');
    expect(api.updated?['user_id'], 'user-meera');
    expect(api.sentVersion, 3);
  });

  testWidgets('a deleted salesman can be restored while the screen is open',
      (tester) async {
    final _SalesmenApi api = _SalesmenApi();
    await _pump(tester, api);
    expect(find.widgetWithText(OutlinedButton, 'Restore deleted'),
        findsNothing);

    await _select(tester, 'Ravi Kumar');
    await tester.tap(find.byKey(const ValueKey('selection-delete')));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Delete'));
    await tester.pumpAndSettle();

    expect(api.deleted, <String>['sm-ravi']);
    expect(find.text('Ravi Kumar'), findsNothing);
    expect(find.textContaining('Restore deleted brings them back'),
        findsOneWidget);

    await tester.tap(find.widgetWithText(OutlinedButton, 'Restore deleted'));
    await tester.pumpAndSettle();

    expect(api.restored, <String>['sm-ravi']);
    expect(find.text('Ravi Kumar'), findsOneWidget);
    expect(find.widgetWithText(OutlinedButton, 'Restore deleted'),
        findsNothing);
  });

  testWidgets('a salesman in use is made inactive, and the screen says so',
      (tester) async {
    final _SalesmenApi api = _SalesmenApi()..inUse.add('sm-meera');
    await _pump(tester, api);
    await _select(tester, 'Meera Raghavan');
    await tester.tap(find.byKey(const ValueKey('selection-delete')));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Delete'));
    await tester.pumpAndSettle();

    expect(find.textContaining('made inactive instead'), findsOneWidget);
    expect(find.text('Inactive'), findsOneWidget);
    expect(find.widgetWithText(OutlinedButton, 'Restore deleted'),
        findsNothing);
  });

  test('the list is read once per firm and again after a change', () async {
    final _CountingApi api = _CountingApi();
    String firm = 'firm-1';
    FirmSalesmen.configure(api: () => api, firmId: () => firm);
    addTearDown(FirmSalesmen.reset);

    await FirmSalesmen.of(api);
    await FirmSalesmen.of(api);
    expect(api.reads, 1, reason: 'one read per session, shared');

    FirmSalesmen.invalidate();
    await FirmSalesmen.of(api);
    expect(api.reads, 2, reason: 'the Salesmen screen changed the list');

    firm = 'firm-2';
    await FirmSalesmen.of(api);
    expect(api.reads, 3, reason: "another firm's list is its own");

    // A screen handed another client reads that one, never the cache.
    final _CountingApi other = _CountingApi();
    await FirmSalesmen.of(other);
    await FirmSalesmen.of(other);
    expect(other.reads, 2);
  });

  testWidgets('without SALESMAN_MANAGE the list is read-only', (tester) async {
    final _SalesmenApi api = _SalesmenApi();
    await _pump(tester, api, codes: const <String>['SALES_VIEW']);

    expect(find.text('Meera Raghavan'), findsOneWidget);
    // Nobody is offered a New they cannot use.
    expect(find.byKey(const ValueKey('toolbar-new')), findsNothing);
    await _select(tester, 'Meera Raghavan');
    expect(find.byKey(const ValueKey('selection-edit')), findsNothing);
    expect(find.byKey(const ValueKey('selection-delete')), findsNothing);
  });
}
