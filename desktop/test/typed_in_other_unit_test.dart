// A line typed in another unit than the line it continues (D-PRC-37).
//
// The server keeps what was typed beside the quantity the caps count: 7 PIECE
// against a 2 BOX note comes back as `entered_quantity` 7 in `invoice_uom_id`
// / `return_uom_id` and `current_*_quantity` 0.5833 (in the note's unit). The
// desktop never types another unit, but a document made through the API can
// be opened in it: the views must read "7 PIECE" and not "0.5833 PIECE", and
// a saved sales bill reopened as a draft must send 7 back with its unit.

import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/document_framework/document_view_dialog.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_management_page.dart';
import 'package:agency_desktop/ui/purchase_returns/purchase_return_management_page.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/access_token.dart';

Json _page(List<Json> rows) => <String, dynamic>{
      'success': true,
      'data': rows,
      'pagination': <String, dynamic>{
        'page': 1,
        'page_size': 20,
        'total_records': rows.length,
        'total_pages': 1,
      },
    };

/// One typed-in-pieces line and one typed in the note's own unit.
List<Json> _lines(String quantityKey, String unitKey) => <Json>[
      <String, dynamic>{
        'line_number': 1,
        'product_id': 'p-1',
        'description': 'Shampoo box of 12',
        quantityKey: '0.5833',
        'entered_quantity': '7.0000',
        unitKey: 'u-pc',
        'unit_price': '100',
      },
      <String, dynamic>{
        'line_number': 2,
        'product_id': 'p-2',
        'description': 'Soap bar',
        quantityKey: '3.0000',
        'entered_quantity': null,
        unitKey: 'u-box',
        'unit_price': '20',
      },
    ];

class _ViewApi extends ApiClient {
  _ViewApi({required this.doc})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json doc;

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
    if (path.contains('uom-framework/uoms')) {
      return _page(<Json>[
        <String, dynamic>{'id': 'u-pc', 'code': 'PIECE', 'name': 'Piece'},
        <String, dynamic>{'id': 'u-box', 'code': 'BOX', 'name': 'Box'},
      ]);
    }
    if (path.contains('/summary')) {
      return <String, dynamic>{
        'success': true,
        'data': <String, dynamic>{'total': 1, 'draft': 1},
      };
    }
    if (path.contains('/history') || path.contains('/timeline')) {
      return <String, dynamic>{'success': true, 'data': <Json>[]};
    }
    if (path.contains('/products') ||
        path.contains('/tax-profiles') ||
        path.contains('/branches') ||
        path.contains('/warehouses') ||
        path.contains('price-variance')) {
      return _page(<Json>[]);
    }
    return _page(<Json>[doc]);
  }
}

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(accessTokenFor(const <String>[
    'PURCHASE_VIEW',
    'PURCHASE_CREATE',
    'PURCHASE_APPROVE',
    'PURCHASE_CANCEL',
    'SALES_VIEW',
    'SALES_CREATE',
    'SALES_APPROVE',
    'SALES_CANCEL',
  ]));

Future<void> _open(WidgetTester tester, Widget page, String number) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(home: Scaffold(body: Phase2Scope(child: page))),
  );
  await tester.pumpAndSettle();
  final Finder row = find.text(number).first;
  await tester.tap(row);
  await tester.pump(const Duration(milliseconds: 50));
  await tester.tap(row);
  await tester.pumpAndSettle();
  expect(find.byType(DocumentViewDialog), findsOneWidget);
}

DesktopPreferencesService _preferences(WidgetTester tester) {
  final Directory dir = Directory.systemTemp.createTempSync('typed-unit');
  addTearDown(() => dir.deleteSync(recursive: true));
  return DesktopPreferencesService(directory: dir);
}

