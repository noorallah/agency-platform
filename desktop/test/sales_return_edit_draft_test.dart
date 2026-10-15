// D-UI-39: a Draft sales return can be opened again and put right. A wrong
// quantity used to mean Cancel and a new document.
//
// The server replaces a Draft from the request -- header, lines, attachment
// records and notes -- so most of what is checked here is that the save
// sends back what the Draft held and the screen does not show.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/document_preview.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/sales_return.dart';
import 'package:agency_desktop/ui/sales_returns/sales_return_editor_dialog.dart';
import 'package:agency_desktop/ui/sales_returns/sales_return_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

const List<String> _mayEdit = [
  'SALES_VIEW',
  'SALES_RETURN',
  'SALES_UPDATE',
  'SALES_APPROVE',
  'SALES_CANCEL',
];

/// A return as the list answers it: two shampoo back off a bill of twelve,
/// one of them damaged, with what a header and a line can hold beyond what
/// the screen shows.
SalesReturn _return({
  String status = 'DRAFT',
  String returned = '2.0000',
  String free = '0.0000',
  String unitPrice = '195.0000',
  String sourceId = 'inv-1',
  List<Json> serials = const [],
}) =>
    SalesReturn.fromJson({
      'id': 'ret-1',
      'customer_id': 'cust-1',
      'customer_name': 'Anand Agencies',
      'branch_id': 'branch-1',
      'warehouse_id': 'wh-1',
      'business_profile_id': 'profile-1',
      'return_number': 'SR-2026-2027-000001',
      'return_date': '2026-08-10',
      'customer_return_number': 'CRN-9',
      'customer_return_date': '2026-08-09',
      'reference_delivery_note_number': 'DN-55',
      'reference_invoice_number': 'SI-OLD-8',
      'reference_number': 'PO-77',
      'return_reason': 'Damaged in transit',
      'currency_code': 'INR',
      'exchange_rate': '1.000000',
      'remarks': 'Collected by the van',
      'status': status,
      'total_current_return_quantity': returned,
      'total_restock_quantity': '1.0000',
      'subtotal': '390.0000',
      'tax_total': '70.2000',
      'additional_charges': '25.0000',
      'round_off': '-0.2000',
      'grand_total': '485.0000',
      'journal_entry_id': null,
      'cost_journal_entry_id': null,
      'cancel_reason': null,
      'version': 4,
      'lines': [
        {
          'id': 'line-1',
          'line_number': 1,
          'source_document_type': 'SALES_INVOICE',
          'source_document_id': sourceId,
          'source_document_number': 'SI-2026-2027-000008',
          'source_document_line_id': 'line-a',
          'source_document_line_number': 1,
          'product_id': 'prod-1',
          'description': 'Shampoo Bottle 180ml',
          'dispatched_quantity': '12.0000',
          'already_returned_quantity': '0.0000',
          'current_return_quantity': returned,
          'free_quantity': free,
          'restock_quantity': '1.0000',
          'damaged_quantity': '1.0000',
          'scrap_quantity': '0.0000',
          'reason_code': 'Damaged in transit',
          'item_condition': 'DENTED',
          'is_damaged': true,
          'is_expired': false,
          'unit_price': unitPrice,
          'discount_percent': '0.0000',
          'discount_amount': '0.0000',
          'charges_amount': '0.0000',
          'tax_profile_id': 'tax-18',
          'tax_amount': '70.2000',
          'net_amount': '460.2000',
          'sales_uom_id': 'u-bottle',
          'return_uom_id': null,
          'conversion_factor': '1.0000000000',
          'warehouse_id': 'wh-1',
          'batch_number': 'B-204',
          'expiry_date': '2027-03-31',
          'remarks': 'Crushed corner',
          'serials': serials,
        }
      ],
      'attachments': [
        {
          'id': 'att-1',
          'sales_return_id': 'ret-1',
          'file_name': 'photo.jpg',
          'mime_type': 'image/jpeg',
          'file_path': 'returns/photo.jpg',
          'attachment_kind': 'SALES_RETURN_FILE',
          'created_at': '2026-08-10T09:00:00Z',
          'updated_at': '2026-08-10T09:00:00Z',
        }
      ],
      'notes': [
        {
          'id': 'note-1',
          'note_type': 'INTERNAL',
          'note': 'Driver says the carton was wet.',
          'created_at': '2026-08-10T09:00:00Z',
          'updated_at': '2026-08-10T09:00:00Z',
        }
      ],
    });

