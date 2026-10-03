// SEL-13: the pick list and loading sheet over several ticked delivery notes.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart' show Json;
import 'package:agency_desktop/ui/delivery_notes/delivery_note_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:printing/printing.dart' show OutputType, Printer;
// ignore: implementation_imports
import 'package:printing/src/interface.dart' show PrintingPlatform;

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

Json _row(int n) => <String, dynamic>{
      'id': 'dn-$n',
      'delivery_note_number': 'DN-000$n',
      'status': 'APPROVED',
      'grand_total': '1000.00',
      'customer_name': 'Customer $n',
      'version': n,
    };

/// Records each sheet request; can be told to refuse them.
class _SheetApi extends ApiClient {
  _SheetApi()
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
    if (refusal != null) {
      throw ApiException(refusal!, statusCode: 422);
    }
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
    if (method == 'GET' && path == '/api/v1/delivery-notes') {
      return <String, dynamic>{
        'data': <Json>[_row(1), _row(2), _row(3)],
        'pagination': <String, dynamic>{'total_records': 3},
      };
    }
    return <String, dynamic>{'data': <dynamic>[]};
  }
}

/// A print dialog that does nothing, so the test needs no plugin.
class _QuietPrinting extends PrintingPlatform {
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
  ) async =>
      true;
}

Future<_SheetApi> _pump(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  PrintingPlatform.instance = _QuietPrinting();
  final Directory temp = Directory.systemTemp.createTempSync('dispatch-sheets');
  addTearDown(() => temp.deleteSync(recursive: true));
  final _SheetApi api = _SheetApi();
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: DeliveryNoteManagementPage(
          api: api,
          preferences: DesktopPreferencesService(directory: temp),
          permissions: PermissionService()
            ..applyAccessToken(_accessToken({
              'roles': <String>['user'],
              'permissions': <String>['SALES_VIEW', 'SALES_APPROVE'],
            })),
          hasActiveFirm: true,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return api;
}

Future<void> _tickTwo(WidgetTester tester) async {
  for (int i = 1; i <= 2; i++) {
    await tester.tap(find.byType(Checkbox).at(i));
    await tester.pumpAndSettle();
  }
}

void main() {
  testWidgets('ticking two notes offers both sheets', (tester) async {
    await _pump(tester);
    await _tickTwo(tester);
    expect(find.text('Pick list'), findsOneWidget);
    expect(find.text('Loading sheet'), findsOneWidget);
  });

  testWidgets('each sheet posts both ids to its own path', (tester) async {
    final _SheetApi api = await _pump(tester);
    await _tickTwo(tester);

    await tester.tap(find.text('Pick list'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Loading sheet'));
    await tester.pumpAndSettle();

    expect(api.downloads, hasLength(2));
    expect(api.downloads[0].$1, 'POST');
    expect(api.downloads[0].$2, '/api/v1/delivery-notes/pick-list');
    expect(api.downloads[0].$3, {
      'note_ids': ['dn-1', 'dn-2'],
    });
    expect(api.downloads[1].$1, 'POST');
    expect(api.downloads[1].$2, '/api/v1/delivery-notes/loading-sheet');
    expect(api.downloads[1].$3, {
      'note_ids': ['dn-1', 'dn-2'],
    });
  });

  testWidgets('a refusal shows the server message', (tester) async {
    final _SheetApi api = await _pump(tester);
    api.refusal = 'DN-0002 is completed; it cannot be picked.';
    await _tickTwo(tester);

    await tester.tap(find.text('Pick list'));
    await tester.pumpAndSettle();

    expect(find.textContaining('DN-0002 is completed'), findsOneWidget);
  });
}
