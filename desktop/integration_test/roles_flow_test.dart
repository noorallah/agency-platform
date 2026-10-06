import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'harness.dart';

/// One user's view of the firm. The app starts once per process, so run this
/// file once per user, one after another, signed in as that user:
///
///     for u in qsexe qsmgr qstore qacct qpexe qpmgr qro qgone; do
///       IT_EMAIL=t10069cwy.$u@fixtures.local IT_PASSWORD='Fixture@2026pw' \
///         bash integration_test/run.sh roles_flow_test.dart
///     done
///
/// What each user does depends on the part of the address after the suffix
/// (the "handle"); every user first walks the menu and opens every screen it
/// offers, flagging the ones that answer an error. The hand-over chain
/// (salesperson, manager, storekeeper, accountant) passes documents on by
/// being the newest on the server and the list: the next user must see the
/// previous one's.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('roles: one user, the screens and the chain',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final String handle = itEmail.split('@').first.split('.').last;
    final FlowLog flow = FlowLog('roles-$handle');
    final Server server = await Server.connect();
    await startAndSignIn(tester);

    final RegExp broken = RegExp(
        r'403|forbidden|not allowed|permission|went wrong|could not|failed|'
        r'coming soon|not built|no analytics|error',
        caseSensitive: false);

    // -- What the menu offers, and whether each item opens -----------------
    await flow.step('menu: walk every offered screen', () async {
      final Finder areaKeys = find.byWidgetPredicate((Widget w) {
        final Key? k = w.key;
        return k is ValueKey<String> &&
            k.value.startsWith('menu-area-') &&
            !<String>[
              'menu-area-current',
              'menu-area-settings',
              'menu-area-more',
              'menu-area-home',
            ].contains(k.value);
      });
      final List<String> areas = <String>{
        for (final Element e in areaKeys.evaluate())
          (e.widget.key! as ValueKey<String>).value.substring(10),
      }.toList();
      // ignore: avoid_print
      print('FLOW: MENU [$handle] areas: ${areas.join(', ')}');
      if (areas.isEmpty) {
        flow.defect('menu', 'this user is offered no menu area at all');
      }
      int opened = 0;
      for (final String area in areas) {
        await tester.tap(find.byKey(ValueKey<String>('menu-area-$area')));
        await pumpFor(tester, const Duration(milliseconds: 600));
        final Finder showAll =
            find.byKey(const ValueKey<String>('menu-show-all'));
        if (showAll.evaluate().isNotEmpty) {
          await tester.tap(showAll);
          await pumpFor(tester, const Duration(milliseconds: 600));
        }
        final List<String> items = <String>[
          for (final Element e in find
              .byWidgetPredicate((Widget w) {
                final Key? k = w.key;
                return k is ValueKey<String> &&
                    k.value.startsWith('menu-item-');
              })
              .evaluate())
            (e.widget.key! as ValueKey<String>).value.substring(10),
        ];
        await tester.sendKeyEvent(LogicalKeyboardKey.escape);
        await pumpFor(tester, const Duration(milliseconds: 400));
        // ignore: avoid_print
        print('FLOW: MENU [$handle] $area: ${items.join(', ')}');
        if (items.isEmpty) {
          flow.defect('menu: $area', 'the area is offered but holds nothing');
        }
        for (final String path in items.toSet()) {
          if (opened++ > 70) break;
          try {
            await openMenu(tester, area, path);
          } catch (error) {
            flow.defect('menu: $path', 'could not be opened: $error');
            continue;
          }
          final List<String> texts = textOnScreen(tester);
          final List<String> bad = texts
              .skip(14)
              .where((String t) => t.length < 220 && broken.hasMatch(t))
              .toList();
          if (bad.isNotEmpty) {
            flow.defect('menu: $path',
                'opens a screen saying: ${bad.take(3).join(' | ')}');
          } else if (texts.length < 22) {
            flow.defect('menu: $path',
                'opens an almost empty screen: ${texts.skip(12).join(' | ')}');
          }
        }
      }
    });

    // -- Per user ----------------------------------------------------------
    Future<Json?> newest(String collection) => server.newest(collection);

    switch (handle) {
      case 'qsexe':
        await flow.step('salesperson: raise an order, find no approve',
            () async {
          await openMenu(tester, 'sell', 'salesOrders');
          await tapNew(tester);
          await chooseIn(tester, 'sales-order-customer', 'Vijaya Stores');
          await chooseIn(tester, 'sales-order-line-product-0', 'Detergent');
          await typeIn(tester, 'sales-order-line-0', 1, '3');
          await pumpFor(tester, const Duration(seconds: 3));
          await saveEditor(tester, 'sales-order-save');
          final Json? order = await newest('sales-orders');
          if (order == null || '${order['status']}' != 'DRAFT') {
            throw StateError('no new draft order (newest: ${order?['status']})');
          }
          await selectRow(tester, docNumber(order));
          final Finder approve = find.ancestor(
              of: find.text('Approve'),
              matching: find.byWidgetPredicate(
                  (Widget w) => w is ButtonStyleButton && w.onPressed != null));
          final bool offered = approve.evaluate().isNotEmpty;
          // ignore: avoid_print
          print('FLOW: INFO [qsexe] order ${docNumber(order)} is DRAFT; '
              'Approve offered to a salesperson: $offered');
          if (offered) {
            flow.defect('salesperson: approve', 'Approve is offered');
          }
        });
        await flow.step('salesperson: open a customer, credit limit', () async {
          await openMenu(tester, 'masters', 'masters/customers');
          await pumpFor(tester, const Duration(seconds: 2));
          // ignore: avoid_print
          print('FLOW: INFO [qsexe] customers screen: '
              '${textOnScreen(tester).skip(14).take(30).join(' | ')}');
        });
      case 'qsmgr':
        await flow.step('manager: find the salesperson draft and approve',
            () async {
          final Json? order = await newest('sales-orders');
          if (order == null || '${order['status']}' != 'DRAFT') {
            throw StateError('the newest order is not a draft: '
                '${order?['status']}');
          }
          await openMenu(tester, 'sell', 'salesOrders');
          await selectRow(tester, docNumber(order));
          await tapButton(tester, 'Approve');
          await confirmIfAsked(tester);
          await pumpFor(tester, const Duration(seconds: 3));
          final Json after = await server.one('sales-orders', '${order['id']}');
          if ('${after['status']}' != 'APPROVED') {
            throw StateError('status is ${after['status']} after Approve');
          }
        });
      case 'qstore':
        await flow.step('storekeeper: deliver the approved order', () async {
          final Json? order = await newest('sales-orders');
          if (order == null || '${order['status']}' != 'APPROVED') {
            throw StateError('the newest order is ${order?['status']}');
          }
          await openMenu(tester, 'sell', 'deliveryNotes/delivery-notes');
          await tapNew(tester);
          await chooseIn(tester, 'delivery-note-order', docNumber(order));
          await pumpFor(tester, const Duration(seconds: 2));
          await saveEditor(tester, 'delivery-note-save');
          final Json? note = await newest('delivery-notes');
          if (note == null) throw StateError('no note saved');
          await selectRow(tester, docNumber(note));
          await tapButton(tester, 'Approve');
          await confirmIfAsked(tester);
          await pumpFor(tester, const Duration(seconds: 3));
          await tapButton(tester, 'Dispatch');
          final Finder anyway =
              find.byKey(const ValueKey<String>('dispatch-anyway'));
          if (anyway.evaluate().isNotEmpty) {
            await tester.tap(anyway.first);
          } else {
            await confirmIfAsked(tester);
          }
          await pumpFor(tester, const Duration(seconds: 3));
          final Json after = await server.one('delivery-notes', '${note['id']}');
          if ('${after['status']}' != 'DISPATCHED') {
            throw StateError('note is ${after['status']}; screen said '
                '"${noticeText(tester)}"');
          }
        });
      case 'qacct':
        await flow.step('accountant: bill the note and take the receipt',
            () async {
          await openMenu(tester, 'sell', 'salesInvoices/sales-invoices');
          await tapNew(tester);
          await chooseIn(tester, 'sales-invoice-bill-customer', 'Vijaya Stores');
          await tapKey(tester, 'sales-invoice-choose-notes');
          await pumpFor(tester, const Duration(seconds: 2));
          await tester.tap(find
              .descendant(
                  of: find.byType(Dialog), matching: find.byType(Checkbox))
              .first);
          await pumpFor(tester, const Duration(milliseconds: 500));
          await confirmIfAsked(tester);
          await saveEditor(tester, 'sales-invoice-save');
          final Json? bill = await newest('sales-invoices');
          if (bill == null) throw StateError('no bill saved');
          await selectRow(tester, docNumber(bill));
          await tapButton(tester, 'Approve');
          await confirmIfAsked(tester);
          await pumpFor(tester, const Duration(seconds: 3));
          final Json after = await server.one('sales-invoices', '${bill['id']}');
          if ('${after['status']}' == 'DRAFT') {
            throw StateError('bill still DRAFT');
          }
        });
        await flow.step('accountant: record a receipt', () async {
          await openMenu(tester, 'sell', 'accounting/receipts');
          await tapNew(tester);
          await typeLabelled(tester, 'Received from', 'Vijaya');
          await pumpFor(tester, const Duration(seconds: 1));
          await tester.tap(find.textContaining('Vijaya Stores').last);
          await pumpFor(tester, const Duration(seconds: 2));
          await typeLabelled(tester, 'Amount', '10');
          final int before =
              ((await server.get('/api/v1/receipts?page_size=100')) as List)
                  .length;
          await tapButtonStarting(tester, 'Record ');
          await pumpFor(tester, const Duration(seconds: 3));
          final int after =
              ((await server.get('/api/v1/receipts?page_size=100')) as List)
                  .length;
          if (after != before + 1) throw StateError('receipt not recorded');
        });
        await flow.step('accountant: approve a purchase order', () async {
          await openMenu(tester, 'buy', 'purchases/purchase-orders');
          final Finder approve = find.ancestor(
              of: find.text('Approve'),
              matching: find.byWidgetPredicate(
                  (Widget w) => w is ButtonStyleButton && w.onPressed != null));
          // ignore: avoid_print
          print('FLOW: INFO [qacct] Approve offered on purchase orders: '
              '${approve.evaluate().isNotEmpty}');
        });
      case 'qpexe':
        await flow.step('purchase officer: try sales bills', () async {
          final Finder item =
              find.byKey(const ValueKey<String>('menu-area-sell'));
          // ignore: avoid_print
          print('FLOW: INFO [qpexe] Sell area offered: '
              '${item.evaluate().isNotEmpty}');
        });
      case 'qgone':
        await flow.step('membership removed while signed in', () async {
          await openMenu(tester, 'sell', 'quotations');
          final Server platform = await Server.connectAs(
              'master.ops@agency.local', 'DemoAdmin@12345',
              firm: server.firmId);
          await platform.write('PUT',
              '/api/v1/users/3618d161-8912-4f7f-8a97-00e4ba897e9c/firms',
              <String, dynamic>{'assignments': <dynamic>[]});
          // ignore: avoid_print
          print('FLOW: INFO [qgone] membership removed over the API');
          await openMenu(tester, 'sell', 'salesOrders');
          await pumpFor(tester, const Duration(seconds: 4));
          // ignore: avoid_print
          print('FLOW: INFO [qgone] after removal the screen shows: '
              '${textOnScreen(tester).skip(10).take(30).join(' | ')}');
        });
      default:
        break;
    }

    flow.finish();
  });
}
