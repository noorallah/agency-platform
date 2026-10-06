// Credit a customer earns, and the one thing this screen must not misstate.
//
// Spending credit settles a bill; it does not discount one. The difference is
// what GST the firm collects, so the screen says it rather than leaving a
// reader to assume the familiar thing.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/customers/loyalty_page.dart';
import 'package:agency_desktop/ui/reports/report_catalog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({
  List<String> perms = const ['LOYALTY_VIEW'],
}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

class _LoyaltyApi extends ApiClient {
  _LoyaltyApi({
    required this.settings,
    this.entries = const [],
    this.lapsedPoints,
    this.refuseReversal,
  }) : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json settings;
  final List<Json> entries;

  /// What the balance reports as lapsed, when a test wants one.
  final String? lapsedPoints;

  /// The server's message when a reversal is refused.
  final String? refuseReversal;

  /// Each reversal asked for: `POST path` and the body sent.
  final List<String> reversed = <String>[];
  final List<Json> reversalBodies = <Json>[];

  /// Every write the screen makes, so a test can read the payload rather than
  /// only whether a dialog appeared.
  final List<Json> written = <Json>[];

  /// Whose balance the screen asked for, if it did.
  String? balanceAsked;

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
    if (path.endsWith('/settings')) {
      if (method == 'PUT') {
        written
            .add(Map<String, dynamic>.from(body ?? const <String, dynamic>{}));
        return <String, dynamic>{'data': settings};
      }
      return <String, dynamic>{'data': settings};
    }
    if (method == 'POST' && path.endsWith('/reverse')) {
      reversed.add('$method $path');
      reversalBodies
          .add(Map<String, dynamic>.from(body ?? const <String, dynamic>{}));
      if (refuseReversal != null) throw ApiException(refuseReversal!);
      return <String, dynamic>{'data': _entry(kind: 'REDEEMED', points: '10')};
    }
    if (method == 'POST' && path.endsWith('/loyalty/adjust')) {
      written.add(Map<String, dynamic>.from(body ?? const <String, dynamic>{}));
      return <String, dynamic>{'data': _entry(kind: 'ADJUSTED')};
    }
    if (path.endsWith('/loyalty/entries')) {
      final String? customer = query?['customer_id'];
      return <String, dynamic>{
        'data': customer == null
            ? entries
            : entries.where((row) => row['customer_id'] == customer).toList(),
      };
    }
    if (method == 'GET') {
      // GET /loyalty/{customer_id}: the balance.
      balanceAsked = path.split('/').last;
      return <String, dynamic>{
        'data': <String, dynamic>{
          'customer_id': balanceAsked,
          'customer_name': 'Kumar Stores',
          'points': '20.0000',
          'amount': '20.00',
          'redeemable': false,
          if (lapsedPoints != null) 'lapsed_points': lapsedPoints,
        },
      };
    }
    return <String, dynamic>{'data': entries};
  }
}

Json _settings({bool enabled = true, int? expiryMonths = 24}) =>
    <String, dynamic>{
      'is_enabled': enabled,
      'points_per_amount': '2.0000',
      'amount_per_point': '1.0000',
      'minimum_redemption_points': 50,
      'expiry_months': expiryMonths,
    };

Json _entry({
  String id = 'le-1',
  String kind = 'EARNED',
  String points = '20.0000',
  String invoice = 'SI-2026-2027-000004',
  String amount = '20.00',
}) =>
    <String, dynamic>{
      'id': id,
      'customer_id': 'c-1',
      'customer_name': 'Kumar Stores',
      'kind': kind,
      'points': points,
      'amount': amount,
      'sales_invoice_number': invoice,
      'earned_on': '2026-06-10',
      'expires_on': '2028-06-10',
    };

