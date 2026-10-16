import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';
import 'sell_data.dart';

/// The firm's own salesmen (P2; book 09, TC-SELL-114 to TC-SELL-118). Run on
/// the `ready-firm` fixture (`scripts/test_fixture.py ready-firm`) as
/// readyadmin, then as readyviewer.
///
/// The admin opens Settings > Selling > Salesmen, adds an entry tied to no
/// user, is refused a second one differing only in case (on New and on Edit),
/// ties one to himself and sees a new order start on it, makes that one
/// inactive and sees it neither offered nor chosen, saves an order naming the
/// untied entry and bills the note raised off it. Then "Salesman required" is
/// switched on in Sales stages, an order and a bill with no salesman are
/// refused, the switch goes back off and both save. The viewer is offered no
/// way to change the list or the switch, and the server is compared before
/// and after. App errors and overflows are counted the whole time.
///
/// The fixture holds no product, so the admin run makes one over HTTP with
/// 50 on hand (the same shape `test_fixture.py` gives its own products).

/// IT_PART=list (or chain, required) runs only that part, for re-driving one.
/// `chain` and `required` read the entries `list` made earlier in the run.
const String _part = String.fromEnvironment('IT_PART');
bool _runs(String part) => _part.isEmpty || _part.split(',').contains(part);

const String _dialog = 'crud-workspace-dialog-surface';
const String _salesmenTab = 'sales/salesmen';
const String _stagesTab = 'settings/sales-stages';
const String _workflow = '/api/v1/sales-orders/workflow-settings';
const String _requiredWords = 'requires a salesman';

