// STK-7, the desktop half: adjustment reasons as a master.
//
//   * the Adjustment Reasons screen lists the firm's reasons and creates one
//     with the body the server declares;
//   * a system reason's code cannot be edited, and it cannot be deleted;
//   * the write-off dialog offers the firm's own reasons and sends the code
//     chosen;
//   * the adjustment dialog sends an optional `reason_code`.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/adjustment_reason.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/finance.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/inventory/adjustment_reasons_page.dart';
import 'package:agency_desktop/ui/inventory/inventory_management_page.dart';
import 'package:agency_desktop/ui/inventory/stock_action_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

const List<Json> _reasonRows = [
  {
    'id': 'r-damage',
    'code': 'DAMAGE',
    'name': 'Damage',
    'ledger_account_id': null,
    'ledger_account_name': null,
    'is_system': true,
    'is_active': true,
    'version': 1,
  },
  {
    'id': 'r-rework',
    'code': 'REWORK',
    'name': 'Sent for rework',
    'ledger_account_id': 'a-1',
    'ledger_account_name': 'Rework loss',
    'is_system': false,
    'is_active': true,
    'version': 1,
  },
];

final List<LedgerAccount> _accounts = [
  LedgerAccount.fromJson(const {
    'id': 'a-1',
    'code': '5100',
    'name': 'Rework loss',
    'is_active': true,
  }),
  LedgerAccount.fromJson(const {
    'id': 'a-2',
    'code': '5200',
    'name': 'Shrinkage',
    'is_active': true,
  }),
];

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? created;

  @override
  Future<List<AdjustmentReasonRecord>> adjustmentReasons({
    bool activeOnly = false,
  }) async {
    return [for (final Json row in _reasonRows) AdjustmentReasonRecord.fromJson(row)];
  }

  @override
  Future<PagedResult<LedgerAccount>> ledgerAccounts({
    String? accountGroupId,
    bool? isActive,
    bool openToHandJournals = false,
  }) async =>
      PagedResult<LedgerAccount>(items: _accounts, total: _accounts.length);

  @override
  Future<List<StorageNodeRecord>> storageNodes(
    String warehouseId, {
    bool includeDeleted = false,
  }) async =>
      const [];

  @override
  Future<Json> create(String resource, Json body) async {
    created = <String, dynamic>{'resource': resource, ...body};
    return <String, dynamic>{'data': body};
  }
}

void _viewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

