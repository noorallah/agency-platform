// L7 step 8: the offers block in the side panel of the sales line editors.
//
// `docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md` section 4. The block shows
// what the last preview listed for the line the cursor is on; a tick sends
// the keys that show ticked as the line's `offer_choice` and prices the
// document again on the editor's own 350 ms timer. Nothing else calls the
// server: moving between lines asks nothing, typing asks once the typing
// pauses, and an untouched line never carries `offer_choice`.
//
// The figures are the server's own (`serverPricing`); only the candidates,
// which those kept answers do not list, are added here.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/quotation.dart';
import 'package:agency_desktop/ui/quotations/quotation_editor_dialog.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/sales/sales_order_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/first_line.dart';
import 'support/server_pricing.dart';

/// [answer] with each string value in [ids] replaced: the kept answers name
/// their records by tokens (`id-7`), the screens by the test's own ids.
Json _renamed(Json answer, Map<String, String> ids) {
  Object? walk(Object? value) {
    if (value is Map) {
      return <String, dynamic>{
        for (final MapEntry<dynamic, dynamic> entry in value.entries)
          '${entry.key}': walk(entry.value),
      };
    }
    if (value is List) return [for (final Object? item in value) walk(item)];
    if (value is String && ids.containsKey(value)) return ids[value];
    return value;
  }

  return walk(answer)! as Json;
}

Json _candidate(
  String key,
  String code, {
  String source = 'promotion',
  String sentence = '',
  String? percent,
  String? free,
  String worth = '0',
  bool applied = false,
  bool available = true,
  String? reason,
  String? needsMore,
  String? thenGives,
  Json? partShare,
}) =>
    <String, dynamic>{
      'key': key,
      'source': source,
      'code': code,
      'name': code,
      'gives': <String, dynamic>{
        'kind': percent != null ? 'PERCENT' : 'FREE_GOODS',
        'percent': percent,
        'free_quantity': free,
        'sentence': sentence,
      },
      'worth': worth,
      'applied': applied,
      'chosen': false,
      'combines': true,
      'available': available,
      'reason': reason,
      'needs_more': needsMore,
      'then_gives': thenGives,
      'part_share': partShare,
      'funded_by': null,
    };

/// What the first line could take, as the design's table lists it.
List<Json> _offers() => <Json>[
      _candidate('g-tea5', 'TEA-5',
          sentence: '5% off', percent: '5', worth: '25.0000', applied: true),
      _candidate('pl-city', 'CITY',
          source: 'price_list',
          sentence: '4%',
          percent: '4',
          worth: '20.0000',
          reason: 'an offer gives the discount'),
      _candidate('g-tea11', 'TEA-11',
          sentence: '11 + 1 free',
          free: '1',
          reason: 'Nothing earned on this line yet.',
          partShare: <String, dynamic>{
            'charged_quantity': '4.5833',
            'free_quantity': '0.4167',
          }),
      _candidate('g-tea24', 'TEA-24',
          sentence: '24 + 3 free',
          free: '3',
          available: false,
          reason: '13 more to earn it.',
          needsMore: '13.0000',
          thenGives: '3 free'),
    ];

/// The second line's: one offer, so the panel visibly follows the cursor.
List<Json> _otherOffers() => <Json>[
      _candidate('g-dust2', 'DUST-2',
          sentence: '2% off', percent: '2', worth: '5.6000', applied: true),
    ];

/// A Quotation priced by the server's kept answer for two lines, with the
/// candidates added; [refuse] is said on every line sent with a choice.
class _QuotationServer {
  final List<Json> asked = <Json>[];
  String? refuse;

  Future<QuotationPreviewRecord> preview(Json draft) async {
    asked.add(draft);
    final Json answer = _renamed(
      serverPricing('quotation_two_lines_preview'),
      <String, String>{'id-7': 'p1', 'id-9': 'p2', 'id-3': 'c1'},
    );
    final List<dynamic> sent = draft['lines'] as List<dynamic>;
    final List<dynamic> lines = answer['lines'] as List<dynamic>;
    for (int at = 0; at < lines.length; at += 1) {
      final Json line = lines[at] as Json;
      line['candidates'] = at == 0 ? _offers() : _otherOffers();
      final bool chose = at < sent.length &&
          (sent[at] as Json)['offer_choice'] != null;
      line['choice_refused'] = chose ? refuse : null;
    }
    return QuotationPreviewRecord.fromJson(answer);
  }
}

