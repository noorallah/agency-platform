import 'package:agency_desktop/ui/workspace/reason_prompt.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// D-UI-23: Hold with the reason box empty closed the prompt and said
/// nothing. The prompt itself now refuses an empty reason, so every caller
/// (they all share `askForReason`) is covered at once.
void main() {
  Future<void> open(WidgetTester tester, void Function(String?) done) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () async => done(await askForReason(
              context,
              title: 'Hold order',
              explanation: 'Say why.',
              confirmLabel: 'Hold',
            )),
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
  }

  testWidgets('an empty reason keeps the prompt open and says it is needed',
      (tester) async {
    String? answer = 'unset';
    await open(tester, (value) => answer = value);
    expect(find.text('A reason is needed'), findsOneWidget);
    expect(
      tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Hold'))
          .onPressed,
      isNull,
    );
    // Enter on an empty box does not close it either.
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    expect(find.text('Hold order'), findsOneWidget);
    expect(answer, 'unset');
    // Blanks alone are still empty.
    await tester.enterText(find.byType(TextField), '   ');
    await tester.pump();
    expect(
      tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Hold'))
          .onPressed,
      isNull,
    );
  });

  testWidgets('a typed reason enables the button and is returned',
      (tester) async {
    String? answer;
    await open(tester, (value) => answer = value);
    await tester.enterText(find.byType(TextField), ' stock check ');
    await tester.pump();
    expect(find.text('A reason is needed'), findsNothing);
    await tester.tap(find.widgetWithText(FilledButton, 'Hold'));
    await tester.pumpAndSettle();
    expect(answer, 'stock check');
  });

  testWidgets('Cancel still dismisses with null', (tester) async {
    String? answer = 'unset';
    await open(tester, (value) => answer = value);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(answer, isNull);
  });
}
