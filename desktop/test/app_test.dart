import 'dart:convert';

import 'package:agency_desktop/app.dart';
import 'package:agency_desktop/core/auth/refresh_token_store.dart';
import 'package:agency_desktop/core/auth/session_controller.dart';
import 'package:agency_desktop/core/navigation/workspace_router.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:agency_desktop/ui/workspace/workspace_components.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

class _MemoryTokenStore implements RefreshTokenStore {
  String? token;
  @override
  Future<void> clear() async => token = null;
  @override
  Future<String?> read() async => token;
  @override
  Future<void> write(String value) async => token = value;
}

void main() {
  test('permission service decodes permission claims for UI visibility', () {
    final PermissionService permissions = PermissionService();

    permissions.applyAccessToken(_accessToken({
      'roles': ['viewer'],
      'permissions': ['USER_VIEW', 'ROLE_VIEW'],
    }));

    expect(permissions.hasPermission('USER_VIEW'), isTrue);
    expect(permissions.hasPermission('FIRM_VIEW'), isFalse);
    expect(permissions.hasAllPermissions(['USER_VIEW', 'ROLE_VIEW']), isTrue);
    expect(permissions.hasAnyPermission(['FIRM_VIEW', 'ROLE_VIEW']), isTrue);
    expect(permissions.hasAnyPermission(['FIRM_VIEW']), isFalse);
    permissions.applyAccessToken('not-a-jwt');
    expect(permissions.permissions, isEmpty);
  });

  test('module catalog uses permission claims without role checks', () {
    final PermissionService permissions = PermissionService();
    permissions.applyAccessToken(_accessToken({
      'roles': ['platform_admin'],
      'permissions': [
        'FIRM_DELETE',
        'FIRM_VIEW',
        'USER_VIEW',
        'USER_UPDATE',
        'ROLE_VIEW',
      ],
    }));

    expect(permissions.hasPermission('FIRM_DELETE'), isTrue);
    final administration = ModuleCatalog.byId(AppModule.administration);
    expect(
      permissions.canAccess(
        administration.requiredPermissions,
        requiresAny: administration.requiresAnyPermission,
      ),
      isTrue,
    );
    final userFirms =
        administration.tabs.firstWhere((tab) => tab.id == 'user-firms');
    expect(
        permissions.hasAllPermissions(userFirms.requiredPermissions), isTrue);
  });

  test('workspace router restores locations and tracks navigation history', () {
    final WorkspaceRouter router =
        WorkspaceRouter(initialLocation: 'administration/roles');

    expect(router.current.module, 'administration');
    expect(router.current.tab, 'roles');
    router.navigate('masters', tab: 'firms');
    expect(router.canGoBack, isTrue);
    router.back();
    expect(router.current.path, 'administration/roles');
    router.forward();
    expect(router.current.path, 'masters/firms');
  });

  test('create checkpoint prevents duplicate records during assignment retry',
      () async {
    final CrudCreateCheckpoint checkpoint = CrudCreateCheckpoint();
    var creates = 0;

    final String firstId = await checkpoint.persist(() async {
      creates++;
      return 'created-id';
    });
    final String retriedId = await checkpoint.persist(() async {
      creates++;
      return 'duplicate-id';
    });

    expect(firstId, 'created-id');
    expect(retriedId, 'created-id');
    expect(creates, 1);
  });

  test('module catalog exposes only high-level navigation modules', () {
    expect(
      ModuleCatalog.modules.map((module) => module.label),
      [
        'Dashboard',
        'Administration',
        'Masters',
        'Sales',
        'Purchases',
        'Inventory',
        'Accounting',
        'Reports',
        'Licensing',
        'Settings',
      ],
    );
    expect(
      ModuleCatalog.byId(AppModule.administration).tabs.map((tab) => tab.label),
      containsAll(['Users', 'Roles', 'Permissions', 'User-Firm Assignments']),
    );
    expect(
      ModuleCatalog.byId(AppModule.administration).tabs.last.available,
      isFalse,
    );
  });

  test('workspace toolbar provides standard actions', () {
    expect(ToolbarAction.values, contains(ToolbarAction.newItem));
    expect(ToolbarAction.values, contains(ToolbarAction.export));
    expect(ToolbarAction.delete.label, 'Delete');
    expect(
        const GridColumn(label: 'Internal', visible: false).visible, isFalse);
  });

  for (final Size size in [
    const Size(1366, 768),
    const Size(1600, 900),
    const Size(1920, 1080),
  ]) {
    testWidgets(
        'management workspace remains bounded at ${size.width.toInt()}x'
        '${size.height.toInt()}', (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = size;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ManagementWorkspaceLayout(
              toolbar: const SizedBox(height: 40, child: Text('Toolbar')),
              searchPanel: const TextField(),
              primaryContent: EnterpriseDataGrid<int>(
                items: List.generate(20, (index) => index),
                total: 2000,
                pageOffset: 0,
                columns: const [GridColumn(label: 'Record')],
                id: (item) => '$item',
                cells: (item) => ['Record $item'],
                onSelect: (_) {},
                onPageChanged: (_) {},
              ),
              detailsPanel: DetailsPanel(
                title: 'Record details',
                lines: List.generate(
                  40,
                  (index) => DetailLine('Field $index', 'Value $index'),
                ),
              ),
              statusBar: const WorkspaceStatusBar(
                total: 2000,
                selected: false,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.byType(PaginatedDataTable), findsOneWidget);
      expect(find.text('Toolbar'), findsOneWidget);
      expect(find.text('2000 records'), findsOneWidget);
    });
  }

  testWidgets('data grid resets its pagination state when page offset changes',
      (tester) async {
    int pageOffset = 20;
    late StateSetter rebuild;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: StatefulBuilder(
            builder: (context, setState) {
              rebuild = setState;
              return EnterpriseDataGrid<int>(
                items: List.generate(20, (index) => pageOffset + index),
                total: 100,
                pageOffset: pageOffset,
                columns: const [GridColumn(label: 'Record')],
                id: (item) => '$item',
                cells: (item) => ['Record $item'],
                onSelect: (_) {},
                onPageChanged: (_) {},
              );
            },
          ),
        ),
      ),
    );

    expect(find.byKey(const ValueKey(20)), findsOneWidget);
    rebuild(() => pageOffset = 0);
    await tester.pump();
    expect(find.byKey(const ValueKey(0)), findsOneWidget);
    expect(find.byKey(const ValueKey(20)), findsNothing);
  });

  testWidgets('CRUD workspace dialog is large, tabbed, and mode aware',
      (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1366, 768);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    final ApiClient api = ApiClient(
      baseUrl: 'http://localhost:8000',
      accessToken: () => null,
      refreshAccessToken: () async => false,
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: CrudWorkspaceDialog(
            title: 'User Management',
            mode: CrudDialogMode.edit,
            api: api,
            values: const {'name': 'Existing user', 'active': true},
            fields: const [
              FieldSpec(key: 'name', label: 'Name', required: true),
              FieldSpec(
                key: 'active',
                label: 'Active',
                boolean: true,
                section: 'Security',
              ),
            ],
            onSave: (_) async {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final Size dialogSize = tester.getSize(
      find.byKey(const ValueKey('crud-workspace-dialog-surface')),
    );
    expect(dialogSize.width, closeTo(1366 * .88, 1));
    expect(dialogSize.height, closeTo(768 * .88, 1));
    expect(find.text('General'), findsOneWidget);
    expect(find.text('Security'), findsOneWidget);
    expect(find.text('Save'), findsOneWidget);
    expect(find.text('Cancel'), findsOneWidget);
    expect(find.text('Existing user'), findsOneWidget);

    await tester.tap(find.text('Security'));
    await tester.pumpAndSettle();
    expect(find.text('Active'), findsOneWidget);
  });

  testWidgets('view dialog is read-only and exposes only Close',
      (tester) async {
    final ApiClient api = ApiClient(
      baseUrl: 'http://localhost:8000',
      accessToken: () => null,
      refreshAccessToken: () async => false,
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: CrudWorkspaceDialog(
            title: 'Firm Management',
            mode: CrudDialogMode.view,
            api: api,
            values: const {'name': 'ABC Traders'},
            fields: const [FieldSpec(key: 'name', label: 'Name')],
            onSave: null,
          ),
        ),
      ),
    );

    final EditableText field =
        tester.widget<EditableText>(find.byType(EditableText));
    expect(field.readOnly, isTrue);
    expect(find.text('Close'), findsOneWidget);
    expect(find.text('Save'), findsNothing);
  });

  testWidgets('workspace dialog preserves values after API save failure',
      (tester) async {
    final ApiClient api = ApiClient(
      baseUrl: 'http://localhost:8000',
      accessToken: () => null,
      refreshAccessToken: () async => false,
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: CrudWorkspaceDialog(
            title: 'User Management',
            mode: CrudDialogMode.create,
            api: api,
            values: const {},
            fields: const [
              FieldSpec(key: 'name', label: 'Name', required: true),
            ],
            onSave: (_) async => throw const ApiException(
              'Unable to save user.',
              details: [
                {'field': 'name', 'message': 'Name is already used.'},
              ],
            ),
          ),
        ),
      ),
    );
    await tester.enterText(find.byType(TextFormField), 'Entered value');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(find.text('Unable to save user.'), findsOneWidget);
    expect(find.text('Entered value'), findsOneWidget);
    expect(find.text('Name is already used.'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('crud-workspace-dialog-surface')),
      findsOneWidget,
    );
  });

  testWidgets('workspace dialog supports Ctrl+S and Escape shortcuts',
      (tester) async {
    final ApiClient api = ApiClient(
      baseUrl: 'http://localhost:8000',
      accessToken: () => null,
      refreshAccessToken: () async => false,
    );
    var saves = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => FilledButton(
            onPressed: () => showDialog<void>(
              context: context,
              barrierDismissible: false,
              builder: (_) => CrudWorkspaceDialog(
                title: 'User Management',
                mode: CrudDialogMode.create,
                api: api,
                values: const {'name': 'Shortcut user'},
                fields: const [
                  FieldSpec(key: 'name', label: 'Name', required: true),
                ],
                onSave: (_) async => saves++,
              ),
            ),
            child: const Text('Open'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.keyS);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
    await tester.pumpAndSettle();
    expect(saves, 1);
    expect(
      find.byKey(const ValueKey('crud-workspace-dialog-surface')),
      findsNothing,
    );

    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('crud-workspace-dialog-surface')),
      findsNothing,
    );
  });

  testWidgets('restored signed-out session opens login navigation',
      (tester) async {
    final SessionController session = SessionController(
      baseUrl: 'http://localhost:8000',
      tokenStore: _MemoryTokenStore(),
    );

    await tester.pumpWidget(AgencyApp(session: session));
    await tester.pump();

    expect(find.text('Sign in'), findsOneWidget);
    expect(find.text('Agency Platform'), findsOneWidget);
  });
}

String _accessToken(Map<String, dynamic> claims) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '');
  return 'header.$payload.signature';
}
