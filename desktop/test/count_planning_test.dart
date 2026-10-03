import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/physical_count.dart';
import 'package:agency_desktop/ui/inventory/count_plans_dialog.dart';
import 'package:agency_desktop/ui/inventory/physical_count_page.dart';
import 'package:agency_desktop/ui/inventory/physical_count_sheet_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Cycle-count planning (STK-6): plans, drawing a sheet from one, and the
/// blind count that withholds the system quantity from the counter.
PermissionService _permissions() {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({
      'permissions': ['INVENTORY_VIEW', 'INVENTORY_ADJUST'],
    })),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

Json _branchJson() => {
      'id': 'b-1',
      'code': 'MAIN',
      'name': 'Main Branch',
      'display_name': 'Main Branch',
    };

Json _warehouseJson() => {
      'id': 'w-1',
      'branch_id': 'b-1',
      'code': 'GOD',
      'name': 'Main Godown',
      'display_name': 'Main Godown',
      'status': 'ACTIVE',
    };

Json _planJson({bool due = true}) => {
      'id': 'plan-1',
      'name': 'Fast movers',
      'branch_id': 'b-1',
      'warehouse_id': 'w-1',
      'abc_class': 'A',
      'storage_node_id': null,
      'frequency_days': 7,
      'blind': true,
      'is_active': true,
      'last_counted_on': '2027-03-01',
      'next_due_on': '2027-03-08',
      'is_due': due,
      'version': 1,
    };

Json _sheetJson({bool blind = false, String status = 'DRAFT'}) => {
      'id': 'pc-1',
      'branch_id': 'b-1',
      'warehouse_id': 'w-1',
      'warehouse_name': 'Main Godown',
      'count_number': 'PC-000001',
      'count_date': '2027-03-31',
      'status': status,
      'remarks': '',
      'posted_at': '',
      'is_blind': blind,
      'count_plan_id': blind ? 'plan-1' : null,
      'lines': [
        {
          'id': 'l-1',
          'line_number': 1,
          'product_id': 'p-1',
          'product_code': 'SKU-1',
          'product_name': 'Widget',
          'batch_id': '',
          'expected_quantity': blind && status == 'DRAFT' ? null : '12.0000',
          'counted_quantity': '',
          'variance_quantity': '',
          'transaction_id': '',
          'remarks': '',
        },
      ],
    };

class _PlanApi extends ApiClient {
  _PlanApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? created;
  String? drawnPlan;
  String? drawnDate;
  Json? opened;
  bool postRefused = false;

  @override
  Future<List<CountPlan>> countPlans() async => [CountPlan.fromJson(_planJson())];

  @override
  Future<PagedResult<BranchRecord>> branches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BranchQuery filters = const BranchQuery(),
  }) async =>
      PagedResult<BranchRecord>(
        items: [BranchRecord.fromJson(_branchJson())],
        total: 1,
      );

  @override
  Future<PagedResult<WarehouseRecord>> warehouses({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    WarehouseQuery filters = const WarehouseQuery(),
  }) async =>
      PagedResult<WarehouseRecord>(
        items: [WarehouseRecord.fromJson(_warehouseJson())],
        total: 1,
      );

  @override
  Future<List<StorageNodeRecord>> storageNodes(
    String warehouseId, {
    bool includeDeleted = false,
  }) async =>
      const [];

  @override
  Future<CountPlan> createCountPlan(Json data) async {
    created = data;
    return CountPlan.fromJson(_planJson());
  }

  @override
  Future<PhysicalCountSheet> drawCountPlanSheet(
    String id, {
    required String countDate,
  }) async {
    drawnPlan = id;
    drawnDate = countDate;
    return PhysicalCountSheet.fromJson(_sheetJson(blind: true));
  }

  @override
  Future<PhysicalCountSheet> openPhysicalCount(Json data) async {
    opened = data;
    return PhysicalCountSheet.fromJson(_sheetJson());
  }

  @override
  Future<PagedResult<PhysicalCountSheet>> physicalCounts({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? countFrom,
    String? countTo,
  }) async =>
      const PagedResult<PhysicalCountSheet>(items: [], total: 0);

  @override
  Future<PhysicalCountSheet> physicalCount(String id) async =>
      PhysicalCountSheet.fromJson(_sheetJson(blind: true));

  @override
  Future<PhysicalCountSheet> recordPhysicalCount(String id, Json data) async =>
      PhysicalCountSheet.fromJson(_sheetJson(blind: true));

  @override
  Future<PhysicalCountSheet> postPhysicalCount(String id) async {
    if (postRefused) {
      throw ApiException(
        'The differences are worth more than your limit; the sheet stays a '
        'draft for somebody allowed more to post.',
      );
    }
    return PhysicalCountSheet.fromJson(_sheetJson(blind: true, status: 'POSTED'));
  }
}

