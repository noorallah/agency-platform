import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A deleted user can be found and brought back -- by a platform
/// administrator, from the Users grid.
///
/// Deletion leaves the memberships and roles in place, so a restore is one
/// flag on the server. The grid's half is finding the row: deleted users are
/// hidden by default, a **Show deleted** filter asks for them, they show as
/// Deleted with Edit dead, and **Restore** is the action on them. None of it
/// is offered to a firm administrator, whose grid cannot see a deleted user
/// at all.
PermissionService _permissions({required bool platformAdmin}) {
  const List<String> codes = [
    'USER_VIEW',
    'USER_CREATE',
    'USER_UPDATE',
    'USER_DELETE',
    'ROLE_VIEW',
    'ROLE_ASSIGN',
  ];
  final String payload = base64Url.encode(utf8.encode(jsonEncode({
    'permissions': platformAdmin ? codes : const <String>[],
    'roles': const <String>[],
    'platform_admin': platformAdmin,
    if (platformAdmin) 'platform_admin_scope': 'ALL_FIRMS',
    'firm_permissions': {'firm-1': codes},
  })));
  return PermissionService()
    ..applyAccessToken('h.$payload.s', activeFirmId: 'firm-1');
}

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  bool? lastDeletedOnly;
  String? lastFirmId;
  final List<String> restored = [];

  @override
  Future<PagedResult<PlatformUser>> users({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    String firmId = '',
    bool deletedOnly = false,
  }) async {
    lastDeletedOnly = deletedOnly;
    lastFirmId = firmId;
    return PagedResult(items: rows, total: rows.length);
  }

  /// What the grid shows; a deleted row when the test wants one.
  List<PlatformUser> rows = const [];

  @override
  Future<List<AssignmentOption>> options(String resource) async => const [];

  @override
  Future<Json> userAssignmentValues(String userId) async =>
      {'role_ids': '', 'firm_ids': '', 'primary_firm_id': ''};

  @override
  Future<String> userFirmRoleLabels(String userId) async => '';

  @override
  Future<PlatformUser> restoreUser(String id) async {
    restored.add(id);
    return _user(deleted: false);
  }
}

PlatformUser _user({required bool deleted}) => PlatformUser(
      id: 'u-1',
      email: 'leaver@example.com',
      fullName: 'Leaver',
      isActive: true,
      forcePasswordChange: false,
      expiresAt: '',
      isDeleted: deleted,
    );

/// The footer of the dialog a row opens in, as the definition builds it.
Future<Widget?> _footer(
  WidgetTester tester,
  ResourceDefinition<PlatformUser> definition,
  PlatformUser user,
) async {
  Widget? built;
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) {
          built = definition.dialogLeadingAction?.call(context, user);
          return built ?? const SizedBox.shrink();
        },
      ),
    ),
  ));
  await tester.pump();
  return built;
}

void main() {
  group('finding a deleted user', () {
    test('a platform administrator can ask for deleted rows', () async {
      // One more choice on the Firm filter rather than a second dropdown,
      // which overflowed the filter row.
      final _Api api = _Api();
      final ResourceDefinition<PlatformUser> definition =
          userDefinition(api, _permissions(platformAdmin: true));

      final ResourceFilter firm =
          definition.filters.singleWhere((f) => f.key == 'firm_id');
      expect(firm.options.map((o) => o.value), contains(deletedUsersFilter));

      await definition.loadPage!(filters: const {'firm_id': deletedUsersFilter});
      expect(api.lastDeletedOnly, isTrue);
      expect(api.lastFirmId, '', reason: 'the choice is not a firm');

      await definition.loadPage!(filters: const {'firm_id': 'firm-1'});
      expect(api.lastDeletedOnly, isFalse,
          reason: 'a real firm shows live rows only');
      expect(api.lastFirmId, 'firm-1');
    });

    test('a firm administrator is not offered the choice', () {
      final ResourceDefinition<PlatformUser> definition =
          userDefinition(_Api(), _permissions(platformAdmin: false));

      expect(definition.filters, isEmpty);
    });

    test('a deleted row says so and cannot be edited', () {
      final ResourceDefinition<PlatformUser> definition =
          userDefinition(_Api(), _permissions(platformAdmin: true));

      expect(definition.cells(_user(deleted: true)).last, 'Deleted');
      expect(definition.canEdit!(_user(deleted: true)), isFalse);
      expect(definition.editRefusal!(_user(deleted: true)),
          contains('Restore them first'));
      expect(definition.canEdit!(_user(deleted: false)), isTrue);
    });
  });

  group('Restore, in the footer of a deleted row\'s dialog', () {
    // Not a toolbar button: the users toolbar is full, and one more control
    // overflowed it at 1600 wide. A deleted row cannot be edited, so View is
    // where somebody lands on it, and the footer is where Roles by firm
    // already is for a live row.
    testWidgets('a platform administrator opening a deleted row is offered it',
        (tester) async {
      final _Api api = _Api();
      final ResourceDefinition<PlatformUser> definition =
          userDefinition(api, _permissions(platformAdmin: true));

      await _footer(tester, definition, _user(deleted: true));
      expect(find.text('Restore'), findsOneWidget);
      expect(find.text('Roles by firm'), findsNothing,
          reason: 'a deleted person has no roles to edit until restored');

      await tester.tap(find.text('Restore'));
      await tester.pumpAndSettle();
      expect(api.restored, ['u-1']);
    });

    testWidgets('a live row keeps Roles by firm', (tester) async {
      final ResourceDefinition<PlatformUser> definition =
          userDefinition(_Api(), _permissions(platformAdmin: true));

      await _footer(tester, definition, _user(deleted: false));
      expect(find.text('Roles by firm'), findsOneWidget);
      expect(find.text('Restore'), findsNothing);
    });

    testWidgets('a firm administrator is not offered it', (tester) async {
      // Their grid never lists a deleted row; this is the second lock.
      final ResourceDefinition<PlatformUser> definition =
          userDefinition(_Api(), _permissions(platformAdmin: false));

      await _footer(tester, definition, _user(deleted: true));
      expect(find.text('Restore'), findsNothing);
    });

    testWidgets('a refused Edit says why and opens the row read-only',
        (tester) async {
      // Reported from the running app: right-click → Edit on a deleted row
      // showed the refusal and opened nothing, so the footer's Restore was
      // unreachable that way. The refusal is about writing; the record is
      // still there to look at, and Restore is on it.
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1600, 900);
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });
      final _Api api = _Api()..rows = [_user(deleted: true)];
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: ResourceManagementPage<PlatformUser>(
            api: api,
            definition: userDefinition(api, _permissions(platformAdmin: true)),
          ),
        ),
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.text('leaver@example.com'),
          buttons: kSecondaryMouseButton);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Edit').last);
      await tester.pumpAndSettle();

      expect(find.textContaining('Restore them first'), findsOneWidget,
          reason: 'the refusal still speaks');
      // The dialog opened, in view mode: its footer carries the deleted
      // row's Restore, which no edit dialog and nothing on the grid has.
      expect(find.widgetWithText(FilledButton, 'Restore'), findsOneWidget,
          reason: 'and the record opens, read-only, with Restore on it');
      expect(find.widgetWithText(FilledButton, 'Save'), findsNothing,
          reason: 'nothing to save on a view');
      // Read-only looks like the edit form with greyed boxes, so the dialog
      // says what it is rather than leaving the reader to infer it.
      expect(find.textContaining('DELETED. Read-only'), findsOneWidget);
      expect(find.text('Deleted'), findsWidgets,
          reason: 'the status cell says so on the grid too');
    });
  });
}