Future<void> _pumpQuotation(
  WidgetTester tester,
  _QuotationServer server, {
  bool mayChoose = true,
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: QuotationEditorDialog(
          customers: [
            Customer.fromJson({
              'id': 'c1',
              'code': 'C-0102',
              'name': 'Sri Murugan Stores',
              'display_name': 'Sri Murugan Stores',
            }),
          ],
          products: [
            Product.fromJson({
              'id': 'p1',
              'code': 'P-1002',
              'name': 'Tata Salt 1kg',
              'selling_price': '100.00',
            }),
            Product.fromJson({
              'id': 'p2',
              'code': 'P-2002',
              'name': 'Tea Dust 250g',
              'selling_price': '40.00',
            }),
          ],
          branches: [
            BranchRecord.fromJson({
              'id': 'ho',
              'code': 'HO',
              'name': 'Head office',
              'display_name': 'Head office',
              'is_default': true,
            }),
          ],
          warehouses: [
            WarehouseRecord.fromJson({
              'id': 'w1',
              'code': 'MAIN',
              'name': 'Main',
              'display_name': 'Main',
              'branch_id': 'ho',
              'is_default': true,
            }),
          ],
          today: DateTime(2026, 9, 26),
          mayChooseOffers: mayChoose,
          preview: server.preview,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('quotation-customer')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Sri Murugan').last);
  await tester.pumpAndSettle();
  await fillFirstLine(tester,
      document: 'quotation', product: 'Tata Salt', quantity: '5');
  await _settle(tester);
}

/// Let the 350 ms preview timer run and its answer land.
Future<void> _settle(WidgetTester tester) async {
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Finder _box(String row, int index, int box) => find
    .descendant(
      of: find.byKey(ValueKey<String>('$row-$index')),
      matching: find.byType(EditableText),
    )
    .at(box);

Future<void> _addSecondQuotationLine(WidgetTester tester) async {
  await tester.tap(find.textContaining('+ add a'));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('quotation-line-product-1')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Tea Dust').last);
  await tester.pumpAndSettle();
  await tester.enterText(_box('quotation-line', 1, 1), '7');
  await _settle(tester);
}

Future<void> _tick(WidgetTester tester, String prefix, String key) async {
  final Finder box = find.byKey(ValueKey<String>('$prefix-$key-tick'));
  await tester.ensureVisible(box);
  await tester.tap(box);
  await tester.pump();
}

Json _sentLine(List<Json> asked, int index) =>
    (asked.last['lines'] as List<dynamic>)[index] as Json;

void main() {
  group('the quotation', () {
    testWidgets('the block shows what the preview listed for the line',
        (tester) async {
      final _QuotationServer server = _QuotationServer();
      await _pumpQuotation(tester, server);
      expect(server.asked, isNotEmpty);
      expect(find.byKey(const ValueKey('quotation-offer-block')),
          findsOneWidget);
      expect(find.text('OFFERS AND DISCOUNTS'), findsOneWidget);
      expect(find.text('TEA-5, 5% off'), findsOneWidget);
      expect(find.text('Price list CITY, 4%'), findsOneWidget);
      expect(find.text('an offer gives the discount'), findsOneWidget);
      expect(find.text('TEA-24, 24 + 3 free'), findsOneWidget);
      expect(find.text('13 more to get 3 free'), findsOneWidget);
      expect(find.text('applied'), findsOneWidget);
      // A hint row has no tick box.
      expect(find.byKey(const ValueKey('quotation-offer-g-tea24-tick')),
          findsNothing);
      // And the hint under the quantity.
      expect(
        tester
            .widget<Text>(
                find.byKey(const ValueKey('quotation-line-offer-hint-0')))
            .data,
        '13 more: 3 free',
      );
      // An untouched line sends no choice, so the server decides.
      expect(_sentLine(server.asked, 0).containsKey('offer_choice'), isFalse);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a tick sends the ticked keys and prices once more',
        (tester) async {
      final _QuotationServer server = _QuotationServer();
      await _pumpQuotation(tester, server);
      await _addSecondQuotationLine(tester);
      // Back to the first line, whose list arrived with the last preview.
      await tester.tap(find.descendant(
          of: find.byKey(const ValueKey('quotation-line-0')),
          matching: find.text('1')));
      await tester.pumpAndSettle();
      final int before = server.asked.length;
      await _tick(tester, 'quotation-offer', 'pl-city');
      // Nothing until the timer runs out, then exactly one.
      expect(server.asked.length, before);
      await _settle(tester);
      expect(server.asked.length, before + 1);
      expect(_sentLine(server.asked, 0)['offer_choice'], <String, dynamic>{
        'discount_from': 'pl-city',
        'offers': <String>['g-tea5'],
        'part_share': null,
      });
      // The other line was not touched and says nothing.
      expect(_sentLine(server.asked, 1).containsKey('offer_choice'), isFalse);
      // The tick holds after the answer.
      expect(
        tester
            .widget<Checkbox>(
                find.byKey(const ValueKey('quotation-offer-pl-city-tick')))
            .value,
        isTrue,
      );
    });

    testWidgets('moving between lines asks the server nothing',
        (tester) async {
      final _QuotationServer server = _QuotationServer();
      await _pumpQuotation(tester, server);
      await _addSecondQuotationLine(tester);
      final int before = server.asked.length;
      expect(find.text('DUST-2, 2% off'), findsOneWidget);
      await tester.tap(find.descendant(
          of: find.byKey(const ValueKey('quotation-line-0')),
          matching: find.text('1')));
      await _settle(tester);
      expect(find.text('TEA-5, 5% off'), findsOneWidget);
      expect(find.text('DUST-2, 2% off'), findsNothing);
      await tester.tap(find.descendant(
          of: find.byKey(const ValueKey('quotation-line-1')),
          matching: find.text('2')));
      await _settle(tester);
      expect(find.text('DUST-2, 2% off'), findsOneWidget);
      expect(server.asked.length, before);
    });

    testWidgets('typing asks once the typing pauses, not per keystroke',
        (tester) async {
      final _QuotationServer server = _QuotationServer();
      await _pumpQuotation(tester, server);
      final int before = server.asked.length;
      final Finder quantity = _box('quotation-line', 0, 1);
      for (final String text in <String>['1', '12', '120']) {
        await tester.enterText(quantity, text);
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(server.asked.length, before);
      await _settle(tester);
      expect(server.asked.length, before + 1);
      expect(_sentLine(server.asked, 0)['quantity'], '120');
    });

    testWidgets('without SALES_OFFER_CHOOSE the block is read-only',
        (tester) async {
      final _QuotationServer server = _QuotationServer();
      await _pumpQuotation(tester, server, mayChoose: false);
      expect(find.text('TEA-5, 5% off'), findsOneWidget);
      final Finder tick =
          find.byKey(const ValueKey('quotation-offer-pl-city-tick'));
      expect(tester.widget<Checkbox>(tick).onChanged, isNull);
      expect(find.byKey(const ValueKey('quotation-offer-g-tea11-part-share')),
          findsNothing);
      final int before = server.asked.length;
      await tester.tap(tick);
      await _settle(tester);
      expect(server.asked.length, before);
      // F6 and Space change nothing either.
      await tester.sendKeyEvent(LogicalKeyboardKey.f6);
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.sendKeyEvent(LogicalKeyboardKey.space);
      await _settle(tester);
      expect(server.asked.length, before);
      await tester.enterText(_box('quotation-line', 0, 1), '6');
      await _settle(tester);
      expect(_sentLine(server.asked, 0).containsKey('offer_choice'), isFalse);
    });

    testWidgets('Part share sets the quantity to what is charged',
        (tester) async {
      final _QuotationServer server = _QuotationServer();
      await _pumpQuotation(tester, server);
      final Finder button =
          find.byKey(const ValueKey('quotation-offer-g-tea11-part-share'));
      await tester.ensureVisible(button);
      expect(find.text('Part share: 4.5833 + 0.4167 free'), findsOneWidget);
      await tester.tap(button);
      await _settle(tester);
      expect(
          tester.widget<EditableText>(_box('quotation-line', 0, 1))
              .controller
              .text,
          '4.5833');
      final Json sent = _sentLine(server.asked, 0);
      expect(sent['quantity'], '4.5833');
      expect(sent.containsKey('free_quantity'), isFalse);
      expect((sent['offer_choice'] as Json)['part_share'], 'g-tea11');
      expect(find.text('0.4167 free from TEA-11'), findsOneWidget);
    });

    testWidgets('a choice the server refused is said on the line',
        (tester) async {
      final _QuotationServer server = _QuotationServer()
        ..refuse = 'Line 1: TEA-11 does not combine with TEA-5.';
      await _pumpQuotation(tester, server);
      await _tick(tester, 'quotation-offer', 'g-tea11');
      await _settle(tester);
      expect(
          (_sentLine(server.asked, 0)['offer_choice'] as Json)['offers'],
          <String>['g-tea5', 'g-tea11']);
      expect(find.byKey(const ValueKey('quotation-offer-refused')),
          findsOneWidget);
      expect(find.text('Line 1: TEA-11 does not combine with TEA-5.'),
          findsOneWidget);
      // Dropped before the save: the next pricing sends no choice.
      await tester.enterText(_box('quotation-line', 0, 1), '6');
      await _settle(tester);
      expect(_sentLine(server.asked, 0)['offer_choice'], isNull);
      expect(find.text('Line 1: TEA-11 does not combine with TEA-5.'),
          findsOneWidget);
    });

    testWidgets('F6 moves into the block; arrows, Space and Enter work',
        (tester) async {
      final _QuotationServer server = _QuotationServer();
      await _pumpQuotation(tester, server);
      final Finder quantity = _box('quotation-line', 0, 1);
      await tester.tap(quantity);
      await tester.pump();
      final int before = server.asked.length;
      await tester.sendKeyEvent(LogicalKeyboardKey.f6);
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.sendKeyEvent(LogicalKeyboardKey.space);
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      expect(tester.widget<EditableText>(quantity).focusNode.hasFocus, isTrue);
      await _settle(tester);
      expect(server.asked.length, before + 1);
      expect(
          (_sentLine(server.asked, 0)['offer_choice'] as Json)['discount_from'],
          'pl-city');
    });
  });

  testWidgets('a sales order sends the choice in its preview and its save',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _SalesApi api = _SalesApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: SalesOrderEditorDialog(
            api: api,
            today: DateTime(2026, 8, 14),
            mayChooseOffers: true,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await fillFirstLine(tester, document: 'sales-order', product: 'Shampoo');
    await tester.tap(find.byKey(const ValueKey('sales-order-customer')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Anand Agencies').last);
    await tester.pumpAndSettle();
    await _settle(tester);
    expect(api.previews, isNotEmpty);
    expect(find.text('TEA-5, 5% off'), findsOneWidget);
    expect(_sentLine(api.previews, 0).containsKey('offer_choice'), isFalse);
    final int before = api.previews.length;
    await _tick(tester, 'sales-order-offer', 'g-tea5');
    await _settle(tester);
    expect(api.previews.length, before + 1);
    expect(_sentLine(api.previews, 0)['offer_choice'], <String, dynamic>{
      'discount_from': null,
      'offers': <String>[],
      'part_share': null,
    });
    // The bill's own offers, read-only under the totals.
    expect(find.byKey(const ValueKey('bill-offers')), findsOneWidget);
    expect(find.text('BILL-2, 2% off the bill · applied'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('sales-order-save')));
    await tester.pumpAndSettle();
    final Json saved = (api.created!['lines'] as List<dynamic>).first as Json;
    expect((saved['offer_choice'] as Json)['offers'], <String>[]);
  });

  testWidgets('a counter bill line sends the choice the same way',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _SalesApi api = _SalesApi(counter: true);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: SalesInvoiceEditorDialog(
            api: api,
            today: DateTime(2026, 8, 14),
            mayChooseOffers: true,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('sales-invoice-customer')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Anand Agencies').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('sales-invoice-direct-product-0')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Shampoo').last);
    await tester.pumpAndSettle();
    await tester.enterText(_box('sales-invoice-direct', 0, 1), '5');
    await _settle(tester);
    expect(api.invoicePreviews, isNotEmpty);
    expect(find.text('Price list CITY, 4%'), findsOneWidget);
    expect(_sentLine(api.invoicePreviews, 0).containsKey('offer_choice'),
        isFalse);
    final int before = api.invoicePreviews.length;
    await _tick(tester, 'sales-invoice-offer', 'pl-city');
    await _settle(tester);
    expect(api.invoicePreviews.length, before + 1);
    expect(_sentLine(api.invoicePreviews, 0)['offer_choice'],
        <String, dynamic>{
          'discount_from': 'pl-city',
          'offers': <String>['g-tea5'],
          'part_share': null,
        });
  });
}

/// The firm the sales order and the counter bill are typed for, priced by
/// the server's kept answers with the candidates added.
class _SalesApi extends ApiClient {
  _SalesApi({this.counter = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// Whether the firm bills straight in, as a counter does, rather than
  /// typing the whole chain.
  final bool counter;
  final List<Json> previews = <Json>[];
  final List<Json> invoicePreviews = <Json>[];
  Json? created;

  Json _paged(List<Json> rows) => <String, dynamic>{
        'data': rows,
        'pagination': <String, dynamic>{'total_records': rows.length},
      };

  Json _priced(String fixture, String product) {
    final Json answer = _renamed(serverPricing(fixture), <String, String>{
      product: 'p1',
    });
    for (final dynamic line in answer['lines'] as List<dynamic>) {
      (line as Json)['candidates'] = _offers();
    }
    answer['bill_candidates'] = <Json>[
      _candidate('g-bill2', 'BILL-2',
          sentence: '2% off the bill', percent: '2', applied: true),
    ];
    return <String, dynamic>{'data': answer};
  }

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
    if (path == '/api/v1/customers') {
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'c1',
          'code': 'C1',
          'name': 'Anand Agencies',
          'display_name': 'Anand Agencies',
          'customer_type': 'BUSINESS',
          'status': 'ACTIVE',
        },
      ]);
    }
    if (path == '/api/v1/products') {
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'p1',
          'code': 'P1',
          'name': 'Shampoo 180ml',
          'selling_price': '100',
          'status': 'ACTIVE',
        },
      ]);
    }
    if (path == '/api/v1/branches') {
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'b1',
          'code': 'HO',
          'name': 'Head Office',
          'display_name': 'Head Office',
          'is_default': true,
        },
      ]);
    }
    if (path == '/api/v1/warehouses') {
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'w1',
          'code': 'WH1',
          'name': 'Main Store',
          'display_name': 'Main Store',
          'is_default': true,
          'branch_id': 'b1',
        },
      ]);
    }
    if (path.contains('workflow-settings')) {
      final bool order = !counter;
      return <String, dynamic>{
        'data': <String, dynamic>{
          'quotation_stage': order,
          'sales_order_stage': order,
          'delivery_note_stage': order,
          'default_warehouse_id': 'w1',
          'is_configured': true,
        },
      };
    }
    if (path.endsWith('/batch-serial/sale-settings')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'price_from_batch': false},
      };
    }
    if (method == 'POST' && path == '/api/v1/sales-orders/preview') {
      previews.add(body!);
      return _priced('sales_order_preview', 'id-8');
    }
    if (method == 'POST' && path == '/api/v1/sales-invoices/preview') {
      invoicePreviews.add(body!);
      return _priced('sales_invoice_preview', 'id-9');
    }
    if (method == 'POST' && path == '/api/v1/sales-orders') {
      created = body;
      return <String, dynamic>{
        'data': <String, dynamic>{'id': 'so-1', 'order_number': 'SO-1'},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}
