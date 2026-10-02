// Backlog 77.1, desktop half: a sale's tax invoice should exist before the
// goods leave.
//
// These pin: the delivery note editor sends its challan reason (and the words
// with Other); dispatching asks the server's dispatch check first, offers
// three choices under WARN and no "Dispatch anyway" under BLOCK; "Dispatch and
// invoice" calls its own route; and the GST documents settings load and PUT
// exactly the seven keys the server declares.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/inventory.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/delivery_notes/delivery_note_editor_dialog.dart';
import 'package:agency_desktop/ui/delivery_notes/delivery_note_management_page.dart';
import 'package:agency_desktop/ui/tax/gst_documents_settings_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

const String _warnMessage =
    'DN-0001 is a sale with no invoice yet. GST law wants the tax invoice '
    'before the goods leave.';

class _GstApi extends ApiClient {
  _GstApi({
    this.enforcement = 'WARN',
    this.message = _warnMessage,
    this.storedDispatch = 'OFF',
  })
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String enforcement;
  final String? message;

  /// What the settings read says about dispatch before invoice.
  final String storedDispatch;

  /// Every call the screens made, as `METHOD path`.
  final List<String> calls = <String>[];
  Json? savedSettings;
  String filingProvider = 'SANDBOX';
  String? savedProvider;
  Json? createdNote;

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
    calls.add('$method $path');
    if (path.endsWith('/dispatch-check')) {
      return {
        'data': {
          'enforcement': enforcement,
          'message': message,
          'would_block': enforcement == 'BLOCK' && message != null,
        },
      };
    }
    if (path.endsWith('/dispatch-and-invoice')) {
      return {
        'message': 'Dispatched and invoiced as INV-0007.',
        'data': {'id': 'inv-1'},
      };
    }
    if (path == '/api/v1/einvoice/settings') {
      if (method == 'PUT') {
        savedProvider = body?['provider'] as String?;
        filingProvider = savedProvider ?? filingProvider;
      }
      return {
        'data': {
          'provider': filingProvider,
          'available': ['SANDBOX', 'OFFLINE'],
        },
      };
    }
    if (path.endsWith('/gst-compliance-settings')) {
      if (method == 'PUT') {
        savedSettings = Map<String, dynamic>.from(body ?? const {});
        return {
          'data': {...?body, 'is_configured': true},
        };
      }
      return {
        'data': {
          'einvoice_applicable_from': '2026-04-01',
          'thirty_day_rule_from': null,
          'dispatch_without_invoice': storedDispatch,
          'route_sale_needs_invoice': false,
          'is_configured': false,
        },
      };
    }
    if (method == 'GET' && path == '/api/v1/delivery-notes/summary') {
      return {
        'data': {'total': 1, 'approved': 1},
      };
    }
    if (method == 'GET' && path == '/api/v1/delivery-notes') {
      return {
        'data': <Json>[
          {
            'id': 'dn-1',
            'delivery_note_number': 'DN-0001',
            'customer_name': 'Customer 1',
            'delivery_date': '2026-08-10',
            'status': 'APPROVED',
            'grand_total': '1000.00',
            'challan_reason': 'ROUTE_SALE',
            'version': 1,
          },
        ],
        'pagination': {'total_records': 1},
      };
    }
    return {'data': <dynamic>[]};
  }

  @override
  Future<Json> create(String resource, Json body) async {
    createdNote = body;
    return {
      'data': {'id': 'dn-9', 'delivery_note_number': 'DN-9', 'status': 'DRAFT'},
    };
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
      // The editor asks for earlier notes against the order; the list asks for
      // the notes themselves.
      resource == 'delivery-notes' && sortBy == 'delivery_date'
          ? await request('GET', '/api/v1/delivery-notes')
          : const <String, dynamic>{'data': <dynamic>[]};

  @override
  Future<PagedResult<InventoryRecord>> inventory({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    InventoryQuery filters = const InventoryQuery(),
  }) async =>
      const PagedResult<InventoryRecord>(items: [], total: 0);
}

