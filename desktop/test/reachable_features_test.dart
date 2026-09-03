// Every feature merged in #185–#194 had a backend and a client method, and six
// of them had no button. The orphan-route guard could not see it: a call in
// `api_client.dart` counts as a caller, so a route can have one while no screen
// can reach it.
//
// These pin the buttons themselves — what a user can actually get to.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/settlement_direction.dart';
import 'package:agency_desktop/ui/customers/loyalty_page.dart';
import 'package:agency_desktop/ui/finance/record_settlement_dialog.dart';
import 'package:agency_desktop/ui/sales/proforma_page.dart';
import 'package:agency_desktop/ui/sales/sales_order_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

class _Api extends ApiClient {
  _Api({this.orders = const <Json>[], this.detail})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> orders;
  final Json? detail;
  final List<String> posted = <String>[];
  Json? sentBody;

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
    if (method == 'POST') {
      posted.add(path);
      sentBody = body;
      return <String, dynamic>{'data': detail};
    }
    if (path.contains('/advances')) {
      return <String, dynamic>{'data': detail};
    }
    if (path.contains('sales-orders')) {
      return <String, dynamic>{
        'data': orders,
        'pagination': <String, dynamic>{'total_records': orders.length},
      };
    }
    if (path.endsWith('/summary')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'total': orders.length, 'draft': orders.length},
      };
    }
    if (path.endsWith('/settings')) {
      return <String, dynamic>{'data': detail};
    }
    return <String, dynamic>{
      'data': const <Json>[],
      'pagination': <String, dynamic>{'total_records': 0},
    };
  }
}

Future<void> _sized(WidgetTester tester, Widget child) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(home: Scaffold(body: child)));
  await tester.pumpAndSettle();
}

Json _scheme() => <String, dynamic>{
      'is_enabled': true,
      'points_per_amount': '2',
      'amount_per_point': '1',
      'minimum_redemption_points': 50,
      'expiry_months': 24,
    };