/// The bill the goods went out on: twelve at 195.00, and one free where a
/// test asks for it.
ReturnableDocument _invoice({String free = '0'}) =>
    ReturnableDocument.fromSalesInvoice({
      'id': 'inv-1',
      'invoice_number': 'SI-2026-2027-000008',
      'invoice_date': '2026-08-04',
      'customer_id': 'cust-1',
      'customer_name': 'Anand Agencies',
      'status': 'APPROVED',
      'lines': [
        {
          'id': 'line-a',
          'line_number': 1,
          'product_id': 'prod-1',
          'description': 'Shampoo Bottle 180ml',
          'current_invoice_quantity': '12.0000',
          'free_quantity': free,
          'unit_price': '195.0000',
          'discount_percent': '0.0000',
        },
        {
          'id': 'line-b',
          'line_number': 2,
          'product_id': 'prod-2',
          'description': 'Soap 100g',
          'current_invoice_quantity': '6.0000',
          'unit_price': '30.0000',
          'discount_percent': '0.0000',
        },
      ],
    });

class _EditApi extends ApiClient {
  _EditApi({required this.rows, this.documents = const [], this.refusal})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<SalesReturn> rows;
  final List<ReturnableDocument> documents;

  /// When set, every save is refused with it.
  final ApiException? refusal;

  int listed = 0;
  String? updatedId;
  Json? updated;
  int? sentVersion;
  int updates = 0;
  int previews = 0;

  /// The Draft each preview was asked to price as replacing (D-UI-99).
  final List<String?> previewedAs = <String?>[];

  @override
  Future<SalesReturnPreviewRecord> previewSalesReturn(
    Json data, {
    String? replacing,
  }) async {
    previews += 1;
    previewedAs.add(replacing);
    return SalesReturnPreviewRecord.fromJson(<String, dynamic>{
      'sales_return': <String, dynamic>{
        'subtotal': '300.00',
        'tax_total': '54.00',
        'grand_total': '354.00',
        'round_off': '0.00',
        'lines': <Json>[],
      },
      'interstate': false,
      'lines': <Json>[],
    });
  }

  @override
  Future<PagedResult<SalesReturn>> salesReturns({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? status,
    String? returnFrom,
    String? returnTo,
  }) async {
    listed += 1;
    return PagedResult<SalesReturn>(items: rows, total: rows.length);
  }

  @override
  Future<List<ReturnableDocument>> returnableDocuments() async => documents;

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
            'firm_id': 'firm-1',
            'branch_id': 'branch-1',
            'code': 'WH-001',
            'name': 'Main',
            'display_name': 'Main warehouse',
            'status': 'ACTIVE',
          }),
        ],
        total: 1,
      );

  @override
  Future<ReturnableSerials> returnableSerials({
    required String sourceType,
    required String sourceLineId,
  }) async =>
      ReturnableSerials.untracked;

  @override
  Future<SalesReturn> updateSalesReturn(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    updates += 1;
    updatedId = id;
    updated = data;
    sentVersion = expectedVersion;
    final ApiException? refused = refusal;
    if (refused != null) throw refused;
    return rows.first;
  }
}

