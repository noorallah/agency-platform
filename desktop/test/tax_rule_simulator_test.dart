// The rule simulator asks the engine the question a document would ask.
//
// Raised from manual testing (plan item 6.7): every simulation answered zero
// tax and "No rule matched". The screen never sent a tax profile -- which
// every seeded rule is keyed on, and without which the engine applies
// nothing -- and its transaction types read SALE, PURCHASE, TRANSFER, which
// no rule has ever named. The document modules pass SALES_INVOICE,
// PURCHASE_INVOICE and the rest; the interstate rule names SALES_INTERSTATE.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/tax_framework.dart';
import 'package:agency_desktop/ui/tax/tax_rule_simulator_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['TAX_VIEW', 'TAX_RULE_VIEW', 'TAX_SIMULATE'],
  }));

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? sent;

  @override
  Future<PagedResult<TaxProfileRecord>> taxProfiles({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    String? taxSystemId,
    bool includeDeleted = false,
  }) async =>
      PagedResult<TaxProfileRecord>(
        items: <TaxProfileRecord>[
          TaxProfileRecord.fromJson(<String, dynamic>{
            'id': 'profile-18-local',
            'tax_system_id': 'gst',
            'code': 'GST_18_LOCAL',
            'name': 'GST 18% local',
            'label': 'GST 18%',
            'status': 'ACTIVE',
            'components': <Json>[],
          }),
        ],
        total: 1,
      );

  @override
  Future<Json> taxSimulation(Json body) async {
    sent = body;
    return <String, dynamic>{
      'data': <String, dynamic>{
        'transaction_type': body['transaction_type'],
        'matched_rule_id': 'rule-interstate-18',
        'applied_components': <Json>[
          <String, dynamic>{
            'code': 'IGST',
            'label': 'IGST',
            'percentage': '18.0000',
            'amount': '180.0000',
          },
        ],
        'total_tax_amount': '180.0000',
        'decisions': <Json>[
          <String, dynamic>{
            'rule_id': 'rule-interstate-18',
            'code': 'INTERSTATE_GST_18',
            'name': 'Interstate sale switches 18 percent GST to IGST',
            'matched': true,
            'priority': 12,
          },
        ],
      },
    };
  }
}

Future<void> _pump(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: TaxRuleSimulatorPage(api: api, permissions: _permissions()),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  test('the types offered are the ones the engine is called with', () {
    expect(
      TaxRuleSimulatorPage.transactionTypes,
      containsAll(<String>[
        'SALES_INVOICE',
        'SALES_INTERSTATE',
        'PURCHASE_INVOICE',
        'EXPORT',
      ]),
    );
    expect(TaxRuleSimulatorPage.transactionTypes, isNot(contains('SALE')));
    expect(TaxRuleSimulatorPage.transactionTypes, isNot(contains('TRANSFER')));
  });

  testWidgets('a simulation carries the chosen profile and type',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    // No profile chosen: the form refuses to run rather than asking the
    // engine a question it will answer with zero.
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Invoice Value (₹)'), '1000');
    await tester.tap(find.textContaining('Run Simulation'));
    await tester.pumpAndSettle();
    expect(api.sent, isNull);
    expect(find.text('Choose the tax profile to simulate'), findsOneWidget);

    await tester.tap(find.byType(DropdownButtonFormField<String>).at(1));
    await tester.pumpAndSettle();
    await tester.tap(find.text('GST_18_LOCAL — GST 18% local').last);
    await tester.pumpAndSettle();

    await tester.tap(find.byType(DropdownButtonFormField<String>).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('SALES_INTERSTATE').last);
    await tester.pumpAndSettle();

    await tester.tap(find.textContaining('Run Simulation'));
    await tester.pumpAndSettle();

    expect(api.sent, isNotNull);
    expect(api.sent!['tax_profile_id'], 'profile-18-local');
    expect(api.sent!['transaction_type'], 'SALES_INTERSTATE');
    expect(find.textContaining('INTERSTATE_GST_18'), findsWidgets);
  });
}
