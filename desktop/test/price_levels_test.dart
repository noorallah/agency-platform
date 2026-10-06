// SEL-9, the desktop half: named price levels.
//
//   * the Price Levels master lists, creates and sends the level as typed;
//   * the product editor sends a product's rates by level as one PUT -- the
//     whole list -- and never sends one it could not read first;
//   * the customer editor sends `price_level_id`, and only once the levels
//     arrived (absent leaves the level alone, null clears it);
//   * the sales order editor shows the server's price for the customer with
//     where it came from, and never overwrites a price somebody typed.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/pricing.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/pricing/price_level_page.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:agency_desktop/ui/sales/sales_order_editor_dialog.dart';
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

const List<PriceLevelRecord> _levels = [
  PriceLevelRecord(id: 'l1', code: 'DEALER', name: 'Dealer', sortOrder: 1),
  PriceLevelRecord(id: 'l2', code: 'RETAIL', name: 'Retail', sortOrder: 2),
];

class _Api extends ApiClient {
  _Api({this.levels = const <Json>[]})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> levels;
  Json? created;

  @override
  Future<List<PriceLevelRecord>> priceLevels() async =>
      [for (final Json row in levels) PriceLevelRecord.fromJson(row)];

  @override
  Future<Json> create(String resource, Json body) async {
    created = <String, dynamic>{'resource': resource, ...body};
    return <String, dynamic>{'data': body};
  }
}

Future<void> _pumpPhase2(
  WidgetTester tester,
  Widget child, {
  Size size = const Size(1600, 900),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, page) => Phase2Scope(child: page!),
    home: Scaffold(body: child),
  ));
  await tester.pumpAndSettle();
}

const ProductMetadataRecord _metadata = ProductMetadataRecord(
  profileCode: 'WHOLESALE',
  features: [],
  categories: [],
  taxProfiles: [],
  requiredAttributeDefinitionIds: [],
  optionalAttributeDefinitionIds: [],
);

final Product _product = Product.fromJson(const {
  'id': 'product-1',
  'code': 'PROD-001',
  'name': 'Pain Relief',
  'product_type': 'STOCK_ITEM',
  'status': 'ACTIVE',
  'unit': 'BOX',
  'selling_price': '100',
});

Widget _productForm({
  List<PriceLevelRecord>? levels = _levels,
  bool canManage = true,
  Future<List<ProductLevelRate>> Function(String)? load,
  required List<List<Json>> puts,
  List<Json>? saved,
}) =>
    ProductWorkspaceDialog(
      mode: ProductDialogMode.edit,
      product: _product,
      categories: const [],
      uoms: const [],
      definitions: const [],
      metadata: _metadata,
      initialTab: 'general',
      priceLevels: levels,
      canManageLevelRates: canManage,
      loadLevelRates: load ??
          (_) async => const [
                ProductLevelRate(
                  priceLevelId: 'l1',
                  priceLevelCode: 'DEALER',
                  priceLevelName: 'Dealer',
                  rate: '90.0000',
                ),
              ],
      onSaveLevelRates: (id, rates) async {
        expect(id, 'product-1');
        puts.add(rates);
      },
      onMetadataForCategory: (_) async => _metadata,
      onSave: (payload) async {
        saved?.add(payload);
        return _product;
      },
      onTabChanged: (_) {},
    );

Future<void> _typeRate(WidgetTester tester, String levelId, String text) async {
  final Finder box =
      find.byKey(ValueKey<String>('product-level-rate-$levelId'));
  await tester.ensureVisible(box);
  await tester.enterText(box, text);
}

