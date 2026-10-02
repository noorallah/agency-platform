// Backlog 78 row 5: the supplier's IRN on an approved bill. The bill's editor
// is read-only once approved, so the Purchase Invoices screen offers "Record
// IRN" for the selected bill; it calls PUT /purchase-invoices/{id}/supplier-irn.
// The orphan-route guard counts the api_client method as a caller, so this
// pins the control that reaches it.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const String _irn =
    '0123456789abcdef0123456789abcdef0123456789abcdef0123456789ABCDEF';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

class _Api extends ApiClient {
  _Api({this.status = 'APPROVED', this.refusal})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String status;
  final String? refusal;
  final List<String?> recorded = <String?>[];

  @override
  Future<Json> setPurchaseInvoiceSupplierIrn(String id, String? irn) async {
    recorded.add(irn);
    if (refusal != null) throw ApiException(refusal!, statusCode: 422);
    return {
      'data': {'id': id, 'supplier_irn': irn?.toLowerCase()},
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
    if (path.endsWith('/summary')) {
      return {'data': <String, dynamic>{}};
    }
    if (path.endsWith('/purchase-invoices')) {
      return {
        'data': [
          {
            'id': 'pi-1',
            'invoice_number': 'PI-0001',
            'invoice_date': '2026-08-13',
            'supplier_invoice_number': 'SUP-1',
            'status': status,
            'grand_total': '590.00',
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
  final Directory temp = Directory.systemTemp.createTempSync('irn');
  addTearDown(() => temp.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseInvoiceManagementPage(
          api: api,
          preferences: DesktopPreferencesService(directory: temp),
          permissions: _permissions(codes),
          hasActiveFirm: true,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.text('PI-0001').first);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Finder get _recordButton => find.text('Record IRN');

void main() {
  testWidgets('an approved bill can be given its IRN', (tester) async {
    final _Api api = _Api();
    await _open(tester, api, const ['PURCHASE_VIEW', 'PURCHASE_UPDATE']);

    await tester.tap(_recordButton.first);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('supplier-irn-input')),
      ' $_irn ',
    );
    await tester.tap(find.byKey(const ValueKey('supplier-irn-save')));
    await tester.pumpAndSettle();

    expect(api.recorded, [_irn]);
    expect(find.byKey(const ValueKey('supplier-irn-input')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('half an IRN is refused in the dialog, which stays open', (
    tester,
  ) async {
    final _Api api = _Api();
    await _open(tester, api, const ['PURCHASE_VIEW', 'PURCHASE_UPDATE']);

    await tester.tap(_recordButton.first);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('supplier-irn-input')),
      'abc',
    );
    await tester.tap(find.byKey(const ValueKey('supplier-irn-save')));
    await tester.pumpAndSettle();

    expect(find.textContaining('64 characters'), findsOneWidget);
    expect(api.recorded, isEmpty);
  });

  testWidgets("the server's refusal stays in the dialog with what was typed", (
    tester,
  ) async {
    final _Api api = _Api(refusal: 'Cancelled bills take no IRN.');
    await _open(tester, api, const ['PURCHASE_VIEW', 'PURCHASE_UPDATE']);

    await tester.tap(_recordButton.first);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('supplier-irn-input')),
      _irn,
    );
    await tester.tap(find.byKey(const ValueKey('supplier-irn-save')));
    await tester.pumpAndSettle();

    expect(find.text('Cancelled bills take no IRN.'), findsOneWidget);
    expect(find.byKey(const ValueKey('supplier-irn-input')), findsOneWidget);
    expect(find.text(_irn), findsOneWidget);
  });

  testWidgets('a blank box clears the IRN', (tester) async {
    final _Api api = _Api();
    await _open(tester, api, const ['PURCHASE_VIEW', 'PURCHASE_UPDATE']);

    await tester.tap(_recordButton.first);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('supplier-irn-save')));
    await tester.pumpAndSettle();

    expect(api.recorded, [null]);
  });

  testWidgets('a cancelled bill is not offered it', (tester) async {
    await _open(
      tester,
      _Api(status: 'CANCELLED'),
      const ['PURCHASE_VIEW', 'PURCHASE_UPDATE'],
    );
    expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
    expect(_recordButton, findsNothing);
  });

  testWidgets('someone who cannot update is not offered it', (tester) async {
    await _open(tester, _Api(), const ['PURCHASE_VIEW']);
    expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
    expect(_recordButton, findsNothing);
  });
}
