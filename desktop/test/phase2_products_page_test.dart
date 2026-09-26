import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Products in phase 2, as the wireframe's view 6: the Stock column with low
/// stock in red, counters that filter (Active, Low stock, No price), and one
/// "Views" chip for saved and recent searches.
class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<ProductQuery> asked = [];

  @override
  Future<PagedResult<Product>> products({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    ProductQuery filters = const ProductQuery(),
  }) async {
    asked.add(filters);
    final List<Product> all = [_short, _plenty];
    return PagedResult(
      items: filters.lowStock ? [_short] : all,
      total: filters.lowStock ? 1 : all.length,
    );
  }

  @override
  Future<Json> documentSummary(String resource,
          {String path = 'summary'}) async =>
      {
        'data': {'active': 2, 'low_stock': 1, 'no_price': 0},
      };

  @override
  Future<List<ProductCategoryRecord>> productCategories() async => const [];

  @override
  Future<ProductMetadataRecord> productMetadata({String? categoryId}) async =>
      const ProductMetadataRecord(
        profileCode: '',
        features: [],
        categories: [],
        taxProfiles: [],
        requiredAttributeDefinitionIds: [],
        optionalAttributeDefinitionIds: [],
      );
}

Product _item(String code, String stock, {bool low = false}) =>
    Product.fromJson({
      'id': code,
      'firm_id': 'firm-1',
      'code': code,
      'name': code,
      'product_type': 'STOCK_ITEM',
      'status': 'ACTIVE',
      'selling_price': '142.00',
      'mrp': '165.00',
      'hsn_sac': '1512',
      'tax_profile_group_code': 'GST_5_LOCAL',
      'stock_on_hand': stock,
      'low_stock': low,
      'attributes': [],
      'media': [],
    });

final Product _short = _item('SHORT', '6', low: true);
final Product _plenty = _item('PLENTY', '240');

Future<_Api> _pump(WidgetTester tester, {double width = 1600}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = Size(width, 800);
  addTearDown(tester.view.reset);
  final _Api api = _Api();
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: ProductManagementPage(
          api: api,
          permissions: PermissionService(),
          // A real folder: applying a filter saves it there.
          preferences: DesktopPreferencesService(
            directory: Directory.systemTemp.createTempSync('products'),
          ),
          hasActiveFirm: true,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return api;
}

void main() {
  testWidgets('the wireframe columns, with low stock in red', (tester) async {
    await _pump(tester, width: 2400);
    for (final String heading in [
      'Code',
      'Name',
      'Unit',
      'HSN',
      'GST',
      'MRP',
      'Selling',
      'Stock',
      'Status',
    ]) {
      expect(find.text(heading), findsOneWidget, reason: heading);
    }
    // Phase 1's row numbers, ticks and Created are not in the wireframe.
    expect(find.text('Created'), findsNothing);
    expect(find.byType(Checkbox), findsNothing);
    expect(find.text('5%'), findsNWidgets(2));
    expect(find.text('Active'), findsWidgets);

    final Text low = tester.widget<Text>(find.text('6'));
    final ThemeData theme = Theme.of(tester.element(find.text('6')));
    expect(low.style?.color, theme.colorScheme.error);
    final Text plenty = tester.widget<Text>(find.text('240'));
    expect(plenty.style?.color, isNot(theme.colorScheme.error));
  });

  testWidgets('the Low stock counter filters the list', (tester) async {
    final _Api api = await _pump(tester);
    expect(find.text('PLENTY'), findsNWidgets(2));

    await tester.tap(find.byKey(const ValueKey('product-counter-low-stock')));
    // Applying a filter saves it to the preferences file first: real I/O,
    // in steps, each of which needs real time and then a pump.
    for (int i = 0; i < 10 && api.asked.length < 2; i++) {
      await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 50)));
      await tester.pump();
    }
    await tester.pumpAndSettle();

    expect(api.asked.last.lowStock, isTrue);
    expect(find.text('PLENTY'), findsNothing);
    expect(find.text('SHORT'), findsNWidgets(2));
  });

  testWidgets('saved and recent searches are one Views chip', (tester) async {
    await _pump(tester);
    expect(find.byKey(const ValueKey('products-views')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('products-views')));
    await tester.pumpAndSettle();
    expect(find.text('No saved views'), findsOneWidget);
    expect(find.byKey(const ValueKey('products-save-filter')), findsOneWidget);
  });
}
