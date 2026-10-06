// D-UI-14: a code that already exists is not "somebody else saved this".
//
// The server answers a clash with 409, the same status it uses for a lost
// version race, so the dialogs read every 409 as a race. A create has no
// version to lose, so on a create the server's own sentence is shown.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/api/concurrency.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/pricing.dart';
import 'package:agency_desktop/ui/pricing/coupon_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const ApiException _clash = ApiException(
  'A coupon with this code already exists.',
  statusCode: 409,
  code: 'resource_conflict',
);

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  @override
  Future<PromotionCouponRecord> createPromotionCoupon(Json body) async =>
      throw _clash;
}

void main() {
  test('a create that clashes shows the server sentence; an edit still races',
      () {
    expect(
      saveFailureMessage(_clash, 'coupon', changesKept: true, isNew: true),
      'A coupon with this code already exists.',
    );
    expect(
      saveFailureMessage(_clash, 'coupon', changesKept: true),
      contains('Somebody else saved this coupon'),
    );
  });

  testWidgets('the coupon dialog names the clash on a duplicate code',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: CouponDialog(
          api: _Api(),
          promotions: <PromotionRecord>[
            PromotionRecord.fromJson(const <String, dynamic>{
              'id': 'p-1',
              'code': 'WELCOME',
              'name': 'Welcome',
              'status': 'ACTIVE',
              'priority': 100,
              'allow_stacking': true,
              'requires_coupon': true,
              'version': 1,
              'version_number': 1,
              'conditions': <Json>[],
              'actions': <Json>[],
            }),
          ],
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Code'), 'SAVE10');
    await tester.tap(find.widgetWithText(FilledButton, 'Create'));
    await tester.pumpAndSettle();

    expect(find.text('A coupon with this code already exists.'),
        findsOneWidget);
    expect(find.textContaining('Somebody else saved'), findsNothing);
  });
}
