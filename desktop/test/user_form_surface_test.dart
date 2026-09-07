import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The whole user form, for every caller, asserted in one place.
///
/// This file exists because the alternative was costing more than it was
/// worth. The user form differs by caller in six ways — which role fields
/// appear, which tier each writes, what is read-only, what is refused and
/// whether the refusal speaks — and each difference was found the same way: a
/// person hit it in the running app and reported it, one round trip at a
/// time. A defect in one combination says nothing about the other two, so
/// fixing them singly kept missing their twins: the silent Edit refusal had a
/// silent Delete beside it, untouched, and the read-only tier line was built
/// for one caller and not its mirror.
///
/// So the matrix is asserted rather than inspected. Three callers, and for
/// each: the Security fields, the tiers a save writes to, and the refusals.
PermissionService _perms({
  required bool platformAdmin,
  String? activeFirmId,
  List<String> codes = const [
    'USER_VIEW',
    'USER_CREATE',
    'USER_UPDATE',
    'ROLE_VIEW',
    'ROLE_ASSIGN',
    'PERMISSION_VIEW',
  ],
}) {
  final String payload = base64Url.encode(utf8.encode(jsonEncode({
    // `_issue_tokens` puts every active code in the global claim for a
    // platform administrator; a fixture granting none tests a shape the
    // application never issues.
    'permissions': platformAdmin ? codes : const <String>[],
    'roles': const <String>[],
    'platform_admin': platformAdmin,
    if (platformAdmin) 'platform_admin_scope': 'ALL_FIRMS',
    'firm_permissions': {'firm-1': codes},
  })));
  return PermissionService()
    ..applyAccessToken('h.$payload.s', activeFirmId: activeFirmId);
}

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  /// Every call in order, so a test can assert what a form open costs and
  /// which tier a save reached.
  final List<String> calls = [];

  @override
  Future<List<AssignmentOption>> options(String resource) async =>
      switch (resource) {
        'roles' => const [
            AssignmentOption(id: 'role-sm', label: 'SALES_MANAGER'),
            AssignmentOption(id: 'role-cashier', label: 'CASHIER'),
          ],
        'firms' => const [
            AssignmentOption(id: 'firm-1', label: 'WHOLE01'),
            AssignmentOption(id: 'firm-2', label: 'ELEC01'),
          ],
        _ => const <AssignmentOption>[],
      };

  @override
  Future<Json> userAssignmentValues(String userId) async =>
      {'role_ids': '', 'firm_ids': 'firm-1,firm-2', 'primary_firm_id': 'firm-1'};

  @override
  Future<Map<String, dynamic>> userFirmAssignmentValues(String userId) async =>
      {'firm_ids': 'firm-1,firm-2', 'primary_firm_id': 'firm-1'};

  @override
  Future<List<String>> userGlobalRoles(String userId) async =>
      const ['role-sm'];

  @override
  Future<List<String>> userFirmRoles(String userId, String firmId) async {
    calls.add('read:$firmId');
    return firmId == 'firm-1'
        ? const ['role-sm']
        : const ['role-cashier'];
  }

  @override
  Future<void> setUserRoles(String userId, List<String> ids) async =>
      calls.add('write:global');

  @override
  Future<void> setUserFirmRoles(
          String userId, String firmId, List<String> ids) async =>
      calls.add('write:$firmId');

  @override
  Future<void> setUserFirms(String u, List<String> f, String p) async =>
      calls.add('write:memberships');
}

PlatformUser _user({required bool shared}) => PlatformUser(
      id: 'user-1',
      email: 'someone@example.com',
      fullName: 'Someone',
      isActive: true,
      forcePasswordChange: false,
      expiresAt: '',
      belongsToOtherFirms: shared,
    );

Future<ResourceDefinition<PlatformUser>> _definition(
  WidgetTester tester,
  _Api api,
  PermissionService perms,
) async {
  late ResourceDefinition<PlatformUser> definition;
  // A real `BuildContext`: `userDefinition` omits every dialog-opening action
  // when `context` is null, so a plain `test` would run over an empty action
  // list and pass whatever the gates said.
  await tester.pumpWidget(MaterialApp(
    home: Builder(builder: (context) {
      definition = userDefinition(api, perms, context: context);
      return const SizedBox.shrink();
    }),
  ));
  return definition;
}

Set<String> _securityKeys(ResourceDefinition<PlatformUser> definition) => {
      for (final FieldSpec f in definition.fields)
        if (f.section == 'Security') f.key,
    };

