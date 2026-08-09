import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/ui/inventory/batch_management_page.dart';
import 'package:agency_desktop/ui/purchase_returns/purchase_return_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Every screen must stay overflow-free from 1366x768 up (UX_GUIDELINES.md).
///
/// This pass added two blocks that consume vertical space in workspaces which
/// were already full: a pager under six lists, and a four-card summary row
/// above the batch grid. The smallest supported window is where that shows.
const List<Size> _sizes = [
  Size(1366, 768),
  Size(1600, 900),
];

void _fixSize(WidgetTester tester, Size size) {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

void main() {
  for (final Size size in _sizes) {
    final String label = '${size.width.toInt()}x${size.height.toInt()}';

    testWidgets('the pager fits beneath a full list at $label', (tester) async {
      _fixSize(tester, size);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Column(
              children: [
                Expanded(
                  child: ListView.separated(
                    itemCount: 20,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (context, index) => ListTile(
                      title: Text('Document $index'),
                      subtitle: const Text('PO-0001 • 2026-08-10 • APPROVED'),
                      trailing: const Text('1,234.00'),
                    ),
                  ),
                ),
                const WorkspacePager(
                  page: 3,
                  pageSize: 20,
                  total: 137,
                  onPageChanged: _ignore,
                ),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('41–60 of 137'), findsOneWidget);
    });

    testWidgets('the batch workspace stays bounded at $label', (tester) async {
      _fixSize(tester, size);
      final Directory temp =
          Directory.systemTemp.createTempSync('batch-overflow-test');
      addTearDown(() => temp.deleteSync(recursive: true));

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: BatchManagementPage(
              api: ApiClient(
                baseUrl: 'http://localhost:8000',
                accessToken: () => null,
                refreshAccessToken: () async => false,
                activeFirmId: () => null,
              ),
              preferences: DesktopPreferencesService(directory: temp),
              permissions: PermissionService(),
              hasActiveFirm: false,
              section: BatchSerialSection.batches,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
    });

    testWidgets('a document workspace stays bounded at $label', (tester) async {
      _fixSize(tester, size);
      final Directory temp =
          Directory.systemTemp.createTempSync('document-overflow-test');
      addTearDown(() => temp.deleteSync(recursive: true));

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PurchaseReturnManagementPage(
              api: ApiClient(
                baseUrl: 'http://localhost:8000',
                accessToken: () => null,
                refreshAccessToken: () async => false,
                activeFirmId: () => null,
              ),
              preferences: DesktopPreferencesService(directory: temp),
              permissions: PermissionService(),
              hasActiveFirm: false,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
    });
  }
}

void _ignore(int _) {}
