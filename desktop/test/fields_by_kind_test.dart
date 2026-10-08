// Custom fields tied to a kind of record (a customer group, a supplier type).
//
// A field with no kind rule is always shown. A field with kind rules is shown
// only on a record whose current kind a rule names, and is required there only
// when that rule says so. A hidden field the record already holds a value for
// stays shown, and a hidden field with no stored value is never sent.

import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/workspace/custom_fields_section.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _field(String id, String code) => {
      'id': id,
      'code': code,
      'name': code,
      'entity_type': 'CUSTOMER',
      'data_type': 'TEXT',
      'mandatory': false,
      'is_active': true,
    };

/// FREE is in no rule; TIED_A is tied to group A (required there); TIED_B to
/// group B (optional there); BOTH is tied to both and required on A only.
ApplicableAttributesRecord _answer() => ApplicableAttributesRecord.fromJson({
      'entity_type': 'CUSTOMER',
      'definitions': [
        _field('def-free', 'FREE'),
        _field('def-a', 'TIED_A'),
        _field('def-b', 'TIED_B'),
        _field('def-both', 'BOTH'),
      ],
      'mandatory_ids': const <String>[],
      'kind_rules': [
        {
          'attribute_definition_id': 'def-a',
          'customer_group_id': 'grp-a',
          'is_mandatory': true,
        },
        {
          'attribute_definition_id': 'def-b',
          'customer_group_id': 'grp-b',
          'is_mandatory': false,
        },
        {
          'attribute_definition_id': 'def-both',
          'customer_group_id': 'grp-a',
          'is_mandatory': true,
        },
        {
          'attribute_definition_id': 'def-both',
          'customer_group_id': 'grp-b',
          'is_mandatory': false,
        },
      ],
    });

Future<CustomFieldsController> _started({
  List<AttributeValueRecord> stored = const [],
}) async {
  final CustomFieldsController controller = CustomFieldsController(
    load: () async => _answer(),
    stored: stored,
  );
  await controller.start();
  return controller;
}

List<String> _shown(CustomFieldsController c) =>
    c.visibleDefinitions.map((d) => d.code).toList();

