// Backlog 54, desktop half: a trade licence check runs before a sales
// document is approved, mirroring the credit-exposure warning
// (sales_credit_notice_test.dart) for the same reason -- ask before the
// call, because approval is the decision being checked.
//
// These pin: a warning lists what was found and the approval still runs; a
// block with no override permission offers only Close, and never approves;
// a block with the override permission sends the reason it was given as
// `licence_override_reason`; and the product and category forms send
// `required_licence_type_id`.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/trade_licence.dart';
import 'package:agency_desktop/ui/desktop_shell.dart' show productCategoryDefinition;
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:agency_desktop/ui/sales/sales_order_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '');
  return 'header.$payload.signature';
}

PermissionService _withPermissions(List<String> permissions) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': permissions,
      }));

Json _checkResponse({required bool wouldBlock}) => <String, dynamic>{
      'direction': 'SALE',
      'enforcement': wouldBlock ? 'BLOCK' : 'WARN',
      'on': '2026-09-30',
      'findings': <Json>[
        {
          'party': 'CUSTOMER',
          'party_name': 'Vijaya Super Stores',
          'licence_type_id': 'type-1',
          'licence_type_name': 'Drug Licence',
          'shortfall': 'MISSING',
          'licence_number': null,
          'valid_from': null,
          'valid_to': null,
          'line_numbers': <int>[1],
          'product_names': <String>['Paracetamol'],
          'message': 'Vijaya Super Stores has no Drug Licence on record.',
        },
      ],
      'would_block': wouldBlock,
      'message': 'Vijaya Super Stores has no Drug Licence on record.',
    };

/// One draft sales order, a licence check answer, and a recording of the
/// calls made and the query the approve call carried.
class _LicenceApi extends ApiClient {
  _LicenceApi({required this.check})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json check;
  final List<String> calls = <String>[];
  Map<String, String>? lastApproveQuery;

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
    calls.add('$method $path');
    if (path.contains('/credit-status')) {
      // OK carries no notice, so the credit warning this page also runs
      // stays out of the way of what this file is testing.
      return <String, dynamic>{
        'success': true,
        'data': <String, dynamic>{
          'customer_id': 'customer-1',
          'customer_name': 'Vijaya Super Stores',
          'enforcement': 'WARN',
          'status': 'OK',
          'limit': '0',
          'exposure': '0',
          'available': '0',
          'used_percent': '0',
          'warn_at_percent': '80',
          'block_at_percent': '100',
          'would_block': false,
          'message': '',
        },
      };
    }
    if (path.contains('/trade-licences/check/')) {
      return <String, dynamic>{'success': true, 'data': check};
    }
    if (path.endsWith('/summary')) {
      return <String, dynamic>{
        'success': true,
        'data': <String, dynamic>{'total': 1, 'draft': 1},
      };
    }
    if (path.contains('/history') || path.contains('/timeline')) {
      return <String, dynamic>{'success': true, 'data': const <dynamic>[]};
    }
    if (path.endsWith('/approve')) {
      lastApproveQuery = query;
    }
    if (method == 'POST') {
      return <String, dynamic>{
        'success': true,
        'data': const <String, dynamic>{},
      };
    }
    return <String, dynamic>{
      'success': true,
      'data': <Map<String, dynamic>>[
        <String, dynamic>{
          'id': 'order-1',
          'order_number': 'SO-0001',
          'order_date': '2026-08-10',
          'status': 'DRAFT',
          'customer_id': 'customer-1',
          'grand_total': '19000.00',
          'lines': const <dynamic>[],
        },
      ],
      'pagination': <String, dynamic>{'total_records': 1},
    };
  }
}

Future<void> _pumpAndApprove(
  WidgetTester tester,
  _LicenceApi api, {
  required PermissionService permissions,
}) async {
  final Directory temp =
      Directory.systemTemp.createTempSync('licence-check-test');
  addTearDown(() => temp.deleteSync(recursive: true));
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: SalesOrderManagementPage(
          api: api,
          preferences: DesktopPreferencesService(directory: temp),
          permissions: permissions,
          hasActiveFirm: true,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.widgetWithText(OutlinedButton, 'Approve').first);
  await tester.pumpAndSettle();
}

/// A firm with one product category and one active licence type, recording
/// what a save writes.
class _CategoryApi extends ApiClient {
  _CategoryApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<(String, Json)> writes = <(String, Json)>[];

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
      writes.add((path, Map<String, dynamic>.from(body ?? const {})));
      return {
        'data': {'id': 'cat-new', ...?body},
      };
    }
    if (path == '/api/v1/trade-licences/types') {
      return {
        'data': [
          {
            'id': 'type-1',
            'code': 'DRUG',
            'name': 'Drug Licence',
            'is_active': true,
          },
        ],
      };
    }
    return {'data': const <dynamic>[]};
  }
}

