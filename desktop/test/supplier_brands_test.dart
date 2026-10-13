// Backlog 129 (M11): a supplier names the brands it may sell, and the product
// box on a purchase order is narrowed to them; the product box on a sales
// order can be narrowed by company or brand. It is only a filter on what the
// box offers: nothing is stored on the document and nothing is refused.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/purchases/purchase_management_page.dart';
import 'package:agency_desktop/ui/sales/sales_order_editor_dialog.dart';
import 'package:agency_desktop/ui/vendors/vendor_management_page.dart';
import 'package:agency_desktop/ui/vendors/vendor_brands_section.dart';
import 'package:agency_desktop/ui/workspace/brand_filter.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

BrandRecord _brand(String id, String name, String companyId, String company) =>
    BrandRecord(
      id: id,
      name: name,
      principalId: companyId,
      principalName: company,
      isActive: true,
    );

final List<BrandRecord> _firmBrands = <BrandRecord>[
  _brand('b-sun', 'Sunrise', 'co-acme', 'Acme Foods'),
  _brand('b-moon', 'Moonlight', 'co-acme', 'Acme Foods'),
  _brand('b-star', 'Starlight', 'co-zed', 'Zed Ltd'),
];

Json _productJson(String id, String name, {String brandId = ''}) =>
    <String, dynamic>{
      'id': id,
      'firm_id': 'firm-1',
      'code': id.toUpperCase(),
      'name': name,
      'unit': 'BOX',
      'purchase_price': '100',
      'selling_price': '120',
      'mrp': '150',
      'status': 'ACTIVE',
      if (brandId.isNotEmpty) 'brand_id': brandId,
      if (brandId.isNotEmpty)
        'brand': _firmBrands.firstWhere((b) => b.id == brandId).name,
    };

Product _product(String id, String name, {String brandId = ''}) =>
    Product.fromJson(_productJson(id, name, brandId: brandId));

final Product _alpha = _product('pa', 'Alpha Biscuit', brandId: 'b-sun');
final Product _moon = _product('pm', 'Moon Cake', brandId: 'b-moon');
final Product _star = _product('ps', 'Star Candy', brandId: 'b-star');
final Product _plain = _product('pn', 'Plain Salt');

VendorBrands _limited(List<BrandRecord> brands, {String source = 'OWN'}) =>
    VendorBrands(
      vendorId: 'vendor-1',
      source: source,
      sourceVendorName: source == 'MAIN_OFFICE' ? 'Head Office Traders' : '',
      namedBrandIds: source == 'OWN' ? [for (final b in brands) b.id] : [],
      brands: brands,
    );

VendorBrands _notLimited() => const VendorBrands(
      vendorId: 'vendor-1',
      source: 'NONE',
      sourceVendorName: '',
      namedBrandIds: <String>[],
      brands: <BrandRecord>[],
    );

class _Api extends ApiClient {
  _Api({
    this.stored,
    this.failBrandsRead = false,
    this.firm = const <BrandRecord>[],
  }) : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// What `GET /vendors/{id}/brands` answers, per supplier id.
  Map<String, VendorBrands>? stored;
  final bool failBrandsRead;
  final List<BrandRecord> firm;
  final List<String> calls = <String>[];
  List<String>? savedIds;

  @override
  Future<List<BrandRecord>> brands() async {
    calls.add('brands');
    if (failBrandsRead) throw const ApiException('down', statusCode: 500);
    return firm;
  }

  @override
  Future<VendorBrands> vendorBrands(String vendorId) async {
    calls.add('vendorBrands $vendorId');
    if (failBrandsRead) throw const ApiException('down', statusCode: 500);
    return stored![vendorId] ?? stored!['*']!;
  }

