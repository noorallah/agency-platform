import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Creating a user: which firms, and which tier the roles land in.
///
/// A platform caller's grant resolves **globally** whenever no firm is named,
/// so hiring somebody as a cashier made them one in every firm they belong to
/// and every firm added later. Nothing on the form said so, and the template
/// picker carried the same surprise. `Apply roles to` is the choice, and it is
/// offered only to a platform caller because a firm administrator's grant is
/// already scoped to their own firm.
///
/// The order matters as much as the choice. A role in one firm needs an active
/// membership there — the token is built per membership, so a grant without
/// one reaches nobody and the service refuses it. Roles used to be written
/// first, while the person was still in no firm.
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
      //
      // In **platform mode**: with a firm selected that firm is editable in
      // its own column and left out of this summary, which
      // `user_form_surface_test.dart` covers.
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

  group('two columns: the global tier and the firm you are in', () {
    test('the second column appears only with a firm selected', () {
      // With none there is nothing for it to name, and platform mode is
      // where a platform administrator starts.
      expect(
        _field(_definition(_CreateApi(), platformAdmin: true),
            'firm_role_ids'),
        isNotNull,
      );
      expect(
        _field(
          _definition(_CreateApi(), platformAdmin: true, activeFirmId: null),
          'firm_role_ids',
        ),
        isNull,
      );
    });

    test('a firm administrator gets one column, not two', () {
      // Their Roles field already *is* their firm's set; a second column
      // would be the same thing twice.
      expect(
        _field(_definition(_CreateApi(), platformAdmin: false),
            'firm_role_ids'),
        isNull,
      );
    });

    test('it loads the roles held in the selected firm', () async {
      final _CreateApi api = _CreateApi();
      final Map<String, dynamic> values =
          await _definition(api, platformAdmin: true)
              .loadAssignments!('user-1');

      expect(values['firm_role_ids'], 'role-sm');
    });

    test('saving writes it to the selected firm alone', () async {
      // The whole point of the column: MEDI01 selected means MEDI01, not
      // everywhere -- which is what happened before it existed.
      final _CreateApi api = _CreateApi();
      await _definition(api, platformAdmin: true).saveAssignments!('user-1', {
        'firm_ids': 'firm-1,firm-2',
        'primary_firm_id': 'firm-1',
        'role_ids': 'role-admin',
        'template_id': '',
        'role_firm_id': '',
        'firm_role_ids': 'role-cashier',
      });

      expect(api.calls, ['firms', 'globalRoles', 'firmRoles']);
      expect(api.scopedFirmIds, ['firm-1']);
      expect(api.scopedRoleIds, ['role-cashier']);
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

    test('the Roles helper says the switcher does not scope it', () {
      // The surprise reported from the running app: roles added with MEDI01
      // selected all landed globally.
      final FieldSpec? roles =
          _field(_definition(_CreateApi(), platformAdmin: true), 'role_ids');

      expect(roles!.helperText, contains('switcher does not change this'));
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

  group('the tier choice on the create form', () {
    test('a platform administrator is asked which firm', () {
      final FieldSpec? field =
          _field(_definition(_CreateApi(), platformAdmin: true),
              'role_firm_id');

      expect(field, isNotNull);
      expect(field!.optionsResource, 'firms');
      // Multi-select: a person hired into three firms may need the role in
      // two of them, and one-at-a-time would mean three trips through the
      // form.
      expect(field.singleSelection, isFalse);
      // Afterwards the person's roles are edited per firm on Roles by firm,
      // so a field on the edit form would offer a second way to do one thing.
      expect(field.createOnly, isTrue);
      expect(field.helperText, contains('every firm'));
    });

    test('a firm administrator is not', () {
      // Their grant is already scoped to their own firm; the question has one
      // answer, and an unanswerable field is worse than none.
      expect(
        _field(_definition(_CreateApi(), platformAdmin: false), 'role_firm_id'),
        isNull,
      );
    });
  });

  group('what saving a new user does', () {
    Future<_CreateApi> save(Map<String, dynamic> values) async {
      final _CreateApi api = _CreateApi();
      await _definition(api, platformAdmin: true)
          .saveAssignments!('user-1', values);
      return api;
    }

    test('memberships are written before roles', () async {
      // The whole reason a per-firm grant is possible here at all: the
      // service refuses a role in a firm the person is not yet a member of.
      final _CreateApi api = await save({
        'firm_ids': 'firm-1',
        'primary_firm_id': 'firm-1',
        'role_ids': 'role-1',
        'template_id': '',
        'role_firm_id': 'firm-1',
      });

      expect(api.calls, ['firms', 'firmRoles']);
      expect(api.scopedFirmIds, ['firm-1']);
    });

    test('naming no firm keeps the global grant', () async {
      final _CreateApi api = await save({
        'firm_ids': 'firm-1',
        'primary_firm_id': 'firm-1',
        'role_ids': 'role-1',
        'template_id': '',
        'role_firm_id': '',
      });

      expect(api.calls, ['firms', 'globalRoles']);
    });

    test('a job template lands in the named firm too', () async {
      // The picker carried the same surprise as the Roles box: applied by a
      // platform caller with no firm, it granted the job everywhere.
      final _CreateApi api = await save({
        'firm_ids': 'firm-1',
        'primary_firm_id': 'firm-1',
        'role_ids': '',
        'template_id': 'template-1',
        'role_firm_id': 'firm-1',
      });

      expect(api.calls, ['firms', 'template']);
      expect(api.templateFirmIds, ['firm-1']);
    });

    test('two firms are written separately', () async {
      // A grant is per firm in the table, so there is no "these two at once"
      // to send. Writing them one at a time is also what lets each firm
      // change its own afterwards without touching the other.
      final _CreateApi api = await save({
        'firm_ids': 'firm-1,firm-2',
        'primary_firm_id': 'firm-1',
        'role_ids': 'role-1',
        'template_id': '',
        'role_firm_id': 'firm-1,firm-2',
      });

      expect(api.calls, ['firms', 'firmRoles', 'firmRoles']);
      expect(api.scopedFirmIds, ['firm-1', 'firm-2']);
    });

    test('a template applies in each named firm', () async {
      final _CreateApi api = await save({
        'firm_ids': 'firm-1,firm-2',
        'primary_firm_id': 'firm-1',
        'role_ids': '',
        'template_id': 'template-1',
        'role_firm_id': 'firm-1,firm-2',
      });

      expect(api.calls, ['firms', 'template', 'template']);
      expect(api.templateFirmIds, ['firm-1', 'firm-2']);
    });

    test('a template with no firm still grants globally', () async {
      // Unchanged on purpose: it is what a platform caller has always meant,
      // and now it is what the form says rather than what it does silently.
      final _CreateApi api = await save({
        'firm_ids': 'firm-1',
        'primary_firm_id': 'firm-1',
        'role_ids': '',
        'template_id': 'template-1',
        'role_firm_id': '',
      });

      expect(api.calls, ['firms', 'template']);
      // One call, carrying no firm -- which is what the endpoint reads as
      // platform-wide.
      expect(api.templateFirmIds, ['']);
    });
  });
}