void main() {
  group('a document opened for reading', () {
    testWidgets('a supplier bill line shows what was typed, in its unit',
        (tester) async {
      final _ViewApi api = _ViewApi(doc: <String, dynamic>{
        'id': 'doc-1',
        'invoice_number': 'PINV-0001',
        'vendor_name': 'Sri Ganesh Traders',
        'status': 'DRAFT',
        'grand_total': '590.00',
        'lines': _lines('current_invoice_quantity', 'invoice_uom_id'),
      });
      await _open(
        tester,
        PurchaseInvoiceManagementPage(
          api: api,
          preferences: _preferences(tester),
          permissions: _permissions(),
          hasActiveFirm: true,
        ),
        'PINV-0001',
      );

      expect(find.text('7.0000'), findsOneWidget);
      expect(find.text('PIECE'), findsOneWidget);
      expect(find.text('0.5833'), findsNothing);
      // A line typed in the note's own unit reads as before.
      expect(find.text('3.0000'), findsOneWidget);
      expect(find.text('BOX'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a purchase return line shows what was typed, in its unit',
        (tester) async {
      final _ViewApi api = _ViewApi(doc: <String, dynamic>{
        'id': 'doc-1',
        'return_number': 'PRET-0001',
        'vendor_name': 'Sri Ganesh Traders',
        'status': 'DRAFT',
        'grand_total': '590.00',
        'lines': _lines('current_return_quantity', 'return_uom_id'),
      });
      await _open(
        tester,
        PurchaseReturnManagementPage(
          api: api,
          preferences: _preferences(tester),
          permissions: _permissions(),
          hasActiveFirm: true,
        ),
        'PRET-0001',
      );

      expect(find.text('7.0000'), findsOneWidget);
      expect(find.text('PIECE'), findsOneWidget);
      expect(find.text('0.5833'), findsNothing);
      expect(find.text('3.0000'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a sales bill line shows what was typed, in its unit',
        (tester) async {
      final _ViewApi api = _ViewApi(doc: <String, dynamic>{
        'id': 'doc-1',
        'invoice_number': 'SINV-0001',
        'invoice_date': '2026-08-10',
        'customer_name': 'Anand Agencies',
        'status': 'DRAFT',
        'grand_total': '590.00',
        'lines': _lines('current_invoice_quantity', 'invoice_uom_id'),
      });
      await _open(
        tester,
        SalesInvoiceManagementPage(
          api: api,
          preferences: _preferences(tester),
          permissions: _permissions(),
          hasActiveFirm: true,
        ),
        'SINV-0001',
      );

      expect(find.text('7.0000'), findsOneWidget);
      expect(find.text('PIECE'), findsOneWidget);
      expect(find.text('0.5833'), findsNothing);
      expect(find.text('3.0000'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  group('a saved sales bill reopened as a draft', () {
    Json draftLine(int number, String id, {bool typed = false}) =>
        <String, dynamic>{
          'source_document_type': 'DELIVERY_NOTE',
          'source_document_id': 'dn-1',
          'source_document_number': 'DN-000001',
          'source_document_line_id': id,
          'line_number': number,
          'product_id': 'p-$number',
          'description': 'Line $number',
          'current_invoice_quantity': typed ? '0.5833' : '2',
          'entered_quantity': typed ? '7.0000' : null,
          'invoice_uom_id': typed ? 'u-pc' : 'u-box',
          'unit_price': '100',
          'discount_percent': '0',
        };

    testWidgets('keeps 7 PIECE as 7 PIECE and says it is read-only',
        (tester) async {
      final _EditorApi api = _EditorApi()
        ..existing = <String, dynamic>{
          'id': 'inv-1',
          'invoice_number': 'SI-1',
          'invoice_date': '2026-08-10',
          'customer_id': 'cust-1',
          'customer_name': 'Anand Agencies',
          'branch_id': 'branch-1',
          'status': 'DRAFT',
          'version': 3,
          'bill_discount_percent': '0',
          'lines': <Json>[
            draftLine(1, 'dn-1-l1', typed: true),
            draftLine(2, 'dn-1-l2'),
          ],
        };
      tester.view.physicalSize = const Size(1366, 768);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Phase2Scope(
            child: SalesInvoiceEditorDialog(
              api: api,
              today: DateTime(2026, 8, 14),
              invoiceId: 'inv-1',
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: 'no overflow at 1366x768');

      // The box shows what was typed, not 0.5833, and cannot be edited.
      final EditableText typedBox = tester.widget<EditableText>(find
          .descendant(
            of: find.byKey(const ValueKey('sales-invoice-line-0')),
            matching: find.byType(EditableText),
          )
          .first);
      expect(typedBox.controller.text, '7');
      expect(typedBox.readOnly, isTrue);
      expect(
        find.textContaining('Typed in PIECE, kept as typed'),
        findsOneWidget,
      );
      // The line in the note's own unit is an ordinary box.
      final EditableText plainBox = tester.widget<EditableText>(find
          .descendant(
            of: find.byKey(const ValueKey('sales-invoice-line-1')),
            matching: find.byType(EditableText),
          )
          .first);
      expect(plainBox.controller.text, '2.0');
      expect(plainBox.readOnly, isFalse);

      await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
      await tester.pumpAndSettle();
      final List<dynamic> lines = api.updated!['lines'] as List<dynamic>;
      expect(lines, hasLength(2));
      final Json typed = lines[0] as Json;
      expect(typed['current_invoice_quantity'], '7');
      expect(typed['invoice_uom_id'], 'u-pc');
      // Nothing is invented for a line typed in the note's own unit.
      expect((lines[1] as Json).containsKey('invoice_uom_id'), isFalse);
      // The previews were priced from what was typed as well.
      final Json priced = (api.previews.last['lines'] as List<dynamic>)[0] as Json;
      expect(priced['current_invoice_quantity'], '7');
      expect(priced['invoice_uom_id'], 'u-pc');
    });
  });
}

class _EditorApi extends ApiClient {
  _EditorApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? existing;
  Json? updated;
  final List<Json> previews = <Json>[];

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
    if (path.contains('workflow-settings')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'quotation_stage': true,
          'sales_order_stage': true,
          'delivery_note_stage': true,
          'is_configured': true,
        },
      };
    }
    if (path.contains('uom-framework/uoms')) {
      return _page(<Json>[
        <String, dynamic>{'id': 'u-pc', 'code': 'PIECE', 'name': 'Piece'},
        <String, dynamic>{'id': 'u-box', 'code': 'BOX', 'name': 'Box'},
      ]);
    }
    if (path.contains('billable')) {
      return <String, dynamic>{'data': const <Json>[]};
    }
    if (method == 'POST' && path == '/api/v1/sales-invoices/preview') {
      previews.add(body!);
      return <String, dynamic>{
        'data': <String, dynamic>{
          'interstate': true,
          'invoice': <String, dynamic>{
            'invoice_number': 'SI-1',
            'subtotal': '0',
            'tax_total': '0',
            'grand_total': '0',
            'lines': const <Json>[],
          },
          'lines': const <Json>[],
        },
      };
    }
    if (method == 'GET' && path.startsWith('/api/v1/sales-invoices/')) {
      return <String, dynamic>{'data': existing};
    }
    if (method == 'PUT' && path.startsWith('/api/v1/sales-invoices/')) {
      updated = body;
      return <String, dynamic>{'data': existing};
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}
