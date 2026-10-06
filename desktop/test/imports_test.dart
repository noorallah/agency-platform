// PG-12 part C: importing. The supplier's currency, a bill in a foreign
// currency (rate required, rupee equivalent shown, no Paid now, TDS or TCS), a
// payment in that currency, the Bills of Entry list and window, the
// revaluation dialog, and nothing overflowing at 1366x768 or 800x600.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/document_preview.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/settlement.dart';
import 'package:agency_desktop/models/settlement_direction.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/finance/fx_revaluation_dialog.dart';
import 'package:agency_desktop/ui/finance/record_settlement_dialog.dart';
import 'package:agency_desktop/ui/purchase_invoices/approve_bill_dialog.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/purchases/bill_of_entry_page.dart';
import 'package:agency_desktop/ui/vendors/vendor_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> perms) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': perms,
  }));

const List<Size> _sizes = [Size(1366, 768), Size(800, 600)];

Json _vendorJson({String? currency}) => <String, dynamic>{
      'id': 'vendor-1',
      'firm_id': 'firm-1',
      'code': 'V001',
      'name': 'Shenzhen Parts',
      'display_name': 'Shenzhen Parts',
      'status': 'ACTIVE',
      'currency_code': currency,
      'addresses': <Json>[],
      'contacts': <Json>[],
      'bank_accounts': <Json>[],
      'tax_details': <Json>[],
      'notes': <Json>[],
    };

Json _boe(String id, String status) => <String, dynamic>{
      'id': id,
      'document_number': 'BOE-$id',
      'boe_number': '99887$id',
      'boe_date': '2026-10-01',
      'port_code': 'INMAA1',
      'vendor_id': 'vendor-1',
      'vendor_code': 'V001',
      'vendor_name': 'Shenzhen Parts',
      'branch_id': null,
      'currency_code': 'USD',
      'exchange_rate': '84.100000',
      'assessable_value': '84100.00',
      'basic_customs_duty': '8410.00',
      'social_welfare_surcharge': '841.00',
      'customs_duty': '9251.00',
      'igst_amount': '17200.00',
      'cess_amount': '0.00',
      'total_duty': '26451.00',
      'inventory_amount': '9251.00',
      'cogs_amount': '0.00',
      'expense_amount': '0.00',
      'status': status,
      'posted_at': status == 'POSTED' ? '2026-10-02T00:00:00Z' : null,
      'journal_entry_id': status == 'POSTED' ? 'je-1' : null,
      'remarks': null,
      'cancel_reason': null,
      'version': 2,
      'purchase_invoices': <Json>[],
      'goods_receipts': <Json>[],
      'lines': [
        {
          'id': 'l-1',
          'line_number': 1,
          'product_id': 'p-1',
          'product_code': 'CHIP',
          'product_name': 'Controller chip',
          'quantity': '100.0000',
          'assessable_value': '84100.00',
          'bcd_rate': '10.0000',
          'bcd_amount': '8410.00',
          'sws_rate': null,
          'sws_amount': '841.00',
          'igst_base': '93351.00',
          'igst_rate': '18.0000',
          'igst_amount': '17200.00',
          'cess_amount': '0.00',
          'total_duty': '26451.00',
          'inventory_amount': '9251.00',
          'cogs_amount': '0.00',
          'expense_amount': '0.00',
        },
      ],
    };

