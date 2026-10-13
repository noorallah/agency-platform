// D-UI-63: the close question sees every kind of change, not only a typed box.
//
// `AskBeforeClosing` took a dialog's word for it, and the promotion dialog's
// word was `Form.onChanged`, which a switch or an added row never reaches.
// The wrapper now also compares what the inputs under it held at the first
// touch with what they hold when a close is asked for.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/pricing/promotion_dialog.dart';
import 'package:agency_desktop/ui/workspace/discard_prompt.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async =>
      <String, dynamic>{
        'data': const <Json>[],
        'pagination': <String, dynamic>{'total_records': 0},
      };
}

Future<void> _open(WidgetTester tester, Widget dialog) async {
  tester.view.physicalSize = const Size(1600, 1400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (BuildContext context) => TextButton(
          onPressed: () =>
              showDialog<Object?>(context: context, builder: (_) => dialog),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

Future<void> _cancel(WidgetTester tester) async {
  await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
  await tester.pumpAndSettle();
}

/// A small dialog with a switch and nothing typed anywhere.
class _SwitchDialog extends StatefulWidget {
  const _SwitchDialog();

  @override
  State<_SwitchDialog> createState() => _SwitchDialogState();
}

class _SwitchDialogState extends State<_SwitchDialog> {
  bool _on = false;

  @override
  Widget build(BuildContext context) => AskBeforeClosing(
        touched: () => false,
        what: 'record has not been saved',
        child: AlertDialog(
          title: const Text('Switch dialog'),
          content: Switch(
            key: const ValueKey('the-switch'),
            value: _on,
            onChanged: (bool value) => setState(() => _on = value),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).maybePop(),
              child: const Text('Cancel'),
            ),
          ],
        ),
      );
}

void main() {
  group('the shared wrapper', () {
    testWidgets('a switch flipped alone makes Cancel ask', (tester) async {
      await _open(tester, const _SwitchDialog());
      await tester.tap(find.byKey(const ValueKey('the-switch')));
      await tester.pumpAndSettle();
      await _cancel(tester);
      expect(find.text('Close without saving?'), findsOneWidget);
    });

    testWidgets('a switch flipped and flipped back closes without a question',
        (tester) async {
      await _open(tester, const _SwitchDialog());
      await tester.tap(find.byKey(const ValueKey('the-switch')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('the-switch')));
      await tester.pumpAndSettle();
      await _cancel(tester);
      expect(find.text('Close without saving?'), findsNothing);
      expect(find.text('Switch dialog'), findsNothing);
    });

    testWidgets('an untouched dialog closes without a question',
        (tester) async {
      await _open(tester, const _SwitchDialog());
      await _cancel(tester);
      expect(find.text('Close without saving?'), findsNothing);
      expect(find.text('Switch dialog'), findsNothing);
    });
  });

  group('the promotion dialog', () {
    testWidgets('a switch flipped on its own makes Cancel ask',
        (tester) async {
      await _open(tester, PromotionDialog(api: _Api()));
      final Finder tile =
          find.byKey(const ValueKey('promotion-requires-coupon'));
      await tester.ensureVisible(tile);
      await tester.tap(tile);
      await tester.pumpAndSettle();
      await _cancel(tester);
      expect(find.text('Close without saving?'), findsOneWidget);
    });

    testWidgets('a condition added on its own makes Cancel ask',
        (tester) async {
      await _open(tester, PromotionDialog(api: _Api()));
      final Finder add = find.text('Add condition');
      await tester.ensureVisible(add);
      await tester.tap(add);
      await tester.pumpAndSettle();
      await _cancel(tester);
      expect(find.text('Close without saving?'), findsOneWidget);
    });

    testWidgets('a benefit added on its own makes Cancel ask', (tester) async {
      await _open(tester, PromotionDialog(api: _Api()));
      final Finder add = find.text('Add benefit');
      await tester.ensureVisible(add);
      await tester.tap(add);
      await tester.pumpAndSettle();
      await _cancel(tester);
      expect(find.text('Close without saving?'), findsOneWidget);
    });

    testWidgets('an untouched promotion closes without a question',
        (tester) async {
      await _open(tester, PromotionDialog(api: _Api()));
      await _cancel(tester);
      expect(find.text('Close without saving?'), findsNothing);
      expect(find.text('New promotion'), findsNothing);
    });
  });
}