void main() {
  group('the role fields each caller is given', () {
    testWidgets('a platform administrator in platform mode', (tester) async {
      // No firm selected, so there is no second column to fill -- and this is
      // where a platform administrator starts.
      final ResourceDefinition<PlatformUser> d = await _definition(
          tester, _Api(), _perms(platformAdmin: true));

      expect(_securityKeys(d), contains('role_ids'));
      expect(_securityKeys(d), contains('firm_roles_note'));
      expect(_securityKeys(d), isNot(contains('firm_role_ids')));
      expect(_securityKeys(d), isNot(contains('global_roles_note')),
          reason: 'their Roles field already is the global tier');
    });

    testWidgets('a platform administrator working in a firm', (tester) async {
      final ResourceDefinition<PlatformUser> d = await _definition(
          tester, _Api(), _perms(platformAdmin: true, activeFirmId: 'firm-1'));

      expect(_securityKeys(d), contains('role_ids'));
      expect(_securityKeys(d), contains('firm_role_ids'),
          reason: 'the firm they are in is editable here');
      expect(_securityKeys(d), contains('firm_roles_note'));
    });

    testWidgets('a firm administrator', (tester) async {
      final ResourceDefinition<PlatformUser> d = await _definition(
          tester, _Api(), _perms(platformAdmin: false, activeFirmId: 'firm-1'));

      expect(_securityKeys(d), contains('role_ids'),
          reason: 'which for them is their own firm');
      expect(_securityKeys(d), contains('global_roles_note'),
          reason: 'a global grant applies here and they must see it');
      expect(_securityKeys(d), isNot(contains('firm_role_ids')),
          reason: 'that would be their own firm twice');
      expect(_securityKeys(d), isNot(contains('role_firm_id')),
          reason: 'their grant is already scoped; the question has one answer');
    });
  });

  group('what a save writes, per caller', () {
    Future<List<String>> save(
      WidgetTester tester,
      PermissionService perms, {
      Map<String, dynamic> extra = const {},
    }) async {
      final _Api api = _Api();
      final ResourceDefinition<PlatformUser> d =
          await _definition(tester, api, perms);
      final Map<String, dynamic> values = await d.loadAssignments!('user-1');
      api.calls.clear();
      await d.saveAssignments!('user-1', {
        ...values,
        'template_id': '',
        'role_firm_id': '',
        ...extra,
      });
      return api.calls;
    }

    testWidgets('platform mode writes memberships and the global tier',
        (tester) async {
      expect(await save(tester, _perms(platformAdmin: true)),
          ['write:memberships', 'write:global']);
    });

    testWidgets('with a firm selected it also writes that firm',
        (tester) async {
      // The case that failed in the running app: roles added with a firm
      // selected all landed globally, because there was nowhere else to put
      // them.
      expect(
        await save(tester,
            _perms(platformAdmin: true, activeFirmId: 'firm-1')),
        ['write:memberships', 'write:global', 'write:firm-1'],
      );
    });

    testWidgets('a firm administrator writes one tier, scoped server-side',
        (tester) async {
      // `_firm_scope` gives their call their own firm, so the same route
      // means something different for them.
      expect(
        await save(tester,
            _perms(platformAdmin: false, activeFirmId: 'firm-1')),
        ['write:memberships', 'write:global'],
      );
    });
  });

  group('a person who also works in another firm', () {
    testWidgets('every caller refuses to edit them, and says why',
        (tester) async {
      // Their profile is platform-wide. The refusal was silent on three
      // routes -- the disabled button, a double-click on the row, and the
      // context menu -- which reads as a broken screen rather than a rule.
      for (final PermissionService perms in [
        _perms(platformAdmin: true),
        _perms(platformAdmin: true, activeFirmId: 'firm-1'),
        _perms(platformAdmin: false, activeFirmId: 'firm-1'),
      ]) {
        final ResourceDefinition<PlatformUser> d =
            await _definition(tester, _Api(), perms);
        expect(d.canEdit!(_user(shared: true)), isFalse);
        expect(d.editRefusal!(_user(shared: true)), isNotNull);
        expect(d.canEdit!(_user(shared: false)), isTrue);
        expect(d.editRefusal!(_user(shared: false)), isNull);
      }
    });

    testWidgets('the refusal names the way round', (tester) async {
      // There is one, and it is not obvious: the server lets a firm caller
      // set a shared user's roles in their own firm, so the only thing
      // stopping anybody was the door.
      final ResourceDefinition<PlatformUser> d = await _definition(
          tester, _Api(), _perms(platformAdmin: false, activeFirmId: 'firm-1'));

      expect(d.editRefusal!(_user(shared: true)), contains('Roles by firm'));
    });

    testWidgets('Roles by firm stays reachable for them', (tester) async {
      final ResourceDefinition<PlatformUser> d = await _definition(
          tester, _Api(), _perms(platformAdmin: false, activeFirmId: 'firm-1'));
      final ResourceAction<PlatformUser> action = d.customActions
          .firstWhere((a) => a.label == 'Roles by firm');

      expect(action.isEnabled, isNull,
          reason: 'no extra condition, so a shared user is still reachable');
    });
  });

  group('what a form open costs', () {
    testWidgets('the selected firm is read once, not twice', (tester) async {
      // It is both the editable column and a candidate for the read-only
      // summary. Reading it twice was harmless; *listing* it twice was not --
      // the two could disagree the moment either was edited.
      final _Api api = _Api();
      final ResourceDefinition<PlatformUser> d = await _definition(
          tester, api, _perms(platformAdmin: true, activeFirmId: 'firm-1'));

      await d.loadAssignments!('user-1');

      expect(api.calls.where((c) => c == 'read:firm-1'), hasLength(1));
      // The other firm still appears in the summary.
      expect(api.calls, contains('read:firm-2'));
    });

    testWidgets('the summary leaves out the firm being edited',
        (tester) async {
      final _Api api = _Api();
      final ResourceDefinition<PlatformUser> d = await _definition(
          tester, api, _perms(platformAdmin: true, activeFirmId: 'firm-1'));

      final Map<String, dynamic> values = await d.loadAssignments!('user-1');

      expect(values['firm_roles_note'], 'ELEC01: CASHIER');
      expect(values['firm_role_ids'], 'role-sm');
    });
  });
}
