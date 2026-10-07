// A typed dialog asks before it is thrown away, and a new coupon names no
// offer for the user.
//
// D-UI-51, 53, 55, 57 and 58 were one defect found five times on screen:
// Cancel on a dialog with something typed in it closed at once. D-UI-54 was a
// new coupon opening with the first offer already chosen, so a code alone was
// saved for life under an offer nobody picked. D-UI-50 was the two bill lists
// reading empty for Accounts, whom the server lets read them.

import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/pricing.dart';
import 'package:agency_desktop/ui/customers/loyalty_adjust_dialog.dart';
import 'package:agency_desktop/ui/pricing/coupon_dialog.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_management_page.dart';
import 'package:agency_desktop/ui/workspace/discard_prompt.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/access_token.dart';

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<String> written = <String>[];
  final List<String> read = <String>[];

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
    if (method != 'GET') {
      written.add('$method $path');
      return <String, dynamic>{'data': <String, dynamic>{}};
    }
    read.add(path);
    // The cards are a report, gated on codes Accounts may not hold.
    if (path.contains('/summary')) {
      throw const ApiException('Permission denied.', statusCode: 403);
    }
    return <String, dynamic>{
      'success': true,
      'data': <Json>[
        <String, dynamic>{
          'id': 'doc-1',
          'invoice_number': 'PINV-0001',
          'vendor_name': 'Sri Ganesh Traders',
          'status': 'APPROVED',
          'grand_total': '590.00',
          'lines': <Json>[],
        },
      ],
      'pagination': <String, dynamic>{'total_records': 1},
    };
  }
}

/// Open [dialog] from a button, as a screen does, so closing it is a real pop.
Future<void> _open(WidgetTester tester, Widget dialog) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (BuildContext context) => TextButton(
          onPressed: () =>
              showDialog<Object?>(context: context, builder: (_) => dialog),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

PromotionRecord _offer() => PromotionRecord.fromJson(const <String, dynamic>{
      'id': 'p-1',
      'code': 'WELCOME',
      'name': 'Welcome',
      'status': 'ACTIVE',
      'priority': 100,
      'allow_stacking': true,
      'requires_coupon': true,
      'version': 1,
      'version_number': 1,
      'conditions': <Json>[],
      'actions': <Json>[],
    });

void main() {
  testWidgets('nothing typed: Cancel closes without a question',
      (tester) async {
    await _open(tester, LoyaltyAdjustDialog(api: _Api()));
    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();

    expect(find.text('Close without saving?'), findsNothing);
    expect(find.text('Adjust points'), findsNothing);
  });

  testWidgets('something typed: Cancel asks, and Keep editing keeps it',
      (tester) async {
    await _open(tester, LoyaltyAdjustDialog(api: _Api()));
    await tester.enterText(
        find.byKey(const ValueKey('loyalty-adjust-reason')), 'Goodwill');
    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();

    expect(find.text('Close without saving?'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('discard-keep-editing')));
    await tester.pumpAndSettle();
    expect(find.text('Adjust points'), findsOneWidget);
    expect(find.text('Goodwill'), findsOneWidget);

    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('discard-and-close')));
    await tester.pumpAndSettle();
    expect(find.text('Adjust points'), findsNothing);
  });

  testWidgets('a save in flight is not interrupted by a close', (tester) async {
    bool touched = true;
    await _open(
      tester,
      AskBeforeClosing(
        touched: () => touched,
        what: 'record has not been saved',
        busy: true,
        child: Builder(
          builder: (BuildContext context) => AlertDialog(
            title: const Text('Busy dialog'),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).maybePop(),
                child: const Text('Cancel'),
              ),
            ],
          ),
        ),
      ),
    );
    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();
    touched = false;

    expect(find.text('Close without saving?'), findsNothing);
    expect(find.text('Busy dialog'), findsOneWidget);
  });

  testWidgets('a new coupon opens with no offer chosen, and a code alone '
      'is not saved', (tester) async {
    final _Api api = _Api();
    await _open(
      tester,
      CouponDialog(api: api, promotions: <PromotionRecord>[_offer()]),
    );
    expect(find.textContaining('WELCOME'), findsNothing);

    await tester.enterText(
        find.widgetWithText(TextFormField, 'Code'), 'SAVE10');
    await tester.tap(find.widgetWithText(FilledButton, 'Create'));
    await tester.pumpAndSettle();

    expect(find.text('Choose the offer'), findsOneWidget);
    expect(api.written, isEmpty);
  });

  testWidgets('an untouched coupon closes without a question', (tester) async {
    await _open(
      tester,
      CouponDialog(api: _Api(), promotions: <PromotionRecord>[_offer()]),
    );
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();

    expect(find.text('Close without saving?'), findsNothing);
    expect(find.text('New coupon'), findsNothing);
  });

  testWidgets('a typed coupon asks before Cancel throws it away',
      (tester) async {
    await _open(
      tester,
      CouponDialog(api: _Api(), promotions: <PromotionRecord>[_offer()]),
    );
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Code'), 'SAVE10');
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();

    expect(find.text('Close without saving?'), findsOneWidget);
  });

  testWidgets('whoever pays a bill sees the bills, cards refused or not',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final Directory temp = Directory.systemTemp.createTempSync('pi-accounts');
    addTearDown(() => temp.deleteSync(recursive: true));
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: PurchaseInvoiceManagementPage(
          api: api,
          preferences: DesktopPreferencesService(directory: temp),
          // Accounts: no purchase code at all, and the server reads the bill
          // to them on `PAYMENT_VIEW` (D-UI-46).
          permissions: PermissionService()
            ..applyAccessToken(accessTokenFor(const <String>['PAYMENT_VIEW'])),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(api.read.any((String path) => path.endsWith('/purchase-invoices')),
        isTrue);
    expect(find.text('PINV-0001'), findsWidgets);
  });
}
