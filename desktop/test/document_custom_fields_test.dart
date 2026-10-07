// MST-6: a firm's own custom fields on its documents.
//
// Three things carry the weight. The definition editor can aim a field at a
// document and mark it for print; a document editor offers the section only
// when the firm defined fields for that kind of document; and a document
// sends `attributes` only once the definitions have arrived and there are
// some -- absent leaves stored values alone, an empty list clears them.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/quotation.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/sales/sales_order_editor_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/first_line.dart';

ApplicableAttributesRecord _applicable(String entityType, {bool any = true}) =>
    ApplicableAttributesRecord.fromJson(<String, dynamic>{
      'entity_type': entityType,
      'definitions': <Json>[
        if (any)
          <String, dynamic>{
            'id': 'def-1',
            'code': 'PROJECT',
            'name': 'Project code',
            'entity_type': entityType,
            'data_type': 'TEXT',
            'is_active': true,
          },
      ],
      'mandatory_ids': const <String>[],
    });

class _SalesOrderApi extends ApiClient {
  _SalesOrderApi({this.defines = true})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool defines;
  final List<String> askedFor = <String>[];
  Json? created;

  @override
  Future<ApplicableAttributesRecord> applicableAttributeDefinitions(
    String entityType,
  ) async {
    askedFor.add(entityType);
    return _applicable(entityType, any: defines);
  }

  Json _paged(List<Json> rows) => <String, dynamic>{
        'data': rows,
        'pagination': <String, dynamic>{'total_records': rows.length},
      };

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
          'currency_code': 'INR',
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
          'mrp': '120',
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
    if (method == 'POST' && path == '/api/v1/sales-orders') {
      created = body;
      return <String, dynamic>{
        'data': <String, dynamic>{'id': 'so-1', 'order_number': 'SO-1'},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

class _PurchaseInvoiceApi extends ApiClient {
  _PurchaseInvoiceApi({this.defines = true})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool defines;
  final List<String> askedFor = <String>[];
  Json? sent;

  @override
  Future<ApplicableAttributesRecord> applicableAttributeDefinitions(
    String entityType,
  ) async {
    askedFor.add(entityType);
    return _applicable(entityType, any: defines);
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
  }) async =>
      {'data': const <Json>[]};

  @override
  Future<Json> createPurchaseInvoice(Json body) async {
    sent = body;
    return {
      'data': {'id': 'pi-1', 'invoice_number': 'PI-1', 'status': 'DRAFT'},
    };
  }
}

GoodsReceiptRecord _receipt() => GoodsReceiptRecord.fromJson({
      'id': 'grn-1',
      'grn_number': 'GRN-2026-000001',
      'receipt_date': '2026-08-10',
      'status': 'COMPLETED',
      'vendor_id': 'vendor-1',
      'vendor_name': 'Medico Distributors',
      'branch_id': 'branch-1',
      'lines': [
        {
          'id': 'grn-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'description': 'Amoxicillin 500mg',
          'accepted_quantity': '20',
          'unit_price': '25',
          'purchase_uom_id': 'uom-box',
          'warehouse_id': 'wh-1',
          'tax_profile_id': 'tax-1',
          'batch_number': 'MARCH-01',
        },
      ],
    });

Future<void> _openSalesOrder(WidgetTester tester, _SalesOrderApi api) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: SalesOrderEditorDialog(api: api, today: DateTime(2026, 8, 14)),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey<String>('sales-order-customer')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Anand Agencies').last);
  await tester.pumpAndSettle();
  // A new order starts with an empty line (D-UI-22), and one is needed to
  // save. It sits below the fold at this size.
  await tester.ensureVisible(
    find.byKey(const ValueKey<String>('sales-order-line-product-0')),
  );
  await tester.pumpAndSettle();
  await fillFirstLine(tester, document: 'sales-order', product: 'Shampoo');
}

Future<void> _openPurchaseInvoice(
  WidgetTester tester,
  _PurchaseInvoiceApi api,
) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: PurchaseInvoiceEditorDialog(
        api: api,
        receipts: [_receipt()],
        products: [
          Product.fromJson({
            'id': 'prod-1',
            'code': 'SKU-1',
            'name': 'Amoxicillin 500mg',
          }),
        ],
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.byType(DropdownButtonFormField<String>).first);
  await tester.pumpAndSettle();
  await tester.tap(find.text('GRN-2026-000001 • 2026-08-10').last);
  await tester.pumpAndSettle();
  Finder field(String label) => find.ancestor(
        of: find.text(label),
        matching: find.byType(TextFormField),
      );
  await tester.enterText(field('Supplier Invoice Number *'), 'SUP-778');
  await tester.enterText(field('Supplier Invoice Date *'), '2026-08-12');
  await tester.enterText(field('Invoice Date *'), '2026-08-13');
  await tester.pumpAndSettle();
}

