import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/quotation.dart';
import 'package:agency_desktop/ui/quotations/quotation_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Prices offered before anything is sold.
///
/// A quotation commits nothing, so the screen's job is to keep saying so — and
/// to make expiry visible, because a lapsed offer is the one thing here that
/// stops being worth anything without its status changing.
PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

const List<String> _fullAccess = [
  'SALES_VIEW',
  'SALES_QUOTATION_CREATE',
  'SALES_APPROVE',
  'SALES_CANCEL',
];

Quotation _quote({
  String status = 'DRAFT',
  bool isExpired = false,
  bool canConvert = false,
  String validUntil = '2026-09-13',
  String orderNumber = '',
  String declineReason = '',
}) =>
    Quotation.fromJson({
      'id': 'q-1',
      'customer_id': 'cust-1',
      'branch_id': 'branch-1',
      'warehouse_id': 'wh-1',
      'quotation_number': 'QT-2026-2027-000001',
      'quotation_date': '2026-08-14',
      'valid_until': validUntil,
      'customer_reference': 'RFQ-42',
      'payment_terms': '30 days',
      'delivery_terms': 'Ex works',
      'status': status,
      'subtotal': '1125.0000',
      'tax_total': '202.5000',
      'grand_total': '1327.5000',
      'converted_sales_order_id': orderNumber.isEmpty ? null : 'so-1',
      'converted_sales_order_number': orderNumber.isEmpty ? null : orderNumber,
      'decline_reason': declineReason,
      'cancel_reason': '',
      'remarks': '',
      'is_expired': isExpired,
      'can_convert': canConvert,
      'lines': [
        {
          'id': 'l-1',
          'line_number': 1,
          'product_id': 'p-1',
          'description': 'Shampoo Bottle 180ml',
          'quantity': '5.0000',
          'unit_price': '250.0000',
          'discount_percent': '10.0000',
          'discount_amount': '125.0000',
          'tax_amount': '202.5000',
          'net_amount': '1327.5000',
          'remarks': '',
        },
        // A second line, because a quotation of one item cannot show whether
        // the editor keeps the rest of the offer when it is revised.
        {
          'id': 'l-2',
          'line_number': 2,
          'product_id': 'p-2',
          'description': 'Soap Bar 100g',
          'quantity': '2.0000',
          'unit_price': '40.0000',
          'discount_percent': '0.0000',
          'discount_amount': '0.0000',
          'tax_amount': '14.4000',
          'net_amount': '94.4000',
          'remarks': '',
        }
      ],
    });

class _QuoteApi extends ApiClient {
  _QuoteApi({this.rows = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Quotation> rows;
  Json? created;
  Json? revised;
  int? revisedVersion;
  final List<String> actions = [];
  String? reason;
  String? convertedId;

  @override
  Future<PagedResult<Quotation>> quotations({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? status,
  }) async =>
      PagedResult<Quotation>(items: rows, total: rows.length);

  @override
  Future<PagedResult<Customer>> customers({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    CustomerQuery filters = const CustomerQuery(),
  }) async =>
      PagedResult<Customer>(
        items: [
          Customer.fromJson({
            'id': 'cust-1',
            'code': 'CUS-001',
            'name': 'Anand Agencies',
            'display_name': 'Anand Agencies',
            'status': 'ACTIVE',
          })
        ],
        total: 1,
      );

  @override
  Future<PagedResult<Product>> products({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    ProductQuery filters = const ProductQuery(),
  }) async =>
      PagedResult<Product>(
        items: [
          Product.fromJson({
            'id': 'p-1',
            'code': 'SHAMP180',
            'name': 'Shampoo Bottle 180ml',
            'status': 'ACTIVE',
          }),
          Product.fromJson({
            'id': 'p-2',
            'code': 'SOAP100',
            'name': 'Soap Bar 100g',
            'status': 'ACTIVE',
          })
        ],
        total: 2,
      );

  @override
  Future<PagedResult<BranchRecord>> branches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BranchQuery filters = const BranchQuery(),
  }) async =>
      PagedResult<BranchRecord>(
        items: [
          BranchRecord.fromJson({
            'id': 'branch-1',
            'code': 'BR-001',
            'name': 'Head office',
            'display_name': 'Head office',
            'status': 'ACTIVE',
          })
        ],
        total: 1,
      );