void main() {
  group('the Price Levels master', () {
    testWidgets('lists the levels and creates one as typed', (tester) async {
      final _Api api = _Api(levels: [
        {'id': 'l1', 'code': 'DEALER', 'name': 'Dealer', 'sort_order': 1},
      ]);
      // The master is a plain page in the shell; its own button is "New".
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: PriceLevelPage(
            api: api,
            permissions:
                _permissions(['PRICE_LIST_VIEW', 'PRICE_LIST_MANAGE']),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      expect(find.text('Dealer'), findsWidgets);

      await tester.tap(find.widgetWithText(FilledButton, 'New').first);
      await tester.pumpAndSettle();
      await tester.enterText(
          find.widgetWithText(TextField, 'Code').first, 'export');
      await tester.enterText(
          find.widgetWithText(TextField, 'Name').first, 'Export');
      await tester.enterText(
          find.widgetWithText(TextField, 'Order').first, '3');
      await tester.tap(find.widgetWithText(FilledButton, 'Save & Close').last);
      await tester.pumpAndSettle();

      expect(api.created, <String, dynamic>{
        'resource': 'price-levels',
        'code': 'EXPORT',
        'name': 'Export',
        'sort_order': 3,
        'is_active': true,
      });
      expect(tester.takeException(), isNull);
    });
  });

  group('the Price Levels master sends the version it read (D-PRC-13)', () {
    Future<_LevelsWire> open(
      WidgetTester tester, {
      int? refuseWith,
    }) async {
      final _LevelsWire api = _LevelsWire(refuseWith: refuseWith);
      tester.view.physicalSize = const Size(1366, 768);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: PriceLevelPage(
            api: api,
            permissions:
                _permissions(['PRICE_LIST_VIEW', 'PRICE_LIST_MANAGE']),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      return api;
    }

    Future<void> openEditor(WidgetTester tester) async {
      await tester.tap(find.descendant(
        of: find.byType(DataTable),
        matching: find.byTooltip('Edit'),
      ).first);
      await tester.pumpAndSettle();
    }

    testWidgets('a save carries the row version as If-Match', (tester) async {
      final _LevelsWire api = await open(tester);
      await openEditor(tester);
      await tester.tap(find.widgetWithText(FilledButton, 'Save & Close').last);
      await tester.pumpAndSettle();

      expect(api.calls, ['PUT /api/v1/price-levels/l1 if-match=7']);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a delete carries it too', (tester) async {
      final _LevelsWire api = await open(tester);
      await tester.tap(find.byIcon(Icons.more_vert).first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Delete').last);
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Delete').last);
      await tester.pumpAndSettle();

      expect(api.calls, ['DELETE /api/v1/price-levels/l1 if-match=7']);
    });

    testWidgets('a stale save says somebody else changed it and stays open',
        (tester) async {
      final _LevelsWire api = await open(tester, refuseWith: 409);
      await openEditor(tester);
      await tester.tap(find.widgetWithText(FilledButton, 'Save & Close').last);
      await tester.pumpAndSettle();

      expect(find.textContaining('Somebody else saved this price level'),
          findsOneWidget);
      expect(find.textContaining('Reload and try again'), findsNothing);
      // Still open, still holding what was typed.
      expect(find.widgetWithText(FilledButton, 'Save & Close'), findsWidgets);
      expect(api.calls, hasLength(1));
    });

    testWidgets('a stale delete says so', (tester) async {
      await open(tester, refuseWith: 409);
      await tester.tap(find.byIcon(Icons.more_vert).first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Delete').last);
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Delete').last);
      await tester.pumpAndSettle();
      expect(find.textContaining('Somebody else saved this price level'),
          findsOneWidget);
    });
  });

  group('prices by level on the product', () {
    testWidgets('the whole list is sent after the product saves',
        (tester) async {
      final List<List<Json>> puts = [];
      final List<Json> saved = [];
      await _pumpPhase2(tester, _productForm(puts: puts, saved: saved));
      expect(find.text('Prices by level'), findsOneWidget);
      // The saved rate is read into its box.
      expect(
        tester
            .widget<TextField>(
                find.byKey(const ValueKey('product-level-rate-l1')))
            .controller!
            .text,
        '90.0000',
      );

      await _typeRate(tester, 'l2', '110');
      await tester.tap(find.byKey(const ValueKey('product-save')));
      await tester.pumpAndSettle();

      expect(saved, hasLength(1));
      expect(puts, hasLength(1));
      expect(puts.single, <Json>[
        {'price_level_id': 'l1', 'rate': '90.0000'},
        {'price_level_id': 'l2', 'rate': '110'},
      ]);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a rate cleared is left out of the list sent', (tester) async {
      final List<List<Json>> puts = [];
      await _pumpPhase2(tester, _productForm(puts: puts));
      await _typeRate(tester, 'l1', '');
      await tester.tap(find.byKey(const ValueKey('product-save')));
      await tester.pumpAndSettle();
      expect(puts.single, isEmpty);
    });

    testWidgets('nothing is sent for a grid nobody touched', (tester) async {
      final List<List<Json>> puts = [];
      await _pumpPhase2(tester, _productForm(puts: puts));
      await tester.tap(find.byKey(const ValueKey('product-save')));
      await tester.pumpAndSettle();
      expect(puts, isEmpty);
    });

    testWidgets('rates that could not be read are never replaced',
        (tester) async {
      final List<List<Json>> puts = [];
      await _pumpPhase2(
        tester,
        _productForm(
          puts: puts,
          load: (_) async => throw const ApiException('boom'),
        ),
      );
      final TextField box = tester.widget<TextField>(
          find.byKey(const ValueKey('product-level-rate-l1')));
      expect(box.readOnly, isTrue);
      expect(find.textContaining('could not be read'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('product-save')));
      await tester.pumpAndSettle();
      expect(puts, isEmpty);
    });

    testWidgets('hidden when the levels are not available', (tester) async {
      await _pumpPhase2(tester, _productForm(levels: null, puts: []));
      expect(find.text('Prices by level'), findsNothing);
    });

    testWidgets('read-only without PRICE_LIST_MANAGE', (tester) async {
      final List<List<Json>> puts = [];
      await _pumpPhase2(tester, _productForm(canManage: false, puts: puts));
      final TextField box = tester.widget<TextField>(
          find.byKey(const ValueKey('product-level-rate-l1')));
      expect(box.readOnly, isTrue);
      await tester.tap(find.byKey(const ValueKey('product-save')));
      await tester.pumpAndSettle();
      expect(puts, isEmpty);
    });
  });

  group('the price level on the customer', () {
    Json customerJson({String? level}) => <String, dynamic>{
          'id': 'cust-1',
          'version': 4,
          'firm_id': 'firm-1',
          'code': 'CUS-001',
          'customer_type': 'BUSINESS',
          'name': 'Anand Agencies',
          'display_name': 'Anand Agencies',
          'currency_code': 'INR',
          'status': 'ACTIVE',
          'payment_terms_days': 30,
          'price_level_id': level,
          'addresses': <dynamic>[],
          'contacts': <dynamic>[],
        };

    Widget form(
      List<Json> sent, {
      Future<List<PriceLevelRecord>> Function()? loadLevels,
    }) =>
        CustomerWorkspaceDialog(
          mode: CustomerDialogMode.edit,
          customer: Customer.fromJson(customerJson(level: 'l1')),
          onSave: (payload) async {
            sent.add(payload);
            return Customer.fromJson(customerJson());
          },
          loadPlaces: (level, {parentId = ''}) async => const [],
          loadPriceLevels: loadLevels,
        );

    testWidgets('sends the level picked, with the helper text', (tester) async {
      final List<Json> sent = [];
      await _pumpPhase2(tester, form(sent, loadLevels: () async => _levels));
      expect(find.textContaining("Blank: the group's level"), findsOneWidget);

      final Finder picker = find.byKey(const ValueKey('customer-price-level'));
      await tester.ensureVisible(picker);
      await tester.tap(picker);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Retail').last);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent.single['price_level_id'], 'l2');
    });

    testWidgets('an untouched level goes back as it was', (tester) async {
      final List<Json> sent = [];
      await _pumpPhase2(tester, form(sent, loadLevels: () async => _levels));
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent.single['price_level_id'], 'l1');
    });

    Widget lockedForm(
      List<Json> sent, {
      required CustomerDialogMode mode,
      required bool mayChange,
    }) =>
        CustomerWorkspaceDialog(
          mode: mode,
          customer: mode == CustomerDialogMode.edit
              ? Customer.fromJson(customerJson(level: 'l1'))
              : null,
          onSave: (payload) async {
            sent.add(payload);
            return Customer.fromJson(customerJson());
          },
          loadPlaces: (level, {parentId = ''}) async => const [],
          loadPriceLevels: () async => _levels,
          mayChangeCreditLimit: mayChange,
        );

    testWidgets('without the settings code the level is locked on an edit '
        'and goes back as stored', (tester) async {
      final List<Json> sent = [];
      await _pumpPhase2(
        tester,
        lockedForm(sent, mode: CustomerDialogMode.edit, mayChange: false),
      );
      final Finder picker = find.byKey(const ValueKey('customer-price-level'));
      expect(
        tester.widget<DropdownButtonFormField<String>>(picker).onChanged,
        isNull,
      );
      expect(find.textContaining('manage customer settings permission'),
          findsWidgets);

      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent.single['price_level_id'], 'l1');
    });

    testWidgets('without the settings code a new customer sends no level',
        (tester) async {
      final List<Json> sent = [];
      await _pumpPhase2(
        tester,
        lockedForm(sent, mode: CustomerDialogMode.create, mayChange: false),
      );
      final Finder picker = find.byKey(const ValueKey('customer-price-level'));
      expect(
        tester.widget<DropdownButtonFormField<String>>(picker).onChanged,
        isNull,
      );
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Customer name'), 'New Shop');
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Display name'), 'New Shop');
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent, hasLength(1));
      expect(sent.single.containsKey('price_level_id'), isFalse);
    });

    testWidgets('with the settings code the picker is open', (tester) async {
      final List<Json> sent = [];
      await _pumpPhase2(
        tester,
        lockedForm(sent, mode: CustomerDialogMode.edit, mayChange: true),
      );
      final Finder picker = find.byKey(const ValueKey('customer-price-level'));
      expect(
        tester.widget<DropdownButtonFormField<String>>(picker).onChanged,
        isNotNull,
      );
    });

    testWidgets('levels that did not load: no picker, nothing sent',
        (tester) async {
      final List<Json> sent = [];
      await _pumpPhase2(
        tester,
        form(sent, loadLevels: () async => throw const ApiException('no')),
      );
      expect(find.byKey(const ValueKey('customer-price-level')), findsNothing);
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent.single.containsKey('price_level_id'), isFalse);
    });
  });

  group('the price on a sales order line', () {
    testWidgets('shows the server price and its source, and keeps a typed one',
        (tester) async {
      final _OrderApi api = _OrderApi();
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (BuildContext context) => TextButton(
              onPressed: () => Navigator.of(context).push<bool>(
                MaterialPageRoute<bool>(
                  builder: (_) => Scaffold(
                    body: Phase2Scope(
                      child: SalesOrderEditorDialog(
                        api: api,
                        today: DateTime(2026, 8, 14),
                      ),
                    ),
                  ),
                ),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      Finder lineBoxes() => find.descendant(
            of: find.byKey(const ValueKey<String>('sales-order-line-0')),
            matching: find.byType(EditableText),
          );
      String price() =>
          tester.widget<EditableText>(lineBoxes().at(3)).controller.text;

      // No customer yet: the product's own price, nothing asked.
      expect(price(), '100');
      expect(api.asked, isEmpty);

      await tester.tap(find.byKey(const ValueKey('sales-order-customer')));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('Anand Agencies').last);
      await tester.pumpAndSettle();
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();

      expect(api.asked, hasLength(1));
      expect(api.asked.single.customerId, 'c1');
      expect(api.asked.single.productIds, ['p1']);
      expect(api.asked.single.on, '2026-08-14');
      expect(price(), '90.00');
      expect(find.text('from: Dealer level'), findsOneWidget);

      // A typed price is the user's: another customer does not rewrite it.
      await tester.enterText(lineBoxes().at(3), '95');
      await tester.pump(const Duration(milliseconds: 400));
      await tester.tap(find.byKey(const ValueKey('sales-order-customer')));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('Bright Stores').last);
      await tester.pumpAndSettle();
      expect(price(), '95');
      expect(find.text('as typed on this order'), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('sales-order-save')));
      await tester.pumpAndSettle();
      final Json line = (api.created!['lines'] as List).first as Json;
      expect(line['unit_price'], '95');
      expect(tester.takeException(), isNull);
    });
  });
}

