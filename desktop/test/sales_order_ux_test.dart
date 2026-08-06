import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/ui/sales/sales_order_management_page.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('module catalog exposes sales order workspace', () {
    expect(ModuleCatalog.byId(AppModule.salesOrders).label, 'Sales Orders');
  });

  testWidgets('sales order workspace renders without an active firm', (
    tester,
  ) async {
    final Directory temp =
        Directory.systemTemp.createTempSync('sales-order-workspace-test');
    final DesktopPreferencesService preferences =
        DesktopPreferencesService(directory: temp);
    final PermissionService permissions = PermissionService();
    final ApiClient api = ApiClient(
      baseUrl: 'http://localhost:8000',
      accessToken: () => null,
      refreshAccessToken: () async => false,
      activeFirmId: () => null,
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SalesOrderManagementPage(
            api: api,
            preferences: preferences,
            permissions: permissions,
            hasActiveFirm: false,
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('Sales Orders'), findsWidgets);
    expect(find.text('Manage customer sales orders and inventory reservations.'), findsOneWidget);
  });
}
