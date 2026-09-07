import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
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
}) {
  final String payload = base64Url.encode(
    utf8.encode(
      jsonEncode({
        'permissions': const <String>[],
        'roles': const <String>[],
        'platform_admin': platformAdmin,
        if (platformAdmin) 'platform_admin_scope': 'ALL_FIRMS',
        'firm_permissions': {'firm-1': codes},
      }),
    ),
  );
  return PermissionService()
    ..applyAccessToken('h.$payload.s', activeFirmId: 'firm-1');
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
  }

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
}) =>
    userDefinition(api, _permissions(platformAdmin: platformAdmin));

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
          _definition(api, platformAdmin: true);

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
          await _definition(api, platformAdmin: true)
              .loadAssignments!('user-1');

      expect(values['firm_roles_note'], 'WHOLE01: SALES_MANAGER');
    });

    test('no firm grants at all reads None', () async {
      final _CreateApi api = _CreateApi()..firmRoleIds = const {};

      final Map<String, dynamic> values =
          await _definition(api, platformAdmin: true)
              .loadAssignments!('user-1');

      expect(values['firm_roles_note'], 'None');
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
