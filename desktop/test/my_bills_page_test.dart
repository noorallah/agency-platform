// My Bills to Collect (backlog 123): the collector's list shows the bills
// handed to him and, marked apart, the other unpaid bills of the same
// customers; the totals keep the two apart; every page is read; a user
// without COLLECTION_OWN_VIEW sees nothing and calls nothing; and the page
// has no action that writes.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/finance/my_bills_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({bool allowed = true, bool record = false}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': <String>[
          if (allowed) 'COLLECTION_OWN_VIEW',
          if (record) 'COLLECTION_OWN_RECORD',
        ],
      }));

Json _bill(String n, String customer,
        {required bool mine, String outstanding = '800.00'}) =>
    <String, dynamic>{
      'invoice_id': 'i-$n',
      'invoice_number': 'INV-$n',
      'invoice_date': '2026-09-01',
      'due_date': '2026-09-30',
      'days_overdue': 5,
      'is_opening_bill': false,
      'customer_id': 'c-$customer',
      'customer_code': 'C-$customer',
      'customer_name': 'Customer $customer',
      'customer_place': customer == '1' ? 'Hosur' : '',
      'invoice_total': 1200,
      'outstanding': outstanding,
      'handed_to_me': mine,
      'handover_id': mine ? 'h-$n' : null,
      'handed_on': mine ? '2026-10-12' : null,
    };

/// Three bills over two pages of two: A and B are mine, C is the same
/// customer's other bill.
final List<List<Json>> _pages = [
  [
    _bill('A', '1', mine: true),
    _bill('C', '1', mine: false, outstanding: '500.00'),
  ],
  [
    _bill('B', '2', mine: true, outstanding: '300.00'),
  ],
];

