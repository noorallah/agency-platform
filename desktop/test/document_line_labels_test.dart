// A document view prints names for the ids a line carries.
//
// Raised from manual testing at 7.8: the goods receipt view showed the
// product as its UUID. Every workspace already reads the firm's products;
// this resolves the ids against those lists, falling back to the id itself
// for one the lists do not hold so a stale list never blanks a line.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/tax_framework.dart';
import 'package:agency_desktop/models/uom_packaging.dart';
import 'package:agency_desktop/ui/document_framework/document_line_labels.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final DocumentLineLabels labels = DocumentLineLabels(
    products: [
      Product.fromJson(<String, dynamic>{
        'id': 'p-1',
        'firm_id': 'firm-1',
        'code': 'DETER1K',
        'name': 'Detergent Powder 1kg',
        'status': 'ACTIVE',
      }),
    ],
    units: [
      UomRecord.fromJson(<String, dynamic>{
        'id': 'u-kg',
        'code': 'KG',
        'name': 'Kilogram',
        'status': 'ACTIVE',
      }),
    ],
    taxProfiles: [
      TaxProfileRecord.fromJson(<String, dynamic>{
        'id': 't-18',
        'tax_system_id': 'gst',
        'code': 'GST_18_LOCAL',
        'name': 'GST 18% local',
        'label': 'GST 18%',
        'status': 'ACTIVE',
        'components': <Map<String, dynamic>>[],
      }),
    ],
  );

  test('a known id becomes its code and name', () {
    expect(labels.product('p-1'), 'DETER1K — Detergent Powder 1kg');
    expect(labels.unit('u-kg'), 'KG');
    expect(labels.taxProfile('t-18'), 'GST_18_LOCAL');
  });

  test('an unknown id is shown as itself, never blanked', () {
    expect(labels.product('p-9'), 'p-9');
    expect(labels.unit('u-9'), 'u-9');
    expect(labels.taxProfile('t-9'), 't-9');
  });

  test('an empty id stays empty', () {
    expect(labels.product(''), '');
    expect(labels.unit(''), '');
    expect(labels.taxProfile(''), '');
  });

  test('with no lists at all the ids are shown, as the views did before', () {
    const DocumentLineLabels none = DocumentLineLabels();
    expect(none.product('p-1'), 'p-1');
  });

  test('load reads the lists, and a list it cannot read costs only its names',
      () async {
    final DocumentLineLabels loaded =
        await DocumentLineLabels.load(_LabelsApi(labels));
    // Found at 9.7: the sales order view never loaded these at all and
    // printed the product's UUID.
    expect(loaded.product('p-1'), 'DETER1K — Detergent Powder 1kg');
    expect(loaded.unit('u-kg'), 'KG');
    // Tax profiles were refused; their ids come back as themselves.
    expect(loaded.taxProfile('t-18'), 't-18');
  });
}

class _LabelsApi extends ApiClient {
  _LabelsApi(this.source)
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final DocumentLineLabels source;

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
        items: source.products,
        total: source.products.length,
      );

  @override
  Future<List<UomRecord>> uoms({bool includeInactive = false}) async =>
      source.units;

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
      throw const ApiException('Forbidden', statusCode: 403);
}
