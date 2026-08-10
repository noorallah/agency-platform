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

  factory AppSemanticColors.forScheme(ColorScheme scheme) {
    final bool dark = scheme.brightness == Brightness.dark;
    return AppSemanticColors(
      success: dark ? const Color(0xff4ade80) : const Color(0xff147d45),
      onSuccess: dark ? const Color(0xff052e16) : Colors.white,
      warning: dark ? const Color(0xffffb74d) : const Color(0xffb54708),
      onWarning: dark ? const Color(0xff3b1f00) : Colors.white,
      information: scheme.primary,
      onInformation: scheme.onPrimary,
      danger: scheme.error,
      onDanger: scheme.onError,
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
    );
  }
}

extension AppThemeTokens on BuildContext {
  AppSemanticColors get semanticColors =>
      Theme.of(this).extension<AppSemanticColors>() ??
      AppSemanticColors.forScheme(Theme.of(this).colorScheme);
}
