import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:agency_desktop/ui/workspace/label_print_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Barcode labels (STK-16): the dialog asks for the PDF with what was chosen,
/// and a refusal stays inside it.
class _LabelApi extends ApiClient {
  _LabelApi({this.status = 'COMPLETED'})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String status;
  String? refuse;
  Map<String, Object?>? productCall;
  Map<String, Object?>? receiptCall;

  @override
  Future<List<int>> productLabelsPdf({
    required List<Map<String, Object?>> items,
    String layout = 'A4_65',
    int skip = 0,
    bool showPrice = true,
  }) async {
    if (refuse != null) throw ApiException(refuse!, statusCode: 422);
    productCall = {
      'items': items,
      'layout': layout,
      'skip': skip,
      'showPrice': showPrice,
    };
    return const [37, 80, 68, 70];
  }

  @override
  Future<List<int>> goodsReceiptLabelsPdf(
    String receiptId, {
    String layout = 'A4_65',
    int skip = 0,
    bool showPrice = true,
  }) async {
    if (refuse != null) throw ApiException(refuse!, statusCode: 422);
    receiptCall = {
      'id': receiptId,
      'layout': layout,
      'skip': skip,
      'showPrice': showPrice,
    };
    return const [37, 80, 68, 70];
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
    if (path.endsWith('/summary')) return {'data': <String, dynamic>{}};
    if (path.endsWith('/goods-receipts')) {
      return {
        'data': [
          {
            'id': 'gr-1',
            'grn_number': 'GRN-0001',
            'receipt_date': '2026-09-01',
            'status': status,
            'grand_total': '60000.00',
            'lines': <Json>[],
          },
        ],
        'pagination': {'total_records': 1},
      };
    }
    return {
      'data': const <Json>[],
      'pagination': {'total_records': 0},
    };
  }
}

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

