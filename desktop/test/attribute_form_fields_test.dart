import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/workspace/attribute_form_fields.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

AttributeDefinitionRecord _definition(
  String code, {
  String dataType = 'TEXT',
  bool mandatory = false,
}) =>
    AttributeDefinitionRecord(
      id: 'def-$code',
      code: code,
      name: code.replaceAll('_', ' '),
      dataType: dataType,
      mandatory: mandatory,
      isActive: true,
      applicableCategory: '',
    );

Future<void> _pump(
  WidgetTester tester,
  AttributeFieldController controller, {
  bool required = false,
  bool readOnly = false,
}) =>
    tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AttributeFormField(
            controller: controller,
            required: required,
            readOnly: readOnly,
          ),
        ),
      ),
    );

void main() {
  testWidgets('a text attribute renders a plain field and sends a string',
      (tester) async {
    final controller = AttributeFieldController(_definition('BATCH_NUMBER'));
    await _pump(tester, controller);

    await tester.enterText(find.byType(TextField), 'B-1001');
    expect(controller.payloadValue, 'B-1001');
    expect(controller.isEmpty, isFalse);
    expect(controller.validate(), isNull);
    controller.dispose();
  });

  testWidgets('a number attribute rejects letters and validates its value',
      (tester) async {
    final controller = AttributeFieldController(
      _definition('SHELF_LIFE_DAYS', dataType: 'NUMBER'),
    );
    await _pump(tester, controller);

    // The input formatter strips anything that cannot be part of a number.
    await tester.enterText(find.byType(TextField), '12abc.5');
    expect(controller.text.text, '12.5');
    expect(controller.validate(), isNull);

    controller.text.text = '1.2.3';
    expect(controller.validate(), contains('must be a number'));
    controller.dispose();
  });

  testWidgets('a date attribute is read-only and filled by the picker',
      (tester) async {
    final controller = AttributeFieldController(
      _definition('EXPIRY_DATE', dataType: 'DATE'),
    );
    await _pump(tester, controller);

    final TextField field = tester.widget(find.byType(TextField));
    expect(field.readOnly, isTrue, reason: 'typing a date by hand invites 422s');
    expect(find.byIcon(Icons.calendar_today_outlined), findsOneWidget);

    await tester.tap(find.byIcon(Icons.calendar_today_outlined));
    await tester.pumpAndSettle();
    expect(find.byType(DatePickerDialog), findsOneWidget);

    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();

    // Whatever the locale shows, the stored value is ISO-8601.
    expect(controller.text.text, matches(RegExp(r'^\d{4}-\d{2}-\d{2}$')));
    expect(controller.validate(), isNull);
    controller.dispose();
  });

  testWidgets('a boolean attribute renders a checkbox and sends a bool',
      (tester) async {
    final controller = AttributeFieldController(
      _definition('APPROVED', dataType: 'BOOLEAN'),
    );
    await _pump(tester, controller);

    expect(find.byType(Checkbox), findsOneWidget);
    expect(find.text('Not set'), findsOneWidget);
    expect(controller.isEmpty, isTrue);
    expect(controller.payloadValue, isNull);

    // Ticking a box reads as yes, so the first tap must not mean "No".
    await tester.tap(find.byType(Checkbox));
    await tester.pumpAndSettle();
    expect(controller.payloadValue, isTrue);
    expect(controller.payloadValue, isA<bool>());
    expect(find.text('Yes'), findsOneWidget);

    await tester.tap(find.byType(Checkbox));
    await tester.pumpAndSettle();
    expect(controller.payloadValue, isFalse);

    // An optional boolean can return to unanswered.
    await tester.tap(find.byType(Checkbox));
    await tester.pumpAndSettle();
    expect(controller.isEmpty, isTrue);
    controller.dispose();
  });

  testWidgets('a required boolean starts unanswered rather than defaulting to No',
      (tester) async {
    // Defaulting a required flag to false would let it be submitted without
    // ever being answered; for something like PRESCRIPTION_REQUIRED that is a
    // wrong answer rather than a missing one. The save-time required check is
    // what must refuse it.
    final controller = AttributeFieldController(
      _definition('PRESCRIBED', dataType: 'BOOLEAN', mandatory: true),
    );
    await _pump(tester, controller, required: true);

    expect(controller.isEmpty, isTrue);
    expect(find.text('Not set'), findsOneWidget);
    expect(controller.payloadValue, isNull);

    await tester.tap(find.byType(Checkbox));
    await tester.pumpAndSettle();
    expect(controller.payloadValue, isTrue);
    controller.dispose();
  });

  testWidgets('an existing boolean value is restored, not shown as text',
      (tester) async {
    final controller = AttributeFieldController(
      _definition('APPROVED', dataType: 'BOOLEAN'),
      initialValue: 'false',
    );
    await _pump(tester, controller);

    expect(controller.boolean, isFalse);
    expect(find.text('No'), findsOneWidget);
    expect(controller.text.text, isEmpty);
    controller.dispose();
  });

  testWidgets('a required field is starred and a read-only field is disabled',
      (tester) async {
    final controller = AttributeFieldController(_definition('MANUFACTURER'));
    await _pump(tester, controller, required: true, readOnly: true);

    expect(find.text('MANUFACTURER *'), findsOneWidget);
    expect(tester.widget<TextField>(find.byType(TextField)).readOnly, isTrue);
    controller.dispose();
  });

  test('clear resets a boolean as well as text', () {
    final text = AttributeFieldController(_definition('NOTE'));
    text.text.text = 'something';
    text.clear();
    expect(text.isEmpty, isTrue);

    final flag = AttributeFieldController(
      _definition('APPROVED', dataType: 'BOOLEAN'),
      initialValue: 'true',
    );
    expect(flag.isEmpty, isFalse);
    flag.clear();
    expect(flag.isEmpty, isTrue, reason: 'a stale boolean would be resubmitted');

    text.dispose();
    flag.dispose();
  });

  test('an unknown data type falls back to text rather than failing', () {
    final controller = AttributeFieldController(
      _definition('MYSTERY', dataType: 'SOMETHING_NEW'),
    );
    controller.text.text = 'value';
    expect(controller.payloadValue, 'value');
    expect(controller.validate(), isNull);
    controller.dispose();
  });
}
