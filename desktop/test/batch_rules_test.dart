// Backlog 79 row 6, desktop half: the firm's batch rules.
//
// These pin: the Batch rules dialog loads, saves exactly the four keys the
// server declares and is read-only without SALES_MANAGE_SETTINGS; dispatching
// asks the batch check first and sends the reason as `batch_reason` when a
// rule needs one; cancelling dispatches nothing; and a price-floor finding
// that is exempt reads as allowed.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/inventory.dart';
import 'package:agency_desktop/models/price_floor.dart';
import 'package:agency_desktop/ui/delivery_notes/delivery_note_management_page.dart';
import 'package:agency_desktop/ui/sales/price_floor_check_dialog.dart';
import 'package:agency_desktop/ui/stock/batch_sale_settings_dialog.dart';
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

const String _findingText =
    'Line 1: batch B-1 expires in 10 days and is left behind.';

class _BatchApi extends ApiClient {
  _BatchApi({this.findings = false, this.needsReason = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool findings;
  final bool needsReason;

  final List<String> calls = <String>[];
  final List<Map<String, String>?> queries = <Map<String, String>?>[];
  Json? savedSettings;

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
    queries.add(query);
    if (path.endsWith('/batch-check')) {
      return {
        'data': {
          'findings': findings
              ? [
                  {
                    'line_number': 1,
                    'kind': 'NEAR_EXPIRY',
                    'message': _findingText,
                  },
                ]
              : <Json>[],
          'needs_reason': needsReason,
          'message': findings ? _findingText : null,
        },
      };
    }
    if (path.endsWith('/dispatch-check')) {
      return {
        'data': {'enforcement': 'OFF', 'message': null, 'would_block': false},
      };
    }
    if (path.endsWith('/batch-serial/sale-settings')) {
      if (method == 'PUT') {
        savedSettings = Map<String, dynamic>.from(body ?? const {});
        return {
          'data': {...?body, 'is_configured': true},
        };
      }
      return {
        'data': {
          'near_expiry_days': 45,
          'near_expiry_policy': 'WARN',
          'fefo_skip_policy': 'RECORD',
          'near_expiry_below_floor': true,
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
            'challan_reason': 'SALE',
            'version': 1,
          },
        ],
        'pagination': {'total_records': 1},
      };
    }
    return {'data': <dynamic>[]};
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

  /// The query sent with the one POST to [suffix], or null.
  Map<String, String>? queryOf(String suffix) {
    final int index =
        calls.indexWhere((call) => call.startsWith('POST') && call.endsWith(suffix));
    return index < 0 ? null : queries[index];
  }
}

Future<void> _pumpPage(WidgetTester tester, _BatchApi api) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory dir = Directory.systemTemp.createTempSync('batch-rules');
  addTearDown(() => dir.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: DeliveryNoteManagementPage(
          api: api,
          preferences: DesktopPreferencesService(directory: dir),
          permissions:
              _permissions(const ['SALES_VIEW', 'SALES_APPROVE', 'SALES_CREATE']),
          hasActiveFirm: true,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
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
  _BatchApi api,
  List<String> codes,
) async {
  tester.view.physicalSize = const Size(800, 700);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: BatchSaleSettingsDialog(
        api: api,
        permissions: _permissions(codes),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  group('the Batch rules dialog', () {
    testWidgets('loads, and saves exactly the four keys', (tester) async {
      final _BatchApi api = _BatchApi();
      await _pumpSettings(tester, api, ['SALES_VIEW', 'SALES_MANAGE_SETTINGS']);
      expect(tester.takeException(), isNull);
      expect(find.text('45'), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('batch-rules-near-expiry')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Need a reason').last);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('batch-rules-below-floor')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('batch-rules-save')));
      await tester.pumpAndSettle();

      expect(api.savedSettings, {
        'near_expiry_days': 45,
        'near_expiry_policy': 'REASON',
        'fefo_skip_policy': 'RECORD',
        'near_expiry_below_floor': false,
      });
    });

    testWidgets('a window outside 0 to 730 is not sent', (tester) async {
      final _BatchApi api = _BatchApi();
      await _pumpSettings(tester, api, ['SALES_VIEW', 'SALES_MANAGE_SETTINGS']);
      await tester.enterText(
        find.byKey(const ValueKey('batch-rules-days')),
        '900',
      );
      await tester.tap(find.byKey(const ValueKey('batch-rules-save')));
      await tester.pumpAndSettle();

      expect(api.savedSettings, isNull);
      expect(find.text('Enter a whole number from 0 to 730.'), findsOneWidget);
    });

    testWidgets('without SALES_MANAGE_SETTINGS nothing can be saved',
        (tester) async {
      final _BatchApi api = _BatchApi();
      await _pumpSettings(tester, api, ['SALES_VIEW']);

      final FilledButton save =
          tester.widget(find.byKey(const ValueKey('batch-rules-save')));
      expect(save.onPressed, isNull);
    });
  });

  group('dispatching under the batch rules', () {
    testWidgets('no findings: dispatched with no reason', (tester) async {
      final _BatchApi api = _BatchApi();
      await _pumpPage(tester, api);
      await _tapDispatch(tester);

      expect(api.calls, contains('GET /api/v1/delivery-notes/dn-1/batch-check'));
      expect(api.calls, contains('POST /api/v1/delivery-notes/dn-1/dispatch'));
      expect(api.queryOf('/dispatch'), isNull);
    });

    testWidgets('a rule that needs a reason asks, and sends it',
        (tester) async {
      final _BatchApi api = _BatchApi(findings: true, needsReason: true);
      await _pumpPage(tester, api);
      await _tapDispatch(tester);

      expect(find.textContaining(_findingText), findsOneWidget);
      expect(api.calls.any((call) => call.startsWith('POST')), isFalse);

      await tester.enterText(find.descendant(of: find.byType(AlertDialog), matching: find.byType(TextField)), 'Customer asked for it');
      await tester.tap(find.text('Dispatch').last);
      await tester.pumpAndSettle();

      expect(api.queryOf('/dispatch'), {'batch_reason': 'Customer asked for it'});
    });

    testWidgets('dismissing the reason prompt dispatches nothing',
        (tester) async {
      final _BatchApi api = _BatchApi(findings: true, needsReason: true);
      await _pumpPage(tester, api);
      await _tapDispatch(tester);
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      expect(api.calls.any((call) => call.startsWith('POST')), isFalse);
    });

    testWidgets('a warning only is a Continue or Cancel, with no reason',
        (tester) async {
      final _BatchApi api = _BatchApi(findings: true);
      await _pumpPage(tester, api);
      await _tapDispatch(tester);

      expect(find.text(_findingText), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('batch-check-continue')));
      await tester.pumpAndSettle();

      expect(api.calls, contains('POST /api/v1/delivery-notes/dn-1/dispatch'));
      expect(api.queryOf('/dispatch'), isNull);
    });

    testWidgets('Cancel on a warning dispatches nothing', (tester) async {
      final _BatchApi api = _BatchApi(findings: true);
      await _pumpPage(tester, api);
      await _tapDispatch(tester);
      await tester.tap(find.byKey(const ValueKey('batch-check-cancel')));
      await tester.pumpAndSettle();

      expect(api.calls.any((call) => call.startsWith('POST')), isFalse);
    });

    testWidgets('Dispatch and invoice sends the reason too', (tester) async {
      final _BatchApi api = _BatchApi(findings: true, needsReason: true);
      await _pumpPage(tester, api);
      await tester.tap(
        find.byKey(const ValueKey('selection-dispatch-and-invoice')),
      );
      await tester.pumpAndSettle();
      await tester.enterText(find.descendant(of: find.byType(AlertDialog), matching: find.byType(TextField)), 'Agreed with buyer');
      await tester.tap(find.text('Dispatch').last);
      await tester.pumpAndSettle();

      expect(
        api.queryOf('/dispatch-and-invoice'),
        {'batch_reason': 'Agreed with buyer'},
      );
    });
  });

  group('price-floor findings', () {
    PriceFloorFinding finding({String? exemption}) =>
        PriceFloorFinding.fromJson({
          'line_number': '1',
          'product_code': 'P1',
          'product_name': 'Product',
          'net_rate': '8',
          'floor': 'minimum',
          'minimum_price': '10',
          'message': exemption == null
              ? 'Line 1 is below its floor.'
              : 'Allowed, near expiry: line 1.',
          'exemption': exemption,
        });

    test('exemption is parsed', () {
      expect(finding().isExempt, isFalse);
      expect(finding(exemption: 'NEAR_EXPIRY').isExempt, isTrue);
    });

    testWidgets('a check with only exempt findings asks nothing',
        (tester) async {
      PriceFloorOutcome? outcome;
      await tester.pumpWidget(MaterialApp(
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () async {
              outcome = await confirmPriceFloor(
                context,
                _permissions(const []),
                check: () async => PriceFloorCheck(
                  enforcement: 'BLOCK',
                  wouldBlock: false,
                  message: null,
                  findings: [finding(exemption: 'NEAR_EXPIRY')],
                ),
              );
            },
            child: const Text('go'),
          ),
        ),
      ));
      await tester.tap(find.text('go'));
      await tester.pumpAndSettle();

      expect(outcome?.proceed, isTrue);
      expect(find.byType(PriceFloorDialog), findsNothing);
    });

    testWidgets('an exempt finding beside a real one reads as allowed',
        (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: PriceFloorDialog(
            check: PriceFloorCheck(
              enforcement: 'WARN',
              wouldBlock: false,
              message: null,
              findings: [finding(), finding(exemption: 'NEAR_EXPIRY')],
            ),
            canOverride: false,
          ),
        ),
      ));

      expect(find.text('Allowed, near expiry: line 1.'), findsOneWidget);
      expect(find.byKey(const ValueKey('price-floor-exempt')), findsOneWidget);
    });
  });
}
