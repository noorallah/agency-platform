import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/diagnostics.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/settings/diagnostics_page.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The crash log.
///
/// The desktop has queued reports to disk and flushed them to the server since
/// the crash reporter was written, and the server records its own failures
/// beside them, with nothing in the client able to read one back. Faults were
/// collected and nobody could look at them.
PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

class _DiagnosticsApi extends ApiClient {
  _DiagnosticsApi({
    this.groups = const [],
    this.occurrences = const [],
    this.occurrencesFail = false,
  }) : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<ErrorReportGroup> groups;
  final List<ErrorReport> occurrences;
  final bool occurrencesFail;
  String? requestedSource;
  String? requestedSearch;
  int? requestedPageSize;
  final List<String> occurrencesFor = [];

  @override
  Future<PagedResult<ErrorReportGroup>> errorGroups({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? source,
  }) async {
    requestedSource = source;
    requestedSearch = search;
    requestedPageSize = pageSize;
    return PagedResult<ErrorReportGroup>(
      items: groups,
      total: groups.length,
    );
  }

  @override
  Future<List<ErrorReport>> errorOccurrences(String fingerprint) async {
    occurrencesFor.add(fingerprint);
    if (occurrencesFail) {
      throw ApiException('Diagnostics are unavailable.', statusCode: 503);
    }
    return occurrences;
  }
}

ErrorReportGroup _group({
  String fingerprint = 'fp-1',
  String source = 'CLIENT',
  String errorType = 'StateError',
  String message = 'Bad state: no active firm',
  int occurrences = 42,
}) =>
    ErrorReportGroup.fromJson({
      'fingerprint': fingerprint,
      'source': source,
      'error_type': errorType,
      'message': message,
      'occurrences': occurrences,
      'first_seen': '2026-08-01T06:00:00Z',
      'last_seen': '2026-08-20T09:30:00Z',
      'app_versions': ['1.0.0', '1.1.0'],
    });

ErrorReport _report({
  String id = 'r-1',
  String fingerprint = 'fp-1',
  List<String> breadcrumbs = const ['opened customers', 'tapped save'],
}) =>
    ErrorReport.fromJson({
      'id': id,
      'source': 'CLIENT',
      'fingerprint': fingerprint,
      'error_type': 'StateError',
      'message': 'Bad state: no active firm',
      'stack_trace': '#0 CustomerPage.save (customer_page.dart:120)',
      'app_version': '1.1.0',
      'build_number': '431',
      'platform_info': 'windows 11',
      'firm_id': 'firm-1',
      'user_id': 'user-1',
      'request_id': 'req-9',
      'context_label': 'customer save',
      'breadcrumbs': breadcrumbs,
      'occurred_at': '2026-08-20T09:29:00Z',
      'received_at': '2026-08-20T09:30:00Z',
    });

