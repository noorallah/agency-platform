// D-SELL-18: selling pickers that could not reach older records.
//
// Each read one page -- the newest 50 notes to bill, 50 notes and 50 invoices
// of any status to return against, 100 orders to state on a proforma, 20
// customers and 100 products to quote, 100 of each to bill directly, the first
// 200 parties to take money from -- so anything older could not be chosen at
// all. The fake below serves every list a page at a time, as the server does,
// and ignores nothing a real server would honour, so a picker that stops at
// page one fails here.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/sales_return.dart';
import 'package:agency_desktop/models/settlement.dart';
import 'package:agency_desktop/models/settlement_direction.dart';
import 'package:agency_desktop/ui/quotations/quotation_management_page.dart';
import 'package:agency_desktop/ui/sales/proforma_page.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_editor_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> perms) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': perms,
  }));

class _PagingApi extends ApiClient {
  _PagingApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// Every GET, as `path?status=…&page=…`.
  final List<String> asked = <String>[];

  static List<Json> _many(int count, Json Function(int index) row) =>
      <Json>[for (int index = 0; index < count; index++) row(index)];

  final List<Json> billable = _many(
    150,
    (int index) => <String, dynamic>{
      'source_document_type': 'DELIVERY_NOTE',
      'source_document_id': 'dn-$index',
      'source_document_number': 'DN-$index',
      'document_date': '2026-08-04',
      'customer_id': 'cust-1',
      'customer_name': 'Anand Agencies',
      'branch_id': 'branch-1',
      'lines': const <Json>[],
    },
  );

  Json _note(String id, String status, {bool dispatched = true}) =>
      <String, dynamic>{
        'id': id,
        'delivery_note_number': id.toUpperCase(),
        'delivery_date': '2026-08-04',
        'customer_id': 'cust-1',
        'status': status,
        'dispatched_at': dispatched ? '2026-08-04T10:00:00Z' : null,
        'lines': const <Json>[],
      };

  late final Map<String, List<Json>> notesByStatus = <String, List<Json>>{
    'DISPATCHED': _many(101, (int index) => _note('dn-$index', 'DISPATCHED')),
    'COMPLETED': <Json>[_note('dn-done', 'COMPLETED')],
    'CLOSED': <Json>[
      _note('dn-closed-shipped', 'CLOSED'),
      _note('dn-closed-unshipped', 'CLOSED', dispatched: false),
    ],
  };

  Json _invoice(String id, String status) => <String, dynamic>{
        'id': id,
        'invoice_number': id.toUpperCase(),
        'invoice_date': '2026-08-05',
        'customer_id': 'cust-1',
        'status': status,
        'lines': const <Json>[],
      };

  late final Map<String, List<Json>> invoicesByStatus = <String, List<Json>>{
    'APPROVED': _many(101, (int index) => _invoice('si-$index', 'APPROVED')),
    'CLOSED': <Json>[_invoice('si-closed', 'CLOSED')],
  };

  final List<Json> partyRows = _many(
    205,
    (int index) => <String, dynamic>{
      'id': 'party-$index',
      'code': 'C${index.toString().padLeft(3, '0')}',
      'name': 'Customer $index',
    },
  );

  final List<Json> customerRows = _many(
    150,
    (int index) => <String, dynamic>{'id': 'cust-$index', 'name': 'Customer $index'},
  );

  final List<Json> productRows = _many(
    150,
    (int index) => <String, dynamic>{'id': 'prod-$index', 'name': 'Product $index'},
  );

  final List<Json> orderRows = _many(
    150,
    (int index) => <String, dynamic>{
      'id': 'so-$index',
      'order_number': 'SO-$index',
      'status': 'APPROVED',
      'grand_total': '10',
    },
  );

