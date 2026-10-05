// Hold and recall at the counter, and the shift (backlog 87 #7, SG-7): Hold
// saves the bill and then parks it and opens a new one, Recall lists the held
// bills and loads the chosen one, the strip shows no shift and then the open
// one, closing posts the count and shows the difference, a refused open keeps
// its dialog open with the server's message, and the shifts list shows rows
// and saves a report.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/counter_shift_widgets.dart';
import 'package:agency_desktop/ui/sales/counter_shifts_page.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['SALES_VIEW'],
  }));

Json _shiftJson({
  String status = 'OPEN',
  String expected = '1500.00',
  int held = 0,
}) =>
    <String, dynamic>{
      'id': 'shift-1',
      'version': 1,
      'shift_number': 'SH-0001',
      'status': status,
      'cashier_id': 'u-1',
      'cashier_name': 'Asha',
      'opened_at': '2026-10-05T09:15:00+00:00',
      'closed_at': status == 'CLOSED' ? '2026-10-05T18:00:00+00:00' : null,
      'opening_float': '500.00',
      'expected_cash': expected,
      'counted_cash': status == 'CLOSED' ? '1450.00' : null,
      'difference': status == 'CLOSED' ? '-50.00' : null,
      'closing_note': null,
      'summary': <String, dynamic>{
        'bills': 4,
        'total_billed': '2300.00',
        'tenders': <String, dynamic>{
          'CASH': '1000.00',
          'UPI': '1300.00',
          'CARD': '0.00',
          'BANK_TRANSFER': '0.00',
        },
        'held_bills': held,
      },
    };

class _Api extends ApiClient {
  _Api({
    this.heldRows = const <Json>[],
    this.openRefusal,
    this.shift,
    this.shiftHeld = 0,
  }) : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  List<Json> heldRows;
  final String? openRefusal;
  Json? shift;
  final int shiftHeld;

  final List<String> calls = <String>[];
  final List<Json> created = <Json>[];
  final List<Json> bodies = <Json>[];
  final List<String> reportNames = <String>[];