void _window(WidgetTester tester, [Size size = const Size(800, 600)]) {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

/// Opens the dialog from a button; [printed] collects what it would show.
Future<void> _openDialog(
  WidgetTester tester,
  _LabelApi api, {
  List<LabelProduct> products = const [],
  String? receiptId,
  List<String>? printed,
}) async {
  _window(tester);
  await tester.pumpWidget(MaterialApp(
    home: Builder(
      builder: (context) => TextButton(
        onPressed: () => showDialog<Object>(
          context: context,
          builder: (context) => LabelPrintDialog(
            api: api,
            subtitle: 'Test',
            products: products,
            receiptId: receiptId,
            openPdfOverride: (name, bytes) async =>
                printed?.add('$name:${bytes.length}'),
          ),
        ),
        child: const Text('open'),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

Finder _key(String key) => find.byKey(ValueKey<String>(key));

Future<void> _pick(WidgetTester tester, String label) async {
  await tester.tap(_key('label-layout'));
  await tester.pumpAndSettle();
  await tester.tap(find.text(label).last);
  await tester.pumpAndSettle();
}

void main() {
  const List<LabelProduct> products = [
    LabelProduct(id: 'p-1', name: 'Detergent 1kg'),
    LabelProduct(id: 'p-2', name: 'Soap'),
  ];

  testWidgets('products are sent with their copies, the sheet and the price',
      (tester) async {
    final _LabelApi api = _LabelApi();
    final List<String> printed = [];
    await _openDialog(tester, api, products: products, printed: printed);

    await _pick(tester, 'A4 sheet, 24 labels (64 x 34 mm)');
    await tester.enterText(_key('label-skip'), '5');
    await tester.enterText(_key('label-copies-p-1'), '12');
    await tester.tap(_key('label-show-price'));
    await tester.pump();
    await tester.tap(_key('label-print'));
    await tester.pumpAndSettle();

    expect(api.productCall, {
      'items': [
        {'product_id': 'p-1', 'copies': 12},
        {'product_id': 'p-2', 'copies': 1},
      ],
      'layout': 'A4_24',
      'skip': 5,
      'showPrice': false,
    });
    expect(printed, ['Product labels:4']);
    expect(find.byType(LabelPrintDialog), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a receipt is printed with its layout and defaults', (
    tester,
  ) async {
    final _LabelApi api = _LabelApi();
    final List<String> printed = [];
    await _openDialog(tester, api, receiptId: 'gr-1', printed: printed);

    await tester.enterText(_key('label-skip'), '64');
    await tester.tap(_key('label-print'));
    await tester.pumpAndSettle();

    expect(api.receiptCall, {
      'id': 'gr-1',
      'layout': 'A4_65',
      'skip': 64,
      'showPrice': true,
    });
    expect(printed.length, 1);
  });

  testWidgets('the roll has no sheet to part-use, so no skip box', (
    tester,
  ) async {
    final _LabelApi api = _LabelApi();
    await _openDialog(tester, api, receiptId: 'gr-1');
    expect(_key('label-skip'), findsOneWidget);

    await _pick(tester, 'Thermal roll 50 x 25 mm');
    expect(_key('label-skip'), findsNothing);

    await tester.tap(_key('label-print'));
    await tester.pumpAndSettle();
    expect(api.receiptCall?['layout'], 'ROLL_50X25');
    expect(api.receiptCall?['skip'], 0);
  });

  testWidgets('a used count past the sheet is refused before any call', (
    tester,
  ) async {
    final _LabelApi api = _LabelApi();
    await _openDialog(tester, api, receiptId: 'gr-1');

    await _pick(tester, 'A4 sheet, 24 labels (64 x 34 mm)');
    await tester.enterText(_key('label-skip'), '24');
    await tester.tap(_key('label-print'));
    await tester.pumpAndSettle();

    expect(find.textContaining('0 to 23'), findsWidgets);
    expect(api.receiptCall, isNull);
    expect(find.byType(LabelPrintDialog), findsOneWidget);
  });

  testWidgets("the server's refusal stays in the dialog with what was typed", (
    tester,
  ) async {
    final _LabelApi api = _LabelApi()..refuse = 'A receipt that is cancelled.';
    final List<String> printed = [];
    await _openDialog(tester, api, receiptId: 'gr-1', printed: printed);

    await tester.enterText(_key('label-skip'), '7');
    await tester.tap(_key('label-print'));
    await tester.pumpAndSettle();

    expect(find.text('A receipt that is cancelled.'), findsOneWidget);
    expect(find.byType(LabelPrintDialog), findsOneWidget);
    expect(find.text('7'), findsOneWidget);
    expect(printed, isEmpty);
  });

  Future<void> openReceipts(WidgetTester tester, _LabelApi api) async {
    _window(tester, const Size(1600, 1100));
    final Directory temp = Directory.systemTemp.createTempSync('labels');
    addTearDown(() => temp.deleteSync(recursive: true));
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: GoodsReceiptManagementPage(
            api: api,
            preferences: DesktopPreferencesService(directory: temp),
            permissions: _permissions(const ['PURCHASE_VIEW']),
            hasActiveFirm: true,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('GRN-0001').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
  }

  testWidgets('the Goods Receipts screen offers labels for the picked receipt',
      (tester) async {
    final _LabelApi api = _LabelApi();
    await openReceipts(tester, api);

    await tester.tap(find.text('Print labels').first);
    await tester.pumpAndSettle();
    expect(find.byType(LabelPrintDialog), findsOneWidget);
    await tester.tap(_key('label-print'));
    // The real print dialog cannot open in a test; the fetch is what matters.
    await tester.pump();
    expect(api.receiptCall?['id'], 'gr-1');
  });

  testWidgets('a cancelled receipt cannot be labelled', (tester) async {
    await openReceipts(tester, _LabelApi(status: 'CANCELLED'));
    // The bar offers only what applies to the picked row.
    expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
    expect(find.text('Print labels'), findsNothing);
    expect(find.byType(LabelPrintDialog), findsNothing);
  });
}
