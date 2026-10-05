// Backlog 87 row 4 (SG-4): other charges on the sales bill, each taxed by the
// server at its own profile. The desktop sends them and shows the priced
// answer; it never works the tax out itself.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/tax_framework.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _ChargesApi extends ApiClient {
  _ChargesApi({this.chargesTotal = '0', this.draftCharges = const <Json>[]})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String chargesTotal;
  final List<Json> draftCharges;
  final List<Json> created = <Json>[];
  final List<Json> previews = <Json>[];

  @override
  Future<PagedResult<TaxProfileRecord>> taxProfiles({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    String? taxSystemId,
    bool includeDeleted = false,
  }) async =>
      PagedResult<TaxProfileRecord>(
        items: <TaxProfileRecord>[
          TaxProfileRecord(
            id: 'tp-18',
            taxSystemId: 'ts',
            code: 'GST18',
            name: 'GST 18%',
            label: 'GST 18%',
            status: 'ACTIVE',
            isHistorical: false,
            isDeleted: false,
            components: const [],
          ),
        ],
        total: 1,
      );

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
    if (path.contains('workflow-settings')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'quotation_stage': false,
          'sales_order_stage': false,
          'delivery_note_stage': false,
          'default_warehouse_id': 'wh-main',
          'is_configured': true,
        },
      };
    }
    if (path.endsWith('/batch-serial/sale-settings')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'price_from_batch': false},
      };
    }
    if (method == 'GET' && path.startsWith('/api/v1/customers')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'cust-1',
            'code': 'C-1',
            'name': 'Walk-in Customer',
            'display_name': 'Walk-in Customer',
          },
        ],
      };
    }
    if (method == 'GET' && path.startsWith('/api/v1/products')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'prod-1',
            'code': 'P-1',
            'name': 'Soap',
            'barcode': '8901234567890',
            'selling_price': '50',
          },
        ],
      };
    }
    if (path.contains('billable')) return <String, dynamic>{'data': <Json>[]};
    if (method == 'GET' && path.startsWith('/api/v1/sales-invoices/inv-')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'id': 'inv-1',
          'status': 'DRAFT',
          'invoice_date': '2026-08-14',
          'customer_id': 'cust-1',
          'customer_name': 'Walk-in Customer',
          'branch_id': 'branch-1',
          'version': 1,
          'charges': draftCharges,
          'lines': <Json>[
            <String, dynamic>{
              'line_number': 1,
              'source_document_type': 'DELIVERY_NOTE',
              'source_document_id': 'dn-own',
              'source_document_number': 'DN-1',
              'source_document_line_id': 'dnl-1',
              'product_id': 'prod-1',
              'warehouse_id': 'wh-main',
              'description': 'Soap',
              'delivered_quantity': '1',
              'current_invoice_quantity': '1',
              'unit_price': '50',
              'discount_percent': '0',
            },
          ],
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/sales-invoices/preview') {
      previews.add(body!);
      return <String, dynamic>{
        'data': <String, dynamic>{
          'interstate': false,
          'invoice': <String, dynamic>{
            'invoice_number': 'SI-1',
            'subtotal': '50',
            'charges_total': chargesTotal,
            'tax_total': '18',
            'grand_total': '168',
            'charges': <Json>[
              <String, dynamic>{
                'name': 'Packing',
                'amount': chargesTotal,
                'tax_amount': '18',
              },
            ],
            'lines': const <Json>[],
          },
          'lines': const <Json>[],
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/sales-invoices') {
      created.add(body!);
      return <String, dynamic>{
        'data': <String, dynamic>{
          'id': 'inv-9',
          'invoice_number': 'SI-9',
          'status': 'DRAFT',
          'version': 1,
        },
      };
    }
    if (method == 'PUT' && path.startsWith('/api/v1/sales-invoices/inv-')) {
      created.add(body!);
      return <String, dynamic>{
        'data': <String, dynamic>{'id': 'inv-1', 'version': 2},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

Future<void> _pump(
  WidgetTester tester,
  _ChargesApi api, {
  String? invoiceId,
  Size size = const Size(1600, 900),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: SalesInvoiceEditorDialog(
          api: api,
          today: DateTime(2026, 8, 14),
          invoiceId: invoiceId,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _billOneProduct(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('sales-invoice-customer')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Walk-in Customer').last);
  await tester.pumpAndSettle();
  await tester.enterText(
      find.byKey(const ValueKey('counter-scan-field')), '8901234567890');
  await tester.testTextInput.receiveAction(TextInputAction.done);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _enter(WidgetTester tester, String key, String text) async {
  final Finder box = find.byKey(ValueKey<String>(key));
  await tester.ensureVisible(box);
  await tester.enterText(box, text);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _addCharge(WidgetTester tester) async {
  final Finder add = find.byKey(const ValueKey('sales-invoice-add-charge'));
  await tester.ensureVisible(add);
  await tester.tap(add);
  await tester.pumpAndSettle();
}

Future<void> _save(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a bill with no charges sends an empty list', (tester) async {
    final _ChargesApi api = _ChargesApi();
    await _pump(tester, api);
    await _billOneProduct(tester);
    await _save(tester);

    expect(api.created.single['charges'], isEmpty);
    expect(api.created.single.containsKey('charges'), isTrue);
  });

  testWidgets('a charge is sent, with its tax profile and SAC, and priced',
      (tester) async {
    final _ChargesApi api = _ChargesApi(chargesTotal: '100');
    await _pump(tester, api);
    await _billOneProduct(tester);
    await _addCharge(tester);
    await _enter(tester, 'sales-invoice-charge-name-0', 'Packing');
    await _enter(tester, 'sales-invoice-charge-amount-0', '100');
    await _enter(tester, 'sales-invoice-charge-sac-0', '998540');

    final Finder tax = find.byKey(const ValueKey('sales-invoice-charge-tax-0'));
    await tester.ensureVisible(tax);
    await tester.tap(tax);
    await tester.pumpAndSettle();
    await tester.tap(find.text('GST 18%').last);
    await tester.pumpAndSettle();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();

    // The preview carried it, and its answer shows beside the row and in
    // the totals.
    expect(api.previews.last['charges'], <Map<String, dynamic>>[
      <String, dynamic>{
        'name': 'Packing',
        'amount': '100',
        'tax_profile_id': 'tp-18',
        'hsn_sac': '998540',
      },
    ]);
    expect(find.textContaining('GST 18.00'), findsOneWidget);
    // The totals block: a Charges figure beside Taxable, from charges_total.
    expect(find.textContaining('Charges  '), findsOneWidget);
    expect(find.textContaining('100.00'), findsWidgets);

    await _save(tester);
    expect(api.created.single['charges'], <Map<String, dynamic>>[
      <String, dynamic>{
        'name': 'Packing',
        'amount': '100',
        'tax_profile_id': 'tp-18',
        'hsn_sac': '998540',
      },
    ]);
    expect(tester.takeException(), isNull);
  });

  testWidgets('an existing draft opens with its charges', (tester) async {
    final _ChargesApi api = _ChargesApi(
      chargesTotal: '100',
      draftCharges: <Json>[
        <String, dynamic>{
          'id': 'ch-1',
          'sequence': 1,
          'name': 'Installation',
          'hsn_sac': '995461',
          'amount': '100.0000',
          'tax_profile_id': 'tp-18',
        },
      ],
    );
    await _pump(tester, api, invoiceId: 'inv-1');

    String text(String key) => tester
        .widget<TextFormField>(find.byKey(ValueKey<String>(key)))
        .controller!
        .text;
    expect(text('sales-invoice-charge-name-0'), 'Installation');
    expect(text('sales-invoice-charge-amount-0'), '100.0000');
    expect(text('sales-invoice-charge-sac-0'), '995461');
    expect(find.byKey(const ValueKey('sales-invoice-charge-name-1')),
        findsNothing);
  });

  testWidgets('the tenth row disables Add and removing frees it',
      (tester) async {
    final _ChargesApi api = _ChargesApi();
    await _pump(tester, api);
    for (int i = 0; i < 10; i++) {
      await _addCharge(tester);
    }
    final Finder add = find.byKey(const ValueKey('sales-invoice-add-charge'));
    expect(find.byKey(const ValueKey('sales-invoice-charge-name-9')),
        findsOneWidget);
    expect(tester.widget<TextButton>(add).onPressed, isNull);

    final Finder remove =
        find.byKey(const ValueKey('sales-invoice-charge-remove-9'));
    await tester.ensureVisible(remove);
    await tester.tap(remove);
    await tester.pumpAndSettle();
    expect(tester.widget<TextButton>(add).onPressed, isNotNull);
  });

  testWidgets('the section fits the 800x600 window', (tester) async {
    final _ChargesApi api = _ChargesApi();
    await _pump(tester, api, size: const Size(800, 600));
    await _addCharge(tester);
    await _addCharge(tester);
    expect(tester.takeException(), isNull);
  });
}
