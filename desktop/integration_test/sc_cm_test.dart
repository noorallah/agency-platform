import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';

/// Commission (book section CM), Sell > All Sell screens > Commission. Run
/// as tradeadmin (Negative, Positive), then qacct (AC), qsmgr (SM), qsexe
/// (FS), qro (RO) for the Role cases. Payouts are accrued over a past
/// period and cancelled again, so the period stays free.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('CM: commission cases ($itHandle)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server me = await Server.connect();
    final Server admin = await Server.connectAs(
        't10069cwy.tradeadmin@fixtures.local', fixturePassword);
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('cm-$itHandle');
    const String menuPath = 'sales/commission';

    Future<bool> openCommission(String view) async {
      await closeOpenEditor(tester);
      try {
        await openMenu(tester, 'sell', menuPath);
      } on TestFailure {
        return false;
      }
      final Finder tab = find.text(view);
      if (tab.evaluate().isNotEmpty) {
        await tester.tap(tab.first);
        await pumpFor(tester, const Duration(seconds: 2));
      }
      return true;
    }

    Future<String> refuseDialog(
      String collection,
      bool Function() isOpen,
      String button,
      Future<void> Function() typing, {
      String? typed,
    }) async {
      final int before = await totalOf(me, collection);
      await typing();
      final Set<String> beforeText = textOnScreen(tester).toSet();
      await tapButton(tester, button);
      await pumpFor(tester, const Duration(seconds: 3));
      final bool open = isOpen();
      final List<String> said = <String>[
        noticeText(tester),
        ...textOnScreen(tester).where((String t) =>
            t.length < 200 && !beforeText.contains(t)),
      ].where((String t) => t.isNotEmpty).toList();
      final int after = await totalOf(me, collection);
      final String saw = 'open=$open, saved=${after - before}, '
          'said="${said.take(3).join(' | ')}"';
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

    bool ruleOpen() => find.text('Rate shape').evaluate().isNotEmpty;
    bool accrueOpen() => find.text('Accrue a period').evaluate().isNotEmpty;

    if (itHandle == 'tradeadmin') {
      await log.step('SC-CM-001 Commission opens on Rates with its columns',
          () async {
        if (!await openCommission('Rates')) {
          throw StateError('Commission not offered');
        }
        final List<String> missing = <String>[
          for (final String h in <String>[
            'Applies to', 'On', 'Rate', 'In force', 'Status'
          ])
            if (!screenHas(tester, h)) h,
        ];
        log.saw = '+ New ${buttonState(tester, '+ New')} (Add rule); '
            'missing $missing';
        if (missing.isNotEmpty) throw StateError('not on screen: $missing');
      });

      // -- Negative -------------------------------------------------------
      for (final String rate in <String>['', '0', '-3']) {
        await log.step('SC-CM-012 rule with Rate "$rate" is refused',
            () async {
          await openCommission('Rates');
          await tapNew(tester);
          await pumpFor(tester, const Duration(seconds: 1));
          log.saw = await refuseDialog(
              'commission/rules', ruleOpen, 'Save', () async {
            if (rate.isNotEmpty) await typeLabelled(tester, 'Rate', rate);
          });
        });
        await closeOpenEditor(tester);
      }

      await log.step('SC-CM-013 Until before In force from is refused',
          () async {
        await openCommission('Rates');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 1));
        log.saw = await refuseDialog('commission/rules', ruleOpen, 'Save',
            () async {
          await typeLabelled(tester, 'Rate', '2');
          await typeLabelled(tester, 'In force from', '2026-12-31');
          await typeLabelled(tester, 'Until', '2026-01-01');
        }, typed: '2026-01-01');
      });
      await closeOpenEditor(tester);

      await log.step('SC-CM-022 the Cancel button on a typed rule asks',
          () async {
        await openCommission('Rates');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 1));
        await typeLabelled(tester, 'Rate', '4');
        await tapButton(tester, 'Cancel');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool gone = !ruleOpen();
        final bool asks = screenHas(tester, 'Keep editing');
        log.saw = 'dialog closed=$gone, asked=$asks, '
            'question="${dialogText(tester)}"';
        if (!asks) {
          throw StateError('Cancel on a dialog holding typing asked nothing '
              '(closed=$gone)');
        }
        await tapKey(tester, 'discard-keep-editing');
        await pumpFor(tester, const Duration(milliseconds: 600));
        final bool kept = screenHasTyped(tester, '4');
        log.saw = '${log.saw}; Keep editing kept the typing=$kept';
        if (!kept) throw StateError('Keep editing lost what was typed');
      });
      await closeOpenEditor(tester);

      await log.step('SC-CM-016 Accrue: no dates is refused', () async {
        await openCommission('Payouts');
        await tapButton(tester, '+ Accrue');
        await pumpFor(tester, const Duration(seconds: 1));
        await typeLabelled(tester, 'From', '');
        await typeLabelled(tester, 'To', '');
        log.saw = await refuseDialog(
            'commission/payouts', accrueOpen, 'Accrue', () async {});
      });
      await closeOpenEditor(tester);

      await log.step('SC-CM-016 Accrue: To before From is refused', () async {
        await openCommission('Payouts');
        await tapButton(tester, '+ Accrue');
        await pumpFor(tester, const Duration(seconds: 1));
        log.saw = await refuseDialog(
            'commission/payouts', accrueOpen, 'Accrue', () async {
          await typeLabelled(tester, 'From', '2026-06-30');
          await typeLabelled(tester, 'To', '2026-06-01');
        }, typed: '2026-06-01');
      });
      await closeOpenEditor(tester);

      await log.step('SC-CM-017 Accrue a period with no collections',
          () async {
        await openCommission('Payouts');
        final int before = await totalOf(me, 'commission/payouts');
        await tapButton(tester, '+ Accrue');
        await pumpFor(tester, const Duration(seconds: 1));
        await typeLabelled(tester, 'From', '2001-01-01');
        await typeLabelled(tester, 'To', '2001-01-31');
        await tapButton(tester, 'Accrue');
        final String said = await watch(tester, seconds: 5, confirm: false);
        final int after = await totalOf(me, 'commission/payouts');
        log.saw = 'payouts ${after - before} more, screen says "$said", '
            'dialog open=${accrueOpen()}';
        if (after != before) throw StateError('a payout was made for 2001');
        if (said.isEmpty && !screenHas(tester, 'Nothing')) {
          throw StateError('N1: nothing said');
        }
      });
      await closeOpenEditor(tester);

      // -- Positive -------------------------------------------------------
      await log.step('SC-CM-011 Collected view lists its report', () async {
        await openCommission('Collected');
        log.saw = 'texts: ${textOnScreen(tester).where((String t) => t.length < 40).skip(14).take(30).join(' | ')}; Show ${buttonState(tester, 'Show')}';
        final bool ok = screenHas(tester, 'Salesman') &&
            (screenHas(tester, 'Commission') || screenHas(tester, 'Collected'));
        if (!ok) throw StateError('report view shows no Salesman grid');
      });

      log.skip('SC-CM-005', 'accruing a real period would hold the period '
          'against the next run (one live payout per person per period); '
          'CM-015 to CM-021, CM-006 to CM-010 need that payout');
    } else {
      final bool offered = await openCommission('Rates');
      Map<String, String> s = <String, String>{};
      if (offered) {
        s = <String, String>{
          'Add rule': buttonState(tester, '+ New'),
          'Edit': buttonState(tester, 'Edit'),
        };
        await tester.tap(find.text('Payouts').first);
        await pumpFor(tester, const Duration(seconds: 2));
        s['Accrue period'] = buttonState(tester, '+ Accrue');
        for (final String b in <String>['Adjust', 'Approve', 'Pay', 'Cancel']) {
          s[b] = buttonState(tester, b);
        }
      }
      final List<String> writes = <String>[
        for (final String b in <String>['Add rule', 'Accrue period'])
          if (s[b] == 'enabled') b,
      ];
      if (itHandle == 'qacct') {
        await log.step('SC-CM-026 AC: Rates, Accrue, Approve, Pay offered',
            () async {
          log.saw = 'offered=$offered $s';
          if (!offered) throw StateError('Commission not offered to Accounts');
          if (s['Add rule'] != 'enabled' || s['Accrue period'] != 'enabled') {
            throw StateError('write buttons missing: $s');
          }
        });
      } else if (itHandle == 'qsmgr') {
        await log.step('SC-CM-024 SM: readable, no Add rule, Accrue, Approve, '
            'Pay', () async {
          log.saw = 'offered=$offered $s';
          if (!offered) throw StateError('Commission not offered to SM');
          if (writes.isNotEmpty) throw StateError('writes enabled: $writes');
        });
      } else if (itHandle == 'qsexe') {
        await log.step('SC-CM-025 FS: Commission not offered', () async {
          log.saw = 'offered=$offered';
          if (offered) throw StateError('Commission offered to Field Sales');
        });
      } else if (itHandle == 'qro') {
        await log.step('SC-CM-027 RO: readable, no write buttons', () async {
          log.saw = 'offered=$offered $s';
          if (!offered) throw StateError('Commission not offered to RO');
          if (writes.isNotEmpty) throw StateError('writes enabled: $writes');
        });
      }
    }
    log.finish();
  });
}
