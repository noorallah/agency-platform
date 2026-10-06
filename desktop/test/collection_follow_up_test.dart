// Collection follow-up (backlog 87 #8, SG-8): the sheet lists what is owing
// and narrows by collector, Record promise posts the right body and keeps the
// dialog open on a refusal, the promises list shows statuses and Withdraw
// posts its reason, and the customer editor sends `collector_id`.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/firm_member.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/finance/collection_follow_up_pages.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['RECEIPT_VIEW', 'RECEIPT_CREATE'],
  }));

Json _row(String customer, String bill, String collectorId, String collector,
        {String? promiseStatus}) =>
    <String, dynamic>{
      'collector_id': collectorId,
      'collector_name': collector,
      'customer_id': 'c-$customer',
      'customer_code': 'C-$customer',
      'customer_name': 'Customer $customer',
      'customer_phone': '98450',
      'invoice_id': 'i-$bill',
      'invoice_number': 'INV-$bill',
      'invoice_date': '2026-09-01',
      'due_date': '2026-09-30',
      'days_overdue': 5,
      'invoice_total': '1200.00',
      'outstanding': '800.00',
      'is_opening_bill': false,
      'promise_id': promiseStatus == null ? null : 'p-$bill',
      'promised_on': promiseStatus == null ? null : '2026-10-10',
      'promised_amount': promiseStatus == null ? null : '500.00',
      'promise_status': promiseStatus,
      'promise_note': null,
      'promise_is_for_account': false,
    };

Json _promise(String id, String status) => <String, dynamic>{
      'id': id,
      'customer_id': 'c-1',
      'customer_code': 'C-1',
      'customer_name': 'Customer 1',
      'sales_invoice_id': 'i-1',
      'invoice_number': 'INV-1',
      'promised_on': '2026-10-10',
      'amount': '500.00',
      'received_amount': '0.00',
      'status': status,
      'note': null,
      'recorded_on': '2026-10-05',
      'recorded_by': 'u-1',
      'recorded_by_name': 'Asha',
      'collector_id': 'u-1',
      'collector_name': 'Asha',
      'version': 1,
    };

