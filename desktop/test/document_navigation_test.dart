// A report is not a module, and a menu entry that filters nothing is a lie.
//
// Delivery Notes declared seven sidebar entries and Sales Invoices seven more.
// Nine of the fourteen were named after a report -- Delivered by Route,
// Overdue Invoices, Invoice vs Delivery and the rest -- and every one of those
// reports exists on the backend and is wired into the desktop's report
// catalogue, reachable from **Reports**. None of them was reachable from the
// entry that named it. Three delivery-note entries opened the unfiltered list,
// two applied a status filter, and all seven invoice entries opened the same
// screen, because `SalesInvoiceManagementPage` never took a tab id at all.
//
// These pin what replaced them: one entry per module, the lifecycle statuses
// on a segmented view bar, and every retired id still resolving somewhere real
// with the view the user asked for.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/ui/delivery_notes/delivery_note_management_page.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_management_page.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

typedef Json = Map<String, dynamic>;

String _accessToken(List<String> permissions) {
  final String claims = base64Url
      .encode(utf8.encode(jsonEncode(<String, dynamic>{
        'roles': <String>['user'],
        'permissions': permissions,
      })))
      .replaceAll('=', '');
  return 'header.$claims.sig';
}

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken(const <String>[
    'SALES_VIEW',
    'SALES_CREATE',
    'SALES_UPDATE',
  ]));

/// Records what each list request asked the server for.
///
/// The defect was invisible from the screen -- every entry rendered a list, and
/// the list looked right -- so the assertion has to be about the query.
class _RecordingApi extends ApiClient {
  _RecordingApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<({String resource, Map<String, String> query})> requests =
      <({String resource, Map<String, String> query})>[];

  /// What the named list was last asked for.
  ///
  /// Filtered by resource on purpose: the delivery note workspace also pages
  /// the deliverable sales orders, and that call carries a status of its own.
  Map<String, String> lastQueryFor(String resource) => requests
      .lastWhere((request) => request.resource == resource)
      .query;

  @override
  Future<Json> documentSummary(String resource, {String path = 'summary'}) async =>
      <String, dynamic>{'data': <String, dynamic>{'total': 1}};

  @override
  Future<Json> documentPage(
    String resource, {
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> additionalQuery = const {},
  }) async {
    requests.add((resource: resource, query: additionalQuery));
    return <String, dynamic>{
      'data': <Json>[
        // One row, so the grid renders. `StandardEmptyState` animates, and
        // `pumpAndSettle` waits for animations to stop.
        <String, dynamic>{
          'id': 'doc-1',
          'firm_id': 'firm-1',
          'delivery_note_number': 'DN-0001',
          'invoice_number': 'INV-0001',
          'status': 'DRAFT',
          'grand_total': '590.00',
          'lines': <Json>[],
        },
      ],
      'pagination': <String, dynamic>{'total': 1},
    };
  }
}

Set<String> _tabIds(AppModule module) =>
    ModuleCatalog.byId(module).tabs.map((tab) => tab.id).toSet();

