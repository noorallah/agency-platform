// The one place a firm can say "a medicine must carry an expiry date", and
// until 2026-08-22 no screen could say it.
//
// An `AttributeDefinition` can be marked mandatory outright, and migration
// `20260815_0087` cleared four that were: EXPIRY_DATE, BATCH_NUMBER,
// MANUFACTURER and IMEI had `mandatory = True` with no category and no profile
// scope, which asked a pharmacy for an IMEI and an electronics distributor for
// an expiry date -- and `AttributeService` refuses the write, so product
// creation was blocked outright on any freshly migrated database. That
// migration cleared them on the understanding that a real requirement would be
// stated in `category_attribute_rules` instead, scoped to a category and
// optionally to one industry. The endpoints existed. Nothing in the desktop
// called them, so for a week nobody could make any attribute mandatory at all.
//
// These pin the screen that closes it: the record carries what the API sends,
// the grid shows names rather than the three UUIDs a rule is made of, and the
// form submits the shape the endpoint expects.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:agency_desktop/ui/workspace/workspace_templates.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Serves the three option lists the form needs and records what it submits.
class _RuleApi extends ApiClient {
  _RuleApi()
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
    if (path.contains('products/categories')) {
      return {
        'data': [
          {'id': 'cat-1', 'code': 'MEDICINE', 'name': 'Medicine'},
        ],
      };
    }
    if (path.contains('attribute-definitions')) {
      return {
        'data': [
          {
            'id': 'attr-1',
            'code': 'EXPIRY_DATE',
            'name': 'Expiry date',
            'entity_type': 'PRODUCT',
            'data_type': 'DATE',
            'mandatory': false,
            'is_active': true,
          },
        ],
      };
    }
    if (path.contains('business-framework/profiles')) {
      return {
        'data': [
          {'id': 'profile-1', 'code': 'PHARMACY', 'name': 'Pharmacy'},
        ],
      };
    }
    return {'data': const <dynamic>[], 'pagination': {'total_records': 0}};
  }
}

PermissionService _permissions() {
  final String claims = base64Url
      .encode(utf8.encode(jsonEncode(<String, dynamic>{
        'roles': <String>['platform-admin'],
        'permissions': <String>['PLATFORM_VIEW', 'PLATFORM_SETTINGS'],
      })))
      .replaceAll('=', '');
  return PermissionService()..applyAccessToken('header.$claims.sig');
}

void main() {
  group('the record carries what the API sends', () {
    test('a rule keeps the names the server resolved for it', () {
      final CategoryAttributeRuleRecord rule =
          CategoryAttributeRuleRecord.fromJson(const {
        'id': 'rule-1',
        'category_code': 'MEDICINE',
        'attribute_definition_id': 'attr-1',
        'attribute_code': 'EXPIRY_DATE',
        'attribute_name': 'Expiry date',
        'business_profile_id': 'profile-1',
        'business_profile_code': 'PHARMACY',
        'is_mandatory': true,
        'validation_override': {'min_days': 30},
      });

      expect(rule.categoryCode, 'MEDICINE');
      expect(rule.attributeName, 'Expiry date');
      expect(rule.businessProfileCode, 'PHARMACY');
      expect(rule.isMandatory, isTrue);
      expect(
        rule.validationOverride,
        {'min_days': 30},
        reason: 'the form cannot edit it, so the record must not drop it',
      );
    });

    test('a rule with no profile reads as one that holds everywhere', () {
      final CategoryAttributeRuleRecord rule =
          CategoryAttributeRuleRecord.fromJson(const {
        'id': 'rule-2',
        'category_code': 'SYRUP',
        'attribute_definition_id': 'attr-1',
        'attribute_code': 'BATCH_NUMBER',
        'attribute_name': 'Batch number',
        'is_mandatory': true,
      });

      expect(rule.businessProfileId, '');
      expect(rule.businessProfileCode, '');
      expect(rule.validationOverride, isNull);
    });

    test('is_mandatory defaults to true, the way the server does', () {
      // The column is `nullable=False, default=True`. A record that read the
      // absence as false would show a rule as not enforced while it is.
      final CategoryAttributeRuleRecord rule =
          CategoryAttributeRuleRecord.fromJson(const {
        'id': 'rule-3',
        'category_code': 'TABLET',
        'attribute_definition_id': 'attr-1',
      });

      expect(rule.isMandatory, isTrue);
    });
  });

  group('the workspace offers the screen', () {
    test('administration declares the tab', () {
      final Set<String> ids = ModuleCatalog.byId(AppModule.administration)
          .tabs
          .map((tab) => tab.id)
          .toSet();

      expect(ids, contains('category-attribute-rules'));
    });

    test('it sits under Business Profiles, beside the attributes it points at',
        () {
      final List<WorkspaceNavigationNode> nodes =
          ModuleCatalog.navigationChildren(
        AppModule.administration,
        <String>{'attribute-definitions', 'category-attribute-rules'},
      );

      Iterable<WorkspaceNavigationNode> flatten(
        Iterable<WorkspaceNavigationNode> input,
      ) sync* {
        for (final WorkspaceNavigationNode node in input) {
          yield node;
          yield* flatten(node.children);
        }
      }

      final Iterable<String> paths =
          flatten(nodes).map((node) => node.path ?? '');

      expect(paths, contains('category-attribute-rules'));
      expect(paths, contains('attribute-definitions'));
    });
  });

  group('the form submits what the endpoint expects', () {
    testWidgets('every id it needs is a picker, not a UUID to be typed',
        (tester) async {
      // Three of the four fields are foreign keys. A text box there is a
      // 422 at best and, for `category_code`, silence: a code matching no
      // category raises nothing and the rule simply never applies.
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1600, 900);
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });
      final _RuleApi api = _RuleApi();

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: ResourceManagementPage<CategoryAttributeRuleRecord>(
            api: api,
            definition: categoryAttributeRuleDefinition(api, _permissions()),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'New').hitTestable());
      await tester.pumpAndSettle();

      expect(find.text('Product category'), findsWidgets);
      expect(find.text('Attribute'), findsWidgets);
      expect(find.text('Limit to business profile'), findsWidgets);
      expect(find.text('Required'), findsWidgets);
      expect(
        find.byType(TextFormField),
        findsNothing,
        reason: 'nothing here is free text -- all four are pickers or a switch',
      );
    });
  });
}
