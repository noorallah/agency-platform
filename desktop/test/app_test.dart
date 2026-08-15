import 'dart:convert';

import 'package:agency_desktop/app.dart';
import 'package:agency_desktop/core/auth/refresh_token_store.dart';
import 'package:agency_desktop/core/auth/session_controller.dart';
import 'package:agency_desktop/core/navigation/workspace_router.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:agency_desktop/ui/workspace/workspace_components.dart';
import 'package:agency_desktop/ui/workspace/workspace_interactions.dart';
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

class _ProductApiWithoutAttributeDefinitions extends _ProductApi {
  @override
  Future<PagedResult<AttributeDefinitionRecord>> attributeDefinitions({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) async =>
      throw const ApiException('Forbidden', statusCode: 403);
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
        WorkspaceRouter(initialLocation: 'administration/tax/tax-profiles');

    expect(router.current.module, 'administration');
    expect(router.current.tab, 'tax/tax-profiles');
    expect(router.current.path, 'administration/tax/tax-profiles');
    router.navigate('masters', tab: 'firms');
    expect(router.canGoBack, isTrue);
    router.back();
    expect(router.current.path, 'administration/tax/tax-profiles');
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

  test('module catalog exposes configured navigation modules', () {
    expect(
      ModuleCatalog.modules.map((module) => module.label),
      [
        'Dashboard',
        'Administration',
        'Masters',
        'Sales',
        'Quotations',
        'Sales Orders',
        'Delivery Notes',
        'Sales Invoices',
        'Sales Returns',
        'Purchases',
        'Purchase Invoices',
        'Purchase Returns',
        'Goods Receipts',
        'Inventory',
        'Finance',
        'Reports',
        'Licensing',
        'Settings',
      ],
    );
    expect(
      ModuleCatalog.byId(AppModule.administration).tabs.map((tab) => tab.label),
      containsAll([
        'Users',
        'Roles',
        'Permissions',
        'User-Firm Assignments',
        'Business Profiles',
        'Feature Management',
        'Module Configuration',
        'Attribute Definitions',
        'Profile Assignment',
      ]),
    );
    // Nothing is offered that cannot be opened. Every tab greyed out as
    // "coming soon" has been removed or given the screen it advertised, so a
    // catalog entry now means a working destination.
    expect(
      [
        for (final ModuleDefinition module in ModuleCatalog.modules)
          for (final ModuleTabDefinition tab in module.tabs)
            if (!tab.available) '${module.label} / ${tab.label}',
      ],
      isEmpty,
    );
    expect(
      ModuleCatalog.byId(AppModule.masters).tabs.map((tab) => tab.label),
      containsAll(['Customers', 'Products', 'Vendors']),
    );
  });

  test('workspace toolbar provides standard actions', () {
    expect(ToolbarAction.values, contains(ToolbarAction.newItem));
    expect(ToolbarAction.values, contains(ToolbarAction.export));
    expect(ToolbarAction.delete.label, 'Delete');
    expect(
        const GridColumn(key: 'internal', label: 'Internal', visible: false)
            .visible,
        isFalse);
  });

  test('workspace shortcut registry exposes the standard desktop bindings', () {
    final WorkspaceShortcutBindings bindings = WorkspaceShortcutBindings(
      create: () {},
      save: () {},
      focusSearch: () {},
      refresh: () {},
      copy: () {},
      cancel: () {},
      delete: () {},
      globalSearch: () {},
    );

    expect(bindings.toCallbacks(), hasLength(10));
  });

  testWidgets('standard empty states provide distinct reusable messages',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: StandardEmptyState(type: EmptyStateType.noSearchResults),
        ),
      ),
    );

    expect(find.text('No search results'), findsOneWidget);
    expect(find.byIcon(Icons.search_off_outlined), findsOneWidget);
  });

  testWidgets('status badge applies enterprise tone mapping', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Column(
            children: [
              StatusBadge.fromStatus('ACTIVE'),
              StatusBadge.fromStatus('PENDING'),
              StatusBadge.fromStatus('EXPIRED'),
            ],
          ),
        ),
      ),
    );

    expect(find.text('ACTIVE'), findsOneWidget);
    expect(find.text('PENDING'), findsOneWidget);
    expect(find.text('EXPIRED'), findsOneWidget);
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
                columns: const [GridColumn(key: 'record', label: 'Record')],
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
      expect(find.byType(DataTable), findsOneWidget);
      expect(find.text('Toolbar'), findsOneWidget);
      expect(find.text('2000 records'), findsOneWidget);
    });
  }

  testWidgets('data grid shows the page it was given, and only that page',
      (tester) async {
    // This used to assert on a ValueKey that existed solely to reset
    // PaginatedDataTable's internal page state. Rows now come straight from
    // `items`, so the thing worth asserting is the rendered content.
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
                columns: const [GridColumn(key: 'record', label: 'Record')],
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

    expect(find.text('Record 20'), findsOneWidget);
    expect(find.text('Record 0'), findsNothing);

    rebuild(() => pageOffset = 0);
    await tester.pump();

    expect(find.text('Record 0'), findsOneWidget);
    expect(find.text('Record 20'), findsNothing);

    // 20 records on a page sized for 20: exactly 20 rows, no blank padding.
    expect(
        tester.widget<DataTable>(find.byType(DataTable)).rows, hasLength(20));
  });

  testWidgets('a grid with row actions pins them outside the scroll',
      (tester) async {
    // Firm Management carries seven data columns plus Actions, so Actions sat
    // off the right edge -- and Flutter never draws a horizontal scrollbar, so
    // nothing said it was there or how to reach it.
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(900, 700);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: EnterpriseDataGrid<int>(
            items: const [1, 2, 3],
            total: 3,
            pageOffset: 0,
            columns: const [
              GridColumn(key: 'a', label: 'Code'),
              GridColumn(key: 'b', label: 'Name'),
              GridColumn(key: 'c', label: 'Contact'),
              GridColumn(key: 'd', label: 'Currency'),
              GridColumn(key: 'e', label: 'Country'),
              GridColumn(key: 'f', label: 'Storage'),
              GridColumn(key: 'g', label: 'Status'),
            ],
            id: (item) => '$item',
            cells: (item) => List.filled(7, 'value $item'),
            onSelect: (_) {},
            onOpen: (_) {},
            onContextAction: (_, __) {},
            contextActions: const [WorkspaceContextAction.delete],
            onPageChanged: (_) {},
          ),
        ),
      ),
    );

    expect(tester.takeException(), isNull);
    // Two tables: the data half scrolls, the Actions half does not.
    expect(find.byType(DataTable), findsNWidgets(2));
    final Finder actionsTable = find.byType(DataTable).last;
    expect(
      find.ancestor(
        of: actionsTable,
        matching: find.byType(SingleChildScrollView),
      ),
      findsWidgets, // the shared vertical scroll
    );
    // The row actions are reachable without scrolling anywhere.
    expect(find.byTooltip('View'), findsNWidgets(3));
    expect(find.byTooltip('More actions'), findsNWidgets(3));
    // And the data half now says it can be scrolled.
    expect(find.byType(Scrollbar), findsWidgets);
  });

  testWidgets('a narrow grid leaves no gap before the pinned actions',
      (tester) async {
    // Three columns and a pinned Actions column left a stretch of nothing
    // between them: the data table took only its intrinsic width and the rest
    // of its Expanded sat empty.
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1400, 700);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: EnterpriseDataGrid<int>(
            items: const [1, 2],
            total: 2,
            pageOffset: 0,
            columns: const [
              GridColumn(key: 'a', label: 'Permission'),
              GridColumn(key: 'b', label: 'Code'),
              GridColumn(key: 'c', label: 'Status'),
            ],
            id: (item) => '$item',
            cells: (item) => ['Name $item', 'CODE_$item', 'Active'],
            onSelect: (_) {},
            onOpen: (_) {},
            onContextAction: (_, __) {},
            contextActions: const [WorkspaceContextAction.delete],
            onPageChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final Finder data = find.byType(DataTable).first;
    final Finder actions = find.byType(DataTable).last;
    // The precise invariant, and one that does not care what the card's border
    // costs: the pinned column begins exactly where the data ends.
    expect(
      tester.getTopLeft(actions).dx,
      closeTo(tester.getTopRight(data).dx, 1),
    );
    // And the data half filled the space rather than sitting at the intrinsic
    // width of three short columns, which is what left the gap.
    expect(tester.getSize(data).width, greaterThan(1000));
  });

  testWidgets('a grid without row actions stays a single table',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: EnterpriseDataGrid<int>(
            items: const [1, 2],
            total: 2,
            pageOffset: 0,
            columns: const [GridColumn(key: 'record', label: 'Record')],
            id: (item) => '$item',
            cells: (item) => ['Record $item'],
            onSelect: (_) {},
            onPageChanged: (_) {},
          ),
        ),
      ),
    );

    // Nothing to pin, so nothing to split -- and nothing to keep aligned.
    expect(find.byType(DataTable), findsOneWidget);
  });

  testWidgets('a partly filled page renders no blank rows', (tester) async {
    // PaginatedDataTable padded every short page out to rowsPerPage with blank
    // rows, and with a checkbox column each blank drew a disabled checkbox --
    // three records under a 25-row page size meant 22 phantom rows.
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: EnterpriseDataGrid<int>(
            items: const [1, 2, 3],
            total: 3,
            pageOffset: 0,
            rowsPerPage: 25,
            columns: const [GridColumn(key: 'record', label: 'Record')],
            id: (item) => '$item',
            cells: (item) => ['Record $item'],
            onSelect: (_) {},
            onPageChanged: (_) {},
          ),
        ),
      ),
    );

    expect(find.text('Record 1'), findsOneWidget);
    expect(find.text('Record 3'), findsOneWidget);
    // Three records, three rows -- the twenty-two blanks are gone.
    expect(tester.widget<DataTable>(find.byType(DataTable)).rows, hasLength(3));

    // And no checkbox column: this grid declares no multi-selection, so there
    // would be nothing to do with a ticked row.
    expect(
      find.descendant(
        of: find.byType(DataTable),
        matching: find.byType(Checkbox),
      ),
      findsNothing,
    );
  });

  testWidgets(
      'CRUD workspace dialog is single-column with collapsible sections',
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
    // Both sections are visible simultaneously (no tab switching) and start
    // expanded, so their fields are immediately visible together.
    expect(find.text('General'), findsOneWidget);
    expect(find.text('Security'), findsOneWidget);
    expect(find.text('Save & Close'), findsOneWidget);
    expect(find.text('Cancel'), findsOneWidget);
    expect(find.text('Existing user'), findsOneWidget);
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
    expect(find.text('Save & Close'), findsNothing);
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
    await tester.tap(find.text('Save & Close'));
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
    expect(find.text('Welcome back'), findsOneWidget);
  });

  testWidgets('every label in the app can be selected and copied',
      (tester) async {
    // Flutter's `Text` is not selectable, so without this nothing on screen
    // could be highlighted -- an operator had to retype a document number or an
    // id out of an error message by hand.
    final SessionController session = SessionController(
      baseUrl: 'http://localhost:8000',
      tokenStore: _MemoryTokenStore(),
    );

    await tester.pumpWidget(AgencyApp(session: session));
    await tester.pump();

    final Finder selection = find.byType(SelectionArea);
    expect(selection, findsOneWidget);
    // Inside the route, not above the Navigator: `SelectableRegion` needs an
    // `Overlay` ancestor and the Navigator is what supplies one, so wrapping
    // higher throws and takes the screen with it.
    expect(
      find.ancestor(of: selection, matching: find.byType(Navigator)),
      findsWidgets,
    );
    // And the screen still renders through it.
    expect(
      find.descendant(of: selection, matching: find.text('Welcome back')),
      findsOneWidget,
    );
  });

  testWidgets('customer workspace composes the shared management framework',
      (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1366, 768);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    final PermissionService permissions = PermissionService()
      ..applyAccessToken(_accessToken({
        'permissions': [
          'CUSTOMER_VIEW',
          'CUSTOMER_CREATE',
          'CUSTOMER_UPDATE',
          'CUSTOMER_DELETE',
          'CUSTOMER_RESTORE',
          'CUSTOMER_EXPORT',
        ],
      }));

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: CustomerManagementPage(
            api: _CustomerApi(),
            permissions: permissions,
            hasActiveFirm: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('New'), findsOneWidget);
    expect(find.text('CUST-001'), findsOneWidget);
    expect(find.text('Acme Customer'), findsWidgets);
    expect(find.text('1 record'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('customer dialog exposes all master-data tabs without overflow',
      (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1366, 768);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: CustomerWorkspaceDialog(
            mode: CustomerDialogMode.create,
            customer: null,
            onSave: (_) async => _customer,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    for (final String tab in [
      'General',
      'Address',
      'Contacts',
      'Financial',
      'Audit'
    ]) {
      expect(find.text(tab), findsOneWidget);
    }
    expect(find.text('Customer code'), findsOneWidget);
    await tester.tap(find.text('Address'));
    await tester.pumpAndSettle();
    expect(find.text('Add address'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('product workspace composes dynamic metadata-driven controls',
      (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1366, 768);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    final PermissionService permissions = PermissionService()
      ..applyAccessToken(_accessToken({
        'permissions': [
          'PRODUCT_VIEW',
          'PRODUCT_CREATE',
          'PRODUCT_UPDATE',
          'PRODUCT_DELETE',
          'PRODUCT_RESTORE',
          'PRODUCT_EXPORT',
        ],
      }));

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProductManagementPage(
            api: _ProductApi(),
            permissions: permissions,
            preferences: DesktopPreferencesService(),
            hasActiveFirm: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('PROD-001'), findsOneWidget);
    expect(find.text('Pain Relief'), findsOneWidget);
    expect(find.text('1 record'), findsOneWidget);
  });

  testWidgets(
      'product list still loads when attribute definitions are forbidden',
      (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1366, 768);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    final PermissionService permissions = PermissionService()
      ..applyAccessToken(_accessToken({
        'permissions': ['PRODUCT_VIEW'],
      }));

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProductManagementPage(
            api: _ProductApiWithoutAttributeDefinitions(),
            permissions: permissions,
            preferences: DesktopPreferencesService(),
            hasActiveFirm: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('PROD-001'), findsOneWidget);
    expect(find.text('Pain Relief'), findsOneWidget);
    expect(find.text('1 record'), findsOneWidget);
  });
}

String _accessToken(Map<String, dynamic> claims) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '');
  return 'header.$payload.signature';
}

final Customer _customer = Customer.fromJson({
  'id': 'customer-1',
  'firm_id': 'firm-1',
  'code': 'CUST-001',
  'customer_type': 'BUSINESS',
  'name': 'Acme Customer',
  'display_name': 'Acme Customer',
  'gst_number': 'GST-001',
  'pan_number': 'PAN-001',
  'email': 'billing@acme.test',
  'phone': '+919876543210',
  'alternate_phone': '',
  'website': 'https://acme.test',
  'credit_limit': 25000,
  'opening_balance': -150,
  'payment_terms_days': 30,
  'currency_code': 'INR',
  'status': 'ACTIVE',
  'notes': '',
  'created_by': 'user-1',
  'created_at': '2026-07-31T00:00:00Z',
  'updated_by': 'user-1',
  'updated_at': '2026-07-31T00:00:00Z',
  'is_deleted': false,
  'addresses': [
    {
      'id': 'address-1',
      'address_type': 'BILLING',
      'address_line1': '1 Main Street',
      'city': 'Chennai',
      'state': 'Tamil Nadu',
      'country': 'IN',
      'postal_code': '600001',
      'is_default_billing': true,
      'is_default_shipping': false,
    },
  ],
  'contacts': [
    {
      'id': 'contact-1',
      'name': 'Accounts',
      'email': 'accounts@acme.test',
      'is_primary': true,
    },
  ],
});

class _CustomerApi extends ApiClient {
  _CustomerApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  @override
  Future<PagedResult<Customer>> customers({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    CustomerQuery filters = const CustomerQuery(),
  }) async =>
      PagedResult(items: [_customer], total: 1);
}

class _ProductApi extends ApiClient {
  _ProductApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  @override
  Future<PagedResult<Product>> products({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    ProductQuery filters = const ProductQuery(),
  }) async =>
      PagedResult(items: [_product], total: 1);

  @override
  Future<List<ProductCategoryRecord>> productCategories() async => const [
        ProductCategoryRecord(
          id: 'cat-1',
          code: 'MEDICINE',
          name: 'Medicine',
          parentId: '',
          level: 0,
          path: 'MEDICINE',
          isActive: true,
        ),
      ];

  @override
  Future<PagedResult<AttributeDefinitionRecord>> attributeDefinitions({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) async =>
      const PagedResult(
        items: [
          AttributeDefinitionRecord(
            id: 'attr-1',
            code: 'EXPIRY_DATE',
            name: 'Expiry Date',
            dataType: 'DATE',
            entityType: 'PRODUCT',
            mandatory: true,
            isActive: true,
            applicableCategory: 'MEDICINE',
            description: '',
            defaultValue: '',
            applicableBusinessProfileId: '',
          )
        ],
        total: 1,
      );

  @override
  Future<ProductMetadataRecord> productMetadata({String? categoryId}) async =>
      const ProductMetadataRecord(
        profileCode: 'MEDICAL',
        features: [ProductFeatureState(code: 'BARCODE', enabled: true)],
        categories: [
          ProductCategoryRecord(
            id: 'cat-1',
            code: 'MEDICINE',
            name: 'Medicine',
            parentId: '',
            level: 0,
            path: 'MEDICINE',
            isActive: true,
          )
        ],
        taxProfiles: [],
        requiredAttributeDefinitionIds: ['attr-1'],
        optionalAttributeDefinitionIds: [],
      );
}

final Product _product = Product.fromJson({
  'id': 'product-1',
  'firm_id': 'firm-1',
  'code': 'PROD-001',
  'name': 'Pain Relief',
  'product_type': 'STOCK_ITEM',
  'status': 'ACTIVE',
  'selling_price': '120.00',
  'is_deleted': false,
  'category_id': 'cat-1',
  'attributes': [],
  'media': [],
});
