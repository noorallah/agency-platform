import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The user form carries one tier, and the other is shown but not written.
///
/// A platform caller's Roles field is the **global** set: what applies in
/// every firm the person belongs to. A firm caller's is their own firm's set,
/// scoped by the server. Neither form names a firm: a firm-tier role is
/// written under **Roles by firm** and nowhere else. The form used to carry
/// two more writers -- a tier picker at create and a second column keyed off
/// the firm switcher -- and two writers for one row is how a role lands in a
/// tier nobody chose.
///
/// The order still matters. A role needs an active membership -- the token is
/// built per membership, so a grant without one reaches nobody and the service
/// refuses it. Roles used to be written first, while the person was still in
/// no firm.
PermissionService _permissions({
  required bool platformAdmin,
  List<String> codes = const [],
  String? activeFirmId = 'firm-1',
}) {
  final String payload = base64Url.encode(
    utf8.encode(
      jsonEncode({
        // `_issue_tokens` puts **all** active codes in the global claim for a
        // platform administrator, so a fixture granting none tests a shape the
        // application never issues.
        'permissions': platformAdmin ? codes : const <String>[],
        'roles': const <String>[],
        'platform_admin': platformAdmin,
        if (platformAdmin) 'platform_admin_scope': 'ALL_FIRMS',
        'firm_permissions': {'firm-1': codes},
      }),
    ),
  );
  return PermissionService()
    ..applyAccessToken('h.$payload.s', activeFirmId: activeFirmId);
}

class _CreateApi extends ApiClient {
  _CreateApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  /// Every call in the order it was made, so the sequence can be asserted.
  final List<String> calls = [];
  final List<String> templateFirmIds = [];
  final List<String> scopedFirmIds = [];

  @override
  Future<Json> userAssignmentValues(String userId) async => {
        'role_ids': '',
        'firm_ids': 'firm-1,firm-2',
        'primary_firm_id': 'firm-1',
      };

  @override
  Future<Map<String, dynamic>> userFirmAssignmentValues(String userId) async =>
      {'firm_ids': 'firm-1,firm-2', 'primary_firm_id': 'firm-1'};

  @override
  Future<List<String>> userGlobalRoles(String userId) async =>
      globalRoleIds;

  List<String> globalRoleIds = const ['role-admin'];

  /// What each firm holds, for the platform-side summary.
  Map<String, List<String>> firmRoleIds = const {
    'firm-1': ['role-sm'],
    'firm-2': ['role-cashier'],
  };

  @override
  Future<List<String>> userFirmRoles(String userId, String firmId) async =>
      firmRoleIds[firmId] ?? const <String>[];

