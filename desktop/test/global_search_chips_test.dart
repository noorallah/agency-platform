import 'package:agency_desktop/ui/workspace/global_search.dart';
import 'package:flutter_test/flutter_test.dart';

/// The categories `SearchCategory` in `backend/app/search/schemas.py` accepts.
/// The backend's `test_search_chips_name_categories_the_server_accepts` reads
/// the chip table against the real schema; this is the desktop's half.
const Set<String> serverCategories = {
  'all',
  'masters',
  'inventory',
  'tax',
  'organization',
};

void main() {
  test('every chip asks a category the server accepts', () {
    // Fourteen chips were offered and six sent a category the server refused
    // with 422; the shell then fell back to an inventory search, so
    // "Customers" answered with stock rows (D-RPT-5).
    for (final GlobalSearchCategory category in GlobalSearchCategory.values) {
      expect(serverCategories, contains(category.wire.category),
          reason: '${category.label} sends ${category.wire.category}');
    }
  });

  test('a chip finer than a category names the types that narrow it', () {
    expect(GlobalSearchCategory.customers.wire.entityTypes, ['customers']);
    expect(GlobalSearchCategory.vendors.wire.entityTypes, ['vendors']);
    expect(GlobalSearchCategory.all.wire.entityTypes, isEmpty);
    expect(GlobalSearchCategory.documents.wire.entityTypes,
        contains('sales_invoices'));
  });
}
