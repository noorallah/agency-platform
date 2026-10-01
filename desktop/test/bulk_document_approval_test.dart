// Bulk approve, cancel and post on the document lists beyond the two order
// lists (backlog 56 A, the rest): sales and purchase invoices, delivery notes,
// credit notes, sales and purchase returns, and journal entries. Tick two
// rows, act on them together, and read what the server did with each.
//
// `bulk_order_approval_test.dart` covers the order lists and the result
// dialog's retry in depth; here every screen proves the same four things --
// one ticked row offers no bulk action, two do, the approve (or post) sends
// both ids to the right path, and the actions follow the single actions'
// permissions.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/delivery_notes/delivery_note_management_page.dart';
import 'package:agency_desktop/ui/finance/journal_entries_page.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_management_page.dart';
import 'package:agency_desktop/ui/purchase_returns/purchase_return_management_page.dart';
import 'package:agency_desktop/ui/sales/credit_note_page.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_management_page.dart';
import 'package:agency_desktop/ui/sales_returns/sales_return_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

/// One row carrying every number key the screens read, so one builder serves
/// all seven.
Json _row(int n) => <String, dynamic>{
      'id': 'doc-$n',
      'invoice_number': 'INV-000$n',
      'delivery_note_number': 'DN-000$n',
      'return_number': 'RET-000$n',
      'credit_note_number': 'CN-000$n',
      'reference_number': 'JV-000$n',
      'invoice_date': '2026-08-23',
      'status': 'DRAFT',
      'grand_total': '1000.00',
      'total_amount': '1000.00',
      'total_debit': '1000.00',
      'customer_name': 'Customer $n',
      'vendor_name': 'Vendor $n',
      'version': n + 3,
    };

/// Serves the same rows for whatever list the screen asks for and records
/// each bulk call. The second row of every approve is refused.
class _BulkApi extends ApiClient {
  _BulkApi({required this.listPath})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String listPath;
  final List<Json> rows = <Json>[_row(1), _row(2), _row(3)];
  final List<(String, Json)> bulkCalls = <(String, Json)>[];

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
    if (method == 'POST' && path.contains('/bulk-')) {
      bulkCalls.add((path, body!));
      final List<Json> items = (body['items'] as List).cast<Json>();
      final bool cancel = path.endsWith('bulk-cancel');
      return <String, dynamic>{
        'data': <String, dynamic>{
          'done': cancel ? items.length : 1,
          'refused': cancel ? 0 : items.length - 1,
          'results': [
            for (int i = 0; i < items.length; i++)
              <String, dynamic>{
                'id': items[i]['id'],
                'number': 'NUM-${items[i]['id']}',
                'outcome': cancel || i == 0 ? 'DONE' : 'REFUSED',
                'message': cancel || i == 0 ? null : 'Already approved.',
              },
          ],
        },
      };
    }
    if (method == 'GET' && path.endsWith('/summary')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'total': rows.length, 'draft': rows.length},
      };
    }
    if (method == 'GET' && path == listPath) {
      return <String, dynamic>{
        'data': rows,
        'pagination': <String, dynamic>{'total_records': rows.length},
      };
    }
    return <String, dynamic>{'data': <dynamic>[]};
  }
}

/// One screen under test.
class _Screen {
  const _Screen({
    required this.name,
    required this.listPath,
    required this.bulkPath,
    required this.codes,
    required this.build,
    this.approveLabel = 'Approve selected',
    this.verb = 'Approved',
    this.cancelPath,
    this.cancelLabel,
    this.cancelPermission,
  });

  final String name;
  final String listPath;

  /// Where the approve (or post) goes.
  final String bulkPath;
  final List<String> codes;
  final String approveLabel;
  final String verb;
  final String? cancelPath;

  /// The reason prompt's confirm button.
  final String? cancelLabel;
  final String? cancelPermission;
  final Widget Function(_BulkApi api, PermissionService permissions, Directory dir)
      build;
}

Widget _prefsPage(
  Directory dir,
  Widget Function(DesktopPreferencesService preferences) page,
) =>
    page(DesktopPreferencesService(directory: dir));

