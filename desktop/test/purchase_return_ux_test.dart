import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/ui/purchase_returns/purchase_return_management_page.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('module catalog exposes purchase return workspace', () {
    expect(ModuleCatalog.byId(AppModule.purchaseReturns).label, 'Purchase Returns');
  });

  testWidgets('purchase return workspace renders without an active firm', (
    tester,
  ) async {
    // The supported minimum. At the 800x600 default the six summary cards and
    // the workspace beneath them do not fit, and an overflow fails the test.
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final Directory temp =
        Directory.systemTemp.createTempSync('purchase-return-workspace-test');
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
          body: PurchaseReturnManagementPage(
            api: api,
            preferences: preferences,
            permissions: permissions,
            hasActiveFirm: false,
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('Purchase Returns'), findsWidgets);
    // The old copy was the invoice description with one word changed, and
    // returns are not about GRN matching or accounting events. It now names
    // the step that moves stock.
    expect(
      find.textContaining('Completing a return is what takes the stock off'),
      findsOneWidget,
    );
  });
}
