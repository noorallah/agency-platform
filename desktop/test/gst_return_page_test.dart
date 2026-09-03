// A return is a view, not a record, and the screen has to say so.
//
// The two things that go wrong on a screen like this are showing a stale
// period's figures under a new period's dates, and showing a zero where the
// answer is "this module does not know". Both are tested here.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/gst_return_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({List<String> perms = const ['SALES_VIEW']}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

class _ReturnsApi extends ApiClient {
  _ReturnsApi({this.one, this.summary, this.failWith, this.failFromCall = 1})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json? one;
  final Json? summary;
  final String? failWith;

  /// Which call starts failing, so a screen can be loaded successfully and
  /// *then* refused — the only way to see whether a failed refresh leaves the
  /// previous period's figures on screen.
  final int failFromCall;
  final List<String> requested = <String>[];

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
    requested.add('$method $path?${query?['from_date']}');
    if (failWith != null && requested.length >= failFromCall) {
      throw ApiException(failWith!, statusCode: 400);
    }
    if (path.endsWith('/gstr3b')) {
      return <String, dynamic>{'data': summary};
    }
    return <String, dynamic>{'data': one};
  }
}

Json _gstr1() => <String, dynamic>{
      'gstin': '29AABCU9603R1ZM',
      'b2b': <Json>[
        <String, dynamic>{
          'gstin': '29AAACR5055K1Z5',
          'invoices': <Json>[
            <String, dynamic>{
              'invoice_number': 'SI-2026-0001',
              'taxable_value': 1000.0,
              'invoice_value': 1180.0,
              'central_tax': 90.0,
              'state_tax': 90.0,
              'integrated_tax': 0.0,
              'rate': 18.0,
            },
          ],
        },
      ],
      'b2cl': const <Json>[],
      'b2cs': <Json>[
        <String, dynamic>{
          'place_of_supply': '29',
          'rate': 18.0,
          'taxable_value': 500.0,
          'central_tax': 45.0,
          'state_tax': 45.0,
          'integrated_tax': 0.0,
        },
      ],
      'cdnr': const <Json>[],
      'hsn': <Json>[
        <String, dynamic>{
          'hsn': '33061020',
          'rate': 18.0,
          'quantity': 15.0,
          'taxable_value': 1500.0,
          'central_tax': 135.0,
          'state_tax': 135.0,
          'integrated_tax': 0.0,
        },
      ],
      'docs': <Json>[
        <String, dynamic>{
          'prefix': 'SI-2026',
          'from': 'SI-2026-0001',
          'to': 'SI-2026-0002',
          'count': 2,
          'cancelled': 0,
        },
      ],
    };

Json _gstr3b() => <String, dynamic>{
      'gstin': '29AABCU9603R1ZM',
      'outward_taxable_supplies': <String, dynamic>{
        'taxable_value': 1500.0,
        'integrated_tax': 0.0,
        'central_tax': 135.0,
        'state_tax': 135.0,
        'cess': 0.0,
      },
      'credit_notes_deducted': <String, dynamic>{
        'taxable_value': 0.0,
        'tax': 0.0,
      },
      'inward_supplies': 'Not derived: the purchase side files this.',
    };

Future<void> _pump(
  WidgetTester tester,
  _ReturnsApi api, {
  PermissionService? permissions,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: GstReturnPage(
        api: api,
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a registered buyer is shown invoice by invoice', (tester) async {
    await _pump(tester, _ReturnsApi(one: _gstr1(), summary: _gstr3b()));

    // The number is what the buyer claims credit against, so it is on screen
    // rather than folded into a total.
    expect(find.text('SI-2026-0001'), findsOneWidget);
    expect(find.text('29AAACR5055K1Z5'), findsOneWidget);
    expect(find.textContaining('Filing as 29AABCU9603R1ZM'), findsOneWidget);
  });

  testWidgets('the summary says it does not know the inward side',
      (tester) async {
    await _pump(tester, _ReturnsApi(one: _gstr1(), summary: _gstr3b()));
    await tester.tap(find.text('GSTR-3B'));
    await tester.pumpAndSettle();

    // A zero in this box would read as "no input credit claimed", which is a
    // different declaration from "this screen cannot derive it".
    expect(find.textContaining('Not derived'), findsOneWidget);
    expect(find.text('135.00'), findsWidgets);
  });

  testWidgets('a refused refresh reports the refusal instead of figures',
      (tester) async {
    // Loads once, then every later call is refused.
    final _ReturnsApi api = _ReturnsApi(
      one: _gstr1(),
      summary: _gstr3b(),
      failWith: 'The period is not open.',
      failFromCall: 3,
    );
    await _pump(tester, api);
    expect(find.text('SI-2026-0001'), findsOneWidget);

    await tester.tap(find.text('Refresh'));
    await tester.pumpAndSettle();

    // What must not happen is the previous period's numbers sitting under
    // the new dates as though they were the answer.
    expect(find.textContaining('The period is not open.'), findsOneWidget);
    expect(find.text('SI-2026-0001'), findsNothing);
  });

  testWidgets('someone who cannot see sales cannot read the return',
      (tester) async {
    await _pump(
      tester,
      _ReturnsApi(one: _gstr1(), summary: _gstr3b()),
      permissions: _permissions(perms: const <String>['CUSTOMER_VIEW']),
    );

    expect(find.textContaining('view sales permission'), findsOneWidget);
    expect(find.text('SI-2026-0001'), findsNothing);
  });
}
