import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';

/// One slide of the sign-in showcase: a strength of the product, with a small
/// worked example and the screen where it lives.
///
/// Every claim must be built and shipped in the version the file travels
/// with. The slides are package content, like the rest of this file.
class BrandingStrength {
  const BrandingStrength({
    required this.kicker,
    required this.title,
    required this.summary,
    required this.headline,
    required this.text,
    required this.points,
    required this.examples,
    required this.findIt,
  });

  /// The small capitalised label above the headline, e.g. `TAX`.
  final String kicker;
  final String title;
  final String summary;
  final String headline;
  final String text;
  final List<String> points;
  final List<BrandingStrengthExample> examples;

  /// The menu path where the feature lives after sign-in.
  final String findIt;

  /// Throws [FormatException] when there is nothing to show (no headline).
  factory BrandingStrength.fromJson(Map<String, dynamic> json) {
    String text(String key) {
      final dynamic raw = json[key];
      return raw is String ? raw.trim() : '';
    }

    final String headline = text('headline');
    if (headline.isEmpty) {
      throw const FormatException('A strength needs a headline.');
    }
    final dynamic points = json['points'];
    final dynamic examples = json['examples'];
    return BrandingStrength(
      kicker: text('kicker'),
      title: text('title'),
      summary: text('summary'),
      headline: headline,
      text: text('text'),
      points: points is List
          ? points
              .whereType<String>()
              .map((String item) => item.trim())
              .where((String item) => item.isNotEmpty)
              .toList()
          : const <String>[],
      examples: examples is List
          ? examples
              .whereType<Map>()
              .map((Map item) => BrandingStrengthExample.fromJson(
                  Map<String, dynamic>.from(item)))
              .toList()
          : const <BrandingStrengthExample>[],
      findIt: text('find_it'),
    );
  }
}

/// One label/value row of a strength's worked example.
class BrandingStrengthExample {
  const BrandingStrengthExample({required this.label, required this.value});

  final String label;
  final String value;

  factory BrandingStrengthExample.fromJson(Map<String, dynamic> json) {
    final dynamic label = json['label'];
    final dynamic value = json['value'];
    return BrandingStrengthExample(
      label: label is String ? label.trim() : '',
      value: value is String ? value.trim() : '',
    );
  }
}

class BrandingConfig {
  const BrandingConfig({
    required this.appName,
    required this.windowName,
    required this.productName,
    required this.companyName,
    required this.logoPath,
    required this.splashPath,
    required this.version,
    required this.copyright,
    required this.loginBackgroundColor,
    required this.loginAccentColor,
    this.supportEmail = '',
    this.supportWebsite = '',
    this.supportPhone = '',
    this.supportWhatsapp = '',
    this.supportHours = '',
    this.tagline = '',
    this.companyLogoPath = '',
    this.productLogoPath = '',
    this.strengths = const <BrandingStrength>[],
    this.serverUrl = '',
  });

  final String appName;
  final String windowName;
  final String productName;
  final String companyName;
  final String logoPath;
  final String splashPath;
  final String version;
  final String copyright;
  final Color loginBackgroundColor;
  final Color loginAccentColor;

  /// Support details; empty means "not given", and a row with no value is
  /// hidden by the screens rather than shown blank.
  final String supportEmail;
  final String supportWebsite;
  final String supportPhone;
  final String supportWhatsapp;
  final String supportHours;

  /// The product's (and company's) tagline, or empty.
  final String tagline;
  final String companyLogoPath;
  final String productLogoPath;

  /// The slides of the sign-in showcase; empty when the file names none.
  final List<BrandingStrength> strengths;

  /// The server this installation was pointed at, or empty.
  ///
  /// Written by Setup -- `http://127.0.0.1:8000` on the server PC, the typed
  /// address on an app-only PC -- into the one file beside the executable, so
  /// it holds for every Windows user of the machine. A user's own choice in
  /// Application Settings still wins; this is the default they start from.
  final String serverUrl;

  /// The same branding with its window titled [windowName] -- how the phase 2
  /// app says which one it is in the Windows taskbar.
  BrandingConfig withWindowName(String windowName) => BrandingConfig(
        appName: appName,
        windowName: windowName,
        productName: productName,
        companyName: companyName,
        logoPath: logoPath,
        splashPath: splashPath,
        version: version,
        supportEmail: supportEmail,
        supportWebsite: supportWebsite,
        supportPhone: supportPhone,
        supportWhatsapp: supportWhatsapp,
        supportHours: supportHours,
        tagline: tagline,
        companyLogoPath: companyLogoPath,
        productLogoPath: productLogoPath,
        strengths: strengths,
        copyright: copyright,
        loginBackgroundColor: loginBackgroundColor,
        loginAccentColor: loginAccentColor,
        serverUrl: serverUrl,
      );

