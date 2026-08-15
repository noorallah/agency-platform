import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/uom/profile_uom_defaults_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A profile's default units are seeded once for every firm on that profile and
/// overridden per firm, so the form's first job is to say which of the two it
/// is showing. Saving always writes the firm's own row, and telling a user they
/// are editing PHARMACY's units when they are editing their own would be a lie
/// about who the change reaches.

String _accessToken(Map<String, dynamic> claims) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '');
  return 'header.$payload.signature';
}

PermissionService _withPermissions(List<String> permissions) {
  final PermissionService service = PermissionService();
  service.applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': permissions,
  }));
  return service;
}

class _DefaultsApi extends ApiClient {
  _DefaultsApi({this.firmId, this.hasDefaults = true})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// Null models the profile-wide row a firm inherits.
  final String? firmId;
  final bool hasDefaults;
  final List<Json> writes = <Json>[];
  final List<Map<String, String>> queries = <Map<String, String>>[];

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
    if (method == 'PUT') {
      writes.add(Map<String, dynamic>.from(body ?? const <String, dynamic>{}));
      queries.add(Map<String, String>.from(query ?? const <String, String>{}));
      return <String, dynamic>{
        'success': true,
        'data': <String, dynamic>{
          ...?body,
          'business_profile_id': 'profile-1',
          'firm_id': 'firm-1',
        },
      };
    }
    if (path.contains('/uoms')) {
      return <String, dynamic>{
        'success': true,
        'data': <dynamic>[
          <String, dynamic>{
            'id': 'uom-strip',
            'code': 'STRIP',
            'name': 'Strip',
            'symbol': 'strip',
            'dimension': 'COUNT',
            'status': 'ACTIVE',
            'is_decimal_allowed': false,
          },
          <String, dynamic>{
            'id': 'uom-box',
            'code': 'BOX',
            'name': 'Box',
            'symbol': 'box',
            'dimension': 'COUNT',
            'status': 'ACTIVE',
            'is_decimal_allowed': false,
          },
        ],
      };
    }
    return <String, dynamic>{
      'success': true,
      'data': hasDefaults
          ? <String, dynamic>{
              'id': 'default-1',
              'business_profile_id': 'profile-1',
              'firm_id': firmId,
              'base_uom_id': 'uom-strip',
              'inventory_uom_id': 'uom-strip',
              'purchase_uom_id': 'uom-box',
              'sales_uom_id': 'uom-strip',
              'allow_fraction': false,
              'allow_decimal': false,
            }
          : null,
    };
  }
}

Future<void> _open(
  WidgetTester tester,
  _DefaultsApi api,
  PermissionService permissions,
) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: ProfileUomDefaultsDialog(
          api: api,
          permissions: permissions,
          profileId: 'profile-1',
          profileName: 'PHARMACY',
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('an inherited default says it belongs to the profile',
      (tester) async {
    await _open(
      tester,
      _DefaultsApi(firmId: null),
      _withPermissions(['UOM_VIEW', 'CONVERSION_RULE_MANAGE']),
    );

    expect(find.textContaining('come with this profile'), findsOneWidget);
    expect(find.textContaining("this firm's own defaults"), findsNothing);
  });

  testWidgets("a firm's own override says so", (tester) async {
    await _open(
      tester,
      _DefaultsApi(firmId: 'firm-1'),
      _withPermissions(['UOM_VIEW', 'CONVERSION_RULE_MANAGE']),
    );

    expect(find.textContaining("this firm's own defaults"), findsOneWidget);
    expect(find.textContaining('come with this profile'), findsNothing);
  });

  testWidgets('a profile with nothing set offers to set it', (tester) async {
    await _open(
      tester,
      _DefaultsApi(hasDefaults: false),
      _withPermissions(['UOM_VIEW', 'CONVERSION_RULE_MANAGE']),
    );

    expect(find.textContaining('default units yet'), findsOneWidget);
  });

  testWidgets('saving sends every unit slot and both switches',
      (tester) async {
    final _DefaultsApi api = _DefaultsApi(firmId: null);
    await _open(
      tester,
      api,
      _withPermissions(['UOM_VIEW', 'CONVERSION_RULE_MANAGE']),
    );

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.writes, hasLength(1));
    final Json sent = api.writes.single;
    // The inherited values are sent back verbatim, which is what makes
    // "save without editing" mean "adopt the profile's units as ours".
    expect(sent['base_uom_id'], 'uom-strip');
    expect(sent['purchase_uom_id'], 'uom-box');
    expect(sent['sales_uom_id'], 'uom-strip');
    expect(sent['inventory_uom_id'], 'uom-strip');
    expect(sent['allow_decimal'], isFalse);
    expect(sent['allow_fraction'], isFalse);
  });

  testWidgets('viewing does not imply changing', (tester) async {
    final _DefaultsApi api = _DefaultsApi(firmId: null);

    await _open(tester, api, _withPermissions(['UOM_VIEW']));

    expect(find.textContaining('manage conversion rules'), findsOneWidget);
    final FilledButton save = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Save'),
    );
    expect(save.onPressed, isNull);
    expect(api.writes, isEmpty);
  });

  testWidgets('the units are not presented as already in force',
      (tester) async {
    await _open(
      tester,
      _DefaultsApi(firmId: 'firm-1'),
      _withPermissions(['UOM_VIEW', 'CONVERSION_RULE_MANAGE']),
    );

    // The units pre-fill a new product's form and can still be changed
    // there. Saying so is the difference between a default and a rule.
    expect(find.textContaining('pre-fill'), findsOneWidget);
  });

  testWidgets('a firm admin is not offered the profile-wide switch',
      (tester) async {
    await _open(
      tester,
      _DefaultsApi(firmId: null),
      _withPermissions(['UOM_VIEW', 'CONVERSION_RULE_MANAGE']),
    );

    expect(
      find.text('Save for every firm on this profile'),
      findsNothing,
      reason: 'setting what other firms inherit is not a firm-level decision',
    );
  });

  testWidgets('a platform admin can save for every firm on the profile',
      (tester) async {
    final _DefaultsApi api = _DefaultsApi(firmId: null);
    await _open(
      tester,
      api,
      _withPermissions([
        'UOM_VIEW',
        'CONVERSION_RULE_MANAGE',
        'PLATFORM_SETTINGS',
      ]),
    );

    final Finder toggle = find.text('Save for every firm on this profile');
    await tester.ensureVisible(toggle);
    await tester.pumpAndSettle();
    await tester.tap(toggle);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.writes, hasLength(1));
    expect(api.queries.single['apply_to'], 'PROFILE');
  });

  testWidgets('the switch defaults to off, so a save stays firm-scoped',
      (tester) async {
    final _DefaultsApi api = _DefaultsApi(firmId: null);
    await _open(
      tester,
      api,
      _withPermissions([
        'UOM_VIEW',
        'CONVERSION_RULE_MANAGE',
        'PLATFORM_SETTINGS',
      ]),
    );

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.queries.single['apply_to'], 'FIRM');
  });
}