  @override
  Future<VendorBrands> setVendorBrands(
    String vendorId,
    List<String> brandIds,
  ) async {
    calls.add('setVendorBrands $vendorId');
    savedIds = brandIds;
    final VendorBrands now = VendorBrands(
      vendorId: vendorId,
      source: brandIds.isEmpty ? 'NONE' : 'OWN',
      sourceVendorName: '',
      namedBrandIds: brandIds,
      brands: [
        for (final BrandRecord brand in firm)
          if (brandIds.contains(brand.id)) brand,
      ],
    );
    stored = <String, VendorBrands>{vendorId: now};
    return now;
  }

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
    if (path == '/api/v1/customers') {
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'c1',
          'code': 'C1',
          'name': 'Anand Agencies',
          'display_name': 'Anand Agencies',
          'customer_type': 'BUSINESS',
          'currency_code': 'INR',
          'status': 'ACTIVE',
        },
      ]);
    }
    if (path == '/api/v1/products') {
      return _paged(<Json>[
        for (final Product item in _salesProducts) _productJson(
            item.id, item.name, brandId: item.brandId),
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
    if (method == 'POST' && path.endsWith('/preview')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'interstate': false,
          'order': <String, dynamic>{'lines': <Json>[]},
          'lines': <Json>[],
        },
      };
    }
    return <String, dynamic>{'data': const <dynamic>[]};
  }

  List<Product> _salesProducts = <Product>[];

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async =>
      PagedResult<Vendor>(
        items: <Vendor>[
          Vendor.fromJson(_vendorJson('vendor-1', 'V001', 'Supplier One')),
        ],
        total: 1,
      );
}

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(
    'header.${base64Url.encode(utf8.encode(jsonEncode(<String, dynamic>{
          'roles': <String>['user'],
          'permissions': codes,
        }))).replaceAll('=', '')}.sig',
  );

Json _paged(List<Json> rows) => <String, dynamic>{
      'data': rows,
      'pagination': <String, dynamic>{'total_records': rows.length},
    };

Json _vendorJson(String id, String code, String name) => <String, dynamic>{
      'id': id,
      'firm_id': 'firm-1',
      'code': code,
      'name': name,
      'display_name': name,
      'status': 'ACTIVE',
      'addresses': <Json>[],
      'contacts': <Json>[],
      'bank_accounts': <Json>[],
      'tax_details': <Json>[],
      'notes': <Json>[],
    };

Finder _keyed(String prefix) => find.byWidgetPredicate((widget) =>
    widget.key is ValueKey<String> &&
    (widget.key! as ValueKey<String>).value.startsWith(prefix));

/// The labels a line's product box offers, read off the box itself.
List<String> _offered(WidgetTester tester, Finder box) => tester
    .widget<DropdownMenu<String>>(box)
    .dropdownMenuEntries
    .map((entry) => entry.label)
    .toList();

String _text(WidgetTester tester, Finder box) => tester
    .widget<EditableText>(
      find.descendant(of: box, matching: find.byType(EditableText)).first,
    )
    .controller
    .text;

