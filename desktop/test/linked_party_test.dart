// ACC-11, customer and supplier as one party: the customer form links a
// supplier, the combined statement reads the two accounts net of each other,
// the supplier form names the customer, and a set-off preselects the other
// side of the same business.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/customers/customer_statement_page.dart';
import 'package:agency_desktop/ui/finance/party_adjustment_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> perms) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': perms,
  }));

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<String> requested = <String>[];
  Json? created;

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
    if (path == '/api/v1/customers/ageing') {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'customer_id': 'cus-1',
            'customer_code': 'C1',
            'customer_name': 'Kumar Stores',
            'total_outstanding': '1500.00',
            'account_balance': '1500.00',
            'buckets': <Json>[
              <String, dynamic>{
                'from_days': 0,
                'to_days': null,
                'amount': '1500.00'
              },
            ],
          },
        ],
      };
    }
    if (path == '/api/v1/customers/cus-1') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'id': 'cus-1',
          'name': 'Kumar Stores',
          'linked_vendor_id': 'ven-1',
        },
      };
    }
    if (path == '/api/v1/customers/cus-1/statement') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'customer_id': 'cus-1',
          'customer_name': 'Kumar Stores',
          'opening_balance': '0.00',
          'closing_balance': '1500.00',
          'lines': <Json>[],
        },
      };
    }
    if (path == '/api/v1/customers/cus-1/combined-statement') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'customer_id': 'cus-1',
          'customer_name': 'Kumar Stores',
          'vendor_id': 'ven-1',
          'vendor_name': 'Kumar Wholesale',
          'receivable_opening': '0.00',
          'payable_opening': '0.00',
          'net_opening': '0.00',
          'receivable_closing': '1500.00',
          'payable_closing': '400.00',
          'net_closing': '1100.00',
          'lines': <Json>[
            <String, dynamic>{
              'transaction_date': '2026-09-01',
              'account': 'RECEIVABLE',
              'transaction_type': 'INVOICE',
              'reference_number': 'SI-77',
              'remarks': '',
              'debit': '1500.00',
              'credit': '0.00',
              'net_balance': '1500.00',
            },
            <String, dynamic>{
              'transaction_date': '2026-09-05',
              'account': 'PAYABLE',
              'transaction_type': 'BILL',
              'reference_number': 'PI-88',
              'remarks': '',
              'debit': '0.00',
              'credit': '400.00',
              'net_balance': '1100.00',
            },
          ],
        },
      };
    }
    if (path == '/api/v1/customers') {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'cus-1',
            'name': 'Kumar Stores',
            'linked_vendor_id': 'ven-1',
          },
        ],
        'pagination': <String, dynamic>{'total_records': 1},
      };
    }
    if (path == '/api/v1/vendors') {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'ven-1',
            'name': 'Kumar Wholesale',
            'display_name': 'Kumar Wholesale',
          },
          <String, dynamic>{
            'id': 'ven-2',
            'name': 'Other Traders',
            'display_name': 'Other Traders',
          },
        ],
        'pagination': <String, dynamic>{'total_records': 2},
      };
    }
    if (path == '/api/v1/vendors/ven-2/linked-customer') {
      return <String, dynamic>{'data': null};
    }
    if (path == '/api/v1/vendors/ven-1/linked-customer') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'customer_id': 'cus-1',
          'code': 'C1',
          'name': 'Kumar Stores',
        },
      };
    }
    if (path == '/api/v1/party-adjustments/open-bills') {
      return <String, dynamic>{'data': <String, dynamic>{}};
    }
    if (path == '/api/v1/party-adjustments/settings') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'approval_threshold': '10000.00',
          'rounding_limit': '10.00',
          'is_default': true,
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/party-adjustments') {
      created = body;
    }
    if (path == '/api/v1/party-adjustments') {
      return <String, dynamic>{
        'data': const <Json>[],
        'pagination': <String, dynamic>{'total_records': 0},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

Json _customerJson({Object? linked}) => <String, dynamic>{
      'id': 'cust-1',
      'version': 4,
      'firm_id': 'firm-1',
      'code': 'CUS-001',
      'customer_type': 'BUSINESS',
      'name': 'Anand Agencies',
      'display_name': 'Anand Agencies',
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'credit_limit': '50000.00',
      'current_outstanding': '12000.00',
      'payment_terms_days': 30,
      'linked_vendor_id': linked,
      'addresses': <dynamic>[],
      'contacts': <dynamic>[],
    };

Vendor _vendor(String id, String name) => Vendor.fromJson(<String, dynamic>{
      'id': id,
      'code': id.toUpperCase(),
      'name': name,
      'display_name': name,
    });

void main() {
  group('the customer form', () {
    Future<List<Json>> pumpForm(
      WidgetTester tester, {
      bool withVendors = true,
      Object? linked,
    }) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final List<Json> sent = <Json>[];
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: CustomerWorkspaceDialog(
            mode: CustomerDialogMode.edit,
            customer: Customer.fromJson(_customerJson(linked: linked)),
            onSave: (payload) async {
              sent.add(payload);
              return Customer.fromJson(_customerJson());
            },
            loadPlaces: (level, {parentId = ''}) async => const [],
            loadVendors: withVendors
                ? () async => [
                      _vendor('ven-1', 'Kumar Wholesale'),
                      _vendor('ven-2', 'Other Traders'),
                    ]
                : null,
          ),
        ),
      ));
      await tester.pumpAndSettle();
      return sent;
    }

    testWidgets('sends the supplier it was linked to', (tester) async {
      final List<Json> sent = await pumpForm(tester);
      final Finder picker = find.byKey(const ValueKey('customer-linked-vendor'));
      await tester.ensureVisible(picker);
      await tester.pumpAndSettle();
      await tester.tap(picker);
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('Other Traders').last);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent.single['linked_vendor_id'], 'ven-2');
    });

    testWidgets('an untouched edit sends the stored link back',
        (tester) async {
      final List<Json> sent = await pumpForm(tester, linked: 'ven-1');
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent.single['linked_vendor_id'], 'ven-1');
    });

    testWidgets('without the supplier list the key is not sent',
        (tester) async {
      final List<Json> sent =
          await pumpForm(tester, withVendors: false, linked: 'ven-1');
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent.single.containsKey('linked_vendor_id'), isFalse);
    });
  });

  testWidgets('the combined statement lists both accounts net of each other',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: CustomerStatementPage(
          api: api,
          permissions:
              _permissions(const ['CUSTOMER_VIEW', 'VENDOR_VIEW']),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    final Finder row = find.text('Kumar Stores').first;
    await tester.tap(row);
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tap(row);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('toolbar-more')));
    await tester.pumpAndSettle();
    final Finder command = find
        .byKey(const ValueKey('toolbar-command-combined-statement-menu'));
    await tester.tap(command);
    await tester.pumpAndSettle();

    expect(api.requested,
        contains('GET /api/v1/customers/cus-1/combined-statement'));
    expect(find.text('SI-77'), findsOneWidget);
    expect(find.text('PI-88'), findsOneWidget);
    expect(find.text('Sales'), findsOneWidget);
    expect(find.text('Purchases'), findsOneWidget);
    expect(find.text('1,100.00'), findsWidgets);
    expect(find.text('They owe us'), findsOneWidget);
    expect(find.text('We owe them'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  group('a set-off', () {
    Future<_Api> openSetOff(WidgetTester tester) async {
      tester.view.physicalSize = const Size(1366, 768);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final _Api api = _Api();
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: PartyAdjustmentPage(
            api: api,
            preferences: DesktopPreferencesService(
              directory: Directory.systemTemp.createTempSync('linked-party'),
            ),
            permissions: _permissions(const [
              'PARTY_ADJUSTMENT_VIEW',
              'PARTY_ADJUSTMENT_MANAGE',
            ]),
            hasActiveFirm: true,
          ),
        ),
      ));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('toolbar-more')));
      await tester.pumpAndSettle();
      await tester
          .tap(find.byKey(const ValueKey('toolbar-command-new-set-off-menu')));
      await tester.pumpAndSettle();
      return api;
    }

    Future<void> pick(WidgetTester tester, Key menu, String label) async {
      await tester.tap(find.byKey(menu));
      await tester.pumpAndSettle();
      await tester.tap(find.text(label).last);
      await tester.pumpAndSettle();
    }

    testWidgets('choosing a customer preselects the linked supplier',
        (tester) async {
      await openSetOff(tester);
      await pick(tester, const ValueKey('pa-customer'), 'Kumar Stores');
      final DropdownMenu<String> vendor = tester
          .widget<DropdownMenu<String>>(find.byKey(const ValueKey('pa-vendor')));
      expect(vendor.controller?.text, 'Kumar Wholesale');
      expect(find.text('Kumar Wholesale'), findsWidgets);
    });

    testWidgets('choosing a supplier preselects the linked customer',
        (tester) async {
      final _Api api = await openSetOff(tester);
      await pick(tester, const ValueKey('pa-vendor'), 'Kumar Wholesale');
      expect(api.requested,
          contains('GET /api/v1/vendors/ven-1/linked-customer'));
      final DropdownMenu<String> customer = tester.widget<DropdownMenu<String>>(
          find.byKey(const ValueKey('pa-customer')));
      expect(customer.controller?.text, 'Kumar Stores');
    });
  });
}
