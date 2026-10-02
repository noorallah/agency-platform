// SEL-8: copy last season's offers with new dates. The dialog sends the ids,
// the window and the suffix, defaults the suffix from the From year, keeps a
// refusal inside itself, and the command is offered only to those who may
// manage promotions.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/pricing.dart';
import 'package:agency_desktop/phase2/phase2_scope.dart';
import 'package:agency_desktop/ui/pricing/promotion_copy_dialog.dart';
import 'package:agency_desktop/ui/pricing/promotion_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _offerJson() => <String, dynamic>{
      'id': 'p-1',
      'code': 'DIWALI',
      'name': 'Diwali',
      'status': 'ACTIVE',
      'priority': 100,
      'allow_stacking': true,
      'requires_coupon': false,
      'version': 1,
      'version_number': 1,
      'conditions': <Json>[],
      'actions': <Json>[],
    };

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
    if (method == 'GET') {
      return <String, dynamic>{
        'data': <Json>[_offerJson()],
        'pagination': <String, dynamic>{'total_records': 1},
      };
    }
    sentPath = '$method $path';
    sentBody = body;
    if (refusal != null) throw ApiException(refusal!, statusCode: 422);
    return <String, dynamic>{
      'data': <Json>[
        <String, dynamic>{..._offerJson(), 'id': 'p-2', 'code': 'DIWALI-26'},
      ],
    };
  }
}

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(
    'h.${base64Url.encode(utf8.encode(jsonEncode(<String, dynamic>{
          'roles': <String>['user'],
          'permissions': codes,
        }))).replaceAll('=', '')}.s',
  );

Future<void> _open(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: PromotionCopyDialog(
        api: api,
        promotions: <PromotionRecord>[PromotionRecord.fromJson(_offerJson())],
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _fill(WidgetTester tester) async {
  await tester.enterText(
      find.byKey(const ValueKey<String>('promotion-copy-from')), '2026-10-01');
  await tester.enterText(
      find.byKey(const ValueKey<String>('promotion-copy-to')), '2026-11-15');
}

void main() {
  testWidgets('copy sends the ids, the window and the suffix', (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    expect(find.text('DIWALI'), findsOneWidget);

    await _fill(tester);
    await tester.tap(find.byKey(const ValueKey<String>('promotion-copy-save')));
    await tester.pumpAndSettle();

    expect(api.sentPath, 'POST /api/v1/promotions/copy');
    expect(api.sentBody, <String, dynamic>{
      'promotion_ids': <String>['p-1'],
      'effective_from': '2026-10-01',
      'effective_to': '2026-11-15',
      'code_suffix': '-26',
    });
    expect(find.byType(PromotionCopyDialog), findsNothing);
  });

  testWidgets('the suffix follows the From year until it is typed over',
      (tester) async {
    await _open(tester, _Api());
    TextField suffix() => tester.widget<TextField>(
        find.byKey(const ValueKey<String>('promotion-copy-suffix')));

    await tester.enterText(
        find.byKey(const ValueKey<String>('promotion-copy-from')),
        '2027-04-01');
    expect(suffix().controller!.text, '-27');

    await tester.enterText(
        find.byKey(const ValueKey<String>('promotion-copy-suffix')), '-NEW');
    await tester.enterText(
        find.byKey(const ValueKey<String>('promotion-copy-from')),
        '2028-04-01');
    expect(suffix().controller!.text, '-NEW');
  });

  testWidgets('a refusal stays in the dialog with what was typed',
      (tester) async {
    final _Api api = _Api(refusal: 'Code DIWALI-26 is already taken.');
    await _open(tester, api);

    await _fill(tester);
    await tester.tap(find.byKey(const ValueKey<String>('promotion-copy-save')));
    await tester.pumpAndSettle();

    expect(find.text('Code DIWALI-26 is already taken.'), findsOneWidget);
    expect(find.byType(PromotionCopyDialog), findsOneWidget);
    final TextField from = tester.widget<TextField>(
        find.byKey(const ValueKey<String>('promotion-copy-from')));
    expect(from.controller!.text, '2026-10-01');
  });

  Future<void> openPage(WidgetTester tester, List<String> codes) async {
    tester.view.physicalSize = const Size(1600, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Phase2Scope(
        child: Scaffold(
          body: PromotionPage(
            api: _Api(),
            permissions: _permissions(codes),
            hasActiveFirm: true,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('toolbar-more')).first);
    await tester.pumpAndSettle();
  }

  testWidgets('the command is offered to those who manage promotions',
      (tester) async {
    await openPage(tester, ['PROMOTION_VIEW', 'PROMOTION_MANAGE']);
    expect(find.text('Copy with new dates...'), findsOneWidget);
  });

  testWidgets('the command is hidden without PROMOTION_MANAGE', (tester) async {
    await openPage(tester, ['PROMOTION_VIEW']);
    expect(find.text('Copy with new dates...'), findsNothing);
  });
}
