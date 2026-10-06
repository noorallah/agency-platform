// GST-7, desktop half: quarterly (QRMP) filers.
//
// Pins: the settings dialog sends the three filing fields; the PMT-06 deposits
// page lists deposits, prefills a new one from the server's suggestion and
// posts exactly the keys the server declares; a monthly filer is told the page
// is not for them; the GST payment preview shows what the deposits paid.
// The calendar labels are pinned in phase2_home_page_test.dart.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/expense.dart';
import 'package:agency_desktop/ui/sales/gst_deposits_page.dart';
import 'package:agency_desktop/ui/sales/gst_payment_page.dart';
import 'package:agency_desktop/ui/tax/gst_documents_settings_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

PermissionService _permissions(List<String> codes) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode({'permissions': codes})));
  return PermissionService()..applyAccessToken('h.$payload.s');
}

class _Api extends ApiClient {
  _Api({this.frequency = 'QUARTERLY'})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String frequency;
  Json? savedSettings;
  Json? postedDeposit;
  Json? reversed;
  final List<String> suggestions = [];

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
    if (path.endsWith('/gst-compliance-settings')) {
      if (method == 'PUT') {
        savedSettings = Map<String, dynamic>.from(body ?? const {});
        return {
          'data': {...?body, 'is_configured': true},
        };
      }
      return {
        'data': {
          'einvoice_applicable_from': null,
          'thirty_day_rule_from': null,
          'dispatch_without_invoice': 'WARN',
          'route_sale_needs_invoice': false,
          'is_configured': true,
          'filing_frequency': frequency,
          'quarterly_from': null,
          'qrmp_payment_method': 'FIXED_SUM',
        },
      };
    }
    if (path == '/api/v1/einvoice/settings') {
      return {
        'data': {
          'provider': 'SANDBOX',
          'available': ['SANDBOX'],
        },
      };
    }
    if (path == '/api/v1/gst-returns/filing-plan') {
      return {
        'data': {
          'filing_frequency': frequency,
          'quarterly_from': null,
          'qrmp_payment_method': 'FIXED_SUM',
          'cash_ledger': {
            'igst': '1000.00',
            'cgst': '500.00',
            'sgst': '500.00',
            'cess': '0.00',
          },
        },
      };
    }
    if (method == 'GET' && path == '/api/v1/gst-returns/cash-deposits') {
      return {
        'data': [
          {
            'id': 'dep-1',
            'return_period': '2026-07',
            'deposit_date': '2026-08-24',
            'method': 'FIXED_SUM',
            'challan_cpin': 'CPIN9',
            'total': '2000.00',
            'status': 'POSTED',
          },
        ],
      };
    }
    if (path == '/api/v1/gst-returns/cash-deposits/suggestion') {
      suggestions.add('${query?['return_period']} ${query?['method']}');
      return {
        'data': {
          'return_period': query?['return_period'],
          'method': query?['method'],
          'due_date': '2026-11-25',
          'heads': {
            'igst': '700.00',
            'cgst': '300.00',
            'sgst': '300.00',
            'cess': '0.00',
          },
          'total': '1300.00',
          'basis': '35% of the cash paid for the last quarter.',
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/gst-returns/cash-deposits') {
      postedDeposit = Map<String, dynamic>.from(body ?? const {});
      return {
        'data': {'id': 'dep-2', ...?body, 'status': 'POSTED'},
      };
    }
    if (path.endsWith('/reverse')) {
      reversed = Map<String, dynamic>.from(body ?? const {});
      return {
        'data': {'id': 'dep-1', 'status': 'REVERSED'},
      };
    }
    if (path == '/api/v1/gst-returns/payments/preview') {
      return {
        'data': {
          'return_period': '2026-09',
          'period_from': '2026-07-01',
          'due_date': '2026-10-24',
          'previous_settled': true,
          'days_late': 0,
          'suggested_interest': '0.00',
          'cash_total': '3000.00',
          'deposits_total': '2000.00',
          'bank_total': '1000.00',
          'heads': [
            for (final String head in ['IGST', 'CGST', 'SGST', 'CESS'])
              {
                'head': head,
                'liability': '1000.00',
                'credit_brought_forward': '0.00',
                'credit_available': '0.00',
                'paid_by_credit': '0.00',
                'cash': '1000.00',
                'paid_from_deposits': '500.00',
                'credit_used': '0.00',
                'carried_forward': '0.00',
              },
          ],
          'utilisation': <dynamic>[],
        },
      };
    }
    if (path == '/api/v1/gst-returns/payments') return {'data': <dynamic>[]};
    return {'data': <dynamic>[]};
  }

  @override
  Future<ExpenseAccountChoices> expenseAccountChoices() async =>
      ExpenseAccountChoices.fromJson({
        'expense_accounts': [
          {'id': 'a-6500', 'code': '6500', 'name': 'Office'},
        ],
        'paid_from_accounts': [
          {'id': 'a-1010', 'code': '1010', 'name': 'Bank'},
        ],
      });
}

Future<void> _pumpDeposits(
  WidgetTester tester,
  _Api api, {
  Size size = const Size(1366, 768),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: GstDepositsPage(
        api: api,
        permissions: _permissions(['SALES_VIEW', 'JOURNAL_POST']),
        hasActiveFirm: true,
        today: DateTime(2026, 10, 3),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('settings: the three filing fields are sent', (tester) async {
    final _Api api = _Api();
    tester.view.physicalSize = const Size(800, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: GstDocumentsSettingsDialog(
          api: api,
          permissions: _permissions(['TAX_VIEW', 'TAX_MANAGE_SETTINGS']),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.byKey(const ValueKey('gst-qrmp-method')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('gst-qrmp-method')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Self-assessment').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('gst-settings-save')));
    await tester.pumpAndSettle();

    final Json sent = api.savedSettings!;
    expect(sent['filing_frequency'], 'QUARTERLY');
    expect(sent.containsKey('quarterly_from'), isTrue);
    expect(sent['quarterly_from'], isNull);
    expect(sent['qrmp_payment_method'], 'SELF_ASSESSMENT');
    expect(tester.takeException(), isNull);
  });

  testWidgets('settings: a monthly firm hides the quarterly choices',
      (tester) async {
    final _Api api = _Api(frequency: 'MONTHLY');
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: GstDocumentsSettingsDialog(
          api: api,
          permissions: _permissions(['TAX_VIEW', 'TAX_MANAGE_SETTINGS']),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('gst-filing-frequency')), findsOneWidget);
    expect(find.byKey(const ValueKey('gst-quarterly-from')), findsNothing);
    expect(find.byKey(const ValueKey('gst-qrmp-method')), findsNothing);
  });

  testWidgets('deposits: lists rows and the cash ledger', (tester) async {
    await _pumpDeposits(tester, _Api());
    expect(find.byKey(const ValueKey('gst-deposit-2026-07')), findsOneWidget);
    expect(find.textContaining('CPIN CPIN9'), findsOneWidget);
    expect(
      tester
          .widget<Text>(find.byKey(const ValueKey('gst-deposit-ledger')))
          .data,
      contains('IGST 1000.00'),
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('deposits: fits 800x600', (tester) async {
    await _pumpDeposits(tester, _Api(), size: const Size(800, 600));
    expect(tester.takeException(), isNull);
  });

  testWidgets('deposits: a monthly filer is told it is not for them',
      (tester) async {
    await _pumpDeposits(tester, _Api(frequency: 'MONTHLY'));
    expect(find.text('No deposits to make'), findsOneWidget);
    expect(find.byKey(const ValueKey('gst-deposit-record')), findsNothing);
  });

  testWidgets('deposits: record prefills from the suggestion and posts',
      (tester) async {
    final _Api api = _Api();
    await _pumpDeposits(tester, api);

    await tester.tap(find.byKey(const ValueKey('gst-deposit-record')));
    await tester.pumpAndSettle();
    expect(api.suggestions.single, '2026-10 FIXED_SUM');
    expect(find.textContaining('35% of the cash paid'), findsOneWidget);
    expect(find.textContaining('Due 2026-11-25'), findsOneWidget);
    expect(
      tester
          .widget<TextField>(find.byKey(const ValueKey('gst-deposit-igst')))
          .controller!
          .text,
      '700.00',
    );

    await tester.enterText(
        find.byKey(const ValueKey('gst-deposit-cpin')), 'CPIN77');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('gst-deposit-save')));
    await tester.pumpAndSettle();

    expect(api.postedDeposit, {
      'return_period': '2026-10',
      'deposit_date': '2026-10-03',
      'money_account_id': 'a-1010',
      'method': 'FIXED_SUM',
      'amount_igst': '700.00',
      'amount_cgst': '300.00',
      'amount_sgst': '300.00',
      'amount_cess': '0.00',
      'challan_cpin': 'CPIN77',
    });
    expect(find.text('PMT-06 deposit recorded.'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('deposits: reverse asks for a reason', (tester) async {
    final _Api api = _Api();
    await _pumpDeposits(tester, api);
    await tester
        .tap(find.byKey(const ValueKey('gst-deposit-reverse-2026-07')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Wrong account');
    await tester.pump();
    await tester.tap(find.text('Reverse').last);
    await tester.pumpAndSettle();
    expect(api.reversed, {'reason': 'Wrong account'});
  });

  testWidgets('payment preview: shows the quarter and the deposits',
      (tester) async {
    final _Api api = _Api();
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: GstPaymentPage(
          api: api,
          permissions: _permissions(['SALES_VIEW', 'JOURNAL_POST']),
          hasActiveFirm: true,
          today: DateTime(2026, 10, 3),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Settles the quarter Jul-Sep 2026.'), findsOneWidget);
    expect(
      find.text('Paid from PMT-06 deposits: 2000.00. From bank: 1000.00.'),
      findsOneWidget,
    );
    expect(find.text('Paid from deposits'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
