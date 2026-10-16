import 'package:agency_desktop/ui/workspace/box_piece_cells.dart'
    show boxesAndPieces, stockInBoxes;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';
import 'sc_gt_test.dart' show leave, openArea, pickRow, pressAndRead;

/// Boxes and pieces on the screens (build row L5, steps 9 to 11). Run on the
/// `lot-firm` fixture (TEST03, both box switches on) as lotadmin, then as
/// lotviewer.
///
/// Every run makes its own masters over HTTP before the app starts (so the
/// screens read them at sign-in), named with the minute and the user
/// (`1432A`): an item `0B<tag>-P` kept in pieces and sold and bought in BOX
/// (1 BOX = 12 PIECE), an item `0B<tag>-N` in pieces only, a customer who
/// bills in boxes and pieces and one who does not, a supplier who buys in
/// them; 89 pieces received; an order of 41 dispatched and billed in draft
/// with a draft return of 5; a second order of 41 with a draft note; a draft
/// purchase order of 41, an approved one of 41 with a draft receipt, and a
/// draft supplier's bill and a draft purchase return off the first receipt.
///
/// As the admin: the two settings rows; the customer and supplier tick and
/// the list filter; a sales order, a quotation and a counter bill typed as
/// 2 boxes + 17 pieces (evened out to 3 + 5, side panel, Pieces only and
/// back, saved: the server's 41 and 12); the continuing figures of the seven
/// other editors; *Show boxes* on the stock list. As the viewer: what is
/// shown and what is refused. Every value on screen is set beside what the
/// server returned; app errors and overflows are counted.

/// IT_PART=settings (or parties, order, quote, counter, continue, stock)
/// runs that part.
const String _part = String.fromEnvironment('IT_PART');
bool _runs(String part) => _part.isEmpty || _part.split(',').contains(part);

const String _salesSettings = '/api/v1/sales-orders/workflow-settings';
const String _buySettings = '/api/v1/purchases/workflow-settings';

String _today() => DateTime.now().toIso8601String().substring(0, 10);

double _n(dynamic v) => double.tryParse('${v ?? ''}'.replaceAll(',', '')) ?? 0;

