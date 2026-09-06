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
import 'package:agency_desktop/ui/administration/clone_user_dialog.dart';
import 'package:agency_desktop/ui/administration/find_person_dialog.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:agency_desktop/ui/workspace/workspace_components.dart';
import 'package:agency_desktop/ui/workspace/module_visibility.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _token(Map<String, dynamic> claims) =>
    'h.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.s';

/// A token carrying the platform designation at its wider reach.
PermissionService _platformAdmin() => PermissionService()
  ..applyAccessToken(
    _token({
      'permissions': const <String>[],
      'roles': const <String>[],
      'platform_admin': true,
      'platform_admin_scope': 'ALL_FIRMS',
    }),
  );

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
  _firmFilterTests();

  group('the template picker', () {
    testWidgets('offers each job and says what it grants', (tester) async {
      // A template chosen by name alone is a permission decision made blind.
      final _Api api = _Api(templates: [
        _template(),
        _template(
            id: 't-2',
            code: 'warehouse',
            name: 'Warehouse',
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

  group('hiring like an existing person', () {
    Future<List<CloneUserDetails?>> open(WidgetTester tester) async {
      final List<CloneUserDetails?> got = <CloneUserDetails?>[];
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => TextButton(
                onPressed: () async => got.add(
                  await askForCloneDetails(context, sourceName: 'Asha'),
                ),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      return got;
    }

    testWidgets('says what does and does not cross over', (tester) async {
      // The distinction the whole feature rests on, and the one thing an
      // administrator pressing this will want to know before they do.
      await open(tester);

      expect(find.textContaining('same roles and firms'), findsOneWidget);
      expect(find.textContaining('none of their personal details'),
          findsOneWidget);
      expect(find.textContaining('Asha'), findsOneWidget);
    });

    testWidgets('says the password is temporary', (tester) async {
      // A password somebody else chose is not a password. The server forces a
      // change; saying so here stops it being handed over as permanent.
      await open(tester);

      expect(
        find.textContaining('change it when they first sign in'),
        findsOneWidget,
      );
    });

    testWidgets('refuses to create somebody with no name or email',
        (tester) async {
      final List<CloneUserDetails?> got = await open(tester);

      await tester.tap(find.widgetWithText(FilledButton, 'Create'));
      await tester.pumpAndSettle();

      expect(got, isEmpty, reason: 'the dialog should still be open');
      expect(find.text('Give the new person a name.'), findsOneWidget);
      expect(find.text('An email is required.'), findsOneWidget);
    });

    testWidgets('an address with no @ is not an email', (tester) async {
      await open(tester);
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Full name'), 'New Hire');
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Email'), 'not-an-email');
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Initial password'), 'Str0ng!');
      await tester.tap(find.widgetWithText(FilledButton, 'Create'));
      await tester.pumpAndSettle();

      expect(find.text('That is not an email.'), findsOneWidget);
    });

    testWidgets('a complete form returns the three fields', (tester) async {
      final List<CloneUserDetails?> got = await open(tester);

      await tester.enterText(
          find.widgetWithText(TextFormField, 'Full name'), '  New Hire  ');
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Email'), ' new@example.com ');
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Initial password'), 'Str0ng!');
      await tester.tap(find.widgetWithText(FilledButton, 'Create'));
      await tester.pumpAndSettle();

      expect(got.single?.fullName, 'New Hire');
      expect(got.single?.email, 'new@example.com');
      // Trimmed, because a stray space in an email is a support call and a
      // stray space in a password is a lockout.
      expect(got.single?.password, 'Str0ng!');
    });

    testWidgets('a dismissal creates nobody', (tester) async {
      final List<CloneUserDetails?> got = await open(tester);

      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      expect(got, [isNull]);
    });
  });

  group('a firm administrator can create a user', () {
    // `FIRM_ADMIN`'s real seeded codes. `FIRM_VIEW` is deliberately absent --
    // it is a platform code, one of the set a firm administrator may not even
    // grant -- and the New-user gate used to demand it, so the single role
    // whose whole job is running a firm's people was refused the button.
    const List<String> firmAdmin = [
      'USER_VIEW',
      'USER_CREATE',
      'USER_UPDATE',
      'USER_DELETE',
      'ROLE_VIEW',
      'ROLE_ASSIGN',
    ];

    test('the gate asks for nothing a firm administrator cannot hold', () {
      final PermissionService permissions = _permissions(firmAdmin);

      // The four the role actually holds are enough.
      expect(
        permissions.canUseAction(
          const ['USER_CREATE', 'ROLE_ASSIGN', 'ROLE_VIEW', 'USER_UPDATE'],
        ),
        isTrue,
      );
      // And the fifth is what used to hide the button.
      expect(permissions.hasPermission('FIRM_VIEW'), isFalse);
    });

    testWidgets('New and Edit are offered on the users grid', (tester) async {
      // Driven through the definition the shell actually builds, so a gate
      // that regains `FIRM_VIEW` fails here rather than on somebody's screen.
      final ResourceDefinition<PlatformUser> definition =
          userDefinition(_UsersApi(), _permissions(firmAdmin));

      expect(definition.canUseAction, isNotNull);
      expect(
        definition.canUseAction!(ToolbarAction.newItem, null),
        isTrue,
        reason: 'a firm administrator must be able to create a user',
      );
      expect(definition.canUseAction!(ToolbarAction.edit, null), isTrue);
    });

    test('the firm picker reads their own firms, not the platform list', () {
      // `/firms` lists every firm on the platform and only a platform
      // administrator may read it, so a firm administrator opening the form
      // got an empty picker and a failed load.
      final ResourceDefinition<PlatformUser> forFirmAdmin =
          userDefinition(_UsersApi(), _permissions(firmAdmin));
      final FieldSpec firms =
          forFirmAdmin.fields.firstWhere((field) => field.key == 'firm_ids');

      expect(firms.optionsResource, 'me/firms');

      final ResourceDefinition<PlatformUser> forPlatform =
          userDefinition(_UsersApi(), _platformAdmin());
      expect(
        forPlatform.fields
            .firstWhere((field) => field.key == 'firm_ids')
            .optionsResource,
        'firms',
      );
    });
  });

  group('creating a user by naming the job', () {
    // The one-step version. Before this the form could only take individual
    // roles, so hiring a counter clerk meant creating the user, finding them
    // in the grid, and applying a template as a second act.
    ResourceDefinition<PlatformUser> definition(_UsersApi api) =>
        userDefinition(
          api,
          _permissions(const [
            'USER_VIEW',
            'USER_CREATE',
            'USER_UPDATE',
            'ROLE_VIEW',
            'ROLE_ASSIGN',
          ]),
        );

    test('the New form offers a Job template field', () {
      final FieldSpec template = definition(_UsersApi())
          .fields
          .firstWhere((field) => field.key == 'template_id');

      expect(template.label, 'Job template');
      expect(template.optionsResource, 'user-templates');
      expect(template.singleSelection, isTrue);
      // Create only: afterwards the person is an ordinary user, and **Apply
      // job template** on the grid is how a job is re-applied. A field here
      // would suggest the user stays tied to the template, which is exactly
      // what a template is not.
      expect(template.createOnly, isTrue);
    });

    test('both boxes are on screen, so it says which one wins', () {
      final List<FieldSpec> fields = definition(_UsersApi()).fields;
      final FieldSpec roles =
          fields.firstWhere((field) => field.key == 'role_ids');
      final FieldSpec template =
          fields.firstWhere((field) => field.key == 'template_id');

      expect(roles.helperText, contains('Ignored when a job template'));
      expect(template.helperText, contains('pick roles by hand'));
    });

    test('naming a job applies it', () async {
      final _UsersApi api = _UsersApi();

      await definition(api).saveAssignments!('u-1', <String, dynamic>{
        'template_id': 't-1',
        'role_ids': '',
        'firm_ids': '',
      });

      expect(api.calls, contains('template:t-1'));
      expect(api.calls.where((c) => c.startsWith('roles:')), isEmpty);
    });

    test('naming no job falls back to the roles picked by hand', () async {
      final _UsersApi api = _UsersApi();

      await definition(api).saveAssignments!('u-1', <String, dynamic>{
        'template_id': '',
        'role_ids': 'r-1,r-2',
        'firm_ids': '',
      });

      expect(api.calls, contains('roles:r-1,r-2'));
      expect(api.calls.where((c) => c.startsWith('template:')), isEmpty);
    });

    test('a job named alongside hand-picked roles decides', () async {
      // One of them has to win. The helper text on Roles says which, rather
      // than leaving somebody to discover it from the audit trail.
      final _UsersApi api = _UsersApi();

      await definition(api).saveAssignments!('u-1', <String, dynamic>{
        'template_id': 't-1',
        'role_ids': 'r-9',
        'firm_ids': '',
      });

      expect(api.calls, contains('template:t-1'));
      expect(api.calls, isNot(contains('roles:r-9')));
    });

    test('editing an existing user is unchanged', () async {
      // `createOnly` keeps the field off the edit form, so nothing sends a
      // template and the roles picker behaves exactly as it always did.
      final _UsersApi api = _UsersApi();

      await definition(api).saveAssignments!('u-1', <String, dynamic>{
        'role_ids': 'r-3',
        'firm_ids': '',
      });

      expect(api.calls, contains('roles:r-3'));
    });
  });

  group('adding somebody who already has an account', () {
    // `list_users` is scoped to the caller's own members, so a firm
    // administrator could not find -- or even learn the existence of --
    // somebody who already works elsewhere. The lookup is the narrow opening
    // for that one job, and these pin its limits.

    Future<List<HireExistingPerson?>> open(
      WidgetTester tester,
      _LookupApi api,
    ) async {
      final List<HireExistingPerson?> chosen = <HireExistingPerson?>[];
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => TextButton(
                onPressed: () async =>
                    chosen.add(await findPersonToHire(context, api)),
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

    testWidgets('says a search reaches other firms and changes none of them',
        (tester) async {
      await open(tester, _LookupApi());

      expect(find.textContaining('Search by name or email'), findsOneWidget);
      expect(
        find.textContaining('does not change anything in any other firm'),
        findsOneWidget,
      );
    });

    testWidgets('a term under three characters searches nothing',
        (tester) async {
      // The first of the limits that makes this a lookup rather than a
      // directory: "a" must not return the platform. Checked here as well as
      // on the server, so somebody typing two letters gets guidance instead
      // of a 422 rendered as a failure.
      final _LookupApi api = _LookupApi(results: [_lookupRow()]);

      await open(tester, api);
      await tester.enterText(find.byType(TextField), 'as');
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();

      expect(api.terms, isEmpty);
      expect(find.text('Type a name or email to search.'), findsOneWidget);
    });

    testWidgets('three characters searches, and lists what came back',
        (tester) async {
      final _LookupApi api = _LookupApi(results: [
        _lookupRow(name: 'Asha Rao', email: 'asha@elsewhere.example'),
      ]);

      await open(tester, api);
      await tester.enterText(find.byType(TextField), 'ash');
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();

      expect(api.terms, ['ash']);
      expect(find.text('Asha Rao'), findsOneWidget);
      expect(find.text('asha@elsewhere.example'), findsOneWidget);
    });

    testWidgets('somebody already here is shown and cannot be added',
        (tester) async {
      // Shown rather than omitted: leaving them out would leave the searcher
      // wondering whether the person has an account at all.
      final _LookupApi api = _LookupApi(results: [
        _lookupRow(name: 'Already Here', alreadyAMember: true),
      ]);

      await open(tester, api);
      await tester.enterText(find.byType(TextField), 'alr');
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();

      expect(find.text('Already in this firm'), findsOneWidget);
      await tester.tap(find.text('Already Here'));
      await tester.pumpAndSettle();
      final FilledButton add = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Add to this firm'),
      );
      expect(add.onPressed, isNull);
    });

    testWidgets('nothing found says they may not have an account yet',
        (tester) async {
      await open(tester, _LookupApi());
      await tester.enterText(find.byType(TextField), 'nobody');
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();

      expect(
          find.textContaining('may not have an account yet'), findsOneWidget);
    });

    testWidgets('choosing somebody returns them with the job', (tester) async {
      final _LookupApi api = _LookupApi(results: [_lookupRow(id: 'u-9')]);
      final List<HireExistingPerson?> chosen = await open(tester, api);

      await tester.enterText(find.byType(TextField), 'ash');
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Asha Rao'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Add to this firm'));
      await tester.pumpAndSettle();

      expect(chosen.single?.person.id, 'u-9');
      // No job chosen is a valid answer: roles can be set afterwards.
      expect(chosen.single?.templateId, '');
    });

    testWidgets('a dismissal adds nobody', (tester) async {
      final List<HireExistingPerson?> chosen = await open(tester, _LookupApi());

      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      expect(chosen, [isNull]);
    });
  });

  group('the add-existing action needs no row', () {
    testWidgets('it is the one action about somebody not in the grid',
        (tester) async {
      // Every other custom action is about the selected row, so the toolbar
      // gates them all on a selection. This one is about a stranger --
      // demanding a row first asks you to click an unrelated person in order
      // to reach them, and the button reads as broken until you happen to.
      //
      // A real BuildContext, because the dialog-opening actions are declared
      // behind `if (context != null)`. Written with `context: null` first and
      // the loop ran over an empty list, so it passed with the fix reverted.
      late ResourceDefinition<PlatformUser> definition;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) {
              definition = userDefinition(
                _UsersApi(),
                _permissions(const [
                  'USER_VIEW',
                  'USER_CREATE',
                  'USER_UPDATE',
                  'ROLE_VIEW',
                  'ROLE_ASSIGN',
                ]),
                context: context,
              );
              return const SizedBox.shrink();
            },
          ),
        ),
      );

      final Map<String, bool> requirement = {
        for (final ResourceAction<PlatformUser> action
            in definition.customActions)
          action.label: action.needsSelection,
      };

      expect(
        requirement,
        {
          'Add existing user': false,
          'Hire like this person': true,
          'Apply job template': true,
        },
        reason: 'exactly one action stands without a selection',
      );
    });

    test('the label says user, which is what the grid calls them', () {
      // "person" and "user" for the same thing on one screen is a small
      // thing that costs somebody a second every time they scan the toolbar.
      final ResourceDefinition<PlatformUser> definition = userDefinition(
        _UsersApi(),
        _permissions(const ['USER_CREATE', 'ROLE_ASSIGN', 'ROLE_VIEW']),
      );

      expect(definition.title, 'Users');
      expect(
        definition.customActions.map((action) => action.label),
        isNot(contains('Add an existing person')),
      );
    });
  });

  group('the create form starts in your own firm', () {
    test('a firm admin gets their firm prefilled', () {
      // `create_user` attaches the caller's firm; `saveAssignments` then sends
      // whatever this picker holds. An untouched picker used to remove the
      // membership the create had just made, so the new user landed in no
      // firm and vanished from the grid -- the form doing the opposite of the
      // API, with nothing on screen to say so.
      final ResourceDefinition<PlatformUser> definition = userDefinition(
        _UsersApi(),
        _permissions(const [
          'USER_VIEW',
          'USER_CREATE',
          'USER_UPDATE',
          'ROLE_VIEW',
          'ROLE_ASSIGN',
        ]),
      );

      final Map<String, dynamic> fresh = definition.initialValues(null);

      expect(fresh['firm_ids'], 'firm-1');
      expect(fresh['primary_firm_id'], 'firm-1');
    });

    test('a platform administrator gets nothing prefilled', () {
      // They have no "own firm". `create_user` attaches nothing for them, and
      // quietly putting a new user into whichever firm their switcher happens
      // to show would be a surprise rather than a default.
      final ResourceDefinition<PlatformUser> definition =
          userDefinition(_UsersApi(), _platformAdmin());

      final Map<String, dynamic> fresh = definition.initialValues(null);

      expect(fresh['firm_ids'], '');
      expect(fresh['primary_firm_id'], '');
    });

    test('editing an existing user prefills nothing of the sort', () {
      // The firms of somebody who already exists are loaded by
      // `loadAssignments`, not guessed from whoever is looking at them.
      final ResourceDefinition<PlatformUser> definition = userDefinition(
        _UsersApi(),
        _permissions(const ['USER_VIEW', 'USER_UPDATE', 'ROLE_VIEW']),
      );
      const PlatformUser existing = PlatformUser(
        id: 'u-1',
        email: 'someone@example.com',
        fullName: 'Someone',
        isActive: true,
        forcePasswordChange: false,
        expiresAt: '',
      );

      expect(
          definition.initialValues(existing).containsKey('firm_ids'), isFalse);
    });
  });

  group('a person who works in more than one firm', () {
    test('their row cannot be edited, and the dialog says why', () {
      // A user record is platform-wide, so the server refuses to edit or
      // delete anybody who also works in a firm this caller cannot see. The
      // flag is what stops somebody filling in a form that cannot save.
      final ResourceDefinition<PlatformUser> definition = userDefinition(
        _UsersApi(),
        _permissions(const [
          'USER_VIEW',
          'USER_CREATE',
          'USER_UPDATE',
          'ROLE_VIEW',
          'ROLE_ASSIGN',
        ]),
      );
      const PlatformUser shared = PlatformUser(
        id: 'u-1',
        email: 'asha@elsewhere.example',
        fullName: 'Asha Rao',
        isActive: true,
        forcePasswordChange: false,
        expiresAt: '',
        belongsToOtherFirms: true,
      );
      const PlatformUser mine = PlatformUser(
        id: 'u-2',
        email: 'mine@example.com',
        fullName: 'Own Person',
        isActive: true,
        forcePasswordChange: false,
        expiresAt: '',
      );

      expect(definition.canEdit!(shared), isFalse);
      expect(definition.canEdit!(mine), isTrue);
      expect(definition.dialogSubtitle!(shared), contains('another firm'));
      expect(
        definition.dialogSubtitle!(shared),
        contains('still yours to set'),
        reason: 'say what they CAN do, not only what they cannot',
      );
    });
  });
}

UserLookupResult _lookupRow({
  String id = 'u-1',
  String name = 'Asha Rao',
  String email = 'asha@elsewhere.example',
  bool alreadyAMember = false,
}) =>
    UserLookupResult(
      id: id,
      fullName: name,
      email: email,
      alreadyAMember: alreadyAMember,
    );

class _LookupApi extends ApiClient {
  _LookupApi({this.results = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<UserLookupResult> results;

  /// Every term the dialog actually sent. A short one must send nothing.
  final List<String> terms = <String>[];

  @override
  Future<List<UserLookupResult>> lookupUsers(String term) async {
    terms.add(term);
    return results;
  }

  @override
  Future<PagedResult<UserTemplate>> userTemplates({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'code',
    bool descending = false,
  }) async =>
      const PagedResult<UserTemplate>(items: [], total: 0);
}

class _UsersApi extends ApiClient {
  _UsersApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// What the form actually did on save, in order.
  final List<String> calls = <String>[];

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
    if (path.contains('/apply-template')) {
      calls.add('template:${body?['template_id']}');
    } else if (path.endsWith('/roles')) {
      calls.add('roles:${(body?['ids'] as List<dynamic>?)?.join(',')}');
    } else if (path.endsWith('/firms')) {
      calls.add('firms');
    }
    return {'success': true, 'data': <String>[]};
  }
}

/// Which users are active in a given firm.
///
/// A platform administrator sees every user, so "who works at WHOLE01?" was a
/// question they could only answer by switching into the firm. The Users grid
/// and the User-Firm Assignments grid both read the same list, so both get the
/// filter -- and neither offers it to a firm administrator, whose list is
/// already their own firm and whom the server refuses the parameter.
void _firmFilterTests() {
  ResourceFilter? firmFilter(ResourceDefinition<PlatformUser> definition) {
    for (final ResourceFilter filter in definition.filters) {
      if (filter.key == 'firm_id') return filter;
    }
    return null;
  }

  group('filtering users by firm', () {
    test('a platform administrator is offered it on both grids', () {
      final PermissionService admin = _platformAdmin();

      for (final ResourceDefinition<PlatformUser> definition in [
        userDefinition(_FirmFilterApi(), admin),
        userFirmAssignmentDefinition(_FirmFilterApi(), admin),
      ]) {
        final ResourceFilter? filter = firmFilter(definition);
        expect(filter, isNotNull, reason: definition.title);
        // The firms are rows in a table, so the choices cannot be a const
        // list -- the grid fetches them.
        expect(filter!.optionsResource, 'firms', reason: definition.title);
        expect(definition.loadPage, isNotNull, reason: definition.title);
      }
    });

    test('a firm administrator is not', () {
      // Their list is already their own firm's people. A filter with one
      // choice is noise, and the server refuses them the parameter anyway.
      final PermissionService firmAdmin = _permissions(
        const ['USER_VIEW', 'USER_CREATE', 'USER_UPDATE', 'ROLE_VIEW'],
      );

      expect(firmFilter(userDefinition(_FirmFilterApi(), firmAdmin)), isNull);
      expect(
        firmFilter(userFirmAssignmentDefinition(_FirmFilterApi(), firmAdmin)),
        isNull,
      );
    });

    test('choosing a firm reaches the request', () async {
      // The filter is worth nothing if the value stops at the grid.
      final _FirmFilterApi api = _FirmFilterApi();
      final ResourceDefinition<PlatformUser> definition =
          userDefinition(api, _platformAdmin());

      await definition.loadPage!(filters: const {'firm_id': 'firm-7'});
      expect(api.lastFirmId, 'firm-7');

      await definition.loadPage!();
      expect(api.lastFirmId, '', reason: 'no filter means every firm');
    });
  });

  group('the firm filter on the users grid', () {
    Future<_FirmFilterApi> pumpGrid(
      WidgetTester tester, {
      bool optionsFail = false,
    }) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1600, 900);
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });
      final _FirmFilterApi api = _FirmFilterApi()..optionsFail = optionsFail;

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: ResourceManagementPage<PlatformUser>(
            api: api,
            definition: userDefinition(api, _platformAdmin()),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      return api;
    }

    testWidgets('renders, and offers the firms it fetched', (tester) async {
      // The definition naming a filter is not the same as a control on
      // screen: the choices are rows in a table, so the grid has to fetch
      // them before there is anything to pick.
      final _FirmFilterApi api = await pumpGrid(tester);

      expect(api.optionsAsked, contains('firms'));
      expect(find.text('Firm'), findsOneWidget);

      await tester.tap(find.byType(DropdownButtonFormField<String>).first);
      await tester.pumpAndSettle();

      expect(find.text('WHOLE01'), findsWidgets);
      expect(find.text('ELEC01'), findsWidgets);
      // Naming no firm has to stay reachable, or the filter has become a
      // requirement rather than a narrowing.
      expect(find.text('All firm'), findsWidgets);
    });

    testWidgets('choosing one reloads the grid against that firm',
        (tester) async {
      final _FirmFilterApi api = await pumpGrid(tester);
      expect(api.lastFirmId, '', reason: 'the first load names no firm');

      await tester.tap(find.byType(DropdownButtonFormField<String>).first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('ELEC01').last);
      await tester.pumpAndSettle();

      expect(api.lastFirmId, 'firm-b');
    });

    testWidgets('a firm list that cannot be read leaves the grid usable',
        (tester) async {
      // Emptying the filter bar because one fetch failed would be worse
      // than a filter with fewer choices -- the grid itself still works.
      final _FirmFilterApi api = await pumpGrid(tester, optionsFail: true);

      expect(api.optionsAsked, contains('firms'));
      expect(find.text('Firm'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });
}


class _FirmFilterApi extends ApiClient {
  _FirmFilterApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  /// The firm the last list request carried, so a test can see it arrive.
  String lastFirmId = '';

  /// Resources whose options were fetched, so a test can see the grid ask.
  final List<String> optionsAsked = [];

  /// Whether the options fetch should fail, for the degraded case.
  bool optionsFail = false;

  @override
  Future<List<AssignmentOption>> options(String resource) async {
    optionsAsked.add(resource);
    if (optionsFail) {
      throw ApiException('the firm list could not be read');
    }
    return const [
      AssignmentOption(id: 'firm-a', label: 'WHOLE01'),
      AssignmentOption(id: 'firm-b', label: 'ELEC01'),
    ];
  }

  @override
  Future<PagedResult<PlatformUser>> users({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    String firmId = '',
  }) async {
    lastFirmId = firmId;
    return const PagedResult(items: <PlatformUser>[], total: 0);
  }
}
