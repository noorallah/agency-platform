import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';

/// Coupons (book section CP), the Coupons side of Settings > Set up >
/// Pricing > Promotions. Run as tradeadmin, then qsmgr (SM), qsexe (FS),
/// qro (RO) for the Role cases.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('CP: coupon cases ($itHandle)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server me = await Server.connect();
    final Server admin = await Server.connectAs(
        't10069cwy.tradeadmin@fixtures.local', fixturePassword);
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('cp-$itHandle');
    final String stamp =
        DateTime.now().millisecondsSinceEpoch.toString().substring(6);

    Future<bool> openCoupons() async {
      await closeOpenEditor(tester);
      try {
        await openSetUp(tester, 'sales/promotions');
      } on TestFailure {
        return false;
      }
      final Finder tab = find.text('Coupons');
      if (tab.evaluate().isEmpty) return true;
      await tester.tap(tab.first);
      await pumpFor(tester, const Duration(seconds: 2));
      return true;
    }

    Future<void> couponsList() async {
      if (!await openCoupons()) throw StateError('Promotions not offered');
      await refreshList(tester);
    }

    Future<void> chooseOffer(String code) async {
      await tester.tap(find.text('Offer').last);
      await pumpFor(tester, const Duration(milliseconds: 600));
      await tester.tap(find.textContaining(code).last);
      await pumpFor(tester, const Duration(milliseconds: 600));
    }

    /// N1 to N3 for the coupon dialog, which carries no keys: it is open
    /// while its Create button is.
    Future<String> refuse(Future<void> Function() typing,
        {String? typed}) async {
      final int before = await totalOf(me, 'promotions/coupons');
      await typing();
      final Set<String> beforeText = textOnScreen(tester).toSet();
      await tapButton(tester, 'Create');
      await pumpFor(tester, const Duration(seconds: 3));
      final bool open = find.text('Create').evaluate().isNotEmpty;
      final List<String> said = <String>[
        noticeText(tester),
        ...textOnScreen(tester)
            .where((String t) => t.length < 200 && !beforeText.contains(t)),
      ].where((String t) => t.isNotEmpty).toList();
      final int after = await totalOf(me, 'promotions/coupons');
      final String saw = 'open=$open, saved=${after - before}, '
          'said="${said.take(3).join(' | ')}"';
      final List<String> faults = <String>[
        if (said.isEmpty) 'N1: nothing says why',
        if (!open) 'N2: the dialog closed',
        if (open && typed != null && !screenHasTyped(tester, typed))
          'N2: typed "$typed" is gone',
        if (after != before) 'N3: ${after - before} saved',
      ];
      if (faults.isNotEmpty) {
        throw StateError('${faults.join('; ')} [$saw]');
      }
      return saw;
    }

    Json offerBody(String code, {bool coupon = true}) => <String, dynamic>{
          'code': code,
          'name': 'Coupon case $code',
          'priority': 100,
          'status': 'ACTIVE',
          'allow_stacking': true,
          'requires_coupon': coupon,
          'conditions': <Json>[],
          'actions': <Json>[
            <String, dynamic>{
              'action_type': 'LINE_DISCOUNT_PERCENT',
              'sequence': 1,
              'percent': '5',
            },
          ],
        };

    if (itHandle == 'tradeadmin') {
      final String offerCode = 'CPO$stamp';
      final Json offer = (await admin.write(
          'POST', '/api/v1/promotions', offerBody(offerCode))) as Json;
      final String dupCode = 'CPD$stamp';
      await admin.write('POST', '/api/v1/promotions/coupons', <String, dynamic>{
        'promotion_id': offer['id'],
        'code': dupCode,
        'status': 'ACTIVE',
      });

      await log.step('SC-CP-001 coupons list opens with its columns', () async {
        await couponsList();
        final List<String> missing = <String>[
          for (final String h in <String>[
            'Code', 'Offer', 'Claimed', 'Per customer', 'Status'
          ])
            if (!screenHas(tester, h)) h,
        ];
        log.saw = '+ New ${buttonState(tester, '+ New')}; '
            'coupon $dupCode listed=${screenHas(tester, dupCode)}';
        if (missing.isNotEmpty) throw StateError('not on screen: $missing');
      });

      // -- Negative -------------------------------------------------------
      await log.step('SC-CP-008 no Code and no Offer: Create is refused',
          () async {
        await couponsList();
        await tapNew(tester);
        log.saw = await refuse(() async {});
      });
      await closeOpenEditor(tester);

      await log.step('SC-CP-008 a Code but no Offer', () async {
        await couponsList();
        await tapNew(tester);
        log.saw = await refuse(() async {
          await typeLabelled(tester, 'Code', 'CPN$stamp');
        }, typed: 'CPN$stamp');
      });
      await closeOpenEditor(tester);

      await log.step('SC-CP-009 the same Code twice is refused in words',
          () async {
        await couponsList();
        await tapNew(tester);
        await chooseOffer(offerCode);
        log.saw = await refuse(() async {
          await typeLabelled(tester, 'Code', dupCode);
        }, typed: dupCode);
      });
      await closeOpenEditor(tester);

      await log.step('SC-CP-010 Live until before Live from is refused',
          () async {
        await couponsList();
        await tapNew(tester);
        await chooseOffer(offerCode);
        log.saw = await refuse(() async {
          await typeLabelled(tester, 'Code', 'CPU$stamp');
          await typeLabelled(tester, 'Live from', '2026-12-31');
          await typeLabelled(tester, 'Live until', '2026-01-01');
        }, typed: '2026-01-01');
      });
      await closeOpenEditor(tester);

      for (final String n in <String>['0', '999999']) {
        await log.step('SC-CP-011 Generate codes: How many $n is refused',
            () async {
          await couponsList();
          await tapMore(tester, 'Generate codes');
          await pumpFor(tester, const Duration(seconds: 2));
          final int before = await totalOf(me, 'promotions/coupons');
          await tester
              .tap(find.byKey(const ValueKey<String>('coupon-batch-offer')));
          await pumpFor(tester, const Duration(milliseconds: 600));
          await tester.tap(find.textContaining(offerCode).last);
          await pumpFor(tester, const Duration(milliseconds: 600));
          await typeInKeyed(tester, 'coupon-batch-count', n);
          await typeInKeyed(tester, 'coupon-batch-prefix', 'G$stamp');
          await tapKey(tester, 'coupon-batch-generate');
          final String said = await watch(tester, seconds: 4, confirm: false);
          final bool open = find
              .byKey(const ValueKey<String>('coupon-batch-generate'))
              .evaluate()
              .isNotEmpty;
          final bool fieldError = find
              .byKey(const ValueKey<String>('coupon-batch-field-error'))
              .evaluate()
              .isNotEmpty;
          final int after = await totalOf(me, 'promotions/coupons');
          final String words = textOnScreen(tester)
              .where((String t) =>
                  t.length < 120 &&
                  RegExp(r'many|most|least|between|above|limit|whole')
                      .hasMatch(t))
              .take(3)
              .join(' | ');
          log.saw = 'open=$open, saved=${after - before}, '
              'fieldError=$fieldError, said="$said", words="$words"';
          if (after != before) throw StateError('N3: ${after - before} saved');
          if (!open) throw StateError('N2: dialog closed');
          if (said.isEmpty && !fieldError && words.isEmpty) {
            throw StateError('N1: nothing says why');
          }
        });
        await closeOpenEditor(tester);
      }

      await log.step('SC-CP-016 the Cancel button on a typed dialog asks',
          () async {
        await couponsList();
        await tapNew(tester);
        await typeLabelled(tester, 'Code', 'CPC$stamp');
        await tapButton(tester, 'Cancel');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool gone = find.text('Create').evaluate().isEmpty;
        final bool asks = screenHas(tester, 'Keep editing') ||
            find.byType(AlertDialog).evaluate().length > 1;
        log.saw = 'dialog closed=$gone, asked=$asks';
        if (gone && !asks) {
          throw StateError('Cancel closed a dialog holding typing without '
              'asking (same family as SCRQ-21/29/33)');
        }
      });
      await closeOpenEditor(tester);

      // -- Positive -------------------------------------------------------
      await log.step('SC-CP-001 a new coupon is saved and listed', () async {
        await couponsList();
        await tapNew(tester);
        await chooseOffer(offerCode);
        await typeLabelled(tester, 'Code', 'CPK$stamp');
        await typeLabelled(tester, 'Total claims allowed', '1');
        await tapButton(tester, 'Create');
        await pumpFor(tester, const Duration(seconds: 3));
        final bool saved = ((await admin
                    .get('/api/v1/promotions/coupons?page_size=100'))
                as List<dynamic>)
            .cast<Json>()
            .any((Json r) => r['code'] == 'CPK$stamp');
        log.saw = 'saved=$saved, listed=${screenHas(tester, 'CPK$stamp')}';
        if (!saved) throw StateError('coupon not saved');
      });

      await log.step('SC-CP-002 Generate codes makes the codes asked for',
          () async {
        await couponsList();
        final int before = await totalOf(me, 'promotions/coupons');
        await tapMore(tester, 'Generate codes');
        await pumpFor(tester, const Duration(seconds: 2));
        await tester
            .tap(find.byKey(const ValueKey<String>('coupon-batch-offer')));
        await pumpFor(tester, const Duration(milliseconds: 600));
        await tester.tap(find.textContaining(offerCode).last);
        await pumpFor(tester, const Duration(milliseconds: 600));
        await typeInKeyed(tester, 'coupon-batch-count', '20');
        await typeInKeyed(tester, 'coupon-batch-prefix', 'G$stamp');
        await tapKey(tester, 'coupon-batch-generate');
        await pumpFor(tester, const Duration(seconds: 4));
        final int after = await totalOf(me, 'promotions/coupons');
        final bool done = find
            .byKey(const ValueKey<String>('coupon-batch-done'))
            .evaluate()
            .isNotEmpty;
        log.saw = 'codes made=${after - before}, done panel=$done '
            '(Save as CSV not pressed: it opens the file chooser)';
        if (after - before != 20) throw StateError('expected 20 new codes');
        await closeOpenEditor(tester);
      });

      await log.step('SC-CP-007 an offer needing a coupon says so', () async {
        await openSetUp(tester, 'sales/promotions');
        await tester.tap(find.text('Offers').first);
        await pumpFor(tester, const Duration(seconds: 2));
        await tester.enterText(find.byType(TextField).first, offerCode);
        await tester.testTextInput.receiveAction(TextInputAction.done);
        await pumpFor(tester, const Duration(seconds: 2));
        await selectRow(tester, offerCode);
        log.saw = 'texts: ${textOnScreen(tester).where((String t) => t.contains('oupon')).take(6).join(' | ')}';
        if (!screenHas(tester, 'Only with a coupon')) {
          throw StateError("no 'Only with a coupon' on the Offers row");
        }
      });
    } else {
      final bool offered = await openCoupons();
      final Map<String, String> s = offered
          ? <String, String>{
              for (final String b in <String>[
                '+ New', 'Edit', 'Delete'
              ])
                b: buttonState(tester, b),
            }
          : <String, String>{};
      Future<void> noWrites() async {
        final List<String> on = <String>[
          for (final String b in <String>['+ New', 'Edit', 'Delete'])
            if (s[b] == 'enabled') b,
        ];
        if (on.isNotEmpty) throw StateError('write buttons enabled: $on');
      }

      if (itHandle == 'qsmgr') {
        await log.step('SC-CP-018 SM: Coupons readable at most, no writes',
            () async {
          log.saw = 'offered=$offered $s';
          await noWrites();
        });
      } else if (itHandle == 'qro') {
        await log.step('SC-CP-020 RO: Coupons readable, no write buttons',
            () async {
          log.saw = 'offered=$offered $s';
          if (!offered) throw StateError('Promotions not offered to RO');
          await noWrites();
        });
      } else if (itHandle == 'qsexe') {
        await log.step('SC-CP-019 FS: creating coupons is not offered',
            () async {
          log.saw = 'offered=$offered $s';
          await noWrites();
        });
      }
    }

    if (itHandle == 'tradeadmin') {
      for (final String id in <String>[
        'SC-CP-003', 'SC-CP-004', 'SC-CP-005', 'SC-CP-006', 'SC-CP-012',
        'SC-CP-013', 'SC-CP-014', 'SC-CP-015', 'SC-CP-017', 'SC-CP-021',
        'SC-CP-022',
      ]) {
        log.skip(id, 'not driven in this pass (needs priced documents or a '
            'file chooser)');
      }
    }
    log.finish();
  });
}
