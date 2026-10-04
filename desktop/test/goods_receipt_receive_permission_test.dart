// D-ROLE-3: raising, editing and completing a goods receipt take
// `PURCHASE_RECEIVE`, which Purchasing, the Purchase Manager and Warehouse
// hold. The screen used to offer Complete to everybody and fail after the
// press for anyone without `PURCHASE_APPROVE`; and Warehouse, holding no
// `PURCHASE_VIEW`, could not open the list at all. The button now follows the
// code the server enforces.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:agency_desktop/ui/workspace/module_visibility.dart';
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
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<String> completed = <String>[];

  @override
  Future<GoodsReceiptRecord> completeGoodsReceipt(String id) async {
    completed.add(id);
    return GoodsReceiptRecord.fromJson({
      'id': id,
      'grn_number': 'GRN-0001',
      'status': 'COMPLETED',
    });
  }

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
    if (path.endsWith('/summary')) {
      return {'data': <String, dynamic>{}};
    }
    if (path.endsWith('/goods-receipts')) {
      return {
        'data': [
          {
            'id': 'gr-1',
            'grn_number': 'GRN-0001',
            'receipt_date': '2026-09-01',
            'status': 'DRAFT',
            'grand_total': '60000.00',
            'lines': <Json>[],
          },
        ],
        'pagination': {'total_records': 1},
      };
    }
    return {
      'data': const <Json>[],
      'pagination': {'total_records': 0},
    };
  }
}

Future<_Api> _open(WidgetTester tester, List<String> codes) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory temp = Directory.systemTemp.createTempSync('receive');
  addTearDown(() => temp.deleteSync(recursive: true));
  final _Api api = _Api();
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: GoodsReceiptManagementPage(
          api: api,
          preferences: DesktopPreferencesService(directory: temp),
          permissions: _permissions(codes),
          hasActiveFirm: true,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.text('GRN-0001').first);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
  return api;
}

/// Press Complete where it is drawn. A command nobody may run is not drawn
/// at all, which is "not offered" as much as a disabled one is; either way
/// nothing reaches the server.
Future<void> _pressComplete(WidgetTester tester) async {
  final Finder complete = find.text('Complete');
  if (complete.evaluate().isEmpty) return;
  await tester.tap(complete.first, warnIfMissed: false);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('Warehouse opens the receipts and completes one', (
    tester,
  ) async {
    final _Api api = await _open(tester, const ['PURCHASE_RECEIVE']);
    expect(find.text('GRN-0001'), findsWidgets);
    await _pressComplete(tester);
    expect(api.completed, ['gr-1']);
  });

  testWidgets('approving orders no longer completes a receipt', (
    tester,
  ) async {
    final _Api api =
        await _open(tester, const ['PURCHASE_VIEW', 'PURCHASE_APPROVE']);
    await _pressComplete(tester);
    expect(api.completed, isEmpty);
  });

  testWidgets('a reader is not offered Complete', (tester) async {
    final _Api api = await _open(tester, const ['PURCHASE_VIEW']);
    await _pressComplete(tester);
    expect(api.completed, isEmpty);
  });

  test('the receipts tab opens to whoever receives', () {
    final ModuleDefinition module = ModuleCatalog.byId(AppModule.goodsReceipts);
    final List<ModuleTabDefinition> tabs = ModuleVisibility.tabsFor(
      module,
      _permissions(const ['PURCHASE_RECEIVE']),
      hasActiveFirm: true,
    );
    expect(tabs.map((tab) => tab.id), contains('receipts'));
  });
}
