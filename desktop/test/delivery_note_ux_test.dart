import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/ui/delivery_notes/delivery_note_management_page.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('module catalog exposes delivery note workspace', () {
    expect(ModuleCatalog.byId(AppModule.deliveryNotes).label, 'Delivery Notes');
  });

  testWidgets('delivery note workspace renders without an active firm', (
    tester,
  ) async {
    // The supported minimum. At the 800x600 default the six summary cards and
    // the workspace beneath them do not fit, and an overflow fails the test.
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    final Directory temp =
        Directory.systemTemp.createTempSync('delivery-note-workspace-test');
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
          body: DeliveryNoteManagementPage(
            api: api,
            preferences: preferences,
            permissions: permissions,
            hasActiveFirm: false,
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('Delivery Notes'), findsWidgets);
    // Plainer than "reservation release and inventory deduction", and it
    // names the step that actually moves stock.
    expect(
      find.textContaining('Dispatching a note is what moves the stock'),
      findsOneWidget,
    );
  });
}

