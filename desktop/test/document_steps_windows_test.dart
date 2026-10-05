// D-BUY-22: every document window carries its own next steps, through the
// one shared strip and from the same definitions as its list toolbar -- so
// a bill, a return, an order, a note and an invoice can each be moved on
// from where it is being looked at, under the code and the status gate the
// toolbar already used. The goods receipt, where the defect was found, has
// its own file: document_steps_goods_receipt_test.dart.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/document_framework.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/delivery_notes/delivery_note_management_page.dart';
import 'package:agency_desktop/ui/document_framework/document_steps.dart';
import 'package:agency_desktop/ui/document_framework/document_view_dialog.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_steps.dart';
import 'package:agency_desktop/ui/purchase_returns/purchase_return_steps.dart';
import 'package:agency_desktop/ui/sales/sales_document_steps.dart';
import 'package:agency_desktop/ui/sales_returns/sales_return_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

/// A server that lists one note and one return, answers any step, and
/// records what it was asked.
class _Api extends ApiClient {
  _Api({this.noteStatus = 'DRAFT'})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String noteStatus;

  final List<String> calls = <String>[];

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
    if (method == 'POST') calls.add('$method $path');
    if (method == 'GET' && path == '/api/v1/delivery-notes') {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'dn-1',
            'delivery_note_number': 'DN-0001',
            'customer_name': 'Customer 1',
            'delivery_date': '2026-10-01',
            'status': noteStatus,
            'grand_total': '1000.00',
            'version': 1,
          },
        ],
        'pagination': <String, dynamic>{'total_records': 1},
      };
    }
    if (method == 'GET' && path == '/api/v1/sales-returns') {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'sr-1',
            'return_number': 'SR-0001',
            'customer_name': 'Customer 1',
            'return_date': '2026-10-01',
            'status': 'DRAFT',
            'grand_total': '500.00',
          },
        ],
        'pagination': <String, dynamic>{'total_records': 1},
      };
    }
    if (path.endsWith('/dispatch-check')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'enforcement': 'OFF', 'message': null},
      };
    }
    if (method == 'POST' && path.startsWith('/api/v1/sales-returns/')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'id': 'sr-1',
          'return_number': 'SR-0001',
          'status': 'APPROVED',
        },
      };
    }
    if (method == 'POST') {
      return <String, dynamic>{'data': const <String, dynamic>{}};
    }
    return <String, dynamic>{'data': const <dynamic>[]};
  }
}