String _today() => DateTime.now().toIso8601String().substring(0, 10);

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('SM: salesmen ($itHandle)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server admin = await Server.connectAs(
        '$itSuffix.readyadmin@fixtures.local', fixturePassword);
    final Server me = await Server.connect();
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('sm-$itHandle');
    final bool isAdmin = itHandle == 'readyadmin';

    // Names carry the minute the run started, so a second run on the same
    // fixture does not collide with the first.
    final DateTime now = DateTime.now();
    final String stamp = '${now.hour.toString().padLeft(2, '0')}'
        '${now.minute.toString().padLeft(2, '0')}';
    final String phone = 'Phone order $stamp';
    final String second = 'Phone Order 2 $stamp';
    final String asha = 'Asha $stamp';
    final String productName = 'SM Product $itSuffix';
    const String customer = 'Fixture Customer';

    String errorsSince(int from) => appErrors.skip(from).take(3).join(' || ');

    // -- Reading the server --------------------------------------------------
    Future<List<Json>> salesmen() async => <Json>[
          for (final dynamic row in (await admin
                  .get('/api/v1/salesmen?page_size=100')) as List<dynamic>)
            row as Json,
        ];
    Future<Json?> salesmanNamed(String name) async {
      for (final Json row in await salesmen()) {
        if (row['name'] == name) return row;
      }
      return null;
    }

    Future<bool> requiredOnServer() async =>
        ((await admin.get(_workflow)) as Json)['salesman_required'] == true;

    // -- Moving about --------------------------------------------------------
    /// Leave whatever is open, answering a form's discard question as well
    /// as the document editors'.
    Future<void> leave() async {
      for (int i = 0; i < 3; i++) {
        final Finder discard = find.text('Discard changes');
        if (discard.evaluate().isNotEmpty) {
          await tester.tap(discard.last);
          await pumpFor(tester, const Duration(milliseconds: 800));
        }
        await closeOpenEditor(tester);
        if (find.byType(Dialog).evaluate().isEmpty) return;
      }
    }

    /// The gear, Selling, its one card: the subject's tab strip.
    Future<void> openSelling() async {
      await leave();
      await tester.tap(find.byKey(const ValueKey<String>('menu-area-settings')));
      await pumpUntil(tester, find.byKey(const ValueKey<String>('setup-search')),
          waitingFor: 'the Settings page');
      await pumpFor(tester, const Duration(milliseconds: 500));
      final Finder tile =
          find.byKey(const ValueKey<String>('setup-section-Selling'));
      if (tile.evaluate().isEmpty) {
        throw StateError('no Selling section in Settings');
      }
      await tester.ensureVisible(tile);
      await tester.tap(tile);
      await pumpFor(tester, const Duration(milliseconds: 700));
      await tapKey(tester, 'setup-subject-selling');
      await pumpUntil(tester, find.byKey(const ValueKey<String>('subject-strip')),
          waitingFor: 'the Selling subject screen');
      await pumpFor(tester, const Duration(seconds: 1));
    }

    /// Selling > the tab for [path]; false when the tab is not offered.
    Future<bool> openTab(String path) async {
      await openSelling();
      final Finder tab = find.byKey(ValueKey<String>('subject-tab-$path'));
      if (tab.evaluate().isEmpty) return false;
      await tester.ensureVisible(tab);
      await tester.tap(tab);
      await pumpFor(tester, const Duration(seconds: 2));
      return true;
    }

    Future<bool> openSalesmen() async {
      if (!await openTab(_salesmenTab)) return false;
      await pumpUntil(
          tester, find.byKey(const ValueKey<String>('subject-body-$_salesmenTab')),
          waitingFor: 'the Salesmen list');
      await pumpFor(tester, const Duration(seconds: 1));
      return true;
    }

    /// Sales stages opens as a window from its tab.
    Future<bool> openStages() async {
      if (!await openTab(_stagesTab)) return false;
      await tapKey(tester, 'subject-window-$_stagesTab');
      await pumpUntil(tester,
          find.byKey(const ValueKey<String>('sales-settings-salesman-required')),
          waitingFor: 'the Sales stages window');
      await pumpFor(tester, const Duration(seconds: 1));
      return true;
    }

    SwitchListTile? requiredSwitch() {
      final Finder f = find.descendant(
          of: find.byKey(const ValueKey<String>('sales-settings-salesman-required')),
          matching: find.byType(SwitchListTile));
      return f.evaluate().isEmpty ? null : tester.widget<SwitchListTile>(f.first);
    }

    /// Open Sales stages, set the switch to [on], press Save. Returns what
    /// the screen said.
    Future<String> setRequired(bool on) async {
      if (!await openStages()) throw StateError('Sales stages not offered');
      String said = '';
      if (requiredSwitch()?.value != on) {
        final Finder sw =
            find.byKey(const ValueKey<String>('sales-settings-salesman-required'));
        await tester.ensureVisible(sw);
        await tester.tap(sw);
        await pumpFor(tester, const Duration(milliseconds: 500));
      }
      await tapDialogButton(tester, 'Save');
      said = await watch(tester, seconds: 4, confirm: false);
      await leave();
      return said;
    }

    /// Tap the grid row whose cell reads exactly [text].
    Future<void> pickRow(String text) async {
      final Finder row = find.byWidgetPredicate(
          (Widget w) => w is Text && (w.data ?? '').trim() == text);
      await pumpUntil(tester, row, waitingFor: 'a row showing $text');
      await tester.tap(row.last);
      await pumpFor(tester, const Duration(milliseconds: 700));
    }

    /// The texts level with the grid row whose cell reads [needle].
    List<String> gridRow(String needle) {
      final Finder anchor = find.text(needle);
      if (anchor.evaluate().isEmpty) return <String>[];
      final double y = tester.getCenter(anchor.last).dy;
      final List<MapEntry<double, String>> found = <MapEntry<double, String>>[];
      for (final Element e in find.byType(Text).evaluate()) {
        final String data = ((e.widget as Text).data ?? '').trim();
        if (data.isEmpty) continue;
        final RenderObject? box = e.renderObject;
        if (box is! RenderBox || !box.attached) continue;
        final Offset c = box.localToGlobal(box.size.center(Offset.zero));
        if ((c.dy - y).abs() < 6) found.add(MapEntry<double, String>(c.dx, data));
      }
      found.sort((MapEntry<double, String> a, MapEntry<double, String> b) =>
          a.key.compareTo(b.key));
      return <String>[for (final MapEntry<double, String> m in found) m.value];
    }

    /// Press [press] and gather every notice and new short text for a while.
    Future<String> pressAndRead(Future<void> Function() press,
        {int seconds = 5}) async {
      final Set<String> before = textOnScreen(tester).toSet();
      await press();
      final Set<String> seen = <String>{};
      final DateTime end = DateTime.now().add(Duration(seconds: seconds));
      while (DateTime.now().isBefore(end)) {
        await tester.pump(const Duration(milliseconds: 200));
        final String n = noticeText(tester);
        if (n.isNotEmpty) seen.add(n);
        for (final String t in textOnScreen(tester)) {
          if (t.length < 240 && t.length > 12 && !before.contains(t)) seen.add(t);
        }
      }
      return seen.join(' || ');
    }

    /// Flip the form's switch titled [label] to [on].
    Future<void> setSwitch(String label, bool on) async {
      final Finder tile = find.widgetWithText(SwitchListTile, label);
      await pumpUntil(tester, tile, waitingFor: 'switch "$label"');
      if (tester.widget<SwitchListTile>(tile.first).value == on) return;
      await tester.ensureVisible(tile.first);
      await tester.tap(tile.first);
      await pumpFor(tester, const Duration(milliseconds: 400));
    }

    /// A document's Salesman box: what it holds now (a name, or "Nobody")
    /// and the names it offers.
    ({String chosen, List<String> offered}) salesmanBox(
        String key, List<Json> all) {
      final Finder f = find.descendant(
          of: find.byKey(ValueKey<String>(key)),
          matching: find.byWidgetPredicate((Widget w) => w is DropdownButton));
      if (f.evaluate().isEmpty) {
        return (chosen: '(no box)', offered: const <String>[]);
      }
      final DropdownButton<dynamic> box =
          tester.widget<DropdownButton<dynamic>>(f.first);
      String label(dynamic id) {
        if (id == null) return 'Nobody';
        for (final Json row in all) {
          if ('${row['id']}' == '$id') return '${row['name']}';
        }
        return '$id';
      }

      return (
        chosen: label(box.value),
        offered: <String>[
          for (final DropdownMenuItem<dynamic> item in box.items ?? <DropdownMenuItem<dynamic>>[])
            if (item.child is Text) (item.child as Text).data ?? '',
        ],
      );
    }

    /// Open a Salesman box and choose [label] (or "Nobody").
    Future<void> chooseSalesman(String key, String label) async {
      await tapKey(tester, key);
      await pumpFor(tester, const Duration(milliseconds: 500));
      final Finder entry = find.text(label);
      await pumpUntil(tester, entry, waitingFor: 'Salesman entry "$label"');
      await tester.tap(entry.last);
      await pumpFor(tester, const Duration(milliseconds: 600));
    }

    /// Sell > Sales Orders > New, the fixture's customer, and (when
    /// [withLine]) one line of the run's product.
    Future<void> newOrder({bool withLine = true, num quantity = 2}) async {
      await leave();
      await openMenu(tester, 'sell', 'salesOrders');
      await tapNew(tester);
      await chooseIn(tester, 'sales-order-customer', customer);
      if (withLine) {
        await chooseIn(tester, 'sales-order-line-product-0', productName);
        await typeIn(tester, 'sales-order-line-0', 1, '$quantity');
      }
      // The starting choice is asked for once the customer is known.
      await pumpFor(tester, const Duration(seconds: 2));
    }

    /// Sell > Sales Invoices > New, the fixture's customer, and the note
    /// [noteId] ticked in the list of that customer's notes (it opens by
    /// itself when more than one is waiting).
    Future<void> newBill(String noteId) async {
      await leave();
      await openMenu(tester, 'sell', 'salesInvoices/sales-invoices');
      await tapNew(tester);
      await chooseIn(tester, 'sales-invoice-bill-customer', customer);
      await pumpFor(tester, const Duration(seconds: 1));
      const ValueKey<String> done = ValueKey<String>('sales-invoice-tick-done');
      if (find.byKey(done).evaluate().isEmpty) {
        await tapKey(tester, 'sales-invoice-choose-notes');
        await pumpFor(tester, const Duration(seconds: 1));
      }
      await tapKey(tester, 'sales-invoice-tick-$noteId');
      await tapKey(tester, 'sales-invoice-tick-done');
      await pumpFor(tester, const Duration(seconds: 3));
    }

    /// The order [orderId] approved, a note raised for all of it, approved
    /// and dispatched -- over HTTP, as the firm admin.
    Future<Json> dispatchOrder(String orderId) async {
      await apiAct(admin, 'sales-orders', orderId, 'approve');
      final Json order = await admin.one('sales-orders', orderId);
      final Json line = (order['lines'] as List<dynamic>).first as Json;
      final Json note = (await admin
          .write('POST', '/api/v1/delivery-notes', <String, dynamic>{
        'sales_order_id': order['id'],
        'delivery_date': _today(),
        'lines': <Json>[
          <String, dynamic>{
            'sales_order_line_id': line['id'],
            'line_number': 1,
            'current_delivery_quantity': line['quantity'],
          },
        ],
      })) as Json;
      await apiAct(admin, 'delivery-notes', '${note['id']}', 'approve');
      await apiAct(admin, 'delivery-notes', '${note['id']}', 'dispatch');
      return admin.one('delivery-notes', '${note['id']}');
    }

    /// The run's product with stock to dispatch; made the first time.
    Future<void> ensureProduct() async {
      final List<dynamic> found = (await admin.get(
              '/api/v1/products?search=${Uri.encodeQueryComponent(productName)}'))
          as List<dynamic>;
      if (found.isNotEmpty) return;
      final List<dynamic> brands =
          (await admin.get('/api/v1/products/brands')) as List<dynamic>;
      Json? brand;
      for (final dynamic b in brands) {
        if ((b as Json)['name'] == 'Fixture Brand') brand = b;
      }
      if (brand == null) {
        final Json company = (await admin.write('POST',
            '/api/v1/products/principals',
            <String, dynamic>{'code': 'FIXTURE', 'name': 'Fixture Company'})) as Json;
        brand = (await admin.write('POST', '/api/v1/products/brands',
            <String, dynamic>{
              'name': 'Fixture Brand',
              'principal_id': company['id'],
            })) as Json;
      }
      String piece = '';
      for (final dynamic u in (await admin
          .get('/api/v1/uom-framework/uoms?page_size=100')) as List<dynamic>) {
        if ((u as Json)['code'] == 'PIECE') piece = '${u['id']}';
      }
      final Json product = (await admin.write('POST', '/api/v1/products',
          <String, dynamic>{
            'code': '${itSuffix.toUpperCase()}-SM',
            'brand_id': brand['id'],
            'name': productName,
            'product_type': 'STOCK_ITEM',
            'tax_profile_group_code': 'GST_18_LOCAL',
            'selling_price': '100',
            'purchase_price': '60',
            'base_uom_id': piece,
            'inventory_uom_id': piece,
            'sales_uom_id': piece,
            'purchase_uom_id': piece,
          })) as Json;
      final Json warehouse =
          ((await admin.get('/api/v1/warehouses?page_size=5')) as List<dynamic>)
              .first as Json;
      final Json opening = (await admin.write('POST',
          '/api/v1/inventory/opening-stock', <String, dynamic>{
            'warehouse_id': warehouse['id'],
            'branch_id': warehouse['branch_id'],
            'reference_number': '${itSuffix.toUpperCase()}-SMOS',
            'posting_date': _today(),
            'lines': <Json>[
              <String, dynamic>{
                'product_id': product['id'],
                'quantity': '50',
                'unit_cost': '60',
              },
            ],
          })) as Json;
      await admin.write('POST',
          '/api/v1/inventory/opening-stock/${opening['id']}/post',
          <String, dynamic>{});
    }

    // =======================================================================
    // Firm admin
    // =======================================================================
    if (isAdmin) {
      await ensureProduct();

      if (_runs('list')) {
        await log.step('SM-001 Salesmen opens from Settings > Selling', () async {
          final int errs = appErrors.length;
          if (!await openSalesmen()) throw StateError('no Salesmen tab');
          final List<String> missing = <String>[
            for (final String h in const <String>[
              'Code', 'Name', 'User account', 'Phone', 'Commission', 'Status',
            ])
              if (!screenHas(tester, h)) h,
          ];
          log.saw = 'columns missing $missing; New ${buttonState(tester, 'New')}'
              '/${buttonState(tester, '+ New')}';
          if (missing.isNotEmpty) {
            throw StateError('not on screen: $missing; on screen: '
                '${textOnScreen(tester).take(60).join(' | ')}');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });

        await log.step('TC-SELL-114 a salesman with no sign-in is added',
            () async {
          final int errs = appErrors.length;
          if (!await openSalesmen()) throw StateError('no Salesmen tab');
          await tapNew(tester);
          await pumpUntil(tester, find.byKey(const ValueKey<String>(_dialog)),
              waitingFor: 'the New salesman form');
          await typeLabelled(tester, 'Name', phone);
          await setSwitch('Earns commission', false);
          final String said =
              await pressAndRead(() => tapButton(tester, 'Save & Close'));
          final Json? row = await salesmanNamed(phone);
          final bool closed =
              find.byKey(const ValueKey<String>(_dialog)).evaluate().isEmpty;
          await searchList(tester, phone);
          final List<String> line = gridRow(phone);
          log.saw = 'said "$said"; form closed=$closed; server '
              '${row == null ? 'has none' : 'user_id=${row['user_id']}, earns=${row['earns_commission']}, active=${row['is_active']}'}'
              '; row $line';
          if (row == null) throw StateError('not saved');
          if (row['user_id'] != null) throw StateError('tied to a user');
          if (row['earns_commission'] != false) {
            throw StateError('Earns commission off was not saved');
          }
          if (!line.contains('Not tied to a user')) {
            throw StateError('the row does not say "Not tied to a user"');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await leave();

        await log.step('TC-SELL-118 New with the same name in other case is '
            'refused', () async {
          final int errs = appErrors.length;
          if (!await openSalesmen()) throw StateError('no Salesmen tab');
          await tapNew(tester);
          await typeLabelled(tester, 'Name', phone.toLowerCase());
          log.saw = await expectRefusal(tester, admin,
              collection: 'salesmen',
              openKey: _dialog,
              typed: phone.toLowerCase(),
              press: () => tapButton(tester, 'Save & Close'));
          final bool words = screenHas(tester, 'already on the list') ||
              noticeText(tester).contains('already on the list');
          log.saw = '${log.saw}; says "already on the list"=$words';
          if (!words) throw StateError('refused, but not saying why');
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await leave();

        await log.step('TC-SELL-118 a second name saves; editing it to the '
            'first in capitals is refused', () async {
          final int errs = appErrors.length;
          if (!await openSalesmen()) throw StateError('no Salesmen tab');
          await tapNew(tester);
          await typeLabelled(tester, 'Name', second);
          final String said =
              await pressAndRead(() => tapButton(tester, 'Save & Close'));
          final Json? row = await salesmanNamed(second);
          if (row == null) throw StateError('"$second" not saved [$said]');
          await leave();
          if (!await openSalesmen()) throw StateError('no Salesmen tab');
          await searchList(tester, second);
          await pickRow(second);
          await tapButton(tester, 'Edit');
          await pumpFor(tester, const Duration(seconds: 1));
          await typeLabelled(tester, 'Name', phone.toUpperCase());
          final String refused = await expectRefusal(tester, admin,
              collection: 'salesmen',
              openKey: _dialog,
              typed: phone.toUpperCase(),
              press: () => tapButton(tester, 'Save & Close'));
          final Json? after = await salesmanNamed(second);
          final String shown = noticeText(tester) + textOnScreen(tester).join(' | ');
          final bool clash = shown.contains('already on the list');
          final bool stale = shown.contains('Somebody else saved');
          log.saw = 'second saved ("$said"); edit: $refused; says "already on '
              'the list"=$clash, "Somebody else saved"=$stale; server name '
              'still "${after?['name']}"';
          if (after == null) throw StateError('the edit renamed it');
          if (stale || !clash) {
            throw StateError('the edit was refused as a save by somebody else, '
                'not as a name already on the list');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await leave();

        await log.step('SM-002 Edit: a phone is added and kept', () async {
          final int errs = appErrors.length;
          if (!await openSalesmen()) throw StateError('no Salesmen tab');
          await searchList(tester, second);
          await pickRow(second);
          await tapButton(tester, 'Edit');
          await pumpFor(tester, const Duration(seconds: 1));
          await typeLabelled(tester, 'Phone', '9800012345');
          final String said =
              await pressAndRead(() => tapButton(tester, 'Save & Close'));
          final Json? row = await salesmanNamed(second);
          await searchList(tester, second);
          log.saw = 'said "$said"; server phone=${row?['phone']}, '
              'earns=${row?['earns_commission']}; row ${gridRow(second)}';
          if (row?['phone'] != '9800012345') throw StateError('phone not saved');
          if (row?['earns_commission'] != true) {
            throw StateError('the edit changed Earns commission');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await leave();

        await log.step('TC-SELL-115 an entry tied to the signed-in user',
            () async {
          final int errs = appErrors.length;
          // A run before this one tied an entry to the same user; a user is
          // tied to one entry at most, so that tie is undone first.
          for (final Json row in await salesmen()) {
            if (row['user_id'] != null) {
              await admin.write('PUT', '/api/v1/salesmen/${row['id']}',
                  <String, dynamic>{'user_id': null});
            }
          }
          if (!await openSalesmen()) throw StateError('no Salesmen tab');
          await tapNew(tester);
          await typeLabelled(tester, 'Name', asha);
          final Finder userBox = find.descendant(
              of: find.byKey(const ValueKey<String>(_dialog)),
              matching: find.text('Not tied to a user'));
          await pumpUntil(tester, userBox, waitingFor: 'the User account box');
          await tester.tap(userBox.last);
          await pumpFor(tester, const Duration(milliseconds: 700));
          final Finder mine = find.textContaining('Ready Firm Admin');
          await pumpUntil(tester, mine, waitingFor: 'Ready Firm Admin offered');
          await tester.tap(mine.last);
          await pumpFor(tester, const Duration(milliseconds: 600));
          final String said =
              await pressAndRead(() => tapButton(tester, 'Save & Close'));
          final Json? row = await salesmanNamed(asha);
          log.saw = 'said "$said"; server user_id=${row?['user_id']}';
          if (row == null || row['user_id'] == null) {
            throw StateError('not saved tied to a user');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await leave();
      }

      if (_runs('chain')) {
        await log.step('TC-SELL-115 signed in as the tied user, a new order '
            'starts on that entry', () async {
          final int errs = appErrors.length;
          await newOrder(withLine: false);
          final List<Json> all = await salesmen();
          final ({String chosen, List<String> offered}) box =
              salesmanBox('sales-order-salesman', all);
          log.saw = 'starts on ${box.chosen}; offers ${box.offered}';
          await leave();
          if (box.chosen != asha) {
            throw StateError('started on ${box.chosen}, not $asha');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });

        await log.step('SM-003 the tied entry is made inactive', () async {
          final int errs = appErrors.length;
          if (!await openSalesmen()) throw StateError('no Salesmen tab');
          await searchList(tester, asha);
          await pickRow(asha);
          await tapButton(tester, 'Edit');
          await pumpFor(tester, const Duration(seconds: 1));
          await setSwitch('Active', false);
          final String said =
              await pressAndRead(() => tapButton(tester, 'Save & Close'));
          final Json? row = await salesmanNamed(asha);
          await searchList(tester, asha);
          log.saw = 'said "$said"; server active=${row?['is_active']}; row '
              '${gridRow(asha)}';
          if (row?['is_active'] != false) throw StateError('still active');
          if (!gridRow(asha).contains('Inactive')) {
            throw StateError('the row does not read Inactive');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await leave();

        String orderId = '';
        await log.step('TC-SELL-114/115 a new order: the inactive entry is '
            'neither offered nor chosen; Phone order is picked and saved',
            () async {
          final int errs = appErrors.length;
          await newOrder();
          final List<Json> all = await salesmen();
          final ({String chosen, List<String> offered}) box =
              salesmanBox('sales-order-salesman', all);
          final List<String> problems = <String>[
            if (box.chosen != 'Nobody') 'starts on ${box.chosen}, not blank',
            if (!box.offered.contains(phone)) '$phone not offered',
            if (!box.offered.contains(second)) '$second not offered',
            if (box.offered.any((String o) => o.startsWith(asha)))
              'inactive $asha offered',
          ];
          await chooseSalesman('sales-order-salesman', phone);
          final Json? before = await admin.newest('sales-orders');
          await saveEditor(tester, 'sales-order-save');
          final Json? made = await admin.newest('sales-orders');
          if (made == null || made['id'] == before?['id']) {
            throw StateError('no order saved');
          }
          orderId = '${made['id']}';
          final Json whole = await admin.one('sales-orders', orderId);
          final Json? ph = await salesmanNamed(phone);
          log.saw = 'starts on ${box.chosen}; offers ${box.offered}; saved '
              '${docNumber(whole)} with salesman_id '
              '${whole['salesman_id'] == ph?['id'] ? phone : whole['salesman_id']}';
          if (whole['salesman_id'] != ph?['id']) {
            problems.add('the order did not keep $phone');
          }
          if (problems.isNotEmpty) throw StateError(problems.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await leave();

        await log.step('TC-SELL-114/115 the bill off that order\'s note takes '
            'Phone order and saves it', () async {
          final int errs = appErrors.length;
          if (orderId.isEmpty) throw StateError('no order from the last step');
          final Json note = await dispatchOrder(orderId);
          final Json? ph = await salesmanNamed(phone);
          await newBill('${note['id']}');
          final ({String chosen, List<String> offered}) box =
              salesmanBox('sales-invoice-salesman', await salesmen());
          final Json? before = await admin.newest('sales-invoices');
          await saveEditor(tester, 'sales-invoice-save');
          final Json? made = await admin.newest('sales-invoices');
          if (made == null || made['id'] == before?['id']) {
            throw StateError('no bill saved (box showed ${box.chosen})');
          }
          final Json bill = await admin.one('sales-invoices', '${made['id']}');
          log.saw = 'note ${docNumber(note)} salesman '
              '${note['salesman_id'] == ph?['id'] ? phone : note['salesman_id']}; '
              'bill box shows ${box.chosen}; saved ${docNumber(bill)} with '
              '${bill['salesman_id'] == ph?['id'] ? phone : bill['salesman_id']}';
          if (box.chosen != phone) {
            throw StateError('the bill box showed ${box.chosen}, not $phone');
          }
          if (bill['salesman_id'] != ph?['id']) {
            throw StateError('the bill did not keep $phone');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await leave();
      }

      if (_runs('required')) {
        // A note with no salesman, raised before the switch goes on.
        Json? blankNote;
        try {
          blankNote = await apiDispatchedNote(admin, quantity: 1);
        } catch (error) {
          log.info('TC-SELL-116', 'could not raise a note with no salesman: '
              '$error');
        }
        final bool wasOn = await requiredOnServer();
        try {
          await log.step('TC-SELL-116 Salesman required is switched on',
              () async {
            final int errs = appErrors.length;
            final String said = await setRequired(true);
            final bool on = await requiredOnServer();
            log.saw = 'server $wasOn -> $on; said "$said"';
            if (!on) throw StateError('the switch did not reach the server');
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });

          await log.step('TC-SELL-116 an order with no salesman is refused',
              () async {
            final int errs = appErrors.length;
            await newOrder(quantity: 1);
            final ({String chosen, List<String> offered}) box =
                salesmanBox('sales-order-salesman', await salesmen());
            if (box.chosen != 'Nobody') {
              await chooseSalesman('sales-order-salesman', 'Nobody');
            }
            final String saw = await expectRefusal(tester, admin,
                collection: 'sales-orders',
                openKey: 'sales-order-save',
                press: () => tapKey(tester, 'sales-order-save'));
            final bool words = screenHas(tester, _requiredWords) ||
                noticeText(tester).contains(_requiredWords);
            log.saw = '$saw; the case\'s words on screen=$words';
            if (!words) throw StateError('refused, but not in the case\'s words');
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
          await leave();

          if (blankNote == null) {
            log.skip('TC-SELL-116 bill', 'no note with no salesman to bill');
          } else {
            await log.step('TC-SELL-116 a bill with no salesman is refused',
                () async {
              final int errs = appErrors.length;
              await newBill('${blankNote!['id']}');
              final ({String chosen, List<String> offered}) box =
                  salesmanBox('sales-invoice-salesman', await salesmen());
              if (box.chosen != 'Nobody') {
                await chooseSalesman('sales-invoice-salesman', 'Nobody');
              }
              final String saw = await expectRefusal(tester, admin,
                  collection: 'sales-invoices',
                  openKey: 'sales-invoice-save',
                  press: () => tapKey(tester, 'sales-invoice-save'));
              final bool words = screenHas(tester, _requiredWords) ||
                  noticeText(tester).contains(_requiredWords);
              log.saw = 'box started on ${box.chosen}; $saw; the case\'s '
                  'words on screen=$words';
              if (!words) {
                throw StateError('refused, but not in the case\'s words');
              }
              if (appErrors.length > errs) throw StateError(errorsSince(errs));
            });
            await leave();
          }

          await log.step('TC-SELL-116 the switch goes back off', () async {
            final int errs = appErrors.length;
            final String said = await setRequired(false);
            final bool on = await requiredOnServer();
            log.saw = 'server now $on; said "$said"';
            if (on) throw StateError('still on');
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });

          await log.step('TC-SELL-116 with it off, an order with no salesman '
              'saves', () async {
            final int errs = appErrors.length;
            await newOrder(quantity: 1);
            final ({String chosen, List<String> offered}) box =
                salesmanBox('sales-order-salesman', await salesmen());
            if (box.chosen != 'Nobody') {
              await chooseSalesman('sales-order-salesman', 'Nobody');
            }
            final Json? before = await admin.newest('sales-orders');
            await saveEditor(tester, 'sales-order-save');
            final Json? made = await admin.newest('sales-orders');
            log.saw = 'saved ${made == null ? 'nothing' : docNumber(made)}, '
                'salesman ${made?['salesman_id']}';
            if (made == null || made['id'] == before?['id']) {
              throw StateError('not saved');
            }
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
          await leave();

          if (blankNote != null) {
            await log.step('TC-SELL-116 with it off, the bill with no '
                'salesman saves', () async {
              final int errs = appErrors.length;
              await newBill('${blankNote!['id']}');
              final Json? before = await admin.newest('sales-invoices');
              await saveEditor(tester, 'sales-invoice-save');
              final Json? made = await admin.newest('sales-invoices');
              log.saw = 'saved ${made == null ? 'nothing' : docNumber(made)}, '
                  'salesman ${made?['salesman_id']}';
              if (made == null || made['id'] == before?['id']) {
                throw StateError('not saved');
              }
              if (appErrors.length > errs) throw StateError(errorsSince(errs));
            });
            await leave();
          }
        } finally {
          // Leave the fixture as found, whatever the screen did.
          if (await requiredOnServer() != wasOn) {
            await admin.write('PUT', _workflow,
                <String, dynamic>{'salesman_required': wasOn});
            log.info('TC-SELL-116', 'switch put back over HTTP');
          }
        }
      }

      log.skip('TC-SELL-115 account manager / round starting choices',
          'the ready fixture has no round and the case\'s customers; '
          'only the tied-user, inactive and from-the-order choices are driven');
      log.skip('TC-SELL-116 delivery note and quotation',
          'only the order and the bill were driven');
      log.skip('TC-SELL-117', 'the printed bill is a PDF preview; its text '
          'is not reachable from a click flow');
      log.skip('TC-TERR-007', 'the ready fixture has no territory, route or '
          'round to assign a salesman to');
    }

    // =======================================================================
    // Viewer (or anybody else)
    // =======================================================================
    if (!isAdmin) {
      await log.step('SM-V01 the Salesmen list: not changeable', () async {
        final int errs = appErrors.length;
        final int before = await me.total('/api/v1/salesmen');
        final bool offered = await openSalesmen();
        String screen = 'tab not offered';
        String said = '';
        if (offered) {
          final String newState = buttonState(tester, 'New') == 'absent'
              ? buttonState(tester, '+ New')
              : buttonState(tester, 'New');
          final String edit = buttonState(tester, 'Edit');
          screen = 'list open, New $newState, Edit $edit';
          if (newState == 'enabled') {
            await tapNew(tester);
            await typeLabelled(tester, 'Name', 'Viewer try $stamp');
            said = await pressAndRead(() => tapButton(tester, 'Save & Close'));
          }
        }
        final ({int status, String text}) post = await me.attempt('POST',
            '/api/v1/salesmen', <String, dynamic>{'name': 'Viewer HTTP $stamp'});
        final int after = await me.total('/api/v1/salesmen');
        log.saw = '$screen; said "$said"; HTTP POST ${post.status}; server '
            'count $before -> $after';
        if (after != before) throw StateError('the viewer added a salesman');
        if (post.status < 400) throw StateError('HTTP POST was accepted');
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      await leave();

      await log.step('SM-V02 Sales stages: Salesman required not changeable',
          () async {
        final int errs = appErrors.length;
        final bool before = await requiredOnServer();
        if (!await openStages()) {
          log.saw = 'Sales stages not offered; server $before';
          return;
        }
        final SwitchListTile? sw = requiredSwitch();
        final bool enabled = sw?.onChanged != null;
        final String save = buttonState(tester, 'Save');
        await leave();
        final bool after = await requiredOnServer();
        log.saw = 'switch value=${sw?.value}, enabled=$enabled; Save $save; '
            'server $before -> $after';
        if (enabled || save == 'enabled') {
          throw StateError('the viewer is offered the change');
        }
        if (after != before) throw StateError('the setting moved');
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      await leave();

      await log.step('SM-V03 Sales orders: no New for the viewer', () async {
        final int errs = appErrors.length;
        await leave();
        await openMenu(tester, 'sell', 'salesOrders');
        final String newState = buttonState(tester, 'New Order') == 'absent'
            ? buttonState(tester, 'New')
            : buttonState(tester, 'New Order');
        log.saw = 'New $newState';
        if (newState == 'enabled') throw StateError('New offered to a viewer');
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
    }

    log.info('errors', 'app errors and overflows this run: ${appErrors.length}');
    log.finish();
  });
}
