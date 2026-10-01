// Retiring a numbering series names the series (D-DLG-5).
//
// The prompt read `"${rule.name}"` literally because the `$` had been escaped.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/document_framework.dart';
import 'package:agency_desktop/ui/settings/numbering_series_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/access_token.dart';

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<String> deleted = <String>[];

  @override
  Future<List<NumberingRule>> numberingRules() async => [
        NumberingRule.fromJson(<String, dynamic>{
          'id': 'r-1',
          'document_type_id': 'dt-1',
          'code': 'SI',
          'name': 'Tax invoices',
          'prefix': 'SI',
          'is_active': true,
        }),
      ];

  @override
  Future<List<DocumentTypeRecord>> documentTypes() async => const [];

  @override
  Future<void> deleteNumberingRule(String id) async => deleted.add(id);
}

void main() {
  testWidgets('the retire prompt shows the real series name', (tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: NumberingSeriesPage(
          api: api,
          permissions: PermissionService()
            ..applyAccessToken(accessTokenFor(const <String>[
              'SETTINGS_VIEW',
              'SETTINGS_UPDATE',
            ])),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Retire'));
    await tester.pumpAndSettle();

    expect(find.textContaining('"Tax invoices"'), findsOneWidget);
    expect(find.textContaining(r'${rule.name}'), findsNothing);
    await tester.tap(find.widgetWithText(FilledButton, 'Retire'));
    await tester.pumpAndSettle();
    expect(api.deleted, ['r-1']);
  });
}