void main() {
  group('the menu offers one entry per workspace', () {
    test('delivery notes declare the list and nothing else', () {
      expect(_tabIds(AppModule.deliveryNotes), <String>{'delivery-notes'});
    });

    test('sales invoices declare the list and nothing else', () {
      expect(_tabIds(AppModule.salesInvoices), <String>{'sales-invoices'});
    });

    test('goods receipts lost the Settings entry that showed the list', () {
      // The page took a `tabId` and read it nowhere, so Settings and Receipts
      // rendered the same screen.
      expect(_tabIds(AppModule.goodsReceipts), <String>{'receipts'});
    });

    test('no group named Reports survives in either module', () {
      // Delivery Notes had one, holding five entries named after five real
      // report endpoints, none of which it opened.
      for (final AppModule module in <AppModule>[
        AppModule.deliveryNotes,
        AppModule.salesInvoices,
      ]) {
        final List<WorkspaceNavigationNode> nodes =
            ModuleCatalog.navigationChildren(module, _tabIds(module));
        expect(nodes.map((node) => node.label), isNot(contains('Reports')));
        expect(nodes.every((node) => node.isLeaf), isTrue);
      }
    });
  });

  group('a retired id still resolves somewhere real', () {
    test('every retired id is gone from the menu', () {
      // Both modules have one tab now, so the shell lands on it whatever a
      // stored workspace names -- no alias map required, unlike Purchases,
      // which has four tabs and still needs one. What a retired id must carry
      // is the view, asserted below.
      final Set<String> declared = <String>{
        ..._tabIds(AppModule.deliveryNotes),
        ..._tabIds(AppModule.salesInvoices),
      };
      for (final String retired in <String>[
        'pending-deliveries',
        'partial-deliveries',
        'delivered-by-route',
        'delivered-by-salesman',
        'delivered-by-warehouse',
        'delivery-history',
        'pending-invoices',
        'overdue-invoices',
        'invoice-register',
        'invoice-reconciliation',
        'customer-outstanding',
        'invoice-history',
      ]) {
        expect(declared, isNot(contains(retired)),
            reason: '$retired named a report it did not open');
      }
    });

    test('an id that stood for a status arrives on that status', () {
      // Landing on the list is not enough: somebody who left the app on
      // Pending Deliveries asked for the approved-but-undispatched ones.
      expect(DeliveryNoteView.fromTabId('pending-deliveries'),
          DeliveryNoteView.approved);
      expect(DeliveryNoteView.fromTabId('partial-deliveries'),
          DeliveryNoteView.dispatched);
      expect(DeliveryNoteView.fromTabId('delivery-history'),
          DeliveryNoteView.completed);
      // The three "delivered by" entries filtered nothing, so All is honest.
      expect(DeliveryNoteView.fromTabId('delivered-by-route'),
          DeliveryNoteView.all);
      expect(DeliveryNoteView.fromTabId(null), DeliveryNoteView.all);

      // `/reports/pending` is the invoices still in draft.
      expect(SalesInvoiceView.fromTabId('pending-invoices'),
          SalesInvoiceView.draft);
      // Overdue needs the due date *and* what is still unpaid, which the list
      // endpoint cannot express. It stays a report.
      expect(SalesInvoiceView.fromTabId('overdue-invoices'),
          SalesInvoiceView.all);

      expect(GoodsReceiptView.fromTabId('pending-receipts'),
          GoodsReceiptView.draft);
      expect(GoodsReceiptView.fromTabId('grn-history'),
          GoodsReceiptView.completed);
      expect(GoodsReceiptView.fromTabId('grn-settings'), GoodsReceiptView.all);
    });
  });

  group('the status bar asks the server for the status', () {
    Future<_RecordingApi> pumpDeliveryNotes(
      WidgetTester tester, {
      DeliveryNoteView initialView = DeliveryNoteView.all,
    }) async {
      tester.view.physicalSize = const Size(1600, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final Directory temp =
          Directory.systemTemp.createTempSync('document-navigation');
      addTearDown(() => temp.deleteSync(recursive: true));
      final _RecordingApi api = _RecordingApi();
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: DeliveryNoteManagementPage(
            api: api,
            preferences: DesktopPreferencesService(directory: temp),
            permissions: _permissions(),
            hasActiveFirm: true,
            initialView: initialView,
          ),
        ),
      ));
      await tester.pumpAndSettle();
      return api;
    }

    testWidgets('every delivery note status is offered', (tester) async {
      await pumpDeliveryNotes(tester);

      for (final String label in <String>[
        'All',
        'Draft',
        'Approved',
        'Dispatched',
        'Completed',
        'Cancelled',
      ]) {
        expect(
          find.widgetWithText(SegmentedButton<DeliveryNoteView>, label),
          findsOneWidget,
        );
      }
    });

    testWidgets('choosing one narrows the request', (tester) async {
      final _RecordingApi api = await pumpDeliveryNotes(tester);
      expect(api.lastQueryFor('delivery-notes'), isEmpty);

      // The summary cards carry the same words, so aim at the segment.
      await tester.tap(find.descendant(
        of: find.byType(SegmentedButton<DeliveryNoteView>),
        matching: find.text('Dispatched'),
      ));
      await tester.pumpAndSettle();

      expect(api.lastQueryFor('delivery-notes'),
          <String, String>{'status': 'DISPATCHED'});
    });

    testWidgets('a seeded view is what the first request carries',
        (tester) async {
      final _RecordingApi api = await pumpDeliveryNotes(
        tester,
        initialView: DeliveryNoteView.approved,
      );

      expect(api.lastQueryFor('delivery-notes'),
          <String, String>{'status': 'APPROVED'});
    });

    testWidgets('the invoice workspace offers Print and its settings',
        (tester) async {
      // The button and the dialog behind it are covered elsewhere; what this
      // asserts is that they are on the screen at all. A control that exists
      // in the source and never renders is the shape this module spent a day
      // removing.
      tester.view.physicalSize = const Size(1600, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final Directory temp =
          Directory.systemTemp.createTempSync('document-navigation-print');
      addTearDown(() => temp.deleteSync(recursive: true));
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: SalesInvoiceManagementPage(
            api: _RecordingApi(),
            preferences: DesktopPreferencesService(directory: temp),
            permissions: _permissions(),
            hasActiveFirm: true,
          ),
        ),
      ));
      await tester.pumpAndSettle();

      expect(find.widgetWithText(OutlinedButton, 'Print'), findsOneWidget);
      expect(find.byTooltip('Print settings'), findsOneWidget);
    });

    testWidgets('sales invoices narrow the same way', (tester) async {
      tester.view.physicalSize = const Size(1600, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final Directory temp =
          Directory.systemTemp.createTempSync('document-navigation-invoice');
      addTearDown(() => temp.deleteSync(recursive: true));
      final _RecordingApi api = _RecordingApi();
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: SalesInvoiceManagementPage(
            api: api,
            preferences: DesktopPreferencesService(directory: temp),
            permissions: _permissions(),
            hasActiveFirm: true,
          ),
        ),
      ));
      await tester.pumpAndSettle();
      expect(api.lastQueryFor('sales-invoices'), isEmpty);

      await tester.tap(find.descendant(
        of: find.byType(SegmentedButton<SalesInvoiceView>),
        matching: find.text('Approved'),
      ));
      await tester.pumpAndSettle();

      expect(api.lastQueryFor('sales-invoices'),
          <String, String>{'status': 'APPROVED'});
    });
  });
}
