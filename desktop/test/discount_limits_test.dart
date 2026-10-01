// Backlog 64 row 3, desktop half: a ceiling on hand-typed discounts per role.
//
// These pin: the dialog lists what the server holds, saves the WHOLE list with
// the exact keys the server declares, stays open with the server's message on a
// refusal, and is read-only without SALES_MANAGE_SETTINGS.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/discount_limits_dialog.dart';
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
  _LimitsApi({this.refuseSave = false, this.rolesAllowed = true})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool refuseSave;
  final bool rolesAllowed;
  Json? saved;

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
    if (path.endsWith('/discount-limits')) {
      if (method == 'PUT') {
        if (refuseSave) throw ApiException('Role CLERK appears twice.');
        saved = Map<String, dynamic>.from(body ?? const {});
        return {'success': true, 'data': body};
      }
      return {
        'success': true,
        'data': {
          'limits': [
            {'role_code': 'SALES_EXEC', 'max_discount_percent': '5.00'},
          ],
        },
      };
    }
    if (path.endsWith('/roles')) {
      if (!rolesAllowed) throw ApiException('Not allowed.');
      return {
        'success': true,
        'data': [
          _role('SALES_EXEC', 'Sales Executive'),
          _role('SALES_MANAGER', 'Sales Manager'),
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
      body: DiscountLimitsDialog(
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
    await _pump(tester, _LimitsApi(), ['SALES_VIEW', 'SALES_MANAGE_SETTINGS']);

    expect(find.text('Sales Executive'), findsOneWidget);
    expect(find.widgetWithText(TextField, '5.00'), findsOneWidget);
  });

  testWidgets('save sends the whole list with the declared keys',
      (tester) async {
    final _LimitsApi api = _LimitsApi();
    await _pump(tester, api, ['SALES_VIEW', 'SALES_MANAGE_SETTINGS']);

    await tester.tap(find.byKey(const ValueKey('discount-limit-add')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('discount-limit-role-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sales Manager').last);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('discount-limit-percent-1')), '15');
    await tester.tap(find.byKey(const ValueKey('discount-limits-save')));
    await tester.pumpAndSettle();

    expect(api.saved, {
      'limits': [
        {'role_code': 'SALES_EXEC', 'max_discount_percent': '5.00'},
        {'role_code': 'SALES_MANAGER', 'max_discount_percent': '15'},
      ],
    });
  });

  testWidgets('removing the only row saves an empty list', (tester) async {
    final _LimitsApi api = _LimitsApi();
    await _pump(tester, api, ['SALES_VIEW', 'SALES_MANAGE_SETTINGS']);

    await tester.tap(find.byKey(const ValueKey('discount-limit-remove-0')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('discount-limits-save')));
    await tester.pumpAndSettle();

    expect(api.saved, {'limits': <Object>[]});
  });

  testWidgets('without the right to list roles the code is typed',
      (tester) async {
    final _LimitsApi api = _LimitsApi(rolesAllowed: false);
    await _pump(tester, api, ['SALES_VIEW', 'SALES_MANAGE_SETTINGS']);

    expect(find.widgetWithText(TextField, 'SALES_EXEC'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('discount-limits-save')));
    await tester.pumpAndSettle();

    expect(api.saved?['limits'], [
      {'role_code': 'SALES_EXEC', 'max_discount_percent': '5.00'},
    ]);
  });

  testWidgets('a percent out of range is refused before any call',
      (tester) async {
    final _LimitsApi api = _LimitsApi();
    await _pump(tester, api, ['SALES_VIEW', 'SALES_MANAGE_SETTINGS']);

    await tester.enterText(
        find.byKey(const ValueKey('discount-limit-percent-0')), '150');
    await tester.tap(find.byKey(const ValueKey('discount-limits-save')));
    await tester.pumpAndSettle();

    expect(find.textContaining('from 0 to 100'), findsOneWidget);
    expect(api.saved, isNull);
  });

  testWidgets('a refused save keeps the dialog open with the message',
      (tester) async {
    final _LimitsApi api = _LimitsApi(refuseSave: true);
    await _pump(tester, api, ['SALES_VIEW', 'SALES_MANAGE_SETTINGS']);

    await tester.tap(find.byKey(const ValueKey('discount-limits-save')));
    await tester.pumpAndSettle();

    expect(find.text('Role CLERK appears twice.'), findsOneWidget);
    expect(find.byType(DiscountLimitsDialog), findsOneWidget);
  });

  testWidgets('without the manage permission the list is read-only',
      (tester) async {
    await _pump(tester, _LimitsApi(), ['SALES_VIEW']);

    final FilledButton save =
        tester.widget(find.byKey(const ValueKey('discount-limits-save')));
    expect(save.onPressed, isNull);
    final OutlinedButton add =
        tester.widget(find.byKey(const ValueKey('discount-limit-add')));
    expect(add.onPressed, isNull);
    final IconButton remove =
        tester.widget(find.byKey(const ValueKey('discount-limit-remove-0')));
    expect(remove.onPressed, isNull);
  });
}
