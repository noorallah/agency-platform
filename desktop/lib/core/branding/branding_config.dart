import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';

class BrandingConfig {
  const BrandingConfig({
    required this.appName,
    required this.windowName,
    required this.productName,
    required this.companyName,
    required this.logoPath,
    required this.splashPath,
    required this.version,
    required this.supportEmail,
    required this.supportWebsite,
    required this.copyright,
    required this.loginBackgroundColor,
    required this.loginAccentColor,
  });

  final String appName;
  final String windowName;
  final String productName;
  final String companyName;
  final String logoPath;
  final String splashPath;
  final String version;
  final String supportEmail;
  final String supportWebsite;
  final String copyright;
  final Color loginBackgroundColor;
  final Color loginAccentColor;

  File? get logoFile => _existingFile(logoPath);
  File? get splashFile => _existingFile(splashPath);

  static const BrandingConfig defaults = BrandingConfig(
    appName: 'Agency Platform',
    windowName: 'Agency Platform Desktop',
    productName: 'Agency Platform',
    companyName: 'Agency',
    logoPath: '',
    splashPath: '',
    version: '1.0.0',
    supportEmail: 'support@example.com',
    supportWebsite: 'https://example.com/support',
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
        return BrandingConfig.fromJson(decoded);
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

  factory BrandingConfig.fromJson(Map<String, dynamic> json) {
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

    return BrandingConfig(
      appName: value('app_name'),
      windowName: value('window_name'),
      productName: value('product_name'),
      companyName: value('company_name'),
      logoPath: optionalPath('logo_path'),
      splashPath: optionalPath('splash_path'),
      version: value('version'),
      supportEmail: value('support_email'),
      supportWebsite: value('support_website'),
      copyright: value('copyright'),
      loginBackgroundColor: _color(value('login_background_color')),
      loginAccentColor: _color(value('login_accent_color')),
    );
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
