import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';

/// Principal claims (book section PC), Buy > All Buy screens > Principal
/// Claims. Run as tradeadmin (Negative, Positive), then qpmgr (PM), qpexe
/// (PU), qacct (AC), qro (RO) for the Role cases.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('PC: principal claim cases ($itHandle)',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server me = await Server.connect();
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('pc-$itHandle');
    const String menuPath = 'purchases/principal-claims';

    Future<bool> openClaims() async {
      await closeOpenEditor(tester);
      try {
        await openMenu(tester, 'buy', menuPath);
      } on TestFailure {
        return false;
      }
      await refreshList(tester);
      return true;
    }

    Future<String> refuse(
      String openKey,
      String button,
      Future<void> Function() typing, {
      String? typed,
      String problemKey = 'claim-problem',
    }) async {
      final int before = await totalOf(me, 'principal-claims');
      await typing();
      final Set<String> beforeText = textOnScreen(tester).toSet();
      await tapKey(tester, button);
      await pumpFor(tester, const Duration(seconds: 3));
      final bool open =
          find.byKey(ValueKey<String>(openKey)).evaluate().isNotEmpty;
      final String problem = '';
      final List<String> said = <String>[
        noticeText(tester),
        ...textOnScreen(tester)
            .where((String t) => t.length < 200 && !beforeText.contains(t)),
      ].where((String t) => t.isNotEmpty).toList();
      final int after = await totalOf(me, 'principal-claims');
      final String saw = 'open=$open, saved=${after - before}, '
          'said="${said.take(4).join(' | ')}" $problem';
      final List<String> faults = <String>[
        if (said.isEmpty) 'N1: nothing says why',
        if (!open) 'N2: the dialog closed',
        if (open && typed != null && !screenHasTyped(tester, typed))
          'N2: typed "$typed" is gone',
        if (after != before) 'N3: ${after - before} saved',
      ];
      if (faults.isNotEmpty) throw StateError('${faults.join('; ')} [$saw]');
      return saw;
    }

    if (itHandle == 'tradeadmin') {
      await log.step('SC-PC-001 Principal Claims opens with its grid and '
          'buttons', () async {
        if (!await openClaims()) throw StateError('not offered');
        final List<String> missing = <String>[
          for (final String h in <String>[
            'Number', 'Principal', 'Period', 'Status', 'Total'
          ])
            if (!screenHas(tester, h)) h,
        ];
        log.saw = 'Price cut claim '
            '${find.byKey(const ValueKey<String>('claim-new-price-cut')).evaluate().isNotEmpty ? 'present' : 'absent'}, '
            '+ New ${buttonState(tester, '+ New')}; missing $missing';
        if (missing.isNotEmpty) throw StateError('not on screen: $missing');
      });

      // -- Negative -------------------------------------------------------
      await log.step('SC-PC-011 New claim with no principal is refused',
          () async {
        if (!await openClaims()) throw StateError('not offered');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 1));
        log.saw = await refuse('claim-principal', 'claim-raise', () async {});
      });
      await closeOpenEditor(tester);

      await log.step('SC-PC-012 Preview with a principal and a period with '
          'nothing in it', () async {
        if (!await openClaims()) throw StateError('not offered');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 1));
        await chooseIn(tester, 'claim-principal', 'Principal t10069cwy');
        await tapKey(tester, 'claim-preview');
        await pumpFor(tester, const Duration(seconds: 3));
        final bool nothing = screenHas(tester, 'Nothing to claim');
        final bool result = find
            .byKey(const ValueKey<String>('claim-preview-result'))
            .evaluate()
            .isNotEmpty;
        log.saw = "preview result shown=$result, 'Nothing to claim' "
            'shown=$nothing; texts '
            '${textOnScreen(tester).where((String t) => t.length < 80 && RegExp(r'claim|Total|period|Nothing').hasMatch(t)).take(6).join(' | ')}';
        if (!result && !nothing && noticeText(tester).isEmpty) {
          throw StateError('N1: the preview answered nothing');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-PC-016 Price cut: Raise with no product is refused',
          () async {
        if (!await openClaims()) throw StateError('not offered');
        await tapKey(tester, 'claim-new-price-cut');
        await pumpFor(tester, const Duration(seconds: 1));
        log.saw = await refuse('pc-raise', 'pc-raise', () async {
          await chooseIn(tester, 'pc-principal', 'Principal t10069cwy');
        }, problemKey: 'pc-problem');
      });
      await closeOpenEditor(tester);

      await log.step('SC-PC-020 the Cancel button on a typed claim dialog '
          'asks', () async {
        if (!await openClaims()) throw StateError('not offered');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 1));
        await chooseIn(tester, 'claim-principal', 'Principal t10069cwy');
        await typeInKeyed(tester, 'claim-remarks', 'typed then left');
        await tapButton(tester, 'Cancel');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool gone = find
            .byKey(const ValueKey<String>('claim-principal'))
            .evaluate()
            .isEmpty;
        final bool asks = screenHas(tester, 'Keep editing') ||
            find.byType(AlertDialog).evaluate().length > 1;
        log.saw = 'dialog closed=$gone, asked=$asks';
        if (gone && !asks) {
          throw StateError('Cancel closed a dialog holding typing without '
              'asking (same family as SCRQ-21/29/33)');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-PC-005 Price cut: Preview answers on screen',
          () async {
        if (!await openClaims()) throw StateError('not offered');
        await tapKey(tester, 'claim-new-price-cut');
        await pumpFor(tester, const Duration(seconds: 1));
        await tapKey(tester, 'pc-preview');
        await pumpFor(tester, const Duration(seconds: 3));
        final String said = <String>[
          noticeText(tester),
          ...textOnScreen(tester).where((String t) =>
              t.length < 120 &&
              RegExp(r'Choose|Add|needs|must|Recalculate|Rate difference')
                  .hasMatch(t)),
        ].where((String t) => t.isNotEmpty).take(3).join(' | ');
        log.saw = 'preview with nothing chosen: "$said"';
        if (said.isEmpty) throw StateError('N1: the preview said nothing');
      });
      await closeOpenEditor(tester);

      for (final String id in <String>[
        'SC-PC-002', 'SC-PC-003', 'SC-PC-004', 'SC-PC-006', 'SC-PC-007',
        'SC-PC-008', 'SC-PC-009', 'SC-PC-010', 'SC-PC-013', 'SC-PC-014',
        'SC-PC-015', 'SC-PC-017', 'SC-PC-018', 'SC-PC-019', 'SC-PC-025',
        'SC-PC-026',
      ]) {
        log.skip(id, 'needs a principal-funded sale and a raised claim, '
            'which the fixture firm does not hold');
      }
    } else {
      final bool offered = await openClaims();
      final Map<String, String> s = offered
          ? <String, String>{
              '+ New': buttonState(tester, '+ New'),
              'Price cut claim': find
                      .byKey(const ValueKey<String>('claim-new-price-cut'))
                      .evaluate()
                      .isNotEmpty
                  ? 'enabled'
                  : 'absent',
            }
          : <String, String>{};
      if (itHandle == 'qpmgr') {
        await log.step('SC-PC-022 PM: offered with raise', () async {
          log.saw = 'offered=$offered $s';
          if (!offered) throw StateError('not offered to PM');
          if (s['+ New'] != 'enabled') throw StateError('no raise: $s');
        });
      } else if (itHandle == 'qpexe') {
        await log.step('SC-PC-021 PU: offered; buttons established', () async {
          log.saw = 'offered=$offered $s';
          if (!offered) throw StateError('not offered to PU');
        });
      } else if (itHandle == 'qacct') {
        await log.step('SC-PC-023 AC: screen offered or not', () async {
          log.saw = 'offered=$offered $s';
        });
      } else if (itHandle == 'qro') {
        await log.step('SC-PC-024 RO: readable, no write buttons', () async {
          log.saw = 'offered=$offered $s';
          if (!offered) throw StateError('not offered to Read Only');
          if (s['+ New'] == 'enabled' || s['Price cut claim'] == 'enabled') {
            throw StateError('a write button is enabled: $s');
          }
        });
      }
    }
    log.finish();
  });
}
