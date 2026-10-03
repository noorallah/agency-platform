// Enquiries and leads (SEL-10): the grid and details pane read an enquiry, a
// new prospect is saved with exactly the declared keys, a follow-up, a loss and
// a conversion each send their body, and the follow-ups-due toggle switches the
// grid to the due list.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/enquiries_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>[
      'SALES_VIEW',
      'SALES_QUOTATION_CREATE',
      'SALES_UPDATE',
    ],
  }));

Json _enquiry({
  String id = 'e-1',
  String status = 'OPEN',
  String? customerId,
  String prospect = 'Ravi Kumar',
}) =>
    <String, dynamic>{
      'id': id,
      'enquiry_number': 'ENQ-$id',
      'enquiry_date': '2026-10-01',
      'branch_id': 'b1',
      'customer_id': customerId,
      'customer_name': customerId == null ? null : 'Anand Agencies',
      'prospect_name': prospect,
      'prospect_company': 'Kumar Traders',
      'prospect_phone': '+919876543210',
      'prospect_email': null,
      'prospect_city': 'Pune',
      'source': 'PHONE',
      'salesman_id': null,
      'expected_value': '25000.00',
      'expected_close_on': null,
      'next_follow_up_on': '2026-10-05',
      'status': status,
      'lost_reason': null,
      'lost_remarks': null,
      'quotation_id': null,
      'remarks': null,
      'version': 1,
      'lines': [
        {
          'line_number': 1,
          'product_id': null,
          'product_name': null,
          'description': 'Steel almirah',
          'quantity': '4',
          'expected_price': '6000',
        },
      ],
      'follow_ups': [
        {
          'id': 'f-1',
          'followed_on': '2026-10-02',
          'note': 'Asked for a catalogue',
          'next_follow_up_on': '2026-10-05',
          'created_by': 'u-1',
        },
      ],
    };

