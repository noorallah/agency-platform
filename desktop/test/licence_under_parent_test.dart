// Backlog 139 (row F8), desktop half: the licence check for a shop under a
// parent buyer.
//
// These pin: *Licence Check* shows the switch **A shop must hold its own
// licence** as the server holds it and sends it on Save; a check that found
// only a line covered by the parent's licence opens no dialog; and where the
// dialog opens for another reason, it lists the covered line under what was
// found.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/trade_licence.dart';
import 'package:agency_desktop/ui/trade_licences/licence_check_dialog.dart';
import 'package:agency_desktop/ui/trade_licences/licence_check_settings_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '');
  return 'header.$payload.signature';
}

PermissionService _withPermissions(List<String> permissions) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': permissions,
      }));

const String _cover = 'Line 1 (Paracetamol): DMart Kukatpally holds no Drug '
    "Licence; its parent DMart's Drug Licence DL-P was used.";

Json _check({required bool withFinding}) => <String, dynamic>{
      'direction': 'SALE',
      'enforcement': 'WARN',
      'on': '2026-10-13',
      'findings': <Json>[
        if (withFinding)
          {
            'party': 'SELLER',
            'party_name': 'The firm',
            'licence_type_id': 'type-1',
            'licence_type_name': 'Drug Licence',
            'shortfall': 'MISSING',
            'licence_number': null,
            'valid_from': null,
            'valid_to': null,
            'line_numbers': <int>[1],
            'product_names': <String>['Paracetamol'],
            'parent_name': null,
            'message': 'Line 1 (Paracetamol): The firm holds no Drug Licence.',
          },
      ],
      'covered_by_parent': <Json>[
        {
          'party': 'CUSTOMER',
          'party_name': 'DMart Kukatpally',
          'parent_name': 'DMart',
          'licence_type_id': 'type-1',
          'licence_type_name': 'Drug Licence',
          'licence_number': 'DL-P',
          'valid_from': null,
          'valid_to': '2027-03-31',
          'line_numbers': <int>[1],
          'product_names': <String>['Paracetamol'],
          'message': _cover,
        },
      ],
      'would_block': false,
      'message': withFinding
          ? 'Line 1 (Paracetamol): The firm holds no Drug Licence.'
          : null,
    };

/// Holds the firm's licence policy, answers a check, and records what was
/// sent.
class _Api extends ApiClient {
  _Api({this.check})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json? check;
  Json settings = <String, dynamic>{
    'sale_enforcement': 'WARN',
    'purchase_enforcement': 'WARN',
    'shop_needs_own_licence': false,
    'is_configured': true,
  };
  Json? sent;

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
    if (path == '/api/v1/trade-licences/settings') {
      if (method == 'PUT') {
        sent = body;
        settings = <String, dynamic>{...settings, ...?body};
      }
      return <String, dynamic>{'success': true, 'data': settings};
    }
    if (path.contains('/trade-licences/check/')) {
      return <String, dynamic>{'success': true, 'data': check};
    }
    return {'data': const <dynamic>[]};
  }
}

Future<void> _pumpSettings(
  WidgetTester tester,
  _Api api,
  List<String> permissions,
) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: LicenceCheckSettingsPage(
          api: api,
          permissions: _withPermissions(permissions),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the switch starts as the server holds it and Save sends it',
      (tester) async {
    final _Api api = _Api();
    await _pumpSettings(
      tester,
      api,
      ['TRADE_LICENCE_VIEW', 'TRADE_LICENCE_MANAGE_SETTINGS'],
    );

    final Finder toggle = find.byKey(const ValueKey('licence-shop-needs-own'));
    expect(find.text('A shop must hold its own licence'), findsOneWidget);
    expect(tester.widget<SwitchListTile>(toggle).value, isFalse);

    await tester.ensureVisible(toggle);
    await tester.tap(toggle);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Save'));
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(api.sent, isNotNull);
    expect(api.sent!['shop_needs_own_licence'], isTrue);
    expect(api.sent!['sale_enforcement'], 'WARN');
    expect(tester.widget<SwitchListTile>(toggle).value, isTrue);
  });

  testWidgets('without the settings permission the switch cannot be moved',
      (tester) async {
    final _Api api = _Api();
    await _pumpSettings(tester, api, ['TRADE_LICENCE_VIEW']);

    final Finder toggle = find.byKey(const ValueKey('licence-shop-needs-own'));
    expect(tester.widget<SwitchListTile>(toggle).onChanged, isNull);
  });

  testWidgets("a line covered by the parent's licence opens no dialog",
      (tester) async {
    final _Api api = _Api(check: _check(withFinding: false));
    LicenceCheckOutcome? outcome;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () async {
              outcome = await confirmLicenceCheck(
                context,
                api,
                _withPermissions(['TRADE_LICENCE_VIEW']),
                document: 'SALES_ORDER',
                documentId: 'order-1',
              );
            },
            child: const Text('Approve'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Approve'));
    await tester.pumpAndSettle();

    expect(find.byType(LicenceCheckDialog), findsNothing);
    expect(outcome, isNotNull);
    expect(outcome!.proceed, isTrue);
    expect(outcome!.overrideReason, isNull);
  });

  testWidgets('the dialog lists the covered line under what was found',
      (tester) async {
    final LicenceCheckRecord check =
        LicenceCheckRecord.fromJson(_check(withFinding: true));
    expect(check.coveredByParent, [_cover]);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: LicenceCheckDialog(check: check, canOverride: false),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('The firm holds no Drug Licence'), findsOneWidget);
    expect(find.text("Covered by a parent's licence"), findsOneWidget);
    expect(find.text(_cover), findsOneWidget);
    expect(find.text('Approve anyway'), findsOneWidget);
  });

  test('an answer from a server older than the switch reads as off', () {
    final TradeLicenceSettingsRecord settings =
        TradeLicenceSettingsRecord.fromJson(<String, dynamic>{
      'sale_enforcement': 'BLOCK',
      'purchase_enforcement': 'WARN',
      'is_configured': true,
    });
    expect(settings.shopNeedsOwnLicence, isFalse);
    expect(
      LicenceCheckRecord.fromJson(<String, dynamic>{
        'direction': 'SALE',
        'enforcement': 'WARN',
        'on': '2026-10-13',
        'findings': const <dynamic>[],
        'would_block': false,
        'message': null,
      }).coveredByParent,
      isEmpty,
    );
  });
}
