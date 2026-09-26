import 'package:flutter/material.dart';

abstract final class AppSpacing {
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double xxl = 32;
}

abstract final class AppDimensions {
  static const double sidebarWidth = 248;
  static const double applicationHeaderHeight = 64;
  static const double minimumWorkspaceWidth = 960;
  static const double compactBreakpoint = 1000;
  static const double controlsWrapBreakpoint = 900;
  static const double dialogScale = .88;
  static const double dialogInset = 24;
  static const double detailsPanelWidth = 300;

  /// The width of a picker that names another document by its number.
  ///
  /// A seeded number reads `PO-WHOLE01-BR_NORTH-2026-2027-000001`, and the
  /// pickers print the date beside it; at 320 the closed field cut the
  /// number itself short, which is the one part the reader is choosing by.
  /// Wide enough for that shape at the body size, and still a single cell
  /// of the header's Wrap at 1366.
  static const double documentPickerWidth = 480;
}

/// The type scale, with line heights, which the app previously had none of.
///
/// Everything inherited Material's defaults, which are tuned for a phone held
/// at arm's length. This is an operator tool read for a full shift on a
/// 1366x768 screen at desk distance, so body text is set at 14.5 on a 1.5 line
/// height -- the ratio normal readability guidance asks for -- and headings
/// tighten as they grow, because generous leading on a large heading only
/// separates it from the thing it labels.
abstract final class AppTypography {
  /// Comfortable reading measure. Beyond roughly this many characters the eye
  /// loses the start of the next line.
  static const double readingMeasure = 72;

  static const double _body = 14.5;
  static const double _bodyHeight = 1.5;
  static const double _headingHeight = 1.2;

  static TextTheme textTheme(ColorScheme scheme) {
    final Color ink = scheme.onSurface;
    final Color muted = scheme.onSurfaceVariant;
    return TextTheme(
      displaySmall: TextStyle(
        fontSize: 30, height: _headingHeight, fontWeight: FontWeight.w700,
        letterSpacing: -0.4, color: ink,
      ),
      headlineMedium: TextStyle(
        fontSize: 24, height: _headingHeight, fontWeight: FontWeight.w700,
        letterSpacing: -0.3, color: ink,
      ),
      headlineSmall: TextStyle(
        fontSize: 20, height: 1.25, fontWeight: FontWeight.w700,
        letterSpacing: -0.2, color: ink,
      ),
      titleLarge: TextStyle(
        fontSize: 17, height: 1.3, fontWeight: FontWeight.w600,
        letterSpacing: -0.1, color: ink,
      ),
      titleMedium: TextStyle(
        fontSize: 15, height: 1.35, fontWeight: FontWeight.w600, color: ink,
      ),
      titleSmall: TextStyle(
        fontSize: 13.5, height: 1.35, fontWeight: FontWeight.w600, color: ink,
      ),
      bodyLarge: TextStyle(
        fontSize: 15.5, height: _bodyHeight, color: ink,
      ),
      bodyMedium: TextStyle(
        fontSize: _body, height: _bodyHeight, color: ink,
      ),
      bodySmall: TextStyle(
        fontSize: 13, height: 1.45, color: muted,
      ),
      labelLarge: TextStyle(
        fontSize: 13.5, height: 1.2, fontWeight: FontWeight.w600, color: ink,
      ),
      labelMedium: TextStyle(
        fontSize: 12.5, height: 1.2, fontWeight: FontWeight.w600, color: muted,
      ),
      // Column headers and eyebrows. Uppercase needs the extra tracking or it
      // reads as a solid block.
      labelSmall: TextStyle(
        fontSize: 11.5, height: 1.2, fontWeight: FontWeight.w600,
        letterSpacing: 0.6, color: muted,
      ),
    );
  }
}

abstract final class AppRadius {
  static const BorderRadius small = BorderRadius.all(Radius.circular(4));
  static const BorderRadius medium = BorderRadius.all(Radius.circular(8));
  static const BorderRadius large = BorderRadius.all(Radius.circular(12));
}