class _Api extends ApiClient {
  _Api({this.vendorCurrency})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String? vendorCurrency;
  final Map<String, Json?> bodies = <String, Json?>{};
  final List<String> calls = <String>[];
  Json? preview;
  Json? payment;
  Json? vendorSaved;

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
    final String call = '$method $path';
    calls.add(call);
    bodies[call] = body;
    switch (call) {
      case 'GET /api/v1/bills-of-entry':
        return {
          'data': [_boe('1', 'DRAFT'), _boe('2', 'POSTED')],
          'pagination': {'total_records': 2},
        };
      case 'GET /api/v1/bills-of-entry/1':
        return {'data': _boe('1', 'DRAFT')};
      case 'GET /api/v1/bills-of-entry/2':
        return {'data': _boe('2', 'POSTED')};
      case 'POST /api/v1/bills-of-entry':
        return {'data': _boe('9', 'DRAFT')};
      case 'POST /api/v1/bills-of-entry/1/post':
        return {'data': _boe('1', 'POSTED')};
      case 'POST /api/v1/bills-of-entry/2/cancel':
        return {'data': _boe('2', 'CANCELLED')};
      case 'POST /api/v1/finance/fx-revaluation':
        return {
          'data': {
            'as_of': '2026-10-31',
            'reference': 'FXREV-20261031',
            'lines': [
              {
                'invoice_id': 'b-1',
                'invoice_number': 'PI-1',
                'currency_code': 'USD',
                'currency_outstanding': '1000.00',
                'carried_amount': '84000.00',
                'revalued_amount': '84500.00',
                'difference': '500.00',
              },
            ],
            'total_difference': '500.00',
            'journal_entry_id': 'je-7',
          },
        };
    }
    if (path == '/api/v1/vendors') {
      return {
        'data': [_vendorJson(currency: vendorCurrency)],
        'pagination': {'total_records': 1},
      };
    }
    if (path == '/api/v1/products') {
      return {
        'data': [
          {'id': 'p-1', 'code': 'CHIP', 'name': 'Controller chip'},
        ],
        'pagination': {'total_records': 1},
      };
    }
    if (path == '/api/v1/purchase-invoices') {
      return {
        'data': [
          {
            'id': 'bill-1',
            'invoice_number': 'PI-1',
            'supplier_invoice_number': 'SZ-77',
            'invoice_date': '2026-09-20',
            'currency_code': 'USD',
            'grand_total': '1000.00',
            'status': 'APPROVED',
          },
        ],
        'pagination': {'total_records': 1},
      };
    }
    if (path == '/api/v1/goods-receipts') {
      return {
        'data': [
          {
            'id': 'grn-9',
            'grn_number': 'GRN-9',
            'receipt_date': '2026-09-21',
            'status': 'COMPLETED',
            'vendor_id': 'vendor-1',
            'branch_id': 'branch-1',
            'lines': <Json>[],
          },
        ],
        'pagination': {'total_records': 1},
      };
    }
    return {'data': const <dynamic>[]};
  }

  @override
  Future<List<GeoPlaceRecord>> geoPlaces(
    GeoLevel level, {
    String parentId = '',
  }) async =>
      const <GeoPlaceRecord>[];

  @override
  Future<Vendor> createVendor(Json data) async {
    vendorSaved = data;
    return Vendor.fromJson(_vendorJson());
  }

  @override
  Future<Vendor> updateVendor(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    vendorSaved = data;
    return Vendor.fromJson(_vendorJson());
  }

  @override
  Future<Json> documentPage(
    String resource, {
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> additionalQuery = const {},
  }) =>
      request('GET', '/api/v1/$resource');

  @override
  Future<PurchaseInvoicePreviewRecord> previewPurchaseInvoice(
    Json data,
  ) async {
    (previews ??= <Json>[]).add(data);
    return PurchaseInvoicePreviewRecord.fromJson({
      'invoice': {
        'invoice_number': 'PI-2026-000009',
        'currency_code': 'USD',
        'exchange_rate': data['exchange_rate'],
        'subtotal': '1000.00',
        'tax_total': '0.00',
        'grand_total': '1000.00',
        'base_tax_total': '0.00',
        'base_grand_total': '84100.00',
        'base_amount_owed': '84100.00',
        'lines': [
          {
            'line_number': 1,
            'source_document_line_id': 'grn-line-1',
            'gross_amount': '1000.00',
            'discount_amount': '0',
            'tax_amount': '0.00',
          },
        ],
      },
      'interstate': false,
      'lines': <Json>[],
    });
  }

  List<Json>? previews;

  @override
  Future<Json> createPurchaseInvoice(Json body) async {
    bodies['bill'] = body;
    return {
      'data': {'id': 'pi-1', 'invoice_number': 'PI-1', 'status': 'DRAFT'}
    };
  }

  @override
  Future<List<OutstandingInvoice>> outstandingInvoices({
    required SettlementDirection direction,
    required String partyId,
  }) async =>
      [
        OutstandingInvoice.fromJson({
          'invoice_id': 'b-usd',
          'invoice_number': 'PI-USD',
          'invoice_date': '2026-09-20',
          'invoice_total': '84100.00',
          'allocated_amount': '0.00',
          'outstanding_amount': '84100.00',
          'currency_code': 'USD',
          'exchange_rate': '84.100000',
          'currency_total': '1000.00',
          'currency_outstanding': '1000.00',
        }),
        OutstandingInvoice.fromJson({
          'invoice_id': 'b-inr',
          'invoice_number': 'PI-INR',
          'invoice_date': '2026-09-21',
          'invoice_total': '500.00',
          'allocated_amount': '0.00',
          'outstanding_amount': '500.00',
        }),
      ];

  @override
  Future<List<SupplierCredit>> supplierCredits(String vendorId) async =>
      const <SupplierCredit>[];

  @override
  Future<Json> tds194qSupplier(String vendorId, {required String on}) async =>
      <String, dynamic>{'applies': false};

  @override
  Future<Settlement> recordSettlement({
    required SettlementDirection direction,
    required Json data,
  }) async {
    payment = data;
    return Settlement.fromJson({
      'id': 's-1',
      'direction': 'PAYMENT',
      'settlement_number': 'PAY-1',
      'currency_code': 'USD',
      'exchange_rate': '84.500000',
      'currency_amount': '1000.00',
      'amount': '84500.00',
      'exchange_difference': '400.00',
      'allocations': <Json>[],
    });
  }
}

