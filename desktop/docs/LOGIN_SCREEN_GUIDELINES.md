# Login Screen Guidelines

## Layout

- Center the login card vertically and horizontally.
- Target card width: 500-560 px.
- Keep generous internal padding and avoid cramped controls.
- Use a soft background gradient or watermark with very low opacity.

## Header

- Show the product name, then the welcome message.
- Use:
  - `Welcome Back`
  - `Sign in to continue.`
- Keep the brand mark larger than the default compact login mark.

## Fields and actions

- Label the username field `Username / Email`.
- Keep password visibility toggling and add Caps Lock feedback when applicable.
- Group sign-in options under a clear section.
- Make Forgot password look secondary and underline only on hover.
- Keep the sign-in button tall and disable it during submit.

## States

- Error banners must be dismissible and keep the entered username/password intact.
- Show the loading spinner and `Signing in...` text while authentication is in flight.
- Keep focus in the password field after a failed sign-in.

## Keyboard

- Enter: submit from the password field.
- Tab / Shift+Tab: native field traversal.
- Escape: dismiss the error banner.
- Ctrl+A / Ctrl+C: preserve the default text-field shortcuts.

## Accessibility

- Use strong contrast for helper and footer text.
- Preserve visible focus indicators.
- Increase hit targets for checkboxes and other touch/click targets.

## Development mode

- Show quick-login presets only in development builds.
- Autofill credentials only; never bypass authentication.

## Footer

- Show application name, version, build number, and environment.
- Hide environment details in production builds.