final List<_Screen> _screens = <_Screen>[
  _Screen(
    name: 'sales invoices',
    listPath: '/api/v1/sales-invoices',
    bulkPath: '/api/v1/sales-invoices/bulk-approve',
    cancelPath: '/api/v1/sales-invoices/bulk-cancel',
    cancelLabel: 'Cancel invoices',
    cancelPermission: 'SALES_CANCEL',
    codes: const ['SALES_VIEW', 'SALES_APPROVE', 'SALES_CANCEL'],
    build: (api, permissions, dir) => _prefsPage(
      dir,
      (preferences) => SalesInvoiceManagementPage(
        api: api,
        preferences: preferences,
        permissions: permissions,
        hasActiveFirm: true,
      ),
    ),
  ),
  _Screen(
    name: 'purchase invoices',
    listPath: '/api/v1/purchase-invoices',
    bulkPath: '/api/v1/purchase-invoices/bulk-approve',
    cancelPath: '/api/v1/purchase-invoices/bulk-cancel',
    cancelLabel: 'Cancel invoices',
    cancelPermission: 'PURCHASE_CANCEL',
    codes: const ['PURCHASE_VIEW', 'PURCHASE_APPROVE', 'PURCHASE_CANCEL'],
    build: (api, permissions, dir) => _prefsPage(
      dir,
      (preferences) => PurchaseInvoiceManagementPage(
        api: api,
        preferences: preferences,
        permissions: permissions,
        hasActiveFirm: true,
      ),
    ),
  ),
  _Screen(
    name: 'delivery notes',
    listPath: '/api/v1/delivery-notes',
    bulkPath: '/api/v1/delivery-notes/bulk-approve',
    cancelPath: '/api/v1/delivery-notes/bulk-cancel',
    cancelLabel: 'Cancel notes',
    cancelPermission: 'SALES_CANCEL',
    codes: const ['SALES_VIEW', 'SALES_APPROVE', 'SALES_CANCEL'],
    build: (api, permissions, dir) => _prefsPage(
      dir,
      (preferences) => DeliveryNoteManagementPage(
        api: api,
        preferences: preferences,
        permissions: permissions,
        hasActiveFirm: true,
      ),
    ),
  ),
  _Screen(
    name: 'credit notes',
    listPath: '/api/v1/credit-notes',
    bulkPath: '/api/v1/credit-notes/bulk-approve',
    codes: const ['CREDIT_NOTE_VIEW', 'CREDIT_NOTE_APPROVE'],
    build: (api, permissions, dir) => _prefsPage(
      dir,
      (preferences) => CreditNotePage(
        api: api,
        preferences: preferences,
        permissions: permissions,
        hasActiveFirm: true,
      ),
    ),
  ),
  _Screen(
    name: 'sales returns',
    listPath: '/api/v1/sales-returns',
    bulkPath: '/api/v1/sales-returns/bulk-approve',
    cancelPath: '/api/v1/sales-returns/bulk-cancel',
    cancelLabel: 'Cancel returns',
    cancelPermission: 'SALES_CANCEL',
    codes: const ['SALES_VIEW', 'SALES_APPROVE', 'SALES_CANCEL'],
    build: (api, permissions, dir) => _prefsPage(
      dir,
      (preferences) => SalesReturnManagementPage(
        api: api,
        preferences: preferences,
        permissions: permissions,
        hasActiveFirm: true,
      ),
    ),
  ),
  _Screen(
    name: 'purchase returns',
    listPath: '/api/v1/purchase-returns',
    bulkPath: '/api/v1/purchase-returns/bulk-approve',
    cancelPath: '/api/v1/purchase-returns/bulk-cancel',
    cancelLabel: 'Cancel returns',
    cancelPermission: 'PURCHASE_CANCEL',
    codes: const ['PURCHASE_VIEW', 'PURCHASE_APPROVE', 'PURCHASE_CANCEL'],
    build: (api, permissions, dir) => _prefsPage(
      dir,
      (preferences) => PurchaseReturnManagementPage(
        api: api,
        preferences: preferences,
        permissions: permissions,
        hasActiveFirm: true,
      ),
    ),
  ),
  _Screen(
    name: 'journal entries',
    listPath: '/api/v1/finance/journal-entries',
    bulkPath: '/api/v1/finance/journal-entries/bulk-post',
    approveLabel: 'Post selected',
    verb: 'Posted',
    codes: const ['JOURNAL_VIEW', 'JOURNAL_POST'],
    build: (api, permissions, dir) => _prefsPage(
      dir,
      (preferences) => JournalEntriesPage(
        api: api,
        preferences: preferences,
        permissions: permissions,
        hasActiveFirm: true,
      ),
    ),
  ),
];

