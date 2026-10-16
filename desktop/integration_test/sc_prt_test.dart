import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:printing/printing.dart' show OutputType, Printer;
// ignore: implementation_imports
import 'package:printing/src/interface.dart' show PrintingPlatform;

import 'cases.dart';
import 'harness.dart';
import 'sc_gt_test.dart' show leave, openArea, pickRow;
import 'sell_data.dart' show tapButtonOrMenu;

/// Printing on the screens (rows P1 and P2; book 08 TC-SELL-099, book 09
/// TC-SELL-109, TC-SELL-112 and TC-SELL-117; the HTTP half is
/// `docs/qa/PRINTING_API_CHECK_ROUND_1_2026-10-15.md`). Run on the printing
/// round's first `ready-firm` as readyadmin, then as readyviewer.
///
/// The admin opens Sales Invoices > ... > Print settings, reads the paper,
/// the copies and the terms against the server, turns the paper to Half page
/// and types two lines of terms, saves, and reads them back. Print on a short
/// bill opens the paper box: it names Half page, and one print is switched to
/// Full page; a customer whose Bill paper is set to Full page on the customer
/// screen gets Full page; a sixty-line bill goes to Full page by itself and
/// offers no choice; Cancel prints nothing. Then the paper goes back to A4 on
/// the screen: a customer on Half page is not read and no box opens. The
/// full-page bill of a batch with a manufacture date is printed and its text
/// read: Mfg, Total quantity, the terms, Market and Order By, and a bill with
/// neither salesman nor round prints neither row.
///
/// What the app hands the printer is caught: the operating system's print
/// dialog is replaced by one that keeps the bytes, so the flow reads the very
/// PDF a person would have printed (page sizes off its /MediaBox, text off its
/// streams), and no printer is touched.
///
/// The viewer reads the same settings with Save off, is refused a save over
/// HTTP, and prints a bill through the paper box.
///
/// Every run makes its own masters and bills over HTTP, named with the minute
/// it started, and puts the firm's print template and sales stages back.

/// IT_PART=settings (or half, full) runs only that part of the admin flow.
const String _part = String.fromEnvironment('IT_PART');
bool _runs(String part) => _part.isEmpty || _part.split(',').contains(part);

const String _template = '/api/v1/document-framework/print-templates/SALES_INVOICE';
const String _workflow = '/api/v1/sales-orders/workflow-settings';

String _today() => DateTime.now().toIso8601String().substring(0, 10);

/// One PDF the app handed to the printer.
class _Printed {
  _Printed(this.name, this.bytes);
  final String name;
  final List<int> bytes;

  /// The size of each page, by /MediaBox: A4, HALF or OTHERwxh.
  List<String> get pages => <String>[
        for (final RegExpMatch m in RegExp(r'/MediaBox\s*\[\s*([\d.\- ]+?)\s*\]')
            .allMatches(latin1.decode(bytes)))
          _kind(m.group(1)!),
      ];

  static String _kind(String box) {
    final List<double> v = <double>[
      for (final String s in box.trim().split(RegExp(r'\s+'))) double.parse(s),
    ];
    final int w = (v[2] - v[0]).round();
    final int h = (v[3] - v[1]).round();
    if ((w - 595).abs() <= 2 && (h - 842).abs() <= 3) return 'A4';
    if ((w - 595).abs() <= 2 && (h - 421).abs() <= 3) return 'HALF';
    return 'OTHER${w}x$h';
  }

  /// The strings the PDF shows, in drawing order (reportlab: flate, maybe
  /// ASCII85 first).
  List<String> get text {
    final String raw = latin1.decode(bytes);
    final List<String> out = <String>[];
    for (final RegExpMatch m
        in RegExp(r'stream\r?\n([\s\S]*?)endstream').allMatches(raw)) {
      String chunk = m.group(1)!.trim();
      List<int> body = latin1.encode(chunk);
      try {
        if (chunk.endsWith('~>')) {
          chunk = chunk.substring(0, chunk.length - 2);
          if (chunk.startsWith('<~')) chunk = chunk.substring(2);
          body = _a85(chunk);
        }
        body = zlib.decode(body);
      } catch (_) {
        continue;
      }
      final String page = latin1.decode(body);
      for (final RegExpMatch s
          in RegExp(r'\(((?:\\.|[^\\)])*)\)').allMatches(page)) {
        final String shown = s
            .group(1)!
            .replaceAll(r'\(', '(')
            .replaceAll(r'\)', ')')
            .replaceAll(r'\\', r'\')
            .trim();
        // The half page pads its cells with spaces; a blank says nothing.
        if (shown.isNotEmpty) out.add(shown);
      }
    }
    return out;
  }

  static List<int> _a85(String s) {
    final List<int> out = <int>[];
    final List<int> group = <int>[];
    for (final int c in s.codeUnits) {
      if (c <= 32) continue;
      if (c == 0x7a && group.isEmpty) {
        out.addAll(const <int>[0, 0, 0, 0]);
        continue;
      }
      group.add(c - 33);
      if (group.length == 5) {
        int v = 0;
        for (final int d in group) {
          v = v * 85 + d;
        }
        out.addAll(<int>[(v >> 24) & 255, (v >> 16) & 255, (v >> 8) & 255, v & 255]);
        group.clear();
      }
    }
    if (group.isNotEmpty) {
      final int n = group.length;
      while (group.length < 5) {
        group.add(84);
      }
      int v = 0;
      for (final int d in group) {
        v = v * 85 + d;
      }
      final List<int> b = <int>[(v >> 24) & 255, (v >> 16) & 255, (v >> 8) & 255, v & 255];
      out.addAll(b.take(n - 1));
    }
    return out;
  }
}

/// The operating system's print dialog, replaced by one that keeps what it
/// was handed and says it printed.
class _KeepingPrinter extends PrintingPlatform {
  final List<_Printed> printed = <_Printed>[];

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);