Future<void> _pumpSection(
  WidgetTester tester,
  _Api api, {
  bool canManage = true,
}) async {
  tester.view.physicalSize = const Size(1200, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: SingleChildScrollView(
        child: VendorBrandsSection(
          api: api,
          vendorId: 'vendor-1',
          canManage: canManage,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _pumpOrder(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseOrderEditorDialog(
          api: api,
          permissions: PermissionService(),
          mode: PurchaseDialogMode.create,
          order: null,
          vendors: <Vendor>[
            Vendor.fromJson(
                _vendorJson('vendor-1', 'V001', 'Northwind Supplies')),
            Vendor.fromJson(_vendorJson('vendor-2', 'V002', 'Open Traders')),
          ],
          branches: <BranchRecord>[
            BranchRecord.fromJson(<String, dynamic>{
              'id': 'branch-1',
              'firm_id': 'firm-1',
              'code': 'BR-001',
              'name': 'Main Branch',
              'display_name': 'Main Branch',
              'status': 'ACTIVE',
              'is_default': true,
            }),
          ],
          warehouses: <WarehouseRecord>[
            WarehouseRecord.fromJson(<String, dynamic>{
              'id': 'warehouse-1',
              'firm_id': 'firm-1',
              'branch_id': 'branch-1',
              'code': 'WH-001',
              'name': 'Main Warehouse',
              'status': 'ACTIVE',
              'is_default': true,
            }),
          ],
          products: <Product>[_alpha, _moon, _star, _plain],
          buyers: const [],
          taxProfiles: const [],
          storageNodes: const [],
          canSubmit: true,
          canApprove: false,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _chooseSupplier(WidgetTester tester, String name) async {
  await tester.tap(find.byKey(const ValueKey('purchase-order-vendor')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining(name).last);
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _chooseBrand(
  WidgetTester tester,
  String key,
  String words,
) async {
  await tester.tap(find.byKey(ValueKey<String>(key)).first);
  await tester.pumpAndSettle();
  await tester.tap(find.text(words).last);
  await tester.pumpAndSettle();
}

Finder get _poBox => _keyed('purchase-order-line-product-').first;

void main() {
  group('narrowing a product list', () {
    test('keeps the products of the brands and every kept id', () {
      final List<Product> all = <Product>[_alpha, _moon, _star, _plain];
      expect(
        productsOfBrands(all, <String>{'b-sun'}).map((p) => p.id),
        <String>['pa'],
      );
      // A product already on a line stays whatever the brand.
      expect(
        productsOfBrands(all, <String>{'b-sun'}, keepIds: <String>{'ps', 'pn'})
            .map((p) => p.id),
        <String>['pa', 'ps', 'pn'],
      );
      // No brand ticked offers only what is kept.
      expect(productsOfBrands(all, <String>{}), isEmpty);
    });

    test('the brands the products carry, once each, by name', () {
      expect(
        brandsOfProducts(<Product>[_star, _alpha, _moon, _plain, _alpha]),
        <(String, String)>[
          ('b-moon', 'Moonlight'),
          ('b-star', 'Starlight'),
          ('b-sun', 'Sunrise'),
        ],
      );
    });

    test('sales choices: a company is its brands, and a brand only if carried',
        () {
      final List<Product> all = <Product>[_alpha, _moon, _star];
      final List<(String, String)> options = salesBrandOptions(all, _firmBrands);
      expect(options.first, ('', 'All products'));
      expect(options.map((o) => o.$2), contains('Acme Foods (all its brands)'));
      expect(options.map((o) => o.$2), contains('Zed Ltd (all its brands)'));
      expect(
        productsForSalesChoice('company:co-acme', all, _firmBrands)
            .map((p) => p.id),
        <String>['pa', 'pm'],
      );
      // A brand no loaded product carries is not offered.
      expect(
        salesBrandOptions(<Product>[_alpha], _firmBrands).map((o) => o.$2),
        <String>['All products', 'Acme Foods (all its brands)', 'Sunrise'],
      );
      // No brand records read: brands from the products, no companies.
      expect(
        salesBrandOptions(all, const <BrandRecord>[]).map((o) => o.$2),
        <String>['All products', 'Moonlight', 'Starlight', 'Sunrise'],
      );
    });
  });

  group('brands this supplier sells (supplier form)', () {
    testWidgets('shows the ticks from the named ids and saves the ticked ids',
        (tester) async {
      final _Api api = _Api(
        firm: _firmBrands,
        stored: <String, VendorBrands>{
          'vendor-1': _limited(<BrandRecord>[_firmBrands[0]]),
        },
      );
      await _pumpSection(tester, api);

      // Two reads on opening, nothing else.
      expect(api.calls, <String>['brands', 'vendorBrands vendor-1']);
      expect(find.text('Sunrise'), findsOneWidget);
      expect(find.text('Acme Foods'), findsNWidgets(2));
      expect(
        tester
            .widget<CheckboxListTile>(
                find.byKey(const ValueKey('vendor-brand-b-sun')))
            .value,
        isTrue,
      );
      expect(
        tester
            .widget<CheckboxListTile>(
                find.byKey(const ValueKey('vendor-brand-b-star')))
            .value,
        isFalse,
      );
      // Nothing changed yet: nothing to save.
      expect(
        tester
            .widget<FilledButton>(find.byKey(const ValueKey('vendor-brands-save')))
            .onPressed,
        isNull,
      );

      await tester.tap(find.byKey(const ValueKey('vendor-brand-b-star')));
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('vendor-brands-save')));
      await tester.pumpAndSettle();

      expect(api.savedIds, unorderedEquals(<String>['b-sun', 'b-star']));
      expect(api.calls.where((c) => c.startsWith('setVendorBrands')).length, 1);
      expect(tester.takeException(), isNull);
    });

    testWidgets('says what applies with nothing ticked: not limited',
        (tester) async {
      final _Api api = _Api(
        firm: _firmBrands,
        stored: <String, VendorBrands>{'vendor-1': _notLimited()},
      );
      await _pumpSection(tester, api);
      expect(
        find.text(
            "No brand ticked: every product is offered on this supplier's orders."),
        findsOneWidget,
      );
    });

    testWidgets('says what applies with nothing ticked: a main office',
        (tester) async {
      final _Api api = _Api(
        firm: _firmBrands,
        stored: <String, VendorBrands>{
          'vendor-1': _limited(
            <BrandRecord>[_firmBrands[0], _firmBrands[1]],
            source: 'MAIN_OFFICE',
          ),
        },
      );
      await _pumpSection(tester, api);
      expect(
        find.text('No brand ticked: it takes the brands of its main office, '
            'Head Office Traders: Sunrise, Moonlight.'),
        findsOneWidget,
      );
    });

    testWidgets('says what applies with nothing ticked: its company',
        (tester) async {
      final _Api api = _Api(
        firm: _firmBrands,
        stored: <String, VendorBrands>{
          'vendor-1': _limited(<BrandRecord>[_firmBrands[2]],
              source: 'COMPANY'),
        },
      );
      await _pumpSection(tester, api);
      expect(
        find.text('No brand ticked: the brands of its company are offered: '
            'Starlight.'),
        findsOneWidget,
      );
    });

    testWidgets('no Save and no tick boxes to change without VENDOR_UPDATE',
        (tester) async {
      final _Api api = _Api(
        firm: _firmBrands,
        stored: <String, VendorBrands>{
          'vendor-1': _limited(<BrandRecord>[_firmBrands[0]]),
        },
      );
      await _pumpSection(tester, api, canManage: false);
      expect(find.byKey(const ValueKey('vendor-brands-save')), findsNothing);
      expect(
        tester
            .widget<CheckboxListTile>(
                find.byKey(const ValueKey('vendor-brand-b-sun')))
            .onChanged,
        isNull,
      );
    });

    testWidgets('a firm with no brands is pointed at Brands, with no Save',
        (tester) async {
      final _Api api = _Api(
        stored: <String, VendorBrands>{'vendor-1': _notLimited()},
      );
      await _pumpSection(tester, api);
      expect(find.text('No brands yet. Add them under Brands.'),
          findsOneWidget);
      expect(find.byKey(const ValueKey('vendor-brands-save')), findsNothing);
    });

    testWidgets('a failed read leaves nothing that could be saved',
        (tester) async {
      final _Api api = _Api(failBrandsRead: true);
      await _pumpSection(tester, api);
      expect(find.byKey(const ValueKey('vendor-brands-error')), findsOneWidget);
      expect(find.byKey(const ValueKey('vendor-brands-save')), findsNothing);
      expect(find.byType(CheckboxListTile), findsNothing);
    });
  });

  group('on the supplier record', () {
    Future<void> open(WidgetTester tester, _Api api, List<String> codes) async {
      tester.view.physicalSize = const Size(1600, 1100);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: VendorManagementPage(
            api: api,
            permissions: _permissions(codes),
            hasActiveFirm: true,
          ),
        ),
      ));
      await tester.pumpAndSettle();
      await tester.tap(find.text('V001').first);
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Edit').first);
      await tester.pumpAndSettle();
    }

    testWidgets('a saved supplier has the section, read once when it opens',
        (tester) async {
      final _Api api = _Api(
        firm: _firmBrands,
        stored: <String, VendorBrands>{'vendor-1': _notLimited()},
      );
      await open(tester, api, <String>['VENDOR_VIEW', 'VENDOR_UPDATE']);
      expect(find.text('Brands this supplier sells'), findsOneWidget);
      expect(find.byKey(const ValueKey('vendor-brand-b-sun')), findsOneWidget);
      expect(api.calls.where((c) => c == 'brands').length, 1);
      expect(api.calls.where((c) => c.startsWith('vendorBrands')).length, 1);
    });
  });

  group('on a purchase order', () {
    testWidgets('a supplier with one brand offers only that brand\'s products',
        (tester) async {
      final _Api api = _Api(stored: <String, VendorBrands>{
        'vendor-1': _limited(<BrandRecord>[_firmBrands[0]]),
        'vendor-2': _notLimited(),
      });
      await _pumpOrder(tester, api);
      // Before a supplier is chosen nothing is narrowed and no read is made.
      expect(_offered(tester, _poBox), hasLength(4));
      expect(api.calls.where((c) => c.startsWith('vendorBrands')), isEmpty);

      await _chooseSupplier(tester, 'Northwind');
      expect(api.calls.where((c) => c.startsWith('vendorBrands')).length, 1);
      expect(_offered(tester, _poBox), hasLength(1));
      expect(_offered(tester, _poBox).single, contains('Alpha Biscuit'));

      // The Brand box: the supplier's brands, then every product.
      await tester.tap(find.byKey(const ValueKey('purchase-order-brand')));
      await tester.pumpAndSettle();
      expect(find.text('All brands of this supplier'), findsWidgets);
      expect(find.text('Sunrise'), findsWidgets);
      expect(find.text('Every product'), findsWidgets);
      await tester.tap(find.text('Every product').last);
      await tester.pumpAndSettle();
      expect(_offered(tester, _poBox), hasLength(4));
      expect(tester.takeException(), isNull);
    });

    testWidgets('a line already holding another brand\'s product keeps it',
        (tester) async {
      final _Api api = _Api(stored: <String, VendorBrands>{
        'vendor-1': _limited(<BrandRecord>[_firmBrands[0]]),
        'vendor-2': _notLimited(),
      });
      await _pumpOrder(tester, api);
      await _chooseSupplier(tester, 'Open Traders');
      await tester.tap(_poBox);
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('Moon Cake').last);
      await tester.pumpAndSettle();
      expect(_text(tester, _poBox), contains('Moon Cake'));

      await _chooseSupplier(tester, 'Northwind');
      // Moon Cake is not Sunrise, but the line holds it.
      expect(_text(tester, _poBox), contains('Moon Cake'));
      final List<String> offered = _offered(tester, _poBox);
      expect(offered.any((label) => label.contains('Alpha Biscuit')), isTrue);
      expect(offered.any((label) => label.contains('Moon Cake')), isTrue);
      expect(offered.any((label) => label.contains('Star Candy')), isFalse);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a supplier that is not limited offers everything by brand',
        (tester) async {
      final _Api api = _Api(stored: <String, VendorBrands>{
        '*': _notLimited(),
      });
      await _pumpOrder(tester, api);
      await _chooseSupplier(tester, 'Open Traders');
      expect(_offered(tester, _poBox), hasLength(4));

      // All products, then the brands the loaded products carry.
      await tester.tap(find.byKey(const ValueKey('purchase-order-brand')));
      await tester.pumpAndSettle();
      expect(find.text('All products'), findsWidgets);
      expect(find.text('Moonlight'), findsWidgets);
      expect(find.text('Every product'), findsNothing);
      await tester.tap(find.text('Moonlight').last);
      await tester.pumpAndSettle();
      expect(_offered(tester, _poBox).single, contains('Moon Cake'));

      // A different supplier resets the choice.
      await _chooseSupplier(tester, 'Northwind');
      expect(_offered(tester, _poBox), hasLength(4));
    });

    testWidgets('a failed read of the brands offers everything, quietly',
        (tester) async {
      final _Api api = _Api(failBrandsRead: true);
      await _pumpOrder(tester, api);
      await _chooseSupplier(tester, 'Northwind');
      expect(_offered(tester, _poBox), hasLength(4));
      expect(find.text('down'), findsNothing);
      expect(tester.takeException(), isNull);
    });
  });

  group('on a sales order', () {
    testWidgets('choosing a company narrows the product box to its brands',
        (tester) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final _Api api = _Api(firm: _firmBrands)
        .._salesProducts = <Product>[_alpha, _moon, _star, _plain];
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Phase2Scope(
            child: SalesOrderEditorDialog(
              api: api,
              today: DateTime(2026, 8, 14),
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();

      // One read of the brands, when the editor opens.
      expect(api.calls.where((c) => c == 'brands').length, 1);
      const ValueKey<String> line = ValueKey('sales-order-line-product-0');
      expect(_offered(tester, find.byKey(line)), hasLength(4));

      await _chooseBrand(
        tester,
        'sales-order-brand',
        'Acme Foods (all its brands)',
      );
      final List<String> offered = _offered(tester, find.byKey(line));
      expect(offered, hasLength(2));
      expect(offered.any((label) => label.contains('Alpha Biscuit')), isTrue);
      expect(offered.any((label) => label.contains('Moon Cake')), isTrue);

      await _chooseBrand(tester, 'sales-order-brand', 'Starlight');
      expect(_offered(tester, find.byKey(line)).single, contains('Star Candy'));
      expect(api.calls.where((c) => c == 'brands').length, 1);
      expect(tester.takeException(), isNull);
    });
  });
}
