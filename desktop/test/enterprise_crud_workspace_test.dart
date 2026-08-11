import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The CRUD workspace is the shell every master and transaction screen reuses,
/// so a regression here is a regression in every module at once. These tests
/// pin the behaviour the modules are entitled to assume: that search reaches
/// the server once rather than per keystroke, that a page-size control only
/// exists when the request can carry it, that an empty table explains which
/// kind of empty it is, and that bulk actions are never offered where the
/// backend has none.

String _accessToken(Map<String, dynamic> claims) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '');
  return 'header.$payload.signature';
}

PermissionService _withPermissions(List<String> permissions) {
  final PermissionService service = PermissionService();
  service.applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': permissions,
  }));
  return service;
}

class _ListRequest {
  const _ListRequest({
    required this.page,
    required this.pageSize,
    required this.search,
    required this.filters,
  });

  final int page;
  final int pageSize;
  final String search;
  final Map<String, String> filters;
}

class _WorkspaceApi extends ApiClient {
  _WorkspaceApi({this.total = 3, this.failWith})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final int total;
  final String? failWith;
  final List<_ListRequest> requests = <_ListRequest>[];
  final List<String> deleted = <String>[];

  List<Permission> _rows(int count) => [
        for (int index = 0; index < count; index++)
          Permission(
            id: 'permission-$index',
            code: 'JOURNAL_POST_$index',
            name: 'Journal Posting $index',
            description: '',
            isActive: index.isEven,
          ),
      ];

