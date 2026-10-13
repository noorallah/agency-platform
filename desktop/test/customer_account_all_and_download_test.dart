// The Account view's whole account, its sheet and its remembered choice
// (backlog 141, F10). What it must not do: read an account of thousands of
// entries in one go, put on the sheet fewer rows than the choice holds, offer
// the row that adds a receipt before the last entry is on the screen, or
// keep asking for a page the server refused.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/phase2/phase2_scope.dart';
import 'package:agency_desktop/ui/customers/customer_statement_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/workbook_cells.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({String user = 'user-1'}) => PermissionService()
  ..applyAccessToken(_accessToken({
    'sub': user,
    'roles': <String>['user'],
    'permissions': <String>['CUSTOMER_VIEW', 'RECEIPT_CREATE'],
  }));

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('account-view'),
    );

/// An account of [entries] bills of 10.00 each, numbered from 1, so entry
/// n leaves a balance of n times ten.
class _AccountApi extends ApiClient {
  _AccountApi({this.entries = 250})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final int entries;

  /// Refuse a read that passes over entries, while this is set.
  String? refuseLaterPagesWith;

  final List<Map<String, String>> accountReads = <Map<String, String>>[];

  Json _line(int number) => <String, dynamic>{
        'transaction_date': '2026-04-01',
        'transaction_type': 'INVOICE',
        'reference_number': 'SI-$number',
        'remarks': '',
        'debit': '10.00',
        'credit': '0.00',
        'balance': '${number * 10}.00',
      };

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
    final Map<String, String> asked = query ?? const <String, String>{};
    if (path.endsWith('/account')) {
      accountReads.add(asked);
      final int last = int.parse(asked['last']!);
      final int skip = int.parse(asked['skip'] ?? '0');
      if (skip > 0 && refuseLaterPagesWith != null) {
        throw ApiException(refuseLaterPagesWith!, statusCode: 503);
      }
      final int first;
      final int end;
      if (asked['from_start'] == 'true') {
        first = skip + 1;
        end = (skip + last).clamp(0, entries);
      } else {
        end = entries - skip;
        first = (end - last + 1).clamp(1, entries);
      }
      return <String, dynamic>{
        'data': <String, dynamic>{
          'customer_id': 'cust-1',
          'customer_name': 'Kumar Stores',
          'opening_balance': '${(first - 1) * 10}.00',
          'closing_balance': '${end * 10}.00',
          'total_entries': entries,
          'lines': <Json>[for (int n = first; n <= end; n++) _line(n)],
        },
      };
    }
    if (path.endsWith('/receipts/outstanding')) {
      return <String, dynamic>{'data': <Json>[]};
    }
    return <String, dynamic>{
      'data': <Json>[
        <String, dynamic>{
          'customer_id': 'cust-1',
          'customer_code': 'C1',
          'customer_name': 'Kumar Stores',
          'total_outstanding': '2500.00',
          'buckets': <Json>[],
        },
      ],
    };
  }
}

/// Open the page in the new UI, pick Kumar Stores, and switch to Account.
Future<void> _openAccount(
  WidgetTester tester,
  _AccountApi api, {
  PermissionService? permissions,
  DesktopPreferencesService? preferences,
}) async {
  tester.view.physicalSize = const Size(1600, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    // A fresh page each time: the second opening is a new sign-in.
    key: UniqueKey(),
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: CustomerStatementPage(
        api: api,
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
        preferences: preferences,
      ),
    ),
  ));
  await tester.pumpAndSettle();
  // The new UI opens a customer on a double click.
  final Finder row = find.text('Kumar Stores').first;
  await tester.tap(row);
  await tester.pump(const Duration(milliseconds: 50));
  await tester.tap(row);
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('view-account')));
  await tester.pumpAndSettle();
}

Future<void> _choose(WidgetTester tester, String label) async {
  await tester.tap(find.byKey(const ValueKey('account-last-chooser')));
  await tester.pumpAndSettle();
  await tester.tap(find.text(label).last);
  await tester.pumpAndSettle();
}

