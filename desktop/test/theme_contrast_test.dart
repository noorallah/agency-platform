// Every colour pair the application draws text or a control with must be
// readable, and must stay readable when somebody changes a token.
//
// The owner's rule for phase 2 (docs/UI_PHASE_2_DESIGN.md 4.14, 2026-09-26):
// screens must be clearly visible and must not tire the eyes over a working
// day. Its measure is WCAG 2.2 AA -- text at 4.5 : 1 against its ground,
// and a control's edge or state marker at 3 : 1. D-QA-1 is what "too faint"
// looks like in practice: the title bar's hover state was there and could not
// be seen.
//
// The ratios are computed from the built `ThemeData`, not from a copy of the
// hex values, so this fails the moment a token or the tonal algorithm moves
// a pair below the line -- in every palette and in both brightnesses.

import 'package:agency_desktop/core/design/design_tokens.dart';
import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// WCAG contrast ratio between two opaque colours.
double _ratio(Color a, Color b) {
  final double la = a.computeLuminance();
  final double lb = b.computeLuminance();
  final double lighter = la > lb ? la : lb;
  final double darker = la > lb ? lb : la;
  return (lighter + 0.05) / (darker + 0.05);
}

const double _text = 4.5;
const double _control = 3;

void main() {
  // Phase 2's light theme takes the wireframe's own greys (owner,
  // 2026-09-26), so it is held to the same pairs as phase 1's.
  for (final bool wireframe in [false, true]) {
    for (final AppPalette palette in AppPalette.values) {
      for (final Brightness brightness in Brightness.values) {
        final String name = '${palette.wireName} ${brightness.name}'
            '${wireframe ? ' (phase 2)' : ''}';
        final ThemeData theme = ThemeRegistry.themeFor(
          palette: palette,
          brightness: brightness,
          wireframe: wireframe,
        );
        final ColorScheme c = theme.colorScheme;
        final AppSemanticColors s = theme.extension<AppSemanticColors>()!;

        // A selected grid row is primary laid over the card at the alpha the
        // theme's data-table style uses; its text has to read on the blend.
        final Color selectedRow = Color.alphaBlend(
          c.primary
              .withValues(alpha: brightness == Brightness.dark ? 0.24 : 0.14),
          c.surfaceContainerLowest,
        );

        final Map<String, (Color, Color, double)> pairs = {
          'body text on the page': (c.onSurface, c.surface, _text),
          'body text on a card or field': (
            c.onSurface,
            c.surfaceContainerLowest,
            _text
          ),
          'body text on a header row': (
            c.onSurface,
            c.surfaceContainerLow,
            _text
          ),
          'secondary text on the page': (c.onSurfaceVariant, c.surface, _text),
          'secondary text on a card': (
            c.onSurfaceVariant,
            c.surfaceContainerLowest,
            _text
          ),
          'secondary text on a header row': (
            c.onSurfaceVariant,
            c.surfaceContainerLow,
            _text
          ),
          'text on a selected row': (c.onSurface, selectedRow, _text),
          'primary button label': (c.onPrimary, c.primary, _text),
          'link or text button on a card': (
            c.primary,
            c.surfaceContainerLowest,
            _text
          ),
          'error text on a card': (c.error, c.surfaceContainerLowest, _text),
          'success badge': (s.onSuccess, s.success, _text),
          'warning badge': (s.onWarning, s.warning, _text),
          'danger badge': (c.onError, c.error, _text),
          'neutral badge': (
            c.onSurfaceVariant,
            c.surfaceContainerHighest,
            _text
          ),
          'success text on a card': (
            s.success,
            c.surfaceContainerLowest,
            _text
          ),
          'warning text on a card': (
            s.warning,
            c.surfaceContainerLowest,
            _text
          ),
          'a field or button edge': (
            c.outline,
            c.surfaceContainerLowest,
            _control
          ),
          'a field edge on the page': (c.outline, c.surface, _control),
          // The border a field is actually drawn with, which is what phase 1
          // got wrong: the tonal outline passed, but fields were edged with the
          // decorative `outlineVariant` at about 1.3 : 1.
          'the edge a text field is drawn with': (
            theme.inputDecorationTheme.enabledBorder!.borderSide.color,
            c.surfaceContainerLowest,
            _control
          ),
          'focus ring': (c.primary, c.surfaceContainerLowest, _control),
          'menu bar text': (s.onChrome, s.chrome, _text),
          'menu bar hint': (s.onChromeMuted, s.chrome, _text),
          'search box text on its fill': (
            s.onChromeMuted,
            s.chromeActive,
            _text
          ),
          'menu bar text on an open area': (s.onChrome, s.chromeActive, _text),
          'the bar under the current area': (
            s.chromeIndicator,
            s.chrome,
            _control
          ),
          'that bar on an open area': (
            s.chromeIndicator,
            s.chromeActive,
            _control
          ),
        };

        for (final MapEntry<String, (Color, Color, double)> pair
            in pairs.entries) {
          test('$name: ${pair.key}', () {
            final double ratio = _ratio(pair.value.$1, pair.value.$2);
            expect(
              ratio,
              greaterThanOrEqualTo(pair.value.$3),
              reason: '${pair.key} is ${ratio.toStringAsFixed(2)} : 1 in the '
                  '$name theme; UI_PHASE_2_DESIGN.md 4.14 asks for '
                  '${pair.value.$3} : 1',
            );
          });
        }

        test('$name: no pure white or pure black ground or text', () {
          for (final Color color in [
            c.surface,
            c.surfaceContainerLowest,
            c.onSurface,
          ]) {
            // Phase 2 light is the wireframe's white by the owner's choice
            // (2026-09-26); black is still never used.
            if (!(wireframe && brightness == Brightness.light)) {
              expect(color, isNot(const Color(0xffffffff)));
            }
            expect(color, isNot(const Color(0xff000000)));
          }
        });
      }
    }
  }
}