class _Api extends ApiClient {
  _Api({
    this.empty = false,
    this.refusal,
    this.withLine = false,
    this.refuseRecord,
  })
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool empty;
  final String? refusal;
  final bool withLine;
  final String? refuseRecord;
  Json? recordedBody;
  String? withdrawn;
  final List<String> requested = <String>[];
  final List<String?> pageAsked = <String?>[];

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
    requested.add('$method $path');
    if (path == '/api/v1/collections/my-bills') {
      if (refusal != null) throw ApiException(refusal!);
      pageAsked.add(query?['page']);
      if (empty) {
        return <String, dynamic>{
          'data': const <Json>[],
          'pagination': {'total_records': 0},
        };
      }
      final int page = int.parse(query?['page'] ?? '1');
      final List<Json> rows = page <= _pages.length
          ? [
              for (final Json row in _pages[page - 1])
                if (withLine && row['invoice_id'] == 'i-B')
                  <String, dynamic>{
                    ...row,
                    'return_id': 'r-B',
                    'return_outcome': 'PART',
                    'return_amount': '300.00',
                  }
                else
                  row,
            ]
          : const <Json>[];
      return <String, dynamic>{
        'data': rows,
        'pagination': {'page': page, 'total_records': 3},
      };
    }
    if (path == '/api/v1/collections/my-bills/day-sheet') {
      return <String, dynamic>{
        'data': {
          'day': '2026-10-13',
          'collector_records_receipt': false,
          'rows': withLine
              ? [
                  {'id': 'r-B', 'outcome': 'PART', 'amount_collected': '300.00'},
                ]
              : const <Json>[],
          'bills_without_a_line': withLine ? 1 : 2,
          'amount_stated': withLine ? '1180.00' : '0.00',
          'amount_receipted': withLine ? '1000.00' : '0.00',
          'amount_not_receipted': withLine ? '180.00' : '0.00',
          'adds_up': !withLine,
        },
      };
    }
    if (method == 'POST' && path.endsWith('/my-bills/returns')) {
      recordedBody = body;
      if (refuseRecord != null) throw ApiException(refuseRecord!);
      return <String, dynamic>{
        'data': {'id': 'r-new'},
      };
    }
    if (method == 'POST' && path.endsWith('/withdraw')) {
      withdrawn = body?['reason'] as String?;
      return <String, dynamic>{
        'data': {'id': 'r-B'},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('my-bills'),
    );

Future<void> _pump(WidgetTester tester, _Api api,
    {bool allowed = true, bool firm = true, bool record = false}) async {
  tester.view.physicalSize = const Size(1200, 800);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: MyBillsPage(
        api: api,
        preferences: _preferences(),
        permissions: _permissions(allowed: allowed, record: record),
        hasActiveFirm: firm,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('every page is read and every row shown', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    expect(api.pageAsked, ['1', '2']);
    expect(find.textContaining('Customer 1 · Hosur'), findsNWidgets(2));
    expect(find.text('Customer 2'), findsOneWidget);
    expect(find.text('INV-A'), findsOneWidget);
    expect(find.text('INV-B'), findsOneWidget);
    expect(find.text('INV-C'), findsOneWidget);
    // Dates are written in the person's format, not as stored.
    expect(find.text('01-09-2026'), findsNWidgets(3));
    expect(find.text('2026-09-01'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the two kinds of bill are marked apart', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    expect(find.text('With me, 12-10-2026'), findsNWidgets(2));
    expect(find.text('Not handed to me'), findsOneWidget);
  });

  testWidgets('the totals keep mine and the others apart', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    expect(
        tester
            .widget<Text>(find.byKey(const ValueKey('my-bills-mine')))
            .data,
        'Handed to me: 2 bills, 1,100.00 outstanding');
    expect(
        tester
            .widget<Text>(find.byKey(const ValueKey('my-bills-others')))
            .data,
        'Other unpaid bills of the same customers: 1 bill, '
        '500.00 outstanding');
  });

  testWidgets('with nothing handed over the page says so in plain words',
      (tester) async {
    final _Api api = _Api(empty: true);
    await _pump(tester, api);
    expect(find.text('No bills handed to you'), findsOneWidget);
    expect(find.byKey(const ValueKey('my-bills-mine')), findsNothing);
  });

  testWidgets('a refusal shows the server message', (tester) async {
    final _Api api = _Api(refusal: 'You cannot see this.');
    await _pump(tester, api);
    expect(find.text('You cannot see this.'), findsOneWidget);
  });

  testWidgets('without COLLECTION_OWN_VIEW nothing is shown or called',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, allowed: false);
    expect(find.text('You cannot see the bills to collect'), findsOneWidget);
    expect(find.text('INV-A'), findsNothing);
    expect(api.requested, isEmpty);
  });

  testWidgets('with no firm chosen nothing is called', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, firm: false);
    expect(find.text('Choose a firm'), findsOneWidget);
    expect(api.requested, isEmpty);
  });

  testWidgets('Refresh reads the list again and nothing is written',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    expect(find.byType(FilledButton), findsNothing);
    expect(find.byType(Checkbox), findsNothing);
    await tester.tap(find.byIcon(Icons.refresh).first);
    await tester.pumpAndSettle();
    expect(api.pageAsked, ['1', '2', '1', '2']);
    expect(api.requested.every((r) => r.startsWith('GET ')), isTrue);
  });

  testWidgets('without COLLECTION_OWN_RECORD no Record button is offered',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    expect(find.byKey(const ValueKey('my-bill-record-i-A')), findsNothing);
    expect(find.byType(TextButton), findsNothing);
  });

  testWidgets('recording a part sends exactly the declared keys',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, record: true);
    // The other customer's bill carries no button.
    expect(find.byKey(const ValueKey('my-bill-record-i-C')), findsNothing);
    await tester.tap(find.byKey(const ValueKey('my-bill-record-i-A')));
    await tester.pumpAndSettle();
    expect(
        find.text('Save notes what you collected. The office records '
            'the receipt.'),
        findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('return-outcome')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Part collected').last);
    await tester.pumpAndSettle();
    // Nothing typed yet: refused before it is sent.
    await tester.tap(find.byKey(const ValueKey('return-save')));
    await tester.pumpAndSettle();
    expect(api.recordedBody, isNull);
    expect(find.byKey(const ValueKey('return-error')), findsOneWidget);
    await tester.enterText(find.byKey(const ValueKey('return-amount')), '300');
    await tester.tap(find.byKey(const ValueKey('return-save')));
    await tester.pumpAndSettle();
    expect(api.recordedBody, {
      'handover_id': 'h-A',
      'outcome': 'PART',
      'amount_collected': '300',
      'payment_mode': 'CASH',
    });
    expect(api.recordedBody!.values.contains(null), isFalse);
    // The list and the day were read again.
    expect(api.pageAsked, ['1', '2', '1', '2']);
    expect(find.byKey(const ValueKey('return-save')), findsNothing);
  });

  testWidgets('a refusal keeps the dialog open with the message',
      (tester) async {
    final _Api api = _Api(refuseRecord: 'This bill is not in your bag.');
    await _pump(tester, api, record: true);
    await tester.tap(find.byKey(const ValueKey('my-bill-record-i-A')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('return-save')));
    await tester.pumpAndSettle();
    expect(api.recordedBody, {
      'handover_id': 'h-A',
      'outcome': 'COLLECTED',
      'payment_mode': 'CASH',
    });
    expect(find.text('This bill is not in your bag.'), findsOneWidget);
    expect(find.byKey(const ValueKey('return-save')), findsOneWidget);
  });

  testWidgets('a bill with a line shows it and can be withdrawn',
      (tester) async {
    final _Api api = _Api(withLine: true);
    await _pump(tester, api, record: true);
    expect(find.byKey(const ValueKey('my-bill-record-i-B')), findsNothing);
    expect(
        tester
            .widget<Text>(find.byKey(const ValueKey('my-bill-line-i-B')))
            .data,
        'Part collected 300.00');
    await tester.tap(find.byKey(const ValueKey('my-bill-withdraw-i-B')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Entered in error');
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, 'Withdraw'));
    await tester.pumpAndSettle();
    expect(api.withdrawn, 'Entered in error');
  });

  testWidgets('the day summary comes from the day sheet', (tester) async {
    final _Api api = _Api(withLine: true);
    await _pump(tester, api);
    expect(
        tester
            .widget<Text>(find.byKey(const ValueKey('my-day-summary')))
            .data,
        'Today: 1 line. Collected 1,180.00. In receipts 1,000.00. '
        'Still with you to hand in: 180.00. 1 bill has no line yet.');
  });
}
