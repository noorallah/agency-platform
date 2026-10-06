// D-UI-13: a validation refusal shows the sentence the server sent.
//
// The server answers a 422 with "The request validation failed." and the
// reason -- "A promotion cannot end before it starts." -- in `details`. The
// shared save-failure text used to print only the first, so a person saw a
// sentence that names nothing. This drives the offer dialog, which saves
// through it, and the helper itself.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/api/concurrency.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/firm_member.dart';
import 'package:agency_desktop/models/pricing.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/pricing/promotion_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const ApiException _refusal = ApiException(
  'The request validation failed.',
  statusCode: 422,
  code: 'validation_error',
  details: <Object?>[
    <String, dynamic>{
      'field': 'body',
      'message': 'A promotion cannot end before it starts.',
      'code': 'value_error',
    },
  ],
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
  Future<List<PrincipalRecord>> principals() async =>
      const <PrincipalRecord>[];

  @override
  Future<List<FirmMember>> firmMembers() async => const <FirmMember>[];

  @override
  Future<PromotionRecord> updatePromotion(
    String id,
    Json body, {
    int? expectedVersion,
  }) async =>
      throw _refusal;
}

void main() {
  test('a validation refusal carries its reasons into the save message', () {
    final String text =
        saveFailureMessage(_refusal, 'promotion', changesKept: true);
    expect(text, contains('A promotion cannot end before it starts.'));
  });

  testWidgets('the offer dialog shows why the server refused it',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    const PromotionRecord existing = PromotionRecord(
      id: 'promo-1',
      code: 'TEN',
      name: 'Ten percent off',
      version: 4,
      priority: 10,
      status: 'ACTIVE',
      allowStacking: true,
      actions: <PromotionActionRecord>[
        PromotionActionRecord(
            actionType: 'LINE_DISCOUNT_PERCENT', percent: '10'),
      ],
      conditions: <PromotionConditionRecord>[],
    );
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () => showDialog<bool>(
              context: context,
              builder: (_) => PromotionDialog(api: _Api(), existing: existing),
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(find.byType(PromotionDialog), findsOneWidget);
    expect(
      find.textContaining('A promotion cannot end before it starts.'),
      findsOneWidget,
    );
  });
}