void main() {
  test('kind_rules are read from the answer', () {
    final ApplicableAttributesRecord answer = _answer();
    expect(answer.kindRules, hasLength(4));
    expect(answer.kindRules.first.customerGroupId, 'grp-a');
    expect(answer.kindRules.first.isMandatory, isTrue);
    expect(answer.kindRules.first.vendorTypeId, '');
    expect(
      ApplicableAttributesRecord.fromJson(const {
        'entity_type': 'CUSTOMER',
      }).kindRules,
      isEmpty,
      reason: 'an answer from before kinds has none',
    );
  });

  group('the controller', () {
    test('with no kind only the untied fields are shown', () async {
      final CustomFieldsController c = await _started();
      expect(_shown(c), ['FREE']);
      c.dispose();
    });

    test('group A shows its fields, group B its own, and no group neither',
        () async {
      final CustomFieldsController c = await _started();

      c.setKind(customerGroupId: 'grp-a');
      expect(_shown(c), ['FREE', 'TIED_A', 'BOTH']);

      c.setKind(customerGroupId: 'grp-b');
      expect(_shown(c), ['FREE', 'TIED_B', 'BOTH']);

      c.setKind(customerGroupId: 'grp-other');
      expect(_shown(c), ['FREE']);

      c.setKind(customerGroupId: '');
      expect(_shown(c), ['FREE']);
      c.dispose();
    });

    test('a tied field is required only where its rule says so', () async {
      final CustomFieldsController c = await _started();

      c.setKind(customerGroupId: 'grp-a');
      expect(c.isRequired('def-a'), isTrue);
      expect(c.isRequired('def-both'), isTrue);
      expect(c.isRequired('def-free'), isFalse);
      expect(c.validate(), 'TIED_A is required.');
      c.controllers['def-a']!.text.text = 'x';
      expect(c.validate(), 'BOTH is required.');
      c.controllers['def-both']!.text.text = 'y';
      expect(c.validate(), isNull);

      c.setKind(customerGroupId: 'grp-b');
      expect(c.isRequired('def-b'), isFalse);
      expect(c.isRequired('def-both'), isFalse, reason: 'optional on B');
      expect(c.validate(), isNull, reason: 'TIED_A is hidden, not checked');
      c.dispose();
    });

    test('a hidden field with nothing stored is not sent', () async {
      final CustomFieldsController c = await _started();
      c.setKind(customerGroupId: 'grp-a');
      c.controllers['def-a']!.text.text = 'typed while on A';
      c.controllers['def-free']!.text.text = 'always';

      c.setKind(customerGroupId: 'grp-b');
      expect(c.payload(), [
        {'attribute_definition_id': 'def-free', 'value': 'always'},
      ]);
      c.dispose();
    });

    test('a hidden field the record already holds stays shown and is sent',
        () async {
      final CustomFieldsController c = await _started(stored: [
        AttributeValueRecord.fromJson(const {
          'id': 'v-1',
          'attribute_definition_id': 'def-a',
          'value_text': 'DL-9',
        }),
      ]);

      c.setKind(customerGroupId: 'grp-b');
      expect(_shown(c), contains('TIED_A'));
      expect(c.payload(), [
        {'attribute_definition_id': 'def-a', 'value': 'DL-9'},
      ]);
      expect(c.isRequired('def-a'), isFalse,
          reason: 'its rule names group A, not the record\'s group');
      c.dispose();
    });

    test('a supplier type matches only supplier-type rules', () async {
      final CustomFieldsController c = CustomFieldsController(
        load: () async => ApplicableAttributesRecord.fromJson({
          'entity_type': 'VENDOR',
          'definitions': [_field('def-v', 'IMPORT_CODE')],
          'mandatory_ids': const <String>[],
          'kind_rules': [
            {
              'attribute_definition_id': 'def-v',
              'vendor_type_id': 'vt-import',
              'is_mandatory': true,
            },
          ],
        }),
      );
      await c.start();
      expect(_shown(c), isEmpty);
      c.setKind(customerGroupId: 'vt-import');
      expect(_shown(c), isEmpty, reason: 'a group id is not a type id');
      c.setKind(vendorTypeId: 'vt-import');
      expect(_shown(c), ['IMPORT_CODE']);
      expect(c.isRequired('def-v'), isTrue);
      c.dispose();
    });

    test('a field required whatever the kind stays required', () async {
      final CustomFieldsController c = CustomFieldsController(
        load: () async => ApplicableAttributesRecord.fromJson({
          'entity_type': 'CUSTOMER',
          'definitions': [_field('def-m', 'MUST')],
          'mandatory_ids': const ['def-m'],
        }),
      );
      await c.start();
      expect(c.isRequired('def-m'), isTrue);
      expect(c.validate(), 'MUST is required.');
      c.dispose();
    });
  });

  group('the customer form', () {
    Json customerJson() => {
          'id': 'cust-1',
          'code': 'C001',
          'name': 'Shop One',
          'display_name': 'Shop One',
          'customer_type': 'BUSINESS',
          'currency_code': 'INR',
          'status': 'ACTIVE',
          'addresses': const <Json>[],
          'contacts': const <Json>[],
        };

    Future<Json?> openAndPick(
      WidgetTester tester, {
      required String? pick,
      required Future<void> Function(WidgetTester tester) afterPick,
    }) async {
      tester.view.physicalSize = const Size(1700, 1400);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      int reads = 0;
      Json? saved;
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: CustomerWorkspaceDialog(
            mode: CustomerDialogMode.edit,
            customer: Customer.fromJson(customerJson()),
            loadPlaces: (level, {parentId = ''}) async => const [],
            loadGroups: () async => const [
              CustomerGroup(id: 'grp-a', code: 'A', name: 'Contractors'),
              CustomerGroup(id: 'grp-b', code: 'B', name: 'Retailers'),
            ],
            loadAttributes: () async {
              reads++;
              return _answer();
            },
            onSave: (payload) async {
              saved = payload;
              return Customer.fromJson(customerJson());
            },
          ),
        ),
      ));
      await tester.pumpAndSettle();
      if (pick != null) {
        await tester.tap(find.text('Financial'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Customer group'));
        await tester.pumpAndSettle();
        await tester.tap(find.text(pick).last);
        await tester.pumpAndSettle();
      }
      await tester.tap(find.text('Custom fields'));
      await tester.pumpAndSettle();
      await afterPick(tester);
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();
      expect(reads, 1, reason: 'changing the group makes no second call');
      return saved;
    }

    testWidgets('no group shows only the untied field', (tester) async {
      await openAndPick(tester, pick: null, afterPick: (tester) async {
        expect(find.byKey(const ValueKey('attribute-def-free')), findsOneWidget);
        expect(find.byKey(const ValueKey('attribute-def-a')), findsNothing);
        expect(find.byKey(const ValueKey('attribute-def-b')), findsNothing);
      });
    });

    testWidgets('choosing a group shows its fields and not the other\'s',
        (tester) async {
      await openAndPick(tester, pick: 'Retailers', afterPick: (tester) async {
        expect(find.byKey(const ValueKey('attribute-def-b')), findsOneWidget);
        expect(find.byKey(const ValueKey('attribute-def-a')), findsNothing);
      });
    });

    testWidgets('a field required for the chosen group stops the save',
        (tester) async {
      final Json? saved = await openAndPick(
        tester,
        pick: 'Contractors',
        afterPick: (tester) async {
          expect(find.byKey(const ValueKey('attribute-def-a')), findsOneWidget);
        },
      );
      expect(saved, isNull);
      await tester.tap(find.text('Financial'));
      await tester.pumpAndSettle();
      expect(find.text('TIED_A is required.'), findsOneWidget);
    });

    testWidgets('an optional tied field saves without a value',
        (tester) async {
      final Json? saved = await openAndPick(
        tester,
        pick: 'Retailers',
        afterPick: (tester) async {},
      );
      expect(saved, isNotNull);
      expect(saved!['attributes'], isEmpty);
    });
  });
}
