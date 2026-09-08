import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/vendors/vendor_management_page.dart';
import 'package:agency_desktop/ui/workspace/custom_fields_section.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Custom fields reach the customer and vendor forms.
///
/// The attribute framework stored values for seven entity types and only the
/// product form read or wrote them. Both forms carry a Custom fields tab now,
/// fed by `/attribute-definitions/applicable` for their entity type, and send
/// `attributes` **only once the definitions arrived** -- absent means "leave
/// them alone" on the server, so a form that could not read the fields must
/// not send the empty list that means "clear them".

ApplicableAttributesRecord _applicable({bool mandatory = false}) =>
    ApplicableAttributesRecord.fromJson({
      'entity_type': 'CUSTOMER',
      'definitions': [
        {
          'id': 'def-licence',
          'code': 'DRUG_LICENCE_NO',
          'name': 'Drug licence no',
          'entity_type': 'CUSTOMER',
          'data_type': 'TEXT',
          'mandatory': mandatory,
          'is_active': true,
        },
        {
          'id': 'def-tier',
          'code': 'TIER',
          'name': 'Tier',
          'entity_type': 'CUSTOMER',
          'data_type': 'NUMBER',
          'mandatory': false,
          'is_active': true,
        },
      ],
      'mandatory_ids': [if (mandatory) 'def-licence'],
    });

Json _customerJson({List<Json> attributes = const []}) => {
      'id': 'cust-1',
      'code': 'C001',
      'name': 'Shop One',
      'display_name': 'Shop One',
      'customer_type': 'BUSINESS',
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'attributes': attributes,
    };

Future<List<GeoPlaceRecord>> _noPlaces(GeoLevel level, {String parentId = ''}) async =>
    const [];

Future<Json?> _openCustomer(
  WidgetTester tester, {
  Future<ApplicableAttributesRecord> Function()? loadAttributes,
  List<Json> stored = const [],
  Future<void> Function(WidgetTester tester)? act,
}) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  Json? saved;
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: CustomerWorkspaceDialog(
        mode: CustomerDialogMode.edit,
        customer: Customer.fromJson(_customerJson(attributes: stored)),
        loadPlaces: _noPlaces,
        loadAttributes: loadAttributes,
        onSave: (payload) async {
          saved = payload;
          return Customer.fromJson(_customerJson());
        },
      ),
    ),
  ));
  await tester.pumpAndSettle();
  if (act != null) await act(tester);
  await tester.tap(find.widgetWithText(FilledButton, 'Save'));
  await tester.pumpAndSettle();
  return saved;
}