void _size(WidgetTester tester, Size size) {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

Future<void> _pumpVendor(WidgetTester tester, _Api api, Size size) async {
  _size(tester, size);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: VendorManagementPage(
        api: api,
        permissions: _permissions(
            ['VENDOR_VIEW', 'VENDOR_CREATE', 'VENDOR_UPDATE']),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.text('V001').first);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
  await tester.tap(find.byTooltip('Edit').first);
  await tester.pumpAndSettle();
}

/// A receipt of goods ordered in [currency] at [rate]; blank is rupees.
GoodsReceiptRecord _receipt({String currency = 'USD', String rate = '83'}) =>
    GoodsReceiptRecord.fromJson({
      if (currency.isNotEmpty) 'currency_code': currency,
      if (currency.isNotEmpty) 'exchange_rate': rate,
      'id': 'grn-1',
      'grn_number': 'GRN-2026-000001',
      'receipt_date': '2026-08-10',
      'status': 'COMPLETED',
      'vendor_id': 'vendor-1',
      'vendor_name': 'Shenzhen Parts',
      'branch_id': 'branch-1',
      'lines': [
        {
          'id': 'grn-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'description': 'Controller chip',
          'accepted_quantity': '10',
          'unit_price': '100',
          'purchase_uom_id': 'uom-box',
          'warehouse_id': 'wh-1',
          'tax_profile_id': 'tax-1',
        },
      ],
    });

Future<void> _pumpBill(
  WidgetTester tester,
  _Api api,
  Size size, {
  String orderCurrency = 'USD',
}) async {
  _size(tester, size);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseInvoiceEditorDialog(
          api: api,
          receipts: [_receipt(currency: orderCurrency)],
          vendors: [Vendor.fromJson(_vendorJson(currency: 'USD'))],
          products: [
            Product.fromJson({
              'id': 'prod-1',
              'code': 'SKU-1',
              'name': 'Controller chip',
            }),
          ],
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester
      .tap(find.byKey(const ValueKey('purchase-invoice-receipt-supplier')));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Shenzhen Parts').last);
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _type(WidgetTester tester, String key, String text) async {
  await tester.enterText(find.byKey(ValueKey<String>(key)), text);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _pumpPayment(WidgetTester tester, _Api api, Size size) async {
  _size(tester, size);
  await tester.pumpWidget(
    MaterialApp(
      home: Phase2Scope(
        child: Scaffold(
          body: RecordSettlementDialog(
            api: api,
            direction: SettlementDirection.payment,
            parties: const [
              PartyOption(id: 'vendor-1', code: 'V001', name: 'Shenzhen Parts'),
            ],
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.byType(TextFormField).first);
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Shenzhen Parts').last);
  await tester.pumpAndSettle();
}

Future<void> _pumpBoe(WidgetTester tester, _Api api, Size size) async {
  _size(tester, size);
  final DesktopPreferencesService preferences = DesktopPreferencesService(
    directory: Directory.systemTemp.createTempSync('boe'),
  );
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: BillOfEntryPage(
        api: api,
        preferences: preferences,
        permissions: _permissions([
          'BILL_OF_ENTRY_VIEW',
          'BILL_OF_ENTRY_MANAGE',
          'PURCHASE_APPROVE',
        ]),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

/// A command of the selection bar, which is where a picked row's actions are.
Future<void> _command(WidgetTester tester, String id) async {
  await tester.tap(find.byKey(ValueKey('selection-$id')));
  await tester.pumpAndSettle();
}

/// The amount box of the only bill row in the payment's table.
Finder _applyBox() =>
    find.descendant(of: find.byType(DataTable), matching: find.byType(TextField));

Finder _figure(String text) => find.textContaining(text, findRichText: true);

void main() {
  group('the supplier currency', () {
    testWidgets('is sent upper-cased, and a short code is refused',
        (tester) async {
      final _Api api = _Api();
      await _pumpVendor(tester, api, const Size(1600, 900));
      final Finder box = find.byKey(const ValueKey('vendor-currency'));
      await tester.ensureVisible(box);
      await tester.enterText(box, 'us');
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('vendor-save')));
      await tester.pumpAndSettle();
      expect(api.vendorSaved, isNull);

      await tester.enterText(box, 'usd');
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('vendor-save')));
      await tester.pumpAndSettle();
      expect(api.vendorSaved?['currency_code'], 'USD');
    });

    testWidgets('blank is sent as null, which clears it', (tester) async {
      final _Api api = _Api(vendorCurrency: 'USD');
      await _pumpVendor(tester, api, const Size(1600, 900));
      final Finder box = find.byKey(const ValueKey('vendor-currency'));
      await tester.ensureVisible(box);
      await tester.enterText(box, '');
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('vendor-save')));
      await tester.pumpAndSettle();
      expect(api.vendorSaved?.containsKey('currency_code'), isTrue);
      expect(api.vendorSaved?['currency_code'], isNull);
    });
  });

  group('a bill in US dollars', () {
    testWidgets('needs a rate, shows the rupee line, and has no TCS',
        (tester) async {
      final _Api api = _Api();
      await _pumpBill(tester, api, const Size(1600, 900));
      // The order's currency is the bill's, with no TCS to offer, at the
      // rate the goods were received at (D-BUY-42).
      final Finder rate =
          find.byKey(const ValueKey('purchase-invoice-exchange-rate-USD'));
      expect(rate, findsOneWidget);
      expect(tester.widget<TextFormField>(rate).initialValue, '83');
      expect(find.byKey(const ValueKey('purchase-invoice-tcs-rate')),
          findsNothing);
      expect(find.byKey(const ValueKey('purchase-invoice-foreign-note')),
          findsOneWidget);

      // Cleared, the bill has no rate: it is not quietly the order's again.
      await _type(tester, 'purchase-invoice-exchange-rate-USD', '');
      await _type(tester, 'purchase-invoice-supplier-number-0', 'SZ-1');
      await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
      await tester.pumpAndSettle();
      expect(api.bodies['bill'], isNull);
      expect(find.textContaining('Enter the exchange rate'), findsWidgets);

      await _type(tester, 'purchase-invoice-exchange-rate-USD', '84.1');
      expect(api.previews!.last['exchange_rate'], '84.1');
      expect(_figure('₹ equivalent'), findsOneWidget);
      expect(_figure('Total USD'), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
      await tester.pumpAndSettle();
      final Json sent = api.bodies['bill']!;
      expect(sent['exchange_rate'], '84.1');
      // Untouched, so the server starts the bill in its order's currency.
      expect(sent.containsKey('currency_code'), isFalse);
      expect(sent.containsKey('tcs_rate_percent'), isFalse);
    });

    testWidgets('untouched, it is saved at the rate its order was received at',
        (tester) async {
      final _Api api = _Api();
      await _pumpBill(tester, api, const Size(1600, 900));
      await _type(tester, 'purchase-invoice-supplier-number-0', 'SZ-1');
      expect(api.previews!.last['exchange_rate'], '83');

      await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
      await tester.pumpAndSettle();

      expect(api.bodies['bill']!['exchange_rate'], '83');
      expect(tester.takeException(), isNull);
    });

    testWidgets('a USD supplier ordered from in rupees is billed in rupees',
        (tester) async {
      // D-BUY-42: the editor showed USD and asked for a rate while the
      // server, which follows the order, saved the bill in rupees.
      final _Api api = _Api();
      await _pumpBill(tester, api, const Size(1600, 900), orderCurrency: '');
      expect(find.byKey(const ValueKey('purchase-invoice-exchange-rate-USD')),
          findsNothing);
      expect(find.byKey(const ValueKey('purchase-invoice-foreign-note')),
          findsNothing);
      expect(find.byKey(const ValueKey('purchase-invoice-tcs-rate')),
          findsOneWidget);

      await _type(tester, 'purchase-invoice-supplier-number-0', 'SZ-1');
      await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
      await tester.pumpAndSettle();

      final Json sent = api.bodies['bill']!;
      expect(sent.containsKey('currency_code'), isFalse);
      expect(sent.containsKey('exchange_rate'), isFalse);
      expect(tester.takeException(), isNull);
    });

    testWidgets('approval offers no Paid now and no TDS', (tester) async {
      _size(tester, const Size(1366, 768));
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () => showDialog<Json>(
                context: context,
                builder: (_) => ApproveBillDialog(
                  number: 'PI-1',
                  currencyCode: 'USD',
                  onApprove: (body) async => <String, dynamic>{},
                ),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('paid-now')), findsNothing);
      expect(find.byKey(const ValueKey('approve-foreign-note')),
          findsOneWidget);
    });
  });

  group('a payment in US dollars', () {
    testWidgets('sends currency_code and exchange_rate, in that currency',
        (tester) async {
      final _Api api = _Api();
      await _pumpPayment(tester, api, const Size(1400, 900));
      expect(find.byKey(const ValueKey('settlement-currency')),
          findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('settlement-currency')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('USD').last);
      await tester.pumpAndSettle();
      // Only the dollar bill is offered, read in dollars.
      expect(find.text('PI-USD'), findsOneWidget);
      expect(find.text('PI-INR'), findsNothing);

      await tester.enterText(
          find.byKey(const ValueKey('settlement-exchange-rate')), '84.5');
      await tester.enterText(
          find.widgetWithText(TextField, 'Amount (USD)'), '1000');
      await tester.enterText(_applyBox(), '1000');
      await tester.pumpAndSettle();
      await tester.tap(find.text('Record payment'));
      await tester.pumpAndSettle();

      final Json sent = api.payment!;
      expect(sent['currency_code'], 'USD');
      expect(sent['exchange_rate'], '84.5');
      expect(sent['amount'], '1000');
      expect(sent['allocations'], [
        {'invoice_id': 'b-usd', 'amount': '1000'},
      ]);
      expect(sent.containsKey('tds_amount'), isFalse);
    });

    testWidgets('a rate is required', (tester) async {
      final _Api api = _Api();
      await _pumpPayment(tester, api, const Size(1400, 900));
      await tester.tap(find.byKey(const ValueKey('settlement-currency')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('USD').last);
      await tester.pumpAndSettle();
      await tester.enterText(
          find.widgetWithText(TextField, 'Amount (USD)'), '1000');
      await tester.enterText(_applyBox(), '1000');
      await tester.pump();
      await tester.tap(find.text('Record payment'));
      await tester.pumpAndSettle();
      expect(api.payment, isNull);
      expect(find.textContaining('Enter the exchange rate'), findsOneWidget);
    });
  });

  group('Bills of Entry', () {
    testWidgets('the list renders both documents', (tester) async {
      await _pumpBoe(tester, _Api(), const Size(1366, 768));
      expect(find.text('BOE-1'), findsOneWidget);
      expect(find.text('BOE-2'), findsOneWidget);
      expect(find.text('INMAA1'), findsNWidgets(2));
      expect(tester.takeException(), isNull);
    });

    testWidgets('create sends the declared fields and omits blank amounts',
        (tester) async {
      final _Api api = _Api();
      await _pumpBoe(tester, api, const Size(1366, 768));
      await tester.tap(find.byKey(const ValueKey('toolbar-new')));
      await tester.pumpAndSettle();

      await tester.enterText(find.byKey(const ValueKey('boe-number')), '7788');
      await tester.enterText(find.byKey(const ValueKey('boe-port')), 'inmaa1');
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('boe-vendor')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Shenzhen Parts').last);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('boe-bill-bill-1')));
      await tester.tap(find.byKey(const ValueKey('boe-receipt-grn-9')));
      await tester.enterText(find.byKey(const ValueKey('boe-product-0')), 'CH');
      await tester.pumpAndSettle();
      await tester.tap(find.text('CHIP · Controller chip').last);
      await tester.pumpAndSettle();
      await tester.enterText(find.byKey(const ValueKey('boe-qty-0')), '100');
      await tester.enterText(
          find.byKey(const ValueKey('boe-value-0')), '84100');
      await tester.enterText(
          find.byKey(const ValueKey('boe-bcd-rate-0')), '10');
      await tester.ensureVisible(find.byKey(const ValueKey('boe-save')));
      await tester.tap(find.byKey(const ValueKey('boe-save')));
      await tester.pumpAndSettle();

      final Json sent = api.bodies['POST /api/v1/bills-of-entry']!;
      expect(sent.keys.toSet(), <String>{
        'boe_number',
        'boe_date',
        'port_code',
        'vendor_id',
        'purchase_invoice_ids',
        'goods_receipt_ids',
        'lines',
      });
      expect(sent['port_code'], 'INMAA1');
      expect(sent['purchase_invoice_ids'], ['bill-1']);
      expect(sent['goods_receipt_ids'], ['grn-9']);
      final Json line = (sent['lines'] as List).single as Json;
      expect(line, {
        'product_id': 'p-1',
        'quantity': '100',
        'assessable_value': '84100',
        'bcd_rate': '10',
      });
      expect(find.byType(BillOfEntryDialog), findsNothing);
    });

    testWidgets('post and cancel call the api', (tester) async {
      final _Api api = _Api();
      await _pumpBoe(tester, api, const Size(1366, 768));
      await tester.tap(find.text('BOE-1'));
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
      await _command(tester, 'post');
      expect(api.calls, contains('POST /api/v1/bills-of-entry/1/post'));

      await tester.tap(find.text('BOE-2'));
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();
      await _command(tester, 'cancel');
      await tester.enterText(find.byType(TextField).last, 'Wrong supplier');
      await tester.pump();
      await tester.tap(find.text('Cancel the Bill of Entry'));
      await tester.pumpAndSettle();
      expect(api.bodies['POST /api/v1/bills-of-entry/2/cancel'],
          {'reason': 'Wrong supplier'});
    });

    for (final Size size in _sizes) {
      testWidgets('the window has no overflow at ${size.width.toInt()}x'
          '${size.height.toInt()}', (tester) async {
        await _pumpBoe(tester, _Api(), size);
        await tester.tap(find.text('BOE-1'));
        await tester.pump(const Duration(milliseconds: 400));
        await tester.pumpAndSettle();
        await tester.tap(find.byKey(const ValueKey('selection-view')));
        await tester.pumpAndSettle();
        expect(find.byType(BillOfEntryDialog), findsOneWidget);
        expect(find.byKey(const ValueKey('boe-t-total')), findsOneWidget);
        expect(find.byKey(const ValueKey('boe-computed-0')), findsOneWidget);
        expect(tester.takeException(), isNull);
      });
    }
  });

  group('revaluing foreign payables', () {
    testWidgets('posts the date and the rates and shows the result',
        (tester) async {
      final _Api api = _Api(vendorCurrency: 'USD');
      _size(tester, const Size(1366, 768));
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: FxRevaluationDialog(api: api)),
      ));
      await tester.pumpAndSettle();
      await tester.enterText(
          find.byKey(const ValueKey('fx-rate-USD')), '84.5');
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('fx-post')));
      await tester.pumpAndSettle();

      final Json sent = api.bodies['POST /api/v1/finance/fx-revaluation']!;
      expect(sent.keys.toSet(), <String>{'as_of', 'rates'});
      expect(sent['rates'], {'USD': '84.5'});
      expect(find.byKey(const ValueKey('fx-result')), findsOneWidget);
      expect(find.textContaining('FXREV-20261031'), findsOneWidget);
      expect(find.textContaining('Net exchange loss ₹500.00'), findsOneWidget);
    });

    for (final Size size in _sizes) {
      testWidgets('the dialog has no overflow at ${size.width.toInt()}x'
          '${size.height.toInt()}', (tester) async {
        _size(tester, size);
        await tester.pumpWidget(MaterialApp(
          home: Scaffold(
              body: FxRevaluationDialog(api: _Api(vendorCurrency: 'USD'))),
        ));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
      });
    }
  });

  for (final Size size in _sizes) {
    testWidgets('the foreign bill and payment have no overflow at '
        '${size.width.toInt()}x${size.height.toInt()}', (tester) async {
      await _pumpBill(tester, _Api(), size);
      expect(tester.takeException(), isNull);
      await _pumpPayment(tester, _Api(), size);
      await tester.tap(find.byKey(const ValueKey('settlement-currency')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('USD').last);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  }
}
