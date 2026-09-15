// Helper text under a field must be readable to the end.
//
// Flutter defaults `helperMaxLines` and `errorMaxLines` to **one** and clips
// the rest without a word. This application's helpers are sentences: "Lower
// case, digits, dots, dashes. Unique in this firm." needs **three** lines in a
// two-column form at 360 wide, and was being rendered in a 19-pixel box
// showing one. A helper nobody can read to the end is worse than none, because
// it reads as a rendering fault rather than a truncation.
//
// Reported on 2026-09-15 as "template code job name showing half text". Two
// wrong diagnoses came first, and both are worth recording because both were
// plausible and both were disproved by measuring rather than by argument:
//
//   * the **input theme's vertical padding** -- compact density gives 8 where
//     Material's outlined default is 24, so the floating label looked starved.
//     Measured: the label's overhang is a constant 5.125 at all three
//     densities, before and after changing that padding. It was never clipped.
//   * the **section card's clip** -- `EnterpriseSection` is a `Card` with
//     `Clip.antiAlias` and a children padding whose top was zero. Measured:
//     the children sit far below the card's top edge, under the expansion
//     header, and were never near the clip.
//
// Neither test could fail, which is the point: a guard that passes with the
// fix reverted is not a guard. This one measures the rendered box against the
// text's own unclamped height, so it fails the moment a helper is truncated
// again.

import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A real helper from a real form, and the width a two-column dialog gives it.
const String _helper =
    'Lower case, digits, dots, dashes. Unique in this firm.';
const double _halfWidth = 360;

/// What the helper was given, and what it needed.
Future<({double rendered, double needed, int lines})> _measure(
  WidgetTester tester, {
  required GridDensity density,
  String text = _helper,
  double width = _halfWidth,
}) async {
  await tester.pumpWidget(MaterialApp(
    theme: ThemeRegistry.themeFor(
      palette: AppPalette.values.first,
      brightness: Brightness.light,
      density: density,
    ),
    home: Scaffold(
      body: SizedBox(
        width: width,
        child: TextField(
          decoration: InputDecoration(
            labelText: 'Template code',
            helperText: text,
          ),
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();

  final Finder helper = find.text(text);
  final RenderBox box = tester.renderObject(helper);
  final TextPainter painter = TextPainter(
    text: TextSpan(text: text, style: tester.widget<Text>(helper).style),
    textDirection: TextDirection.ltr,
  )..layout(maxWidth: box.size.width);
  return (
    rendered: box.size.height,
    needed: painter.size.height,
    lines: painter.computeLineMetrics().length,
  );
}

void main() {
  for (final GridDensity density in GridDensity.values) {
    testWidgets('a wrapping helper is shown in full at ${density.name}',
        (tester) async {
      final ({double rendered, double needed, int lines}) box =
          await _measure(tester, density: density);

      expect(box.lines, greaterThan(1),
          reason: 'the premise: this helper does not fit on one line at '
              '$_halfWidth wide. If it now does, pick a longer one — the '
              'test is measuring nothing.');
      expect(
        box.rendered,
        greaterThanOrEqualTo(box.needed),
        reason: 'the helper needs ${box.needed} across ${box.lines} lines and '
            'was given ${box.rendered}, so the rest is clipped away with '
            'nothing on screen to say so.',
      );
    });
  }

  testWidgets('an error message may wrap too', (tester) async {
    // Same default, same clipping, and a refusal is the worst thing to
    // truncate: it is the one message whose whole job is being read.
    //
    // **Three lines, not unlimited.** Some server refusals here run to five or
    // six — the control-account one quotes a count and a reason — and a field
    // that grows without bound shoves the rest of a form around as somebody
    // types. Three covers every helper in the application and a refusal of
    // ordinary length; anything longer belongs in a notification, not under a
    // box. This asserts the ordinary case is whole, which is what was broken.
    await tester.pumpWidget(MaterialApp(
      theme: ThemeRegistry.themeFor(
        palette: AppPalette.values.first,
        brightness: Brightness.light,
        density: GridDensity.compact,
      ),
      home: const Scaffold(
        body: SizedBox(
          width: _halfWidth,
          child: TextField(
            decoration: InputDecoration(
              labelText: 'Template code',
              errorText: 'A template with this code already exists.',
            ),
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    final Finder error = find.textContaining('already exists');
    final RenderBox box = tester.renderObject(error);
    final TextPainter painter = TextPainter(
      text: TextSpan(
        text: tester.widget<Text>(error).data,
        style: tester.widget<Text>(error).style,
      ),
      textDirection: TextDirection.ltr,
    )..layout(maxWidth: box.size.width);

    expect(painter.computeLineMetrics().length, greaterThan(1));
    expect(box.size.height, greaterThanOrEqualTo(painter.size.height));
  });
}
