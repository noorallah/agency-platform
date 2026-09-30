// Removing a customer group from the Groups dialog asks first (D-DLG-2).
//
// The x beside a group removed it at once; its sibling in the phase 2 page
// confirms.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/customers/customer_group_dialog.dart';
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
  Future<PagedResult<CustomerGroup>> customerGroups({
    int page = 1,
    int pageSize = 100,
    String search = '',
  }) async =>
      const PagedResult<CustomerGroup>(
        items: [CustomerGroup(id: 'g-1', code: 'RET', name: 'Retailer')],
        total: 1,
      );

  @override
  Future<void> deleteCustomerGroup(String id) async => deleted.add(id);
}

void main() {
  testWidgets('the x asks before removing a group', (tester) async {
    tester.view.physicalSize = const Size(1400, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: CustomerGroupDialog(
          api: api,
          permissions: PermissionService()
            ..applyAccessToken(accessTokenFor(const <String>[
              'CUSTOMER_VIEW',
              'CUSTOMER_MANAGE_SETTINGS',
            ])),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Remove'));
    await tester.pumpAndSettle();
    expect(find.text('Remove Retailer?'), findsOneWidget);
    expect(api.deleted, isEmpty);
    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();
    expect(api.deleted, isEmpty);

    await tester.tap(find.byTooltip('Remove'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Remove'));
    await tester.pumpAndSettle();
    expect(api.deleted, ['g-1']);
  });
}
