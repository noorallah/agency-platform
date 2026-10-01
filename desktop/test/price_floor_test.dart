// Backlog 64 row 2, desktop half: warn or block a sale below its floor.
//
// These pin: the settings dialog saves the policy it was shown and stays open
// with the server's message on a refusal; approving under WARN lists the
// findings and still approves; a block with the override permission asks a
// reason and sends it as `price_override_reason`; a block without it never
// approves; and the product form sends `minimum_selling_price`.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:agency_desktop/ui/sales/price_floor_settings_dialog.dart';
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

Json _check({required bool wouldBlock}) => <String, dynamic>{
      'enforcement': wouldBlock ? 'BLOCK' : 'WARN',
      'would_block': wouldBlock,
      'message': 'Line 1 is below its minimum price.',
      'findings': <Json>[
        {
          'line_number': 1,
          'product_id': 'product-1',
          'product_code': 'PROD-001',
          'product_name': 'Pain Relief',
          'net_rate': '90.00',
          'floor': 'minimum',
          'minimum_price': '95.00',
          'message': 'Pain Relief is priced at 90.00, below its minimum 95.00.',
        },
      ],
    };

class _FloorApi extends ApiClient {
  _FloorApi({this.check, this.refuseSave = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json? check;
  final bool refuseSave;
  final List<String> calls = <String>[];
  Json? savedSettings;
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
    if (path.endsWith('/price-floor-settings')) {
      if (method == 'PUT') {
        if (refuseSave) {
          throw ApiException('Only a manager may change the price floor.');
        }
        savedSettings = Map<String, dynamic>.from(body ?? const {});
        return {
          'success': true,
          'data': {...?body, 'is_configured': true},
        };
      }
      return {
        'success': true,
        'data': {
          'enforcement': 'OFF',
          'include_cost': false,
          'is_configured': false,
        },
      };
    }
    if (path.contains('/credit-status')) {
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
    if (path.endsWith('/price-check')) {
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
    if (path.endsWith('/approve')) lastApproveQuery = query;
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
  _FloorApi api, {
  required PermissionService permissions,
}) async {
  final Directory temp =
      Directory.systemTemp.createTempSync('price-floor-test');
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

Future<void> _pumpSettings(
  WidgetTester tester,
  _FloorApi api,
  List<String> codes,
) async {
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: PriceFloorSettingsDialog(
        api: api,
        permissions: _withPermissions(codes),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the settings dialog saves the policy chosen', (tester) async {
    final _FloorApi api = _FloorApi();
    await _pumpSettings(tester, api, ['SALES_VIEW', 'SALES_MANAGE_SETTINGS']);

    await tester.tap(find.byKey(const ValueKey('price-floor-enforcement')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Block').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('price-floor-include-cost')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('price-floor-save')));
    await tester.pumpAndSettle();

    expect(api.savedSettings, {'enforcement': 'BLOCK', 'include_cost': true});
  });

  testWidgets('a refused save keeps the dialog open with the message',
      (tester) async {
    final _FloorApi api = _FloorApi(refuseSave: true);
    await _pumpSettings(tester, api, ['SALES_VIEW', 'SALES_MANAGE_SETTINGS']);

    await tester.tap(find.byKey(const ValueKey('price-floor-save')));
    await tester.pumpAndSettle();

    expect(find.text('Only a manager may change the price floor.'),
        findsOneWidget);
    expect(find.byType(PriceFloorSettingsDialog), findsOneWidget);
  });

  testWidgets('without the manage permission the policy cannot be saved',
      (tester) async {
    final _FloorApi api = _FloorApi();
    await _pumpSettings(tester, api, ['SALES_VIEW']);

    final FilledButton save = tester.widget(
      find.byKey(const ValueKey('price-floor-save')),
    );
    expect(save.onPressed, isNull);
  });

  testWidgets('under WARN the findings are listed and approving still runs',
      (tester) async {
    final _FloorApi api = _FloorApi(check: _check(wouldBlock: false));
    await _pumpAndApprove(
      tester,
      api,
      permissions: _withPermissions(['SALES_VIEW', 'SALES_APPROVE']),
    );

    expect(find.textContaining('below its minimum 95.00'), findsOneWidget);
    expect(find.text('Override…'), findsNothing);

    await tester.tap(find.byKey(const ValueKey('price-floor-approve-anyway')));
    await tester.pumpAndSettle();

    expect(api.calls.any((call) => call.endsWith('/price-check')), isTrue);
    expect(api.calls.any((call) => call.endsWith('/approve')), isTrue);
    expect(api.lastApproveQuery, isNull);
  });

  testWidgets('under BLOCK with the override permission a reason is sent',
      (tester) async {
    final _FloorApi api = _FloorApi(check: _check(wouldBlock: true));
    await _pumpAndApprove(
      tester,
      api,
      permissions: _withPermissions(
        ['SALES_VIEW', 'SALES_APPROVE', 'SALES_PRICE_OVERRIDE'],
      ),
    );

    await tester.tap(find.byKey(const ValueKey('price-floor-override')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, 'Reason'),
      'Clearing short-dated stock.',
    );
    await tester.tap(find.text('Override').last);
    await tester.pumpAndSettle();

    expect(
      api.lastApproveQuery?['price_override_reason'],
      'Clearing short-dated stock.',
    );
  });

  testWidgets('under BLOCK without the override permission nothing approves',
      (tester) async {
    final _FloorApi api = _FloorApi(check: _check(wouldBlock: true));
    await _pumpAndApprove(
      tester,
      api,
      permissions: _withPermissions(['SALES_VIEW', 'SALES_APPROVE']),
    );

    final Finder dialog = find.byType(AlertDialog);
    expect(find.descendant(of: dialog, matching: find.text('Override…')),
        findsNothing);
    expect(find.textContaining('who may override the price floor'),
        findsOneWidget);

    await tester.tap(find.descendant(of: dialog, matching: find.text('Close')));
    await tester.pumpAndSettle();

    expect(api.calls.any((call) => call.endsWith('/approve')), isFalse);
  });

  testWidgets('the product form sends minimum_selling_price', (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    Json? sent;
    final Product product = Product.fromJson(const {
      'id': 'product-1',
      'code': 'PROD-001',
      'name': 'Pain Relief',
      'product_type': 'STOCK_ITEM',
      'status': 'ACTIVE',
      'unit': 'BOX',
      'selling_price': '100',
      'minimum_selling_price': '95.00',
    });
    const ProductMetadataRecord metadata = ProductMetadataRecord(
      profileCode: 'WHOLESALE',
      features: [],
      categories: [],
      taxProfiles: [],
      requiredAttributeDefinitionIds: [],
      optionalAttributeDefinitionIds: [],
    );
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: ProductWorkspaceDialog(
          mode: ProductDialogMode.edit,
          product: product,
          categories: const [],
          uoms: const [],
          definitions: const [],
          metadata: metadata,
          initialTab: 'general',
          onMetadataForCategory: (_) async => metadata,
          onSave: (payload) async {
            sent = payload;
            return product;
          },
          onTabChanged: (_) {},
        ),
      ),
    ));
    await tester.pumpAndSettle();

    final Finder field =
        find.widgetWithText(TextField, 'Minimum selling price');
    expect(field, findsOneWidget);
    expect(find.textContaining('Per stock unit.'), findsOneWidget);
    await tester.ensureVisible(field);
    await tester.enterText(field, '97.50');
    await tester.tap(find.byKey(const ValueKey('product-save')));
    await tester.pumpAndSettle();

    expect(sent?['minimum_selling_price'], '97.50');
  });
}