void main() {
  testWidgets('a warning lists what was found, and approving anyway runs it',
      (tester) async {
    final _LicenceApi api = _LicenceApi(check: _checkResponse(wouldBlock: false));

    await _pumpAndApprove(
      tester,
      api,
      permissions: _withPermissions(
        ['SALES_VIEW', 'SALES_APPROVE', 'TRADE_LICENCE_VIEW'],
      ),
    );

    expect(
      find.textContaining('has no Drug Licence on record'),
      findsOneWidget,
    );
    expect(find.text('Approve anyway'), findsOneWidget);
    expect(find.text('Override…'), findsNothing);

    await tester.tap(find.text('Approve anyway'));
    await tester.pumpAndSettle();

    expect(api.calls.any((call) => call.contains('/trade-licences/check/')), isTrue);
    expect(api.calls.any((call) => call.endsWith('/approve')), isTrue);
  });

  testWidgets(
      'a block with no override permission offers only Close, and never approves',
      (tester) async {
    final _LicenceApi api = _LicenceApi(check: _checkResponse(wouldBlock: true));

    await _pumpAndApprove(
      tester,
      api,
      permissions: _withPermissions(
        ['SALES_VIEW', 'SALES_APPROVE', 'TRADE_LICENCE_VIEW'],
      ),
    );

    final Finder dialog = find.byType(AlertDialog);
    expect(find.descendant(of: dialog, matching: find.text('Override…')),
        findsNothing);
    expect(
        find.descendant(of: dialog, matching: find.text('Close')),
        findsOneWidget);

    await tester.tap(find.descendant(of: dialog, matching: find.text('Close')));
    await tester.pumpAndSettle();

    expect(api.calls.any((call) => call.endsWith('/approve')), isFalse);
  });

  testWidgets('a block with the override permission sends the reason given',
      (tester) async {
    final _LicenceApi api = _LicenceApi(check: _checkResponse(wouldBlock: true));

    await _pumpAndApprove(
      tester,
      api,
      permissions: _withPermissions([
        'SALES_VIEW',
        'SALES_APPROVE',
        'TRADE_LICENCE_VIEW',
        'TRADE_LICENCE_OVERRIDE',
      ]),
    );

    expect(find.text('Override…'), findsOneWidget);
    await tester.tap(find.text('Override…'));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextField, 'Reason'),
      'The customer collects it in person tomorrow.',
    );
    await tester.pump();
    await tester.tap(find.text('Override').last);
    await tester.pumpAndSettle();

    expect(
      api.lastApproveQuery?['licence_override_reason'],
      'The customer collects it in person tomorrow.',
    );
  });

  testWidgets('the product form sends the licence type chosen',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    Json? sent;
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: ProductWorkspaceDialog(
          mode: ProductDialogMode.create,
          product: null,
          categories: const [],
          uoms: const [],
          licenceTypes: const [
            TradeLicenceTypeRecord(
              id: 'type-1',
              version: 1,
              code: 'DRUG',
              name: 'Drug Licence',
              formNumbers: '',
              expires: true,
              isActive: true,
              description: '',
            ),
          ],
          definitions: const [],
          metadata: const ProductMetadataRecord(
            profileCode: '',
            features: [],
            categories: [],
            taxProfiles: [],
            requiredAttributeDefinitionIds: [],
            optionalAttributeDefinitionIds: [],
          ),
          initialTab: 'general',
          onMetadataForCategory: (_) async => const ProductMetadataRecord(
            profileCode: '',
            features: [],
            categories: [],
            taxProfiles: [],
            requiredAttributeDefinitionIds: [],
            optionalAttributeDefinitionIds: [],
          ),
          onSave: (payload) async {
            sent = payload;
            return Product.fromJson(const {
              'id': 'product-1',
              'code': 'PARA',
              'name': 'Paracetamol',
              'product_type': 'STOCK_ITEM',
              'status': 'ACTIVE',
            });
          },
          onTabChanged: (_) {},
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, 'Product code'),
      'PARA',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Product name *'),
      'Paracetamol',
    );
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('product-licence-type')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Drug Licence').last);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('product-save')));
    await tester.pumpAndSettle();

    expect(sent?['required_licence_type_id'], 'type-1');
  });

  testWidgets('the category form sends the licence type chosen',
      (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1600, 900);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    final _CategoryApi api = _CategoryApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: ResourceManagementPage<ProductCategoryRecord>(
          api: api,
          definition: productCategoryDefinition(
            api,
            _withPermissions(['PRODUCT_VIEW', 'PRODUCT_UPDATE']),
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(FilledButton, 'New').hitTestable());
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Category code'), 'MEDICINE');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Name'), 'Medicine');
    await tester.pump();
    await tester.tap(find.text('DRUG · Drug Licence'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save & Close'));
    await tester.pumpAndSettle();

    expect(api.writes, hasLength(1));
    final (String path, Json body) = api.writes.single;
    expect(path, '/api/v1/products/categories');
    expect(body['required_licence_type_id'], 'type-1');
  });
}