class _Api extends ApiClient {
  _Api({this.rows = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;
  final List<String> requested = <String>[];
  final Map<String, Json?> bodies = <String, Json?>{};

  Json _paged(List<Json> items) => <String, dynamic>{
        'data': items,
        'pagination': <String, dynamic>{'total_records': items.length},
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
    requested.add('$method $path');
    if (method != 'GET') bodies['$method $path'] = body;
    if (path == '/api/v1/branches') {
      return _paged([
        <String, dynamic>{
          'id': 'b1',
          'code': 'HO',
          'name': 'Head Office',
          'display_name': 'Head Office',
          'is_default': true,
        },
      ]);
    }
    if (path == '/api/v1/warehouses') {
      return _paged([
        <String, dynamic>{
          'id': 'w1',
          'code': 'WH1',
          'name': 'Main Store',
          'display_name': 'Main Store',
          'is_default': true,
          'branch_id': 'b1',
        },
      ]);
    }
    if (path == '/api/v1/customers' || path == '/api/v1/products') {
      return _paged(const <Json>[]);
    }
    if (path == '/api/v1/firm-members') {
      return <String, dynamic>{'data': const <Json>[]};
    }
    if (method == 'POST' && path == '/api/v1/enquiries') {
      return <String, dynamic>{'data': _enquiry(id: 'e-9')};
    }
    if (method == 'POST' && path.endsWith('/convert')) {
      return <String, dynamic>{
        'data': {..._enquiry(status: 'QUOTED'), 'quotation_id': 'q-1'},
      };
    }
    if (method == 'POST' && path.endsWith('/lost')) {
      return <String, dynamic>{'data': _enquiry(status: 'LOST')};
    }
    if (method == 'POST') return <String, dynamic>{'data': _enquiry()};
    if (path == '/api/v1/enquiries/follow-ups-due') {
      return <String, dynamic>{
        'data': [_enquiry(id: 'e-due', prospect: 'Due Today')],
      };
    }
    if (path == '/api/v1/enquiries/reports/lost') {
      return <String, dynamic>{'data': const <Json>[]};
    }
    if (path.startsWith('/api/v1/enquiries/')) {
      final String id = path.split('/').last;
      return <String, dynamic>{
        'data': rows.firstWhere((row) => row['id'] == id),
      };
    }
    if (path == '/api/v1/enquiries') return <String, dynamic>{'data': rows};
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('enquiries'),
    );

Future<void> _pump(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1600, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: EnquiriesPage(
        api: api,
        preferences: _preferences(),
        permissions: _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester, String number) async {
  await tester.tap(find.text(number).first);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

Future<void> _tap(WidgetTester tester, String key) async {
  final Finder finder = find.byKey(ValueKey(key));
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the grid and the details pane read an enquiry', (tester) async {
    final _Api api = _Api(rows: [_enquiry()]);
    await _pump(tester, api);
    expect(find.text('ENQ-e-1'), findsOneWidget);
    expect(find.text('Kumar Traders'), findsOneWidget);
    await _select(tester, 'ENQ-e-1');
    // The row is read again, not taken from the list.
    expect(api.requested, contains('GET /api/v1/enquiries/e-1'));
    expect(find.byKey(const ValueKey('enquiry-details')), findsOneWidget);
    expect(find.textContaining('Steel almirah'), findsOneWidget);
    expect(find.textContaining('Asked for a catalogue'), findsOneWidget);
  });

  testWidgets('a new prospect is saved with the declared keys', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();

    await _tap(tester, 'enquiry-save');
    expect(find.byKey(const ValueKey('enquiry-problem')), findsOneWidget);
    expect(api.bodies['POST /api/v1/enquiries'], isNull);

    await tester.enterText(
        find.byKey(const ValueKey('enquiry-name')), 'Ravi Kumar');
    await tester.enterText(
        find.byKey(const ValueKey('enquiry-phone')), '+919876543210');
    await tester.enterText(
        find.byKey(const ValueKey('enquiry-value')), '25000');
    await tester.enterText(
        find.byKey(const ValueKey('enquiry-line-description-0')),
        'Steel almirah');
    await tester.enterText(
        find.byKey(const ValueKey('enquiry-line-quantity-0')), '4');
    await _tap(tester, 'enquiry-save');

    final Json body = api.bodies['POST /api/v1/enquiries']!;
    expect(body.keys.toSet(), {
      'enquiry_date',
      'branch_id',
      'customer_id',
      'prospect_name',
      'prospect_company',
      'prospect_phone',
      'prospect_email',
      'prospect_city',
      'source',
      'salesman_id',
      'expected_value',
      'expected_close_on',
      'next_follow_up_on',
      'remarks',
      'lines',
    });
    expect(body['branch_id'], 'b1');
    expect(body['customer_id'], isNull);
    expect(body['prospect_name'], 'Ravi Kumar');
    expect(body['prospect_phone'], '+919876543210');
    expect(body['expected_value'], '25000');
    final Json line = (body['lines'] as List).single as Json;
    expect(line.keys.toSet(),
        {'product_id', 'description', 'quantity', 'expected_price'});
    expect(line['description'], 'Steel almirah');
    expect(line['quantity'], '4');
  });

  testWidgets('a follow-up sends its body', (tester) async {
    final _Api api = _Api(rows: [_enquiry()]);
    await _pump(tester, api);
    await _select(tester, 'ENQ-e-1');
    await tester.tap(find.byKey(const ValueKey('selection-log-follow-up')));
    await tester.pumpAndSettle();

    await _tap(tester, 'followup-save');
    expect(find.byKey(const ValueKey('followup-problem')), findsOneWidget);

    await tester.enterText(
        find.byKey(const ValueKey('followup-note')), 'Sent the catalogue');
    await _tap(tester, 'followup-save');

    final Json body = api.bodies['POST /api/v1/enquiries/e-1/follow-ups']!;
    expect(body.keys.toSet(), {'followed_on', 'note', 'next_follow_up_on'});
    expect(body['note'], 'Sent the catalogue');
    expect(body['next_follow_up_on'], isNull);
  });

  testWidgets('marking lost sends the reason', (tester) async {
    final _Api api = _Api(rows: [_enquiry()]);
    await _pump(tester, api);
    await _select(tester, 'ENQ-e-1');
    await tester.tap(find.byKey(const ValueKey('selection-mark-lost')));
    await tester.pumpAndSettle();

    await _tap(tester, 'lost-save');
    expect(find.byKey(const ValueKey('lost-problem')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('lost-reason')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Price').last);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('lost-remarks')), 'Cheaper elsewhere');
    await _tap(tester, 'lost-save');

    final Json body = api.bodies['POST /api/v1/enquiries/e-1/lost']!;
    expect(body.keys.toSet(), {'reason', 'remarks'});
    expect(body['reason'], 'PRICE');
    expect(body['remarks'], 'Cheaper elsewhere');
  });

  testWidgets('converting sends the quotation details', (tester) async {
    final _Api api = _Api(rows: [_enquiry()]);
    await _pump(tester, api);
    await _select(tester, 'ENQ-e-1');
    await tester.tap(find.byKey(const ValueKey('selection-convert-enquiry')));
    await tester.pumpAndSettle();
    await _tap(tester, 'convert-save');

    final Json body = api.bodies['POST /api/v1/enquiries/e-1/convert']!;
    expect(body.keys.toSet(), {
      'warehouse_id',
      'quotation_date',
      'valid_until',
      'customer_type',
      'customer_code',
    });
    expect(body['warehouse_id'], 'w1');
    expect(body['customer_type'], 'BUSINESS');
    expect(body['customer_code'], isNull);
  });

  testWidgets('the follow-ups due toggle reads the due list', (tester) async {
    final _Api api = _Api(rows: [_enquiry()]);
    await _pump(tester, api);
    expect(api.requested,
        isNot(contains('GET /api/v1/enquiries/follow-ups-due')));
    await tester.tap(find.byKey(const ValueKey('enquiry-due-toggle')));
    await tester.pumpAndSettle();
    expect(api.requested, contains('GET /api/v1/enquiries/follow-ups-due'));
    expect(find.text('ENQ-e-due'), findsOneWidget);
    expect(find.text('ENQ-e-1'), findsNothing);
  });
}