  File? get logoFile => _existingFile(logoPath);
  File? get splashFile => _existingFile(splashPath);
  File? get companyLogoFile => _existingFile(companyLogoPath);
  File? get productLogoFile => _existingFile(productLogoPath);

  static const BrandingConfig defaults = BrandingConfig(
    appName: 'Agency Platform',
    windowName: 'Agency Platform Desktop',
    productName: 'Agency Platform',
    companyName: 'Agency',
    logoPath: '',
    splashPath: '',
    version: '1.0.0',
    copyright: '© 2026 Agency',
    loginBackgroundColor: Color(0xfff6f8fc),
    loginAccentColor: Color(0xff155eef),
  );

  static Future<BrandingConfig> load({List<File>? candidates}) async {
    final List<File> files = candidates ?? _candidateFiles();
    for (final File file in files) {
      if (!await file.exists()) {
        continue;
      }
      try {
        final dynamic decoded = jsonDecode(await file.readAsString());
        if (decoded is! Map<String, dynamic>) {
          throw const FormatException(
              'Branding configuration must be a JSON object.');
        }
        // A logo named without a folder is looked for beside this file, so
        // the package carries its own artwork wherever it is installed.
        return BrandingConfig.fromJson(decoded, base: file.parent);
      } on FileSystemException catch (error) {
        debugPrint(
            'Unable to read branding configuration ${file.path}: $error');
      } on FormatException catch (error) {
        debugPrint('Invalid branding configuration ${file.path}: $error');
      }
    }
    debugPrint(
        'Branding configuration was not found; using built-in defaults.');
    return defaults;
  }

  static List<File> _candidateFiles() {
    final String separator = Platform.pathSeparator;
    return [
      File(
          '${File(Platform.resolvedExecutable).parent.path}${separator}config${separator}branding.json'),
      File(
          '${Directory.current.path}${separator}config${separator}branding.json'),
    ];
  }

  /// Read the branding file. A relative path to a picture is resolved
  /// against [base], the folder the file sits in; an absolute one, and any
  /// path when no folder is given, is kept as written.
  factory BrandingConfig.fromJson(
    Map<String, dynamic> json, {
    Directory? base,
  }) {
    String value(String key) {
      final dynamic raw = json[key];
      if (raw is! String || raw.trim().isEmpty) {
        throw FormatException(
            'Branding field "$key" must be a non-empty string.');
      }
      return raw.trim();
    }

    String optionalPath(String key) {
      final dynamic raw = json[key];
      if (raw == null) {
        return '';
      }
      if (raw is! String) {
        throw FormatException('Branding field "$key" must be a string.');
      }
      return raw.trim();
    }

    String picture(String key) {
      final String path = optionalPath(key);
      if (path.isEmpty || base == null || File(path).isAbsolute) return path;
      return '${base.path}${Platform.pathSeparator}$path';
    }

    return BrandingConfig(
      appName: value('app_name'),
      windowName: value('window_name'),
      productName: value('product_name'),
      companyName: value('company_name'),
      logoPath: picture('logo_path'),
      splashPath: picture('splash_path'),
      version: value('version'),
      supportEmail: optionalPath('support_email'),
      supportWebsite: optionalPath('support_website'),
      supportPhone: optionalPath('support_phone'),
      supportWhatsapp: optionalPath('support_whatsapp'),
      supportHours: optionalPath('support_hours'),
      tagline: optionalPath('tagline'),
      companyLogoPath: picture('company_logo_path'),
      productLogoPath: picture('product_logo_path'),
      strengths: _strengths(json['strengths']),
      copyright: value('copyright'),
      loginBackgroundColor: _color(value('login_background_color')),
      loginAccentColor: _color(value('login_accent_color')),
      serverUrl: optionalPath('server_url'),
    );
  }

  static List<BrandingStrength> _strengths(dynamic raw) {
    if (raw is! List) {
      return const <BrandingStrength>[];
    }
    final List<BrandingStrength> slides = <BrandingStrength>[];
    for (final dynamic item in raw) {
      try {
        if (item is! Map) {
          throw const FormatException('A strength must be an object.');
        }
        slides.add(
            BrandingStrength.fromJson(Map<String, dynamic>.from(item)));
      } on FormatException catch (error) {
        debugPrint('Skipping a malformed branding strength: $error');
      }
    }
    return slides;
  }

  static Color _color(String value) {
    final String hex = value.startsWith('#') ? value.substring(1) : value;
    if (!RegExp(r'^[0-9a-fA-F]{6}$').hasMatch(hex)) {
      throw FormatException('Invalid color "$value". Use #RRGGBB.');
    }
    return Color(int.parse('ff$hex', radix: 16));
  }

  static File? _existingFile(String path) {
    if (path.isEmpty) {
      return null;
    }
    final File file = File(path);
    return file.existsSync() ? file : null;
  }
}
