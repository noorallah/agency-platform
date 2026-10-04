import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import '../../models/agency_branding.dart';
import '../platform/app_storage.dart';

/// The agency's branding as it was last read from the server, kept on this PC
/// so the sign-in screen can show it on the very next start, before -- and
/// whether or not -- the server answers.
///
/// Two small files beside the preferences: `agency_branding.json` and the logo
/// bytes. Every call is wrapped: a cache that cannot be read or written is no
/// cache, never an error on the sign-in screen.
class AgencyBrandingCache {
  AgencyBrandingCache({Directory? directory}) : _directory = directory;

  final Directory? _directory;

  Directory get _dir =>
      _directory ??
      Directory(
        '${AppStorage.root}${Platform.pathSeparator}.agency_platform',
      );

  File get _jsonFile =>
      File('${_dir.path}${Platform.pathSeparator}agency_branding.json');
  File get _logoFile =>
      File('${_dir.path}${Platform.pathSeparator}agency_branding_logo.bin');

  /// What was cached for [server], or null. Synchronous on purpose: two files
  /// of a few kilobytes, and the first frame is what it is for.
  CachedAgencyBranding? readSync(String server) {
    try {
      if (!_jsonFile.existsSync()) return null;
      final dynamic decoded = jsonDecode(_jsonFile.readAsStringSync());
      if (decoded is! Map<String, dynamic>) return null;
      if (decoded['server'] != server) return null;
      final dynamic branding = decoded['branding'];
      if (branding is! Map<String, dynamic>) return null;
      final AgencyBranding parsed = AgencyBranding.fromJson(branding);
      if (!parsed.isSet) return null;
      Uint8List? logo;
      if (parsed.hasLogo && _logoFile.existsSync()) {
        logo = _logoFile.readAsBytesSync();
      }
      return CachedAgencyBranding(branding: parsed, logo: logo);
    } on Object {
      return null;
    }
  }

  /// Remember [branding] and [logo] for [server]; a branding that is not set
  /// clears the cache instead.
  Future<void> write(
    String server,
    AgencyBranding branding,
    Uint8List? logo,
  ) async {
    try {
      if (!branding.isSet) {
        await clear();
        return;
      }
      await _dir.create(recursive: true);
      await _jsonFile.writeAsString(
        jsonEncode(<String, Object?>{
          'server': server,
          'branding': <String, Object?>{
            'is_set': true,
            'agency_name': branding.agencyName,
            'tagline': branding.tagline,
            'accent_color': branding.accentColor,
            'has_logo': branding.hasLogo,
            'version': branding.version,
          },
        }),
      );
      if (branding.hasLogo && logo != null) {
        await _logoFile.writeAsBytes(logo);
      } else if (await _logoFile.exists()) {
        await _logoFile.delete();
      }
    } on Object {
      // A cache that cannot be written is simply not there next time.
    }
  }

  Future<void> clear() async {
    try {
      if (await _jsonFile.exists()) await _jsonFile.delete();
      if (await _logoFile.exists()) await _logoFile.delete();
    } on Object {
      // Nothing to do about it.
    }
  }
}

class CachedAgencyBranding {
  const CachedAgencyBranding({required this.branding, this.logo});

  final AgencyBranding branding;
  final Uint8List? logo;
}
