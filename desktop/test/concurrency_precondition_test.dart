// Every screen that can save an existing record should send the version it
// read, and say something true when the save is refused.
//
// The precondition is opt-in on the server: a request without `If-Match` is
// accepted. So nothing fails loudly if a screen stops sending it — the writes
// quietly go back to last-one-wins, which is the state this application was in
// until 2026-08-15. These tests are the only thing that notices.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/api/concurrency.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/quotation.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/models/inventory.dart';
import 'package:agency_desktop/models/sales_territory.dart';
import 'package:agency_desktop/models/tax_framework.dart';
import 'package:agency_desktop/models/uom_packaging.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('the precondition value', () {
    test('a real version is sent', () {
      expect(preconditionFor(7), 7);
    });

    test('zero sends nothing rather than a guess', () {
      // Zero is "the server published no version" — an older backend, or a
      // response predating the field. Sending 1, or *, would be inventing a
      // precondition nobody read.
      expect(preconditionFor(0), isNull);
    });
  });

  group('what the message says about the typing', () {
    test('an editor that stays open says the changes survive', () {
      final String message = concurrencyMessage('customer', changesKept: true);
      expect(message, contains('still here and have not been sent'));
    });

    test('an editor that has closed does not claim they survive', () {
      // Products and customers save from inside the dialog; vendors, branches,
      // warehouses and quotations return their payload and close first, so by
      // the time a refusal arrives the typing is already gone. Telling those
      // users their work is safe would be a lie they act on.
      final String message = concurrencyMessage('vendor', changesKept: false);
      expect(message, contains('were not saved'));
      expect(message, isNot(contains('still here')));
    });

    test('the noun is the one the user would say', () {
      expect(concurrencyMessage('quotation', changesKept: false),
          contains('this quotation'));
    });

    test('an ordinary failure keeps the server sentence', () {
      const ApiException duplicate = ApiException(
        'Vendor code already exists in this firm.',
        statusCode: 422,
      );
      expect(
        saveFailureMessage(duplicate, 'vendor', changesKept: false),
        'Vendor code already exists in this firm.',
      );
    });

    test('a conflict is rewritten', () {
      const ApiException conflict = ApiException(
        'This record changed since you loaded it. Reload and try again.',
        statusCode: 409,
      );
      expect(
        saveFailureMessage(conflict, 'vendor', changesKept: false),
        isNot(contains('Reload and try again')),
      );
    });
  });

  group('the version reaches the model', () {
    test('vendor', () {
      expect(Vendor.fromJson(_row('code')).version, 5);
    });

    test('product', () {
      expect(Product.fromJson(_row('code')).version, 5);
    });

    test('branch', () {
      expect(BranchRecord.fromJson(_row('code')).version, 5);
    });

    test('warehouse', () {
      expect(WarehouseRecord.fromJson(_row('code')).version, 5);
    });

    test('quotation', () {
      expect(Quotation.fromJson(_row('quotation_number')).version, 5);
    });

    test('a record without one reads as zero', () {
      final Json json = _row('code')..remove('version');
      expect(Vendor.fromJson(json).version, 0);
    });

    test('uom', () {
      expect(UomRecord.fromJson(_row('code')).version, 5);
    });

    test('uom group', () {
      expect(UomGroupRecord.fromJson(_row('code')).version, 5);
    });

    test('packaging type', () {
      expect(PackagingTypeRecord.fromJson(_row('code')).version, 5);
    });

    test('tax system', () {
      expect(TaxSystemRecord.fromJson(_row('code')).version, 5);
    });

    test('tax rule', () {
      expect(TaxRuleRecord.fromJson(_row('code')).version, 5);
    });

    test('batch', () {
      expect(BatchRecord.fromJson(_row('code')).version, 5);
    });

    test('lot', () {
      expect(LotRecord.fromJson(_row('code')).version, 5);
    });

    test('serial', () {
      expect(SerialRecord.fromJson(_row('code')).version, 5);
    });

    test('inventory record', () {
      expect(InventoryRecord.fromJson(_row('code')).version, 5);
    });

    test('territory', () {
      expect(SalesTerritory.fromJson(_row('code')).version, 5);
    });

    test('beat plan', () {
      expect(BeatPlanRecord.fromJson(_row('code')).version, 5);
    });

    test('route type', () {
      expect(TerritoryRouteTypeRecord.fromJson(_row('code')).version, 5);
    });

    test('a place', () {
      expect(
        GeoPlaceRecord.fromJson(GeoLevel.city, _row('code')).version,
        5,
      );
    });
  });

  group('two versions on one record', () {
    // uom and tax were the two modules left last-one-wins, and this is why:
    // a conversion rule and a tax rule each publish a revision of their own,
    // and the revision was called `version` -- the one name the concurrency
    // counter has to have. They are separate fields now.
    test('a conversion rule keeps its revision apart from its counter', () {
      final ConversionRuleRecord rule = ConversionRuleRecord.fromJson(
        <String, dynamic>{
          'id': 'rule-1',
          'from_uom_id': 'box',
          'to_uom_id': 'piece',
          'conversion_factor': '12',
          'version_number': 3,
          'version': 9,
          'effective_from': '2026-01-01',
          'status': 'ACTIVE',
        },
      );
      expect(rule.versionNumber, 3, reason: 'the published revision');
      expect(rule.version, 9, reason: 'the concurrency counter');
    });

    test('a tax rule does the same', () {
      final TaxRuleRecord rule = TaxRuleRecord.fromJson(<String, dynamic>{
        'id': 'rule-1',
        'code': 'GST_ZERO',
        'version_number': 2,
        'version': 6,
      });
      expect(rule.versionNumber, 2);
      expect(rule.version, 6);
    });

    test('an older backend that publishes neither still parses', () {
      final TaxRuleRecord rule = TaxRuleRecord.fromJson(<String, dynamic>{
        'id': 'rule-1',
        'code': 'GST_ZERO',
      });
      expect(rule.version, 0, reason: 'so the save carries no precondition');
    });
  });

  group('the screen sends it', () {
    test('a product save carries the version it was read at', () async {
      final _ProductApi api = _ProductApi();
      final ProductController controller = ProductController(api);
      final Product loaded = Product.fromJson(_row('code')..['version'] = 11);

      await controller.save(loaded, <String, dynamic>{});

      expect(api.sentVersion, 11);
    });

    test('a product create carries none', () async {
      final _ProductApi api = _ProductApi();
      final ProductController controller = ProductController(api);

      await controller.save(null, <String, dynamic>{});

      expect(api.sentVersion, isNull);
    });
  });
}

Json _row(String codeKey) => <String, dynamic>{
      'id': 'row-1',
      'version': 5,
      'firm_id': 'firm-1',
      codeKey: 'X-001',
      'name': 'Something',
      'display_name': 'Something',
      'status': 'ACTIVE',
      'currency_code': 'INR',
      'quotation_date': '2026-08-15',
      'valid_until': '2026-09-15',
      'customer_id': 'cust-1',
      'branch_id': 'branch-1',
      'warehouse_id': 'wh-1',
      'lines': <dynamic>[],
      'addresses': <dynamic>[],
      'contacts': <dynamic>[],
      'media': <dynamic>[],
      'attributes': <dynamic>[],
    };

class _ProductApi extends ApiClient {
  _ProductApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  int? sentVersion;

  @override
  Future<Product> updateProduct(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    sentVersion = expectedVersion;
    return Product.fromJson(_row('code'));
  }

  @override
  Future<Product> createProduct(Json data) async => Product.fromJson(_row('code'));
}
