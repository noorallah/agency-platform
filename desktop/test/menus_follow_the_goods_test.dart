// The Inventory tracking screens follow the goods the firm trades in
// (backlog 89, step 6).
//
// No `testWidgets` here, so the API client talks to a real loopback server
// (see api_client_if_match_test.dart for why).

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:agency_desktop/ui/workspace/module_visibility.dart';
import 'package:flutter_test/flutter_test.dart';

const List<String> _trackingTabs = [
  'batches',
  'lots',
  'serials',
  'expiry-monitor',
];

PermissionService _service(List<String> permissions) {
  final String payload = base64Url.encode(
    utf8.encode(
      jsonEncode({
        'permissions': <String>[],
        'roles': const <String>[],
        'platform_admin': false,
        'firm_permissions': {'firm-1': permissions},
      }),
    ),
  );
  return PermissionService()
    ..applyAccessToken('h.$payload.s', activeFirmId: 'firm-1');
}

Set<String> _shown(Set<String>? tracking, List<String> permissions) {
  final ModuleVisibility view = ModuleVisibility(
    permissions: _service(permissions),
    goodsTracking: tracking,
  );
  return view
      .tabIds(ModuleCatalog.byId(AppModule.inventory))
      .where(_trackingTabs.contains)
      .toSet();
}

const List<String> _everything = ['BATCH_VIEW', 'SERIAL_VIEW', 'PRODUCT_VIEW'];

Future<ApiClient> _serverAnswering(List<Map<String, dynamic>> rows) async {
  final HttpServer server =
      await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  int calls = 0;
  server.listen((HttpRequest request) async {
    calls++;
    request.response
      ..statusCode = 200
      ..headers.contentType = ContentType.json
      ..write(jsonEncode(<String, dynamic>{'data': rows}));
    await request.response.close();
  });
  addTearDown(() {
    expect(calls, 1, reason: 'one request carries codes and tracking');
    return server.close(force: true);
  });
  return ApiClient(
    baseUrl: 'http://127.0.0.1:${server.port}',
    accessToken: () => null,
    refreshAccessToken: () async => false,
    activeFirmId: () => 'firm-1',
  );
}

void main() {
  group('the menu follows the goods', () {
    test('unknown tracking shows all four tabs', () {
      expect(_shown(null, _everything), _trackingTabs.toSet());
    });

    test('no tracking hides all four', () {
      expect(_shown(<String>{}, _everything), isEmpty);
    });

    test('BATCH shows batches and lots only', () {
      expect(_shown({'BATCH'}, _everything), {'batches', 'lots'});
    });

    test('BATCH and EXPIRY add the expiry monitor', () {
      expect(
        _shown({'BATCH', 'EXPIRY'}, _everything),
        {'batches', 'lots', 'expiry-monitor'},
      );
    });

    test('SERIAL shows serials only', () {
      expect(_shown({'SERIAL'}, _everything), {'serials'});
    });

    test('permissions still apply on top of the tracking', () {
      final Set<String> all = {'BATCH', 'EXPIRY', 'SERIAL'};
      expect(_shown(all, ['PRODUCT_VIEW']), isEmpty);
      expect(_shown(all, ['SERIAL_VIEW', 'PRODUCT_VIEW']), {'serials'});
      expect(_shown({'BATCH'}, ['SERIAL_VIEW', 'PRODUCT_VIEW']), isEmpty);
    });

    test('the one tab filter takes the tracking too', () {
      final List<String> ids = ModuleVisibility.tabsFor(
        ModuleCatalog.byId(AppModule.inventory),
        _service(_everything),
        hasActiveFirm: true,
        goodsTracking: {'SERIAL'},
      ).map((tab) => tab.id).toList();
      expect(ids, contains('serials'));
      expect(ids, isNot(contains('batches')));
    });
  });

  group('the client reads the goods tracking from the one request', () {
    test('a list on the INVENTORY row', () async {
      final ApiClient api = await _serverAnswering([
        {'code': 'SALES', 'goods_tracking': null},
        {
          'code': 'INVENTORY',
          'goods_tracking': ['BATCH', 'expiry'],
        },
      ]);
      final ActiveBusinessModules active = await api.activeBusinessModules();
      expect(active.codes, {'SALES', 'INVENTORY'});
      expect(active.goodsTracking, {'BATCH', 'EXPIRY'});
    });

    test('an empty list is none, not unknown', () async {
      final ApiClient api = await _serverAnswering([
        {'code': 'INVENTORY', 'goods_tracking': <String>[]},
      ]);
      expect((await api.activeBusinessModules()).goodsTracking, isEmpty);
    });

    test('an absent key is unknown', () async {
      final ApiClient api = await _serverAnswering([
        {'code': 'INVENTORY'},
        {'code': 'SALES', 'goods_tracking': null},
      ]);
      final ActiveBusinessModules active = await api.activeBusinessModules();
      expect(active.goodsTracking, isNull);
      expect(active.codes, {'INVENTORY', 'SALES'});
    });
  });
}
