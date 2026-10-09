import 'package:flutter/material.dart';
import 'package:window_manager/window_manager.dart';

import '../core/design/design_tokens.dart';
import 'agency_header.dart';
import 'sign_in_screen.dart';

/// What the app's own title bar says at the moment.
///
/// Either a line of text (the sign-in screen: the product, then "Sign in") or the
/// agency and the selected firm (the signed-in frame).
@immutable
class TitleBarContent {
  const TitleBarContent({this.text = '', this.agency, this.firm});

  final String text;
  final AgencyIdentity? agency;

  /// The selected firm, or null when none is selected.
  final String? firm;

  @override
  bool operator ==(Object other) =>
      other is TitleBarContent &&
      other.text == text &&
      identical(other.agency, agency) &&
      other.firm == firm;

  @override
  int get hashCode => Object.hash(text, identityHashCode(agency), firm);
}

/// The app's own title bar (decision B9, option 1; D-UI-6).
///
/// Windows' title bar is hidden for phase 2 on Windows and this strip takes
/// its place: the agency's logo, name and tagline, the selected firm as plain
/// text, and minimise, maximise and close. The agency therefore shows once,
/// and the menu bar below starts with Home.
///
/// [enabled] is set by `DesktopWindowController` once the window really has
/// no title bar of its own. A widget test, a phone and phase 1 leave it off,
/// and then nothing here is drawn and the agency stays on the menu strip.
class AppTitleBar {
  AppTitleBar._();

  /// Whether the window has no title bar of its own, so the app draws one.
  static bool enabled = false;

  /// What the strip shows. Screens set it; the strip listens.
  static final ValueNotifier<TitleBarContent> content =
      ValueNotifier<TitleBarContent>(const TitleBarContent());

  /// Show a line of text (a screen with no agency of its own to show).
  static void showText(String text) {
    content.value = TitleBarContent(text: text);
  }

  /// Show the agency and the selected firm.
  static void showAgency(AgencyIdentity agency, String? firm) {
    content.value = TitleBarContent(
      text: windowTitleFor(agency.name, firm),
      agency: agency,
      firm: firm,
    );
  }

  /// Put the strip above [child] when the app draws its own title bar.
  ///
  /// Used from `MaterialApp.builder`, so the strip stays above every route:
  /// a dialog does not cover it and the window can still be moved. The page
  /// below is told the height it really has.
  static Widget wrap(BuildContext context, Widget child) {
    if (!enabled) return child;
    final MediaQueryData media = MediaQuery.of(context);
    return Column(children: [
      const SizedBox(height: kWindowCaptionHeight, child: AppTitleBarStrip()),
      Expanded(
        child: MediaQuery(
          data: media.copyWith(
            size: Size(
              media.size.width,
              (media.size.height - kWindowCaptionHeight)
                  .clamp(0.0, double.infinity),
            ),
          ),
          child: child,
        ),
      ),
    ]);
  }
}

/// The strip itself: drag it to move the window, double-click to maximise.
class AppTitleBarStrip extends StatelessWidget {
  const AppTitleBarStrip({super.key});

  /// Room the three window buttons and the left padding take.
  static const double _buttonsAndPadding = 16 + 3 * 46 + 12;

  @override
  Widget build(BuildContext context) {
    final AppSemanticColors colors = context.semanticColors;
    final TextTheme text = Theme.of(context).textTheme;
    final double room =
        (MediaQuery.sizeOf(context).width - _buttonsAndPadding)
            .clamp(0.0, double.infinity);
    return ValueListenableBuilder<TitleBarContent>(
      valueListenable: AppTitleBar.content,
      builder: (context, shown, _) => WindowCaption(
        key: const ValueKey('app-title-bar'),
        brightness: Brightness.dark,
        backgroundColor: colors.chrome,
        title: SizedBox(
          width: room,
          child: _title(shown, colors, text),
        ),
      ),
    );
  }

  Widget _title(
    TitleBarContent shown,
    AppSemanticColors colors,
    TextTheme text,
  ) {
    final TextStyle? name = text.bodyMedium?.copyWith(
      color: colors.onChrome,
      fontWeight: FontWeight.w600,
    );
    final TextStyle? muted =
        text.bodyMedium?.copyWith(color: colors.onChromeMuted);
    final AgencyIdentity? agency = shown.agency;
    if (agency == null) {
      return Align(
        alignment: Alignment.centerLeft,
        child: Text(
          shown.text,
          key: const ValueKey('app-title-text'),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: name,
        ),
      );
    }
    final String firm = shown.firm ?? '';
    return Row(children: [
      ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 72),
        child: AgencyMark(
          name: agency.name,
          logo: agency.logo,
          logoFile: agency.logoFile,
          size: 22,
        ),
      ),
      const SizedBox(width: 8),
      Flexible(
        flex: 3,
        child: Text(
          agency.name,
          key: const ValueKey('agency-header-name'),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: name,
        ),
      ),
      if (agency.tagline.isNotEmpty) ...[
        const SizedBox(width: 10),
        Flexible(
          flex: 2,
          child: Text(
            agency.tagline,
            key: const ValueKey('agency-header-tagline'),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: text.bodySmall?.copyWith(color: colors.onChromeMuted),
          ),
        ),
      ],
      if (firm.isNotEmpty) ...[
        const SizedBox(width: 10),
        Text('>', style: muted),
        const SizedBox(width: 8),
        Flexible(
          flex: 3,
          child: Text(
            firm,
            key: const ValueKey('agency-header-firm'),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: muted,
          ),
        ),
      ],
    ]);
  }
}
