import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/audit.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/settings/audit_log_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The audit trail.
///
/// Every mutation has written one since the platform started, and a database
/// trigger in every store makes the table append-only, with nothing in the
/// client able to read a single row.
PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

class _AuditApi extends ApiClient {
  _AuditApi({this.rows = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<AuditLogEntry> rows;
  String? requestedAction;

  @override
  Future<PagedResult<AuditLogEntry>> auditLogs({
    int page = 1,
    int pageSize = 20,
    String? action,
    String? entityType,
    String? dateFrom,
    String? dateTo,
  }) async {
    requestedAction = action;
    return PagedResult<AuditLogEntry>(items: rows, total: rows.length);
  }
}

AuditLogEntry _entry({
  String action = 'customer.updated',
  Json before = const {'name': 'Acme', 'credit_limit': '1000.00'},
  Json after = const {'name': 'Acme', 'credit_limit': '5000.00'},
}) =>
    AuditLogEntry.fromJson({
      'id': 'a-1',
      'created_at': '2026-08-14T06:00:00Z',
      'action': action,
      'entity_type': 'customer',
      'entity_id': 'c-1',
      'actor_id': 'u-1',
      'firm_id': 'firm-1',
      'before_data': before,
      'after_data': after,
      'ip_address': '10.0.0.4',
      'application_version': '1.0.0',
    });

Future<void> _pump(
  WidgetTester tester,
  _AuditApi api, {
  List<String> perms = const ['AUDIT_LOG_VIEW'],
  String? firmLabel = 'Wholesale Hub',
}) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: AuditLogPage(
          api: api,
          permissions: _permissionsFor(perms),
          firmLabel: firmLabel,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('reading an entry', () {
    test('only the fields that actually moved are changes', () {
      // An audit row carries whole snapshots on both sides. Showing every
      // field buries the one somebody is looking for.
      final AuditLogEntry entry = _entry();
      expect(entry.changes.map((c) => c.field).toList(), ['credit_limit']);
      expect(entry.changes.single.before, '1000.00');
      expect(entry.changes.single.after, '5000.00');
    });

    test('a creation has no earlier version', () {
      final AuditLogEntry entry = _entry(
        action: 'customer.created',
        before: const {},
        after: const {'name': 'Acme'},
      );
      expect(entry.hasBothSides, isFalse);
      expect(entry.changes.single.before, '');
    });

    test('a deletion has nothing after it', () {
      final AuditLogEntry entry = _entry(
        action: 'customer.deleted',
        before: const {'name': 'Acme'},
        after: const {},
      );
      expect(entry.afterData, isEmpty);
      expect(entry.changes.single.after, '');
    });
  });

  group('the audit screen', () {
    testWidgets('a change shows what it was and what it became',
        (tester) async {
      await _pump(tester, _AuditApi(rows: [_entry()]));

      expect(find.text('credit_limit'), findsOneWidget);
      expect(find.text('1000.00'), findsOneWidget);
      expect(find.text('5000.00'), findsOneWidget);
      expect(find.text('name'), findsNothing, reason: 'it did not change');
    });

    testWidgets('it says which trail this is', (tester) async {
      // The trail is per store. A reader who takes this for everything will
      // conclude that something they cannot see never happened.
      await _pump(tester, _AuditApi(rows: [_entry()]));
      expect(
        find.textContaining('The trail for Wholesale Hub'),
        findsOneWidget,
      );
      expect(find.textContaining('in their own stores'), findsOneWidget);
    });

    testWidgets('the platform trail says what it holds', (tester) async {
      await _pump(tester, _AuditApi(rows: [_entry()]), firmLabel: null);
      expect(find.textContaining('The platform trail'), findsOneWidget);
    });

    testWidgets('an empty result explains itself', (tester) async {
      // Every mutation writes a row, so "nothing here" means the wrong store
      // or the wrong filter -- not that nothing happened.
      await _pump(tester, _AuditApi());
      expect(find.textContaining('a different store'), findsOneWidget);
    });

    testWidgets('searching by action passes the filter through',
        (tester) async {
      final _AuditApi api = _AuditApi(rows: [_entry()]);
      await _pump(tester, api);

      await tester.enterText(
        find.widgetWithText(TextField, 'Action'),
        'settlement.receipt.reversed',
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Search'));
      await tester.pumpAndSettle();

      expect(api.requestedAction, 'settlement.receipt.reversed');
    });

    testWidgets('without AUDIT_LOG_VIEW there is nothing to show',
        (tester) async {
      await _pump(tester, _AuditApi(), perms: const ['SETTINGS_VIEW']);
      expect(find.textContaining('do not have permission'), findsOneWidget);
    });
  });
}
