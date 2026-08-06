import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/sales_territory.dart';
import 'package:agency_desktop/core/api/api_client.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('assigned firm response retains switcher membership metadata', () {
    final AssignedFirm firm = AssignedFirm.fromJson({
      'id': 'firm-1',
      'code': 'ABC',
      'name': 'ABC Traders',
      'is_primary': true,
    });

    expect(firm.name, 'ABC Traders');
    expect(firm.isPrimary, isTrue);
  });

  test('firm parsing maps the backend FirmResponse fields', () {
    final Firm firm = Firm.fromJson({
      'id': 'firm-1',
      'code': 'ACME',
      'name': 'Acme Agency',
      'gst_number': 'GST-123',
      'pan_number': 'PAN-123',
      'country': 'US',
      'currency_code': 'USD',
      'financial_year_start': '2026-01-01',
      'is_active': false,
    });

    expect(firm.id, 'firm-1');
    expect(firm.gstNumber, 'GST-123');
    expect(firm.currencyCode, 'USD');
    expect(firm.financialYearStart, '2026-01-01');
    expect(firm.isActive, isFalse);
    expect(firm.toJson(), containsPair('currency_code', 'USD'));
  });

  test('role and user parsing matches CRUD response fields', () {
    final Role role = Role.fromJson({
      'id': 'role-1',
      'code': 'manager',
      'name': 'Manager',
    });
    final PlatformUser user = PlatformUser.fromJson({
      'id': 'user-1',
      'email': 'manager@acme.test',
      'full_name': 'Agency Manager',
      'expires_at': '2026-12-31T00:00:00Z',
    });

    expect(role.code, 'manager');
    expect(user.expiresAt, '2026-12-31T00:00:00Z');
  });

  test('auth token parsing accepts a wrapped rotating token response', () {
    final AuthTokens tokens = AuthTokens.fromJson({
      'data': {
        'access_token': 'access',
        'refresh_token': 'rotated-refresh',
        'must_change_password': true,
      },
    });

    expect(tokens.accessToken, 'access');
    expect(tokens.refreshToken, 'rotated-refresh');
    expect(tokens.forcePasswordChange, isTrue);
  });

  test('paged response reads the standard pagination total_records value', () {
    final PagedResult<Permission> page = ApiClient.parsePagedResponse(
      {
        'data': [
          {'id': 'permission-1', 'code': 'users.read', 'name': 'Read users'},
        ],
        'pagination': {'total_records': 41},
      },
      Permission.fromJson,
    );

    expect(page.items.single.code, 'users.read');
    expect(page.total, 41);
  });

  test('primary firm is included in the membership assignment payload', () {
    final Json payload = ApiClient.userFirmAssignmentsPayload(
      ['firm-1'],
      'firm-primary',
    );
    final List<dynamic> assignments = payload['assignments'] as List<dynamic>;

    expect(assignments, hasLength(2));
    expect(
      assignments,
      contains(
        predicate(
          (dynamic assignment) =>
              assignment is Map &&
              assignment['firm_id'] == 'firm-primary' &&
              assignment['is_primary'] == true &&
              assignment['is_active'] == true,
        ),
      ),
    );
  });

  test('customer parsing retains nested master data and financial values', () {
    final Customer customer = Customer.fromJson({
      'id': 'customer-1',
      'firm_id': 'firm-1',
      'code': 'CUST-001',
      'customer_type': 'BUSINESS',
      'name': 'Acme',
      'display_name': 'Acme',
      'credit_limit': '1000.00',
      'opening_balance': '-50.00',
      'payment_terms_days': 30,
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'is_deleted': false,
      'addresses': [
        {
          'id': 'address-1',
          'address_type': 'BILLING',
          'address_line1': 'Main Street',
          'city': 'Chennai',
          'state': 'Tamil Nadu',
          'country': 'IN',
          'postal_code': '600001',
          'is_default_billing': true,
        },
      ],
      'contacts': [
        {'id': 'contact-1', 'name': 'Accounts', 'is_primary': true},
      ],
    });

    expect(customer.city, 'Chennai');
    expect(customer.creditLimit, '1000.00');
    expect(customer.openingBalance, '-50.00');
    expect(customer.contacts.single.isPrimary, isTrue);
  });

  test('business profile framework entities parse from API payloads', () {
    final BusinessProfileRecord profile = BusinessProfileRecord.fromJson({
      'id': 'profile-1',
      'code': 'PHARMACY',
      'name': 'Pharmacy',
      'industry_type': 'PHARMACY',
      'status': 'ACTIVE',
      'is_default': false,
    });
    final BusinessFeatureRecord feature = BusinessFeatureRecord.fromJson({
      'id': 'feature-1',
      'code': 'EXPIRY_TRACKING',
      'name': 'Expiry Tracking',
      'category': 'OPERATIONS',
      'default_enabled': true,
      'is_active': true,
    });
    final BusinessModuleRecord module = BusinessModuleRecord.fromJson({
      'id': 'module-1',
      'code': 'INVENTORY',
      'name': 'Inventory',
      'ui_route': 'inventory',
      'default_enabled': false,
      'is_active': true,
    });
    final AttributeDefinitionRecord attribute =
        AttributeDefinitionRecord.fromJson({
      'id': 'attribute-1',
      'code': 'BATCH_NUMBER',
      'name': 'Batch Number',
      'data_type': 'TEXT',
      'mandatory': true,
      'is_active': true,
      'applicable_category': 'MEDICINE',
    });

    expect(profile.code, 'PHARMACY');
    expect(feature.defaultEnabled, isTrue);
    expect(module.uiRoute, 'inventory');
    expect(attribute.mandatory, isTrue);
  });

  test('product entities parse metadata and dynamic values', () {
    final Product product = Product.fromJson({
      'id': 'product-1',
      'firm_id': 'firm-1',
      'code': 'PROD-1',
      'name': 'Pain Relief',
      'product_type': 'STOCK_ITEM',
      'status': 'ACTIVE',
      'is_deleted': false,
      'attributes': [
        {
          'id': 'attr-value-1',
          'attribute_definition_id': 'attr-1',
          'value_text': '30',
        }
      ],
      'media': [
        {
          'id': 'media-1',
          'media_kind': 'IMAGE',
          'file_name': 'photo.png',
          'storage_path': '/products/photo.png',
          'is_primary': true,
        }
      ],
    });
    final ProductMetadataRecord metadata = ProductMetadataRecord.fromJson({
      'profile_code': 'MEDICAL',
      'features': [
        {'code': 'BARCODE', 'enabled': true}
      ],
      'categories': [
        {
          'id': 'cat-1',
          'code': 'MEDICINE',
          'name': 'Medicine',
          'level': 0,
          'path': 'MEDICINE',
          'is_active': true,
        }
      ],
      'required_attribute_definition_ids': ['attr-1'],
      'optional_attribute_definition_ids': ['attr-2'],
    });

    expect(product.code, 'PROD-1');
    expect(product.attributes.single.valueText, '30');
    expect(product.media.single.isPrimary, isTrue);
    expect(metadata.featureEnabled('BARCODE'), isTrue);
    expect(metadata.categories.single.code, 'MEDICINE');
  });

  test('sales territory entities parse hierarchy, node, and query payloads',
      () {
    final TerritoryHierarchyRecord hierarchy =
        TerritoryHierarchyRecord.fromJson({
      'config_id': 'cfg-1',
      'firm_id': 'firm-1',
      'business_profile_id': 'profile-1',
      'max_levels': 5,
      'allow_multi_route_per_salesman': true,
      'allow_multi_salesman_per_route': false,
      'enforce_customer_leaf_assignment': true,
      'levels': [
        {
          'id': 'lvl-1',
          'level_order': 1,
          'level_code': 'REGION',
          'display_name': 'Region',
          'description': 'Top level',
          'is_mandatory': true,
          'is_enabled': true,
        },
      ],
    });
    final SalesTerritory territory = SalesTerritory.fromJson({
      'id': 'terr-1',
      'firm_id': 'firm-1',
      'business_profile_id': 'profile-1',
      'hierarchy_level_id': 'lvl-1',
      'hierarchy_level_name': 'Region',
      'parent_id': '',
      'code': 'NORTH',
      'name': 'North Region',
      'description': 'Northern zone',
      'status': 'ACTIVE',
      'path': 'North Region',
      'sort_order': 10,
      'customer_count': 12,
      'active_customer_count': 10,
      'inactive_customer_count': 2,
      'new_customer_count': 1,
      'potential_customer_count': 1,
      'salesman_count': 3,
      'route_profile': {
        'route_type_id': 'route-type-1',
        'route_type_name': 'Sales Route',
        'visit_frequency': 'WEEKLY',
        'effective_from': '2026-08-01',
        'effective_to': '2026-12-31',
        'city_id': 'city-1',
        'postal_code_id': 'postal-1',
        'locality_id': 'loc-1',
        'working_days': [1, 4],
      },
      'is_deleted': false,
      'created_at': '2026-08-01T10:00:00Z',
      'updated_at': '2026-08-01T10:00:00Z',
    });
    final TerritoryTreeNodeRecord tree = TerritoryTreeNodeRecord.fromJson({
      'id': 'terr-1',
      'parent_id': '',
      'hierarchy_level_id': 'lvl-1',
      'hierarchy_level_name': 'Region',
      'code': 'NORTH',
      'name': 'North Region',
      'status': 'ACTIVE',
      'path': 'North Region',
      'children': [
        {
          'id': 'terr-2',
          'parent_id': 'terr-1',
          'hierarchy_level_id': 'lvl-2',
          'hierarchy_level_name': 'Route',
          'code': 'R1',
          'name': 'Route 1',
          'status': 'ACTIVE',
          'path': 'North Region > Route 1',
          'children': [],
        },
      ],
    });
    final Map<String, String> query = const TerritoryQuery(
      hierarchyLevelId: 'lvl-1',
      parentId: 'terr-1',
      status: 'ACTIVE',
      salesmanId: 'user-1',
      includeDeleted: true,
    ).toQuery();

    expect(hierarchy.levels.single.displayName, 'Region');
    expect(territory.customerCount, 12);
    expect(territory.routeProfile?.routeTypeName, 'Sales Route');
    expect(tree.children.single.code, 'R1');
    expect(query['include_deleted'], 'true');
    expect(query['salesman_id'], 'user-1');
  });
}