  @override
  Future<PagedResult<Permission>> permissions({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) async {
    requests.add(
      _ListRequest(
        page: page,
        pageSize: pageSize,
        search: search,
        filters: const {},
      ),
    );
    final String? failure = failWith;
    if (failure != null) throw ApiException(failure);
    final int count = search.isEmpty ? total : 0;
    return PagedResult(items: _rows(count), total: count);
  }

  @override
  Future<void> delete(String resource, String id) async => deleted.add(id);
}

/// These are desktop screens; the 800x600 default pushes the Actions column
/// out of the viewport and makes taps miss.
void _desktopViewport(WidgetTester tester) {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1600, 900);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

Widget _host(Widget child) => MaterialApp(home: Scaffold(body: child));

Widget _permissionsPage(
  _WorkspaceApi api, {
  List<String> permissions = const [
    'PERMISSION_VIEW',
    'PERMISSION_CREATE',
    'PERMISSION_UPDATE',
    'PERMISSION_DELETE',
  ],
}) =>
    _host(
      ResourceManagementPage<Permission>(
        api: api,
        definition: permissionDefinition(
          api,
          _withPermissions(permissions),
          showFrame: false,
        ),
      ),
    );

void main() {
  group('Permissions as the reference implementation', () {
    testWidgets('leads with the readable name and keeps the code',
        (tester) async {
      _desktopViewport(tester);
      final api = _WorkspaceApi();
      await tester.pumpWidget(_permissionsPage(api));
      await tester.pumpAndSettle();

      final ResourceDefinition<Permission> definition = permissionDefinition(
        api,
        _withPermissions(const ['PERMISSION_VIEW']),
      );
      // An administrator scans for "Journal Posting", not JOURNAL_POST.
      expect(definition.headers.first, 'Permission');
      expect(definition.headers[1], 'Code');
      expect(find.text('Journal Posting 0'), findsOneWidget);
      expect(find.text('JOURNAL_POST_0'), findsOneWidget);
    });

    testWidgets('names what it can be searched by', (tester) async {
      _desktopViewport(tester);
      final api = _WorkspaceApi();
      await tester.pumpWidget(_permissionsPage(api));
      await tester.pumpAndSettle();

      expect(find.text('Search permissions by name or code'), findsOneWidget);
    });

    test('declares no filters, because the endpoint accepts none', () {
      final api = _WorkspaceApi();
      final ResourceDefinition<Permission> definition = permissionDefinition(
        api,
        _withPermissions(const ['PERMISSION_VIEW']),
      );

      expect(definition.filters, isEmpty);
      expect(definition.bulkActions, isEmpty);
    });
  });

  group('search', () {
    testWidgets('debounces typing into a single request', (tester) async {
      _desktopViewport(tester);
      final api = _WorkspaceApi();
      await tester.pumpWidget(_permissionsPage(api));
      await tester.pumpAndSettle();
      expect(api.requests.length, 1);

      await tester.enterText(find.byType(TextField).first, 'jou');
      await tester.pump(const Duration(milliseconds: 100));
      await tester.enterText(find.byType(TextField).first, 'jour');
      await tester.pump(const Duration(milliseconds: 100));
      await tester.enterText(find.byType(TextField).first, 'journal');
      // Still inside the debounce window: nothing has been asked for yet.
      await tester.pump(const Duration(milliseconds: 100));
      expect(api.requests.length, 1);

      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();

      // Three keystrokes, one request -- not one request per character.
      expect(api.requests.length, 2);
      expect(api.requests.last.search, 'journal');
    });

    testWidgets('offers a clear button only once there is text',
        (tester) async {
      _desktopViewport(tester);
      final api = _WorkspaceApi();
      await tester.pumpWidget(_permissionsPage(api));
      await tester.pumpAndSettle();

      expect(find.byTooltip('Clear search'), findsNothing);

      await tester.enterText(find.byType(TextField).first, 'journal');
      await tester.pumpAndSettle();
      expect(find.byTooltip('Clear search'), findsOneWidget);

      await tester.tap(find.byTooltip('Clear search'));
      await tester.pumpAndSettle();
      expect(api.requests.last.search, '');
      expect(find.text('Journal Posting 0'), findsOneWidget);
    });
  });

  group('paging', () {
    testWidgets('a page-size change reaches the server', (tester) async {
      _desktopViewport(tester);
      final api = _WorkspaceApi();
      await tester.pumpWidget(_permissionsPage(api));
      await tester.pumpAndSettle();
      expect(api.requests.first.pageSize, 25);

      // Driven through the grid's own callback rather than PaginatedDataTable's
      // footer layout, which is Flutter's to change.
      final EnterpriseDataGrid<Permission> grid =
          tester.widget(find.byType(EnterpriseDataGrid<Permission>));
      expect(grid.availableRowsPerPage, const [25, 50, 100]);
      grid.onRowsPerPageChanged!(50);
      await tester.pumpAndSettle();

      // The number in the selector is worthless unless the request carries it.
      expect(api.requests.last.pageSize, 50);
      expect(api.requests.last.page, 1);
    });
  });

  group('states', () {
    testWidgets('an empty search result offers to clear it', (tester) async {
      _desktopViewport(tester);
      final api = _WorkspaceApi();
      await tester.pumpWidget(_permissionsPage(api));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField).first, 'nothing-matches');
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();

      expect(find.text('No permissions found'), findsOneWidget);
      expect(find.text('Clear filters'), findsOneWidget);

      await tester.tap(find.text('Clear filters'));
      await tester.pumpAndSettle();
      expect(find.text('Journal Posting 0'), findsOneWidget);
    });

    testWidgets('a genuinely empty table offers to create instead',
        (tester) async {
      _desktopViewport(tester);
      final api = _WorkspaceApi(total: 0);
      await tester.pumpWidget(_permissionsPage(api));
      await tester.pumpAndSettle();

      expect(find.text('No permissions yet'), findsOneWidget);
      expect(find.text('Create permission'), findsOneWidget);
      expect(find.text('Clear filters'), findsNothing);
    });

    testWidgets('an empty table offers no create without the permission',
        (tester) async {
      _desktopViewport(tester);
      final api = _WorkspaceApi(total: 0);
      await tester.pumpWidget(
        _permissionsPage(api, permissions: const ['PERMISSION_VIEW']),
      );
      await tester.pumpAndSettle();

      expect(find.text('No permissions yet'), findsOneWidget);
      expect(find.text('Create permission'), findsNothing);
    });

    testWidgets('a failed load explains itself and offers a retry',
        (tester) async {
      _desktopViewport(tester);
      final api = _WorkspaceApi(failWith: 'The server is unavailable.');
      await tester.pumpWidget(_permissionsPage(api));
      await tester.pumpAndSettle();

      expect(find.text('The server is unavailable.'), findsOneWidget);
      expect(find.widgetWithText(OutlinedButton, 'Try again'), findsOneWidget);
    });
  });

  group('row and bulk actions', () {
    testWidgets('a row shows view and edit, and hides the rest in a menu',
        (tester) async {
      _desktopViewport(tester);
      final api = _WorkspaceApi();
      await tester.pumpWidget(_permissionsPage(api));
      await tester.pumpAndSettle();

      // Scoped to the table: the toolbar carries its own View/Edit tooltips.
      Finder inGrid(String tooltip) => find.descendant(
            of: find.byType(DataTable),
            matching: find.byTooltip(tooltip),
          );

      // One eye and one pencil per row, not one icon per available action.
      expect(inGrid('View'), findsNWidgets(3));
      expect(inGrid('Edit'), findsNWidgets(3));
      expect(inGrid('Delete'), findsNothing);
      expect(inGrid('More actions'), findsNWidgets(3));

      await tester.tap(find.byIcon(Icons.more_vert).first);
      await tester.pumpAndSettle();
      expect(find.text('Delete'), findsOneWidget);
      expect(find.text('Copy row'), findsOneWidget);
    });

    testWidgets('row actions respect the permission model', (tester) async {
      _desktopViewport(tester);
      final api = _WorkspaceApi();
      await tester.pumpWidget(
        _permissionsPage(api, permissions: const ['PERMISSION_VIEW']),
      );
      await tester.pumpAndSettle();

      Finder inGrid(String tooltip) => find.descendant(
            of: find.byType(DataTable),
            matching: find.byTooltip(tooltip),
          );

      expect(inGrid('View'), findsNWidgets(3));
      expect(inGrid('Edit'), findsNothing);
    });

    testWidgets('selecting a row selects it and opens nothing beside the table',
        (tester) async {
      _desktopViewport(tester);
      final api = _WorkspaceApi();
      await tester.pumpWidget(_permissionsPage(api));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Journal Posting 0'));
      // Rows carry a double-tap handler, so a single tap is held for the
      // double-tap timeout before it resolves. pumpAndSettle does not flush
      // that timer.
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();

      // A single click used to open a summary panel that re-read the row and
      // took ~300px from the table. Opening a record is double-click's job.
      expect(find.byType(QuickSummaryPanel), findsNothing);
      expect(find.text('Selected Permissions'), findsNothing);

      // The selection is still real: the status bar reports it.
      expect(find.textContaining('1 selected'), findsOneWidget);
    });

    testWidgets('double-clicking a row opens it', (tester) async {
      _desktopViewport(tester);
      final api = _WorkspaceApi();
      await tester.pumpWidget(_permissionsPage(api));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Journal Posting 0'));
      // The recognizer discards a second tap that arrives sooner than
      // kDoubleTapMinTime, so the two taps need a gap between them.
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(find.text('Journal Posting 0'));
      await tester.pumpAndSettle();

      // The view dialog is read-only, so Close is its only footer action.
      expect(find.text('Close'), findsOneWidget);
    });

    testWidgets('paging reports a row offset, not a page number',
        (tester) async {
      // Every caller converts with `offset ~/ rowsPerPage + 1`, so this
      // contract has to survive the move off PaginatedDataTable.
      _desktopViewport(tester);
      final List<int> offsets = <int>[];
      await tester.pumpWidget(
        _host(
          EnterpriseDataGrid<int>(
            items: List.generate(25, (index) => index),
            total: 164,
            pageOffset: 0,
            rowsPerPage: 25,
            columns: const [GridColumn(key: 'record', label: 'Record')],
            id: (item) => '$item',
            cells: (item) => ['Record $item'],
            onSelect: (_) {},
            onPageChanged: offsets.add,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('1–25 of 164'), findsOneWidget);
      await tester.tap(find.byTooltip('Next page'));
      await tester.pumpAndSettle();

      expect(offsets, [25]);
    });

    testWidgets('a module with no bulk actions offers no checkbox column',
        (tester) async {
      _desktopViewport(tester);
      final api = _WorkspaceApi();
      await tester.pumpWidget(_permissionsPage(api));
      await tester.pumpAndSettle();

      // Permissions has no bulk endpoint. A checkbox whose only outcome is a
      // count of what you ticked is a column spent on nothing.
      expect(find.byType(Checkbox), findsNothing);
    });

    testWidgets('a module with bulk actions gets the checkbox and the bar',
        (tester) async {
      _desktopViewport(tester);
      final api = _WorkspaceApi();
      Set<String>? invokedWith;
      final ResourceDefinition<Permission> base = permissionDefinition(
        api,
        _withPermissions(const ['PERMISSION_VIEW', 'PERMISSION_DELETE']),
        showFrame: false,
      );
      final ResourceDefinition<Permission> withBulk = ResourceDefinition(
        title: base.title,
        resource: base.resource,
        headers: base.headers,
        cells: base.cells,
        id: base.id,
        load: base.load,
        fields: base.fields,
        initialValues: base.initialValues,
        payload: base.payload,
        showFrame: false,
        bulkActions: [
          WorkspaceBulkAction(
            label: 'Deactivate',
            icon: Icons.block,
            onInvoke: (ids) async {
              invokedWith = ids;
              return '${ids.length} deactivated.';
            },
          ),
        ],
      );

      await tester.pumpWidget(
        _host(
            ResourceManagementPage<Permission>(api: api, definition: withBulk)),
      );
      await tester.pumpAndSettle();

      expect(find.byType(Checkbox), findsWidgets);
      await tester.tap(find.byType(Checkbox).at(1));
      await tester.pumpAndSettle();

      expect(find.text('1 selected'), findsOneWidget);
      await tester.tap(find.widgetWithText(TextButton, 'Deactivate'));
      await tester.pumpAndSettle();

      expect(invokedWith, hasLength(1));
      // The selection clears once the action has been applied.
      expect(find.text('1 selected'), findsNothing);
    });

    testWidgets('clicking a row marks it selected, not just the toolbar',
        (tester) async {
      _desktopViewport(tester);
      final api = _WorkspaceApi();
      await tester.pumpWidget(_permissionsPage(api));
      await tester.pumpAndSettle();

      // Two tables now: the scrolling data half, then the pinned Actions half.
      // The data half is first.
      DataRow rowFor(String text) => tester
          .widget<DataTable>(find.byType(DataTable).first)
          .rows
          .firstWhere(
            (row) => row.cells.any(
              (cell) => find
                  .descendant(
                    of: find.byWidget(cell.child),
                    matching: find.text(text),
                  )
                  .evaluate()
                  .isNotEmpty,
            ),
          );

      expect(rowFor('Journal Posting 0').selected, isFalse);

      await tester.tap(find.text('Journal Posting 0'));
      // Rows carry a double-tap handler, so the single tap is held for the
      // double-tap timeout before it resolves.
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();

      // The row's appearance used to be driven only by the checkbox, so a
      // clicked row enabled the toolbar and looked untouched.
      expect(rowFor('Journal Posting 0').selected, isTrue);
      expect(rowFor('Journal Posting 1').selected, isFalse);
    });
  });
}
