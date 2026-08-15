// The attribute definition update endpoint replaces the whole record, so any
// column the form does not send reverts to its default. The form carried seven
// of eleven and hardcoded two of those to '', so saving an edit wiped the
// description and default value, reset `entity_type` to PRODUCT, and cleared
// `applicable_business_profile_id` — quietly turning a pharmacy-only field
// into one every industry sees.
//
// It also offered `data_type` and `applicable_category` as free text. A bad
// data type is answered with a 422; a mistyped category matches no product
// category and raises nothing at all, so the field simply never applies.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Row {
  const _Row(this.id, this.code);
  final String id, code;
}

/// Serves product categories and records what the form submits.
class _FormApi extends ApiClient {
  _FormApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> writes = <Json>[];

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
    if (method == 'POST') {
      writes.add(Map<String, dynamic>.from(body ?? const <String, dynamic>{}));
      return {'data': body};
    }
    if (path.contains('categories')) {
      return {
        'data': [
          {'id': 'cat-1', 'code': 'MEDICINE', 'name': 'Medicine'},
        ],
      };
    }
    return {'data': const <dynamic>[], 'pagination': {'total_records': 0}};
  }
}

ResourceDefinition<_Row> _formDefinition() => ResourceDefinition<_Row>(
      title: 'Things',
      resource: 'things',
      showFrame: false,
      headers: const ['Code'],
      cells: (row) => [row.code],
      id: (row) => row.id,
      load: ({int page = 1, String search = '', String? sortBy,
              bool descending = false,
              Map<String, String?> filters = const {}}) async =>
          const PagedResult<_Row>(items: <_Row>[], total: 0),
      fields: const [
        FieldSpec(key: 'code', label: 'Attribute code', required: true),
        FieldSpec(
          key: 'data_type',
          label: 'Data type',
          required: true,
          choices: ['TEXT', 'NUMBER', 'DATE', 'BOOLEAN'],
        ),
        FieldSpec(
          key: 'applicable_category',
          label: 'Limit to product category',
          optionsResource: 'products/categories',
          singleSelection: true,
          submitsCode: true,
        ),
      ],
      initialValues: (row) => const {'data_type': 'TEXT'},
      payload: (values, isCreating) => {
        'code': values['code'],
        'data_type': values['data_type'],
        'applicable_category': values['applicable_category'],
      },
    );

Future<void> _openCreateForm(WidgetTester tester, _FormApi api) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1600, 900);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: ResourceManagementPage<_Row>(api: api, definition: _formDefinition()),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.widgetWithText(FilledButton, 'New').hitTestable());
  await tester.pumpAndSettle();
}

void main() {
  group('the record carries every column the API sends', () {
    test('a definition round-trips the fields the edit form used to drop', () {
      final AttributeDefinitionRecord record =
          AttributeDefinitionRecord.fromJson(const {
        'id': 'attr-1',
        'code': 'DRUG_LICENSE_NUMBER',
        'name': 'Drug licence number',
        'description': 'The licence printed on the pack.',
        'entity_type': 'VENDOR',
        'data_type': 'TEXT',
        'mandatory': true,
        'default_value': 'NA',
        'validation_rule': {'max_length': 20},
        'applicable_category': 'MEDICINE',
        'applicable_business_profile_id': 'profile-pharmacy',
        'is_active': true,
      });

      expect(record.description, 'The licence printed on the pack.');
      expect(record.defaultValue, 'NA');
      expect(
        record.entityType,
        'VENDOR',
        reason: 'an omitted entity_type reverts the record to PRODUCT',
      );
      expect(
        record.applicableBusinessProfileId,
        'profile-pharmacy',
        reason: 'losing this un-scopes the field to every industry',
      );
      expect(record.validationRule, {'max_length': 20});
    });

    test('absent optional fields read as empty rather than throwing', () {
      final AttributeDefinitionRecord record =
          AttributeDefinitionRecord.fromJson(const {
        'id': 'attr-2',
        'code': 'COLOR',
        'name': 'Colour',
        'entity_type': 'PRODUCT',
        'data_type': 'TEXT',
        'mandatory': false,
        'is_active': true,
      });

      expect(record.description, '');
      expect(record.defaultValue, '');
      expect(record.applicableBusinessProfileId, '');
      expect(record.applicableCategory, '');
      expect(record.validationRule, isNull);
    });
  });

  group('the form offers valid values instead of a free text box', () {
    testWidgets('data type is a dropdown of the four the server accepts',
        (tester) async {
      await _openCreateForm(tester, _FormApi());

      final Finder dropdown = find.ancestor(
        of: find.text('Data type'),
        matching: find.byType(DropdownButtonFormField<String>),
      );
      expect(dropdown, findsOneWidget);

      await tester.tap(dropdown);
      await tester.pumpAndSettle();
      for (final String type in ['TEXT', 'NUMBER', 'DATE', 'BOOLEAN']) {
        expect(find.text(type), findsWidgets, reason: '\$type must be offered');
      }
    });

    testWidgets('a chosen category submits its code, not its id',
        (tester) async {
      final _FormApi api = _FormApi();
      await _openCreateForm(tester, api);

      await tester.enterText(
          find.widgetWithText(TextFormField, 'Attribute code'), 'SHADE');
      // The category is offered as a chip labelled with its code.
      await tester.tap(find.widgetWithText(FilterChip, 'MEDICINE'));
      await tester.pumpAndSettle();
      final Finder save = find.text('Save & Close');
      await tester.ensureVisible(save);
      await tester.pumpAndSettle();
      await tester.tap(save);
      await tester.pumpAndSettle();

      expect(api.writes, hasLength(1));
      expect(
        api.writes.single['applicable_category'],
        'MEDICINE',
        reason: 'an id here matches no category and never applies',
      );
      expect(api.writes.single['applicable_category'], isNot('cat-1'));
    });
  });
}
