// Backlog 78 row 6: the supplier's e-way bill on a goods receipt. A completed
// receipt's editor is closed, so the Goods Receipts screen offers "Record
// e-way bill" for the selected receipt; it calls
// PUT /goods-receipts/{id}/eway-bill. The orphan-route guard counts the
// api_client method as a caller, so this pins the control that reaches it.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_management_page.dart';
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

class _Api extends ApiClient {
  _Api({this.status = 'COMPLETED', this.refusal, this.warning})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String status;
  final String? refusal;
  final String? warning;
  final List<List<String?>> recorded = <List<String?>>[];

  @override
  Future<GoodsReceiptRecord> setGoodsReceiptEwayBill(
    String id,
    String? number,
    String? date,
  ) async {
    recorded.add(<String?>[id, number, date]);
    if (refusal != null) throw ApiException(refusal!, statusCode: 422);
    return GoodsReceiptRecord.fromJson({
      'id': id,
      'grn_number': 'GRN-0001',
      'eway_bill_number': number,
      'eway_bill_date': date,
      'eway_bill_warning': warning,
    });
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
    if (path.endsWith('/summary')) {
      return {'data': <String, dynamic>{}};
    }
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

Future<void> _open(WidgetTester tester, _Api api, List<String> codes) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory temp = Directory.systemTemp.createTempSync('eway');
  addTearDown(() => temp.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: GoodsReceiptManagementPage(
          api: api,
          preferences: DesktopPreferencesService(directory: temp),
          permissions: _permissions(codes),
          hasActiveFirm: true,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.text('GRN-0001').first);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Finder get _recordButton => find.text('Record e-way bill');

Future<void> _fill(WidgetTester tester, String number, {String? date}) async {
  await tester.tap(_recordButton.first);
  await tester.pumpAndSettle();
  await tester.enterText(
      find.byKey(const ValueKey('eway-bill-number-input')), number);
  if (date != null) {
    await tester.enterText(
        find.byKey(const ValueKey('eway-bill-date-input')), date);
  }
  await tester.tap(find.byKey(const ValueKey('eway-bill-save')));
  await tester.pumpAndSettle();
}

void main() {
  const List<String> allowed = ['PURCHASE_VIEW', 'PURCHASE_UPDATE'];

  testWidgets('a completed receipt can be given its e-way bill', (
    tester,
  ) async {
    final _Api api = _Api();
    await _open(tester, api, allowed);

    await _fill(tester, ' 1234-5678 9012 ', date: '2026-09-02');

    expect(api.recorded, [
      ['gr-1', '1234-5678 9012', '2026-09-02'],
    ]);
    expect(find.byKey(const ValueKey('eway-bill-number-input')), findsNothing);
    expect(find.textContaining('E-way bill recorded'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a server warning is shown after the save', (tester) async {
    final _Api api = _Api(warning: 'Goods worth 60,000.00 need an e-way bill.');
    await _open(tester, api, allowed);

    await _fill(tester, '');

    expect(api.recorded, [
      ['gr-1', null, null],
    ]);
    expect(find.textContaining('Goods worth 60,000.00'), findsOneWidget);
  });

  testWidgets('a bad number is refused in the dialog, which stays open', (
    tester,
  ) async {
    final _Api api = _Api();
    await _open(tester, api, allowed);

    await _fill(tester, '12345');

    expect(find.text('An e-way bill number is 12 digits.'), findsOneWidget);
    expect(api.recorded, isEmpty);
  });

  testWidgets("the server's refusal stays in the dialog with what was typed", (
    tester,
  ) async {
    final _Api api = _Api(refusal: 'Cancelled receipts take no e-way bill.');
    await _open(tester, api, allowed);

    await _fill(tester, '123456789012');

    expect(find.text('Cancelled receipts take no e-way bill.'),
        findsOneWidget);
    expect(
        find.byKey(const ValueKey('eway-bill-number-input')), findsOneWidget);
    expect(find.text('123456789012'), findsOneWidget);
  });

  testWidgets('a cancelled receipt is not offered it', (tester) async {
    await _open(tester, _Api(status: 'CANCELLED'), allowed);
    expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
    expect(_recordButton, findsNothing);
  });

  testWidgets('someone who cannot update is not offered it', (tester) async {
    await _open(tester, _Api(), const ['PURCHASE_VIEW']);
    expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
    expect(_recordButton, findsNothing);
  });
}