/// The phase 2 list. The scope sits above the app, as it does in the
/// product, so the editor the list opens is the phase 2 one too.
Future<void> _pump(
  WidgetTester tester,
  _EditApi api, {
  List<String> perms = _mayEdit,
  Size size = const Size(1366, 768),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    Phase2Scope(
      child: MaterialApp(
        home: Scaffold(
          body: SalesReturnManagementPage(
            api: api,
            preferences: DesktopPreferencesService(
              directory: Directory.systemTemp.createTempSync('return-edit'),
            ),
            permissions: _permissionsFor(perms),
            hasActiveFirm: true,
            today: DateTime(2026, 8, 14),
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester) async {
  await tester.tap(find.text('SR-2026-2027-000001').first);
  // Past the double-click window, which is when a click is a selection.
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

final Finder _edit = find.byKey(const ValueKey('selection-edit'));

Future<void> _openEdit(WidgetTester tester) async {
  await _select(tester);
  await tester.tap(_edit);
  await tester.pumpAndSettle();
}

String _cell(WidgetTester tester, String name) => tester
    .widget<EditableText>(find.descendant(
      of: find.byKey(ValueKey<String>('sales-return-$name-inv-1-0')),
      matching: find.byType(EditableText),
    ))
    .controller
    .text;

Json _line(Json payload) => (payload['lines'] as List).single as Json;

void main() {
  group('offering Edit', () {
    testWidgets('a Draft is offered Edit', (tester) async {
      await _pump(tester, _EditApi(rows: [_return()]));
      await _select(tester);

      expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
      expect(_edit, findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('an approved return is not', (tester) async {
      await _pump(tester, _EditApi(rows: [_return(status: 'APPROVED')]));
      await _select(tester);

      // The bar is there, with the return's other steps; Edit is not one.
      expect(find.byKey(const ValueKey('selection-complete')), findsOneWidget);
      expect(_edit, findsNothing);
    });

    testWidgets('nor is anybody without SALES_UPDATE', (tester) async {
      await _pump(
        tester,
        _EditApi(rows: [_return()]),
        perms: const ['SALES_VIEW', 'SALES_RETURN', 'SALES_APPROVE'],
      );
      await _select(tester);

      expect(find.byKey(const ValueKey('selection-approve')), findsOneWidget);
      expect(_edit, findsNothing);
    });

    testWidgets('the list still fits 800 by 600 with a Draft picked',
        (tester) async {
      await _pump(
        tester,
        _EditApi(rows: [_return()]),
        size: const Size(800, 600),
      );
      await _select(tester);

      expect(tester.takeException(), isNull);
    });
  });

  group('opening a Draft', () {
    testWidgets('the editor holds what the Draft holds', (tester) async {
      final _EditApi api =
          _EditApi(rows: [_return()], documents: [_invoice()]);
      await _pump(tester, api);
      await _openEdit(tester);

      expect(tester.takeException(), isNull);
      expect(find.byType(SalesReturnEditorDialog), findsOneWidget);
      expect(find.text('Edit sales return'), findsOneWidget);
      expect(find.text('New sales return'), findsNothing);
      expect(
        tester.widget<Text>(find.byKey(const ValueKey('document-number'))).data,
        'SR-2026-2027-000001',
      );
      expect(find.textContaining('(new)'), findsNothing);
      // Its document, fixed, and every line of it.
      expect(find.byKey(const ValueKey('sales-return-document-fixed')),
          findsOneWidget);
      expect(find.byKey(const ValueKey('sales-return-document')), findsNothing);
      expect(find.text('Soap 100g'), findsOneWidget);
      // The figures as stored, written as somebody would type them.
      expect(_cell(tester, 'returning'), '2');
      expect(_cell(tester, 'damaged'), '1');
      expect(_cell(tester, 'scrap'), '0');
      expect(find.widgetWithText(TextFormField, 'CRN-9'), findsOneWidget);
      expect(find.widgetWithText(TextFormField, 'Damaged in transit'),
          findsOneWidget);
      expect(find.widgetWithText(TextFormField, 'Collected by the van'),
          findsOneWidget);
      // Its own figures, as the server priced them when it was saved.
      expect(find.textContaining('485.00', findRichText: true), findsWidgets);
    });

    testWidgets('saved with nothing changed, it sends the Draft back whole',
        (tester) async {
      final _EditApi api =
          _EditApi(rows: [_return()], documents: [_invoice()]);
      await _pump(tester, api);
      await _openEdit(tester);
      await tester.tap(find.byKey(const ValueKey('sales-return-save')));
      await tester.pumpAndSettle();

      expect(api.updates, 1);
      expect(api.updatedId, 'ret-1');
      expect(api.sentVersion, 4);
      final Json sent = api.updated!;
      // Its own day, not the 14th it was opened on.
      expect(sent['return_date'], '2026-08-10');
      expect(sent['warehouse_id'], 'wh-1');
      expect(sent['customer_return_number'], 'CRN-9');
      expect(sent['return_reason'], 'Damaged in transit');
      expect(sent['remarks'], 'Collected by the van');
      // What the screen does not show, which the server would clear.
      expect(sent['customer_return_date'], '2026-08-09');
      expect(sent['reference_delivery_note_number'], 'DN-55');
      expect(sent['reference_invoice_number'], 'SI-OLD-8');
      expect(sent['reference_number'], 'PO-77');
      expect(sent['currency_code'], 'INR');
      expect(sent['exchange_rate'], '1.000000');
      expect(sent['business_profile_id'], 'profile-1');
      expect(sent['additional_charges'], '25.0000');
      expect(sent['round_off'], '-0.2000');
      // Only the fields the write model declares: an id would be refused.
      expect(sent['attachments'], [
        {
          'file_name': 'photo.jpg',
          'mime_type': 'image/jpeg',
          'file_path': 'returns/photo.jpg',
          'attachment_kind': 'SALES_RETURN_FILE',
        }
      ]);
      expect(sent['notes'], [
        {'note_type': 'INTERNAL', 'note': 'Driver says the carton was wet.'}
      ]);

      final Json line = _line(sent);
      expect(line['source_document_type'], 'SALES_INVOICE');
      expect(line['source_document_id'], 'inv-1');
      expect(line['source_document_line_id'], 'line-a');
      expect(line['current_return_quantity'], '2');
      expect(line['damaged_quantity'], '1');
      expect(line['scrap_quantity'], '0');
      expect(line['reason_code'], 'Damaged in transit');
      expect(line['item_condition'], 'DENTED');
      expect(line['is_damaged'], true);
      expect(line['tax_profile_id'], 'tax-18');
      expect(line['batch_number'], 'B-204');
      expect(line['expiry_date'], '2027-03-31');
      expect(line['remarks'], 'Crushed corner');
      expect(line['serial_ids'], isEmpty);
      // A figure sent is a figure typed. The price is the bill's, nothing
      // free came back and the line sits in the return's own warehouse, so
      // none of them is said.
      expect(line.containsKey('unit_price'), isFalse);
      expect(line.containsKey('discount_percent'), isFalse);
      expect(line.containsKey('free_quantity'), isFalse);
      expect(line.containsKey('restock_quantity'), isFalse);
      expect(line.containsKey('warehouse_id'), isFalse);

      // The list was read again and the return is still the one picked.
      expect(api.listed, 2);
      expect(find.byType(SalesReturnEditorDialog), findsNothing);
      expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
      expect(find.textContaining('SR-2026-2027-000001 saved'), findsOneWidget);
    });

    testWidgets('a quantity put right goes with everything else it held',
        (tester) async {
      final _EditApi api =
          _EditApi(rows: [_return()], documents: [_invoice()]);
      await _pump(tester, api);
      await _openEdit(tester);
      await tester.enterText(
        find.byKey(const ValueKey<String>('sales-return-returning-inv-1-0')),
        '3',
      );
      // Past the pause after typing, so the preview has been asked.
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();
      // Priced as it is typed, as replacing the Draft (D-UI-99); nothing
      // says the figures wait for the save any more.
      expect(api.previews, greaterThan(0));
      expect(find.textContaining('worked out when this is saved'),
          findsNothing);
      await tester.tap(find.byKey(const ValueKey('sales-return-save')));
      await tester.pumpAndSettle();

      final Json sent = api.updated!;
      expect(_line(sent)['current_return_quantity'], '3');
      expect(_line(sent)['damaged_quantity'], '1');
      expect(sent['return_date'], '2026-08-10');
      expect(sent['reference_number'], 'PO-77');
      expect(sent['notes'], hasLength(1));
      expect(api.sentVersion, 4);
    });

    testWidgets('a changed Draft is priced as replacing itself',
        (tester) async {
      final _EditApi api =
          _EditApi(rows: [_return()], documents: [_invoice()]);
      await _pump(tester, api);
      await _openEdit(tester);
      await tester.enterText(
        find.byKey(const ValueKey<String>('sales-return-returning-inv-1-0')),
        '3',
      );
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();

      // D-UI-99: the preview named the Draft, so its own five do not count
      // against the line, and the totals are the server's.
      expect(api.previewedAs, isNotEmpty);
      expect(api.previewedAs, everyElement('ret-1'));
      expect(find.textContaining('354'), findsWidgets);
    });

    testWidgets('free goods a Draft brought back stay free', (tester) async {
      // Thirteen back off twelve charged and one free. The server keeps one
      // free figure, typed or worked out, so it is sent back as it stands.
      final _EditApi api = _EditApi(
        rows: [_return(returned: '13.0000', free: '1.0000')],
        documents: [_invoice(free: '1.0000')],
      );
      await _pump(tester, api);
      await _openEdit(tester);

      expect(_cell(tester, 'returning'), '13');
      expect(_cell(tester, 'free'), '1');
      await tester.tap(find.byKey(const ValueKey('sales-return-save')));
      await tester.pumpAndSettle();
      expect(_line(api.updated!)['current_return_quantity'], '13');
      expect(_line(api.updated!)['free_quantity'], '1');
    });

    testWidgets('a price typed on the Draft is sent, the bill\'s own is not',
        (tester) async {
      final _EditApi api = _EditApi(
        rows: [_return(unitPrice: '150.0000')],
        documents: [_invoice()],
      );
      await _pump(tester, api);
      await _openEdit(tester);
      await tester.tap(find.byKey(const ValueKey('sales-return-save')));
      await tester.pumpAndSettle();

      expect(_line(api.updated!)['unit_price'], '150.0000');
    });

    testWidgets('the units a line picked are sent with it', (tester) async {
      final _EditApi api = _EditApi(
        rows: [
          _return(serials: [
            {'serial_id': 'sn-1', 'serial_number': 'IMEI-1', 'status': 'SOLD'},
            {'serial_id': 'sn-2', 'serial_number': 'IMEI-2', 'status': 'SOLD'},
          ]),
        ],
        documents: [_invoice()],
      );
      await _pump(tester, api);
      await _openEdit(tester);
      await tester.tap(find.byKey(const ValueKey('sales-return-save')));
      await tester.pumpAndSettle();

      expect(_line(api.updated!)['serial_ids'],
          unorderedEquals(<String>['sn-1', 'sn-2']));
    });

    testWidgets('a refusal keeps the window open with the sentence',
        (tester) async {
      final _EditApi api = _EditApi(
        rows: [_return()],
        documents: [_invoice()],
        refusal: const ApiException(
          'This record was changed by someone else. Reload it and try again.',
          statusCode: 409,
        ),
      );
      await _pump(tester, api);
      await _openEdit(tester);
      await tester.enterText(
        find.byKey(const ValueKey<String>('sales-return-returning-inv-1-0')),
        '5',
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('sales-return-save')));
      await tester.pumpAndSettle();

      expect(api.updates, 1);
      expect(find.byType(SalesReturnEditorDialog), findsOneWidget);
      expect(find.textContaining('changed by someone else'), findsOneWidget);
      expect(_cell(tester, 'returning'), '5');
      // Nothing was saved, so the list was not read again.
      expect(api.listed, 1);
    });

    testWidgets('a document no longer returnable is said, not opened empty',
        (tester) async {
      final _EditApi api = _EditApi(rows: [_return()]);
      await _pump(tester, api);
      await _openEdit(tester);

      expect(find.byType(SalesReturnEditorDialog), findsNothing);
      expect(
        find.textContaining('was raised against SI-2026-2027-000008, which is '
            'not among the documents goods can come back against now'),
        findsOneWidget,
      );
    });
  });

  group('what cannot be edited here', () {
    test('a line typed in a unit of its own', () {
      final SalesReturn draft = SalesReturn.fromJson({
        'return_number': 'SR-9',
        'lines': [
          {
            'line_number': 1,
            'source_document_type': 'SALES_INVOICE',
            'source_document_id': 'inv-1',
            'source_document_line_id': 'line-a',
            'current_return_quantity': '0.5833',
            'entered_quantity': '7.0000',
            'return_uom_id': 'u-pc',
            'sales_uom_id': 'u-box',
          }
        ],
      });
      expect(salesReturnEditRefusal(draft, [_invoice()]),
          contains('typed in another unit'));
    });

    test('a return against more than one document', () {
      final SalesReturn draft = SalesReturn.fromJson({
        'return_number': 'SR-9',
        'lines': [
          for (final String id in const ['inv-1', 'inv-2'])
            {
              'source_document_type': 'SALES_INVOICE',
              'source_document_id': id,
              'source_document_number': id,
              'source_document_line_id': 'line-a',
            },
        ],
      });
      expect(salesReturnEditRefusal(draft, [_invoice()]),
          contains('more than one document'));
    });

    test('a Draft the editor can hold is not refused', () {
      expect(salesReturnEditRefusal(_return(), [_invoice()]), isNull);
    });
  });
}
