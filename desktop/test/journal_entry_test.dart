import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/finance.dart';
import 'package:agency_desktop/ui/finance/journal_entries_page.dart';
import 'package:agency_desktop/ui/finance/journal_entry_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Writing a journal entry by hand.
///
/// The rule that makes it a journal entry rather than a note is that it
/// balances, and the running total is on screen while it is written because
/// finding out on save is finding out too late.
PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

JournalDraftLine _line(String account, {String debit = '', String credit = ''}) =>
    JournalDraftLine(ledgerAccountId: account, debit: debit, credit: credit);

class _JournalApi extends ApiClient {
  _JournalApi({this.entries = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<JournalEntry> entries;
  String? posted;
  Json? reversed;

  @override
  Future<PagedResult<JournalEntry>> journalEntries({
    int page = 1,
    int pageSize = 20,
    String search = '',
    bool descending = true,
    String? accountingPeriodId,
    String? status,
  }) async =>
      PagedResult<JournalEntry>(items: entries, total: entries.length);

  @override
  Future<JournalEntry> postJournalEntry(String id) async {
    posted = id;
    return entries.first;
  }

  @override
  Future<JournalEntry> reverseJournalEntry(String id, Json data) async {
    reversed = data;
    return entries.first;
  }
}

JournalEntry _entry({
  required String reference,
  String status = 'DRAFT',
  String source = '',
}) =>
    JournalEntry.fromJson({
      'id': 'je-$reference',
      'reference_number': reference,
      'journal_date': '2026-08-10',
      'accounting_period_id': 'p-1',
      'status': status,
      'total_debit': '100.00',
      'total_credit': '100.00',
      'is_balanced': true,
      'source_module': source,
      'description': '',
    });

Future<void> _pumpList(
  WidgetTester tester,
  _JournalApi api, {
  List<String> perms = const [
    'JOURNAL_VIEW',
    'JOURNAL_CREATE',
    'JOURNAL_POST',
    'JOURNAL_REVERSE',
  ],
}) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: JournalEntriesPage(
          api: api,
          permissions: _permissionsFor(perms),
          hasActiveFirm: true,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('an entry has to balance', () {
    test('equal sides pass', () {
      expect(
        validateJournalLines([
          _line('a', debit: '100'),
          _line('b', credit: '100'),
        ]),
        isNull,
      );
    });

    test('unequal sides say by how much', () {
      // The number is the point: "does not balance" without it sends somebody
      // to add the column up by hand.
      expect(
        validateJournalLines([
          _line('a', debit: '100'),
          _line('b', credit: '90'),
        ]),
        contains('differ by 10.00'),
      );
    });

    test('a line cannot be a debit and a credit at once', () {
      expect(
        validateJournalLines([
          _line('a', debit: '100', credit: '100'),
          _line('b', credit: '100'),
        ]),
        contains('not both'),
      );
    });

    test('one line is not an entry', () {
      expect(
        validateJournalLines([_line('a', debit: '100')]),
        contains('at least two lines'),
      );
    });

    test('an amount with no account is caught before the server sees it', () {
      expect(
        validateJournalLines([
          _line('', debit: '100'),
          _line('b', credit: '100'),
        ]),
        contains('choose the account'),
      );
    });

    test('blank rows are ignored rather than refused', () {
      // An empty row is somebody's cursor, not an instruction.
      expect(
        validateJournalLines([
          _line('a', debit: '100'),
          _line('b', credit: '100'),
          JournalDraftLine(),
        ]),
        isNull,
      );
    });

    test('rounding to the paisa does not fail a matched pair', () {
      expect(
        validateJournalLines([
          _line('a', debit: '33.33'),
          _line('b', debit: '33.33'),
          _line('c', debit: '33.34'),
          _line('d', credit: '100.00'),
        ]),
        isNull,
      );
    });
  });

  group('a line becomes a payload', () {
    test('amounts are sent to two places on the side they were typed', () {
      final Json json = _line('acc-1', debit: '250.5').toJson();
      expect(json['ledger_account_id'], 'acc-1');
      expect(json['debit_amount'], '250.50');
      expect(json['credit_amount'], '0.00');
    });

    test('no line number is sent, because the schema forbids one', () {
      // `JournalLineInput` has no such field and rejects extras outright. The
      // engine numbers the lines itself.
      expect(_line('acc-1', debit: '10').toJson().containsKey('line_number'),
          isFalse);
    });
  });

  group('the journal list', () {
    testWidgets('only a draft can be posted', (tester) async {
      final _JournalApi api = _JournalApi(entries: [
        _entry(reference: 'JV-1', status: 'POSTED', source: 'sales_invoice'),
      ]);
      await _pumpList(tester, api);

      final FilledButton post = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Post'),
      );
      expect(post.onPressed, isNull, reason: 'a posted entry cannot be posted again');
    });

    testWidgets('only a posted entry can be reversed', (tester) async {
      final _JournalApi api = _JournalApi(entries: [_entry(reference: 'JV-2')]);
      await _pumpList(tester, api);

      final OutlinedButton reverse = tester.widget<OutlinedButton>(
        find.widgetWithText(OutlinedButton, 'Reverse'),
      );
      expect(reverse.onPressed, isNull, reason: 'a draft has nothing to reverse');
    });

    testWidgets('an entry a document wrote says which', (tester) async {
      // "Who wrote this" is the first question anybody asks of an entry they
      // did not expect.
      final _JournalApi api = _JournalApi(entries: [
        _entry(reference: 'JV-3', status: 'POSTED', source: 'goods_receipt'),
      ]);
      await _pumpList(tester, api);

      expect(find.text('Posted by goods_receipt'), findsOneWidget);
    });

    testWidgets('without JOURNAL_POST the button is not offered at all',
        (tester) async {
      final _JournalApi api = _JournalApi(entries: [_entry(reference: 'JV-4')]);
      await _pumpList(tester, api, perms: const ['JOURNAL_VIEW']);

      expect(find.widgetWithText(FilledButton, 'Post'), findsNothing);
      expect(find.widgetWithText(OutlinedButton, 'Reverse'), findsNothing);
      expect(find.widgetWithText(FilledButton, 'New Entry'), findsNothing);
    });
  });
}
