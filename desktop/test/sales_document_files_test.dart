// SG-6: a customer's PO scan or a signed challan kept with a sales document.
// The server stores the files; these tests pin the desktop half for the sales
// invoice and the sales order -- the Files column, the Attachments action
// opening the one shared panel with a single list request, an upload reaching
// the endpoint of the document it was made on, and who sees Add and Delete.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/document_file.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/purchases/document_attachments_dialog.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_management_page.dart';
import 'package:agency_desktop/ui/sales/sales_order_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'sub': 'user-1',
    'roles': <String>['user'],
    'permissions': codes,
  }));

class _Api extends ApiClient {
  _Api({this.rows = const <Json>[]})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;
  final List<String> fileListCalls = <String>[];
  final List<String> uploads = <String>[];

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
    if (path.endsWith('/files')) {
      fileListCalls.add('$method $path');
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'f-1',
            'file_name': 'customer-po.pdf',
            'content_type': 'application/pdf',
            'size_bytes': 2048,
            'caption': 'their PO',
            'created_at': '2026-10-05T09:30:00Z',
          },
        ],
      };
    }
    if (path.endsWith('/summary')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'total': rows.length, 'draft': rows.length},
      };
    }
    return <String, dynamic>{
      'data': rows,
      'pagination': <String, dynamic>{'total_records': rows.length},
    };
  }

  @override
  Future<Json> multipartRequest(
    String method,
    String path, {
    required Map<String, String> fields,
    String? fileField,
    String? fileName,
    List<int>? fileBytes,
    String? fileContentType,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async {
    uploads.add('$method $path $fileName');
    return <String, dynamic>{
      'data': <String, dynamic>{
        'id': 'f-2',
        'file_name': fileName,
        'content_type': fileContentType,
        'size_bytes': fileBytes?.length ?? 0,
        'caption': '',
        'created_at': '2026-10-05T10:00:00Z',
      },
    };
  }
}

Json _invoice({int files = 2}) => <String, dynamic>{
      'id': 'si-1',
      'invoice_number': 'INV-0001',
      'invoice_date': '2026-10-05',
      'status': 'APPROVED',
      'grand_total': '1000.00',
      'customer_id': 'cus-1',
      'customer_name': 'Acme Traders',
      'attached_file_count': files,
    };

Json _order({int files = 3}) => <String, dynamic>{
      'id': 'so-1',
      'order_number': 'SO-0001',
      'order_date': '2026-10-05',
      'status': 'APPROVED',
      'grand_total': '1000.00',
      'customer_id': 'cus-1',
      'customer_name': 'Acme Traders',
      'attached_file_count': files,
    };

Future<void> _pumpInvoices(
  WidgetTester tester,
  _Api api,
  List<String> codes, {
  Size size = const Size(1600, 1100),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory temp = Directory.systemTemp.createTempSync('sg6-invoices');
  addTearDown(() => temp.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: SalesInvoiceManagementPage(
        api: api,
        preferences: DesktopPreferencesService(directory: temp),
        permissions: _permissions(codes),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _pumpOrders(
  WidgetTester tester,
  _Api api,
  List<String> codes,
) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory temp = Directory.systemTemp.createTempSync('sg6-orders');
  addTearDown(() => temp.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: SalesOrderManagementPage(
        api: api,
        preferences: DesktopPreferencesService(directory: temp),
        permissions: _permissions(codes),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _openDialog(
  WidgetTester tester,
  _Api api,
  AttachableDocument kind, {
  bool canEdit = true,
  XFile? picked,
}) async {
  tester.view.physicalSize = const Size(800, 600);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: DocumentAttachmentsDialog(
        api: api,
        kind: kind,
        documentId: 'doc-1',
        subtitle: 'DOC-1',
        canEdit: canEdit,
        pickFile: picked == null ? null : () async => picked,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  const List<String> writer = ['SALES_VIEW', 'SALES_UPDATE'];

  testWidgets('the invoice list shows the Files column with the count',
      (tester) async {
    await _pumpInvoices(tester, _Api(rows: [_invoice()]), writer);

    expect(find.text('Files'), findsOneWidget);
    expect(find.text('\u{1F4CE} 2'), findsOneWidget);
  });

  testWidgets('an invoice with nothing attached shows a blank Files cell',
      (tester) async {
    await _pumpInvoices(tester, _Api(rows: [_invoice(files: 0)]), writer);

    expect(find.text('Files'), findsOneWidget);
    expect(find.textContaining('\u{1F4CE}'), findsNothing);
  });

  testWidgets('the order list shows the Files column with the count',
      (tester) async {
    await _pumpOrders(tester, _Api(rows: [_order()]), writer);

    expect(find.text('Files'), findsOneWidget);
    expect(find.text('\u{1F4CE} 3'), findsOneWidget);
  });

  testWidgets('Attachments on an invoice opens the panel with one list call',
      (tester) async {
    final _Api api = _Api(rows: [_invoice()]);
    await _pumpInvoices(tester, api, writer);

    await tester.tap(find.text('INV-0001'));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('selection-attachments')));
    await tester.pumpAndSettle();

    expect(find.text('Attachments · INV-0001'), findsOneWidget);
    expect(find.text('customer-po.pdf'), findsOneWidget);
    expect(api.fileListCalls, ['GET /api/v1/sales-invoices/si-1/files']);
    expect(find.byKey(const ValueKey('document-file-add')), findsOneWidget);

    // A rebuild does not ask again.
    await tester.pump();
    expect(api.fileListCalls, hasLength(1));
  });

  testWidgets('Attachments on an order opens the panel for that order',
      (tester) async {
    final _Api api = _Api(rows: [_order()]);
    await _pumpOrders(tester, api, writer);

    await tester.tap(find.text('SO-0001'));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('selection-attachments')));
    await tester.pumpAndSettle();

    expect(find.text('Attachments · SO-0001'), findsOneWidget);
    expect(api.fileListCalls, ['GET /api/v1/sales-orders/so-1/files']);
  });

  testWidgets('a reader sees the files but no Add and no Delete',
      (tester) async {
    final _Api api = _Api(rows: [_invoice()]);
    await _pumpInvoices(tester, api, const ['SALES_VIEW']);

    await tester.tap(find.text('INV-0001'));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('selection-attachments')));
    await tester.pumpAndSettle();

    expect(find.text('customer-po.pdf'), findsOneWidget);
    expect(find.byKey(const ValueKey('document-file-add')), findsNothing);
    expect(find.byTooltip('Delete'), findsNothing);
  });

  testWidgets('an upload on an invoice goes to the sales invoice endpoint',
      (tester) async {
    final _Api api = _Api();
    await _openDialog(
      tester,
      api,
      AttachableDocument.salesInvoice,
      picked: XFile.fromData(
        Uint8List.fromList(List<int>.filled(64, 1)),
        name: 'signed-challan.pdf',
        path: 'signed-challan.pdf',
      ),
    );

    await tester.tap(find.byKey(const ValueKey('document-file-add')));
    await tester.pumpAndSettle();

    expect(api.uploads,
        ['POST /api/v1/sales-invoices/doc-1/files signed-challan.pdf']);
  });

  testWidgets('an upload on an order goes to the sales order endpoint',
      (tester) async {
    final _Api api = _Api();
    await _openDialog(
      tester,
      api,
      AttachableDocument.salesOrder,
      picked: XFile.fromData(
        Uint8List.fromList(List<int>.filled(64, 1)),
        name: 'po.png',
        path: 'po.png',
      ),
    );

    await tester.tap(find.byKey(const ValueKey('document-file-add')));
    await tester.pumpAndSettle();

    expect(api.uploads, ['POST /api/v1/sales-orders/doc-1/files po.png']);
  });

  testWidgets('without write permission the panel hides Add and Delete',
      (tester) async {
    await _openDialog(
      tester,
      _Api(),
      AttachableDocument.salesInvoice,
      canEdit: false,
    );

    expect(find.text('customer-po.pdf'), findsOneWidget);
    expect(find.byKey(const ValueKey('document-file-add')), findsNothing);
    expect(find.byTooltip('Delete'), findsNothing);
  });
}