Future<void> _pump(
  WidgetTester tester,
  _DiagnosticsApi api, {
  List<String> perms = const ['DIAGNOSTICS_VIEW'],
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: DiagnosticsPage(
          api: api,
          permissions: _permissionsFor(perms),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('reaching the screen', () {
    ModuleDefinition settings() => ModuleCatalog.byId(AppModule.settings);

    bool sees(PermissionService perms, ModuleDefinition module) =>
        perms.canAccess(module.requiredPermissions,
            requiresAny: module.requiresAnyPermission);

    bool seesTab(PermissionService perms, String id) {
      final ModuleTabDefinition tab =
          settings().tabs.firstWhere((tab) => tab.id == id);
      return perms.canAccess(tab.requiredPermissions,
          requiresAny: tab.requiresAnyPermission);
    }

    test('the auditor role can open the workspace it exists to read', () {
      // SYSTEM_AUDITOR holds AUDIT_LOG_VIEW and DIAGNOSTICS_VIEW and no
      // SETTINGS_VIEW. Demanding all three hid the workspace from the one
      // role that exists to read what is in it.
      final PermissionService auditor = _permissionsFor(
        const ['FIRM_VIEW', 'USER_VIEW', 'AUDIT_LOG_VIEW', 'DIAGNOSTICS_VIEW'],
      );
      expect(sees(auditor, settings()), isTrue);
      expect(seesTab(auditor, 'diagnostics'), isTrue);
      expect(seesTab(auditor, 'audit-logs'), isTrue);
    });

    test('seeing the workspace is not seeing both trails', () {
      // The two tabs answer to different people, and each carries its own
      // code, so reaching the module must not hand over the other one.
      final PermissionService settingsOnly =
          _permissionsFor(const ['SETTINGS_VIEW']);
      expect(sees(settingsOnly, settings()), isTrue);
      expect(seesTab(settingsOnly, 'diagnostics'), isFalse);
      expect(seesTab(settingsOnly, 'audit-logs'), isFalse);
    });

    test('holding none of the three keeps the workspace hidden', () {
      expect(sees(_permissionsFor(const ['CUSTOMER_VIEW']), settings()),
          isFalse);
    });
  });

  group('reading a group', () {
    test('the count and the versions come down with the fault', () {
      final ErrorReportGroup group = _group();
      expect(group.occurrences, 42);
      expect(group.appVersions, ['1.0.0', '1.1.0']);
    });

    test('a report with no stack trace parses to empty, not null', () {
      final ErrorReport row = ErrorReport.fromJson({
        'id': 'r-2',
        'source': 'SERVER',
        'fingerprint': 'fp-2',
        'error_type': 'IntegrityError',
        'message': 'duplicate key',
        'stack_trace': null,
        'breadcrumbs': null,
        'received_at': '2026-08-20T09:30:00Z',
      });
      expect(row.stackTrace, isEmpty);
      expect(row.breadcrumbs, isEmpty);
      expect(row.occurredAt, isEmpty);
    });
  });

  group('the diagnostics screen', () {
    testWidgets('a fault shows how often it happened', (tester) async {
      // The count is what ranks the work: one fault seen 42 times is the one
      // to fix first, and a list of 42 identical rows would say the same thing
      // unreadably.
      await _pump(tester, _DiagnosticsApi(groups: [_group()]));

      expect(find.text('StateError'), findsWidgets);
      expect(find.text('42×'), findsOneWidget);
      expect(find.textContaining('42 occurrences'), findsOneWidget);
      expect(find.textContaining('Versions 1.0.0, 1.1.0'), findsOneWidget);
    });

    testWidgets('the first fault opens with its occurrences', (tester) async {
      final _DiagnosticsApi api = _DiagnosticsApi(
        groups: [_group()],
        occurrences: [_report()],
      );
      await _pump(tester, api);

      expect(api.occurrencesFor, ['fp-1']);
      await tester.tap(find.text('2026-08-20T09:29:00Z'));
      await tester.pumpAndSettle();
      expect(find.textContaining('customer_page.dart:120'), findsOneWidget);
      expect(find.textContaining('opened customers'), findsOneWidget);
      // The one field that ties a client crash to the server's own logs.
      expect(find.textContaining('Request req-9'), findsOneWidget);
    });

    testWidgets('choosing another fault reads that one', (tester) async {
      final _DiagnosticsApi api = _DiagnosticsApi(
        groups: [
          _group(),
          _group(
            fingerprint: 'fp-2',
            source: 'SERVER',
            errorType: 'IntegrityError',
            message: 'duplicate key value violates unique constraint',
            occurrences: 3,
          ),
        ],
        occurrences: [_report()],
      );
      await _pump(tester, api);

      await tester.tap(find.text('IntegrityError'));
      await tester.pumpAndSettle();

      expect(api.occurrencesFor, ['fp-1', 'fp-2']);
      expect(find.textContaining('3 occurrences'), findsOneWidget);
    });

    testWidgets('the source filter reaches the API', (tester) async {
      final _DiagnosticsApi api = _DiagnosticsApi(groups: [_group()]);
      await _pump(tester, api);

      await tester.tap(find.byType(DropdownButtonFormField<String>));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Server').last);
      await tester.pumpAndSettle();

      expect(api.requestedSource, 'SERVER');
    });

    testWidgets('it asks for a page size the server accepts', (tester) async {
      // MAX_PAGE_SIZE is 100 and the endpoint now refuses more with a 422.
      // Two screens have already shipped asking for 500.
      final _DiagnosticsApi api = _DiagnosticsApi(groups: [_group()]);
      await _pump(tester, api);
      expect(api.requestedPageSize, lessThanOrEqualTo(100));
    });

    testWidgets('it says this is every firm at once', (tester) async {
      // The opposite of the audit trail beside it, which shows one store.
      await _pump(tester, _DiagnosticsApi(groups: [_group()]));
      expect(find.textContaining('Every firm at once'), findsOneWidget);
    });

    testWidgets('an empty result explains the delay', (tester) async {
      // Clients queue on disk until they can sign in, so "nothing" can mean
      // "not yet" rather than "nothing failed".
      await _pump(tester, _DiagnosticsApi());
      expect(find.textContaining('queue reports on disk'), findsOneWidget);
    });

    testWidgets('a failed occurrence read does not look like no data',
        (tester) async {
      final _DiagnosticsApi api = _DiagnosticsApi(
        groups: [_group()],
        occurrencesFail: true,
      );
      await _pump(tester, api);

      expect(find.textContaining('Could not read the occurrences'),
          findsOneWidget);
      expect(find.textContaining('Diagnostics are unavailable'), findsOneWidget);
    });

    testWidgets('without DIAGNOSTICS_VIEW there is nothing to show',
        (tester) async {
      final _DiagnosticsApi api = _DiagnosticsApi(groups: [_group()]);
      await _pump(tester, api, perms: const ['SETTINGS_VIEW']);

      expect(find.textContaining('do not have permission'), findsOneWidget);
      // And it must not have asked: a screen that reads and then hides the
      // answer is a leak waiting for a rendering bug.
      expect(api.requestedSource, isNull);
      expect(api.occurrencesFor, isEmpty);
    });
  });
}