  @override
  Future<PagedResult<WarehouseRecord>> warehouses({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    WarehouseQuery filters = const WarehouseQuery(),
  }) async =>
      PagedResult<WarehouseRecord>(
        items: [
          WarehouseRecord.fromJson({
            'id': 'wh-1',
            'code': 'WH-001',
            'name': 'Main',
            'display_name': 'Main warehouse',
            'status': 'ACTIVE',
          })
        ],
        total: 1,
      );

  @override
  Future<Quotation> createQuotation(Json data) async {
    created = data;
    return _quote();
  }

  @override
  Future<Quotation> updateQuotation(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    revised = data;
    revisedVersion = expectedVersion;
    return _quote();
  }

  @override
  Future<Quotation> quotationAction(
    String id,
    String action, {
    String? reason,
  }) async {
    actions.add(action);
    this.reason = reason;
    return _quote(status: action == 'send' ? 'SENT' : 'ACCEPTED');
  }

  @override
  Future<QuotationConversion> convertQuotation(String id, {Json? data}) async {
    convertedId = id;
    return QuotationConversion(
      quotation: _quote(status: 'CONVERTED', orderNumber: 'SO-2026-2027-000010'),
      orderNumber: 'SO-2026-2027-000010',
    );
  }
}

Future<void> _pump(
  WidgetTester tester,
  _QuoteApi api, {
  List<String> perms = _fullAccess,
  bool hasActiveFirm = true,
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: QuotationManagementPage(
          api: api,
          permissions: _permissionsFor(perms),
          hasActiveFirm: hasActiveFirm,
          today: DateTime(2026, 8, 14),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester) async {
  await tester.tap(find.textContaining('QT-2026-2027-000001').first);
  await tester.pumpAndSettle();
}

void main() {
  group('reading an offer', () {
    testWidgets('a live quotation says how long it stands', (tester) async {
      await _pump(tester, _QuoteApi(rows: [_quote(status: 'SENT')]));

      expect(find.text('stands until 2026-09-13'), findsWidgets);
      expect(find.text('SENT'), findsOneWidget);
    });

    testWidgets('a lapsed one is badged as well as dated', (tester) async {
      // SENT reads the same the day before and the day after the prices lapse,
      // so the status word alone cannot carry this.
      await _pump(
        tester,
        _QuoteApi(rows: [_quote(status: 'SENT', isExpired: true)]),
      );

      expect(find.text('EXPIRED'), findsOneWidget);
      expect(find.text('lapsed on 2026-09-13'), findsWidgets);
    });

    testWidgets('a converted one names the order it became', (tester) async {
      await _pump(
        tester,
        _QuoteApi(
          rows: [
            _quote(status: 'CONVERTED', orderNumber: 'SO-2026-2027-000010')
          ],
        ),
      );

      expect(find.text('became SO-2026-2027-000010'), findsWidgets);
    });

    testWidgets('a declined one carries the reason', (tester) async {
      await _pump(
        tester,
        _QuoteApi(
          rows: [
            _quote(status: 'DECLINED', declineReason: 'Competitor was cheaper')
          ],
        ),
      );

      expect(
        find.text('declined — Competitor was cheaper'),
        findsWidgets,
        reason: 'why the firm is losing work is recorded nowhere else',
      );
    });

    testWidgets('the detail says nothing is reserved', (tester) async {
      await _pump(tester, _QuoteApi(rows: [_quote(status: 'SENT')]));
      await _select(tester);

      expect(
        find.textContaining('Nothing is reserved and nothing is owed'),
        findsOneWidget,
      );
      expect(find.textContaining('1125.0000 + 202.5000 tax'), findsOneWidget);
    });

    testWidgets('a converted one says where the commitment lives now',
        (tester) async {
      await _pump(
        tester,
        _QuoteApi(
          rows: [
            _quote(status: 'CONVERTED', orderNumber: 'SO-2026-2027-000010')
          ],
        ),
      );
      await _select(tester);

      expect(
        find.textContaining('stock is reserved when that order is approved'),
        findsOneWidget,
      );
    });
  });

  group('acting on one', () {
    testWidgets('a draft can be sent and revised, not accepted twice',
        (tester) async {
      final _QuoteApi api = _QuoteApi(rows: [_quote()]);
      await _pump(tester, api);
      await _select(tester);

      expect(find.widgetWithText(FilledButton, 'Mark as sent'), findsOneWidget);
      expect(find.widgetWithText(OutlinedButton, 'Revise'), findsOneWidget);

      await tester.tap(find.widgetWithText(FilledButton, 'Mark as sent'));
      await tester.pumpAndSettle();
      expect(api.actions, ['send']);
    });

    testWidgets('declining asks why', (tester) async {
      final _QuoteApi api = _QuoteApi(rows: [_quote(status: 'SENT')]);
      await _pump(tester, api);
      await _select(tester);

      await tester.tap(find.widgetWithText(OutlinedButton, 'Customer declined'));
      await tester.pumpAndSettle();
      expect(
        find.textContaining('It is the only place this is recorded'),
        findsOneWidget,
      );

      await tester.enterText(find.byType(TextField).last, 'Price too high');
      await tester.tap(find.widgetWithText(FilledButton, 'Decline'));
      await tester.pumpAndSettle();

      expect(api.actions, ['decline']);
      expect(api.reason, 'Price too high');
    });

    testWidgets('an accepted quotation converts', (tester) async {
      final _QuoteApi api = _QuoteApi(
        rows: [_quote(status: 'ACCEPTED', canConvert: true)],
      );
      await _pump(tester, api);
      await _select(tester);

      await tester.tap(find.widgetWithText(FilledButton, 'Convert to order'));
      await tester.pumpAndSettle();

      expect(api.convertedId, 'q-1');
    });

    testWidgets('an expired accepted quotation offers a disabled convert',
        (tester) async {
      // The server refuses it, so the button says why rather than failing.
      await _pump(
        tester,
        _QuoteApi(
          rows: [
            _quote(status: 'ACCEPTED', isExpired: true, canConvert: false)
          ],
        ),
      );
      await _select(tester);

      final TextButton button = tester.widget<TextButton>(
        find.widgetWithText(TextButton, 'Convert to order'),
      );
      expect(button.onPressed, isNull);
      expect(find.byType(Tooltip), findsWidgets);
    });

    testWidgets('an expired quotation cannot be accepted at all',
        (tester) async {
      await _pump(
        tester,
        _QuoteApi(rows: [_quote(status: 'SENT', isExpired: true)]),
      );
      await _select(tester);

      expect(
        find.widgetWithText(FilledButton, 'Customer accepted'),
        findsNothing,
      );
    });

    testWidgets('a converted quotation cannot be withdrawn', (tester) async {
      await _pump(
        tester,
        _QuoteApi(
          rows: [
            _quote(status: 'CONVERTED', orderNumber: 'SO-2026-2027-000010')
          ],
        ),
      );
      await _select(tester);

      expect(find.widgetWithText(TextButton, 'Withdraw'), findsNothing);
    });

    testWidgets('without SALES_APPROVE nobody decides', (tester) async {
      await _pump(
        tester,
        _QuoteApi(rows: [_quote(status: 'SENT')]),
        perms: const ['SALES_VIEW', 'SALES_QUOTATION_CREATE'],
      );
      await _select(tester);

      expect(
        find.widgetWithText(FilledButton, 'Customer accepted'),
        findsNothing,
      );
      expect(find.widgetWithText(FilledButton, 'Mark as sent'), findsNothing);
    });
  });

  group('writing one', () {
    testWidgets('it defaults to thirty days and sends what was typed',
        (tester) async {
      final _QuoteApi api = _QuoteApi();
      await _pump(tester, api);
      await tester.tap(find.widgetWithText(FilledButton, 'New Quotation'));
      await tester.pumpAndSettle();

      // Thirty days from the pinned today, so the field is never empty.
      expect(find.text('2026-09-13'), findsOneWidget);

      await tester.enterText(
        find.widgetWithText(TextFormField, 'Quantity'),
        '5',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Unit price'),
        '250',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Discount %'),
        '10',
      );
      await tester.pumpAndSettle();

      // The consequence of the three numbers, before saving.
      expect(find.textContaining('Quoted before tax: 1125.00'), findsOneWidget);

      await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
      await tester.pumpAndSettle();

      final Json? sent = api.created;
      expect(sent, isNotNull);
      expect(sent!['quotation_date'], '2026-08-14');
      expect(sent['valid_until'], '2026-09-13');
      expect(sent['customer_id'], 'cust-1');
      final Map<String, dynamic> line =
          Map<String, dynamic>.from((sent['lines'] as List).single as Map);
      expect(line['quantity'], '5');
      expect(line['unit_price'], '250');
      expect(line['discount_percent'], '10');
    });

    testWidgets('it sends every line that was typed', (tester) async {
      final _QuoteApi api = _QuoteApi();
      await _pump(tester, api);
      await tester.tap(find.widgetWithText(FilledButton, 'New Quotation'));
      await tester.pumpAndSettle();

      await tester.enterText(find.widgetWithText(TextFormField, 'Quantity'), '5');
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Unit price'), '250');
      await tester.tap(find.widgetWithText(TextButton, 'Add line'));
      await tester.pumpAndSettle();

      // Two of each now, so each field is addressed by position.
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Quantity').last, '2');
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Unit price').last, '40');
      await tester.pumpAndSettle();

      // Each line shows what it contributes, and the offer shows the sum --
      // one total alone does not say which of the lines was mistyped.
      expect(find.text('Line 1: 1250.00'), findsOneWidget);
      expect(find.text('Line 2: 80.00'), findsOneWidget);
      expect(find.textContaining('Quoted before tax: 1330.00'), findsOneWidget);

      await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
      await tester.pumpAndSettle();

      final List<dynamic> lines = api.created!['lines'] as List<dynamic>;
      expect(lines.length, 2);
      expect((lines[0] as Map)['line_number'], 1);
      expect((lines[0] as Map)['quantity'], '5');
      expect((lines[1] as Map)['line_number'], 2);
      expect((lines[1] as Map)['quantity'], '2');
      expect((lines[1] as Map)['unit_price'], '40');
    });

    testWidgets('removing a line takes its own numbers with it',
        (tester) async {
      final _QuoteApi api = _QuoteApi();
      await _pump(tester, api);
      await tester.tap(find.widgetWithText(FilledButton, 'New Quotation'));
      await tester.pumpAndSettle();

      await tester.enterText(find.widgetWithText(TextFormField, 'Quantity'), '1');
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Unit price'), '10');
      for (final String pair in const ['2:20', '3:30']) {
        await tester.tap(find.widgetWithText(TextButton, 'Add line'));
        await tester.pumpAndSettle();
        await tester.enterText(find.widgetWithText(TextFormField, 'Quantity').last,
            pair.split(':').first);
        await tester.enterText(
            find.widgetWithText(TextFormField, 'Unit price').last,
            pair.split(':').last);
      }
      await tester.pumpAndSettle();

      // Drop the middle line. Its controllers belong to the draft, so what is
      // left has to be the first and third rows -- if the state kept parallel
      // lists instead, the third row would inherit the second's numbers.
      await tester.tap(find.byTooltip('Remove this line').at(1));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
      await tester.pumpAndSettle();

      final List<dynamic> lines = api.created!['lines'] as List<dynamic>;
      expect(lines.length, 2);
      expect((lines[0] as Map)['quantity'], '1');
      expect((lines[0] as Map)['unit_price'], '10');
      // Renumbered, because line_number is the document's own sequence and a
      // gap in it is not something the server should be asked to hold.
      expect((lines[1] as Map)['line_number'], 2);
      expect((lines[1] as Map)['quantity'], '3');
      expect((lines[1] as Map)['unit_price'], '30');
    });

    testWidgets('the only line cannot be removed', (tester) async {
      await _pump(tester, _QuoteApi());
      await tester.tap(find.widgetWithText(FilledButton, 'New Quotation'));
      await tester.pumpAndSettle();

      // A quotation with no lines is not an offer and the server refuses one,
      // so the control says why rather than failing on save.
      expect(find.byTooltip('A quotation needs at least one line'),
          findsOneWidget);
      final IconButton button = tester.widget<IconButton>(
        find.ancestor(
          of: find.byTooltip('A quotation needs at least one line'),
          matching: find.byType(IconButton),
        ),
      );
      expect(button.onPressed, isNull);
    });

    testWidgets('a revision starts from every line the offer holds',
        (tester) async {
      final _QuoteApi api = _QuoteApi(rows: [_quote()]);
      await _pump(tester, api);
      await _select(tester);
      await tester.tap(find.widgetWithText(OutlinedButton, 'Revise'));
      await tester.pumpAndSettle();

      // Both lines of the stored quotation are on screen. Seeding only the
      // first is a silent deletion: the update replaces the whole collection
      // with whatever is sent.
      expect(find.widgetWithText(TextFormField, 'Quantity'), findsNWidgets(2));
      expect(find.text('Line 1: 1125.00'), findsOneWidget);
      expect(find.text('Line 2: 80.00'), findsOneWidget);

      await tester.tap(find.widgetWithText(FilledButton, 'Save revision'));
      await tester.pumpAndSettle();

      final List<dynamic> lines = api.revised!['lines'] as List<dynamic>;
      expect(lines.length, 2);
      expect((lines[0] as Map)['product_id'], 'p-1');
      // The rate that was quoted, not the amount it worked out to. Only the
      // amount was parsed before, so revising re-sent the line at full price.
      expect((lines[0] as Map)['discount_percent'], '10.0000');
      expect((lines[1] as Map)['product_id'], 'p-2');
    });

    testWidgets('it refuses a quantity or price of nothing', (tester) async {
      final _QuoteApi api = _QuoteApi();
      await _pump(tester, api);
      await tester.tap(find.widgetWithText(FilledButton, 'New Quotation'));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithText(TextFormField, 'Quantity'),
        '0',
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
      await tester.pumpAndSettle();

      expect(find.text('Enter the quantity.'), findsOneWidget);
      expect(api.created, isNull);
    });

    testWidgets('without the quotation permission there is no button',
        (tester) async {
      await _pump(
        tester,
        _QuoteApi(rows: [_quote()]),
        perms: const ['SALES_VIEW'],
      );

      expect(
        find.widgetWithText(FilledButton, 'New Quotation'),
        findsNothing,
      );
    });
  });

  group('the empty and unauthorised states', () {
    testWidgets('no firm, no quotations', (tester) async {
      await _pump(tester, _QuoteApi(), hasActiveFirm: false);
      expect(find.textContaining('Choose a firm'), findsOneWidget);
    });

    testWidgets('without SALES_VIEW there is nothing to show', (tester) async {
      await _pump(tester, _QuoteApi(), perms: const ['INVENTORY_VIEW']);
      expect(find.textContaining('do not have permission'), findsOneWidget);
    });

    testWidgets('an empty list explains what a quotation is', (tester) async {
      await _pump(tester, _QuoteApi());
      expect(find.text('Nothing has been quoted'), findsOneWidget);
      expect(find.textContaining('reserves no stock'), findsOneWidget);
    });
  });

  group('the model', () {
    test('an offer is open only while nobody has decided and it stands', () {
      expect(_quote(status: 'SENT').isOpen, isTrue);
      expect(_quote(status: 'SENT', isExpired: true).isOpen, isFalse);
      expect(_quote(status: 'ACCEPTED').isOpen, isFalse);
      expect(_quote(status: 'CONVERTED').isOpen, isFalse);
    });

    test('a conversion reads both documents out of one answer', () {
      final QuotationConversion result = QuotationConversion.fromJson({
        'data': {
          'id': 'q-1',
          'quotation_number': 'QT-1',
          'status': 'CONVERTED',
          'lines': [],
        },
        'order': {'id': 'so-1', 'order_number': 'SO-9'},
      });

      expect(result.quotation.quotationNumber, 'QT-1');
      expect(result.orderNumber, 'SO-9');
    });
  });
}
