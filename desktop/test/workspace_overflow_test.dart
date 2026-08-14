import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:agency_desktop/ui/dashboard_page.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/finance/finance_workspace.dart';
import 'package:agency_desktop/ui/delivery_notes/delivery_note_management_page.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_management_page.dart';
import 'package:agency_desktop/ui/inventory/batch_management_page.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_management_page.dart';
import 'package:agency_desktop/ui/purchase_returns/purchase_return_management_page.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_management_page.dart';
import 'package:agency_desktop/ui/sales/sales_order_management_page.dart';
import 'package:agency_desktop/ui/vendors/vendor_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Every screen must stay overflow-free from 1366x768 up (UX_GUIDELINES.md).
///
/// This is the regression net for the UX work. Spacing, type scale, density
/// and chrome changes all move layouts, and the smallest supported window is
/// where that shows first -- so the matrix is deliberately widened here
/// *before* those changes land rather than after they break something.
///
/// Each screen is pumped at both supported sizes and in both brightnesses,
/// because the theme now supplies a designed pair rather than one palette, and
/// a layout that fits in light can still fail in dark where a container is a
/// different tone and a border appears.
const List<Size> _sizes = [
  Size(1366, 768),
  Size(1600, 900),
];

typedef _PageBuilder = Widget Function(_Deps deps);

/// The collaborators every page needs, none of which touch the network while
/// `hasActiveFirm` is false.
class _Deps {
  _Deps(this.api, this.preferences, this.permissions);

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
}

/// The screens an operator is in every day, plus the two that already had
/// coverage. Named so a failure says which screen broke.
final Map<String, _PageBuilder> _screens = {
  'sales orders': (d) => SalesOrderManagementPage(
        api: d.api,
        preferences: d.preferences,
        permissions: d.permissions,
        hasActiveFirm: false,
      ),
  'sales invoices': (d) => SalesInvoiceManagementPage(
        api: d.api,
        preferences: d.preferences,
        permissions: d.permissions,
        hasActiveFirm: false,
      ),
  'delivery notes': (d) => DeliveryNoteManagementPage(
        api: d.api,
        preferences: d.preferences,
        permissions: d.permissions,
        hasActiveFirm: false,
        tabId: 'delivery-notes',
      ),
  'goods receipts': (d) => GoodsReceiptManagementPage(
        api: d.api,
        preferences: d.preferences,
        permissions: d.permissions,
        hasActiveFirm: false,
        tabId: 'receipts',
      ),
  'purchase invoices': (d) => PurchaseInvoiceManagementPage(
        api: d.api,
        preferences: d.preferences,
        permissions: d.permissions,
        hasActiveFirm: false,
      ),
  'purchase returns': (d) => PurchaseReturnManagementPage(
        api: d.api,
        preferences: d.preferences,
        permissions: d.permissions,
        hasActiveFirm: false,
      ),
  // The accounting screens, added with them. A trial balance is seven numeric
  // columns wide, which is exactly the shape that overflows first.
  'finance': (d) => FinanceWorkspace(
        api: d.api,
        preferences: d.preferences,
        permissions: d.permissions,
        hasActiveFirm: false,
        tabId: 'chart-of-accounts',
      ),
  'journal entries': (d) => FinanceWorkspace(
        api: d.api,
        preferences: d.preferences,
        permissions: d.permissions,
        hasActiveFirm: false,
        tabId: 'journal-entries',
      ),
  'trial balance': (d) => FinanceWorkspace(
        api: d.api,
        preferences: d.preferences,
        permissions: d.permissions,
        hasActiveFirm: false,
        tabId: 'trial-balance',
      ),
  // Two pickers side by side above a six-column table, which is the other
  // shape that runs out of width first.
  'profit and loss': (d) => FinanceWorkspace(
        api: d.api,
        preferences: d.preferences,
        permissions: d.permissions,
        hasActiveFirm: false,
        tabId: 'profit-loss',
      ),
  'ledgers': (d) => FinanceWorkspace(
        api: d.api,
        preferences: d.preferences,
        permissions: d.permissions,
        hasActiveFirm: false,
        tabId: 'ledgers',
      ),
  'customers': (d) => CustomerManagementPage(
        api: d.api,
        permissions: d.permissions,
        hasActiveFirm: false,
      ),
  'vendors': (d) => VendorManagementPage(
        api: d.api,
        permissions: d.permissions,
        hasActiveFirm: false,
      ),
  'dashboard': (d) => DashboardPage(api: d.api, permissions: d.permissions),
  'batches': (d) => BatchManagementPage(
        api: d.api,
        preferences: d.preferences,
        permissions: d.permissions,
        hasActiveFirm: false,
        section: BatchSerialSection.batches,
      ),
};

void _fixSize(WidgetTester tester, Size size) {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

_Deps _dependencies() {
  final Directory temp = Directory.systemTemp.createTempSync('overflow-test');
  addTearDown(() => temp.deleteSync(recursive: true));
  return _Deps(
    ApiClient(
      baseUrl: 'http://localhost:8000',
      accessToken: () => null,
      refreshAccessToken: () async => false,
      activeFirmId: () => null,
    ),
    DesktopPreferencesService(directory: temp),
    PermissionService(),
  );
}

void main() {
  for (final Size size in _sizes) {
    final String dimensions = '${size.width.toInt()}x${size.height.toInt()}';

    for (final Brightness brightness in Brightness.values) {
      final String mode = brightness == Brightness.dark ? 'dark' : 'light';

      for (final MapEntry<String, _PageBuilder> screen in _screens.entries) {
        testWidgets('${screen.key} fits at $dimensions in $mode', (tester) async {
          _fixSize(tester, size);
          final _Deps deps = _dependencies();
          final ThemeManager themes = ThemeManager(deps.preferences);

          await tester.pumpWidget(
            MaterialApp(
              theme: themes.lightTheme,
              darkTheme: themes.darkTheme,
              themeMode: brightness == Brightness.dark
                  ? ThemeMode.dark
                  : ThemeMode.light,
              home: Scaffold(body: screen.value(deps)),
            ),
          );
          await tester.pumpAndSettle();

          // A RenderFlex overflow surfaces here, which is what makes this a
          // guardrail rather than a smoke test.
          expect(tester.takeException(), isNull);
        });
      }
    }

    testWidgets('the pager fits beneath a full list at $dimensions',
        (tester) async {
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
  }
}

void _ignore(int _) {}
