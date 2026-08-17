// No screen may ask a list endpoint for more than it will serve.
//
// `MAX_PAGE_SIZE` is 100 and it is **refused, not clamped** — on the routers
// that build their pagination by hand it comes back as a 500. The New Purchase
// Order form asked for `pageSize: 200` of warehouses and `pageSize: 500` of
// products, both of which failed against every real server; and because the six
// lookups shared one `Future.wait`, which fails fast, the four healthy ones were
// abandoned too. The result on screen was a form with **no vendor and no branch
// to choose**, even though those two requests had succeeded.
//
// This stayed green for the life of the project because every test fake ignores
// `pageSize` and answers whatever it likes. So these tests do the one thing the
// fakes never did: refuse an over-sized page the way the server does.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/workspace/paged_fetch.dart';
import 'package:flutter_test/flutter_test.dart';

/// A client that behaves like the real server: over the cap is a 500.
class _StrictApi extends ApiClient {
  _StrictApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<int> requestedPageSizes = <int>[];

  void _reject(int pageSize) {
    requestedPageSizes.add(pageSize);
    if (pageSize > maxApiPageSize) {
      throw const ApiException(
        'An unexpected error occurred.',
        statusCode: 500,
      );
    }
  }

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async {
    _reject(pageSize);
    return const PagedResult<Vendor>(items: <Vendor>[], total: 0);
  }

  @override
  Future<PagedResult<BranchRecord>> branches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BranchQuery filters = const BranchQuery(),
  }) async {
    _reject(pageSize);
    return const PagedResult<BranchRecord>(
      items: <BranchRecord>[],
      total: 0,
    );
  }

  @override
  Future<PagedResult<WarehouseRecord>> warehouses({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    WarehouseQuery filters = const WarehouseQuery(),
  }) async {
    _reject(pageSize);
    return const PagedResult<WarehouseRecord>(
      items: <WarehouseRecord>[],
      total: 0,
    );
  }

  @override
  Future<PagedResult<Product>> products({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    ProductQuery filters = const ProductQuery(),
  }) async {
    _reject(pageSize);
    return const PagedResult<Product>(items: <Product>[], total: 0);
  }
}

void main() {
  test('the cap this platform actually serves', () {
    // Mirrors MAX_PAGE_SIZE in backend/app/core/constants/core.py.
    expect(maxApiPageSize, 100);
  });

  test('fetchAllPages never asks for more than the cap', () async {
    final _StrictApi api = _StrictApi();

    final List<Product> products = await fetchAllPages(
      (page) => api.products(page: page, pageSize: maxApiPageSize),
    );

    expect(products, isEmpty);
    expect(api.requestedPageSizes.every((size) => size <= maxApiPageSize), isTrue);
  });

  test('an over-sized page is refused, which is the defect', () async {
    // Not a hypothetical: this is exactly what the purchase form sent.
    final _StrictApi api = _StrictApi();

    await expectLater(
      api.warehouses(page: 1, pageSize: 200),
      throwsA(isA<ApiException>()),
    );
    await expectLater(
      api.products(page: 1, pageSize: 500),
      throwsA(isA<ApiException>()),
    );
  });

  test('one failing lookup must not abandon the others', () async {
    // The second half of the defect. `Future.wait` rejects on the first
    // failure and drops the rest, so a single bad request emptied six
    // dropdowns. Reading them independently keeps what succeeded.
    final _StrictApi api = _StrictApi();

    Future<List<T>> lookup<T>(Future<List<T>> Function() read) async {
      try {
        return await read();
      } on ApiException {
        return <T>[];
      }
    }

    final List<Vendor> vendors = await lookup(
      () => fetchAllPages((page) => api.vendors(page: page)),
    );
    final List<Product> overSized = await lookup(
      () async => (await api.products(page: 1, pageSize: 500)).items,
    );

    // The bad one yields nothing; the good one still answered.
    expect(overSized, isEmpty);
    expect(api.requestedPageSizes, contains(500));
    expect(vendors, isEmpty);

    // Fail-fast is what this replaced: proven, not assumed.
    await expectLater(
      Future.wait<dynamic>([
        api.vendors(page: 1),
        api.products(page: 1, pageSize: 500),
      ]),
      throwsA(isA<ApiException>()),
    );
  });
}
