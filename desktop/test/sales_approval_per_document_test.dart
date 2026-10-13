// Approval is a step of its own, per document kind (backlog 119, M1).
//
// A firm may decide that a sales order, a delivery note or a sales bill is
// complete once it is saved. Then the window offers one *Save*, which saves
// the draft and at once runs the approve step -- with every question approval
// already asks -- and whoever raised the document may approve it without the
// approve code, because the server stamped `approval_step: false` on it.
// These pin the window's buttons and the list's Approve step on both sides.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/sales_document_steps.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/sales/sales_order_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/first_line.dart';

/// Someone who may raise sales documents and may not approve them.
PermissionService _raiser() => PermissionService()
  ..applyAccessToken(
    'header.${base64Url.encode(utf8.encode(jsonEncode(<String, dynamic>{
          'sub': 'u-me',
          'roles': <String>['user'],
          'permissions': <String>[
            'SALES_VIEW',
            'SALES_CREATE',
            'SALES_INVOICE_CREATE',
          ],
        }))).replaceAll('=', '')}.sig',
  );

class _Api extends ApiClient {
  _Api({required this.approvalStep})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// What the firm's settings say of every document kind.
  final bool approvalStep;
  final List<String> calls = <String>[];

  Json _paged(List<Json> rows) => <String, dynamic>{
        'data': rows,
        'pagination': <String, dynamic>{'total_records': rows.length},
      };

  Json _saved(String number) => <String, dynamic>{
        'id': 'doc-1',
        'version': 1,
        'order_number': number,
        'invoice_number': number,
        'status': 'DRAFT',
        'customer_id': 'c1',
        'grand_total': '118',
        'approval_step': approvalStep,
        'created_by': 'u-me',
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
    if (method != 'GET' && !path.endsWith('/preview')) {
      calls.add('$method $path');
    }
    if (path == '/api/v1/customers') {
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'c1',
          'code': 'C1',
          'name': 'Anand Agencies',
          'display_name': 'Anand Agencies',
          'customer_type': 'BUSINESS',
          'currency_code': 'INR',
          'default_discount_percent': '0',
          'status': 'ACTIVE',
        },
      ]);
    }
    if (path == '/api/v1/products') {
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'p1',
          'code': 'P1',
          'name': 'Shampoo 180ml',
          'selling_price': '100',
          'mrp': '120',
          'status': 'ACTIVE',
        },
      ]);
    }
    if (path == '/api/v1/branches') {
      return _paged(<Json>[
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
      return _paged(<Json>[
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
    if (path == '/api/v1/sales-orders/workflow-settings') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'quotation_stage': true,
          'sales_order_stage': true,
          'delivery_note_stage': true,
          'is_configured': true,
          'sales_order_approval': approvalStep,
          'delivery_note_approval': approvalStep,
          'sales_invoice_approval': approvalStep,
        },
      };
    }
    if (path == '/api/v1/firm-members') return <String, dynamic>{'data': []};
    if (path == '/api/v1/uom-framework/uoms') return _paged(<Json>[]);
    if (method == 'POST' && path == '/api/v1/sales-orders/preview') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'interstate': false,
          'order': <String, dynamic>{
            'order_number': 'SO-1',
            'subtotal': '100',
            'tax_total': '18',
            'grand_total': '118',
            'lines': const <Json>[],
          },
          'lines': const <Json>[],
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/sales-orders') {
      return <String, dynamic>{'data': _saved('SO-1')};
    }
    if (method == 'POST' && path == '/api/v1/sales-invoices') {
      return <String, dynamic>{'data': _saved('SI-1')};
    }
    if (method == 'POST' && path.endsWith('/approve')) {
      return <String, dynamic>{'data': <String, dynamic>{}};
    }
    if (path.contains('billable')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'sales_order_number': 'SO-9',
            'source_document_type': 'DELIVERY_NOTE',
            'source_document_id': 'dn-1',
            'source_document_number': 'DN-1',
            'document_date': '2026-08-04',
            'customer_id': 'c1',
            'customer_name': 'Anand Agencies',
            'branch_id': 'b1',
            'lines': <Json>[
              <String, dynamic>{
                'source_document_line_id': 'dn-1-l1',
                'line_number': 1,
                'product_id': 'p1',
                'description': 'Shampoo Bottle 180ml',
                'source_quantity': '4',
                'already_invoiced_quantity': '0',
                'remaining_quantity': '4',
                'unit_price': '100',
                'discount_percent': '0',
                'free_quantity': '0',
              },
            ],
          },
        ],
      };
    }
    if (method == 'POST' && path == '/api/v1/sales-invoices/preview') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'interstate': false,
          'invoice': <String, dynamic>{
            'invoice_number': 'SI-1',
            'subtotal': '400',
            'tax_total': '72',
            'grand_total': '472',
            'lines': const <Json>[],
          },
          'lines': const <Json>[],
        },
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

