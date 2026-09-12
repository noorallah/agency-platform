import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/sales_order_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A refused lifecycle action on a sales order says why on screen.
///
/// Found on the 2026-09-12 manual pass (plan item 8.7): MEDI01 blocks on
/// credit, the server refused Approve with "GreenCross Hospital would be at
/// 136.5% of a 250000.00 credit limit ...", and the desktop showed nothing
/// -- the page's action runner had no catch, so the refusal went to the
/// crash log and the button appeared to do nothing. Every other document
/// page shows the server's sentence; this one does now.

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() {
  final PermissionService service = PermissionService();
  service.applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['SALES_VIEW', 'SALES_APPROVE'],
  }));
  return service;
}

const String _refusal = 'GreenCross Hospital would be at 136.5% of a '
    '250000.00 credit limit. Collect payment or raise the limit before '
    'continuing.';

class _BlockingApi extends ApiClient {
  _BlockingApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

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
    if (path.contains('/credit-status')) {
      // The pre-check says the server will block, so the client's own
      // notice stays silent and the server's refusal is all there is.
      return <String, dynamic>{
        'success': true,
        'data': <String, dynamic>{
          'customer_id': 'customer-1',
          'customer_name': 'GreenCross Hospital',
          'enforcement': 'BLOCK',
          'status': 'BLOCKED',
          'would_block': true,
          'message': _refusal,
        },
      };
    }
    if (path.endsWith('/approve')) {
      throw const ApiException(_refusal, statusCode: 422);
    }
    if (path.endsWith('/summary')) {
      return <String, dynamic>{
        'success': true,
        'data': <String, dynamic>{'total': 1, 'draft': 1},
      };
    }
    if (path.contains('/history') || path.contains('/timeline')) {
      return <String, dynamic>{'success': true, 'data': const <dynamic>[]};
    }
    return <String, dynamic>{
      'success': true,
      'data': <Map<String, dynamic>>[
        <String, dynamic>{
          'id': 'order-1',
          'order_number': 'SO-0001',
          'order_date': '2026-09-12',
          'status': 'DRAFT',
          'customer_id': 'customer-1',
          'grand_total': '341250.00',
          'lines': const <dynamic>[],
        },
      ],
      'pagination': <String, dynamic>{'total_records': 1},
    };
  }
}

void main() {
  testWidgets('a refused approval shows the server\'s reason', (tester) async {
    final Directory temp =
        Directory.systemTemp.createTempSync('sales-order-refusal');
    addTearDown(() => temp.deleteSync(recursive: true));
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SalesOrderManagementPage(
            api: _BlockingApi(),
            preferences: DesktopPreferencesService(directory: temp),
            permissions: _permissions(),
            hasActiveFirm: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OutlinedButton, 'Approve').first);
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.textContaining('136.5% of a 250000.00 credit limit'),
        findsOneWidget);
  });
}
