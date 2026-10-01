import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/branches/work_defaults_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A person's own usual branch and warehouse (backlog 44): it fills a blank
/// ahead of the firm's default, only when it is among the choices offered, and
/// never restricts anything.
BranchRecord _branch(String id, {bool isDefault = false}) =>
    BranchRecord.fromJson({
      'id': id,
      'code': id.toUpperCase(),
      'name': 'Branch $id',
      'display_name': 'Branch $id',
      'is_default': isDefault,
    });

WarehouseRecord _warehouse(
  String id, {
  required String branchId,
  bool isDefault = false,
}) =>
    WarehouseRecord.fromJson({
      'id': id,
      'code': id.toUpperCase(),
      'name': 'Store $id',
      'display_name': 'Store $id',
      'branch_id': branchId,
      'is_default': isDefault,
    });

class _Api extends ApiClient {
  _Api({this.ignored = const <String>[], this.branchId, this.warehouseId})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<String> ignored;
  final String? branchId;
  final String? warehouseId;
  final List<Json> writes = <Json>[];
  final List<String> paths = <String>[];

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
    if (path.endsWith('/my-work-defaults') || path.contains('/work-defaults/')) {
      paths.add('$method $path');
      if (method == 'PUT') {
        writes.add(Map<String, dynamic>.from(body!));
        return {'success': true, 'data': {...body, 'ignored': <String>[]}};
      }
      return {
        'success': true,
        'data': {
          'branch_id': branchId,
          'warehouse_id': warehouseId,
          'ignored': ignored,
        },
      };
    }
    final bool isBranches = path.endsWith('/branches');
    final List<Map<String, dynamic>> rows = isBranches
        ? [
            {'id': 'b1', 'name': 'North', 'display_name': 'North'},
            {'id': 'b2', 'name': 'South', 'display_name': 'South'},
          ]
        : [
            {
              'id': 'w1',
              'branch_id': 'b1',
              'name': 'North store',
              'display_name': 'North store',
            },
            {
              'id': 'w2',
              'branch_id': 'b2',
              'name': 'South store',
              'display_name': 'South store',
            },
          ];
    return {
      'success': true,
      'data': rows,
      'pagination': {
        'page': 1,
        'page_size': 100,
        'total_records': rows.length,
        'total_pages': 1,
      },
    };
  }
}

void main() {
  tearDown(UserWorkDefaults.clear);

  group('preferredBranchId', () {
    final List<BranchRecord> branches = [
      _branch('b1'),
      _branch('b2', isDefault: true),
    ];

    test('the firm default applies with no user default', () {
      expect(preferredBranchId(branches), 'b2');
    });

    test('the user default wins when it is in the list', () {
      UserWorkDefaults.branchId = 'b1';
      expect(preferredBranchId(branches), 'b1');
    });

    test('a user default not in the list is ignored', () {
      UserWorkDefaults.branchId = 'gone';
      expect(preferredBranchId(branches), 'b2');
    });
  });

  group('preferredWarehouseId', () {
    final List<WarehouseRecord> warehouses = [
      _warehouse('w1', branchId: 'b1', isDefault: true),
      _warehouse('w2', branchId: 'b1'),
      _warehouse('w3', branchId: 'b2', isDefault: true),
    ];

    test('the firm default applies with no user default', () {
      expect(preferredWarehouseId(warehouses, branchId: 'b1'), 'w1');
    });

    test('the user default wins when it is among the candidates', () {
      UserWorkDefaults.warehouseId = 'w2';
      expect(preferredWarehouseId(warehouses, branchId: 'b1'), 'w2');
      expect(preferredWarehouseId(warehouses), 'w2');
    });

    test('a user default of another branch is ignored for this branch', () {
      UserWorkDefaults.warehouseId = 'w3';
      expect(preferredWarehouseId(warehouses, branchId: 'b1'), 'w1');
    });

    test('clear() removes both', () {
      UserWorkDefaults.set(
        const WorkDefaults(branchId: 'b1', warehouseId: 'w1'),
      );
      UserWorkDefaults.clear();
      expect(UserWorkDefaults.branchId, isNull);
      expect(UserWorkDefaults.warehouseId, isNull);
    });
  });

  group('My Branch and Warehouse dialog', () {
    Future<void> open(WidgetTester tester, _Api api) async {
      await tester.binding.setSurfaceSize(const Size(1366, 768));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: WorkDefaultsDialog(api: api)),
        ),
      );
      await tester.pumpAndSettle();
    }

    Future<void> choose(WidgetTester tester, String key, String text) async {
      await tester.tap(find.byKey(ValueKey<String>(key)));
      await tester.pumpAndSettle();
      await tester.tap(find.text(text).last);
      await tester.pumpAndSettle();
    }

    testWidgets('Save sends the chosen branch and warehouse', (tester) async {
      final _Api api = _Api();
      await open(tester, api);
      await choose(tester, 'work-defaults-branch', 'South');
      await choose(tester, 'work-defaults-warehouse-b2', 'South store');
      await tester.tap(find.byKey(const ValueKey<String>('work-defaults-save')));
      await tester.pumpAndSettle();
      expect(api.writes, [
        {'branch_id': 'b2', 'warehouse_id': 'w2'},
      ]);
      expect(UserWorkDefaults.branchId, 'b2');
      expect(UserWorkDefaults.warehouseId, 'w2');
    });

    testWidgets('Clear sends nulls', (tester) async {
      final _Api api = _Api(branchId: 'b1', warehouseId: 'w1');
      UserWorkDefaults.set(const WorkDefaults(branchId: 'b1', warehouseId: 'w1'));
      await open(tester, api);
      await tester.tap(find.byKey(const ValueKey<String>('work-defaults-clear')));
      await tester.pumpAndSettle();
      expect(api.writes, [
        {'branch_id': null, 'warehouse_id': null},
      ]);
      expect(UserWorkDefaults.branchId, isNull);
    });

    testWidgets("an administrator sets another member's, not their own",
        (tester) async {
      // Backlog 44: the users grid opens the same form for somebody else.
      final _Api api = _Api(branchId: 'b1', warehouseId: 'w1');
      UserWorkDefaults.set(const WorkDefaults(branchId: 'b1', warehouseId: 'w1'));
      addTearDown(UserWorkDefaults.clear);
      await tester.binding.setSurfaceSize(const Size(1366, 768));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: WorkDefaultsDialog(
              api: api, userId: 'u-9', personName: 'Ravi K'),
        ),
      ));
      await tester.pumpAndSettle();
      expect(find.text('Branch and warehouse · Ravi K'), findsOneWidget);
      await choose(tester, 'work-defaults-branch', 'South');
      await choose(tester, 'work-defaults-warehouse-b2', 'South store');
      await tester.tap(find.byKey(const ValueKey<String>('work-defaults-save')));
      await tester.pumpAndSettle();
      expect(api.paths, [
        'GET /api/v1/branches/work-defaults/u-9',
        'PUT /api/v1/branches/work-defaults/u-9',
      ]);
      expect(api.writes, [
        {'branch_id': 'b2', 'warehouse_id': 'w2'},
      ]);
      // The signed-in person's own defaults are not theirs to replace.
      expect(UserWorkDefaults.branchId, 'b1');
      expect(UserWorkDefaults.warehouseId, 'w1');
    });

    testWidgets('shows an ignored message', (tester) async {
      final _Api api = _Api(
        ignored: ['The warehouse you usually work from has been retired.'],
      );
      await open(tester, api);
      expect(
        find.text('The warehouse you usually work from has been retired.'),
        findsOneWidget,
      );
    });
  });
}