class _Api extends ApiClient {
  _Api({this.refusal, this.promises = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String? refusal;
  final List<Json> promises;
  final List<String> requested = <String>[];
  final List<Map<String, String>?> sheetQueries = [];
  Json? posted;
  Json? withdrawn;

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
    if (path == '/api/v1/firm-members') {
      return <String, dynamic>{
        'data': [
          {'user_id': 'u-1', 'full_name': 'Asha', 'email': 'a@x.in'},
          {'user_id': 'u-2', 'full_name': 'Ravi', 'email': 'r@x.in'},
        ],
      };
    }
    if (path == '/api/v1/collections/sheet') {
      sheetQueries.add(query);
      final String? who = query?['collector_id'];
      final List<Json> all = [
        _row('1', '1', 'u-1', 'Asha', promiseStatus: 'PENDING'),
        _row('2', '2', 'u-2', 'Ravi'),
      ];
      final List<Json> shown = who == null
          ? all
          : all.where((row) => row['collector_id'] == who).toList();
      return <String, dynamic>{
        'data': shown,
        'pagination': {'total_records': shown.length},
      };
    }
    if (method == 'POST' && path == '/api/v1/collections/promises') {
      posted = body;
      if (refusal != null) throw ApiException(refusal!);
      return <String, dynamic>{'data': _promise('p-new', 'PENDING')};
    }
    if (path.endsWith('/withdraw')) {
      withdrawn = body;
      return <String, dynamic>{'data': _promise('p-1', 'WITHDRAWN')};
    }
    if (path.startsWith('/api/v1/collections/promises')) {
      return <String, dynamic>{
        'data': promises,
        'pagination': {'total_records': promises.length},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('collection-follow-up'),
    );

Future<void> _pump(WidgetTester tester, Widget page,
    {Size size = const Size(1366, 768)}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(body: page),
  ));
  await tester.pumpAndSettle();
}

CollectionSheetPage _sheet(_Api api) => CollectionSheetPage(
      api: api,
      preferences: _preferences(),
      permissions: _permissions(),
      hasActiveFirm: true,
      saveBytesOverride: null,
    );

Future<void> _select(WidgetTester tester, String text) async {
  await tester.tap(find.text(text).first);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the sheet lists the bills and narrows by collector',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, _sheet(api));
    expect(find.text('Customer 1'), findsOneWidget);
    expect(find.text('Customer 2'), findsOneWidget);
    expect(find.text('Pending'), findsOneWidget);

    await tester.tap(find.byType(DropdownButtonFormField<String>).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ravi').last);
    await tester.pumpAndSettle();
    expect(api.sheetQueries.last!['collector_id'], 'u-2');
    expect(find.text('Customer 1'), findsNothing);
    expect(find.text('Customer 2'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('sheet-overdue-only')));
    await tester.pumpAndSettle();
    expect(api.sheetQueries.last!['overdue_only'], 'true');
  });

  testWidgets('Record promise posts the bill and the outstanding',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, _sheet(api));
    await _select(tester, 'Customer 2');
    await tester.tap(find.byKey(const ValueKey('selection-record-promise')));
    await tester.pumpAndSettle();
    expect(find.text('Record a payment promise'), findsOneWidget);
    expect(
        tester
            .widget<TextField>(find.byKey(const ValueKey('promise-amount')))
            .controller!
            .text,
        '800.00');

    await tester.enterText(
        find.byKey(const ValueKey('promise-note')), 'After the festival');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('promise-save')));
    await tester.pumpAndSettle();

    expect(api.posted!['customer_id'], 'c-2');
    expect(api.posted!['sales_invoice_id'], 'i-2');
    expect(api.posted!['amount'], '800.00');
    expect(api.posted!['note'], 'After the festival');
    expect(api.posted!['promised_on'], isNotEmpty);
    expect(find.text('Record a payment promise'), findsNothing);
  });

  testWidgets('a refusal keeps the dialog open with the server message',
      (tester) async {
    final _Api api = _Api(refusal: 'The amount is more than the bill owes.');
    await _pump(tester, _sheet(api), size: const Size(800, 600));
    await _select(tester, 'Customer 2');
    await tester.tap(find.byKey(const ValueKey('selection-record-promise')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('promise-save')));
    await tester.pumpAndSettle();
    expect(find.text('The amount is more than the bill owes.'),
        findsOneWidget);
    expect(find.text('Record a payment promise'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the promises list shows statuses and Withdraw sends a reason',
      (tester) async {
    final _Api api = _Api(promises: [
      _promise('p-1', 'BROKEN'),
      _promise('p-2', 'KEPT'),
    ]);
    await _pump(
      tester,
      PaymentPromisesPage(
        api: api,
        preferences: _preferences(),
        permissions: _permissions(),
        hasActiveFirm: true,
      ),
    );
    expect(find.text('Broken'), findsOneWidget);
    expect(find.text('Kept'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('promises-due-today')));
    await tester.pumpAndSettle();
    expect(api.requested,
        contains('GET /api/v1/collections/promises/due-today'));

    await tester.tap(find.byKey(const ValueKey('promises-due-today')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Broken').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('selection-withdraw-promise')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Customer paid cash');
    await tester.pump();
    await tester.tap(find.text('Withdraw').last);
    await tester.pumpAndSettle();
    expect(api.requested,
        contains('POST /api/v1/collections/promises/p-1/withdraw'));
    expect(api.withdrawn, {'reason': 'Customer paid cash'});
  });

  group('the customer editor', () {
    Json customerJson() => <String, dynamic>{
          'id': 'cust-1',
          'version': 1,
          'firm_id': 'firm-1',
          'code': 'CUS-001',
          'customer_type': 'BUSINESS',
          'name': 'Anand Agencies',
          'display_name': 'Anand Agencies',
          'currency_code': 'INR',
          'status': 'ACTIVE',
          'credit_limit': '0',
          'current_outstanding': '0',
          'payment_terms_days': 30,
          'collector_id': 'u-1',
          'addresses': <dynamic>[],
          'contacts': <dynamic>[],
        };

    Future<List<Json>> pumpEditor(WidgetTester tester) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final List<Json> sent = <Json>[];
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: CustomerWorkspaceDialog(
            mode: CustomerDialogMode.edit,
            customer: Customer.fromJson(customerJson()),
            onSave: (payload) async {
              sent.add(payload);
              return Customer.fromJson(customerJson());
            },
            loadPlaces: (level, {parentId = ''}) async => const [],
            loadMembers: () async => const [
              FirmMember(userId: 'u-1', fullName: 'Asha'),
              FirmMember(userId: 'u-2', fullName: 'Ravi'),
            ],
          ),
        ),
      ));
      await tester.pumpAndSettle();
      return sent;
    }

    testWidgets('prefills the collector and sends a change', (tester) async {
      final List<Json> sent = await pumpEditor(tester);
      final Finder picker = find.byKey(const ValueKey('customer-collector'));
      await tester.ensureVisible(picker);
      await tester.pumpAndSettle();
      expect(
          tester
              .widget<DropdownButtonFormField<String>>(picker)
              .initialValue,
          'u-1');
      await tester.tap(picker);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Ravi').last);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent.last['collector_id'], 'u-2');
    });

    testWidgets('an untouched edit sends the stored collector back',
        (tester) async {
      final List<Json> sent = await pumpEditor(tester);
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent.last['collector_id'], 'u-1');
    });
  });
}