Future<void> _pumpPage(
  WidgetTester tester,
  _GstApi api, {
  List<String> codes = const ['SALES_VIEW', 'SALES_APPROVE', 'SALES_CREATE'],
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory dir = Directory.systemTemp.createTempSync('gst-dispatch');
  addTearDown(() => dir.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: DeliveryNoteManagementPage(
          api: api,
          preferences: DesktopPreferencesService(directory: dir),
          permissions: _permissions(codes),
          hasActiveFirm: true,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  // A tap waits out a possible double-tap before it selects.
  await tester.tap(find.text('DN-0001'));
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

Future<void> _tapDispatch(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('selection-dispatch')));
  await tester.pumpAndSettle();
}

Future<void> _pumpSettings(
  WidgetTester tester,
  _GstApi api,
  List<String> codes,
) async {
  tester.view.physicalSize = const Size(800, 600);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: GstDocumentsSettingsDialog(
        api: api,
        permissions: _permissions(codes),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _openEditor(WidgetTester tester, _GstApi api) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: DeliveryNoteEditorDialog(
          api: api,
          salesOrders: [
            {
              'id': 'so-1',
              'order_number': 'SO-0001',
              'order_date': '2026-08-01',
              'warehouse_id': 'wh-1',
              'status': 'APPROVED',
              'lines': [
                {
                  'id': 'so-line-1',
                  'line_number': 1,
                  'product_id': 'prod-1',
                  'description': 'Amoxicillin',
                  'quantity': '10',
                  'reserved_quantity': '10',
                  'unit_price': '40',
                  'sales_uom_id': 'uom-box',
                  'warehouse_id': 'wh-1',
                },
              ],
            },
          ],
          warehouses: [
            WarehouseRecord.fromJson(
              {'id': 'wh-1', 'code': 'MAIN', 'name': 'Main Warehouse'},
            ),
          ],
          products: [
            Product.fromJson(
              {'id': 'prod-1', 'code': 'SKU-1', 'name': 'Amoxicillin'},
            ),
          ],
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('delivery-note-order')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('SO-0001').last);
  await tester.pumpAndSettle();
}

void main() {
  group('the delivery note editor', () {
    testWidgets('sends Sale as the reason by default', (tester) async {
      final _GstApi api = _GstApi();
      await _openEditor(tester, api);
      expect(find.text('Say why'), findsNothing);

      await tester.tap(find.byKey(const ValueKey('delivery-note-save')));
      await tester.pumpAndSettle();

      expect(api.createdNote?['challan_reason'], 'SALE');
      expect(api.createdNote?.containsKey('challan_reason_note'), isFalse);
    });

    testWidgets('sends Other with the words typed', (tester) async {
      final _GstApi api = _GstApi();
      await _openEditor(tester, api);

      await tester.tap(
        find.byKey(const ValueKey('delivery-note-challan-reason')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Other').last);
      await tester.pumpAndSettle();
      expect(find.text('Say why'), findsOneWidget);
      await tester.enterText(
        find.byKey(const ValueKey('delivery-note-challan-reason-note')),
        'Samples for a trade fair',
      );
      await tester.tap(find.byKey(const ValueKey('delivery-note-save')));
      await tester.pumpAndSettle();

      expect(api.createdNote?['challan_reason'], 'OTHER');
      expect(
        api.createdNote?['challan_reason_note'],
        'Samples for a trade fair',
      );
    });
  });

  group('dispatching', () {
    testWidgets('with nothing to say the note is dispatched as before',
        (tester) async {
      final _GstApi api = _GstApi(message: null);
      await _pumpPage(tester, api);
      await _tapDispatch(tester);

      expect(find.text('Dispatch anyway'), findsNothing);
      expect(api.calls, contains('GET /api/v1/delivery-notes/dn-1/dispatch-check'));
      expect(api.calls, contains('POST /api/v1/delivery-notes/dn-1/dispatch'));
    });

    testWidgets('under WARN three choices are offered and Dispatch anyway goes',
        (tester) async {
      final _GstApi api = _GstApi();
      await _pumpPage(tester, api);
      await _tapDispatch(tester);

      expect(find.text(_warnMessage), findsOneWidget);
      expect(find.text('Dispatch and invoice'), findsWidgets);
      expect(find.byKey(const ValueKey('dispatch-anyway')), findsOneWidget);
      expect(find.byKey(const ValueKey('dispatch-cancel')), findsOneWidget);
      expect(api.calls.any((call) => call.endsWith('/dispatch')), isFalse);

      await tester.tap(find.byKey(const ValueKey('dispatch-anyway')));
      await tester.pumpAndSettle();

      expect(api.calls, contains('POST /api/v1/delivery-notes/dn-1/dispatch'));
    });

    testWidgets('Cancel dispatches nothing', (tester) async {
      final _GstApi api = _GstApi();
      await _pumpPage(tester, api);
      await _tapDispatch(tester);
      await tester.tap(find.byKey(const ValueKey('dispatch-cancel')));
      await tester.pumpAndSettle();

      expect(api.calls.any((call) => call.startsWith('POST')), isFalse);
    });

    testWidgets('under BLOCK there is no Dispatch anyway', (tester) async {
      final _GstApi api = _GstApi(enforcement: 'BLOCK');
      await _pumpPage(tester, api);
      await _tapDispatch(tester);

      expect(find.text(_warnMessage), findsOneWidget);
      expect(find.byKey(const ValueKey('dispatch-anyway')), findsNothing);
      expect(find.byKey(const ValueKey('dispatch-and-invoice')), findsOneWidget);
      expect(find.byKey(const ValueKey('dispatch-cancel')), findsOneWidget);
    });

    testWidgets('the dialog\'s Dispatch and invoice calls its route',
        (tester) async {
      final _GstApi api = _GstApi();
      await _pumpPage(tester, api);
      await _tapDispatch(tester);
      await tester.tap(find.byKey(const ValueKey('dispatch-and-invoice')));
      await tester.pumpAndSettle();

      expect(
        api.calls,
        contains('POST /api/v1/delivery-notes/dn-1/dispatch-and-invoice'),
      );
      expect(api.calls.contains('POST /api/v1/delivery-notes/dn-1/dispatch'),
          isFalse);
      expect(find.text('Dispatched and invoiced as INV-0007.'), findsOneWidget);
    });

    testWidgets('an approved note offers Dispatch and invoice directly',
        (tester) async {
      final _GstApi api = _GstApi();
      await _pumpPage(tester, api);
      await tester.tap(
        find.byKey(const ValueKey('selection-dispatch-and-invoice')),
      );
      await tester.pumpAndSettle();

      expect(
        api.calls,
        contains('POST /api/v1/delivery-notes/dn-1/dispatch-and-invoice'),
      );
      expect(api.calls.any((call) => call.endsWith('/dispatch-check')), isFalse);
    });

    testWidgets('without SALES_CREATE the direct action is disabled',
        (tester) async {
      final _GstApi api = _GstApi();
      await _pumpPage(tester, api, codes: const ['SALES_VIEW', 'SALES_APPROVE']);

      final Finder action =
          find.byKey(const ValueKey('selection-dispatch-and-invoice'));
      if (action.evaluate().isNotEmpty) {
        final Widget widget = tester.widget(action);
        expect(
          widget is ButtonStyleButton ? widget.onPressed : null,
          isNull,
        );
      }
    });

    testWidgets('the note\'s view says why the goods go out', (tester) async {
      final _GstApi api = _GstApi();
      await _pumpPage(tester, api);
      await tester.tap(find.byKey(const ValueKey('selection-view')));
      await tester.pumpAndSettle();

      expect(find.textContaining('Van or route sale'), findsWidgets);
    });
  });

  group('the GST documents settings', () {
    testWidgets('load, and save exactly the seven keys', (tester) async {
      final _GstApi api = _GstApi();
      await _pumpSettings(tester, api, ['TAX_VIEW', 'TAX_MANAGE_SETTINGS']);
      expect(tester.takeException(), isNull);
      expect(find.text('2026-04-01'), findsOneWidget);

      // The 800x600 window scrolls the dialog's body.
      await tester.ensureVisible(
        find.byKey(const ValueKey('gst-dispatch-policy')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('gst-dispatch-policy')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Block').last);
      await tester.pumpAndSettle();
      await tester.ensureVisible(
        find.byKey(const ValueKey('gst-route-sale-needs-invoice')),
      );
      await tester.pumpAndSettle();
      await tester.tap(
        find.byKey(const ValueKey('gst-route-sale-needs-invoice')),
      );
      await tester.pumpAndSettle();
      // The e-way bill limit loads as the server's default and is editable.
      await tester.ensureVisible(find.byKey(const ValueKey('gst-eway-limit')));
      await tester.pumpAndSettle();
      expect(find.text('50000'), findsOneWidget);
      await tester.enterText(
        find.byKey(const ValueKey('gst-eway-limit')),
        '75000',
      );
      await tester.tap(find.byKey(const ValueKey('gst-settings-save')));
      await tester.pumpAndSettle();

      expect(api.savedSettings, {
        'einvoice_applicable_from': '2026-04-01',
        'thirty_day_rule_from': null,
        'dispatch_without_invoice': 'BLOCK',
        'route_sale_needs_invoice': true,
        'itc_claim_basis': 'ALL',
        'gstr2b_tolerance': '1.00',
        'eway_bill_limit': '75000',
      });
    });

    testWidgets('the e-invoice filing choice saves through its own call',
        (tester) async {
      final _GstApi api = _GstApi();
      await _pumpSettings(tester, api, ['TAX_VIEW', 'TAX_MANAGE_SETTINGS']);
      await tester.ensureVisible(
        find.byKey(const ValueKey('einvoice-filing-provider')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('einvoice-filing-provider')));
      await tester.pumpAndSettle();
      await tester.tap(
        find.text('Offline: upload on the e-invoice portal').last,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('gst-settings-save')));
      await tester.pumpAndSettle();

      expect(api.savedProvider, 'OFFLINE');
      expect(api.savedSettings?.containsKey('provider'), isFalse);
    });

    testWidgets('a value the screen does not know reads as the server default',
        (tester) async {
      // The server defaults to WARN; starting the box at Off claimed a
      // policy nobody chose (D-UI-1).
      final _GstApi api = _GstApi(storedDispatch: 'SOMETHING_NEW');
      await _pumpSettings(tester, api, ['TAX_VIEW', 'TAX_MANAGE_SETTINGS']);
      await tester.ensureVisible(
        find.byKey(const ValueKey('gst-dispatch-policy')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('gst-settings-save')));
      await tester.pumpAndSettle();

      expect(api.savedSettings?['dispatch_without_invoice'], 'WARN');
    });

    testWidgets('without TAX_MANAGE_SETTINGS nothing can be saved',
        (tester) async {
      final _GstApi api = _GstApi();
      await _pumpSettings(tester, api, ['TAX_VIEW']);

      final FilledButton save = tester.widget(
        find.byKey(const ValueKey('gst-settings-save')),
      );
      expect(save.onPressed, isNull);
    });
  });
}