Future<_BulkApi> _pump(
  WidgetTester tester,
  _Screen screen,
  List<String> codes,
) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory temp = Directory.systemTemp.createTempSync('bulk-doc-test');
  addTearDown(() => temp.deleteSync(recursive: true));
  final _BulkApi api = _BulkApi(listPath: screen.listPath);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: screen.build(api, _permissions(codes), temp),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return api;
}

/// The selection bar's own text -- the status bar also counts what is ticked.
Finder _barSays(String text) => find.descendant(
      of: find.byKey(const ValueKey('selection-bar')),
      matching: find.textContaining(text, findRichText: true),
    );

/// Tick the first [count] data rows (the header's own box is index 0).
Future<void> _tick(WidgetTester tester, int count) async {
  for (int i = 1; i <= count; i++) {
    await tester.tap(find.byType(Checkbox).at(i));
    await tester.pumpAndSettle();
  }
}

void main() {
  for (final _Screen screen in _screens) {
    testWidgets('${screen.name}: approve selected sends both ids',
        (tester) async {
      final _BulkApi api = await _pump(tester, screen, screen.codes);

      // One row ticked is still a single-row selection: no bulk action yet.
      await _tick(tester, 1);
      expect(find.text(screen.approveLabel), findsNothing);

      await tester.tap(find.byType(Checkbox).at(2));
      await tester.pumpAndSettle();
      expect(_barSays('2 selected'), findsOneWidget);

      await tester.tap(find.text(screen.approveLabel));
      await tester.pumpAndSettle();

      expect(api.bulkCalls, hasLength(1));
      expect(api.bulkCalls.single.$1, screen.bulkPath);
      final List<Json> items =
          (api.bulkCalls.single.$2['items'] as List).cast<Json>();
      expect(items.map((item) => item['id']).toSet(), {'doc-1', 'doc-2'});
      expect(api.bulkCalls.single.$2.containsKey('reason'), isFalse);

      expect(find.text('${screen.verb} 1 of 2'), findsOneWidget);
      expect(find.textContaining('Already approved.'), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('bulk-close')));
      await tester.pumpAndSettle();
      expect(_barSays('2 selected'), findsNothing);
    });

    if (screen.cancelPath != null) {
      testWidgets('${screen.name}: cancel selected sends the typed reason',
          (tester) async {
        final _BulkApi api = await _pump(tester, screen, screen.codes);
        await _tick(tester, 2);

        await tester.tap(find.text('Cancel selected'));
        await tester.pumpAndSettle();
        await tester.enterText(find.byType(TextField).last, 'Entered twice.');
        await tester
            .tap(find.widgetWithText(FilledButton, screen.cancelLabel!));
        await tester.pumpAndSettle();

        expect(api.bulkCalls.single.$1, screen.cancelPath);
        expect(api.bulkCalls.single.$2['reason'], 'Entered twice.');
        expect(find.text('Cancelled 2 of 2'), findsOneWidget);
      });

      testWidgets('${screen.name}: cancel needs its own permission',
          (tester) async {
        await _pump(
          tester,
          screen,
          [
            for (final String code in screen.codes)
              if (code != screen.cancelPermission) code,
          ],
        );
        await _tick(tester, 2);

        expect(find.text(screen.approveLabel), findsOneWidget);
        expect(find.text('Cancel selected'), findsNothing);
      });
    } else {
      testWidgets('${screen.name}: no cancel is offered for a batch',
          (tester) async {
        await _pump(tester, screen, screen.codes);
        await _tick(tester, 2);

        expect(find.text(screen.approveLabel), findsOneWidget);
        expect(find.text('Cancel selected'), findsNothing);
      });
    }

    testWidgets('${screen.name}: approve needs its permission',
        (tester) async {
      // Everything but the approving (or posting) code.
      final List<String> codes = [
        for (final String code in screen.codes)
          if (!code.endsWith('_APPROVE') && !code.endsWith('_POST')) code,
      ];
      final _BulkApi api = await _pump(tester, screen, codes);
      await _tick(tester, 2);

      // A command the person may not run is not offered at all.
      expect(find.text(screen.approveLabel), findsNothing);
      expect(api.bulkCalls, isEmpty);
    });
  }
}
