// A named bundle of roles for one job, and the button that applies it.
//
// A route with a client method and no button is the hole this repo has been
// caught by before: `test_routes_have_a_caller.py` counts a call in
// `api_client.dart` as a caller, so six features merged in #185–#194 had a
// backend, a client method and nothing a person could press. These pin the
// control itself.
//
// The dialog also carries two shapes that were written wrongly twice in one
// afternoon before `askForReason` existed: it owns everything it builds, and
// its content is bounded in both dimensions, because an `AlertDialog` gives
// its content unbounded height and a stretched Column with no width overflows
// by tens of thousands of pixels instead of laying out.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/administration/apply_template_dialog.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:agency_desktop/ui/workspace/module_visibility.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _token(Map<String, dynamic> claims) =>
    'h.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.s';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(
    _token({
      'permissions': const <String>[],
      'roles': const <String>[],
      'firm_permissions': {'firm-1': codes},
    }),
    activeFirmId: 'firm-1',
  );

Json _template({
  String id = 't-1',
  String code = 'counter-sales',
  String name = 'Counter Sales',
  List<String> roleCodes = const ['BILLING_EXECUTIVE', 'CASHIER'],
  bool isActive = true,
  bool isSystem = true,
}) =>
    {
      'id': id,
      'code': code,
      'name': name,
      'description': 'Takes payment and raises the bill at the counter.',
      'firm_id': isSystem ? null : 'firm-1',
      'is_active': isActive,
      'is_system': isSystem,
      'role_ids': [for (int i = 0; i < roleCodes.length; i++) 'r-$i'],
      'role_codes': roleCodes,
    };

class _Api extends ApiClient {
  _Api({this.templates = const <Json>[]})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> templates;
  final List<String> applied = <String>[];

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
    if (path.startsWith('/api/v1/user-templates')) {
      return {
        'success': true,
        'data': templates,
        'pagination': {'total_records': templates.length},
      };
    }
    if (path.contains('/apply-template')) {
      applied.add('$path:${body?['template_id']}');
      return {'success': true, 'data': <String>[]};
    }
    return {'success': true, 'data': <String>[]};
  }
}

/// Open the picker and return the sink its result lands in.
///
/// A sink rather than a return value: the helper returns as soon as the dialog
/// is on screen, which is long before anybody has chosen anything, so reading
/// the future here would only ever see null.
Future<List<UserTemplate?>> _open(WidgetTester tester, _Api api) async {
  final List<UserTemplate?> chosen = <UserTemplate?>[];
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () async => chosen.add(
              await pickUserTemplate(context, api, personName: 'Asha'),
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  return chosen;
}

void main() {
  group('the template picker', () {
    testWidgets('offers each job and says what it grants', (tester) async {
      // A template chosen by name alone is a permission decision made blind.
      final _Api api = _Api(templates: [
        _template(),
        _template(id: 't-2', code: 'warehouse', name: 'Warehouse',
            roleCodes: const ['INVENTORY_MANAGER']),
      ]);

      await _open(tester, api);

      expect(find.text('Counter Sales'), findsOneWidget);
      expect(find.text('BILLING_EXECUTIVE, CASHIER'), findsOneWidget);
      expect(find.text('Warehouse'), findsOneWidget);
      expect(find.text('INVENTORY_MANAGER'), findsOneWidget);
    });

    testWidgets('says the roles are replaced, and editable afterwards',
        (tester) async {
      // The decision behind the whole feature: a template is where an
      // administrator starts, not somewhere the user stays. Somebody pressing
      // Apply should not have to discover that from the audit log.
      await _open(tester, _Api(templates: [_template()]));

      expect(
        find.textContaining('replaced'),
        findsOneWidget,
        reason: 'applying replaces what the person holds; say so',
      );
      expect(find.textContaining('edit them afterwards'), findsOneWidget);
    });

    testWidgets('Apply is dead until a job is chosen', (tester) async {
      await _open(tester, _Api(templates: [_template()]));

      final FilledButton apply = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Apply'),
      );
      expect(apply.onPressed, isNull);

      await tester.tap(find.text('Counter Sales'));
      await tester.pumpAndSettle();

      final FilledButton armed = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Apply'),
      );
      expect(armed.onPressed, isNotNull);
    });

    testWidgets('a dismissal chooses nothing', (tester) async {
      final List<UserTemplate?> chosen =
          await _open(tester, _Api(templates: [_template()]));
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      expect(chosen, [isNull]);
    });

    testWidgets('a retired job is not offered', (tester) async {
      // It stays on the templates screen, where retiring it is the point. It
      // has no business being offered to hire into.
      final _Api api = _Api(templates: [
        _template(),
        _template(id: 't-2', code: 'old-job', name: 'Old Job', isActive: false),
      ]);

      await _open(tester, api);

      expect(find.text('Counter Sales'), findsOneWidget);
      expect(find.text('Old Job'), findsNothing);
    });

    testWidgets('no templates at all says so rather than showing an empty box',
        (tester) async {
      await _open(tester, _Api());

      expect(find.text('No job templates are available.'), findsOneWidget);
    });

    testWidgets('choosing a job returns it, and the caller can apply it',
        (tester) async {
      final _Api api = _Api(templates: [_template()]);

      final List<UserTemplate?> chosen = await _open(tester, api);
      await tester.tap(find.text('Counter Sales'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Apply'));
      await tester.pumpAndSettle();

      expect(chosen.single?.id, 't-1');
      expect(chosen.single?.roleCodes, ['BILLING_EXECUTIVE', 'CASHIER']);
      // And the call the workspace then makes reaches the right route.
      await api.applyUserTemplate('u-1', chosen.single!.id);
      expect(api.applied, ['/api/v1/users/u-1/apply-template:t-1']);
    });
  });

  group('the templates screen is reachable', () {
    test('the Administration module offers a User Templates tab', () {
      // The half the orphan-route guard cannot see: a route can have a caller
      // in `api_client.dart` while no screen reaches it.
      final ModuleDefinition administration =
          ModuleCatalog.byId(AppModule.administration);
      final ModuleTabDefinition tab = administration.tabs.firstWhere(
        (candidate) => candidate.id == 'user-templates',
        orElse: () => throw StateError('no user-templates tab'),
      );

      expect(tab.label, 'User Templates');
      // A template is a bundle of roles, so the screen is useless without the
      // role list beside it.
      expect(tab.requiredPermissions, contains('ROLE_VIEW'));
    });

    test('somebody who may see roles is offered it', () {
      final ModuleVisibility view = ModuleVisibility(
        permissions: _permissions(const ['USER_VIEW', 'ROLE_VIEW']),
      );
      final ModuleDefinition administration =
          ModuleCatalog.byId(AppModule.administration);

      expect(view.allows(administration), isTrue);
      expect(view.tabIds(administration), contains('user-templates'));
    });

    test('somebody who may not see roles is not', () {
      final ModuleVisibility view = ModuleVisibility(
        permissions: _permissions(const ['USER_VIEW']),
      );

      expect(
        view.tabIds(ModuleCatalog.byId(AppModule.administration)),
        isNot(contains('user-templates')),
      );
    });
  });
}
