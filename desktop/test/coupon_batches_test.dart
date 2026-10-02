// SEL-5: bulk single-use coupon codes. The dialog sends the count, prefix and
// window the person typed, keeps a refusal inside itself with everything
// typed, and offers the offer's CSV once the codes exist.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/pricing.dart';
import 'package:agency_desktop/phase2/phase2_scope.dart';
import 'package:agency_desktop/ui/pricing/coupon_batch_dialog.dart';
import 'package:agency_desktop/ui/pricing/promotion_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api extends ApiClient {
  _Api({this.refusal})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String? refusal;
  Json? sentBody;
  String? sentPath;
  final List<String> downloads = <String>[];

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
    sentPath = '$method $path';
    sentBody = body;
    if (refusal != null) throw ApiException(refusal!, statusCode: 422);
    return <String, dynamic>{
      'data': <String, dynamic>{
        'count': 3,
        'codes': <String>['DIWALI-AAAA', 'DIWALI-BBBB', 'DIWALI-CCCC'],
      },
    };
  }

  @override
  Future<List<int>> downloadBytes(
    String path, {
    Map<String, String>? query,
    String method = 'GET',
    Json? body,
    bool retrying = false,
  }) async {
    downloads.add(path);
    return utf8.encode('Code,Status\nDIWALI-AAAA,ACTIVE\n');
  }
}

PromotionRecord _offer() => PromotionRecord.fromJson(<String, dynamic>{
      'id': 'p-1',
      'code': 'DIWALI',
      'name': 'Diwali',
      'status': 'ACTIVE',
      'priority': 100,
      'allow_stacking': true,
      'requires_coupon': true,
      'version': 1,
      'version_number': 1,
      'conditions': <Json>[],
      'actions': <Json>[],
    });

Future<void> _open(
  WidgetTester tester,
  _Api api, {
  List<MapEntry<String, List<int>>>? saved,
}) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: CouponBatchDialog(
        api: api,
        promotions: <PromotionRecord>[_offer()],
        saveBytesOverride: saved == null
            ? null
            : (name, bytes) async => saved.add(MapEntry(name, bytes)),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('generate sends the count, prefix and window typed',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);

    await tester.enterText(
        find.byKey(const ValueKey<String>('coupon-batch-count')), '3');
    await tester.enterText(
        find.byKey(const ValueKey<String>('coupon-batch-prefix')), 'diwali');
    await tester.enterText(
        find.byKey(const ValueKey<String>('coupon-batch-from')), '2026-10-01');
    await tester.tap(find.byKey(const ValueKey<String>('coupon-batch-generate')));
    await tester.pumpAndSettle();

    expect(api.sentPath, 'POST /api/v1/promotions/p-1/coupons/generate');
    expect(api.sentBody, <String, dynamic>{
      'count': 3,
      'prefix': 'diwali',
      'effective_from': '2026-10-01',
    });
    expect(find.text('3 codes generated'), findsOneWidget);
  });

  testWidgets('a refusal stays in the dialog with what was typed',
      (tester) async {
    final _Api api = _Api(refusal: 'That prefix is already in use.');
    await _open(tester, api);

    await tester.enterText(
        find.byKey(const ValueKey<String>('coupon-batch-count')), '7');
    await tester.tap(find.byKey(const ValueKey<String>('coupon-batch-generate')));
    await tester.pumpAndSettle();

    expect(find.text('That prefix is already in use.'), findsOneWidget);
    expect(find.byKey(const ValueKey<String>('coupon-batch-done')), findsNothing);
    final TextField count = tester.widget<TextField>(
        find.byKey(const ValueKey<String>('coupon-batch-count')));
    expect(count.controller!.text, '7');
  });

  testWidgets('a count out of range is caught before the server is asked',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);

    await tester.enterText(
        find.byKey(const ValueKey<String>('coupon-batch-count')), '5001');
    await tester.tap(find.byKey(const ValueKey<String>('coupon-batch-generate')));
    await tester.pumpAndSettle();

    expect(api.sentPath, isNull);
    expect(find.text('How many must be 1 to 5000.'), findsOneWidget);
  });

  testWidgets('Save as CSV saves the exported bytes', (tester) async {
    final _Api api = _Api();
    final List<MapEntry<String, List<int>>> saved = [];
    await _open(tester, api, saved: saved);

    await tester.tap(find.byKey(const ValueKey<String>('coupon-batch-generate')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey<String>('coupon-batch-save-csv')));
    await tester.pumpAndSettle();

    expect(api.downloads.single, '/api/v1/promotions/p-1/coupons/export');
    expect(saved.single.key, 'Coupons DIWALI.csv');
    expect(utf8.decode(saved.single.value), startsWith('Code,Status'));
  });

  testWidgets('phase 2 offers Generate codes and Export codes behind the menu',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Phase2Scope(
        child: Scaffold(
          body: PromotionPage(
            api: api,
            permissions: PermissionService()
              ..applyAccessToken(
                'h.${base64Url.encode(utf8.encode(jsonEncode(<String, dynamic>{
                      'roles': <String>['user'],
                      'permissions': <String>[
                        'PROMOTION_VIEW',
                        'PROMOTION_MANAGE',
                      ],
                    }))).replaceAll('=', '')}.s',
              ),
            hasActiveFirm: true,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('toolbar-more')).first);
    await tester.pumpAndSettle();
    expect(find.text('Generate codes'), findsOneWidget);
    expect(find.text('Export codes'), findsOneWidget);
  });
}
