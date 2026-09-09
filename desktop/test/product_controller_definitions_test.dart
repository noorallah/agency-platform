// The product form reads its custom-field catalogue from the firm-scoped
// endpoint, not the platform one.
//
// `/attribute-definitions` is PlatformPrincipal, so a firm administrator gets
// 403; the desktop swallowed it and left the catalogue empty, so the fields
// the metadata named could not be resolved and the Attributes tab rendered
// "Unknown attribute definition" (docs/BACKLOG.md 24). The controller must ask
// `/attribute-definitions/applicable`, which is gated on firm membership -- the
// same door the customer and vendor forms use.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/uom_packaging.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:flutter_test/flutter_test.dart';

AttributeDefinitionRecord _def(String id, String code) =>
    AttributeDefinitionRecord(
      id: id,
      code: code,
      name: code,
      dataType: 'TEXT',
      entityType: 'PRODUCT',
      mandatory: false,
      isActive: true,
      applicableCategory: 'CORE_PRODUCTS',
      description: '',
      defaultValue: '',
      applicableBusinessProfileId: '',
    );

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  bool rawCatalogueAsked = false;
  bool applicableAsked = false;

  // The platform catalogue: a firm administrator is refused it.
  @override
  Future<PagedResult<AttributeDefinitionRecord>> attributeDefinitions({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) async {
    rawCatalogueAsked = true;
    throw ApiException('platform only', statusCode: 403);
  }

  @override
  Future<ApplicableAttributesRecord> applicableAttributeDefinitions(
    String entityType,
  ) async {
    applicableAsked = true;
    return ApplicableAttributesRecord(
      entityType: entityType,
      definitions: [_def('def-pack', 'PACK_SIZE')],
      mandatoryIds: const [],
    );
  }

  // Everything else bootstrap() touches, kept empty.
  @override
  Future<List<ProductCategoryRecord>> productCategories() async => const [];
  @override
  Future<ProductMetadataRecord> productMetadata({String? categoryId}) async =>
      const ProductMetadataRecord(
        profileCode: 'WHOLESALE',
        features: [],
        categories: [],
        taxProfiles: [],
        requiredAttributeDefinitionIds: [],
        optionalAttributeDefinitionIds: [],
      );
  @override
  Future<List<UomRecord>> uoms({bool includeInactive = false}) async =>
      const [];
  @override
  Future<BusinessProfileUomDefaults?> firmUomDefaults() async => null;
}

void main() {
  test('the catalogue comes from the applicable endpoint, not the platform one',
      () async {
    final _Api api = _Api();
    final ProductController controller = ProductController(api);

    await controller.bootstrap();

    expect(api.applicableAsked, isTrue,
        reason: 'the firm-scoped endpoint is the one a firm admin can read');
    expect(api.rawCatalogueAsked, isFalse,
        reason: 'the platform catalogue 403s for a firm administrator');
    expect(controller.attributeDefinitions.map((d) => d.code), ['PACK_SIZE'],
        reason: 'so the fields the metadata names can be resolved');
  });
}