  @override
  Future<bool> layoutPdf(
    Printer? printer,
    Object? onLayout,
    String name,
    Object? format,
    bool dynamicLayout,
    bool usePrinterSettings,
    OutputType outputType,
    bool forceCustomPrintPaper,
  ) async {
    final dynamic bytes = await (onLayout as dynamic)(format);
    printed.add(_Printed(name, List<int>.from(bytes as Uint8List)));
    return true;
  }
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('PRT: printing ($itHandle)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final bool isAdmin = itHandle == 'readyadmin';
    final Server admin = await Server.connectAs(
        '$itSuffix.readyadmin@fixtures.local', fixturePassword);
    final Server me = await Server.connect();
    await startAndSignIn(tester);
    collectAppErrors();
    final _KeepingPrinter printer = _KeepingPrinter();
    PrintingPlatform.instance = printer;
    final FlowLog log = FlowLog('prt-$itHandle');

    final DateTime now = DateTime.now();
    final String stamp = '${now.hour.toString().padLeft(2, '0')}'
        '${now.minute.toString().padLeft(2, '0')}';
    final String tag = '$stamp${isAdmin ? 'A' : 'V'}';

    String errorsSince(int from) => appErrors.skip(from).take(3).join(' || ');

    // -- Reading the server --------------------------------------------------
    Future<List<Json>> list(String path) async => <Json>[
          for (final dynamic row in (await admin.get(path)) as List<dynamic>)
            row as Json,
        ];
    Future<Json> template() async => (await admin.get(_template)) as Json;
    Future<Json> paperOf(String billId) async =>
        (await admin.get('/api/v1/sales-invoices/$billId/print/paper')) as Json;

    // -- Masters and bills, made over HTTP -------------------------------------
    final Json branch = (await list('/api/v1/branches?page_size=50'))
        .firstWhere((Json b) => b['code'] == 'HO');
    final Json warehouse = (await list('/api/v1/warehouses?page_size=50'))
        .firstWhere((Json w) => w['code'] == 'MAIN');
    final String piece = '${(await list('/api/v1/uom-framework/uoms?page_size=100')).firstWhere((Json u) => u['code'] == 'PIECE')['id']}';
    final List<Json> brands = await list('/api/v1/products/brands');
    String brand;
    if (brands.isNotEmpty) {
      brand = '${brands.first['id']}';
    } else {
      final Json company = (await admin.write('POST',
          '/api/v1/products/principals',
          <String, dynamic>{'code': 'FIXTURE', 'name': 'Fixture Company'})) as Json;
      brand = '${((await admin.write('POST', '/api/v1/products/brands', <String, dynamic>{'name': 'Fixture Brand', 'principal_id': company['id']})) as Json)['id']}';
    }

    Future<Json> product(String code, {bool batch = false}) async =>
        (await admin.write('POST', '/api/v1/products', <String, dynamic>{
          'code': code,
          'name': 'PRT item $code',
          'brand_id': brand,
          'product_type': 'STOCK_ITEM',
          'tax_profile_group_code': 'GST_18_LOCAL',
          'selling_price': '100',
          'purchase_price': '60',
          'base_uom_id': piece,
          'inventory_uom_id': piece,
          'sales_uom_id': piece,
          'purchase_uom_id': piece,
          'track_batch': batch,
          'track_expiry': batch,
          'track_manufacturing_date': batch,
        })) as Json;

    Future<Json> customer(String code, {String? paper}) async =>
        (await admin.write('POST', '/api/v1/customers', <String, dynamic>{
          'code': code,
          'name': 'PRT buyer $code',
          'customer_type': 'BUSINESS',
          'currency_code': 'INR',
          if (paper != null) 'bill_page_size': paper,
        })) as Json;

    final Json plain = await product('0P$tag');
    Json? withMfg, noMfg;
    final List<Json> stockLines = <Json>[
      <String, dynamic>{
        'product_id': plain['id'],
        'quantity': '300',
        'unit_cost': '60',
      },
    ];
    if (isAdmin) {
      withMfg = await product('0M$tag', batch: true);
      noMfg = await product('0N$tag', batch: true);
      stockLines.addAll(<Json>[
        <String, dynamic>{
          'product_id': withMfg['id'],
          'quantity': '50',
          'unit_cost': '60',
          'batch_number': 'MF$tag',
          'expiry_date': '2027-12-31',
          'mrp': '150',
        },
        <String, dynamic>{
          'product_id': noMfg['id'],
          'quantity': '50',
          'unit_cost': '60',
          'batch_number': 'NM$tag',
          'expiry_date': '2027-11-30',
          'mrp': '150',
        },
      ]);
    }
    final Json opening = (await admin.write('POST',
        '/api/v1/inventory/opening-stock', <String, dynamic>{
      'branch_id': branch['id'],
      'warehouse_id': warehouse['id'],
      'reference_number': 'OS-PRT$tag',
      'posting_date': _today(),
      'lines': stockLines,
    })) as Json;
    await admin.write('POST',
        '/api/v1/inventory/opening-stock/${opening['id']}/post', <String, dynamic>{});

    String salesmanName = '';
    String marketName = '';
    Json? roundBuyer;
    String? salesmanId, routeId;
    if (isAdmin) {
      // The batch of M was made in January 2026; N's records no such day.
      final Json lot =
          (await list('/api/v1/batch-serial/batches?search=MF$tag')).first;
      await admin.write('PUT', '/api/v1/batch-serial/batches/${lot['id']}',
          <String, dynamic>{'manufacturing_date': '2026-01-15'});
      // A salesman on the firm's list, and a round the buyer is on.
      salesmanName = 'PRT Asha $tag';
      final Json salesman = (await admin.write('POST', '/api/v1/salesmen',
          <String, dynamic>{'name': salesmanName})) as Json;
      salesmanId = '${salesman['id']}';
      const String t = '/api/v1/sales-territories';
      final Json lv = (await admin.get('$t/hierarchy-levels')) as Json;
      final Map<String, String> levels = <String, String>{
        for (final dynamic l in lv['levels'] as List<dynamic>)
          '${(l as Json)['level_code']}': '${l['id']}',
      };
      Future<Json> node(String code, String level, String? parent,
              [Json? extra]) async =>
          (await admin.write('POST', t, <String, dynamic>{
            'code': '$code$tag',
            'name': '$code $tag',
            'hierarchy_level_id': levels[level],
            'parent_id': parent,
            ...?extra,
          })) as Json;
      final Json region = await node('PRG', 'REGION', null);
      final Json area = await node('PTR', 'TERRITORY', '${region['id']}');
      final Json kind = (await admin.write('POST', '$t/route-types',
          <String, dynamic>{'code': 'PRT$tag', 'name': 'PRT $tag'})) as Json;
      marketName = 'Market $tag';
      final Json round = (await admin.write('POST', t, <String, dynamic>{
        'code': 'PRO$tag',
        'name': marketName,
        'hierarchy_level_id': levels['ROUTE'],
        'parent_id': area['id'],
        'route_profile': <String, dynamic>{
          'route_type_id': kind['id'],
          'visit_frequency': 'WEEKLY',
          'working_days': <int>[1],
        },
      })) as Json;
      routeId = '${(round['route_profile'] as Json)['id']}';
      roundBuyer = await customer('PR$tag');
      await admin.write('PUT', '$t/${round['id']}/customers', <String, dynamic>{
        'customer_ids': <String>['${roundBuyer['id']}'],
      });
      await admin.write('PUT', '$t/${round['id']}/salesmen', <String, dynamic>{
        'assignments': <Json>[
          <String, dynamic>{'salesman_id': salesmanId, 'is_primary': true},
        ],
      });
    }
    final Json buyerA = await customer('PA$tag');
    final Json buyerB = await customer('PB$tag');
    final Json buyerC = await customer('PC$tag', paper: 'HALF');

    // Bills typed alone: the order and note stages are off while they are
    // made, and put back straight after.
    final Json stages = (await admin.get(_workflow)) as Json;
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
    Future<Json> bill(Json buyer, List<Json> lines, {Json? extra}) async {
      final Json made = (await admin.write('POST', '/api/v1/sales-invoices',
          <String, dynamic>{
        'customer_id': buyer['id'],
        'branch_id': branch['id'],
        'invoice_date': _today(),
        'lines': <Json>[
          for (int i = 0; i < lines.length; i++)
            <String, dynamic>{
              'line_number': i + 1,
              'warehouse_id': warehouse['id'],
              ...lines[i],
            },
        ],
        ...?extra,
      })) as Json;
      return (await admin.write('POST',
          '/api/v1/sales-invoices/${made['id']}/approve', <String, dynamic>{})) as Json;
    }

    Json one(Json p, [num qty = 1]) => <String, dynamic>{
          'product_id': p['id'],
          'current_invoice_quantity': '$qty',
        };
    late Json billShort, billLong, billB, billC;
    Json? billFull;
    await admin.write('PUT', _workflow, <String, dynamic>{
      ...stagesBack,
      'sales_order_stage': false,
      'delivery_note_stage': false,
    });
    try {
      billShort = await bill(buyerA, <Json>[one(plain)]);
      billB = await bill(buyerB, <Json>[one(plain)]);
      billC = await bill(buyerC, <Json>[one(plain)]);
      billLong = await bill(buyerA, <Json>[for (int i = 0; i < 60; i++) one(plain)]);
      if (isAdmin) {
        billFull = await bill(roundBuyer!, <Json>[
          <String, dynamic>{...one(withMfg!, 4), 'free_quantity': '1'},
          one(noMfg!, 6),
        ], extra: <String, dynamic>{
          'salesman_id': salesmanId,
          'route_id': routeId,
        });
      }
    } finally {
      await admin.write('PUT', _workflow, stagesBack);
    }
    String no(Json b) => '${b['invoice_number']}';
    log.info('masters', 'tag $tag; bills short ${no(billShort)}, long '
        '${no(billLong)}, B ${no(billB)}, C ${no(billC)}'
        '${billFull == null ? '' : ', full ${no(billFull)}'}');

    // The firm's template as found, put back whatever the screens did.
    final Json heldTemplate = await template();
    final Json templateBack = <String, dynamic>{
      for (final MapEntry<String, dynamic> e in heldTemplate.entries)
        if (!<String>['id', 'document_type', 'is_customised'].contains(e.key))
          e.key: e.value,
    };

    // -- Moving about --------------------------------------------------------
    Future<void> openBills() async {
      await leave(tester);
      await openMenu(tester, 'sell', 'salesInvoices/sales-invoices');
      await pumpFor(tester, const Duration(seconds: 1));
    }

    Future<void> chooseBill(Json b) async {
      await openBills();
      await searchList(tester, no(b));
      await pickRow(tester, no(b));
    }

    Future<void> openSettings() async {
      await openBills();
      await tapButtonOrMenu(tester, 'Print settings');
      await pumpUntil(tester, find.textContaining('Print settings'),
          waitingFor: 'the Print settings dialog');
      await pumpUntil(tester, find.text('Paper'), waitingFor: 'the settings');
      await pumpFor(tester, const Duration(milliseconds: 500));
    }

    DropdownButton<String>? paperBox() {
      for (final Element e
          in find.byWidgetPredicate((Widget w) => w is DropdownButton<String>).evaluate()) {
        final DropdownButton<String> d = e.widget as DropdownButton<String>;
        if ((d.items ?? <DropdownMenuItem<String>>[])
            .any((DropdownMenuItem<String> i) => i.value == 'THERMAL80')) {
          return d;
        }
      }
      return null;
    }

    DropdownButton<int>? copiesBox() {
      final Finder f = find.byWidgetPredicate((Widget w) => w is DropdownButton<int>);
      return f.evaluate().isEmpty ? null : tester.widget<DropdownButton<int>>(f.first);
    }

    TextField? termsBox() {
      final Finder f = fieldLabelled('Terms');
      return f.evaluate().isEmpty ? null : tester.widget<TextField>(f.first);
    }

    Future<void> choosePaper(String label) async {
      final Finder box = find.byWidgetPredicate((Widget w) =>
          w is DropdownButton<String> &&
          (w.items ?? <DropdownMenuItem<String>>[])
              .any((DropdownMenuItem<String> i) => i.value == 'THERMAL80'));
      await tester.ensureVisible(box.first);
      await pumpFor(tester, const Duration(milliseconds: 300));
      await tester.tap(box.first);
      await pumpFor(tester, const Duration(milliseconds: 700));
      await tester.tap(find.text(label).last);
      await pumpFor(tester, const Duration(milliseconds: 700));
    }

    /// Save in the settings dialog; returns what the screen said.
    Future<String> saveSettings() async {
      final Set<String> seen = <String>{};
      await tapDialogButton(tester, 'Save');
      final DateTime end = DateTime.now().add(const Duration(seconds: 5));
      while (DateTime.now().isBefore(end)) {
        await tester.pump(const Duration(milliseconds: 200));
        final String n = noticeText(tester);
        if (n.isNotEmpty && !n.contains('Print settings —')) seen.add(n);
      }
      return seen.join(' || ');
    }

    /// The paper box, as it stands: title, sentence, choice offered, chosen.
    ({String text, bool choice, String? chosen}) paperPrompt() {
      final Finder seg = find.byWidgetPredicate((Widget w) => w is SegmentedButton<String>);
      return (
        text: dialogText(tester),
        choice: seg.evaluate().isNotEmpty,
        chosen: seg.evaluate().isEmpty
            ? null
            : tester.widget<SegmentedButton<String>>(seg.first).selected.first,
      );
    }

    /// Press Print on the chosen bill. Returns the prompt it opened (or null
    /// when none opened within a few seconds).
    Future<({String text, bool choice, String? chosen})?> pressPrint() async {
      await tapButtonOrMenu(tester, 'Print');
      final DateTime end = DateTime.now().add(const Duration(seconds: 8));
      while (DateTime.now().isBefore(end)) {
        await tester.pump(const Duration(milliseconds: 200));
        if (find.byType(AlertDialog).evaluate().isNotEmpty &&
            find.textContaining('prints on').evaluate().isNotEmpty) {
          await pumpFor(tester, const Duration(milliseconds: 400));
          return paperPrompt();
        }
        if (find.byType(SnackBar).evaluate().isNotEmpty) return null;
      }
      return null;
    }

    /// Wait for a print to reach the printer after [count] earlier ones.
    Future<_Printed?> printedAfter(int count) async {
      final DateTime end = DateTime.now().add(const Duration(seconds: 25));
      while (DateTime.now().isBefore(end)) {
        await tester.pump(const Duration(milliseconds: 200));
        if (printer.printed.length > count) {
          await pumpFor(tester, const Duration(milliseconds: 600));
          return printer.printed.last;
        }
      }
      return null;
    }

    String pagesSaid(_Printed? p) =>
        p == null ? 'nothing printed' : '${p.pages.length} pages ${p.pages.toSet()}';

    bool allOf(_Printed? p, String kind) =>
        p != null && p.pages.isNotEmpty && p.pages.every((String k) => k == kind);

    final String terms1 = 'Goods once sold are not taken back $tag.';
    final String terms2 = 'Subject to Chennai jurisdiction.';

    try {
      // =====================================================================
      // Firm admin
      // =====================================================================
      if (isAdmin) {
        if (_runs('settings') || _runs('half')) {
          await log.step('TC-SELL-099 1 / PRT-S1 Print settings read as the '
              'server holds them', () async {
            final int errs = appErrors.length;
            final Json held = await template();
            await openSettings();
            final DropdownButton<String>? paper = paperBox();
            final DropdownButton<int>? copies = copiesBox();
            log.saw = 'screen paper ${paper?.value}, copies ${copies?.value}, '
                'terms "${termsBox()?.controller?.text}"; server paper '
                '${held['page_size']}, copies ${(held['copy_labels'] as List<dynamic>).length}, '
                'terms ${held['terms']}';
            final List<String> faults = <String>[
              if (paper?.value != held['page_size']) 'paper differs',
              if (copies?.value != (held['copy_labels'] as List<dynamic>).length)
                'copies differ',
              if ((termsBox()?.controller?.text ?? '') != (held['terms'] ?? ''))
                'terms differ',
            ];
            if (faults.isNotEmpty) throw StateError(faults.join('; '));
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });

          await log.step('TC-SELL-099 1 / TC-SELL-112 1 Half page and two lines '
              'of terms are saved', () async {
            final int errs = appErrors.length;
            final Json held = await template();
            await openSettings();
            // What the dialog holds before anything is changed: a save
            // writes every box back, so a box it failed to fill is a box the
            // save empties.
            final int? copiesShown = copiesBox()?.value;
            final Finder declarationBox = fieldLabelled('Declaration');
            final String declarationShown = declarationBox.evaluate().isEmpty
                ? '(no box)'
                : tester.widget<TextField>(declarationBox.first).controller?.text ?? '';
            final List<String> problem = textOnScreen(tester)
                .where((String t) => RegExp(r'reach|could not|failed|error',
                        caseSensitive: false)
                    .hasMatch(t))
                .toList();
            await choosePaper('Half page (half of A4)');
            final bool note = find
                .byKey(const ValueKey<String>('print-half-page-note'))
                .evaluate()
                .isNotEmpty;
            final bool layout = find
                .byKey(const ValueKey<String>('print-bill-layout'))
                .evaluate()
                .isNotEmpty;
            final Finder terms = fieldLabelled('Terms');
            await tester.ensureVisible(terms.first);
            await tester.enterText(terms.first, '$terms1\n$terms2');
            await pumpFor(tester, const Duration(milliseconds: 400));
            final String said = await saveSettings();
            final bool closed = find.text('Paper').evaluate().isEmpty;
            final Json after = await template();
            final int heldCopies = (held['copy_labels'] as List<dynamic>).length;
            final int afterCopies = (after['copy_labels'] as List<dynamic>).length;
            log.saw = 'dialog opened with copies $copiesShown, declaration '
                '"${declarationShown.length > 30 ? declarationShown.substring(0, 30) : declarationShown}", '
                'problem text $problem; half-page note shown=$note; Bill layout offered=$layout; '
                'said "$said"; closed=$closed; server paper ${after['page_size']}, '
                'terms "${after['terms']}", copies $heldCopies -> $afterCopies, '
                'declaration kept ${after['declaration'] == held['declaration']}';
            final List<String> faults = <String>[
              if (afterCopies != heldCopies) 'the save changed the copies',
              if (after['declaration'] != held['declaration'])
                'the save changed the declaration',
              if (!note) 'no line saying a long bill goes to a full page',
              if (layout) 'Bill layout offered on a half page',
              if (!said.contains('Print settings saved')) 'no saved notice',
              if (after['page_size'] != 'HALF') 'server paper not HALF',
              if (after['terms'] != '$terms1\n$terms2') 'server terms differ',
            ];
            if (faults.isNotEmpty) {
              throw StateError('${faults.join('; ')} [${log.saw}]');
            }
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });

          await log.step('PRT-S2 reopened, the paper and the terms read back',
              () async {
            final int errs = appErrors.length;
            await openSettings();
            final String? paper = paperBox()?.value;
            final String typed = termsBox()?.controller?.text ?? '';
            log.saw = 'paper $paper; terms "$typed"';
            await leave(tester);
            if (paper != 'HALF') throw StateError('paper reads $paper');
            if (typed != '$terms1\n$terms2') throw StateError('terms differ');
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
        }

        if (_runs('half')) {
          if ((await template())['page_size'] != 'HALF') {
            // A part run on its own: the screen part above did not run.
            await admin.write('PUT', _template,
                <String, dynamic>{...templateBack, 'page_size': 'HALF', 'terms': '$terms1\n$terms2'});
          }
          await log.step('TC-SELL-109 2 a short bill: the box names Half page, '
              'Full page offered; it prints on half pages', () async {
            final int errs = appErrors.length;
            final Json server = await paperOf('${billShort['id']}');
            await chooseBill(billShort);
            final ({String text, bool choice, String? chosen})? box =
                await pressPrint();
            final int before = printer.printed.length;
            if (box != null) await tapDialogButton(tester, 'Print');
            final _Printed? got = await printedAfter(before);
            final String notice = await watch(tester, seconds: 2, confirm: false);
            log.saw = 'box "${box?.text}", choice ${box?.choice}, chosen '
                '${box?.chosen}; server paper ${server['paper']}, may_choose '
                '${server['may_choose']}; printed ${pagesSaid(got)}; said "$notice"';
            final List<String> faults = <String>[
              if (box == null) 'no box',
              if (box != null && !box.text.contains('Print ${no(billShort)}'))
                'the box does not name the bill',
              if (box != null && !box.text.contains('prints on a Half page'))
                'the box does not say Half page',
              if (box != null && !box.text.contains("printer's tray"))
                'no word about the tray',
              if (box != null && (!box.choice || box.chosen != 'HALF'))
                'Half not chosen or no choice',
              if (!allOf(got, 'HALF')) 'not printed on half pages',
              if (server['paper'] != 'HALF') 'server says ${server['paper']}',
            ];
            if (faults.isNotEmpty) throw StateError(faults.join('; '));
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
          await leave(tester);

          await log.step('TC-SELL-109 3 the same bill switched to Full page '
              'for this print', () async {
            final int errs = appErrors.length;
            await chooseBill(billShort);
            final ({String text, bool choice, String? chosen})? box =
                await pressPrint();
            if (box == null) throw StateError('no box');
            await tester.tap(find.descendant(
                of: find.byType(AlertDialog), matching: find.text('Full page')));
            await pumpFor(tester, const Duration(milliseconds: 500));
            final String sentence = dialogText(tester);
            final int before = printer.printed.length;
            await tapDialogButton(tester, 'Print');
            final _Printed? got = await printedAfter(before);
            log.saw = 'after choosing Full: "$sentence"; printed ${pagesSaid(got)}';
            if (!sentence.contains('prints on a Full page')) {
              throw StateError('the sentence did not follow the choice');
            }
            if (!allOf(got, 'A4')) throw StateError('not printed on A4');
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
          await leave(tester);

          await log.step('TC-SELL-109 4 and 8: the box opens on Half page '
              'again; Cancel prints nothing and says nothing', () async {
            final int errs = appErrors.length;
            await chooseBill(billShort);
            final ({String text, bool choice, String? chosen})? box =
                await pressPrint();
            final int before = printer.printed.length;
            if (box != null) await tapDialogButton(tester, 'Cancel');
            final String said = await watch(tester, seconds: 3, confirm: false);
            log.saw = 'opens on ${box?.chosen}; after Cancel printed '
                '${printer.printed.length - before}, said "$said"';
            if (box?.chosen != 'HALF') throw StateError('opened on ${box?.chosen}');
            if (printer.printed.length != before) throw StateError('printed');
            if (said.isNotEmpty) throw StateError('a message was shown');
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
          await leave(tester);

          await log.step('TC-SELL-099 4 customer B set to Full page on the '
              'customer screen', () async {
            final int errs = appErrors.length;
            await openArea(tester, 'masters', 'masters/customers');
            await searchList(tester, '${buyerB['name']}');
            await pickRow(tester, '${buyerB['name']}');
            if (buttonState(tester, 'Edit') == 'enabled') {
              await tapButton(tester, 'Edit');
            } else {
              await tester.tap(find.byTooltip('Edit').first);
              await pumpFor(tester, const Duration(seconds: 1));
            }
            // The phase 2 editor is one page of sections; the box is under
            // Money.
            final Finder box =
                find.byKey(const ValueKey<String>('customer-bill-page-size'));
            await pumpUntil(tester, box, waitingFor: 'the Bill paper box');
            final bool helper = screenHas(tester,
                'Read where the firm prints its bills on half pages');
            final bool startsFirm = screenHas(tester, "Firm's setting");
            await tester.ensureVisible(box);
            await pumpFor(tester, const Duration(milliseconds: 500));
            await tester.tap(box);
            await pumpFor(tester, const Duration(milliseconds: 700));
            await tester.tap(find.text('Full page (A4)').last);
            await pumpFor(tester, const Duration(milliseconds: 500));
            final bool shows = screenHas(tester, 'Full page (A4)');
            await tapButton(tester, 'Save customer');
            final String said = await watch(tester, seconds: 4, confirm: false);
            final Json after = (await admin.get('/api/v1/customers/${buyerB['id']}')) as Json;
            log.saw = 'helper shown=$helper; started on Firm\'s setting='
                '$startsFirm; box then shows Full page (A4)=$shows; said '
                '"$said"; server '
                'bill_page_size ${after['bill_page_size']}';
            await leave(tester);
            if (after['bill_page_size'] != 'A4') throw StateError('not saved');
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });

          await log.step('TC-SELL-109 5 B\'s bill: Full page because the '
              'customer is set so; Half offered; prints on A4', () async {
            final int errs = appErrors.length;
            final Json server = await paperOf('${billB['id']}');
            await chooseBill(billB);
            final ({String text, bool choice, String? chosen})? box =
                await pressPrint();
            final int before = printer.printed.length;
            if (box != null) await tapDialogButton(tester, 'Print');
            final _Printed? got = await printedAfter(before);
            log.saw = 'box "${box?.text}", choice ${box?.choice}, chosen '
                '${box?.chosen}; server ${server['paper']} customer '
                '${server['customer_paper']}; printed ${pagesSaid(got)}';
            final List<String> faults = <String>[
              if (box == null) 'no box',
              if (box != null && !box.text.contains("customer's bills are set to a full page"))
                'does not say the customer is on a full page',
              if (box != null && (!box.choice || box.chosen != 'A4'))
                'Full not chosen or no choice',
              if (!allOf(got, 'A4')) 'not printed on A4',
            ];
            if (faults.isNotEmpty) throw StateError(faults.join('; '));
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
          await leave(tester);

          await log.step('TC-SELL-109 6 B\'s bill switched to Half page',
              () async {
            final int errs = appErrors.length;
            await chooseBill(billB);
            final ({String text, bool choice, String? chosen})? box =
                await pressPrint();
            if (box == null) throw StateError('no box');
            await tester.tap(find.descendant(
                of: find.byType(AlertDialog), matching: find.text('Half page')));
            await pumpFor(tester, const Duration(milliseconds: 500));
            final int before = printer.printed.length;
            await tapDialogButton(tester, 'Print');
            final _Printed? got = await printedAfter(before);
            log.saw = 'printed ${pagesSaid(got)}';
            if (!allOf(got, 'HALF')) throw StateError('not on half pages');
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
          await leave(tester);

          await log.step('TC-SELL-099 3 / TC-SELL-109 7 a sixty-line bill: Full '
              'page by itself, no choice', () async {
            final int errs = appErrors.length;
            final Json server = await paperOf('${billLong['id']}');
            await chooseBill(billLong);
            final ({String text, bool choice, String? chosen})? box =
                await pressPrint();
            final int before = printer.printed.length;
            if (box != null) await tapDialogButton(tester, 'Print');
            final _Printed? got = await printedAfter(before);
            log.saw = 'box "${box?.text}", choice ${box?.choice}; server '
                '${server['paper']} fits_half ${server['fits_half_page']}; '
                'printed ${pagesSaid(got)}';
            final List<String> faults = <String>[
              if (box == null) 'no box',
              if (box != null && !box.text.contains('too long for half a page'))
                'does not say it is too long',
              if (box != null && box.choice) 'a choice is offered',
              if (!allOf(got, 'A4')) 'not printed on A4',
            ];
            if (faults.isNotEmpty) throw StateError(faults.join('; '));
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
          await leave(tester);

          await log.step('TC-SELL-112 4 the round\'s bill on half pages: '
              'Market, Total quantity, terms; no Mfg', () async {
            final int errs = appErrors.length;
            await chooseBill(billFull!);
            final ({String text, bool choice, String? chosen})? box =
                await pressPrint();
            final int before = printer.printed.length;
            if (box != null) await tapDialogButton(tester, 'Print');
            final _Printed? got = await printedAfter(before);
            final List<String> text = got?.text ?? <String>[];
            final String joined = text.join(' | ');
            final int q = text.indexWhere((String s) => s.startsWith('Total quantity'));
            log.saw = 'box chosen ${box?.chosen}; printed ${pagesSaid(got)}; '
                'Market ${text.contains(marketName)}, Total quantity '
                '${q < 0 ? 'absent' : text.skip(q).take(4).join(' ')}, terms '
                '${joined.contains(terms1)}, Mfg ${text.contains('Mfg')}';
            final List<String> faults = <String>[
              if (!allOf(got, 'HALF')) 'not on half pages',
              if (!text.contains(marketName)) 'no Market',
              if (q < 0) 'no Total quantity',
              if (!joined.contains(terms1) || !joined.contains(terms2)) 'terms missing',
              if (text.contains('Mfg')) 'a Mfg column on the half page',
            ];
            if (faults.isNotEmpty) throw StateError('${faults.join('; ')} [$joined]');
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
          await leave(tester);
        }

        if (_runs('full')) {
          await log.step('TC-SELL-099 6 / PRT-S3 Paper set back to A4 on the '
              'screen', () async {
            final int errs = appErrors.length;
            await openSettings();
            await choosePaper('A4');
            final bool note = find
                .byKey(const ValueKey<String>('print-half-page-note'))
                .evaluate()
                .isNotEmpty;
            final bool layout = find
                .byKey(const ValueKey<String>('print-bill-layout'))
                .evaluate()
                .isNotEmpty;
            final String said = await saveSettings();
            final Json after = await template();
            log.saw = 'half-page note=$note, Bill layout offered=$layout; said '
                '"$said"; server paper ${after['page_size']}, terms kept '
                '${after['terms'] == '$terms1\n$terms2'}';
            if (after['page_size'] != 'A4') throw StateError('server not A4');
            if (note) throw StateError('the half-page line still shows');
            if (!layout) throw StateError('no Bill layout on A4');
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
          if ((await template())['page_size'] != 'A4') {
            await admin.write('PUT', _template, <String, dynamic>{
              ...templateBack,
              'page_size': 'A4',
              'terms': '$terms1\n$terms2',
            });
          }

          await log.step('TC-SELL-109 1 / TC-SELL-099 7 a full-page firm: the '
              'customer on Half page is not read, no box', () async {
            final int errs = appErrors.length;
            final Json server = await paperOf('${billC['id']}');
            await chooseBill(billC);
            final int before = printer.printed.length;
            final ({String text, bool choice, String? chosen})? box =
                await pressPrint();
            if (box != null) await tapDialogButton(tester, 'Cancel');
            final _Printed? got = box == null ? await printedAfter(before) : null;
            log.saw = 'box ${box == null ? 'none' : '"${box.text}"'}; server '
                'paper ${server['paper']}, customer_paper '
                '${server['customer_paper']}, may_choose ${server['may_choose']}; '
                'printed ${pagesSaid(got)}';
            final List<String> faults = <String>[
              if (box != null) 'a box opened',
              if (!allOf(got, 'A4')) 'not printed on A4',
              if (server['customer_paper'] != null) 'server read the customer',
              if (server['may_choose'] == true) 'server offers a choice',
            ];
            if (faults.isNotEmpty) throw StateError(faults.join('; '));
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
          await leave(tester);

          await log.step('TC-SELL-112 3 / TC-SELL-117 the round\'s bill on A4: '
              'Mfg, Total quantity, terms, Market, Order By', () async {
            final int errs = appErrors.length;
            final Json whole = await admin.one('sales-invoices', '${billFull!['id']}');
            final List<dynamic> lines = whole['lines'] as List<dynamic>;
            final double qty = lines.fold<double>(
                0, (double s, dynamic l) => s + num2((l as Json)['current_invoice_quantity'] ?? l['quantity']));
            await chooseBill(billFull!);
            final bool onScreen = screenHas(tester, no(billFull!));
            final int before = printer.printed.length;
            final ({String text, bool choice, String? chosen})? box =
                await pressPrint();
            if (box != null) await tapDialogButton(tester, 'Print');
            final _Printed? got = await printedAfter(before);
            final List<String> text = got?.text ?? <String>[];
            // The first copy only: each copy repeats the page.
            final int end = text.indexOf('DUPLICATE FOR TRANSPORTER');
            final List<String> first =
                end > 0 ? text.sublist(0, end) : text;
            final String joined = first.join(' | ');
            final int ob = first.indexOf('Order By');
            final int mk = first.indexOf('Market');
            final int q = first.indexWhere((String s) => s.startsWith('Total quantity'));
            final int b1 = first.indexOf('MF$tag');
            final int b2 = first.indexOf('NM$tag');
            final String after1 = b1 < 0 ? '' : first.skip(b1 + 1).take(2).join(' ');
            final String after2 = b2 < 0 ? '' : first.skip(b2 + 1).take(1).join(' ');
            final String totalRow = q < 0 ? '' : first.skip(q).take(3).join(' ');
            final List<String> termsAt = <String>[
              for (int i = 0; i < first.length; i++)
                if (first[i].contains(terms1) || first[i].contains(terms2)) '$i',
            ];
            log.saw = 'row on screen=$onScreen; box ${box == null ? 'none' : 'opened'}; '
                'printed ${pagesSaid(got)}; Mfg column ${first.contains('Mfg')}; '
                'line 1 after batch "$after1", line 2 after batch "$after2"; '
                'total row "$totalRow" (server lines sum $qty, free '
                '${whole['total_free_quantity']}); terms at $termsAt of '
                '${first.length}, TERMS heading ${first.contains('TERMS')}; '
                'Market "${mk < 0 ? '' : first[mk + 1]}"; Order By '
                '"${ob < 0 ? '' : first[ob + 1]}"';
            final List<String> faults = <String>[
              if (box != null) 'a box opened on an A4 firm',
              if (!allOf(got, 'A4')) 'not on A4',
              if (!first.contains('Mfg')) 'no Mfg column',
              if (!after1.startsWith('01/26')) 'line 1 Mfg is not 01/26',
              if (!RegExp(r'^\d{4}-\d{2}-\d{2}').hasMatch(after2))
                'line 2 has something between batch and expiry',
              if (q < 0) 'no Total quantity row',
              if (q >= 0 && !totalRow.contains(qty.toStringAsFixed(0))) 'total quantity is not $qty',
              if (q >= 0 && !totalRow.contains('1 free')) 'the free goods are not named beside it',
              if (termsAt.length < 2) 'the terms are not printed',
              if (mk < 0 || first[mk + 1] != marketName) 'Market is not $marketName',
              if (ob < 0 || first[ob + 1] != salesmanName) 'Order By is not $salesmanName',
            ];
            if (faults.isNotEmpty) throw StateError('${faults.join('; ')} [$joined]');
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
          await leave(tester);

          await log.step('TC-SELL-117 / TC-SELL-112 5 a bill with no salesman, '
              'no round, no batch: no Order By, no Market, no Mfg', () async {
            final int errs = appErrors.length;
            await chooseBill(billShort);
            final int before = printer.printed.length;
            final ({String text, bool choice, String? chosen})? box =
                await pressPrint();
            if (box != null) await tapDialogButton(tester, 'Print');
            final _Printed? got = await printedAfter(before);
            final List<String> text = got?.text ?? <String>[];
            log.saw = 'box ${box == null ? 'none' : 'opened'}; printed '
                '${pagesSaid(got)}; Order By ${text.contains('Order By')}, '
                'Market ${text.contains('Market')}, Mfg ${text.contains('Mfg')}, '
                'Total quantity ${text.any((String s) => s.startsWith('Total quantity'))}';
            final List<String> faults = <String>[
              if (!allOf(got, 'A4')) 'not on A4',
              if (text.contains('Order By')) 'Order By printed',
              if (text.contains('Market')) 'Market printed',
              if (text.contains('Mfg')) 'Mfg printed',
            ];
            if (faults.isNotEmpty) throw StateError(faults.join('; '));
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
          await leave(tester);
        }
        log.skip('TC-SELL-099 5 / TC-SELL-109 9 Print selected',
            'the bulk run is the server\'s check and print_selected_test.dart');
        log.skip('TC-SELL-117 trade layout, deleted salesman, roll',
            'only the standard full page and the half page were printed');
      }

      // =====================================================================
      // Viewer
      // =====================================================================
      if (!isAdmin) {
        await admin.write('PUT', _template, <String, dynamic>{
          ...templateBack,
          'page_size': 'HALF',
          'terms': '$terms1\n$terms2',
        });

        await log.step('PRT-V1 Print settings: read, Save off, the reason in '
            'words; a save over HTTP is refused', () async {
          final int errs = appErrors.length;
          final Json held = await template();
          await openSettings();
          final String? paper = paperBox()?.value;
          final bool paperOff = paperBox()?.onChanged == null;
          final TextField? terms = termsBox();
          final String save = buttonState(tester, 'Save');
          final String preview = buttonState(tester, 'Preview');
          final List<String> words = textOnScreen(tester)
              .where((String t) => RegExp(r'permission|cannot|can only|read only|may not|role',
                      caseSensitive: false)
                  .hasMatch(t))
              .toList();
          await leave(tester);
          final ({int status, String text}) put = await me.attempt('PUT', _template,
              <String, dynamic>{...templateBack, 'page_size': 'A4'});
          final Json after = await template();
          log.saw = 'paper $paper (server ${held['page_size']}), paper box '
              'off=$paperOff, terms box enabled=${terms?.enabled}, Save $save, '
              'Preview $preview; words on screen $words; HTTP PUT ${put.status} '
              '"${put.text.length > 160 ? put.text.substring(0, 160) : put.text}"; '
              'server paper after ${after['page_size']}';
          final List<String> faults = <String>[
            if (paper != held['page_size']) 'paper differs',
            if (!paperOff || terms?.enabled != false) 'a box can be changed',
            if (save == 'enabled') 'Save is offered',
            if (put.status != 403) 'HTTP PUT answered ${put.status}',
            if (after['page_size'] != held['page_size']) 'the setting moved',
            if (words.isEmpty) 'nothing on screen says why it cannot be saved',
          ];
          if (faults.isNotEmpty) {
            throw StateError('${faults.join('; ')} [${log.saw}]');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });

        await log.step('PRT-V2 / TC-SELL-109 2-3 the viewer prints: the box '
            'names Half page, Full page chosen prints on A4', () async {
          final int errs = appErrors.length;
          await chooseBill(billShort);
          final ({String text, bool choice, String? chosen})? box =
              await pressPrint();
          if (box == null) throw StateError('no box');
          await tester.tap(find.descendant(
              of: find.byType(AlertDialog), matching: find.text('Full page')));
          await pumpFor(tester, const Duration(milliseconds: 500));
          final int before = printer.printed.length;
          await tapDialogButton(tester, 'Print');
          final _Printed? got = await printedAfter(before);
          final String said = await watch(tester, seconds: 2, confirm: false);
          log.saw = 'box "${box.text}", chosen ${box.chosen}; printed '
              '${pagesSaid(got)}; said "$said"';
          if (!box.text.contains('prints on a Half page') || box.chosen != 'HALF') {
            throw StateError('the box did not open on Half page');
          }
          if (!allOf(got, 'A4')) throw StateError('not on A4');
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await leave(tester);

        await log.step('PRT-V3 a long bill as the viewer: Full page, no choice',
            () async {
          final int errs = appErrors.length;
          await chooseBill(billLong);
          final ({String text, bool choice, String? chosen})? box =
              await pressPrint();
          final int before = printer.printed.length;
          if (box != null) await tapDialogButton(tester, 'Print');
          final _Printed? got = await printedAfter(before);
          log.saw = 'box "${box?.text}", choice ${box?.choice}; printed ${pagesSaid(got)}';
          if (box == null || box.choice || !box.text.contains('too long')) {
            throw StateError('not the too-long box');
          }
          if (!allOf(got, 'A4')) throw StateError('not on A4');
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await leave(tester);
      }
    } finally {
      await admin.write('PUT', _template, templateBack);
      log.info('template', 'put back as found (paper ${templateBack['page_size']})');
    }

    log.info('errors', 'app errors and overflows this run: ${appErrors.length}');
    log.finish();
  });
}