  Json _page(
    List<Json> rows,
    Map<String, String>? query, {
    bool paged = true,
    int? defaultSize,
  }) {
    final int page = int.tryParse(query?['page'] ?? '') ?? 1;
    final int size = int.tryParse(query?['page_size'] ?? query?['limit'] ?? '') ??
        defaultSize ??
        rows.length;
    final int start = (page - 1) * size;
    return <String, dynamic>{
      'data': start >= rows.length
          ? const <Json>[]
          : rows.sublist(start, (start + size).clamp(0, rows.length)),
      if (paged) 'pagination': <String, dynamic>{'total_records': rows.length},
    };
  }

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
    asked.add('$path?status=${query?['status'] ?? ''}&page=${query?['page'] ?? ''}');
    if (path.contains('workflow-settings')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'quotation_stage': false,
          'sales_order_stage': false,
          'delivery_note_stage': false,
          'is_configured': true,
        },
      };
    }
    if (path.endsWith('/sales-invoices/billable')) {
      return _page(billable, query, paged: false);
    }
    // Asked for no page, the route answered its first 200 by code.
    if (path.endsWith('/parties')) {
      return _page(partyRows, query, paged: false, defaultSize: 200);
    }
    if (path == '/api/v1/delivery-notes') {
      return _page(notesByStatus[query?['status']] ?? const <Json>[], query);
    }
    if (path == '/api/v1/sales-invoices') {
      return _page(invoicesByStatus[query?['status']] ?? const <Json>[], query);
    }
    if (path.startsWith('/api/v1/customers')) return _page(customerRows, query);
    if (path.startsWith('/api/v1/products')) return _page(productRows, query);
    if (path.startsWith('/api/v1/sales-orders')) return _page(orderRows, query);
    return <String, dynamic>{
      'data': const <Json>[],
      'pagination': <String, dynamic>{'total_records': 0},
    };
  }
}

void _big(WidgetTester tester) {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

void main() {
  test('Bill this delivery note reaches past the newest page', () async {
    final _PagingApi api = _PagingApi();

    final documents = await api.billableDocuments();

    expect(documents, hasLength(150));
    expect(documents.last.sourceDocumentNumber, 'DN-149');
  });

  test('the return source picker reads every returnable document, and only '
      'those', () async {
    final _PagingApi api = _PagingApi();

    final List<ReturnableDocument> documents = await api.returnableDocuments();
    final Set<String> ids = documents.map((doc) => doc.id).toSet();

    // Past the first page of each kind.
    expect(ids, containsAll(<String>['dn-100', 'si-100']));
    expect(ids, containsAll(<String>['dn-done', 'dn-closed-shipped', 'si-closed']));
    // A note closed without ever leaving has nothing to come back.
    expect(ids, isNot(contains('dn-closed-unshipped')));
    expect(documents, hasLength(101 + 1 + 1 + 101 + 1));
    // Asked by status, so a draft or a cancelled document is never offered.
    final Set<String> statuses = <String>{
      for (final String call in api.asked)
        if (call.startsWith('/api/v1/delivery-notes?') ||
            call.startsWith('/api/v1/sales-invoices?'))
          call.split('status=')[1].split('&').first,
    };
    expect(statuses, <String>{'DISPATCHED', 'COMPLETED', 'CLOSED', 'APPROVED'});
  });

  test('Record Receipt offers every party, not the first 200', () async {
    final _PagingApi api = _PagingApi();

    final List<PartyOption> parties =
        await api.settlementParties(direction: SettlementDirection.receipt);

    expect(parties, hasLength(205));
    expect(parties.last.code, 'C204');
  });

  testWidgets('the direct-bill editor reads every customer and product',
      (tester) async {
    _big(tester);
    final _PagingApi api = _PagingApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () => showDialog<bool>(
              context: context,
              builder: (_) => SalesInvoiceEditorDialog(
                api: api,
                today: DateTime(2026, 8, 14),
              ),
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    expect(api.asked, contains('/api/v1/customers?status=&page=2'));
    expect(api.asked, contains('/api/v1/products?status=&page=2'));
  });

  testWidgets('a quotation can be written for a customer past the first page',
      (tester) async {
    _big(tester);
    final _PagingApi api = _PagingApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: QuotationManagementPage(
          api: api,
          permissions:
              _permissions(const <String>['SALES_VIEW', 'SALES_QUOTATION_CREATE']),
          hasActiveFirm: true,
          today: DateTime(2026, 8, 14),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('New Quotation'));
    await tester.pumpAndSettle();

    expect(api.asked, contains('/api/v1/customers?status=&page=2'));
    expect(api.asked, contains('/api/v1/products?status=&page=2'));
  });

  testWidgets('a proforma can state an order past the newest hundred',
      (tester) async {
    _big(tester);
    final _PagingApi api = _PagingApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: ProformaPage(
          api: api,
          permissions:
              _permissions(const <String>['PROFORMA_VIEW', 'PROFORMA_MANAGE']),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('New'));
    await tester.pumpAndSettle();

    expect(api.asked, contains('/api/v1/sales-orders?status=&page=2'));
  });
}
