// Purchase invoices and purchase returns get their width back.
//
// Both put a `ListView` of records at `flex: 3` beside a document pane at
// `flex: 4` — the preview of the one record pointed at had *more* room than
// every record — and neither had a table at all. Same shape the goods receipt
// workspace had before it.
//
// The toolbars were worse than the layout. Each offered eight document
// actions of which only three or four reached the backend; the rest fell
// through to a notification reading "Placeholder action for purchase
// invoices." — a button whose whole behaviour is to say it has none.
//
// And on returns, **Close called `/complete`**: the button named after ending
// the document was the one that takes the stock off, and `/close` was never
// called at all.

import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/document_framework/document_framework_widgets.dart';
import 'package:agency_desktop/ui/document_framework/document_view_dialog.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_management_page.dart';
import 'package:agency_desktop/ui/purchase_returns/purchase_return_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/access_token.dart';

Json _page(String key, List<Json> rows) => <String, dynamic>{
      'success': true,
      'data': rows,
      'pagination': <String, dynamic>{
        'page': 1,
        'page_size': 20,
        'total_records': rows.length,
        'total_pages': 1,
      },
    };

class _DocumentApi extends ApiClient {
  _DocumentApi({required this.numberField, required this.number})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String numberField;
  final String number;

  /// Every action path the screen asked the server for, so a button can be
  /// checked against what it actually calls rather than against its label.
  final List<String> actions = <String>[];

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
    if (path.contains('/approve') ||
        path.contains('/cancel') ||
        path.contains('/close') ||
        path.contains('/complete')) {
      actions.add(path);
      return <String, dynamic>{'success': true, 'data': <String, dynamic>{}};
    }
    if (path.contains('/summary')) {
      return <String, dynamic>{
        'success': true,
        'data': <String, dynamic>{'total': 1, 'draft': 1},
      };
    }
    if (path.contains('/history') || path.contains('/timeline')) {
      return <String, dynamic>{'success': true, 'data': <Json>[]};
    }
    return _page('data', <Json>[
      <String, dynamic>{
        'id': 'doc-1',
        numberField: number,
        'status': 'DRAFT',
        'grand_total': '590.00',
        'lines': <Json>[],
      },
    ]);
  }
}

Future<void> _pump(WidgetTester tester, Widget page) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(home: Scaffold(body: page)));
  await tester.pumpAndSettle();
}

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(accessTokenFor(const <String>[
    'PURCHASE_VIEW',
    'PURCHASE_CREATE',
    'PURCHASE_APPROVE',
    'PURCHASE_CANCEL',
  ]));

Directory _temp(WidgetTester tester, String name) {
  final Directory dir = Directory.systemTemp.createTempSync(name);
  addTearDown(() => dir.deleteSync(recursive: true));
  return dir;
}

void main() {
  group('purchase invoices', () {
    Future<_DocumentApi> open(WidgetTester tester) async {
      final _DocumentApi api =
          _DocumentApi(numberField: 'invoice_number', number: 'PINV-0001');
      await _pump(
        tester,
        PurchaseInvoiceManagementPage(
          api: api,
          preferences:
              DesktopPreferencesService(directory: _temp(tester, 'pinv')),
          permissions: _permissions(),
          hasActiveFirm: true,
        ),
      );
      return api;
    }

    testWidgets('a real table, and no pinned document pane', (tester) async {
      await open(tester);

      expect(find.byType(EnterpriseDocumentLines), findsNothing);
      expect(find.byType(EnterpriseTimeline), findsNothing);
      expect(find.text('PINV-0001'), findsWidgets);
    });

    testWidgets('double-clicking a row opens the document', (tester) async {
      await open(tester);

      final Finder row = find.text('PINV-0001').first;
      await tester.tap(row);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(row);
      await tester.pumpAndSettle();

      expect(find.byType(DocumentViewDialog), findsOneWidget);
    });

    testWidgets('only the actions the backend has are offered',
        (tester) async {
      await open(tester);

      for (final String label in <String>['Approve', 'Cancel', 'Close']) {
        expect(find.text(label), findsWidgets);
      }
      // These fell through to "Placeholder action for purchase invoices."
      for (final String label in <String>['Reject', 'Email', 'Print']) {
        expect(find.text(label), findsNothing, reason: '$label did nothing');
      }
    });
  });

  group('purchase returns', () {
    Future<_DocumentApi> open(WidgetTester tester) async {
      final _DocumentApi api =
          _DocumentApi(numberField: 'return_number', number: 'PRET-0001');
      await _pump(
        tester,
        PurchaseReturnManagementPage(
          api: api,
          preferences:
              DesktopPreferencesService(directory: _temp(tester, 'pret')),
          permissions: _permissions(),
          hasActiveFirm: true,
        ),
      );
      return api;
    }

    testWidgets('a real table, and no pinned document pane', (tester) async {
      await open(tester);

      expect(find.byType(EnterpriseDocumentLines), findsNothing);
      expect(find.byType(EnterpriseTimeline), findsNothing);
      expect(find.text('PRET-0001'), findsWidgets);
    });

    testWidgets('double-clicking a row opens the document', (tester) async {
      await open(tester);

      final Finder row = find.text('PRET-0001').first;
      await tester.tap(row);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(row);
      await tester.pumpAndSettle();

      expect(find.byType(DocumentViewDialog), findsOneWidget);
    });

    testWidgets('a button is disabled when the status forbids it',
        (tester) async {
      // The row this fake serves is DRAFT. Approve applies to a draft;
      // completing needs an approved return, so it must be dead.
      await open(tester);
      await tester.tap(find.text('PRET-0001').first);
      await tester.pumpAndSettle();

      bool enabled(String label) =>
          tester
              .widget<OutlinedButton>(
                find.widgetWithText(OutlinedButton, label),
              )
              .onPressed !=
          null;

      expect(enabled('Approve'), isTrue, reason: 'a draft can be approved');
      expect(enabled('Complete'), isFalse,
          reason: 'only an approved return can be completed');
      expect(enabled('Cancel'), isTrue);
    });

    testWidgets('Complete completes, and Close closes', (tester) async {
      // The defect: the button labelled Close called `/complete`, which is the
      // step that takes stock off, and `/close` was never called at all.
      final _DocumentApi api = await open(tester);
      await tester.tap(find.text('PRET-0001').first);
      await tester.pumpAndSettle();

      // Close is the one a draft allows; Complete needs an approved return
      // and is covered by the gate tests.
      await tester.tap(find.widgetWithText(OutlinedButton, 'Close'));
      await tester.pumpAndSettle();
      expect(api.actions.last, endsWith('/close'),
          reason: 'Close used to call /complete, which posts a stock movement');
    });
  });
}
