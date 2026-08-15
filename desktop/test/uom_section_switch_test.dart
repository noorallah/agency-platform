// Clicking a UOM sub-tab must load that sub-tab, first time.
//
// Reported from manual testing: "UOM & Packaging sub menus — when we click the
// first time data is not loading; we need to click Refresh, then it starts
// loading."
//
// The cause was not in this page's loading logic. All five UOM sub-tabs build
// `UomManagementPage` in the same slot of the same `switch` with no key, so
// Flutter reused the Element and kept the State: `initState` never ran again
// and the new section was never fetched. The grid then rendered the new
// section's still-empty list as "no records" — which looks exactly like data
// failing to load — and Refresh appeared to fix it only because `_load` reads
// the section that had, by then, already changed.
//
// The test that would have caught it is the second `pumpWidget` below: same
// position, same type, no key, different section. `UomManagementPage` had no
// test at all before this.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/uom/uom_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>[
      'UOM_VIEW',
      'UOM_MANAGE',
      'PACKAGING_MANAGE',
      'CONVERSION_RULE_MANAGE',
    ],
  }));

/// Records which endpoints were asked for, and answers one row each so the
/// grid has something distinctive to show per section.
class _UomApi extends ApiClient {
  _UomApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

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
    requested.add(path);
    return <String, dynamic>{'data': _payloadFor(path), 'pagination': null};
  }

  List<Json> _payloadFor(String path) {
    if (path.contains('uom-groups')) {
      return <Json>[
        <String, dynamic>{'id': 'g-1', 'code': 'WEIGHTGRP', 'name': 'Weight'},
      ];
    }
    if (path.contains('packaging-types')) {
      return <Json>[
        <String, dynamic>{'id': 'p-1', 'code': 'CARTONPKG', 'name': 'Carton'},
      ];
    }
    if (path.contains('conversion-rules')) {
      return <Json>[
        <String, dynamic>{
          'id': 'c-1',
          'product_id': 'prod-1',
          'from_uom_id': 'BOXRULE',
          'to_uom_id': 'PCS',
          'conversion_factor': '10',
          'status': 'ACTIVE',
        },
      ];
    }
    if (path.contains('industry-templates')) {
      return <Json>[
        <String, dynamic>{'id': 't-1', 'code': 'PHARMATPL', 'name': 'Pharma'},
      ];
    }
    return <Json>[
      <String, dynamic>{'id': 'u-1', 'code': 'PIECEUNIT', 'name': 'Piece'},
    ];
  }
}

Future<void> _pump(
  WidgetTester tester,
  _UomApi api,
  UomManagementSection section,
) async {
  await tester.binding.setSurfaceSize(const Size(1600, 900));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  // No key, deliberately. That is how the shell builds these, and keying here
  // would hide the very thing under test.
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: UomManagementPage(
        api: api,
        permissions: _permissions(),
        hasActiveFirm: true,
        section: section,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('switching sub-tab in place loads the new sub-tab',
      (tester) async {
    final _UomApi api = _UomApi();
    await _pump(tester, api, UomManagementSection.uoms);
    expect(find.textContaining('PIECEUNIT'), findsWidgets);

    // The same widget type at the same position with a new section: Flutter
    // reuses the State, so only `didUpdateWidget` can notice.
    await _pump(tester, api, UomManagementSection.uomGroups);

    expect(
      api.requested.any((path) => path.contains('uom-groups')),
      isTrue,
      reason: 'the new section was never fetched — this is the reported bug',
    );
    expect(find.textContaining('WEIGHTGRP'), findsWidgets,
        reason: 'the new section rendered without its data');
    expect(find.textContaining('PIECEUNIT'), findsNothing,
        reason: 'the previous section is still on screen');
  });

  testWidgets('every sub-tab loads when reached in sequence', (tester) async {
    // The user clicks along the menu rather than opening one tab in isolation,
    // and every hop is a same-class switch.
    final _UomApi api = _UomApi();
    const List<(UomManagementSection, String)> walk =
        <(UomManagementSection, String)>[
      (UomManagementSection.uoms, 'PIECEUNIT'),
      (UomManagementSection.uomGroups, 'WEIGHTGRP'),
      (UomManagementSection.packagingTypes, 'CARTONPKG'),
      (UomManagementSection.conversionRules, 'BOXRULE'),
      (UomManagementSection.industryTemplates, 'PHARMATPL'),
    ];

    for (final (UomManagementSection section, String marker) in walk) {
      await _pump(tester, api, section);
      expect(find.textContaining(marker), findsWidgets,
          reason: '${section.name} did not load on arrival');
      expect(find.textContaining('Unable to load'), findsNothing);
    }
  });

  testWidgets('a search typed on one sub-tab does not follow to the next',
      (tester) async {
    final _UomApi api = _UomApi();
    await _pump(tester, api, UomManagementSection.uoms);

    final Finder search = find.byType(TextField).first;
    await tester.enterText(search, 'piece');
    await tester.pumpAndSettle();

    await _pump(tester, api, UomManagementSection.packagingTypes);

    // A term typed for Units means nothing on Packaging Types, and leaving it
    // in the box shows a filtered grid with no visible reason.
    expect(
      tester.widget<TextField>(find.byType(TextField).first).controller?.text,
      isEmpty,
    );
  });
}
