// A customer can be put in a group from the form.
//
// The customer-group tier is the last rung of the discount resolver, and the
// API accepted `customer_group_id` on create and update from the start -- but
// the form had no control for it and never sent it, so no customer could be
// assigned to a group from the UI, and the Groups button only managed the list
// (docs/BACKLOG.md 21). Two behaviours: the current group fills in, and a
// chosen group reaches the payload (with "no group" sent as null).

import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _customerJson({String? groupId}) => <String, dynamic>{
      'id': 'cust-1',
      'code': 'C001',
      'name': 'Shop One',
      'display_name': 'Shop One',
      'customer_type': 'BUSINESS',
      'customer_group_id': groupId,
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'credit_limit': '25000.00',
      'default_discount_percent': '0',
      'addresses': const <Json>[],
      'contacts': const <Json>[],
    };

List<CustomerGroup> _groups() => const [
      CustomerGroup(id: 'grp-retail', code: 'RET', name: 'Retailer'),
      CustomerGroup(id: 'grp-whole', code: 'WHL', name: 'Wholesaler'),
    ];

Future<Json?> _openAndSave(
  WidgetTester tester, {
  String? groupId,
  required Future<void> Function(WidgetTester tester) act,
}) async {
  tester.view.physicalSize = const Size(1700, 1400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  Json? saved;
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: CustomerWorkspaceDialog(
        mode: CustomerDialogMode.edit,
        customer: Customer.fromJson(_customerJson(groupId: groupId)),
        loadPlaces: (level, {parentId = ''}) async => const [],
        loadGroups: () async => _groups(),
        onSave: (payload) async {
          saved = payload;
          return Customer.fromJson(_customerJson(groupId: groupId));
        },
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Financial'));
  await tester.pumpAndSettle();
  await act(tester);
  await tester.tap(find.widgetWithText(FilledButton, 'Save'));
  await tester.pumpAndSettle();
  return saved;
}

void main() {
  testWidgets('the form offers a Customer group dropdown of the firms groups',
      (tester) async {
    await _openAndSave(tester, act: (tester) async {
      expect(
          find.widgetWithText(DropdownButtonFormField<String>, 'Customer group'),
          findsOneWidget);
      await tester.tap(find.text('Customer group'));
      await tester.pumpAndSettle();
      expect(find.text('Retailer'), findsWidgets);
      expect(find.text('Wholesaler'), findsWidgets);
      expect(find.text('No group'), findsWidgets);
    });
  });

  testWidgets('the current group fills in', (tester) async {
    await _openAndSave(
      tester,
      groupId: 'grp-whole',
      act: (tester) async {
        expect(find.text('Wholesaler'), findsOneWidget);
      },
    );
  });

  testWidgets('a chosen group reaches the payload', (tester) async {
    final Json? saved = await _openAndSave(tester, act: (tester) async {
      await tester.tap(find.text('Customer group'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Wholesaler').last);
      await tester.pumpAndSettle();
    });

    expect(saved!['customer_group_id'], 'grp-whole');
  });

  testWidgets('choosing No group sends null, not an empty string',
      (tester) async {
    // The server reads null as "no segment"; an empty string is a schema
    // error, and the id of a group named "" cannot exist.
    final Json? saved = await _openAndSave(
      tester,
      groupId: 'grp-whole',
      act: (tester) async {
        await tester.tap(find.text('Wholesaler'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('No group').last);
        await tester.pumpAndSettle();
      },
    );

    expect(saved!.containsKey('customer_group_id'), isTrue);
    expect(saved['customer_group_id'], isNull);
  });
}
