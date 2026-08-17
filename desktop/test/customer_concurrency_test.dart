// Two people editing one customer must not silently overwrite each other.
//
// The server has published the record's version as an `ETag` and accepted it
// back as `If-Match` since 2026-08-15, and this client sent neither — so the
// second save won and the first user's work was gone with no message. A
// customer update replaces the whole address and contact collection, so the
// loser does not merge badly: they lose every row they entered.
//
// The precondition is opt-in on the server, which is what makes these tests
// worth having. Nothing fails loudly if the client stops sending the header —
// the writes just quietly go back to last-one-wins.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _customerJson({int version = 4}) => <String, dynamic>{
      'id': 'cust-1',
      'version': version,
      'firm_id': 'firm-1',
      'code': 'CUS-001',
      'customer_type': 'BUSINESS',
      'name': 'Anand Agencies',
      'display_name': 'Anand Agencies',
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'addresses': <dynamic>[],
      'contacts': <dynamic>[],
    };

/// Pump the editor with a save that behaves however the test needs.
Future<void> _pumpEditor(
  WidgetTester tester,
  Future<Customer> Function(Json payload) onSave,
) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: CustomerWorkspaceDialog(
          mode: CustomerDialogMode.edit,
          customer: Customer.fromJson(_customerJson()),
          onSave: onSave,
          loadPlaces: (level, {parentId = ''}) async => const [],
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('the version travels with the record', () {
    test('it is parsed off the response', () {
      expect(Customer.fromJson(_customerJson(version: 12)).version, 12);
    });

    test('a response without one reads as zero, not as version 1', () {
      // Zero is the signal for "the server did not publish one", which makes
      // the save send no precondition. Defaulting to 1 would send a version
      // nobody read and refuse every edit on an older backend.
      final Json json = _customerJson()..remove('version');
      expect(Customer.fromJson(json).version, 0);
    });

    test('the controller sends the version the record was read at', () async {
      final _CapturingApi api = _CapturingApi();
      final CustomerController controller = CustomerController(api);
      final Customer loaded = Customer.fromJson(_customerJson(version: 9));

      await controller.save(loaded, <String, dynamic>{'code': 'CUS-001'});

      expect(api.sentVersion, 9);
    });

    test('a create carries no precondition', () async {
      final _CapturingApi api = _CapturingApi();
      final CustomerController controller = CustomerController(api);

      await controller.save(null, <String, dynamic>{'code': 'CUS-002'});

      expect(api.sentVersion, isNull, reason: 'nothing exists to conflict with');
    });

    test('an unversioned record saves without a precondition', () async {
      final _CapturingApi api = _CapturingApi();
      final CustomerController controller = CustomerController(api);
      final Json json = _customerJson()..remove('version');

      await controller.save(Customer.fromJson(json), <String, dynamic>{});

      // An older backend must stay usable, not have every save refused.
      expect(api.sentVersion, isNull);
    });
  });

  group('what the user sees when they lose the race', () {
    testWidgets('a conflict says the typing is still there', (tester) async {
      await _pumpEditor(
        tester,
        (_) async => throw const ApiException(
          'This record changed since you loaded it. Reload and try again.',
          statusCode: 409,
        ),
      );

      await tester.enterText(
        find.widgetWithText(TextFormField, 'Customer name'),
        'Anand Agencies (renamed)',
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(find.textContaining('Somebody else saved this customer'),
          findsOneWidget);
      // The dialog stays open and keeps what was typed. Closing it is what
      // loses the work, so the message has to be read before that happens.
      expect(find.byType(CustomerWorkspaceDialog), findsOneWidget);
      expect(find.text('Anand Agencies (renamed)'), findsOneWidget);
    });

    testWidgets('an ordinary failure still shows the server message',
        (tester) async {
      await _pumpEditor(
        tester,
        (_) async => throw const ApiException(
          'Customer code already exists in this firm.',
          statusCode: 409,
        ).copyAsValidation(),
      );

      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      // A 422 is not a concurrency problem and must not be dressed as one.
      expect(find.text('Customer code already exists in this firm.'),
          findsOneWidget);
    });
  });
}

extension on ApiException {
  /// The same failure reported as validation rather than a conflict.
  ApiException copyAsValidation() =>
      ApiException(message, statusCode: 422, details: details);
}

class _CapturingApi extends ApiClient {
  _CapturingApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  int? sentVersion;
  bool called = false;

  @override
  Future<Customer> updateCustomer(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    called = true;
    sentVersion = expectedVersion;
    return Customer.fromJson(_customerJson());
  }

  @override
  Future<Customer> createCustomer(Json data) async {
    called = true;
    return Customer.fromJson(_customerJson());
  }
}
