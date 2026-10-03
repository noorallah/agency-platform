// MST-8: a firm keeps its own custom fields beside the shared catalogue.
//
// The list carries both; a shared row (null `firm_id`) is read-only to the
// firm, and the grid says so rather than letting the server answer 404.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _FieldsApi extends ApiClient {
  _FieldsApi()
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
    if (path.endsWith('/firm-custom-fields')) {
      return {
        'data': [
          {
            'id': 'shared-1',
            'firm_id': null,
            'code': 'MANUFACTURER',
            'name': 'Manufacturer',
            'entity_type': 'PRODUCT',
            'data_type': 'TEXT',
            'mandatory': false,
            'is_active': true,
          },
          {
            'id': 'own-1',
            'firm_id': 'firm-1',
            'code': 'SHELF_LIFE',
            'name': 'Shelf life',
            'entity_type': 'PRODUCT',
            'data_type': 'NUMBER',
            'mandatory': true,
            'is_active': true,
          },
        ],
      };
    }
    return {'data': const <dynamic>[], 'pagination': {'total_records': 0}};
  }
}

PermissionService _permissions(List<String> codes) {
  final String claims = base64Url
      .encode(utf8.encode(jsonEncode(<String, dynamic>{
        'roles': <String>['user'],
        'permissions': codes,
      })))
      .replaceAll('=', '');
  return PermissionService()..applyAccessToken('header.$claims.sig');
}

Future<void> _open(WidgetTester tester, _FieldsApi api,
    PermissionService permissions) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1600, 900);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: ResourceManagementPage<AttributeDefinitionRecord>(
        api: api,
        definition: firmCustomFieldDefinition(api, permissions),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  test('a record without firm_id is shared; one with it is the firm\'s', () {
    expect(
      AttributeDefinitionRecord.fromJson(
              const {'id': 'a', 'code': 'A', 'firm_id': null})
          .isShared,
      isTrue,
    );
    final AttributeDefinitionRecord own = AttributeDefinitionRecord.fromJson(
        const {'id': 'b', 'code': 'B', 'firm_id': 'firm-1'});
    expect(own.isShared, isFalse);
    expect(own.firmId, 'firm-1');
  });

  test('the tabs are firm-scoped and ask the custom field codes', () {
    final tabs = ModuleCatalog.byId(AppModule.administration)
        .tabs
        .where((tab) => tab.id.startsWith('firm-custom-field'))
        .toList();
    expect(tabs.map((tab) => tab.id),
        containsAll(['firm-custom-fields', 'firm-custom-field-rules']));
    for (final tab in tabs) {
      expect(tab.requiresFirm, isTrue);
      expect(tab.requiredPermissions, ['CUSTOM_FIELD_VIEW']);
    }
  });

  test('a shared field cannot be edited and says why', () {
    final definition = firmCustomFieldDefinition(
        _FieldsApi(), _permissions(['CUSTOM_FIELD_MANAGE']));
    final shared = AttributeDefinitionRecord.fromJson(
        const {'id': 'a', 'code': 'A', 'firm_id': null});
    final own = AttributeDefinitionRecord.fromJson(
        const {'id': 'b', 'code': 'B', 'firm_id': 'firm-1'});
    expect(definition.canEdit!(shared), isFalse);
    expect(definition.editRefusal!(shared),
        'Shared fields are kept by the platform.');
    expect(definition.canEdit!(own), isTrue);
  });

  testWidgets('the grid lists shared and own fields with their owner',
      (tester) async {
    await _open(
        tester, _FieldsApi(), _permissions(['CUSTOM_FIELD_VIEW']));

    for (final String heading in [
      'Code',
      'Name',
      'Applies to',
      'Type',
      'Mandatory',
      'Active',
      'Owner',
    ]) {
      expect(find.text(heading), findsWidgets);
    }
    expect(find.text('MANUFACTURER'), findsOneWidget);
    expect(find.text('SHELF_LIFE'), findsOneWidget);
    expect(find.text('Shared'), findsOneWidget);
    expect(find.text('This firm'), findsOneWidget);
  });

  testWidgets('opening a shared field says the platform keeps it',
      (tester) async {
    await _open(tester, _FieldsApi(),
        _permissions(['CUSTOM_FIELD_VIEW', 'CUSTOM_FIELD_MANAGE']));

    final Finder row = find.text('MANUFACTURER').first;
    await tester.tap(row);
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tap(row);
    await tester.pumpAndSettle();

    expect(find.textContaining('Shared fields are kept by the platform'),
        findsWidgets);
  });

  testWidgets('creating a field posts the body the server declares',
      (tester) async {
    final _FieldsApi api = _FieldsApi();
    await _open(tester, api,
        _permissions(['CUSTOM_FIELD_VIEW', 'CUSTOM_FIELD_MANAGE']));

    await tester.tap(find.widgetWithText(FilledButton, 'New').hitTestable());
    await tester.pumpAndSettle();
    final Finder boxes = find.byType(TextFormField);
    await tester.enterText(boxes.at(0), 'COLOUR');
    await tester.enterText(boxes.at(1), 'Colour');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save & Close').hitTestable());
    await tester.pumpAndSettle();

    expect(api.writes, hasLength(1));
    expect(api.writes.single, {
      'code': 'COLOUR',
      'name': 'Colour',
      'entity_type': 'PRODUCT',
      'data_type': 'TEXT',
      'applicable_category': null,
      'applicable_business_profile_id': null,
      'mandatory': false,
      'description': null,
      'default_value': null,
      'is_active': true,
      'validation_rule': null,
    });
  });
}
