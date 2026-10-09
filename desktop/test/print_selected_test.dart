// Print selected: several ticked bills, or several ticked challans, are
// fetched as one PDF and sent to the printer once. Before this a bill could
// only be printed one at a time, while Approve and Cancel already took a
// selection (owner, 2026-10-09).

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart' show Json;
import 'package:agency_desktop/ui/delivery_notes/delivery_note_management_page.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:agency_desktop/ui/workspace/printed_document.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:printing/printing.dart' show OutputType, Printer;
// ignore: implementation_imports
import 'package:printing/src/interface.dart' show PrintingPlatform;

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

Json _row(int n) => <String, dynamic>{
      'id': 'doc-$n',
      'invoice_number': 'INV-000$n',
      'delivery_note_number': 'DN-000$n',
      'invoice_date': '2026-10-09',
      'status': 'APPROVED',
      'grand_total': '1000.00',
      'customer_name': 'Customer $n',
      'version': n,
    };

/// Serves three rows to whichever list asks and records each download.
class _PrintApi extends ApiClient {
  _PrintApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  String? refusal;
  final List<(String, String, Json?)> downloads = <(String, String, Json?)>[];

  @override
  Future<List<int>> downloadBytes(
    String path, {
    Map<String, String>? query,
    String method = 'GET',
    Json? body,
    bool retrying = false,
  }) async {
    downloads.add((method, path, body));
    if (refusal != null) throw ApiException(refusal!, statusCode: 422);
    return <int>[37, 80, 68, 70];
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
    if (method == 'GET' && path.endsWith('/summary')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'total': 3, 'approved': 3},
      };
    }
    if (method == 'GET' &&
        (path == '/api/v1/sales-invoices' ||
            path == '/api/v1/delivery-notes')) {
      return <String, dynamic>{
        'data': <Json>[_row(1), _row(2), _row(3)],
        'pagination': <String, dynamic>{'total_records': 3},
      };
    }
    return <String, dynamic>{'data': <dynamic>[]};
  }
}

/// A print dialog that records what it was handed, so the test needs no
/// plugin and can say the run reached the printer once.
class _QuietPrinting extends PrintingPlatform {
  final List<String> printed = <String>[];

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);

  @override
  Future<bool> layoutPdf(
    Printer? printer,
    Object? onLayout,
    String name,
    Object? format,
    bool dynamicLayout,
    bool usePrinterSettings,
    OutputType outputType,
    bool forceCustomPrintPaper,
  ) async {
    printed.add(name);
    return true;
  }
}

Future<(_PrintApi, _QuietPrinting)> _pump(
  WidgetTester tester, {
  required bool invoices,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final _QuietPrinting printing = _QuietPrinting();
  PrintingPlatform.instance = printing;
  final Directory temp = Directory.systemTemp.createTempSync('print-selected');
  addTearDown(() => temp.deleteSync(recursive: true));
  final _PrintApi api = _PrintApi();
  final DesktopPreferencesService preferences =
      DesktopPreferencesService(directory: temp);
  // Viewing is all a print needs: no approve or cancel code is held.
  final PermissionService permissions = PermissionService()
    ..applyAccessToken(_accessToken({
      'roles': <String>['user'],
      'permissions': <String>['SALES_VIEW'],
    }));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: invoices
            ? SalesInvoiceManagementPage(
                api: api,
                preferences: preferences,
                permissions: permissions,
                hasActiveFirm: true,
              )
            : DeliveryNoteManagementPage(
                api: api,
                preferences: preferences,
                permissions: permissions,
                hasActiveFirm: true,
              ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return (api, printing);
}

Future<void> _tickTwo(WidgetTester tester) async {
  for (int i = 1; i <= 2; i++) {
    await tester.tap(find.byType(Checkbox).at(i));
    await tester.pumpAndSettle();
  }
}

void main() {
  test('the screen states the limit the server enforces', () {
    final String router = File(
      '../backend/app/sales_invoice/services/invoice_pdf.py',
    ).readAsStringSync();
    expect(router, contains('MAX_PRINT_RUN = $maxPrintRun'));
  });

  for (final bool invoices in <bool>[true, false]) {
    final String name = invoices ? 'sales invoices' : 'delivery notes';
    final String path = invoices
        ? '/api/v1/sales-invoices/bulk-print'
        : '/api/v1/delivery-notes/bulk-print';
    final String key = invoices ? 'invoice_ids' : 'note_ids';

    testWidgets('$name: Print selected is offered only for a selection',
        (tester) async {
      await _pump(tester, invoices: invoices);
      expect(find.text('Print selected'), findsNothing);
      await _tickTwo(tester);
      expect(find.text('Print selected'), findsOneWidget);
    });

    testWidgets('$name: both ids go in one request and print once',
        (tester) async {
      final (_PrintApi api, _QuietPrinting printing) =
          await _pump(tester, invoices: invoices);
      await _tickTwo(tester);

      await tester.tap(find.text('Print selected'));
      await tester.pumpAndSettle();

      expect(api.downloads, hasLength(1));
      expect(api.downloads.single.$1, 'POST');
      expect(api.downloads.single.$2, path);
      expect(api.downloads.single.$3, {
        key: ['doc-1', 'doc-2'],
      });
      expect(printing.printed, hasLength(1));
      expect(printing.printed.single, startsWith('2 '));
    });

    testWidgets('$name: a refusal shows the server message and prints nothing',
        (tester) async {
      final (_PrintApi api, _QuietPrinting printing) =
          await _pump(tester, invoices: invoices);
      api.refusal = 'This firm prints on a thermal roll, so print them one '
          'at a time.';
      await _tickTwo(tester);

      await tester.tap(find.text('Print selected'));
      await tester.pumpAndSettle();

      expect(find.textContaining('thermal roll'), findsOneWidget);
      expect(printing.printed, isEmpty);
    });
  }
}