Future<void> _pumpPage(WidgetTester tester, _Api api, List<String> codes) async {
  _viewport(tester);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: AdjustmentReasonsPage(api: api, permissions: _permissions(codes)),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  group('the Adjustment Reasons screen', () {
    testWidgets('lists the reasons, the system ones marked', (tester) async {
      await _pumpPage(tester, _Api(), ['INVENTORY_VIEW']);

      expect(find.text('DAMAGE'), findsOneWidget);
      expect(find.text('REWORK'), findsOneWidget);
      expect(find.text('Sent for rework'), findsOneWidget);
      expect(find.text('Rework loss'), findsOneWidget);
      expect(find.text('Default adjustment account'), findsOneWidget);
      expect(find.text('Yes'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a new reason posts the body the server declares',
        (tester) async {
      final _Api api = _Api();
      await _pumpPage(tester, api, ['INVENTORY_VIEW', 'INVENTORY_MANAGE_REASONS']);

      await tester.tap(find.widgetWithText(FilledButton, 'New').first);
      await tester.pumpAndSettle();
      await tester.enterText(
          find.widgetWithText(TextField, 'Code').first, 'rework2');
      await tester.enterText(
          find.widgetWithText(TextField, 'Name').first, 'Second rework');
      await tester.tap(find.widgetWithText(
          DropdownButtonFormField<String>, 'Ledger account'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('5200 - Shrinkage').last);
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Save & Close').last);
      await tester.pumpAndSettle();

      expect(api.created, <String, dynamic>{
        'resource': 'inventory/adjustment-reasons',
        'code': 'REWORK2',
        'name': 'Second rework',
        'ledger_account_id': 'a-2',
        'is_active': true,
      });
      expect(tester.takeException(), isNull);
    });

    testWidgets('a reason with no account sends null, which clears it',
        (tester) async {
      final _Api api = _Api();
      await _pumpPage(tester, api, ['INVENTORY_VIEW', 'INVENTORY_MANAGE_REASONS']);

      await tester.tap(find.widgetWithText(FilledButton, 'New').first);
      await tester.pumpAndSettle();
      await tester.enterText(find.widgetWithText(TextField, 'Code').first, 'x1');
      await tester.enterText(find.widgetWithText(TextField, 'Name').first, 'X');
      await tester.tap(find.widgetWithText(FilledButton, 'Save & Close').last);
      await tester.pumpAndSettle();

      expect(api.created!['ledger_account_id'], isNull);
      expect(api.created!.containsKey('ledger_account_id'), isTrue);
    });

    testWidgets('a system reason keeps its code and cannot be deleted',
        (tester) async {
      await _pumpPage(tester, _Api(), ['INVENTORY_VIEW', 'INVENTORY_MANAGE_REASONS']);

      // The first row is the system reason.
      await tester.tap(find.text('DAMAGE'));
      await tester.pumpAndSettle();
      final Finder delete = find.widgetWithText(OutlinedButton, 'Delete');
      if (delete.evaluate().isNotEmpty) {
        expect(tester.widget<OutlinedButton>(delete).onPressed, isNull);
      }

      await tester.tap(find.descendant(
        of: find.byType(DataTable),
        matching: find.byTooltip('Edit'),
      ).first);
      await tester.pumpAndSettle();
      final TextField code =
          tester.widget<TextField>(find.widgetWithText(TextField, 'Code').first);
      expect(code.readOnly, isTrue);
      expect(tester.takeException(), isNull);

      await tester.tap(find.byTooltip('Close').last);
      await tester.pumpAndSettle();

      // A custom reason is deletable from its row menu; the system one is not.
      await tester.tap(find.byIcon(Icons.more_vert).first);
      await tester.pumpAndSettle();
      expect(find.text('Delete'), findsNothing);
    });
  });

  group('the write-off dialog', () {
    Widget dialog({
      List<StockReasonOption>? reasons,
      required List<Json> saved,
    }) =>
        MaterialApp(
          home: Scaffold(
            body: StockActionDialog(
              action: StockAction.writeOff,
              productLabel: 'Detergent',
              warehouseLabel: 'North',
              sourceWarehouseId: 'w-1',
              available: 10,
              quarantined: 0,
              warehouses: const [],
              reasons: reasons ?? fallbackStockReasons,
              onSave: (Json draft) async => saved.add(draft),
            ),
          ),
        );

    testWidgets("offers the firm's own reason and sends its code",
        (tester) async {
      _viewport(tester);
      final List<Json> saved = [];
      await tester.pumpWidget(dialog(
        saved: saved,
        reasons: const [
          StockReasonOption(code: 'DAMAGE', name: 'Damage'),
          StockReasonOption(code: 'REWORK', name: 'Sent for rework'),
        ],
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Damage').last);
      await tester.pumpAndSettle();
      expect(find.text('Loss'), findsNothing);
      await tester.tap(find.text('Sent for rework').last);
      await tester.pumpAndSettle();
      await tester.enterText(find.widgetWithText(TextField, 'Quantity'), '3');
      await tester.tap(find.widgetWithText(FilledButton, 'Write off'));
      await tester.pumpAndSettle();

      expect(saved, hasLength(1));
      expect(saved.single['reason'], 'REWORK');
      expect(tester.takeException(), isNull);
    });

    testWidgets('falls back to the six when no list is given',
        (tester) async {
      _viewport(tester);
      await tester.pumpWidget(dialog(saved: []));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Damage').last);
      await tester.pumpAndSettle();
      for (final String name in [
        'Expiry',
        'Loss',
        'Internal use',
        'Given to staff',
        'Display / sample / demo',
      ]) {
        expect(find.text(name), findsOneWidget);
      }
    });
  });

  group('the adjustment dialog', () {
    Widget dialog(List<StockReasonOption> reasons, List<Json> saved) {
      final BranchRecord branch = BranchRecord.fromJson(
          const {'id': 'b-1', 'code': 'BR', 'name': 'Main'});
      final WarehouseRecord warehouse = WarehouseRecord.fromJson(
          const {'id': 'w-1', 'branch_id': 'b-1', 'code': 'WH', 'name': 'North'});
      final Product product = Product.fromJson(const {
        'id': 'p-1',
        'code': 'P1',
        'name': 'Detergent',
        'product_type': 'STOCK_ITEM',
        'status': 'ACTIVE',
        'unit': 'BOX',
      });
      return MaterialApp(
        home: Scaffold(
          body: StockAdjustmentDialog(
            api: _Api(),
            branches: [branch],
            warehouses: [warehouse],
            products: [product],
            reasons: reasons,
            onSave: (StockAdjustmentDraft draft) async =>
                saved.add(draft.toJson()),
          ),
        ),
      );
    }

    testWidgets('sends reason_code when one is chosen', (tester) async {
      _viewport(tester);
      final List<Json> saved = [];
      await tester.pumpWidget(dialog(
        const [StockReasonOption(code: 'REWORK', name: 'Sent for rework')],
        saved,
      ));
      await tester.pumpAndSettle();
      await tester.enterText(
          find.widgetWithText(TextField, 'Quantity (+ or - value)'), '-2');
      final Finder reason = find.widgetWithText(
          DropdownButtonFormField<String>, 'Reason (optional)');
      await tester.ensureVisible(reason);
      await tester.pumpAndSettle();
      await tester.tap(reason);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Sent for rework').last);
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Post adjustment'));
      await tester.pumpAndSettle();

      expect(saved.single['reason_code'], 'REWORK');
      expect(tester.takeException(), isNull);
    });

    testWidgets('sends no reason_code when left alone', (tester) async {
      _viewport(tester);
      final List<Json> saved = [];
      await tester.pumpWidget(dialog(
        const [StockReasonOption(code: 'REWORK', name: 'Sent for rework')],
        saved,
      ));
      await tester.pumpAndSettle();
      await tester.enterText(
          find.widgetWithText(TextField, 'Quantity (+ or - value)'), '4');
      await tester.tap(find.widgetWithText(FilledButton, 'Post adjustment'));
      await tester.pumpAndSettle();

      expect(saved.single.containsKey('reason_code'), isFalse);
    });
  });
}