void _size(WidgetTester tester) {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

/// A document view carrying [strip], opened as a page opens it.
Future<List<Object?>> _view(WidgetTester tester, Widget strip) async {
  _size(tester);
  final List<Object?> closedWith = <Object?>[];
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () async {
            closedWith.add(await showDialog<Object>(
              context: context,
              builder: (_) => DocumentViewDialog(
                title: 'Document',
                subtitle: '',
                icon: Icons.description_outlined,
                header: const DocumentHeaderSnapshot(
                  documentTypeCode: 'X',
                  documentTypeName: 'X',
                  documentNumber: 'X-1',
                  documentDate: '2026-10-01',
                  status: 'DRAFT',
                ),
                lines: const [],
                totals: const DocumentTotalsSnapshot(
                  subtotal: '0',
                  discount: '0',
                  tax: '0',
                  charges: '0',
                  roundOff: '0',
                  grandTotal: '0',
                ),
                history: const [],
                steps: strip,
              ),
            ));
          },
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  return closedWith;
}

Finder _step(String id) => find.byKey(ValueKey<String>('document-step-$id'));

Future<void> _openRow(WidgetTester tester, String number) async {
  final Finder row = find.text(number).first;
  await tester.tap(row);
  await tester.pump(const Duration(milliseconds: 50));
  await tester.tap(row);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a draft bill offers Approve to an approver, and takes it', (
    tester,
  ) async {
    final _Api api = _Api();
    final List<Object?> closed = await _view(
      tester,
      DocumentStepStrip<DocumentRef>(
        record: const DocumentRef(id: 'pi-1', number: 'PI-1', status: 'DRAFT'),
        steps: purchaseInvoiceSteps(
          api,
          _permissions(const ['PURCHASE_VIEW', 'PURCHASE_APPROVE']),
        ),
      ),
    );
    expect(_step('approve'), findsOneWidget);
    await tester.tap(_step('approve'));
    await tester.pumpAndSettle();
    // PG-3 and PG-5: Approve opens a dialog, and the dialog approves.
    await tester.tap(find.byKey(const ValueKey('approve-bill-confirm')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('POST /api/v1/purchase-invoices/pi-1/approve'));
    expect(closed.single, isA<DocumentStepDone>());
  });

  testWidgets('a bill reader is offered no step', (tester) async {
    await _view(
      tester,
      DocumentStepStrip<DocumentRef>(
        record: const DocumentRef(id: 'pi-1', number: 'PI-1', status: 'DRAFT'),
        steps: purchaseInvoiceSteps(
          _Api(),
          _permissions(const ['PURCHASE_VIEW']),
        ),
      ),
    );
    expect(_step('approve'), findsNothing);
    expect(find.byKey(const ValueKey('document-steps-more')), findsNothing);
  });

  testWidgets('an approved return offers Complete, not Approve', (
    tester,
  ) async {
    await _view(
      tester,
      DocumentStepStrip<DocumentRef>(
        record:
            const DocumentRef(id: 'pr-1', number: 'PR-1', status: 'APPROVED'),
        steps: purchaseReturnSteps(
          _Api(),
          _permissions(const ['PURCHASE_APPROVE', 'PURCHASE_CANCEL']),
        ),
      ),
    );
    expect(_step('complete'), findsOneWidget);
    expect(_step('approve'), findsNothing);
  });

  testWidgets('a draft sales order offers Approve', (
    tester,
  ) async {
    final _Api api = _Api();
    final PermissionService manager =
        _permissions(const ['SALES_VIEW', 'SALES_APPROVE', 'SALES_CANCEL']);
    await _view(
      tester,
      DocumentStepStrip<Json>(
        record: const {'id': 'so-1', 'order_number': 'SO-1', 'status': 'DRAFT'},
        steps: salesOrderSteps(api, manager),
      ),
    );
    expect(_step('approve'), findsOneWidget);
    expect(_step('release'), findsNothing);
  });

  testWidgets('a held sales order offers Release, not Approve', (
    tester,
  ) async {
    final _Api api = _Api();
    final PermissionService manager =
        _permissions(const ['SALES_VIEW', 'SALES_APPROVE', 'SALES_CANCEL']);
    await _view(
      tester,
      DocumentStepStrip<Json>(
        record: const {
          'id': 'so-1',
          'order_number': 'SO-1',
          'status': 'APPROVED',
          'is_on_hold': true,
        },
        steps: salesOrderSteps(api, manager),
      ),
    );
    expect(_step('release'), findsOneWidget);
    expect(_step('approve'), findsNothing);
  });

  testWidgets('a draft sales invoice offers Approve to an approver', (
    tester,
  ) async {
    await _view(
      tester,
      DocumentStepStrip<Json>(
        record: const {
          'id': 'si-1',
          'invoice_number': 'SI-1',
          'status': 'DRAFT',
        },
        steps: salesInvoiceSteps(
          _Api(),
          _permissions(const ['SALES_VIEW', 'SALES_APPROVE']),
        ),
      ),
    );
    expect(_step('approve'), findsOneWidget);
  });

  testWidgets('a refused step keeps the view open with the reason', (
    tester,
  ) async {
    final List<Object?> closed = await _view(
      tester,
      DocumentStepStrip<DocumentRef>(
        record: const DocumentRef(id: 'pi-1', number: 'PI-1', status: 'DRAFT'),
        steps: [
          DocumentStep<DocumentRef>(
            id: 'approve',
            label: 'Approve',
            icon: Icons.check,
            forward: true,
            permitted: true,
            allows: (_) => true,
            run: (_, __) async =>
                throw const ApiException('The period is closed.'),
          ),
        ],
      ),
    );
    await tester.tap(_step('approve'));
    await tester.pumpAndSettle();
    expect(closed, isEmpty);
    expect(find.text('The period is closed.'), findsOneWidget);
  });

  testWidgets('a delivery note window offers its next step', (tester) async {
    _size(tester);
    final Directory dir = Directory.systemTemp.createTempSync('dn-steps');
    addTearDown(() => dir.deleteSync(recursive: true));
    final _Api api = _Api(noteStatus: 'APPROVED');
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: DeliveryNoteManagementPage(
            api: api,
            preferences: DesktopPreferencesService(directory: dir),
            permissions: _permissions(const ['SALES_VIEW', 'SALES_APPROVE']),
            hasActiveFirm: true,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await _openRow(tester, 'DN-0001');
    expect(find.byType(DocumentViewDialog), findsOneWidget);
    expect(_step('dispatch'), findsOneWidget);
    expect(_step('approve'), findsNothing);

    await tester.tap(_step('dispatch'));
    await tester.pumpAndSettle();
    expect(api.calls, contains('POST /api/v1/delivery-notes/dn-1/dispatch'));
    expect(find.byType(DocumentViewDialog), findsNothing);
  });

  testWidgets('a sales return window offers Approve on a draft', (
    tester,
  ) async {
    _size(tester);
    final Directory dir = Directory.systemTemp.createTempSync('sr-steps');
    addTearDown(() => dir.deleteSync(recursive: true));
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: SalesReturnManagementPage(
            api: api,
            preferences: DesktopPreferencesService(directory: dir),
            permissions: _permissions(const ['SALES_VIEW', 'SALES_APPROVE']),
            hasActiveFirm: true,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await _openRow(tester, 'SR-0001');
    expect(_step('approve'), findsOneWidget);
    await tester.tap(_step('approve'));
    await tester.pumpAndSettle();
    expect(api.calls, ['POST /api/v1/sales-returns/sr-1/approve']);
  });
}