Future<void> _pump(WidgetTester tester, Widget editor) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (BuildContext context) => TextButton(
          onPressed: () => Navigator.of(context).push<Object>(
            MaterialPageRoute<Object>(
              builder: (_) => Scaffold(body: Phase2Scope(child: editor)),
            ),
          ),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _pumpOrder(WidgetTester tester, _Api api) async {
  await _pump(
    tester,
    SalesOrderEditorDialog(
      api: api,
      today: DateTime(2026, 8, 14),
      steps: salesOrderSteps(api, _raiser()),
    ),
  );
  await fillFirstLine(tester, document: 'sales-order', product: 'Shampoo');
  await tester.tap(find.byKey(const ValueKey('sales-order-customer')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Anand Agencies').last);
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _pumpInvoice(WidgetTester tester, _Api api) async {
  await _pump(
    tester,
    SalesInvoiceEditorDialog(
      api: api,
      today: DateTime(2026, 8, 14),
      steps: salesInvoiceSteps(api, _raiser()),
    ),
  );
  await tester.tap(find.byKey(const ValueKey('sales-invoice-bill-customer')));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Anand Agencies').last);
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

String _label(WidgetTester tester, String key) => ((tester
        .widget<FilledButton>(find.byKey(ValueKey<String>(key)))
        .child) as Text)
    .data!;

void main() {
  group('a sales order', () {
    testWidgets(
        'with approval off: one Save, no second button, and it approves',
        (tester) async {
      final _Api api = _Api(approvalStep: false);
      await _pumpOrder(tester, api);

      expect(_label(tester, 'sales-order-save'), 'Save');
      expect(find.byKey(const ValueKey('sales-order-save-approve')),
          findsNothing);
      await tester.tap(find.byKey(const ValueKey('sales-order-save')));
      await tester.pumpAndSettle();

      expect(api.calls, contains('POST /api/v1/sales-orders'));
      expect(api.calls, contains('POST /api/v1/sales-orders/doc-1/approve'));
      expect(tester.takeException(), isNull);
    });

    testWidgets('with approval a step: Save draft only, nothing approved',
        (tester) async {
      final _Api api = _Api(approvalStep: true);
      await _pumpOrder(tester, api);

      expect(_label(tester, 'sales-order-save'), 'Save draft');
      expect(find.byKey(const ValueKey('sales-order-save-approve')),
          findsNothing);
      await tester.tap(find.byKey(const ValueKey('sales-order-save')));
      await tester.pumpAndSettle();

      expect(api.calls, contains('POST /api/v1/sales-orders'));
      expect(api.calls.where((c) => c.endsWith('/approve')), isEmpty);
    });
  });

  group('a sales invoice', () {
    testWidgets('with approval off: one Save that approves', (tester) async {
      final _Api api = _Api(approvalStep: false);
      await _pumpInvoice(tester, api);

      expect(_label(tester, 'sales-invoice-save'), 'Save');
      expect(find.byKey(const ValueKey('sales-invoice-save-approve')),
          findsNothing);
      await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
      await tester.pumpAndSettle();

      expect(api.calls, contains('POST /api/v1/sales-invoices'));
      expect(
          api.calls, contains('POST /api/v1/sales-invoices/doc-1/approve'));
    });

    testWidgets('with approval a step: Save draft, no approve call',
        (tester) async {
      final _Api api = _Api(approvalStep: true);
      await _pumpInvoice(tester, api);

      expect(_label(tester, 'sales-invoice-save'), 'Save draft');
      expect(find.byKey(const ValueKey('sales-invoice-save-approve')),
          findsNothing);
      await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
      await tester.pumpAndSettle();

      expect(api.calls, contains('POST /api/v1/sales-invoices'));
      expect(api.calls.where((c) => c.endsWith('/approve')), isEmpty);
    });
  });

  group('the list offers Approve per row', () {
    Json row({required bool step, required String by}) => <String, dynamic>{
          'id': 'r1',
          'status': 'DRAFT',
          'approval_step': step,
          'created_by': by,
        };

    test('to the person who raised a row with no approval step', () {
      final _Api api = _Api(approvalStep: true);
      for (final steps in [
        salesOrderSteps(api, _raiser()),
        salesInvoiceSteps(api, _raiser()),
      ]) {
        final approve = steps.firstWhere((s) => s.id == 'approve');
        expect(approve.enabledFor(row(step: false, by: 'u-me')), isTrue);
        // Raised by someone else, or approval is a step: the code is needed.
        expect(approve.enabledFor(row(step: false, by: 'u-other')), isFalse);
        expect(approve.enabledFor(row(step: true, by: 'u-me')), isFalse);
      }
    });
  });
}