/// One price level at version 7, recording every write with its If-Match.
class _LevelsWire extends ApiClient {
  _LevelsWire({this.refuseWith})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final int? refuseWith;
  final List<String> calls = <String>[];

  static const Map<String, dynamic> _row = <String, dynamic>{
    'id': 'l1',
    'code': 'DEALER',
    'name': 'Dealer',
    'sort_order': 1,
    'is_active': true,
    'version': 7,
  };

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
    if (method == 'PUT' || method == 'DELETE') {
      calls.add('$method $path if-match=$expectedVersion');
      if (refuseWith != null) {
        throw ApiException(
          'This record changed since you loaded it. Reload and try again.',
          statusCode: refuseWith,
        );
      }
      return <String, dynamic>{'data': _row};
    }
    return <String, dynamic>{
      'data': <Json>[_row],
    };
  }
}

class _Asked {
  const _Asked(this.productIds, this.on, this.customerId);
  final List<String> productIds;
  final String on;
  final String customerId;
}

class _OrderApi extends ApiClient {
  _OrderApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<_Asked> asked = [];
  Json? created;

  @override
  Future<Map<String, UnitPriceQuote>> unitPrices({
    required List<String> productIds,
    required String on,
    String customerId = '',
    String territoryId = '',
  }) async {
    asked.add(_Asked(productIds, on, customerId));
    return {
      'p1': const UnitPriceQuote(
        productId: 'p1',
        unitPrice: '90.0000',
        source: 'PRICE_LEVEL',
      ),
    };
  }

