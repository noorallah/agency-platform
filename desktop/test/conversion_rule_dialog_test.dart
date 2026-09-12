// A conversion rule names its units and product by code, and the server
// accepts what the form sends.
//
// Raised ahead of manual test 6.8: the Create Conversion Rule dialog asked
// for "From UOM ID" and "To UOM ID" -- ids nobody can type -- and sent a
// `version` key the server forbids, so every rule created from the desktop
// was refused with "The request validation failed." The grid showed the
// same raw ids, and its Version column showed the concurrency counter
// rather than the rule's revision.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/uom_packaging.dart';
import 'package:agency_desktop/ui/uom/uom_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['UOM_VIEW', 'UOM_MANAGE', 'CONVERSION_RULE_MANAGE'],
  }));

const String _pack = '81000000-0000-0000-0000-000000000003';
const String _kg = '81000000-0000-0000-0000-000000000010';

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? created;

  @override
  Future<List<UomRecord>> uoms({bool includeInactive = false}) async =>
      <UomRecord>[
        UomRecord.fromJson(<String, dynamic>{
          'id': _pack,
          'code': 'PACK',
          'name': 'Pack',
          'status': 'ACTIVE',
        }),
        UomRecord.fromJson(<String, dynamic>{
          'id': _kg,
          'code': 'KG',
          'name': 'Kilogram',
          'status': 'ACTIVE',
        }),
      ];

  @override
  Future<PagedResult<Product>> products({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    ProductQuery filters = const ProductQuery(),
  }) async =>
      PagedResult<Product>(
        items: <Product>[
          Product.fromJson(<String, dynamic>{
            'id': 'prod-deter',
            'firm_id': 'firm-1',
            'code': 'DETER1K',
            'name': 'Detergent Powder 1kg',
            'status': 'ACTIVE',
          }),
        ],
        total: 1,
      );

  @override
  Future<PagedResult<ConversionRuleRecord>> conversionRules({
    int page = 1,
    int pageSize = 20,
    String productId = '',
  }) async =>
      PagedResult<ConversionRuleRecord>(
        items: <ConversionRuleRecord>[
          ConversionRuleRecord.fromJson(<String, dynamic>{
            'id': 'rule-1',
            'product_id': 'prod-deter',
            'from_uom_id': _pack,
            'to_uom_id': _kg,
            'conversion_factor': '1.0000000000',
            'version_number': 1,
            'version': 7,
            'effective_from': '2024-04-01',
            'status': 'ACTIVE',
          }),
        ],
        total: 1,
      );

  @override
  Future<ConversionRuleRecord> createConversionRule(Json data) async {
    created = data;
    return ConversionRuleRecord.fromJson(<String, dynamic>{
      'id': 'rule-2',
      ...data,
    });
  }
}

Future<void> _pump(WidgetTester tester, _Api api) async {
  await tester.binding.setSurfaceSize(const Size(1600, 900));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: UomManagementPage(
        api: api,
        permissions: _permissions(),
        hasActiveFirm: true,
        section: UomManagementSection.conversionRules,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the grid shows codes, the product, and the revision',
      (tester) async {
    await _pump(tester, _Api());
    expect(find.text('PACK'), findsOneWidget);
    expect(find.text('KG'), findsOneWidget);
    expect(find.text('DETER1K'), findsOneWidget);
    expect(find.text(_pack), findsNothing, reason: 'no raw ids on the grid');
    // Revision 1, not the concurrency counter 7.
    expect(find.text('1'), findsOneWidget);
    expect(find.text('7'), findsNothing);
  });

  testWidgets('a firm-wide rule is created from codes, with no version key',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await tester.tap(find.widgetWithText(FilledButton, 'Add'));
    await tester.pumpAndSettle();
    expect(find.text('Create Conversion Rule'), findsOneWidget);

    // Product stays "Firm-wide". Pick the two units by code.
    await tester.tap(find.byType(DropdownButtonFormField<String>).at(0));
    await tester.pumpAndSettle();
    await tester.tap(find.text('PACK — Pack').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DropdownButtonFormField<String>).at(1));
    await tester.pumpAndSettle();
    await tester.tap(find.text('KG — Kilogram').last);
    await tester.pumpAndSettle();

    await tester.enterText(find.widgetWithText(TextFormField, 'Factor'), '2');
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Effective from (YYYY-MM-DD)'),
      '2024-04-01',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.created, isNotNull);
    expect(api.created, <String, dynamic>{
      'from_uom_id': _pack,
      'to_uom_id': _kg,
      'conversion_factor': '2',
      'effective_from': '2024-04-01',
      'status': 'ACTIVE',
    });
    expect(api.created!.containsKey('version'), isFalse,
        reason: 'the server forbids unknown keys, and version is not one of its');
    expect(api.created!.containsKey('product_id'), isFalse,
        reason: 'firm-wide means no product, not a null product');
    expect(find.text('Conversion rule saved.'), findsOneWidget);
  });

  testWidgets('the same unit on both sides is refused before sending',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    await tester.tap(find.widgetWithText(FilledButton, 'Add'));
    await tester.pumpAndSettle();

    await tester.tap(find.byType(DropdownButtonFormField<String>).at(0));
    await tester.pumpAndSettle();
    await tester.tap(find.text('PACK — Pack').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DropdownButtonFormField<String>).at(1));
    await tester.pumpAndSettle();
    await tester.tap(find.text('PACK — Pack').last);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(find.text('The two units must differ'), findsOneWidget);
    expect(api.created, isNull);
  });
}
