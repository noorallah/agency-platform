// Backlog 68 row 4, desktop half: the largest purchase order each role may
// approve.
//
// These pin: the dialog lists what the server holds, saves the WHOLE list with
// the exact keys the server declares, stays open with the server's message on a
// refusal, is read-only without PURCHASE_MANAGE_SETTINGS, and is offered under
// Settings > Buying.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/phase2/menu_layout.dart';
import 'package:agency_desktop/ui/purchases/purchase_approval_limits_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '');
  return 'header.$payload.signature';
}

PermissionService _withPermissions(List<String> permissions) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': permissions,
      }));

Json _role(String code, String name) => <String, dynamic>{
      'id': code,
      'code': code,
      'name': name,
      'description': '',
      'is_active': true,
      'is_system': true,
    };

class _LimitsApi extends ApiClient {
  _LimitsApi({this.refuseSave = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool refuseSave;
  Json? saved;
  String? savedPath;

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
    if (path.endsWith('/approval-limits')) {
      if (method == 'PUT') {
        if (refuseSave) throw ApiException('Role BUYER is listed twice.');
        saved = Map<String, dynamic>.from(body ?? const {});
        savedPath = path;
        return {'success': true, 'data': body};
      }
      return {
        'success': true,
        'data': {
          'limits': [
            {'role_code': 'BUYER', 'max_order_amount': '50000.00'},
          ],
        },
      };
    }
    if (path.endsWith('/roles')) {
      return {
        'success': true,
        'data': [
          _role('BUYER', 'Buyer'),
          _role('PURCHASE_MANAGER', 'Purchase Manager'),
        ],
        'pagination': {'total_records': 2},
      };
    }
    throw StateError('unexpected $method $path');
  }
}

Future<void> _pump(
  WidgetTester tester,
  _LimitsApi api,
  List<String> codes,
) async {
  tester.view.physicalSize = const Size(1200, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: PurchaseApprovalLimitsDialog(
        api: api,
        permissions: _withPermissions(codes),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('loads the limits the server holds, by role name',
      (tester) async {
    await _pump(
        tester, _LimitsApi(), ['PURCHASE_VIEW', 'PURCHASE_MANAGE_SETTINGS']);

    expect(find.text('Buyer'), findsOneWidget);
    expect(find.widgetWithText(TextField, '50000.00'), findsOneWidget);
  });

  testWidgets('save sends the whole list with the declared keys',
      (tester) async {
    final _LimitsApi api = _LimitsApi();
    await _pump(tester, api, ['PURCHASE_VIEW', 'PURCHASE_MANAGE_SETTINGS']);

    await tester.tap(find.byKey(const ValueKey('approval-limit-add')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('approval-limit-role-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Purchase Manager').last);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('approval-limit-amount-1')), '500000');
    await tester.tap(find.byKey(const ValueKey('approval-limits-save')));
    await tester.pumpAndSettle();

    expect(api.savedPath, '/api/v1/purchases/approval-limits');
    expect(api.saved, {
      'limits': [
        {'role_code': 'BUYER', 'max_order_amount': '50000.00'},
        {'role_code': 'PURCHASE_MANAGER', 'max_order_amount': '500000'},
      ],
    });
  });

  testWidgets('a negative amount is refused before any call', (tester) async {
    final _LimitsApi api = _LimitsApi();
    await _pump(tester, api, ['PURCHASE_VIEW', 'PURCHASE_MANAGE_SETTINGS']);

    await tester.enterText(
        find.byKey(const ValueKey('approval-limit-amount-0')), '-5');
    await tester.tap(find.byKey(const ValueKey('approval-limits-save')));
    await tester.pumpAndSettle();

    expect(find.textContaining('zero or more'), findsOneWidget);
    expect(api.saved, isNull);
  });

  testWidgets('a refused save keeps the dialog open with the message',
      (tester) async {
    final _LimitsApi api = _LimitsApi(refuseSave: true);
    await _pump(tester, api, ['PURCHASE_VIEW', 'PURCHASE_MANAGE_SETTINGS']);

    await tester.tap(find.byKey(const ValueKey('approval-limits-save')));
    await tester.pumpAndSettle();

    expect(find.text('Role BUYER is listed twice.'), findsOneWidget);
    expect(find.byType(PurchaseApprovalLimitsDialog), findsOneWidget);
  });

  testWidgets('without the manage permission the list is read-only',
      (tester) async {
    await _pump(tester, _LimitsApi(), ['PURCHASE_VIEW']);

    final FilledButton save =
        tester.widget(find.byKey(const ValueKey('approval-limits-save')));
    expect(save.onPressed, isNull);
    final OutlinedButton add =
        tester.widget(find.byKey(const ValueKey('approval-limit-add')));
    expect(add.onPressed, isNull);
  });

  test('is offered under Settings > Buying to purchase viewers', () {
    final MenuItemSpec item = MenuLayout.settings.groups
        .singleWhere((group) => group.label == 'Buying')
        .items
        .singleWhere((item) => item.path == MenuLayout.approvalLimitsRoute);
    expect(item.label, 'Approval Limits');
    expect(item.isSetting, isTrue);
    expect(item.permission, 'PURCHASE_VIEW');
  });
}