/// Scroll the account's rows to their end, as far as they are read.
Future<void> _toTheEnd(WidgetTester tester) async {
  final ScrollableState rows = tester.state<ScrollableState>(
    find
        .ancestor(
          of: find.text('SI-1'),
          matching: find.byWidgetPredicate(
            (widget) =>
                widget is Scrollable &&
                widget.axisDirection == AxisDirection.down,
          ),
        )
        .first,
  );
  rows.position.jumpTo(rows.position.maxScrollExtent);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('All opens on the first entry and reads one page', (tester) async {
    final _AccountApi api = _AccountApi();
    await _openAccount(tester, api);
    api.accountReads.clear();

    await _choose(tester, 'Show all');

    expect(api.accountReads, [
      {'last': '100', 'from_start': 'true'},
    ]);
    expect(find.textContaining('The first 100 of 250 entries'), findsOneWidget);
    expect(find.text('SI-1'), findsOneWidget);
    // The whole account opens at nothing.
    expect(find.text('Opening balance'), findsNothing);
    // More is to come, so the row that adds a receipt is not there yet.
    expect(find.byKey(const ValueKey('account-more')), findsOneWidget);
    expect(find.byKey(const ValueKey('account-row-add')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('scrolling to the end reads the next page, until the last',
      (tester) async {
    final _AccountApi api = _AccountApi();
    await _openAccount(tester, api);
    await _choose(tester, 'Show all');
    api.accountReads.clear();

    await _toTheEnd(tester);
    expect(api.accountReads, [
      {'last': '100', 'from_start': 'true', 'skip': '100'},
    ]);
    expect(find.textContaining('The first 200 of 250 entries'), findsOneWidget);

    await _toTheEnd(tester);
    expect(api.accountReads.last,
        {'last': '100', 'from_start': 'true', 'skip': '200'});
    expect(find.textContaining('All 250 entries'), findsOneWidget);
    expect(find.byKey(const ValueKey('account-more')), findsNothing);

    // The last entry closes on the account's balance, and the row follows it.
    await _toTheEnd(tester);
    expect(find.text('SI-250'), findsOneWidget);
    expect(find.text('2500.00'), findsOneWidget);
    expect(find.byKey(const ValueKey('account-row-add')), findsOneWidget);
    // Nothing is left to read, so nothing more is asked.
    expect(api.accountReads, hasLength(2));
    expect(tester.takeException(), isNull);
  });

  testWidgets('a short account under All is read once and has its row',
      (tester) async {
    final _AccountApi api = _AccountApi(entries: 3);
    await _openAccount(tester, api);
    api.accountReads.clear();

    await _choose(tester, 'Show all');

    expect(api.accountReads, hasLength(1));
    expect(find.textContaining('All 3 entries'), findsOneWidget);
    expect(find.byKey(const ValueKey('account-row-add')), findsOneWidget);
  });

  testWidgets('Download under All writes every entry, read in pages of 200',
      (tester) async {
    final _AccountApi api = _AccountApi();
    await _openAccount(tester, api);
    await _choose(tester, 'Show all');
    api.accountReads.clear();

    final List<String> name = <String>[];
    final List<List<Object?>> cells = await downloadedSheet(tester, name: name);

    expect(api.accountReads, [
      {'last': '200', 'from_start': 'true', 'skip': '100'},
    ]);
    expect(name.single, contains('customer-account'));
    expect(cells[0][0], 'Customer account: Kumar Stores');
    expect(cells[1][0], 'All 250 entries');
    final int head = cells.indexWhere((row) => row.isNotEmpty && row[0] == 'Date');
    expect(cells[head], [
      'Date',
      'Type',
      'Reference',
      'Remarks',
      'Debit',
      'Credit',
      'Balance',
    ]);
    final List<List<Object?>> rows = cells.sublist(head + 1);
    expect(rows, hasLength(250));
    expect(rows.first[2], 'SI-1');
    expect(rows.first[6], 10);
    expect(rows.last[2], 'SI-250');
    // The same closing balance the statement shows, as a number.
    expect(rows.last[6], 2500);
  });

  testWidgets('Download under the last 20 writes those rows and reads nothing',
      (tester) async {
    final _AccountApi api = _AccountApi();
    await _openAccount(tester, api);
    api.accountReads.clear();

    final List<List<Object?>> cells = await downloadedSheet(tester);

    expect(api.accountReads, isEmpty);
    expect(cells[1][0], 'The last 20 of 250 entries');
    final int head = cells.indexWhere((row) => row.isNotEmpty && row[0] == 'Date');
    final List<List<Object?>> rows = cells.sublist(head + 1);
    // What the entries not shown left, then the twenty.
    expect(rows, hasLength(21));
    expect(rows.first[1], 'Opening balance');
    expect(rows.first[6], 2300);
    expect(rows[1][2], 'SI-231');
    expect(rows.last[6], 2500);
  });

  testWidgets('the choice is there again at the next sign-in, for that user',
      (tester) async {
    final DesktopPreferencesService preferences = _preferences();
    final _AccountApi api = _AccountApi();
    await _openAccount(tester, api, preferences: preferences);
    expect(api.accountReads.single, {'last': '20'});
    await _choose(tester, 'Show 50');

    api.accountReads.clear();
    await _openAccount(tester, api, preferences: preferences);
    expect(api.accountReads.single, {'last': '50'});

    // Somebody else on this machine has made no choice.
    api.accountReads.clear();
    await _openAccount(
      tester,
      api,
      preferences: preferences,
      permissions: _permissions(user: 'user-2'),
    );
    expect(api.accountReads.single, {'last': '20'});

    // All is remembered like any other choice.
    await _choose(tester, 'Show all');
    api.accountReads.clear();
    await _openAccount(
      tester,
      api,
      preferences: preferences,
      permissions: _permissions(user: 'user-2'),
    );
    expect(api.accountReads.single, {'last': '100', 'from_start': 'true'});
    // And the first user still has theirs.
    api.accountReads.clear();
    await _openAccount(tester, api, preferences: preferences);
    expect(api.accountReads.single, {'last': '50'});
  });

  testWidgets('a page that is refused is said, and asked again only on request',
      (tester) async {
    final _AccountApi api = _AccountApi()
      ..refuseLaterPagesWith = 'The server is busy.';
    await _openAccount(tester, api);
    await _choose(tester, 'Show all');
    api.accountReads.clear();

    await _toTheEnd(tester);
    await _toTheEnd(tester);

    expect(api.accountReads, hasLength(1));
    expect(
      find.text('The rest could not be read: The server is busy.'),
      findsOneWidget,
    );
    // The entries read are still there.
    expect(find.textContaining('The first 100 of 250 entries'), findsOneWidget);

    api.refuseLaterPagesWith = null;
    await tester.tap(find.byKey(const ValueKey('account-more-again')));
    await tester.pumpAndSettle();

    expect(api.accountReads, hasLength(2));
    expect(find.textContaining('The first 200 of 250 entries'), findsOneWidget);
  });
}