void main() {
  group('a proforma can be raised', () {
    testWidgets('the New button offers the orders a proforma may state',
        (tester) async {
      final _Api api = _Api(orders: <Json>[
        <String, dynamic>{
          'id': 'so-1',
          'order_number': 'SO-0001',
          'status': 'APPROVED',
          'grand_total': '1000.00',
          'customer_id': 'c-1',
        },
        // A draft is not a deal, so the picker must not offer it -- the server
        // refuses it anyway, and offering it wastes the user's time twice.
        <String, dynamic>{
          'id': 'so-2',
          'order_number': 'SO-0002',
          'status': 'DRAFT',
          'grand_total': '500.00',
          'customer_id': 'c-1',
        },
      ]);
      await _sized(
        tester,
        ProformaPage(
          api: api,
          permissions: _permissions(const ['PROFORMA_VIEW', 'PROFORMA_MANAGE']),
          hasActiveFirm: true,
        ),
      );

      await tester.tap(find.widgetWithText(FilledButton, 'New'));
      await tester.pumpAndSettle();
      // Opened, because a dropdown renders only its selected item until it
      // is -- so a closed one proves nothing about what it offers.
      await tester.tap(find.byType(DropdownButtonFormField<String>));
      await tester.pumpAndSettle();

      expect(find.textContaining('SO-0001'), findsWidgets);
      expect(find.textContaining('SO-0002'), findsNothing);
    });

    testWidgets('someone who cannot manage cannot raise one', (tester) async {
      await _sized(
        tester,
        ProformaPage(
          api: _Api(),
          permissions: _permissions(const ['PROFORMA_VIEW']),
          hasActiveFirm: true,
        ),
      );

      final Finder button = find.widgetWithText(FilledButton, 'New');
      expect(tester.widget<FilledButton>(button).onPressed, isNull);
    });
  });

  group('lapsed points can be swept', () {
    testWidgets('the register offers it', (tester) async {
      await _sized(
        tester,
        LoyaltyPage(
          api: _Api(detail: _scheme()),
          permissions: _permissions(const ['LOYALTY_VIEW', 'LOYALTY_MANAGE']),
          hasActiveFirm: true,
        ),
      );

      expect(
        tester
            .widget<OutlinedButton>(
                find.widgetWithText(OutlinedButton, 'Expire lapsed'))
            .onPressed,
        isNotNull,
      );
    });

    testWidgets('reading the register is not authority to sweep it',
        (tester) async {
      await _sized(
        tester,
        LoyaltyPage(
          api: _Api(detail: _scheme()),
          permissions: _permissions(const ['LOYALTY_VIEW']),
          hasActiveFirm: true,
        ),
      );

      expect(
        tester
            .widget<OutlinedButton>(
                find.widgetWithText(OutlinedButton, 'Expire lapsed'))
            .onPressed,
        isNull,
      );
    });
  });

  group('a receipt can name its order', () {
    testWidgets('the order picker appears for a receipt', (tester) async {
      await _sized(
        tester,
        RecordSettlementDialog(
          api: _Api(),
          direction: SettlementDirection.receipt,
          parties: const [
            PartyOption(id: 'c-1', code: 'C1', name: 'Kumar Stores'),
          ],
        ),
      );

      expect(find.textContaining('Against order'), findsOneWidget);
    });

    testWidgets('and not for a payment, which has no sales order behind it',
        (tester) async {
      await _sized(
        tester,
        RecordSettlementDialog(
          api: _Api(),
          direction: SettlementDirection.payment,
          parties: const [
            PartyOption(id: 'v-1', code: 'V1', name: 'Supplier'),
          ],
        ),
      );

      // The server refuses one, so offering the field would be accepting
      // input it discards.
      expect(find.textContaining('Against order'), findsNothing);
    });
  });

  group('an order shows what has been paid against it', () {
    testWidgets('including a reversed receipt, which is not dropped',
        (tester) async {
      final Directory temp = Directory.systemTemp.createTempSync('deposits');
      addTearDown(() => temp.deleteSync(recursive: true));
      final _Api api = _Api(
        // The page lists through `documentPage('sales-orders')`, which this
        // fake serves from `orders`.
        orders: <Json>[
          <String, dynamic>{
            'id': 'so-1',
            'order_number': 'SO-0001',
            'order_date': '2026-08-23',
            'reference_number': '',
            'status': 'APPROVED',
            'grand_total': '1000.00',
            'customer_id': 'c-1',
            'is_on_hold': false,
          },
        ],
        detail: <String, dynamic>{
          'order_number': 'SO-0001',
          'total_received': '5000.00',
          'total_unapplied': '5000.00',
          'receipts': <Json>[
            <String, dynamic>{
              'settlement_number': 'RC-0001',
              'settlement_date': '2026-09-01',
              'amount': '5000.00',
              'status': 'POSTED',
            },
            <String, dynamic>{
              'settlement_number': 'RC-0002',
              'settlement_date': '2026-09-02',
              'amount': '900.00',
              'status': 'REVERSED',
            },
          ],
        },
      );
      await _sized(
        tester,
        SalesOrderManagementPage(
          api: api,
          preferences: DesktopPreferencesService(directory: temp),
          permissions: _permissions(const ['SALES_VIEW', 'SALES_APPROVE']),
          hasActiveFirm: true,
        ),
      );

      // Opened from the row rather than a toolbar button: the deposits are a
      // fact about the order, and the lifecycle row is already full at the
      // narrowest size the shell supports.
      await tester.tap(find.byTooltip('View').first);
      await tester.pumpAndSettle();

      expect(find.textContaining('5000.00 received'), findsOneWidget);
      // A deposit that vanished from the screen leaves nobody able to say why
      // the figure changed.
      expect(find.textContaining('RC-0002'), findsOneWidget);
      expect(find.textContaining('(reversed)'), findsOneWidget);
    });
  });
}