/// How tightly the interface packs, as real measurements rather than a label.
///
/// `GridDensity` has existed in preferences since the beginning with a setter
/// nothing called and a value nothing read. The one place density was honoured
/// changed rows-per-page and not row height, which is the opposite of what the
/// word means. These are the numbers that make it real, and because they are
/// applied through `ThemeData` every grid, list and field inherits them without
/// a single call site changing.
@immutable
class AppDensityTokens extends ThemeExtension<AppDensityTokens> {
  const AppDensityTokens({
    required this.rowHeight,
    required this.headerHeight,
    required this.pagePadding,
    required this.cardPadding,
    required this.fieldGap,
    required this.sectionGap,
    required this.visualDensity,
  });

  final double rowHeight;
  final double headerHeight;
  final double pagePadding;
  final double cardPadding;
  final double fieldGap;
  final double sectionGap;
  final VisualDensity visualDensity;

  /// Compact is the default on a small screen. At 1366x768 the chrome already
  /// costs a third of the height, so every reclaimed row is a row of data.
  static const AppDensityTokens compact = AppDensityTokens(
    rowHeight: 34,
    headerHeight: 38,
    pagePadding: AppSpacing.md,
    cardPadding: AppSpacing.md,
    fieldGap: AppSpacing.sm,
    sectionGap: AppSpacing.lg,
    visualDensity: VisualDensity(horizontal: -2, vertical: -2),
  );

  static const AppDensityTokens comfortable = AppDensityTokens(
    rowHeight: 42,
    headerHeight: 46,
    pagePadding: AppSpacing.lg,
    cardPadding: AppSpacing.lg,
    fieldGap: AppSpacing.md,
    sectionGap: AppSpacing.xl,
    visualDensity: VisualDensity(horizontal: -1, vertical: -1),
  );

  static const AppDensityTokens spacious = AppDensityTokens(
    rowHeight: 50,
    headerHeight: 54,
    pagePadding: AppSpacing.xl,
    cardPadding: AppSpacing.xl,
    fieldGap: AppSpacing.lg,
    sectionGap: AppSpacing.xxl,
    visualDensity: VisualDensity.standard,
  );

  @override
  AppDensityTokens copyWith({
    double? rowHeight,
    double? headerHeight,
    double? pagePadding,
    double? cardPadding,
    double? fieldGap,
    double? sectionGap,
    VisualDensity? visualDensity,
  }) =>
      AppDensityTokens(
        rowHeight: rowHeight ?? this.rowHeight,
        headerHeight: headerHeight ?? this.headerHeight,
        pagePadding: pagePadding ?? this.pagePadding,
        cardPadding: cardPadding ?? this.cardPadding,
        fieldGap: fieldGap ?? this.fieldGap,
        sectionGap: sectionGap ?? this.sectionGap,
        visualDensity: visualDensity ?? this.visualDensity,
      );

  @override
  AppDensityTokens lerp(
    covariant ThemeExtension<AppDensityTokens>? other,
    double t,
  ) {
    if (other is! AppDensityTokens) return this;
    return AppDensityTokens(
      rowHeight: lerpDouble(rowHeight, other.rowHeight, t),
      headerHeight: lerpDouble(headerHeight, other.headerHeight, t),
      pagePadding: lerpDouble(pagePadding, other.pagePadding, t),
      cardPadding: lerpDouble(cardPadding, other.cardPadding, t),
      fieldGap: lerpDouble(fieldGap, other.fieldGap, t),
      sectionGap: lerpDouble(sectionGap, other.sectionGap, t),
      visualDensity: t < 0.5 ? visualDensity : other.visualDensity,
    );
  }

  static double lerpDouble(double a, double b, double t) => a + (b - a) * t;
}

@immutable
class AppSemanticColors extends ThemeExtension<AppSemanticColors> {
  const AppSemanticColors({
    required this.success,
    required this.onSuccess,
    required this.warning,
    required this.onWarning,
    required this.information,
    required this.onInformation,
    required this.danger,
    required this.onDanger,
    required this.chrome,
    required this.onChrome,
    required this.onChromeMuted,
    required this.chromeActive,
  });

  final Color success;
  final Color onSuccess;
  final Color warning;
  final Color onWarning;
  final Color information;
  final Color onInformation;

