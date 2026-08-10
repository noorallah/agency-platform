# Login Screen Guidelines

Implemented by `lib/ui/auth_screens.dart`. Covered by `test/login_screen_test.dart`.

## Layout

- Two columns above 1200px: an introduction panel and the sign-in card, centered
  as a pair. Below 1200px the introduction panel is **dropped, not stacked** —
  stacking it puts marketing copy between the user and the password field.
- Sign-in card width: 500-560 px (`_cardWidth`, currently 520).
- Below 580px of room between the toolbar and the footer (`_tightHeight`, which
  the 960x640 window minimum hits), the card sheds its brand mark and outer
  margin. Decoration gives way first; no control is ever removed.
- **The screen must not scroll.** The `SingleChildScrollView` is a safety net
  for a window smaller than the supported minimum, not the normal state.
  `fits without scrolling at every supported window size` asserts
  `maxScrollExtent == 0` at 1920x1080, 1600x900, 1366x768 and 960x640; it will
  fail if content is added back.
- Background is a low-contrast gradient only. No watermark icons — at 4-5%
  opacity they read as grey blocks off the edges rather than as texture.

## Tokens

Spacing comes from `AppSpacing`, corners from `AppRadius`, colors from
`Theme.of(context).colorScheme` and `context.semanticColors`. No raw pixel
literals for spacing, no `Colors.white` / `Colors.black`, no hardcoded font
sizes — this screen was the largest offender outside the tax module.

Type roles follow `DESKTOP_STYLE_GUIDE.md`: `headlineMedium` for the card and
panel headings, `titleSmall` for feature titles, `bodyMedium` for body,
`bodySmall` for captions and the footer, `labelMedium` for group labels.

## Header

- The brand appears **exactly once** at every width: in the introduction panel
  when it is shown, otherwise inside the card. `_BrandMark` renders
  `branding.logoFile` when one is configured and falls back to an icon.
- Card copy: `Welcome back`, then `Sign in to continue to <app name>.`
- The top bar carries appearance and settings only, right-aligned: a one-click
  light/dark toggle, the full `ThemeSelector` menu, and Application Settings.
  Do not re-add per-mode shortcut buttons — they duplicate the first section of
  the Appearance menu.

## Fields and actions

- Label the username field `Username / Email`. It carries no permanent helper
  text; the label already says what is accepted.
- Remembered usernames are offered through `RawAutocomplete`.
- Keep password visibility toggling and Caps Lock feedback (`_CapsLockNotice`,
  colored with `context.semanticColors.warning`).
- Group the two remembering choices under a `Sign-in options` label. Labels are
  self-describing (`Remember my username`, `Keep me signed in on this device`)
  so neither needs a subtitle. Leave the checkboxes at full hit-target size —
  this is the one screen that does not take the app's compact list density.
- `Forgot password?` is a right-aligned `TextButton` under the password field.
  It is recovery, not an alternative sign-in method, so it gets no `or` divider
  and no button weight of its own.
- Sign in is a `FilledButton` at 48px full width — never a hand-built
  `Ink`/`InkWell`, which has no focus ring, no keyboard activation and no
  disabled state.

## States

- **Error banners show the real message.** `_ErrorBanner`'s generic default is
  a fallback for a null error, not the text every failure gets; a user whose
  backend is unreachable must not be told to check their password.
- Banners are dismissible and keep the entered username/password intact.
- Show the spinner and `Signing in...` while authentication is in flight; the
  button is disabled but keeps the primary color so it still reads as the
  action in progress.
- Keep focus in the password field after a failed sign-in.

## Keyboard

- Enter: submit from the password field.
- Tab / Shift+Tab: native field traversal.
- Escape: dismiss the error banner.
- Ctrl+A / Ctrl+C: preserve the default text-field shortcuts.

## Accessibility

- Error banners are `Semantics(liveRegion: true)`.
- Preserve visible focus indicators — one reason the primary action must stay a
  real button.
- Use strong contrast for helper and footer text.

## Footer

- Application name, version, build number, and environment; environment is
  hidden in release builds.
- Styled to match the shell's `ApplicationStatusBar` (32px,
  `surfaceContainerHighest`, `bodySmall`, 14px icons) but implemented
  separately: that component always renders API and database connection
  indicators, and before sign-in neither has been probed, so both would sit at
  "checking" forever.
- Do not put controls here that do not work. The `English (India)` row was a
  bare `Row` with no tap handler and no i18n behind it; language lives in
  Application Settings as an acknowledged placeholder.