  @override
  Future<List<int>> counterShiftReportPdf(String id) {
    calls.add('report:$id');
    return Future<List<int>>.value(<int>[1, 2, 3]);
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
    if (path.contains('workflow-settings')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'quotation_stage': false,
          'sales_order_stage': false,
          'delivery_note_stage': false,
          'default_warehouse_id': 'wh-main',
          'is_configured': true,
        },
      };
    }
    if (path.endsWith('/batch-serial/sale-settings')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'price_from_batch': false},
      };
    }
    if (method == 'GET' && path.startsWith('/api/v1/customers')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'cust-1',
            'code': 'C-1',
            'name': 'Walk-in Customer',
            'display_name': 'Walk-in Customer',
          },
        ],
      };
    }
    if (method == 'GET' && path.startsWith('/api/v1/products')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'prod-1',
            'code': 'P-1',
            'name': 'Soap',
            'barcode': '8901234567890',
            'selling_price': '50',
          },
        ],
      };
    }
    if (path.contains('billable')) return <String, dynamic>{'data': <Json>[]};
    if (path == '/api/v1/counter-shifts/current') {
      calls.add('shift-current');
      return <String, dynamic>{'data': shift};
    }
    if (method == 'POST' && path == '/api/v1/counter-shifts/open') {
      calls.add('shift-open');
      if (openRefusal != null) {
        throw ApiException(openRefusal!, statusCode: 409);
      }
      shift = _shiftJson();
      return <String, dynamic>{'data': shift};
    }
    if (method == 'GET' && path == '/api/v1/counter-shifts/shift-1') {
      return <String, dynamic>{'data': shift ?? _shiftJson(held: shiftHeld)};
    }
    if (method == 'POST' && path == '/api/v1/counter-shifts/shift-1/close') {
      calls.add('shift-close');
      bodies.add(body!);
      shift = null;
      return <String, dynamic>{'data': _shiftJson(status: 'CLOSED')};
    }
    if (method == 'GET' && path == '/api/v1/counter-shifts') {
      calls.add('shift-list:${query?['status'] ?? ''}');
      return <String, dynamic>{
        'data': <Json>[
          _shiftJson(),
          <String, dynamic>{..._shiftJson(status: 'CLOSED'), 'id': 'shift-2'},
        ],
        'pagination': <String, dynamic>{'total_records': 2},
      };
    }
    if (method == 'GET' && path == '/api/v1/sales-invoices') {
      calls.add('held-list');
      return <String, dynamic>{
        'data': heldRows,
        'pagination': <String, dynamic>{'total_records': heldRows.length},
      };
    }
    if (method == 'GET' && path.startsWith('/api/v1/sales-invoices/inv-')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'id': 'inv-held',
          'status': 'DRAFT',
          'invoice_date': '2026-10-05',
          'customer_id': 'cust-1',
          'customer_name': 'Walk-in Customer',
          'branch_id': 'branch-1',
          'version': 2,
          'is_held': false,
          'lines': <Json>[
            <String, dynamic>{
              'line_number': 1,
              'source_document_type': 'DELIVERY_NOTE',
              'source_document_id': 'dn-own',
              'source_document_number': 'DN-1',
              'source_document_line_id': 'dnl-1',
              'product_id': 'prod-1',
              'warehouse_id': 'wh-main',
              'description': 'Soap',
              'delivered_quantity': '1',
              'current_invoice_quantity': '1',
              'unit_price': '50',
              'discount_percent': '0',
            },
          ],
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/sales-invoices/preview') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'interstate': false,
          'invoice': <String, dynamic>{
            'invoice_number': 'SI-1',
            'subtotal': '50',
            'tax_total': '0',
            'grand_total': '50',
            'lines': const <Json>[],
          },
          'lines': const <Json>[],
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/sales-invoices') {
      calls.add('create');
      created.add(body!);
      return <String, dynamic>{
        'data': <String, dynamic>{
          'id': 'inv-${created.length}',
          'invoice_number': 'SI-${created.length}',
          'status': 'DRAFT',
          'version': 1,
        },
      };
    }
    if (method == 'POST' && path.endsWith('/hold')) {
      calls.add('hold:$path');
      bodies.add(body ?? const <String, dynamic>{});
      return <String, dynamic>{'data': <String, dynamic>{'is_held': true}};
    }
    if (method == 'POST' && path.endsWith('/recall')) {
      calls.add('recall:$path');
      return <String, dynamic>{'data': <String, dynamic>{'is_held': false}};
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

Future<void> _pumpEditor(
  WidgetTester tester,
  _Api api, {
  Size size = const Size(1600, 900),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: SalesInvoiceEditorDialog(
          api: api,
          today: DateTime(2026, 10, 5),
          mayApprove: true,
          printer: (context, bytes, name) async {},
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _scan(WidgetTester tester, String code) async {
  await tester.enterText(
      find.byKey(const ValueKey('counter-scan-field')), code);
  await tester.testTextInput.receiveAction(TextInputAction.done);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _chooseCustomer(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('sales-invoice-customer')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Walk-in Customer').last);
  await tester.pumpAndSettle();
}

Json _held(String id, String number) => <String, dynamic>{
      'id': id,
      'invoice_number': number,
      'customer_name': 'Walk-in Customer',
      'buyer_name': 'Ravi',
      'grand_total': '50.00',
      'held_at': '2026-10-05T10:00:00+00:00',
      'held_note': 'gone for cash',
      'is_held': true,
    };

void main() {
  testWidgets('Hold stays disabled until a line, then saves, holds and starts '
      'a fresh bill', (tester) async {
    final _Api api = _Api();
    await _pumpEditor(tester, api);
    expect(
        tester
            .widget<OutlinedButton>(
                find.byKey(const ValueKey('sales-invoice-hold')))
            .onPressed,
        isNull);
    await _chooseCustomer(tester);
    await _scan(tester, '8901234567890');
    expect(
        tester
            .widget<OutlinedButton>(
                find.byKey(const ValueKey('sales-invoice-hold')))
            .onPressed,
        isNotNull);

    await tester.tap(find.byKey(const ValueKey('sales-invoice-hold')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('hold-note')), 'gone for cash');
    await tester.tap(find.byKey(const ValueKey('hold-confirm')));
    await tester.pumpAndSettle();

    // Saved first, then held, in that order, with the note.
    final List<String> order = api.calls
        .where((c) => c == 'create' || c.startsWith('hold:'))
        .toList();
    expect(order, <String>['create', 'hold:/api/v1/sales-invoices/inv-1/hold']);
    expect(api.bodies.single, <String, dynamic>{'note': 'gone for cash'});
    // A new bill: the product is gone and Hold is disabled again.
    expect(find.text('Soap'), findsNothing);
    expect(
        tester
            .widget<OutlinedButton>(
                find.byKey(const ValueKey('sales-invoice-hold')))
            .onPressed,
        isNull);
    expect(tester.takeException(), isNull);
  });

  testWidgets('F8 holds the bill, and a blank note is fine', (tester) async {
    final _Api api = _Api();
    await _pumpEditor(tester, api);
    await _chooseCustomer(tester);
    await _scan(tester, '8901234567890');
    await tester.sendKeyEvent(LogicalKeyboardKey.f8);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('hold-confirm')));
    await tester.pumpAndSettle();
    expect(api.calls.any((c) => c.startsWith('hold:')), isTrue);
    expect(api.bodies.single, isEmpty);
  });

  testWidgets('Recall lists the held bills and loads the chosen one',
      (tester) async {
    final _Api api =
        _Api(heldRows: <Json>[_held('inv-held', 'SI-9'), _held('inv-2', 'SI-8')]);
    await _pumpEditor(tester, api);
    // The count is read once as the editor opens.
    expect(api.calls.where((c) => c == 'held-list').length, 1);
    expect(find.text('Recall (2)'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('sales-invoice-recall')));
    await tester.pumpAndSettle();
    expect(find.textContaining('SI-9'), findsOneWidget);
    expect(find.textContaining('Walk-in Customer (Ravi)'), findsWidgets);
    expect(find.textContaining('gone for cash'), findsWidgets);

    await tester.tap(find.byKey(const ValueKey('held-bill-inv-held')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('recall:/api/v1/sales-invoices/inv-held/recall'));
    // The draft is on screen as a saved bill being corrected.
    expect(find.text('Sales invoice'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the strip says no shift is open, then shows the one that is',
      (tester) async {
    final _Api api = _Api();
    await _pumpEditor(tester, api);
    expect(find.byKey(const ValueKey('counter-shift-strip')), findsOneWidget);
    expect(find.text('No shift open'), findsOneWidget);
    expect(api.calls.where((c) => c == 'shift-current').length, 1);

    await tester.tap(find.byKey(const ValueKey('counter-shift-open')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('shift-opening-float')), findsOneWidget);
    await tester.enterText(
        find.byKey(const ValueKey('shift-opening-float')), '500');
    await tester.tap(find.byKey(const ValueKey('shift-open-save')));
    await tester.pumpAndSettle();

    expect(find.text('No shift open'), findsNothing);
    expect(find.text('Shift SH-0001'), findsOneWidget);
    expect(find.text('4 bills'), findsOneWidget);
    expect(find.text('cash expected 1500.00'), findsOneWidget);
    expect(find.byKey(const ValueKey('counter-shift-close')), findsOneWidget);
  });

  testWidgets('a refused open keeps the dialog open with the message',
      (tester) async {
    final _Api api =
        _Api(openRefusal: 'You already have a shift open: SH-0001.');
    await _pumpEditor(tester, api);
    await tester.tap(find.byKey(const ValueKey('counter-shift-open')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('shift-open-save')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('shift-opening-float')), findsOneWidget);
    expect(find.text('You already have a shift open: SH-0001.'),
        findsOneWidget);
    expect(find.text('No shift open'), findsOneWidget);
  });

  testWidgets('Close shift posts the counted cash and shows the difference',
      (tester) async {
    final _Api api = _Api(shift: _shiftJson(held: 1), shiftHeld: 1);
    await _pumpEditor(tester, api);
    expect(find.text('Shift SH-0001'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('counter-shift-close')));
    await tester.pumpAndSettle();
    // Takings by mode and the expected cash, from a fresh read.
    expect(find.text('UPI'), findsOneWidget);
    expect(find.text('1300.00'), findsOneWidget);
    expect(find.byKey(const ValueKey('shift-held-warning')), findsOneWidget);

    await tester.enterText(
        find.byKey(const ValueKey('shift-counted-cash')), '1450');
    await tester.pumpAndSettle();
    expect(find.text('Short by 50.00'), findsOneWidget);
    await tester.enterText(
        find.byKey(const ValueKey('shift-counted-cash')), '1550');
    await tester.pumpAndSettle();
    expect(find.text('Over by 50.00'), findsOneWidget);
    await tester.enterText(
        find.byKey(const ValueKey('shift-counted-cash')), '1450');
    await tester.enterText(
        find.byKey(const ValueKey('shift-closing-note')), 'note one');
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('shift-close-save')));
    await tester.pumpAndSettle();
    expect(api.bodies.single,
        <String, dynamic>{'counted_cash': '1450', 'note': 'note one'});
    expect(find.byKey(const ValueKey('shift-closed-difference')),
        findsOneWidget);
    expect(find.text('Short by 50.00'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('shift-closed-done')));
    await tester.pumpAndSettle();
    // The strip is read again after the close: no shift is open now.
    expect(find.text('No shift open'), findsOneWidget);
  });

  testWidgets('the close dialog offers the report once closed',
      (tester) async {
    final _Api api = _Api(shift: _shiftJson());
    final List<String> saved = <String>[];
    tester.view.physicalSize = const Size(800, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: CloseShiftDialog(
          api: api,
          shiftId: 'shift-1',
          saveBytesOverride: (name, bytes) async => saved.add(name),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('shift-counted-cash')), '1500');
    await tester.tap(find.byKey(const ValueKey('shift-close-save')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('shift-print-report')));
    await tester.pumpAndSettle();
    expect(saved, <String>['Shift SH-0001.pdf']);
    expect(api.calls, contains('report:shift-1'));
    expect(find.byKey(const ValueKey('shift-report-message')), findsOneWidget);
  });

  testWidgets('the strip does not overflow at 800x600', (tester) async {
    final _Api api = _Api(shift: _shiftJson());
    await _pumpEditor(tester, api, size: const Size(800, 600));
    expect(find.byKey(const ValueKey('counter-shift-strip')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the shifts list shows rows, narrows by status, views and '
      'saves a report', (tester) async {
    final _Api api = _Api();
    final List<String> saved = <String>[];
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: CounterShiftsPage(
          api: api,
          permissions: _permissions(),
          hasActiveFirm: true,
          saveBytesOverride: (name, bytes) async => saved.add(name),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.text('SH-0001'), findsWidgets);
    expect(find.text('Asha'), findsWidgets);
    expect(find.text('Open'), findsWidgets);
    expect(find.text('Closed'), findsWidgets);

    await tester.tap(find.byKey(const ValueKey('shifts-status-')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Closed').last);
    await tester.pumpAndSettle();
    expect(api.calls, contains('shift-list:CLOSED'));

    // Print needs a row: nothing is offered until one is chosen.
    expect(find.byKey(const ValueKey('selection-print-shift-report')),
        findsNothing);
    await tester.tap(find.text('SH-0001').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('selection-view-shift')));
    await tester.pumpAndSettle();
    expect(find.text('1300.00'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('shift-summary-close')));
    await tester.pumpAndSettle();

    await tester
        .tap(find.byKey(const ValueKey('selection-print-shift-report')));
    await tester.pumpAndSettle();
    expect(saved, <String>['Shift SH-0001.pdf']);
    expect(tester.takeException(), isNull);
  });
}