bool _same(double? a, double b) => a != null && (a - b).abs() < 0.005;

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('BP: boxes and pieces ($itHandle)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final bool isAdmin = itHandle == 'lotadmin';
    final Server admin = await Server.connectAs(
        '$itSuffix.lotadmin@fixtures.local', fixturePassword);
    final Server me = await Server.connect();
    final FlowLog log = FlowLog('bp-$itHandle');

    final DateTime now = DateTime.now();
    final String stamp = '${now.hour.toString().padLeft(2, '0')}'
        '${now.minute.toString().padLeft(2, '0')}';
    final String tag = '$stamp${isAdmin ? 'A' : 'V'}';

    Future<List<Json>> list(String path) async => <Json>[
          for (final dynamic row in (await admin.get(path)) as List<dynamic>)
            row as Json,
        ];

    // -- Masters, made over HTTP before the app starts -----------------------
    late Json branch, warehouse, vendor, boxCustomer, plainCustomer;
    late Json productP, productN;
    late String piece, box;
    Json? orderA, noteA, billA, returnA, orderB;
    Json? po1, gr1, po2, gr2, po3, pbill;
    final String nameP = 'BP box $tag';
    final String nameN = 'BP loose $tag';
    final String nameC = 'BP boxed cust $tag';
    final String nameC2 = 'BP plain cust $tag';
    final String nameV = 'BP supplier $tag';

    Future<String> brandId() async {
      for (final Json b in await list('/api/v1/products/brands')) {
        if (b['name'] == 'Check Brand' || b['name'] == 'Fixture Brand') {
          return '${b['id']}';
        }
      }
      final Json company = (await admin.write('POST',
          '/api/v1/products/principals',
          <String, dynamic>{'code': 'FIXTURE', 'name': 'Fixture Company'})) as Json;
      final Json brand = (await admin.write('POST', '/api/v1/products/brands',
          <String, dynamic>{
            'name': 'Fixture Brand',
            'principal_id': company['id'],
          })) as Json;
      return '${brand['id']}';
    }

    Json line0(Json? doc) =>
        ((doc?['lines'] as List<dynamic>?) ?? <dynamic>[]).isEmpty
            ? <String, dynamic>{}
            : (doc!['lines'] as List<dynamic>).first as Json;

    Future<Json> approvedPo(String qty, {bool approve = true}) async {
      final Json po = (await admin.write('POST', '/api/v1/purchases',
          <String, dynamic>{
            'vendor_id': vendor['id'],
            'branch_id': branch['id'],
            'warehouse_id': warehouse['id'],
            'purchase_date': _today(),
            'box_and_piece_entry': true,
            'lines': <Json>[
              <String, dynamic>{
                'product_id': productP['id'],
                'ordered_quantity': qty,
                'unit_price': '5',
                'purchase_uom_id': piece,
                'inventory_uom_id': piece,
                'pack_size': '12',
              },
            ],
          })) as Json;
      if (approve) {
        await apiAct(admin, 'purchases', '${po['id']}', 'submit');
        await apiAct(admin, 'purchases', '${po['id']}', 'approve');
      }
      return admin.one('purchases', '${po['id']}');
    }

    Future<Json> receipt(Json po, String qty, {bool complete = true}) async {
      final Json gr = (await admin.write('POST', '/api/v1/goods-receipts',
          <String, dynamic>{
            'purchase_order_id': po['id'],
            'receipt_date': _today(),
            'lines': <Json>[
              <String, dynamic>{
                'purchase_order_line_id': line0(po)['id'],
                'line_number': 1,
                'current_receipt_quantity': qty,
                'unit_price': '5',
                'warehouse_id': warehouse['id'],
              },
            ],
          })) as Json;
      if (complete) {
        await apiAct(admin, 'goods-receipts', '${gr['id']}', 'complete');
      }
      return admin.one('goods-receipts', '${gr['id']}');
    }

    Future<Json> approvedOrder(String qty) async {
      final Json so = (await admin.write('POST', '/api/v1/sales-orders',
          <String, dynamic>{
            'customer_id': boxCustomer['id'],
            'branch_id': branch['id'],
            'warehouse_id': warehouse['id'],
            'order_date': _today(),
            'box_and_piece_entry': true,
            'lines': <Json>[
              <String, dynamic>{
                'line_number': 1,
                'product_id': productP['id'],
                'quantity': qty,
                'unit_price': '10',
                'pack_size': '12',
              },
            ],
          })) as Json;
      await apiAct(admin, 'sales-orders', '${so['id']}', 'approve');
      return admin.one('sales-orders', '${so['id']}');
    }

    Future<Json> note(Json so, String qty) async {
      final Json dn = (await admin.write('POST', '/api/v1/delivery-notes',
          <String, dynamic>{
            'sales_order_id': so['id'],
            'delivery_date': _today(),
            'lines': <Json>[
              <String, dynamic>{
                'sales_order_line_id': line0(so)['id'],
                'line_number': 1,
                'current_delivery_quantity': qty,
              },
            ],
          })) as Json;
      return admin.one('delivery-notes', '${dn['id']}');
    }

    final bool ready = await log.step('BP-PREP masters over HTTP', () async {
      for (final Json b in await list('/api/v1/branches?page_size=100')) {
        if (b['code'] == 'HO') branch = b;
      }
      for (final Json w in await list('/api/v1/warehouses?page_size=100')) {
        if (w['code'] == 'MAIN') warehouse = w;
      }
      for (final Json u in await list('/api/v1/uom-framework/uoms?page_size=200')) {
        if (u['code'] == 'PIECE') piece = '${u['id']}';
        if (u['code'] == 'BOX') box = '${u['id']}';
      }
      final Json sales = (await admin.get(_salesSettings)) as Json;
      final Json buying = (await admin.get(_buySettings)) as Json;
      if (sales['box_and_piece_entry'] != true ||
          buying['box_and_piece_entry'] != true) {
        throw StateError('PRECONDITION the TEST03 switches are not both on: '
            'sales ${sales['box_and_piece_entry']}, buying '
            '${buying['box_and_piece_entry']}');
      }
      final String brand = await brandId();
      Json product(String code, String name, bool boxed) => <String, dynamic>{
            'code': code,
            'brand_id': brand,
            'name': name,
            'product_type': 'STOCK_ITEM',
            'tax_profile_group_code': 'GST_18_LOCAL',
            'selling_price': '10',
            'purchase_price': '5',
            'base_uom_id': piece,
            'inventory_uom_id': piece,
            'sales_uom_id': boxed ? box : piece,
            'purchase_uom_id': boxed ? box : piece,
          };
      productP = (await admin.write('POST', '/api/v1/products',
          product('0B$tag-P', nameP, true))) as Json;
      await admin.write('POST', '/api/v1/uom-framework/conversion-rules',
          <String, dynamic>{
            'product_id': productP['id'],
            'from_uom_id': box,
            'to_uom_id': piece,
            'conversion_factor': '12',
            'effective_from': '2026-04-01',
          });
      productN = (await admin.write('POST', '/api/v1/products',
          product('0B$tag-N', nameN, false))) as Json;
      boxCustomer = (await admin.write('POST', '/api/v1/customers',
          <String, dynamic>{
            'code': 'BC$tag',
            'name': nameC,
            'customer_type': 'BUSINESS',
            'currency_code': 'INR',
            'box_and_piece_entry': true,
          })) as Json;
      plainCustomer = (await admin.write('POST', '/api/v1/customers',
          <String, dynamic>{
            'code': 'BD$tag',
            'name': nameC2,
            'customer_type': 'BUSINESS',
            'currency_code': 'INR',
          })) as Json;
      vendor = (await admin.write('POST', '/api/v1/vendors', <String, dynamic>{
        'code': 'BV$tag',
        'name': nameV,
        'box_and_piece_entry': true,
      })) as Json;
      po1 = await approvedPo('89');
      gr1 = await receipt(po1!, '89');
      log.saw = 'products ${productP['code']} (BOX of 12), ${productN['code']}; '
          'customers $nameC (boxes ${boxCustomer['box_and_piece_entry']}), '
          '$nameC2 (${plainCustomer['box_and_piece_entry']}); supplier $nameV '
          '(${vendor['box_and_piece_entry']}); PO ${docNumber(po1!)} line pack '
          '${line0(po1)['pack_size']}; receipt ${docNumber(gr1!)} '
          '${gr1!['status']} line pack ${line0(gr1)['pack_size']}';
    });

    if (ready && _runs('continue')) {
      await log.step('BP-PREP documents to continue, over HTTP', () async {
        final List<String> made = <String>[];
        Future<void> attempt(String what, Future<void> Function() body) async {
          try {
            await body();
            made.add(what);
          } catch (error) {
            made.add('$what FAILED ($error)');
          }
        }

        await attempt('order A, note A dispatched, draft bill, draft return',
            () async {
          orderA = await approvedOrder('41');
          noteA = await note(orderA!, '41');
          await apiAct(admin, 'delivery-notes', '${noteA!['id']}', 'approve');
          await apiAct(admin, 'delivery-notes', '${noteA!['id']}', 'dispatch');
          noteA = await admin.one('delivery-notes', '${noteA!['id']}');
          final Json bill = (await admin.write('POST', '/api/v1/sales-invoices',
              <String, dynamic>{
                'customer_id': boxCustomer['id'],
                'branch_id': branch['id'],
                'invoice_date': _today(),
                'source_documents': <Json>[
                  <String, dynamic>{
                    'source_document_type': 'DELIVERY_NOTE',
                    'source_document_id': noteA!['id'],
                  },
                ],
                'lines': <Json>[
                  <String, dynamic>{
                    'source_document_type': 'DELIVERY_NOTE',
                    'source_document_id': noteA!['id'],
                    'source_document_line_id': line0(noteA)['id'],
                    'line_number': 1,
                    'current_invoice_quantity': '41',
                  },
                ],
              })) as Json;
          billA = await admin.one('sales-invoices', '${bill['id']}');
          final Json ret = (await admin.write('POST', '/api/v1/sales-returns',
              <String, dynamic>{
                'customer_id': boxCustomer['id'],
                'branch_id': branch['id'],
                'warehouse_id': warehouse['id'],
                'return_date': _today(),
                'source_documents': <Json>[
                  <String, dynamic>{
                    'source_document_type': 'DELIVERY_NOTE',
                    'source_document_id': noteA!['id'],
                  },
                ],
                'lines': <Json>[
                  <String, dynamic>{
                    'source_document_type': 'DELIVERY_NOTE',
                    'source_document_id': noteA!['id'],
                    'source_document_line_id': line0(noteA)['id'],
                    'line_number': 1,
                    'current_return_quantity': '5',
                  },
                ],
              })) as Json;
          returnA = await admin.one('sales-returns', '${ret['id']}');
        });
        await attempt('order B, approved, nothing delivered', () async {
          orderB = await approvedOrder('41');
        });
        await attempt('draft PO of 41', () async {
          po3 = await approvedPo('41', approve: false);
        });
        await attempt('approved PO of 41 with a draft receipt', () async {
          po2 = await approvedPo('41');
          gr2 = await receipt(po2!, '41', complete: false);
        });
        await attempt('draft supplier bill off receipt 1', () async {
          final Json b = (await admin.write('POST', '/api/v1/purchase-invoices',
              <String, dynamic>{
                'vendor_id': vendor['id'],
                'branch_id': branch['id'],
                'invoice_date': _today(),
                'supplier_invoice_number': 'SB$tag',
                'supplier_invoice_date': _today(),
                'source_documents': <Json>[
                  <String, dynamic>{
                    'source_document_type': 'GOODS_RECEIPT',
                    'source_document_id': gr1!['id'],
                  },
                ],
                'lines': <Json>[
                  <String, dynamic>{
                    'source_document_type': 'GOODS_RECEIPT',
                    'source_document_id': gr1!['id'],
                    'source_document_line_id': line0(gr1)['id'],
                    'line_number': 1,
                    'current_invoice_quantity': '89',
                  },
                ],
              })) as Json;
          pbill = await admin.one('purchase-invoices', '${b['id']}');
        });
        log.saw = made.join('; ');
        if (made.any((String m) => m.contains('FAILED'))) {
          throw StateError(log.saw!);
        }
      });
    }

    await startAndSignIn(tester);
    collectAppErrors();
    final void Function(FlutterErrorDetails)? collect = FlutterError.onError;
    FlutterError.onError = (FlutterErrorDetails details) {
      collect?.call(details);
      final String all = details.toString();
      if (all.contains('overflowed')) {
        final String where = all
            .split('\n')
            .where((String l) =>
                l.contains('.dart:') ||
                l.contains('constraints') ||
                l.contains('size:'))
            .take(6)
            .join(' | ');
        // ignore: avoid_print
        print('FLOW: INFO [bp-$itHandle] overflow at :: $where');
      }
    };
    if (!ready) {
      log.finish();
      return;
    }

    String errorsSince(int from) => appErrors.skip(from).take(3).join(' || ');
    Future<void> away() => leave(tester);

    List<String> keysStarting(String prefix) => <String>{
          for (final Element e in find.byWidgetPredicate((Widget w) {
            final Key? k = w.key;
            return k is ValueKey<String> && k.value.startsWith(prefix);
          }).evaluate())
            (e.widget.key! as ValueKey<String>).value,
        }.toList();

    List<String> textsUnder(String key) {
      final Finder f = find.byKey(ValueKey<String>(key));
      if (f.evaluate().isEmpty) return <String>[];
      return <String>[
        for (final Text t in tester.widgetList<Text>(
            find.descendant(of: f.first, matching: find.byType(Text))))
          if ((t.data ?? '').trim().isNotEmpty) t.data!.trim(),
        if (tester.widget(f.first) is Text)
          (tester.widget(f.first) as Text).data ?? '',
      ];
    }

    /// The text in the cell keyed exactly [key], or '(absent)'.
    String cell(String key) {
      final Finder f = find.byKey(ValueKey<String>(key));
      if (f.evaluate().isEmpty) return '(absent)';
      final Finder inner =
          find.descendant(of: f.first, matching: find.byType(EditableText));
      if (inner.evaluate().isEmpty) return '(no box)';
      return tester.widget<EditableText>(inner.first).controller.text;
    }

    Future<void> typeKeyed(String key, String text) async {
      final Finder box = find.byKey(ValueKey<String>(key));
      await pumpUntil(tester, box, waitingFor: 'box $key');
      await tester.ensureVisible(box.first);
      final Finder inner =
          find.descendant(of: box.first, matching: find.byType(EditableText));
      final Finder target = inner.evaluate().isEmpty ? box.first : inner.first;
      await tester.enterText(target, text);
      await pumpFor(tester, const Duration(milliseconds: 400));
    }

    Future<void> tapCell(String key) async {
      final Finder box = find.byKey(ValueKey<String>(key));
      await pumpUntil(tester, box, waitingFor: 'cell $key');
      await tester.ensureVisible(box.first);
      await tester.tap(box.first, warnIfMissed: false);
      await pumpFor(tester, const Duration(milliseconds: 600));
    }

    Future<String> openFromList(String number) async {
      await refreshList(tester);
      await searchList(tester, number);
      await pickRow(tester, number);
      for (final String b in const <String>['Edit', 'Open', 'View']) {
        if (buttonState(tester, b) == 'enabled') {
          await tapButton(tester, b);
          await pumpFor(tester, const Duration(seconds: 3));
          return b;
        }
      }
      throw StateError('no Edit, Open or View for $number');
    }

    /// Open a screen from the menu; a view still closing can swallow the
    /// first tap, so leave and try once more.
    Future<void> goTo(String area, String path) async {
      try {
        await openArea(tester, area, path);
      } on TestFailure {
        await tester.sendKeyEvent(LogicalKeyboardKey.escape);
        await away();
        await pumpFor(tester, const Duration(seconds: 1));
        await openArea(tester, area, path);
      }
    }

    /// Texts on screen that read as boxes ("3 x 12 + 5").
    List<String> boxTexts() => <String>{
          for (final String t in textOnScreen(tester))
            if (RegExp(r'\d+ x 12').hasMatch(t)) t,
        }.toList();

    // =======================================================================
    // 1. The two settings rows
    // =======================================================================
    if (_runs('settings')) {
      Future<void> settingsRow(String what, String path, String section,
          String key, String serverPath) async {
        await log.step('BP-SET $what: the box-and-piece row shows on', () async {
          final int errs = appErrors.length;
          await away();
          await tester.tap(find.byKey(const ValueKey<String>('menu-area-settings')));
          await pumpFor(tester, const Duration(seconds: 1));
          await tapKey(tester, 'setup-section-$section');
          await pumpFor(tester, const Duration(milliseconds: 600));
          await tapKey(tester, 'setup-subject-${section.toLowerCase()}');
          await pumpFor(tester, const Duration(seconds: 2));
          await tapKey(tester, 'subject-tab-$path');
          await pumpFor(tester, const Duration(seconds: 2));
          // The step opens as a window from its tab.
          if (find.text('Buying stages').evaluate().isNotEmpty) {
            await tapButton(tester, 'Open');
          } else {
            await tapButtonStarting(tester, 'Open ');
          }
          await pumpFor(tester, const Duration(seconds: 3));
          final Finder sw = find.byKey(ValueKey<String>(key));
          await pumpUntil(tester, sw, waitingFor: 'the switch $key');
          final SwitchListTile tile = tester.widget<SwitchListTile>(sw.first);
          final Json server = (await me.get(serverPath)) as Json;
          log.saw = 'switch ${tile.value}, editable ${tile.onChanged != null}; '
              'server ${server['box_and_piece_entry']}';
          if (tile.value != true || server['box_and_piece_entry'] != true) {
            throw StateError('not on: ${log.saw}');
          }
          if (!isAdmin && tile.onChanged != null) {
            throw StateError('the viewer may change it');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await away();
      }

      await settingsRow('Sales Stages', 'settings/sales-stages', 'Selling',
          'sales-box-and-piece-entry-switch', _salesSettings);
      await settingsRow('Purchase Settings', 'purchases/purchase-settings',
          'Buying', 'purchase-box-and-piece-entry-switch', _buySettings);
    }

    // =======================================================================
    // 2. Customer and supplier: the tick and the list filter
    // =======================================================================
    if (_runs('parties')) {
      Future<void> party({
        required String who,
        required String path,
        required String collection,
        required String tickKey,
        required String filterKey,
        required Json marked,
        required Json? unmarked,
        required String markedName,
      }) async {
        await log.step('BP-PARTY $who list filter Yes keeps only the marked '
            'one', () async {
          final int errs = appErrors.length;
          await away();
          await openArea(tester, 'masters', path);
          await searchList(tester, tag);
          final bool bothBefore = find.textContaining(markedName).evaluate().isNotEmpty;
          await tapKey(tester, 'phase2-filters');
          final Finder filter = find.byKey(ValueKey<String>(filterKey));
          await pumpUntil(tester, filter, waitingFor: 'the filter $filterKey');
          await tester.tap(filter.first);
          await pumpFor(tester, const Duration(milliseconds: 700));
          await tester.tap(find.text('Yes').last);
          await pumpFor(tester, const Duration(milliseconds: 700));
          await tapButton(tester, 'Apply');
          await pumpFor(tester, const Duration(seconds: 3));
          final bool markedShown =
              find.textContaining(markedName).evaluate().isNotEmpty;
          final bool unmarkedShown = unmarked != null &&
              find.textContaining('${unmarked['name']}').evaluate().isNotEmpty;
          final List<Json> server = <Json>[
            for (final dynamic r in (await me.get('/api/v1/$collection?search='
                    '${Uri.encodeQueryComponent(tag)}&box_and_piece_entry=true'))
                as List<dynamic>)
              r as Json,
          ];
          log.saw = 'before the filter marked shown $bothBefore; with Yes '
              'marked shown $markedShown, unmarked shown $unmarkedShown; '
              'server with the filter ${[for (final Json r in server) r['name']]}';
          final List<String> faults = <String>[
            if (!markedShown) 'the marked one is not listed',
            if (unmarkedShown) 'the unmarked one is still listed',
            if (!server.any((Json r) => r['id'] == marked['id']))
              'the server does not list the marked one',
            if (unmarked != null &&
                server.any((Json r) => r['id'] == unmarked['id']))
              'the server lists the unmarked one',
          ];
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });

        await log.step('BP-PARTY $who form shows the tick as the server holds '
            'it', () async {
          final int errs = appErrors.length;
          await away();
          await openArea(tester, 'masters', path);
          final String how = await openFromList('${marked['code']}');
          final Finder tick = find.byKey(ValueKey<String>(tickKey));
          await pumpUntil(tester, tick, waitingFor: 'the tick $tickKey');
          final CheckboxListTile t = tester.widget<CheckboxListTile>(tick.first);
          final Json server = await me.one(collection, '${marked['id']}');
          log.saw = 'opened with $how; tick ${t.value}, editable '
              '${t.onChanged != null}; server ${server['box_and_piece_entry']}';
          if (t.value != true || server['box_and_piece_entry'] != true) {
            throw StateError('tick and server disagree or are off');
          }
          if (!isAdmin && t.onChanged != null) {
            throw StateError('the viewer may change the tick');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await away();
      }

      await party(
        who: 'customer',
        path: 'masters/customers',
        collection: 'customers',
        tickKey: 'customer-box-and-piece-entry',
        filterKey: 'customer-filter-box-and-pieces',
        marked: boxCustomer,
        unmarked: plainCustomer,
        markedName: nameC,
      );
      await party(
        who: 'supplier',
        path: 'masters/vendors',
        collection: 'vendors',
        tickKey: 'vendor-box-and-piece-entry',
        filterKey: 'vendor-filter-box-and-pieces',
        marked: vendor,
        unmarked: null,
        markedName: nameV,
      );

      if (isAdmin) {
        await log.step('BP-PARTY customer: ticking the plain customer saves '
            'it on the server', () async {
          final int errs = appErrors.length;
          await away();
          await openArea(tester, 'masters', 'masters/customers');
          await openFromList('${plainCustomer['code']}');
          final Finder tick =
              find.byKey(const ValueKey<String>('customer-box-and-piece-entry'));
          await pumpUntil(tester, tick, waitingFor: 'the tick');
          await tester.ensureVisible(tick.first);
          await tester.tap(tick.first);
          await pumpFor(tester, const Duration(milliseconds: 600));
          final String said = await pressAndRead(
              tester, () => tapButton(tester, 'Save customer'),
              seconds: 5);
          final Json server = await admin.one('customers', '${plainCustomer['id']}');
          log.saw = 'said "$said"; server ${server['box_and_piece_entry']}';
          if (server['box_and_piece_entry'] != true) {
            throw StateError('not saved: ${log.saw}');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await away();
      } else {
        await log.step('BP-PARTY viewer: the server refuses the tick', () async {
          final ({int status, String text}) put = await me.attempt('PUT',
              '/api/v1/customers/${plainCustomer['id']}',
              <String, dynamic>{'box_and_piece_entry': true});
          log.saw = 'PUT as the viewer ${put.status}';
          if (put.status != 403) throw StateError('server answered ${put.status}');
        });
      }
    }

    // =======================================================================
    // 3. Typing boxes and pieces: sales order, quotation, counter bill
    // =======================================================================
    /// Type 2 boxes and 17 pieces on line 0 of the editor whose cells start
    /// [prefix]; return what the cells, the note and the side panel said.
    Future<String> typeTwoAndSeventeen(
        String prefix, String noteKey, String sideKey) async {
      await typeKeyed('$prefix-box', '2');
      await typeKeyed('$prefix-pcs', '17');
      // Leaving the Pcs cell evens it out.
      await tapCell('$prefix-free-box');
      await pumpFor(tester, const Duration(seconds: 2));
      return 'box "${cell('$prefix-box')}", pcs "${cell('$prefix-pcs')}", '
          'note "${textsUnder(noteKey).join(' ')}", side '
          '"${textsUnder(sideKey).join(' ')}"';
    }

    List<String> evenFaults(String prefix, String sideKey) => <String>[
          if (cell('$prefix-box') != '3') 'box cell is ${cell('$prefix-box')}',
          if (cell('$prefix-pcs') != '5') 'pcs cell is ${cell('$prefix-pcs')}',
          if (!textsUnder(sideKey)
              .join(' ')
              .contains('Box of 12. 3 boxes + 5 pcs = 41 pcs.'))
            'the side panel does not read "Box of 12. 3 boxes + 5 pcs = 41 pcs."',
        ];

    String savedFaults(Json? doc, String qtyKey) {
      if (doc == null) return 'nothing saved';
      final Json l = line0(doc);
      return <String>[
        if (!_same(_n(l[qtyKey] ?? l['quantity']), 41))
          'server quantity ${l[qtyKey] ?? l['quantity']}',
        if (!_same(_n(l['pack_size']), 12)) 'server pack ${l['pack_size']}',
        if (doc['box_and_piece_entry'] != true)
          'server flag ${doc['box_and_piece_entry']}',
      ].join('; ');
    }

    Future<Json?> newFor(String collection, Set<String> before) async {
      for (final Json r in await list('/api/v1/$collection?customer_id='
          '${boxCustomer['id']}&page_size=100')) {
        if (!before.contains('${r['id']}')) {
          return admin.one(collection, '${r['id']}');
        }
      }
      return null;
    }

    Future<Set<String>> idsFor(String collection) async => <String>{
          for (final Json r in await list('/api/v1/$collection?customer_id='
              '${boxCustomer['id']}&page_size=100'))
            '${r['id']}',
        };

    if (isAdmin && _runs('order')) {
      bool opened = false;
      await log.step('BP-SO-1 a new order for the boxed customer opens in '
          'boxes and pieces', () async {
        final int errs = appErrors.length;
        await away();
        await goTo('sell', 'salesOrders');
        await tapNew(tester);
        await pumpUntil(tester, find.byKey(const ValueKey<String>('sales-order-save')));
        await chooseIn(tester, 'sales-order-customer', nameC);
        await chooseIn(tester, 'sales-order-line-product-0', nameP);
        await pumpFor(tester, const Duration(seconds: 3));
        opened = true;
        final bool toggle = find
            .byKey(const ValueKey<String>('sales-order-box-and-pieces'))
            .evaluate()
            .isNotEmpty;
        final List<String> cells = keysStarting('sales-order-line-0-')
            .where((String k) => RegExp(r'-(box|pcs|free-box|free-pcs)$').hasMatch(k))
            .toList()
          ..sort();
        final bool heads = find.text('Box').evaluate().isNotEmpty &&
            find.text('Pcs').evaluate().isNotEmpty &&
            find.text('Free box').evaluate().isNotEmpty &&
            find.text('Free pcs').evaluate().isNotEmpty;
        log.saw = 'toggle $toggle; headings Box/Pcs/Free box/Free pcs $heads; '
            'cells $cells; customer server mark ${boxCustomer['box_and_piece_entry']}';
        if (!toggle) throw StateError('no Boxes and pieces / Pieces only toggle');
        if (!heads || cells.length != 4) {
          throw StateError('not in boxes and pieces for a boxed customer');
        }
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      if (opened) {
        await log.step('BP-SO-2 2 boxes + 17 pcs evens out to 3 + 5, side '
            'panel 41 pcs', () async {
          final int errs = appErrors.length;
          log.saw = await typeTwoAndSeventeen('sales-order-line-0',
              'sales-order-line-box-note-0', 'sales-order-side-boxes');
          final List<String> faults =
              evenFaults('sales-order-line-0', 'sales-order-side-boxes');
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await log.step('BP-SO-3 Pieces only shows 41 in Qty, and back', () async {
          final int errs = appErrors.length;
          await tapKey(tester, 'box-piece-toggle-off');
          await pumpFor(tester, const Duration(seconds: 1));
          final bool cellsGone = keysStarting('sales-order-line-0-box').isEmpty;
          final bool qty = find.text('Qty').evaluate().isNotEmpty;
          final String boxes = boxesIn(tester, 'sales-order-line-0');
          await tapKey(tester, 'box-piece-toggle-on');
          await pumpFor(tester, const Duration(seconds: 1));
          log.saw = 'Pieces only: box cells gone $cellsGone, Qty heading $qty, '
              'line boxes "$boxes"; back on: box "${cell('sales-order-line-0-box')}", '
              'pcs "${cell('sales-order-line-0-pcs')}"';
          final List<String> faults = <String>[
            if (!cellsGone) 'box cells still shown',
            if (!qty) 'no Qty heading',
            if (!boxes.split(' / ').contains('41')) 'Qty is not 41',
            if (cell('sales-order-line-0-box') != '3' ||
                cell('sales-order-line-0-pcs') != '5')
              'back on, the cells are not 3 + 5',
          ];
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await log.step('BP-SO-4 a pieces-only item on line 2: its box cells '
            'are closed', () async {
          final int errs = appErrors.length;
          if (find
              .byKey(const ValueKey<String>('sales-order-line-product-1'))
              .evaluate()
              .isEmpty) {
            final Finder add = find.textContaining('add a product');
            if (add.evaluate().isNotEmpty) {
              await tester.tap(add.first);
              await pumpFor(tester, const Duration(seconds: 1));
            }
          }
          await chooseIn(tester, 'sales-order-line-product-1', nameN);
          await pumpFor(tester, const Duration(seconds: 2));
          final bool closed = find
                  .byKey(const ValueKey<String>('sales-order-line-1-box-closed'))
                  .evaluate()
                  .isNotEmpty &&
              find
                  .byKey(const ValueKey<String>('sales-order-line-1-free-box-closed'))
                  .evaluate()
                  .isNotEmpty;
          await typeKeyed('sales-order-line-1-pcs', '15');
          await tapCell('sales-order-line-1-free-pcs');
          final String side = textsUnder('sales-order-side-boxes').join(' ');
          log.saw = 'box cells closed $closed; pcs "${cell('sales-order-line-1-pcs')}" '
              '(15 typed, stays: no pack); side panel for it "$side"';
          if (!closed) throw StateError('the box cells are open on a pieces-only item');
          if (cell('sales-order-line-1-pcs') != '15') {
            throw StateError('15 pcs did not stay 15');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await log.step('BP-SO-5 saved: the server holds 41 at a pack of 12, '
            'and 15 with no pack', () async {
          final int errs = appErrors.length;
          final Set<String> before = await idsFor('sales-orders');
          final String said = await pressAndRead(
              tester, () => tapKey(tester, 'sales-order-save'),
              seconds: 8);
          final Json? made = await newFor('sales-orders', before);
          final List<dynamic> lines = (made?['lines'] as List<dynamic>?) ?? <dynamic>[];
          log.saw = 'said "$said"; ${made == null ? 'no order' : '${docNumber(made)} flag ${made['box_and_piece_entry']}'}; '
              'lines ${[for (final dynamic l in lines) '${(l as Json)['quantity']} pack ${l['pack_size']}']}';
          final String faults = savedFaults(made, 'quantity');
          final bool second = lines.length > 1 &&
              _same(_n((lines[1] as Json)['quantity']), 15) &&
              (lines[1] as Json)['pack_size'] == null;
          if (faults.isNotEmpty) throw StateError(faults);
          if (!second) throw StateError('line 2 is not 15 with no pack');
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
      }
      await away();

      await log.step('BP-SO-6 a pack size that is not the item\'s is refused '
          'by the server', () async {
        final ({int status, String text}) r = await admin.attempt(
            'POST', '/api/v1/sales-orders', <String, dynamic>{
          'customer_id': boxCustomer['id'],
          'branch_id': branch['id'],
          'warehouse_id': warehouse['id'],
          'order_date': _today(),
          'lines': <Json>[
            <String, dynamic>{
              'line_number': 1,
              'product_id': productN['id'],
              'quantity': '15',
              'unit_price': '10',
              'pack_size': '12',
            },
          ],
        });
        log.saw = '${r.status} ${r.text.length > 300 ? r.text.substring(0, 300) : r.text}';
        if (r.status < 400 || r.status >= 500) {
          throw StateError('answered ${r.status}');
        }
      });
    }

    if (isAdmin && _runs('quote')) {
      bool opened = false;
      await log.step('BP-QT-1 a quotation typed 2 boxes + 17 pcs evens out to '
          '3 + 5', () async {
        final int errs = appErrors.length;
        await away();
        await openMenu(tester, 'sell', 'quotations');
        await tapNew(tester);
        await pumpUntil(tester, find.byKey(const ValueKey<String>('quotation-save')));
        await chooseIn(tester, 'quotation-customer', nameC);
        await chooseIn(tester, 'quotation-line-product-0', nameP);
        await pumpFor(tester, const Duration(seconds: 3));
        opened = true;
        final String typed = await typeTwoAndSeventeen('quotation-line-0',
            'quotation-line-box-note-0', 'quotation-side-boxes');
        log.saw = typed;
        final List<String> faults =
            evenFaults('quotation-line-0', 'quotation-side-boxes');
        if (faults.isNotEmpty) throw StateError(faults.join('; '));
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      if (opened) {
        await log.step('BP-QT-2 the quotation saved: 41 at a pack of 12',
            () async {
          final int errs = appErrors.length;
          final Set<String> before = await idsFor('quotations');
          final String said = await pressAndRead(
              tester, () => tapKey(tester, 'quotation-save'),
              seconds: 8);
          final Json? made = await newFor('quotations', before);
          log.saw = 'said "$said"; ${made == null ? 'none' : '${docNumber(made)} flag ${made['box_and_piece_entry']}, line ${line0(made)['quantity']} pack ${line0(made)['pack_size']}'}';
          final String faults = savedFaults(made, 'quantity');
          if (faults.isNotEmpty) throw StateError(faults);
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
      }
      await away();
    }

    if (isAdmin && _runs('counter')) {
      final Json stages = (await admin.get(_salesSettings)) as Json;
      const List<String> stageKeys = <String>[
        'quotation_stage', 'sales_order_stage', 'delivery_note_stage',
        'default_branch_id', 'default_warehouse_id', 'promotion_mode',
        'max_line_discount_percent', 'rate_includes_tax',
        'new_outlets_need_approval', 'reservation_lapse_days',
        'sales_order_approval', 'delivery_note_approval',
        'sales_invoice_approval', 'round_bills_to_rupee', 'salesman_required',
        'box_and_piece_entry',
      ];
      final Json stagesBack = <String, dynamic>{
        for (final String k in stageKeys)
          if (stages.containsKey(k)) k: stages[k],
      };
      try {
        await admin.write('PUT', _salesSettings, <String, dynamic>{
          ...stagesBack,
          'quotation_stage': false,
          'sales_order_stage': false,
          'delivery_note_stage': false,
          'default_branch_id': branch['id'],
          'default_warehouse_id': warehouse['id'],
        });
        log.info('BP-SB', 'order and note stages off over HTTP');
        bool opened = false;
        await log.step('BP-SB-1 a counter bill typed 2 boxes + 17 pcs evens '
            'out to 3 + 5', () async {
          final int errs = appErrors.length;
          await away();
          await openMenu(tester, 'sell', 'salesInvoices/sales-invoices');
          await tapNew(tester);
          await pumpFor(tester, const Duration(seconds: 2));
          Future<void> pick(String key, String filter, String name) async {
            await tapKey(tester, key);
            final Finder box = find.descendant(
                of: find.byKey(ValueKey<String>(key)),
                matching: find.byType(EditableText));
            if (box.evaluate().isNotEmpty) {
              await tester.enterText(box.first, filter);
              await pumpFor(tester, const Duration(seconds: 1));
            }
            final Finder entry = find.textContaining(name);
            await pumpUntil(tester, entry, waitingFor: 'entry $name');
            await tester.tap(entry.last, warnIfMissed: false);
            await pumpFor(tester, const Duration(seconds: 1));
          }

          await pick('sales-invoice-customer', 'BC$tag', nameC);
          await pick('sales-invoice-direct-product-0', '0B$tag-P', nameP);
          await pumpFor(tester, const Duration(seconds: 3));
          opened = true;
          final bool toggle = find
              .byKey(const ValueKey<String>('box-piece-toggle-on'))
              .evaluate()
              .isNotEmpty;
          final String typed = await typeTwoAndSeventeen(
              'sales-invoice-direct-0',
              'sales-invoice-direct-box-note-0',
              'sales-invoice-side-boxes');
          log.saw = 'toggle $toggle; $typed';
          final List<String> faults =
              evenFaults('sales-invoice-direct-0', 'sales-invoice-side-boxes');
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        if (opened) {
          await log.step('BP-SB-2 the counter bill saved as a draft: 41 at a '
              'pack of 12', () async {
            final int errs = appErrors.length;
            final Set<String> before = await idsFor('sales-invoices');
            final String said = await pressAndRead(
                tester, () => tapKey(tester, 'sales-invoice-save'),
                seconds: 10);
            // Put the stages back at once (a run cut off before its finally
            // left the firm billing directly once, 2026-10-16).
            await admin.write('PUT', _salesSettings, stagesBack);
            final Json? made = await newFor('sales-invoices', before);
            log.saw = 'said "$said"; ${made == null ? 'none' : '${docNumber(made)} ${made['status']} flag ${made['box_and_piece_entry']}, line ${line0(made)['current_invoice_quantity'] ?? line0(made)['quantity']} pack ${line0(made)['pack_size']}'}';
            if (made != null) {
              final ({int status, String text}) gone = await admin.attempt(
                  'POST',
                  '/api/v1/sales-invoices/${made['id']}/cancel',
                  <String, dynamic>{'reason': 'click flow clean-up'});
              log.info('BP-SB', 'draft cancelled: ${gone.status}');
            }
            final String faults = savedFaults(made, 'current_invoice_quantity');
            if (faults.isNotEmpty) throw StateError(faults);
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
        }
        await admin.write('PUT', _salesSettings, stagesBack);
        await away();
      } finally {
        await admin.write('PUT', _salesSettings, stagesBack);
        log.info('BP-SB', 'workflow stages put back over HTTP');
      }
    }

    // =======================================================================
    // 4. Continuing figures read "3 x 12 + 5"
    // =======================================================================
    if (_runs('continue') || _runs('prnew')) {
      Future<void> continuing(String id, String what, String area, String path,
          Json? doc, String prefix, String want) async {
        if (doc == null) {
          log.skip(id, 'its document could not be made over HTTP');
          return;
        }
        await log.step('$id $what: continuing figures read "$want"', () async {
          final int errs = appErrors.length;
          await away();
          await goTo(area, path);
          final String how = await openFromList(docNumber(doc));
          await pumpFor(tester, const Duration(seconds: 2));
          final List<String> seen = boxTexts();
          final String cells = <String>[
            for (final String k in keysStarting('$prefix-line-0-'))
              if (RegExp(r'-(box|pcs)$').hasMatch(k)) '${k.split('-').last}=${cell(k)}',
          ].join(', ');
          final Json l = line0(doc);
          log.saw = 'opened with $how; box texts $seen; cells [$cells]; server '
              'line pack ${l['pack_size']}, flag ${doc['box_and_piece_entry']}';
          // A purchase order continues nothing: its own cells are read.
          final bool ownCells =
              prefix == 'purchase-order' && cells.startsWith('box=3, pcs=5');
          if (!ownCells && !seen.any((String t) => t.contains(want))) {
            throw StateError('no "$want" on screen: ${log.saw}; screen '
                '${textOnScreen(tester).skip(20).take(60).join(' | ')}');
          }
          if (!_same(_n(l['pack_size']), 12)) {
            throw StateError('server pack ${l['pack_size']}');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await away();
      }

      final String forty1 = boxesAndPieces('41', '12');
      final String eighty9 = boxesAndPieces('89', '12');
      Future<void> newOn(String id, String what, String area, String path,
          String pickerKey, Json? source, String prefix, String want) async {
        if (source == null) {
          log.skip(id, 'its source could not be made over HTTP');
          return;
        }
        await log.step('$id $what: continuing figures read "$want"', () async {
          final int errs = appErrors.length;
          await away();
          await goTo(area, path);
          await tapNew(tester);
          await pumpFor(tester, const Duration(seconds: 2));
          await chooseIn(tester, pickerKey, docNumber(source));
          await pumpFor(tester, const Duration(seconds: 3));
          final List<String> seen = boxTexts();
          final String cells = <String>[
            for (final String k in keysStarting('$prefix-line-0-'))
              if (RegExp(r'-(box|pcs)$').hasMatch(k)) '${k.split('-').last}=${cell(k)}',
          ].join(', ');
          final bool toggle = find
              .byKey(ValueKey<String>('$prefix-box-and-pieces'))
              .evaluate()
              .isNotEmpty;
          log.saw = 'toggle $toggle; box texts $seen; cells [$cells]; server '
              'source line ${line0(source)['quantity'] ?? line0(source)['current_receipt_quantity']} '
              'pack ${line0(source)['pack_size']}';
          if (!seen.any((String t) => t.contains(want))) {
            throw StateError('no "$want" on screen: ${log.saw}; screen '
                '${textOnScreen(tester).skip(20).take(60).join(' | ')}');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await away();
      }

      if (_runs('continue')) {
        await newOn('BP-DN', 'a new delivery note on order B', 'sell',
          'deliveryNotes/delivery-notes', 'delivery-note-order', orderB,
          'delivery-note', forty1);
        await continuing('BP-SI', 'the draft bill of note A', 'sell',
          'salesInvoices/sales-invoices', billA, 'sales-invoice', forty1);
        await continuing('BP-SR', 'the draft return of note A', 'sell',
          'salesReturns', returnA, 'sales-return', forty1);
        await continuing('BP-PO', 'the draft purchase order of 41', 'buy',
          'purchases/purchase-orders', po3, 'purchase-order', forty1);
        await continuing('BP-GR', 'the draft receipt on the order of 41', 'buy',
          'goodsReceipts/receipts', gr2, 'goods-receipt', forty1);
        await continuing('BP-PI', 'the draft supplier\'s bill of receipt 1 (89)',
          'buy', 'purchaseInvoices', pbill, 'purchase-invoice', eighty9);
      }
      await newOn('BP-PR', 'a new purchase return of receipt 1 (89)', 'buy',
          'purchaseReturns', 'purchase-return-receipt', gr1, 'purchase-return',
          eighty9);
    }

    // =======================================================================
    // 5. Stock: Show boxes
    // =======================================================================
    if (_runs('stock')) {
      bool turnedOn = false;
      try {
        await log.step('BP-ST Show boxes reads the stock of the boxed item as '
            'the server\'s quantity in boxes', () async {
          final int errs = appErrors.length;
          await away();
          await goTo('stock', 'inventory/inventory');
          await searchList(tester, '0B$tag-P');
          await pumpFor(tester, const Duration(seconds: 2));
          final Finder toggle = find.byKey(const ValueKey<String>('show-boxes'));
          final bool offered = toggle.evaluate().isNotEmpty;
          final List<String> before = rowOf(tester, nameP);
          if (offered) {
            await tester.tap(toggle.first);
            turnedOn = true;
            await pumpFor(tester, const Duration(seconds: 2));
          }
          final List<String> after = rowOf(tester, nameP);
          Json? row;
          for (final dynamic r in (await me.get('/api/v1/inventory?search='
                  '${Uri.encodeQueryComponent('0B$tag-P')}&page_size=20'))
              as List<dynamic>) {
            if ((r as Json)['product_id'] == productP['id']) row = r;
          }
          final String want = row == null
              ? '(no row)'
              : stockInBoxes('${row['current_quantity']}', '12');
          log.saw = 'Show boxes offered $offered; row before $before; after '
              '$after; server current ${row?['current_quantity']} pack '
              '${row?['pack_size']} ${row?['pack_unit_code']}, expected "$want"';
          if (!offered) throw StateError('Show boxes is not offered');
          if (row == null) throw StateError('no stock row on the server');
          if (!_same(_n(row['pack_size']), 12)) {
            throw StateError('server pack ${row['pack_size']}');
          }
          if (!after.contains(want)) {
            throw StateError('the row does not read "$want": ${log.saw}');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
      } finally {
        if (turnedOn) {
          final Finder toggle = find.byKey(const ValueKey<String>('show-boxes'));
          if (toggle.evaluate().isNotEmpty) {
            await tester.tap(toggle.first);
            await pumpFor(tester, const Duration(seconds: 1));
          }
        }
      }
      await away();
    }

    // =======================================================================
    // 6. The viewer: what is shown and refused
    // =======================================================================
    if (!isAdmin && _runs('order')) {
      final Json so = orderB ?? await approvedOrder('41');
      await log.step('BP-V-1 the viewer opens a saved boxed order: 41 PIECE, '
          'read only, no New', () async {
        final int errs = appErrors.length;
        await away();
        await openMenu(tester, 'sell', 'salesOrders');
        final String newState = buttonState(tester, 'New');
        final String how = await openFromList(docNumber(so));
        await pumpFor(tester, const Duration(seconds: 2));
        final Finder boxCell =
            find.byKey(const ValueKey<String>('sales-order-line-0-box'));
        bool? readOnly;
        if (boxCell.evaluate().isNotEmpty) {
          final Finder inner =
              find.descendant(of: boxCell.first, matching: find.byType(EditableText));
          if (inner.evaluate().isNotEmpty) {
            readOnly = tester.widget<EditableText>(inner.first).readOnly;
          }
        }
        final bool save = find
            .byKey(const ValueKey<String>('sales-order-save'))
            .evaluate()
            .isNotEmpty;
        final List<String> seenBoxes = boxTexts();
        final List<String> lineRow = rowOf(tester, '41.0000');
        log.saw = 'view line $lineRow; box texts $seenBoxes; New $newState; opened with $how; box '
            '"${cell('sales-order-line-0-box')}", pcs '
            '"${cell('sales-order-line-0-pcs')}", read only $readOnly; save '
            'button $save; server ${line0(so)['quantity']} pack '
            '${line0(so)['pack_size']}';
        final List<String> faults = <String>[
          if (newState == 'enabled') 'New offered to the viewer',
          // The saved order opens as its view: the line in pieces, in the
          // unit it was counted in (D-UI-112: it read 41 BOX).
          if (!lineRow.contains('41.0000')) 'the view has no line of 41',
          if (lineRow.contains('BOX')) 'the line of 41 pieces reads as BOX',
          if (!lineRow.contains('PIECE')) 'the line does not say PIECE',
          if (readOnly == false) 'the cells can be typed in',
        ];
        if (faults.isNotEmpty) {
          throw StateError('${faults.join('; ')}: ${log.saw}; screen '
              '${textOnScreen(tester).skip(20).take(70).join(' | ')}');
        }
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      await away();
      await log.step('BP-V-2 the server refuses the viewer an order in boxes',
          () async {
        final ({int status, String text}) r = await me.attempt(
            'POST', '/api/v1/sales-orders', <String, dynamic>{
          'customer_id': boxCustomer['id'],
          'branch_id': branch['id'],
          'warehouse_id': warehouse['id'],
          'order_date': _today(),
          'box_and_piece_entry': true,
          'lines': <Json>[
            <String, dynamic>{
              'line_number': 1,
              'product_id': productP['id'],
              'quantity': '41',
              'unit_price': '10',
              'pack_size': '12',
            },
          ],
        });
        log.saw = 'POST as the viewer ${r.status}';
        if (r.status != 403) throw StateError('answered ${r.status}');
      });
    }

    log.skip('BP-print', 'prints are the printing round');
    log.skip('BP-scan', 'a pack scan on the counter bill needs a scanner');
    log.info('errors', 'app errors and overflows this run: ${appErrors.length}');
    log.finish();
  });
}