void main() {
  group('the custom field definition editor', () {
    final definition = firmCustomFieldDefinition(
      _SalesOrderApi(),
      PermissionService(),
    );

    test('offers the six document types as places a field can sit', () {
      final spec =
          definition.fields.firstWhere((field) => field.key == 'entity_type');
      expect(
        spec.choices,
        containsAll(<String>[
          'QUOTATION',
          'SALES_ORDER',
          'DELIVERY_NOTE',
          'SALES_INVOICE',
          'PURCHASE_ORDER',
          'PURCHASE_INVOICE',
        ]),
      );
      expect(spec.choiceLabels?['SALES_ORDER'], 'Sales order');
      expect(spec.choiceLabels?['PURCHASE_INVOICE'], 'Purchase invoice');
    });

    test('sends show_on_print, and reads it back from the row', () {
      final row = AttributeDefinitionRecord.fromJson(const <String, dynamic>{
        'id': 'a',
        'code': 'PROJECT',
        'name': 'Project',
        'entity_type': 'SALES_ORDER',
        'data_type': 'TEXT',
        'show_on_print': true,
        'firm_id': 'firm-1',
      });
      expect(row.showOnPrint, isTrue);

      final values = definition.initialValues(row);
      expect(values['show_on_print'], isTrue);
      expect(definition.payload(values, false)['show_on_print'], isTrue);

      final fresh = definition.initialValues(null);
      expect(definition.payload(fresh, true)['show_on_print'], isFalse);
    });

    test('an older response without the flag reads as not printed', () {
      final row = AttributeDefinitionRecord.fromJson(const <String, dynamic>{
        'id': 'a',
        'code': 'A',
      });
      expect(row.showOnPrint, isFalse);
    });
  });

  group('the document models read attributes defensively', () {
    test('a quotation without them has none; one with them keeps them', () {
      expect(Quotation.fromJson(const <String, dynamic>{}).attributes, isEmpty);
      final quotation = Quotation.fromJson(<String, dynamic>{
        'attributes': [
          {
            'id': 'v1',
            'attribute_definition_id': 'def-1',
            'value_text': 'PRJ-1',
          },
          'not a map',
        ],
      });
      expect(quotation.attributes, hasLength(1));
      expect(quotation.attributes.single.valueText, 'PRJ-1');
    });
  });

  group('sales order editor', () {
    testWidgets('sends attributes once the definitions arrived',
        (tester) async {
      final api = _SalesOrderApi();
      await _openSalesOrder(tester, api);

      expect(api.askedFor, ['SALES_ORDER']);
      expect(find.text('Additional details'), findsOneWidget);
      await tester.enterText(
        find.byKey(const ValueKey<String>('attribute-def-1')),
        'PRJ-9',
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
      await tester.pumpAndSettle();

      expect(api.created!['attributes'], [
        {'attribute_definition_id': 'def-1', 'value': 'PRJ-9'},
      ]);
    });

    testWidgets('omits attributes, and the section, with no definitions',
        (tester) async {
      final api = _SalesOrderApi(defines: false);
      await _openSalesOrder(tester, api);

      expect(find.text('Additional details'), findsNothing);
      await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
      await tester.pumpAndSettle();

      expect(api.created, isNotNull);
      expect(api.created!.containsKey('attributes'), isFalse);
    });
  });

  group('purchase invoice editor', () {
    testWidgets('sends attributes once the definitions arrived',
        (tester) async {
      final api = _PurchaseInvoiceApi();
      await _openPurchaseInvoice(tester, api);

      expect(api.askedFor, ['PURCHASE_INVOICE']);
      expect(find.text('Additional details'), findsOneWidget);
      await tester.enterText(
        find.byKey(const ValueKey<String>('attribute-def-1')),
        'PRJ-4',
      );
      await tester.tap(find.text('Save Invoice'));
      await tester.pumpAndSettle();

      expect(api.sent!['attributes'], [
        {'attribute_definition_id': 'def-1', 'value': 'PRJ-4'},
      ]);
    });

    testWidgets('omits attributes, and the section, with no definitions',
        (tester) async {
      final api = _PurchaseInvoiceApi(defines: false);
      await _openPurchaseInvoice(tester, api);

      expect(find.text('Additional details'), findsNothing);
      await tester.tap(find.text('Save Invoice'));
      await tester.pumpAndSettle();

      expect(api.sent, isNotNull);
      expect(api.sent!.containsKey('attributes'), isFalse);
    });
  });
}
