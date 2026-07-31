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
  });

  final Color success;
  final Color onSuccess;
  final Color warning;
  final Color onWarning;
  final Color information;
  final Color onInformation;

  factory AppSemanticColors.forScheme(ColorScheme scheme) {
    final bool dark = scheme.brightness == Brightness.dark;
    return AppSemanticColors(
      success: dark ? const Color(0xff4ade80) : const Color(0xff147d45),
      onSuccess: dark ? const Color(0xff052e16) : Colors.white,
      warning: dark ? const Color(0xffffb74d) : const Color(0xffb54708),
      onWarning: dark ? const Color(0xff3b1f00) : Colors.white,
      information: scheme.primary,
      onInformation: scheme.onPrimary,
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
  }) =>
      AppSemanticColors(
        success: success ?? this.success,
        onSuccess: onSuccess ?? this.onSuccess,
        warning: warning ?? this.warning,
        onWarning: onWarning ?? this.onWarning,
        information: information ?? this.information,
        onInformation: onInformation ?? this.onInformation,
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
    );
  }
}

extension AppThemeTokens on BuildContext {
  AppSemanticColors get semanticColors =>
      Theme.of(this).extension<AppSemanticColors>() ??
      AppSemanticColors.forScheme(Theme.of(this).colorScheme);
}