void main() {
  group('the controller', () {
    test('answers only the filled fields, and validates the mandatory ones',
        () async {
      final CustomFieldsController controller = CustomFieldsController(
        load: () async => _applicable(mandatory: true),
      );
      expect(controller.canSend, isFalse, reason: 'nothing read yet');
      await controller.start();
      expect(controller.canSend, isTrue);
      expect(controller.validate(), 'Drug licence no is required.');

      controller.controllers['def-licence']!.text.text = 'DL-4471';
      expect(controller.validate(), isNull);
      expect(controller.payload(), [
        {'attribute_definition_id': 'def-licence', 'value': 'DL-4471'},
      ]);
      controller.dispose();
    });

    test('seeds the fields from the stored values', () async {
      final CustomFieldsController controller = CustomFieldsController(
        load: () async => _applicable(),
        stored: [
          AttributeValueRecord.fromJson(const {
            'id': 'v-1',
            'attribute_definition_id': 'def-tier',
            'value_number': '2',
          }),
        ],
      );
      await controller.start();
      expect(controller.controllers['def-tier']!.text.text, '2');
      controller.dispose();
    });

    test('a failed read leaves the form with nothing to send', () async {
      final CustomFieldsController controller = CustomFieldsController(
        load: () async => throw const ApiException('down', statusCode: 503),
      );
      await controller.start();
      expect(controller.canSend, isFalse);
      expect(controller.error, 'down');
      controller.dispose();
    });
  });

  group('the customer form', () {
    testWidgets('carries a Custom fields tab and sends what was typed',
        (tester) async {
      final Json? saved = await _openCustomer(
        tester,
        loadAttributes: () async => _applicable(),
        act: (tester) async {
          await tester.tap(find.text('Custom fields'));
          await tester.pumpAndSettle();
          await tester.enterText(
            find.byKey(const ValueKey('attribute-def-licence')),
            'DL-4471',
          );
        },
      );

      expect(saved!['attributes'], [
        {'attribute_definition_id': 'def-licence', 'value': 'DL-4471'},
      ]);
    });

    testWidgets('shows the stored value and sends it back unchanged',
        (tester) async {
      final Json? saved = await _openCustomer(
        tester,
        loadAttributes: () async => _applicable(),
        stored: const [
          {
            'id': 'v-1',
            'attribute_definition_id': 'def-licence',
            'value_text': 'DL-9',
          },
        ],
      );
      expect(saved!['attributes'], [
        {'attribute_definition_id': 'def-licence', 'value': 'DL-9'},
      ]);
    });

    testWidgets('a missing mandatory field stops the save and says which',
        (tester) async {
      final Json? saved = await _openCustomer(
        tester,
        loadAttributes: () async => _applicable(mandatory: true),
      );
      expect(saved, isNull);
      expect(find.text('Drug licence no is required.'), findsOneWidget);
    });

    testWidgets('a failed read sends no attributes at all', (tester) async {
      // Absent means "leave them alone"; an empty list would clear them.
      final Json? saved = await _openCustomer(
        tester,
        loadAttributes: () async =>
            throw const ApiException('down', statusCode: 503),
      );
      expect(saved, isNotNull);
      expect(saved!.containsKey('attributes'), isFalse);
    });

    testWidgets('without a loader there is no tab', (tester) async {
      await _openCustomer(tester);
      expect(find.text('Custom fields'), findsNothing);
    });
  });

  group('the vendor form', () {
    testWidgets('carries a Custom fields tab and sends what was typed',
        (tester) async {
      final _VendorApi api = _VendorApi();
      tester.view.physicalSize = const Size(1600, 1200);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: VendorManagementPage(
            api: api,
            permissions: _permissions(),
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

      // The seventh tab of a scrollable strip sits past the dialog's edge.
      await tester.ensureVisible(find.text('Custom fields'));
      await tester.tap(find.text('Custom fields'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const ValueKey('attribute-def-vtier')),
        '2',
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(api.saved!['attributes'], [
        {'attribute_definition_id': 'def-vtier', 'value': '2'},
      ]);
    });
  });
}

PermissionService _permissions() {
  final String payload = base64Url.encode(utf8.encode(jsonEncode({
    'permissions': ['VENDOR_VIEW', 'VENDOR_CREATE', 'VENDOR_UPDATE'],
  })));
  return PermissionService()..applyAccessToken('h.$payload.s');
}

Json _vendorJson() => {
      'id': 'vendor-1',
      'code': 'V001',
      'name': 'Supplier One',
      'display_name': 'Supplier One',
      'status': 'ACTIVE',
      'gst_registration': false,
      'business_attributes': <String, dynamic>{},
    };

class _VendorApi extends ApiClient {
  _VendorApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? saved;

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async =>
      PagedResult<Vendor>(items: [Vendor.fromJson(_vendorJson())], total: 1);

  @override
  Future<List<AssignmentOption>> options(String resource) async => const [];

  @override
  Future<ApplicableAttributesRecord> applicableAttributeDefinitions(
    String entityType,
  ) async =>
      ApplicableAttributesRecord.fromJson({
        'entity_type': entityType,
        'definitions': [
          {
            'id': 'def-vtier',
            'code': 'SUPPLIER_TIER',
            'name': 'Supplier tier',
            'entity_type': 'VENDOR',
            'data_type': 'NUMBER',
            'mandatory': false,
            'is_active': true,
          },
        ],
        'mandatory_ids': const [],
      });

  @override
  Future<Vendor> updateVendor(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    saved = data;
    return Vendor.fromJson(_vendorJson());
  }
}