  /// Destructive and blocked states. `COLOR_GUIDELINES.md` has listed this as a
  /// core role since the beginning; until now it did not exist, so every screen
  /// that needed it reached for `Colors.red` and stopped adapting to the theme.
  final Color danger;
  final Color onDanger;

  /// The phase 2 menu bar (UI_PHASE_2_DESIGN.md 4.1): a dark band in both
  /// themes, so the frame reads apart from the work beneath it. [onChrome]
  /// is its text, [onChromeMuted] its hints, [chromeActive] the ground of
  /// an area that is open or pointed at.
  final Color chrome;
  final Color onChrome;
  final Color onChromeMuted;
  final Color chromeActive;

  factory AppSemanticColors.forScheme(ColorScheme scheme) {
    final bool dark = scheme.brightness == Brightness.dark;
    return AppSemanticColors(
      // Light values darkened (2026-09-26) so each still reads at 4.5 : 1 as
      // text on a tinted status chip, not only on a plain ground (4.14).
      success: dark ? const Color(0xff4ade80) : const Color(0xff11703d),
      onSuccess: dark ? const Color(0xff052e16) : Colors.white,
      warning: dark ? const Color(0xffffb74d) : const Color(0xffa2400a),
      onWarning: dark ? const Color(0xff3b1f00) : Colors.white,
      information: scheme.primary,
      onInformation: scheme.onPrimary,
      danger: scheme.error,
      onDanger: scheme.onError,
      chrome: dark ? const Color(0xff0f1315) : const Color(0xff1e2a38),
      onChrome: const Color(0xffe6ebf0),
      onChromeMuted: const Color(0xffb3bfcc),
      chromeActive: dark ? const Color(0xff26313a) : const Color(0xff2f4156),
    );
  }

  @override
  AppSemanticColors copyWith({
    Color? success,
    Color? onSuccess,
    Color? warning,
    Color? onWarning,
    Color? information,
    Color? onInformation,
    Color? danger,
    Color? onDanger,
    Color? chrome,
    Color? onChrome,
    Color? onChromeMuted,
    Color? chromeActive,
  }) =>
      AppSemanticColors(
        success: success ?? this.success,
        onSuccess: onSuccess ?? this.onSuccess,
        warning: warning ?? this.warning,
        onWarning: onWarning ?? this.onWarning,
        information: information ?? this.information,
        onInformation: onInformation ?? this.onInformation,
        danger: danger ?? this.danger,
        onDanger: onDanger ?? this.onDanger,
        chrome: chrome ?? this.chrome,
        onChrome: onChrome ?? this.onChrome,
        onChromeMuted: onChromeMuted ?? this.onChromeMuted,
        chromeActive: chromeActive ?? this.chromeActive,
      );

  @override
  AppSemanticColors lerp(
    covariant ThemeExtension<AppSemanticColors>? other,
    double t,
  ) {
    if (other is! AppSemanticColors) return this;
    return AppSemanticColors(
      success: Color.lerp(success, other.success, t)!,
      onSuccess: Color.lerp(onSuccess, other.onSuccess, t)!,
      warning: Color.lerp(warning, other.warning, t)!,
      onWarning: Color.lerp(onWarning, other.onWarning, t)!,
      information: Color.lerp(information, other.information, t)!,
      onInformation: Color.lerp(onInformation, other.onInformation, t)!,
      danger: Color.lerp(danger, other.danger, t)!,
      onDanger: Color.lerp(onDanger, other.onDanger, t)!,
      chrome: Color.lerp(chrome, other.chrome, t)!,
      onChrome: Color.lerp(onChrome, other.onChrome, t)!,
      onChromeMuted: Color.lerp(onChromeMuted, other.onChromeMuted, t)!,
      chromeActive: Color.lerp(chromeActive, other.chromeActive, t)!,
    );
  }
}

extension AppThemeTokens on BuildContext {
  /// Spacing and sizing for the density the user has chosen.
  AppDensityTokens get density =>
      Theme.of(this).extension<AppDensityTokens>() ??
      AppDensityTokens.comfortable;

  AppSemanticColors get semanticColors =>
      Theme.of(this).extension<AppSemanticColors>() ??
      AppSemanticColors.forScheme(Theme.of(this).colorScheme);
}