  Json _paged(List<Json> rows) => <String, dynamic>{
        'data': rows,
        'pagination': <String, dynamic>{'total_records': rows.length},
      };

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
    if (path == '/api/v1/customers') {
      return _paged(<Json>[
        for (final (String id, String name) in [
          ('c1', 'Anand Agencies'),
          ('c2', 'Bright Stores'),
        ])
          <String, dynamic>{
            'id': id,
            'code': id.toUpperCase(),
            'name': name,
            'display_name': name,
            'customer_type': 'BUSINESS',
            'currency_code': 'INR',
            'status': 'ACTIVE',
          },
      ]);
    }
    if (path == '/api/v1/products') {
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'p1',
          'code': 'P1',
          'name': 'Shampoo 180ml',
          'selling_price': '100',
          'mrp': '120',
          'status': 'ACTIVE',
        },
      ]);
    }
    if (path == '/api/v1/branches') {
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'b1',
          'code': 'HO',
          'name': 'Head Office',
          'display_name': 'Head Office',
          'is_default': true,
        },
      ]);
    }
    if (path == '/api/v1/warehouses') {
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'w1',
          'code': 'WH1',
          'name': 'Main Store',
          'display_name': 'Main Store',
          'is_default': true,
          'branch_id': 'b1',
        },
      ]);
    }
    if (method == 'GET' && path == '/api/v1/sales-orders/workflow-settings') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'quotation_stage': true,
          'sales_order_stage': true,
          'delivery_note_stage': true,
          'rate_includes_tax': false,
          'is_configured': true,
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/sales-orders') {
      created = body;
      return <String, dynamic>{
        'data': <String, dynamic>{'id': 'so-1', 'order_number': 'SO-1'},
      };
    }
    if (method == 'POST' && path == '/api/v1/sales-orders/preview') {
      // Keep the last figures: the preview is not what is under test.
      throw const ApiException('not priced in this test');
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}