  @override
  Future<List<AssignmentOption>> options(String resource) async =>
      switch (resource) {
        'roles' => const [
            AssignmentOption(id: 'role-admin', label: 'FIRM_ADMIN'),
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
  Future<void> setUserFirms(
    String userId,
    List<String> firmIds,
    String primaryFirmId,
  ) async {
    calls.add('firms');
  }

  @override
  Future<void> setUserRoles(String userId, List<String> ids) async {
    calls.add('globalRoles');
  }

  @override
  Future<void> setUserFirmRoles(
    String userId,
    String firmId,
    List<String> roleIds,
  ) async {
    calls.add('firmRoles');
    scopedFirmIds.add(firmId);
    scopedRoleIds.add(roleIds.join(','));
  }

  final List<String> scopedRoleIds = [];

  @override
  Future<void> applyUserTemplate(
    String userId,
    String templateId, {
    String firmId = '',
  }) async {
    calls.add('template');
    templateFirmIds.add(firmId);
  }
}

ResourceDefinition<PlatformUser> _definition(
  _CreateApi api, {
  required bool platformAdmin,
  List<String> codes = const ['ROLE_ASSIGN', 'ROLE_VIEW'],
  String? activeFirmId = 'firm-1',
}) =>
    userDefinition(
      api,
      _permissions(
        platformAdmin: platformAdmin,
        codes: codes,
        activeFirmId: activeFirmId,
      ),
    );

FieldSpec? _field(ResourceDefinition<PlatformUser> definition, String key) {
  for (final FieldSpec field in definition.fields) {
    if (field.key == key) return field;
  }
  return null;
}

void main() {
  group('the tier a caller cannot edit is still shown', () {
    test('a firm administrator sees the global grants, read-only', () async {
      // A global grant applies **in their firm**, so a form showing only
      // their own tier reports less than the person can do.
      final _CreateApi api = _CreateApi();
      final ResourceDefinition<PlatformUser> definition =
          _definition(api, platformAdmin: false);

      final FieldSpec? note = _field(definition, 'global_roles_note');
      expect(note, isNotNull);
      expect(note!.alwaysReadOnly, isTrue);
      expect(note.editOnly, isTrue);

      final Map<String, dynamic> values =
          await definition.loadAssignments!('user-1');
      expect(values['global_roles_note'], 'FIRM_ADMIN');
    });

    test('none is said rather than left blank', () async {
      // Blank reads as "not loaded"; None reads as an answer.
      final _CreateApi api = _CreateApi()..globalRoleIds = const [];
      final Map<String, dynamic> values =
          await _definition(api, platformAdmin: false)
              .loadAssignments!('user-1');

      expect(values['global_roles_note'], 'None');
    });

    test('a platform administrator sees the firm grants instead', () async {
      // The mirror. Their Roles field is the global set, so without this the
      // page says nothing about what the person does in each firm.
      final _CreateApi api = _CreateApi();
      final ResourceDefinition<PlatformUser> definition =
          _definition(api, platformAdmin: true, activeFirmId: null);

      expect(_field(definition, 'global_roles_note'), isNull,
          reason: 'the Roles field above already is their global set');
      final FieldSpec? note = _field(definition, 'firm_roles_note');
      expect(note, isNotNull);
      expect(note!.alwaysReadOnly, isTrue);

      final Map<String, dynamic> values =
          await definition.loadAssignments!('user-1');
      // Each firm named beside what it holds -- a grant is per firm, so a
      // flat list of roles would say nothing about where they apply.
      expect(values['firm_roles_note'],
          'WHOLE01: SALES_MANAGER  ·  ELEC01: CASHIER');
    });

    test('the summary names every firm, the selected one included', () async {
      // Nothing on the form edits a firm's set any more, so there is no
      // second place for the selected firm to appear -- and leaving it out
      // would make the summary depend on the switcher, which is exactly the
      // coupling that put roles in the wrong tier.
      final _CreateApi api = _CreateApi();
      final ResourceDefinition<PlatformUser> definition =
          _definition(api, platformAdmin: true, activeFirmId: 'firm-1');

      expect(_field(definition, 'firm_roles_note')!.label,
          'Roles in specific firms');
      final Map<String, dynamic> values =
          await definition.loadAssignments!('user-1');
      expect(values['firm_roles_note'],
          'WHOLE01: SALES_MANAGER  ·  ELEC01: CASHIER');
      expect(values.containsKey('firm_role_ids'), isFalse);
    });

    test('a firm with no roles is left out of the summary', () async {
      final _CreateApi api = _CreateApi()
        ..firmRoleIds = const {'firm-1': ['role-sm']};

      final Map<String, dynamic> values =
          await _definition(api, platformAdmin: true, activeFirmId: null)
              .loadAssignments!('user-1');

      expect(values['firm_roles_note'], 'WHOLE01: SALES_MANAGER');
    });

    test('no firm grants at all reads None', () async {
      final _CreateApi api = _CreateApi()..firmRoleIds = const {};

      final Map<String, dynamic> values =
          await _definition(api, platformAdmin: true, activeFirmId: null)
              .loadAssignments!('user-1');

      expect(values['firm_roles_note'], 'None');
    });
  });

  group('a person who also works in another firm', () {
    // Their profile is platform-wide and not this firm's to change. The
    // refusal was silent -- a disabled toolbar button, but a double-click on
    // the row and the context menu's Edit both returned without a word, which
    // reads as a broken screen rather than a rule.
    PlatformUser shared({bool elsewhere = true}) => PlatformUser(
          id: 'user-1',
          email: 'view@abc.com',
          fullName: 'View Only',
          isActive: true,
          forcePasswordChange: false,
          expiresAt: '',
          belongsToOtherFirms: elsewhere,
        );

    test('editing is refused, and the refusal says why', () {
      final ResourceDefinition<PlatformUser> definition =
          _definition(_CreateApi(), platformAdmin: false);

      expect(definition.canEdit!(shared()), isFalse);
      final String? why = definition.editRefusal!(shared());
      expect(why, isNotNull);
      // Naming the way round is the point: the server allows a firm caller to
      // set a shared user's roles in their own firm, so the only thing
      // stopping anybody was the door.
      expect(why, contains('Roles by firm'));
    });

    test('somebody in this firm alone is edited normally', () {
      final ResourceDefinition<PlatformUser> definition =
          _definition(_CreateApi(), platformAdmin: false);

      expect(definition.canEdit!(shared(elsewhere: false)), isTrue);
      expect(definition.editRefusal!(shared(elsewhere: false)), isNull);
    });

    testWidgets('Roles by firm is not gated by the same rule',
        (tester) async {
      // The whole point of the message above. It needs a selected row like
      // the other row actions, and nothing else.
      //
      // A `testWidgets` with a real `BuildContext`, not a plain `test`:
      // `userDefinition` omits every dialog-opening action when `context` is
      // null, so a plain test would run over an empty list and pass whatever
      // the gate said.
      late ResourceDefinition<PlatformUser> definition;
      await tester.pumpWidget(MaterialApp(
        home: Builder(
          builder: (context) {
            definition = userDefinition(
              _CreateApi(),
              _permissions(
                platformAdmin: false,
                codes: const ['ROLE_ASSIGN', 'ROLE_VIEW'],
              ),
              context: context,
            );
            return const SizedBox.shrink();
          },
        ),
      ));

      final ResourceAction<PlatformUser> action = definition.customActions
          .firstWhere((a) => a.label == 'Roles by firm');
      expect(action.isEnabled, isNull,
          reason: 'no extra condition, so a shared user is still reachable');
      expect(action.needsSelection, isTrue);
    });
  });

  group('one tier per form, and no firm named on it', () {
    // The form used to carry two per-firm writers beside the global field: a
    // tier picker at create (`role_firm_id`) and, with a firm selected, a
    // second editable column (`firm_role_ids`). Both are gone. Roles by firm
    // is the only place a firm-tier role is written, whoever the caller is.
    for (final (String caller, bool platformAdmin, String? firm) in [
      ('a platform administrator in platform mode', true, null),
      ('a platform administrator working in a firm', true, 'firm-1'),
      ('a firm administrator', false, 'firm-1'),
    ]) {
      test('$caller is given one editable role field', () {
        final ResourceDefinition<PlatformUser> definition = _definition(
          _CreateApi(),
          platformAdmin: platformAdmin,
          activeFirmId: firm,
        );

        expect(_field(definition, 'role_ids'), isNotNull);
        expect(_field(definition, 'firm_role_ids'), isNull);
        expect(_field(definition, 'role_firm_id'), isNull);
      });
    }

    test('the field is named for the tier it writes', () {
      expect(
        _field(_definition(_CreateApi(), platformAdmin: true), 'role_ids')!
            .label,
        'Roles in every firm',
      );
      // A firm caller's save is scoped to their firm by the server, so for
      // them the same field is their firm's set and must say so.
      expect(
        _field(_definition(_CreateApi(), platformAdmin: false), 'role_ids')!
            .label,
        'Roles in this firm',
      );
    });

    test('the Roles helper points at Roles by firm for one firm', () {
      // The surprise reported from the running app: roles added with MEDI01
      // selected all landed globally. The form no longer pretends the
      // switcher has a say; it names the screen that does.
      final FieldSpec? roles =
          _field(_definition(_CreateApi(), platformAdmin: true), 'role_ids');

      expect(roles!.helperText, contains('Roles by firm'));
      expect(roles.helperText, contains('every firm'));
    });
  });

  group('reaching the per-firm editor from the form', () {
    test('the edit dialog offers it, the create dialog does not', () {
      // A platform administrator editing somebody with a firm selected
      // expects their change to land in that firm. It does not, and never
      // will. This is the way to the screen that *is* per firm, one click
      // from where the expectation forms.
      final ResourceDefinition<PlatformUser> definition =
          _definition(_CreateApi(), platformAdmin: true);

      expect(definition.dialogLeadingAction, isNotNull);
    });

    test('a caller who cannot assign roles is not offered it', () {
      // Giving somebody a role is the privilege this needs, so it must not be
      // reachable by anybody who could not assign one at a time.
      expect(
        _definition(
          _CreateApi(),
          platformAdmin: false,
          codes: const ['USER_VIEW'],
        ).dialogLeadingAction,
        isNull,
      );
    });

    test('a firm administrator who can assign roles is offered it', () {
      // Their firm's section is the only one they will see, which is the
      // point: one click to the roles they may actually change.
      expect(
        _definition(_CreateApi(), platformAdmin: false).dialogLeadingAction,
        isNotNull,
      );
    });
  });

  group('what saving a user does', () {
    Future<_CreateApi> save(
      Map<String, dynamic> values, {
      bool platformAdmin = true,
      String? activeFirmId = 'firm-1',
    }) async {
      final _CreateApi api = _CreateApi();
      await _definition(
        api,
        platformAdmin: platformAdmin,
        activeFirmId: activeFirmId,
      ).saveAssignments!('user-1', values);
      return api;
    }

    test('memberships are written before roles', () async {
      // The service refuses a role for somebody in no firm, so the order is
      // the difference between a hire that works and one that is refused.
      final _CreateApi api = await save({
        'firm_ids': 'firm-1',
        'primary_firm_id': 'firm-1',
        'role_ids': 'role-1',
        'template_id': '',
      });

      expect(api.calls, ['firms', 'globalRoles']);
    });

    test('a platform caller writes the global tier and nothing else',
        () async {
      // With a firm selected, too. The switcher has no say in where a role
      // lands: a per-firm write keyed off it is what put roles in a tier
      // nobody chose, and Roles by firm names the firm beside the roles.
      for (final String? firm in ['firm-1', null]) {
        final _CreateApi api = await save({
          'firm_ids': 'firm-1,firm-2',
          'primary_firm_id': 'firm-1',
          'role_ids': 'role-admin',
          'template_id': '',
        }, activeFirmId: firm);

        expect(api.calls, ['firms', 'globalRoles']);
        expect(api.scopedFirmIds, isEmpty,
            reason: 'no per-firm write from this form, whatever is selected');
      }
    });

    test('a firm administrator writes one tier, scoped server-side',
        () async {
      // Same call; `_firm_scope` gives it their own firm on the server.
      final _CreateApi api = await save({
        'firm_ids': 'firm-1',
        'primary_firm_id': 'firm-1',
        'role_ids': 'role-sm',
        'template_id': '',
      }, platformAdmin: false);

      expect(api.calls, ['firms', 'globalRoles']);
      expect(api.scopedFirmIds, isEmpty);
    });

    test('a job template decides, and grants as the caller does', () async {
      // Naming a job wins over hand-picked roles. One call, carrying no firm:
      // the endpoint scopes it exactly as it scopes `setUserRoles`, so the
      // template lands in the same tier the Roles field would have.
      final _CreateApi api = await save({
        'firm_ids': 'firm-1',
        'primary_firm_id': 'firm-1',
        'role_ids': 'role-1',
        'template_id': 'template-1',
      });

      expect(api.calls, ['firms', 'template']);
      expect(api.templateFirmIds, ['']);
    });

    test('a stray per-firm value from an older form is ignored', () async {
      // Nothing reads `role_firm_id` or `firm_role_ids` any more, so a value
      // under either key cannot reach a firm. Pinned because the fields were
      // removed rather than hidden, and a hidden field's value still saves.
      final _CreateApi api = await save({
        'firm_ids': 'firm-1,firm-2',
        'primary_firm_id': 'firm-1',
        'role_ids': 'role-admin',
        'template_id': '',
        'role_firm_id': 'firm-2',
        'firm_role_ids': 'role-cashier',
      });

      expect(api.calls, ['firms', 'globalRoles']);
      expect(api.scopedFirmIds, isEmpty);
    });
  });
}