Future<void> _pump(WidgetTester tester, Widget child) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(home: Scaffold(body: child)));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the plans grid shows a due plan and its schedule',
      (tester) async {
    await _pump(
      tester,
      CountPlansDialog(api: _PlanApi(), canManage: true),
    );

    expect(find.text('Fast movers'), findsOneWidget);
    expect(find.text('Main Godown'), findsOneWidget);
    expect(find.text('Class A'), findsOneWidget);
    expect(find.text('7 days'), findsOneWidget);
    expect(find.text('2027-03-01'), findsOneWidget);
    expect(find.text('2027-03-08 (due)'), findsOneWidget);
  });

  testWidgets('adding a plan posts the body', (tester) async {
    final _PlanApi api = _PlanApi();
    await _pump(tester, CountPlansDialog(api: api, canManage: true));

    await tester.tap(find.byKey(const ValueKey<String>('count-plan-add')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey<String>('count-plan-name')), 'Weekly A');
    await tester.enterText(
        find.byKey(const ValueKey<String>('count-plan-days')), '14');
    await tester.tap(find.byKey(const ValueKey<String>('count-plan-blind')));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.created, isNotNull);
    expect(api.created!['name'], 'Weekly A');
    expect(api.created!['branch_id'], 'b-1');
    expect(api.created!['warehouse_id'], 'w-1');
    expect(api.created!['frequency_days'], 14);
    expect(api.created!['blind'], true);
    expect(api.created!['is_active'], true);
    expect(api.created!['abc_class'], isNull);
  });

  testWidgets('draw sheet calls the plan path and returns the sheet',
      (tester) async {
    final _PlanApi api = _PlanApi();
    PhysicalCountSheet? drawn;
    await _pump(
      tester,
      Builder(
        builder: (context) => TextButton(
          onPressed: () async => drawn = await showDialog<PhysicalCountSheet>(
            context: context,
            builder: (_) => CountPlansDialog(api: api, canManage: true),
          ),
          child: const Text('open plans'),
        ),
      ),
    );
    await tester.tap(find.text('open plans'));
    await tester.pumpAndSettle();
    final Finder draw =
        find.byKey(const ValueKey<String>('count-plan-draw-plan-1'));
    await tester.ensureVisible(draw);
    await tester.pumpAndSettle();
    await tester.tap(draw);
    await tester.pumpAndSettle();

    expect(api.drawnPlan, 'plan-1');
    expect(api.drawnDate, matches(RegExp(r'^\d{4}-\d{2}-\d{2}$')));
    expect(drawn?.countNumber, 'PC-000001');
    expect(drawn?.isBlind, isTrue);
  });

  testWidgets('a blind draft hides expected and difference', (tester) async {
    await _pump(
      tester,
      PhysicalCountSheetDialog(
        api: _PlanApi(),
        sheet: PhysicalCountSheet.fromJson(_sheetJson(blind: true)),
        canCount: true,
      ),
    );

    expect(find.byKey(const ValueKey<String>('blind-count-badge')),
        findsOneWidget);
    expect(find.text('Expected'), findsNothing);
    expect(find.text('Difference'), findsNothing);
    expect(find.text('Counted'), findsOneWidget);
  });

  testWidgets('a posted blind sheet shows expected and difference',
      (tester) async {
    await _pump(
      tester,
      PhysicalCountSheetDialog(
        api: _PlanApi(),
        sheet: PhysicalCountSheet.fromJson(
            _sheetJson(blind: true, status: 'POSTED')),
        canCount: true,
      ),
    );

    expect(find.byKey(const ValueKey<String>('blind-count-badge')),
        findsNothing);
    expect(find.text('Expected'), findsOneWidget);
    expect(find.text('Difference'), findsOneWidget);
    expect(find.text('12.0000'), findsOneWidget);
  });

  testWidgets('a posting refusal shows the server message', (tester) async {
    final _PlanApi api = _PlanApi()..postRefused = true;
    await _pump(
      tester,
      PhysicalCountSheetDialog(
        api: api,
        sheet: PhysicalCountSheet.fromJson(_sheetJson(blind: true)),
        canCount: true,
      ),
    );

    await tester.tap(find.widgetWithText(FilledButton, 'Post count'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Post count').last);
    await tester.pumpAndSettle();

    expect(find.textContaining('somebody allowed more to post'),
        findsOneWidget);
  });

  testWidgets('a new count sends is_blind', (tester) async {
    final _PlanApi api = _PlanApi();
    await _pump(
      tester,
      PhysicalCountPage(
        api: api,
        preferences: DesktopPreferencesService(
          directory: Directory.systemTemp.createTempSync('count-planning'),
        ),
        permissions: _permissions(),
        hasActiveFirm: true,
      ),
    );

    await tester.tap(find.text('Open Count'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey<String>('open-count-blind')));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Open'));
    await tester.pumpAndSettle();

    expect(api.opened, isNotNull);
    expect(api.opened!['is_blind'], true);
  });
}
