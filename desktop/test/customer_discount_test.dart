// A customer carries a standing discount, and the form can read and set it.
//
// The rate lives on the customer and fills in on every sales line that says
// nothing about a discount, so the field on this form is the only place a firm
// sets the arrangement up. Two behaviours, both of which had no coverage while
// the backend rule did:
//
// 1. What the server holds is what the box shows, so somebody editing the
//    customer sees the rate they are about to keep.
// 2. What is typed reaches the payload, including a zero — the server reads
//    "0" as "no standing arrangement" rather than as silence.

import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const String _field = 'Default discount %';

Json _customerJson({String discount = '0'}) => <String, dynamic>{
      'id': 'cust-1',
      'code': 'C001',
      'name': 'Shop One',
      'display_name': 'Shop One',
      'customer_type': 'BUSINESS',
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'credit_limit': '25000.00',
      'default_discount_percent': discount,
      'addresses': const <Json>[],
      'contacts': const <Json>[],
    };

/// Open the editor on the Financial tab, do [act], and save.
Future<Json?> _openAndSave(
  WidgetTester tester, {
  String discount = '0',
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
        customer: Customer.fromJson(_customerJson(discount: discount)),
        loadPlaces: (level, {parentId = ''}) async => const [],
        onSave: (payload) async {
          saved = payload;
          return Customer.fromJson(_customerJson(discount: discount));
        },
      ),
    ),
  ));
  await tester.pumpAndSettle();
  // The discount sits beside the credit limit, which is where somebody looking
  // for what this customer is owed and allowed would look for it.
  await tester.tap(find.text('Financial'));
  await tester.pumpAndSettle();
  await act(tester);
  await tester.tap(find.widgetWithText(FilledButton, 'Save'));
  await tester.pumpAndSettle();
  return saved;
}

void main() {
  testWidgets('the form shows the rate the customer is on', (tester) async {
    await _openAndSave(
      tester,
      discount: '10.0000',
      act: (tester) async {
        expect(find.widgetWithText(TextFormField, _field), findsOneWidget);
        expect(find.text('10.0000'), findsOneWidget);
      },
    );
  });

  testWidgets('a typed rate reaches the payload', (tester) async {
    final Json? saved = await _openAndSave(tester, act: (tester) async {
      await tester.enterText(
        find.widgetWithText(TextFormField, _field),
        '7.5',
      );
    });

    expect(saved!['default_discount_percent'], '7.5');
  });

  testWidgets('clearing the box sends zero rather than nothing',
      (tester) async {
    // An empty string is a schema error server-side, and omitting the field
    // means "leave it alone" now that the update is partial -- neither of
    // which is what somebody who emptied the box meant.
    final Json? saved = await _openAndSave(
      tester,
      discount: '10.0000',
      act: (tester) async {
        await tester.enterText(
          find.widgetWithText(TextFormField, _field),
          '',
        );
      },
    );

    expect(saved!['default_discount_percent'], '0');
  });

  testWidgets('a rate above a hundred is refused before it is sent',
      (tester) async {
    // Caught here as well as on the server, which answers a schema error
    // naming a limit this form never mentioned.
    final Json? saved = await _openAndSave(tester, act: (tester) async {
      await tester.enterText(
        find.widgetWithText(TextFormField, _field),
        '500',
      );
    });

    expect(saved, isNull);
    expect(find.text('$_field cannot be more than 100.'), findsOneWidget);
  });

  testWidgets('a negative rate is refused too', (tester) async {
    final Json? saved = await _openAndSave(tester, act: (tester) async {
      await tester.enterText(
        find.widgetWithText(TextFormField, _field),
        '-5',
      );
    });

    expect(saved, isNull);
    expect(find.text('$_field cannot be negative.'), findsOneWidget);
  });
}
