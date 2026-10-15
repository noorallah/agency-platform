// The customer record in the phase 2 app (2026-09-26): a full-page tab with
// every section in one scroll and a side panel of what they owe, instead of a
// dialog of seven tabs (design section 9, item 1).

import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/salesman.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _customerJson() => <String, dynamic>{
      'id': 'cust-1',
      'version': 4,
      'firm_id': 'firm-1',
      'code': 'CUS-001',
      'customer_type': 'BUSINESS',
      'name': 'Anand Agencies',
      'display_name': 'Anand Agencies',
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'credit_limit': '50000.00',
      'current_outstanding': '12000.00',
      'payment_terms_days': 30,
      'addresses': <dynamic>[],
      'contacts': <dynamic>[],
    };

void main() {
  testWidgets('phase 2 shows the whole record on one page and saves it',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    Json? sent;
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: CustomerWorkspaceDialog(
          mode: CustomerDialogMode.edit,
          customer: Customer.fromJson(_customerJson()),
          onSave: (payload) async {
            sent = payload;
            return Customer.fromJson(_customerJson());
          },
          loadPlaces: (level, {parentId = ''}) async => const [],
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    // No tabs: the money fields sit on the same page as the name.
    expect(find.text('Customer name'), findsOneWidget);
    expect(find.text('Credit limit'), findsOneWidget);
    expect(find.text('Contact persons'), findsOneWidget);

    // The side panel says what they owe against their limit.
    expect(find.byKey(const ValueKey('document-side-panel')), findsOneWidget);
    expect(find.text('12,000.00'), findsOneWidget);
    expect(find.text('38,000.00'), findsOneWidget);
    expect(find.text('30 days'), findsOneWidget);

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Display name'),
      'Anand Agencies (Main)',
    );
    await tester.tap(find.byKey(const ValueKey('customer-save')));
    await tester.pumpAndSettle();
    expect(sent?['display_name'], 'Anand Agencies (Main)');
    expect(sent?['code'], 'CUS-001');
  });

  group('the minimum shelf life', () {
    Future<List<Json>> pumpForm(WidgetTester tester) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final List<Json> sent = <Json>[];
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: CustomerWorkspaceDialog(
            mode: CustomerDialogMode.edit,
            customer: Customer.fromJson(<String, dynamic>{
              ..._customerJson(),
              'minimum_shelf_life_days': 90,
            }),
            onSave: (payload) async {
              sent.add(payload);
              return Customer.fromJson(_customerJson());
            },
            loadPlaces: (level, {parentId = ''}) async => const [],
          ),
        ),
      ));
      await tester.pumpAndSettle();
      return sent;
    }

    final Finder box =
        find.widgetWithText(TextFormField, 'Minimum shelf life (days)');

    testWidgets('loads, and an untouched edit sends it back', (tester) async {
      final List<Json> sent = await pumpForm(tester);
      expect(tester.widget<TextFormField>(box).controller!.text, '90');
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent.last['minimum_shelf_life_days'], 90);
    });

    testWidgets('above 3650 is refused on the form', (tester) async {
      final List<Json> sent = await pumpForm(tester);
      await tester.enterText(box, '4000');
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent, isEmpty);
      expect(find.textContaining('cannot be more than 3650'), findsOneWidget);
    });

    testWidgets('blank is sent as null, clearing it', (tester) async {
      final List<Json> sent = await pumpForm(tester);
      await tester.enterText(box, '');
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent.last.containsKey('minimum_shelf_life_days'), isTrue);
      expect(sent.last['minimum_shelf_life_days'], isNull);
    });
  });

  testWidgets('the account manager is picked from the firm and kept if gone',
      (tester) async {
    // Backlog 67 row 2: a stored manager who has left stays selectable and
    // is sent back unchanged; a salesman picked replaces them. P2: the list
    // is the firm's salesman list, so the id sent is a salesman's.
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final List<Json> sent = <Json>[];
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: CustomerWorkspaceDialog(
          mode: CustomerDialogMode.edit,
          customer: Customer.fromJson(
            <String, dynamic>{..._customerJson(), 'salesman_id': 'sm-gone'},
          ),
          onSave: (payload) async {
            sent.add(payload);
            return Customer.fromJson(_customerJson());
          },
          loadPlaces: (level, {parentId = ''}) async => const [],
          loadSalesmen: () async => const [
            Salesman(id: 'sm-asha', name: 'Asha Rao'),
            Salesman(id: 'sm-ravi', name: 'Ravi K'),
            Salesman(id: 'sm-old', name: 'Old Hand', isActive: false),
          ],
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Account manager'), findsOneWidget);
    expect(find.text('Current manager (no longer on the list)'),
        findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('customer-account-manager')));
    await tester.pumpAndSettle();
    // Only the active salesmen are offered.
    expect(find.textContaining('Old Hand'), findsNothing);
    await tester.tap(find.text('Asha Rao').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('customer-save')));
    await tester.pumpAndSettle();
    expect(sent.last['salesman_id'], 'sm-asha');
  });

  testWidgets('without the salesman list the manager is neither shown nor lost',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    Json? sent;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: CustomerWorkspaceDialog(
          mode: CustomerDialogMode.edit,
          customer: Customer.fromJson(
            <String, dynamic>{..._customerJson(), 'salesman_id': 'u-asha'},
          ),
          onSave: (payload) async {
            sent = payload;
            return Customer.fromJson(_customerJson());
          },
          loadPlaces: (level, {parentId = ''}) async => const [],
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Account manager'), findsNothing);
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(sent?['salesman_id'], 'u-asha');
  });

  group('the customer code (MST-5)', () {
    Future<List<Json>> pumpForm(
      WidgetTester tester,
      CustomerDialogMode mode,
      Customer? customer,
    ) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final List<Json> sent = <Json>[];
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: CustomerWorkspaceDialog(
            mode: mode,
            customer: customer,
            onSave: (payload) async {
              sent.add(payload);
              return Customer.fromJson(_customerJson());
            },
            loadPlaces: (level, {parentId = ''}) async => const [],
          ),
        ),
      ));
      await tester.pumpAndSettle();
      return sent;
    }

    testWidgets('a new customer may leave it blank and sends none',
        (tester) async {
      final List<Json> sent =
          await pumpForm(tester, CustomerDialogMode.create, null);
      expect(find.text('Blank: issued on save'), findsOneWidget);
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Customer name'),
        'New Traders',
      );
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent, hasLength(1));
      expect(sent.single.containsKey('code'), isFalse);
    });

    testWidgets('an edit still refuses a blank code', (tester) async {
      final List<Json> sent = await pumpForm(
        tester,
        CustomerDialogMode.edit,
        Customer.fromJson(_customerJson()),
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Customer code'),
        '',
      );
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent, isEmpty);
      expect(find.text('Customer code is required.'), findsOneWidget);
    });
  });

  group('the TCS switch (backlog 113)', () {
    Future<List<Json>> pumpForm(
      WidgetTester tester,
      CustomerDialogMode mode,
      Customer? customer,
    ) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final List<Json> sent = <Json>[];
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: CustomerWorkspaceDialog(
            mode: mode,
            customer: customer,
            onSave: (payload) async {
              sent.add(payload);
              return Customer.fromJson(_customerJson());
            },
            loadPlaces: (level, {parentId = ''}) async => const [],
          ),
        ),
      ));
      await tester.pumpAndSettle();
      return sent;
    }

    final Finder control = find.byKey(const ValueKey('customer-tcs-applicable'));

    testWidgets('a new customer sends true',
        (tester) async {
      final List<Json> sent =
          await pumpForm(tester, CustomerDialogMode.create, null);
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Customer name'),
        'New Traders',
      );
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent.single['tcs_applicable'], true);
    });

    testWidgets('switching it off sends false', (tester) async {
      final List<Json> sent =
          await pumpForm(tester, CustomerDialogMode.create, null);
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Customer name'),
        'New Traders',
      );
      await tester.ensureVisible(control);
      await tester.tap(control);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent.single['tcs_applicable'], false);
    });

    testWidgets('a record that says off shows it off', (tester) async {
      await pumpForm(
        tester,
        CustomerDialogMode.edit,
        Customer.fromJson(<String, dynamic>{
          ..._customerJson(),
          'tcs_applicable': false,
        }),
      );
      await tester.ensureVisible(control);
      expect(tester.widget<CheckboxListTile>(control).value, false);
    });
  });

  group('L5: bills in boxes and pieces', () {
    Future<List<Json>> pumpTick(
      WidgetTester tester, {
      required bool offered,
      Json? stored,
    }) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final List<Json> sent = <Json>[];
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: CustomerWorkspaceDialog(
            mode: CustomerDialogMode.edit,
            customer: Customer.fromJson(stored ?? _customerJson()),
            offerBoxAndPieces: offered,
            onSave: (payload) async {
              sent.add(payload);
              return Customer.fromJson(_customerJson());
            },
            loadPlaces: (level, {parentId = ''}) async => const [],
          ),
        ),
      ));
      await tester.pumpAndSettle();
      return sent;
    }

    const ValueKey<String> tick = ValueKey('customer-box-and-piece-entry');

    testWidgets('with the selling switch on the tick is shown and sent',
        (tester) async {
      final List<Json> sent = await pumpTick(tester, offered: true);
      final Finder control = find.byKey(tick);
      await tester.ensureVisible(control);
      expect(find.text('Bills in boxes and pieces'), findsOneWidget);
      expect(tester.widget<CheckboxListTile>(control).value, isFalse);
      await tester.tap(control);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent.single['box_and_piece_entry'], isTrue);
    });

    testWidgets('a marked customer reads as marked', (tester) async {
      await pumpTick(tester,
          offered: true,
          stored: <String, dynamic>{
            ..._customerJson(),
            'box_and_piece_entry': true,
          });
      await tester.ensureVisible(find.byKey(tick));
      expect(tester.widget<CheckboxListTile>(find.byKey(tick)).value, isTrue);
    });

    testWidgets('with the switch off there is no tick and nothing is sent',
        (tester) async {
      final List<Json> sent = await pumpTick(tester, offered: false);
      expect(find.byKey(tick), findsNothing);
      await tester.tap(find.byKey(const ValueKey('customer-save')));
      await tester.pumpAndSettle();
      expect(sent.single.containsKey('box_and_piece_entry'), isFalse);
    });
  });
}
