// The one mechanism behind D-DLG-1: a dialog that saves before it closes.
//
// A dialog that popped its typed values and left the create/update call to its
// caller showed a server refusal as a toast over a dialog that was already
// gone. `SaveInDialog` keeps the dialog open while the request runs, shows a
// refusal inside it with every field kept, and closes only on success,
// returning the saved record.

import 'dart:async';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Probe extends StatefulWidget {
  const _Probe({required this.onSave});

  final Future<String> Function(String typed) onSave;

  @override
  State<_Probe> createState() => _ProbeState();
}

class _ProbeState extends State<_Probe> with SaveInDialog<_Probe> {
  final TextEditingController _name = TextEditingController();

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            saveErrorBanner(),
            TextField(
              controller: _name,
              decoration: const InputDecoration(labelText: 'Name'),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
          FilledButton(
            onPressed: saving
                ? null
                : () => saveAndClose<String>(() => widget.onSave(_name.text)),
            child: const Text('Save'),
          ),
        ],
      );
}

Future<void> _open(
  WidgetTester tester,
  Future<String> Function(String) onSave,
  void Function(Object?) onResult,
) async {
  await tester.pumpWidget(MaterialApp(
    home: Builder(
      builder: (context) => TextButton(
        onPressed: () async => onResult(await showDialog<Object>(
          context: context,
          builder: (context) => _Probe(onSave: onSave),
        )),
        child: const Text('open'),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a refusal stays in the dialog, typing kept; a retry closes it',
      (tester) async {
    int calls = 0;
    Object? result;
    await _open(tester, (typed) async {
      calls++;
      if (calls == 1) throw const ApiException('Name already taken.');
      return 'saved:$typed';
    }, (value) => result = value);

    await tester.enterText(find.byType(TextField), 'Acme');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(find.byType(AlertDialog), findsOneWidget);
    expect(find.text('Name already taken.'), findsOneWidget);
    expect(find.text('Acme'), findsOneWidget);
    expect(result, isNull);

    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    expect(result, 'saved:Acme', reason: 'the saved record is returned');
  });

  testWidgets('the buttons are disabled while the save is in flight',
      (tester) async {
    final Completer<String> gate = Completer<String>();
    int calls = 0;
    Object? result;
    await _open(tester, (typed) {
      calls++;
      return gate.future;
    }, (value) => result = value);

    await tester.tap(find.text('Save'));
    await tester.pump();

    expect(find.byType(AlertDialog), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(find.widgetWithText(FilledButton, 'Save'))
          .onPressed,
      isNull,
    );
    expect(
      tester
          .widget<TextButton>(find.widgetWithText(TextButton, 'Cancel'))
          .onPressed,
      isNull,
    );
    expect(calls, 1);

    gate.complete('done');
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    expect(result, 'done');
  });
}
