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
    // One editable field per caller, plus the tier they cannot write, shown
    // read-only. Nothing on the form names a firm: the tier picker at create
    // and the second column keyed off the switcher are both gone, and Roles
    // by firm is the only per-firm writer.
    const Set<String> gone = {'firm_role_ids', 'role_firm_id'};

    testWidgets('a platform administrator in platform mode', (tester) async {
      final ResourceDefinition<PlatformUser> d = await _definition(
          tester, _Api(), _perms(platformAdmin: true));

      expect(_securityKeys(d), contains('role_ids'));
      expect(_securityKeys(d), contains('firm_roles_note'));
      expect(_securityKeys(d).intersection(gone), isEmpty);
      expect(_securityKeys(d), isNot(contains('global_roles_note')),
          reason: 'their Roles field already is the global tier');
    });

    testWidgets('a platform administrator working in a firm', (tester) async {
      // The same form. Selecting a firm changes nothing about it -- that
      // coupling is what wrote roles into a tier nobody chose.
      final ResourceDefinition<PlatformUser> d = await _definition(
          tester, _Api(), _perms(platformAdmin: true, activeFirmId: 'firm-1'));

      expect(_securityKeys(d), contains('role_ids'));
      expect(_securityKeys(d), contains('firm_roles_note'));
      expect(_securityKeys(d).intersection(gone), isEmpty);
    });

    testWidgets('a firm administrator', (tester) async {
      final ResourceDefinition<PlatformUser> d = await _definition(
          tester, _Api(), _perms(platformAdmin: false, activeFirmId: 'firm-1'));

      expect(_securityKeys(d), contains('role_ids'),
          reason: 'which for them is their own firm');
      expect(_securityKeys(d), contains('global_roles_note'),
          reason: 'a global grant applies here and they must see it');
      expect(_securityKeys(d).intersection(gone), isEmpty);
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
        ...extra,
      });
      return api.calls;
    }

    testWidgets('platform mode writes memberships and the global tier',
        (tester) async {
      expect(await save(tester, _perms(platformAdmin: true)),
          ['write:memberships', 'write:global']);
    });

    testWidgets('with a firm selected it writes exactly the same',
        (tester) async {
      // The per-firm write this form used to make here is gone. A platform
      // administrator with MEDI01 selected who wants a role in MEDI01 goes
      // to Roles by firm, where the firm is named beside the roles.
      expect(
        await save(tester,
            _perms(platformAdmin: true, activeFirmId: 'firm-1')),
        ['write:memberships', 'write:global'],
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
    testWidgets('each firm is read once, whatever is selected', (tester) async {
      // One read per firm the person belongs to, for the summary, and no
      // second read of the selected firm -- there is no longer a column for
      // it to fill.
      final _Api api = _Api();
      final ResourceDefinition<PlatformUser> d = await _definition(
          tester, api, _perms(platformAdmin: true, activeFirmId: 'firm-1'));

      await d.loadAssignments!('user-1');

      expect(api.calls.where((c) => c.startsWith('read:')),
          ['read:firm-1', 'read:firm-2']);
    });

    testWidgets('the summary names every firm, the selected one included',
        (tester) async {
      // Leaving it out made the summary depend on the switcher. Nothing else
      // on the form shows that firm now, so the summary is the one place.
      final _Api api = _Api();
      final ResourceDefinition<PlatformUser> d = await _definition(
          tester, api, _perms(platformAdmin: true, activeFirmId: 'firm-1'));

      final Map<String, dynamic> values = await d.loadAssignments!('user-1');

      expect(values['firm_roles_note'],
          'WHOLE01: SALES_MANAGER  ·  ELEC01: CASHIER');
      expect(values.containsKey('firm_role_ids'), isFalse);
    });
  });
}
