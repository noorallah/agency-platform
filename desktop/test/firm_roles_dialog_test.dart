import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/identity/firm_roles_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Roles by firm: two tiers, and only one of them is editable here.
///
/// A platform administrator writes the **global** set, which applies in every
/// firm the person belongs to. Either administrator writes a **firm** set. The
/// two are additive, and a firm administrator may not touch the global one --
/// but must see it, because it applies in their firm and leaving it out shows
/// them less than the person really has.
///
/// The defect behind the whole screen: the user form's single Roles box wrote
/// through a path that replaced *every* row regardless of firm, so a platform
/// administrator pressing Save without changing anything collapsed each firm's
/// separate roles into one global grant.
class _RolesApi extends ApiClient {
  _RolesApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  /// Firms the person belongs to, and every role that can be granted.
  @override
  Future<List<AssignmentOption>> options(String resource) async =>
      switch (resource) {
        'firms' => const [
            AssignmentOption(id: 'firm-1', label: 'WHOLE01'),
            AssignmentOption(id: 'firm-2', label: 'ELEC01'),
            AssignmentOption(id: 'firm-3', label: 'NOT-A-MEMBER'),
          ],
        'roles' => const [
            AssignmentOption(id: 'role-admin', label: 'FIRM_ADMIN'),
            AssignmentOption(id: 'role-sm', label: 'SALES_MANAGER'),
            AssignmentOption(id: 'role-cashier', label: 'CASHIER'),
          ],
        _ => const <AssignmentOption>[],
      };

  @override
  Future<Map<String, dynamic>> userFirmAssignmentValues(String userId) async =>
      {'firm_ids': 'firm-1,firm-2', 'primary_firm_id': 'firm-1'};

  @override
  Future<List<String>> userGlobalRoles(String userId) async =>
      const ['role-admin'];

  @override
  Future<List<String>> userFirmRoles(String userId, String firmId) async =>
      firmId == 'firm-1' ? const ['role-sm'] : const <String>[];

  /// What the last save carried, so a test can see the firm arrive.
  String savedFirmId = '';
  List<String> savedRoleIds = const [];

  @override
  Future<void> setUserFirmRoles(
    String userId,
    String firmId,
    List<String> roleIds,
  ) async {
    savedFirmId = firmId;
    savedRoleIds = roleIds;
  }
}

Future<_RolesApi> _open(WidgetTester tester) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1400, 1000);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  final _RolesApi api = _RolesApi();
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: FirmRolesDialog(
        api: api,
        userId: 'user-1',
        userLabel: 'Ravi Kumar · ravi@example.com',
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return api;
}

void main() {
  group('roles by firm', () {
    testWidgets('only the firms the person belongs to are listed',
        (tester) async {
      // A role in a firm somebody is not a member of is not reachable access:
      // the token is built per membership, so the grant would look done and
      // do nothing.
      await _open(tester);

      expect(find.text('WHOLE01'), findsOneWidget);
      expect(find.text('ELEC01'), findsOneWidget);
      expect(find.text('NOT-A-MEMBER'), findsNothing);
    });

    testWidgets('the global roles are shown and cannot be changed',
        (tester) async {
      await _open(tester);

      expect(find.text('Applies in every firm'), findsOneWidget);
      // `FIRM_ADMIN` appears once as the disabled global chip, and once per
      // firm as a selectable option -- so find the disabled one specifically.
      final Iterable<FilterChip> chips =
          tester.widgetList<FilterChip>(find.byType(FilterChip));
      final Iterable<FilterChip> disabled =
          chips.where((chip) => chip.onSelected == null);
      expect(disabled, hasLength(1),
          reason: 'the global grant is the only chip a caller cannot toggle');
      expect((disabled.first.label as Text).data, 'FIRM_ADMIN');
    });

    testWidgets('each firm shows what it holds, separately', (tester) async {
      await _open(tester);

      // WHOLE01 has SALES_MANAGER selected; ELEC01 has nothing.
      expect(
        find.text('No roles here — a member with nothing to do.'),
        findsOneWidget,
        reason: 'ELEC01 holds none, and an empty box should say so',
      );
    });

    testWidgets('saving carries the firm it was edited in', (tester) async {
      // The whole point: one Save affects one firm. The old single box wrote
      // every firm at once.
      final _RolesApi api = await _open(tester);

      // Add CASHIER to ELEC01 -- the second firm section.
      final Finder cashierChips = find.widgetWithText(FilterChip, 'CASHIER');
      await tester.tap(cashierChips.last);
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(TextButton, 'Save').last);
      await tester.pumpAndSettle();

      expect(api.savedFirmId, 'firm-2');
      expect(api.savedRoleIds, ['role-cashier']);
    });

    testWidgets('Save is offered only where something changed', (tester) async {
      await _open(tester);

      final Iterable<TextButton> saves = tester
          .widgetList<TextButton>(find.widgetWithText(TextButton, 'Save'));
      expect(saves, hasLength(2), reason: 'one per firm');
      expect(
        saves.every((button) => button.onPressed == null),
        isTrue,
        reason: 'nothing edited yet, so neither firm can be saved',
      );
    });
  });
}