Future<void> _pump(
  WidgetTester tester,
  _LoyaltyApi api, {
  PermissionService? permissions,
  bool phase2 = false,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: phase2 ? (context, child) => Phase2Scope(child: child!) : null,
    home: Scaffold(
      body: LoyaltyPage(
        api: api,
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the screen says spending settles rather than discounts',
      (tester) async {
    await _pump(tester, _LoyaltyApi(settings: _settings()));

    // The difference is what GST the firm collects, so it is not left to be
    // assumed.
    expect(
      find.textContaining('settles a bill; it does not discount it'),
      findsOneWidget,
    );
  });

  testWidgets('the scheme is spelled out, expiry included', (tester) async {
    await _pump(tester, _LoyaltyApi(settings: _settings()));

    // The server sends four decimals; the banner must not repeat them.
    expect(
        find.textContaining('2 points per 100, worth 1 each'), findsOneWidget);
    expect(find.textContaining('expire after 24 months'), findsOneWidget);
  });

  testWidgets('points that never expire say so rather than showing a blank',
      (tester) async {
    // Null is a real choice here, not a missing value.
    await _pump(tester, _LoyaltyApi(settings: _settings(expiryMonths: null)));

    expect(find.textContaining('never expire'), findsOneWidget);
  });

  testWidgets('a firm with no scheme is told nobody is earning',
      (tester) async {
    await _pump(tester, _LoyaltyApi(settings: _settings(enabled: false)));

    expect(find.textContaining('nobody is earning'), findsOneWidget);
  });

  testWidgets('the ledger signs the points so the direction is visible',
      (tester) async {
    await _pump(
      tester,
      _LoyaltyApi(
        settings: _settings(),
        entries: <Json>[
          _entry(),
          _entry(kind: 'REDEEMED', points: '-10.0000'),
        ],
      ),
    );

    // A reader should see which way it went without decoding the kind first.
    expect(find.text('+20.00'), findsOneWidget);
    expect(find.text('-10.00'), findsOneWidget);
  });

  testWidgets('someone without the view permission sees nothing',
      (tester) async {
    await _pump(
      tester,
      _LoyaltyApi(settings: _settings(), entries: <Json>[_entry()]),
      permissions: _permissions(perms: const <String>['CUSTOMER_VIEW']),
    );

    expect(find.textContaining('view loyalty permission'), findsOneWidget);
    expect(find.textContaining('Kumar Stores'), findsNothing);
  });

  testWidgets('the scheme can be opened and changed, not only read',
      (tester) async {
    // `PUT /api/v1/loyalty/settings` shipped with `LOYALTY_MANAGE_SETTINGS`
    // seeded and granted, and no way to call it: `api_client.dart` carried
    // only the GET. The orphan-route guard asks whether a *path* is named,
    // not whether a *method* is, so the write was masked by its own read.
    // Found at plan step 21.4 on 2026-09-15.
    final _LoyaltyApi api = _LoyaltyApi(settings: _settings());
    await _pump(
      tester,
      api,
      permissions: _permissions(
          perms: const ['LOYALTY_VIEW', 'LOYALTY_MANAGE_SETTINGS']),
    );

    await tester.tap(find.text('Scheme settings'));
    await tester.pumpAndSettle();
    expect(find.text('Loyalty scheme'), findsOneWidget);

    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(api.written, hasLength(1));
    expect(api.written.single['points_per_amount'], '2');
    expect(api.written.single['minimum_redemption_points'], 50);
  });

  testWidgets('switching expiry off sends an explicit null, not an omission',
      (tester) async {
    // Null means points never expire and zero would mean they expire the day
    // they are earned, so the two are different answers -- and the server
    // dumps with `exclude_unset`, where an *omitted* key means "leave it
    // alone". Sending nothing would silently keep the old expiry.
    final _LoyaltyApi api = _LoyaltyApi(settings: _settings(expiryMonths: 24));
    await _pump(
      tester,
      api,
      permissions: _permissions(
          perms: const ['LOYALTY_VIEW', 'LOYALTY_MANAGE_SETTINGS']),
    );

    await tester.tap(find.text('Scheme settings'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Points expire'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(api.written.single.containsKey('expiry_months'), isTrue,
        reason: 'omitting it would mean "leave it alone"');
    expect(api.written.single['expiry_months'], isNull);
  });

  testWidgets('without the settings permission the scheme opens read-only',
      (tester) async {
    // Offered to anybody who may read the scheme: the banner states the rate,
    // and somebody asking why a balance is what it is should reach the rule
    // behind it. Saving is what needs the permission.
    final _LoyaltyApi api = _LoyaltyApi(settings: _settings());
    await _pump(tester, api);

    await tester.tap(find.text('Scheme settings'));
    await tester.pumpAndSettle();

    expect(find.textContaining('manage loyalty settings permission'),
        findsOneWidget);
    final FilledButton save = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Save'),
    );
    expect(save.onPressed, isNull);
  });

  testWidgets('one customer\'s ledger and balance can be asked for',
      (tester) async {
    // The page had no customer filter and no balance, though the API had
    // both; the balances report was the only route (BL-31.15).
    final _LoyaltyApi api = _LoyaltyApi(
      settings: _settings(),
      entries: <Json>[
        _entry(),
        <String, dynamic>{
          ..._entry(),
          'id': 'le-2',
          'customer_id': 'c-2',
          'customer_name': 'Patel Traders',
        },
      ],
    );
    await _pump(tester, api);
    expect(find.textContaining('Patel Traders'), findsWidgets);

    await tester.tap(find.byType(DropdownButton<String?>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Kumar Stores').last);
    await tester.pumpAndSettle();

    expect(api.balanceAsked, 'c-1');
    expect(find.textContaining('Kumar Stores: 20.00 points, worth 20.00'),
        findsOneWidget);
    expect(find.textContaining('below the floor'), findsOneWidget);
    expect(find.textContaining('Patel Traders'), findsNothing);
  });

  // D-QA-8: the adjustment route existed and no screen called it.
  testWidgets('adjusting points needs the scheme permission', (tester) async {
    await _pump(tester, _LoyaltyApi(settings: _settings(), entries: [_entry()]),
        permissions:
            _permissions(perms: const ['LOYALTY_VIEW', 'LOYALTY_MANAGE']));

    final OutlinedButton adjust =
        tester.widget(find.widgetWithText(OutlinedButton, 'Adjust points'));
    expect(adjust.onPressed, isNull,
        reason: 'granting points is writing off a receivable once spent, so '
            'it takes LOYALTY_MANAGE_SETTINGS, which spending credit does not');
  });

  testWidgets('a balance is corrected with signed points and a reason',
      (tester) async {
    final _LoyaltyApi api =
        _LoyaltyApi(settings: _settings(), entries: [_entry()]);
    await _pump(tester, api,
        permissions: _permissions(
            perms: const ['LOYALTY_VIEW', 'LOYALTY_MANAGE_SETTINGS']));
    await tester.tap(find.byType(DropdownButton<String?>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Kumar Stores').last);
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(OutlinedButton, 'Adjust points'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('loyalty-adjust-points')), '-5');
    await tester.tap(find.text('Record adjustment'));
    await tester.pumpAndSettle();
    expect(api.written, isEmpty, reason: 'no reason given yet');

    await tester.enterText(find.byKey(const ValueKey('loyalty-adjust-reason')),
        'Credited twice on SI-4');
    await tester.tap(find.text('Record adjustment'));
    await tester.pumpAndSettle();

    expect(api.written, hasLength(1));
    expect(api.written.single, <String, dynamic>{
      'customer_id': 'c-1',
      'points': '-5',
      'reason': 'Credited twice on SI-4',
    });
    expect(find.text('Adjust points'), findsOneWidget,
        reason: 'the dialog closed, only the toolbar button remains');
  });

  group('putting points back (D-PRC-6)', () {
    const List<String> manage = <String>['LOYALTY_VIEW', 'LOYALTY_MANAGE'];
    final Finder putBack =
        find.byKey(const ValueKey('toolbar-command-put-points-back'));

    // One earned row, one redemption of 10 on SI-RED, one row putting back
    // the redemption of 5 on SI-DONE, and the redemption it undid.
    List<Json> ledger() => <Json>[
          _entry(id: 'le-earn', invoice: 'SI-EARN'),
          _entry(
              id: 'le-red',
              kind: 'REDEEMED',
              points: '-10.0000',
              invoice: 'SI-RED',
              amount: '-10.00'),
          _entry(
              id: 'le-done',
              kind: 'REDEEMED',
              points: '-5.0000',
              invoice: 'SI-DONE',
              amount: '-5.00'),
          _entry(
              id: 'le-undo',
              kind: 'REDEEMED',
              points: '5.0000',
              invoice: 'SI-DONE',
              amount: '5.00'),
        ];

    bool enabled(WidgetTester tester) {
      final Widget button = tester.widget(putBack);
      return button is ButtonStyleButton && button.onPressed != null;
    }

    testWidgets('a redemption can be put back, with a reason', (tester) async {
      final _LoyaltyApi api =
          _LoyaltyApi(settings: _settings(), entries: ledger());
      await _pump(tester, api, permissions: _permissions(perms: manage),
          phase2: true);

      await tester.tap(find.text('SI-RED'));
      await tester.pumpAndSettle();
      expect(enabled(tester), isTrue);
      await tester.tap(putBack);
      await tester.pumpAndSettle();

      // No reason, nothing sent (the box closes empty-handed).
      await tester.tap(find.widgetWithText(FilledButton, 'Put points back'));
      await tester.pumpAndSettle();
      expect(api.reversed, isEmpty);
      await tester.tap(putBack);
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'Keyed on the wrong bill');
      await tester.tap(find.widgetWithText(FilledButton, 'Put points back'));
      await tester.pumpAndSettle();

      expect(api.reversed.single, 'POST /api/v1/loyalty/redemptions/le-red/reverse');
      expect(api.reversalBodies.single,
          <String, dynamic>{'reason': 'Keyed on the wrong bill'});
      expect(tester.takeException(), isNull);
    });

    testWidgets('only a live redemption offers it', (tester) async {
      final _LoyaltyApi api =
          _LoyaltyApi(settings: _settings(), entries: ledger());
      await _pump(tester, api, permissions: _permissions(perms: manage),
          phase2: true);

      await tester.tap(find.text('SI-EARN'));
      await tester.pumpAndSettle();
      expect(enabled(tester), isFalse, reason: 'earned points are not spent');

      // The row that put points back, and the redemption it undid.
      await tester.tap(find.text('Points put back'));
      await tester.pumpAndSettle();
      expect(enabled(tester), isFalse);
      await tester.tap(find.text('SI-DONE').first);
      await tester.pumpAndSettle();
      expect(enabled(tester), isFalse);
    });

    testWidgets('a row putting points back reads plainly', (tester) async {
      await _pump(
          tester, _LoyaltyApi(settings: _settings(), entries: ledger()),
          phase2: true);
      expect(find.text('Points put back'), findsOneWidget);
    });

    testWidgets('without the manage permission the action is not offered',
        (tester) async {
      await _pump(
          tester, _LoyaltyApi(settings: _settings(), entries: ledger()),
          phase2: true);
      expect(putBack, findsNothing);
    });

    testWidgets("the server's refusal is shown", (tester) async {
      final _LoyaltyApi api = _LoyaltyApi(
        settings: _settings(),
        entries: ledger(),
        refuseReversal: 'Those points were already put back, on 2026-10-06.',
      );
      await _pump(tester, api, permissions: _permissions(perms: manage),
          phase2: true);
      await tester.tap(find.text('SI-RED'));
      await tester.pumpAndSettle();
      await tester.tap(putBack);
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'Wrong bill');
      await tester.tap(find.widgetWithText(FilledButton, 'Put points back'));
      await tester.pumpAndSettle();
      expect(find.textContaining('already put back'), findsOneWidget);
    });
  });

  testWidgets('the balance names points that have lapsed (D-PRC-3)',
      (tester) async {
    await _pump(
      tester,
      _LoyaltyApi(
          settings: _settings(), entries: [_entry()], lapsedPoints: '12.0000'),
      phase2: true,
    );
    await tester.tap(find.byKey(const ValueKey('loyalty-customer')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Kumar Stores').last);
    await tester.pumpAndSettle();
    expect(find.text('Lapsed'), findsOneWidget);
    expect(find.text('12.00'), findsOneWidget);
  });

  test('the balances report names the lapsed points and their value', () {
    final Set<String> keys = reportCatalog
        .firstWhere((report) => report.id == 'loyalty-balances')
        .columns
        .map((column) => column.key)
        .toSet();
    expect(keys, containsAll(<String>['lapsed_points', 'lapsed_amount']));
  });

  testWidgets('phase 2: the scheme behind the (i), the ledger a grid',
      (tester) async {
    // Review 2026-09-27: the scheme sentence, a customer picker and a
    // balance were crammed into the search slot above a raw table.
    await _pump(tester, _LoyaltyApi(settings: _settings()), phase2: true);
    expect(find.byKey(const ValueKey('page-notice')), findsOneWidget);
    expect(find.byKey(const ValueKey('loyalty-customer')), findsOneWidget);
    expect(find.byType(DataTable), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
