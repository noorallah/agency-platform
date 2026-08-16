import 'dart:convert';

import 'package:flutter/foundation.dart';

/// Decodes access-token claims for UI visibility only; the API remains authoritative.
///
/// Grants are resolved the same way the backend resolves them: the global
/// permissions carried by firm-independent roles, plus the permissions the user
/// holds **in the active firm**. Merging every firm's grants together would show
/// a user actions they only hold elsewhere, and the API would then reject them.
class PermissionService extends ChangeNotifier {
  Set<String> _global = const {};
  Set<String> _roles = const {};
  Map<String, Set<String>> _byFirm = const {};
  String? _activeFirmId;
  Set<String> _effective = const {};

  /// Permissions that apply right now, for the firm currently selected.
  Set<String> get permissions => Set.unmodifiable(_effective);

  /// The firm whose grants are currently in effect, if any.
  String? get activeFirmId => _activeFirmId;

  /// Permissions the user holds in a firm they are not currently working in.
  ///
  /// Exposed so a screen can explain *why* an action is unavailable rather than
  /// simply hiding it.
  Set<String> permissionsForFirm(String firmId) =>
      Set.unmodifiable(_byFirm[firmId] ?? const <String>{});

  void applyAccessToken(String? token, {String? activeFirmId}) {
    final Map<String, dynamic>? claims = _decodePayload(token);
    _global = _stringClaims(claims?['permissions']).toSet();
    _roles = _stringClaims(claims?['roles']).toSet();

    final Object? firmClaims = claims?['firm_permissions'];
    final Map<String, Set<String>> byFirm = {};
    if (firmClaims is Map) {
      firmClaims.forEach((key, value) {
        if (key is String) byFirm[key] = _stringClaims(value).toSet();
      });
    }
    _byFirm = byFirm;
    _activeFirmId = activeFirmId;
    _recompute();
  }

  /// Re-resolve grants after the user switches firm, without a new token.
  void setActiveFirm(String? firmId) {
    if (_activeFirmId == firmId) return;
    _activeFirmId = firmId;
    _recompute();
  }

  void _recompute() {
    final Set<String> next = {
      ..._global,
      if (_activeFirmId != null) ...?_byFirm[_activeFirmId],
    };
    if (setEquals(_effective, next)) return;
    _effective = next;
    notifyListeners();
  }

  /// Whether the user carries the immutable platform-admin designation.
  ///
  /// A role rather than a permission, matching the backend: `platform_admin`
  /// short-circuits every permission check there, and a handful of endpoints —
  /// the shared geography masters among them — are guarded by the designation
  /// itself and by no permission code at all. Without this a screen has no
  /// honest way to tell whether to offer those actions.
  bool get isPlatformAdmin => _roles.contains('platform_admin');

  bool hasPermission(String permission) => _effective.contains(permission);

  bool hasAllPermissions(Iterable<String> permissions) =>
      permissions.every(_effective.contains);

  bool hasAnyPermission(Iterable<String> permissions) =>
      permissions.any(_effective.contains);

  bool canAccess(
    Iterable<String> permissions, {
    bool requiresAny = false,
  }) =>
      permissions.isEmpty ||
      (requiresAny
          ? hasAnyPermission(permissions)
          : hasAllPermissions(permissions));

  bool canUseModule(
    Iterable<String> permissions, {
    bool requiresAny = false,
  }) =>
      canAccess(permissions, requiresAny: requiresAny);

  bool canUseTab(
    Iterable<String> permissions, {
    bool requiresAny = false,
  }) =>
      canAccess(permissions, requiresAny: requiresAny);

  bool canUseAction(Iterable<String> permissions) =>
      hasAllPermissions(permissions);

  bool canViewPage(
    Iterable<String> permissions, {
    bool requiresAny = false,
  }) =>
      canAccess(permissions, requiresAny: requiresAny);

  static Map<String, dynamic>? _decodePayload(String? token) {
    if (token == null || token.isEmpty) return null;
    final List<String> parts = token.split('.');
    if (parts.length != 3 || parts[1].isEmpty) return null;
    try {
      final Object? decoded = jsonDecode(
        utf8.decode(base64Url.decode(base64Url.normalize(parts[1]))),
      );
      return decoded is Map<String, dynamic> ? decoded : null;
    } on ArgumentError {
      return null;
    } on FormatException {
      return null;
    }
  }

  static Set<String> _stringClaims(Object? value) {
    if (value is! List) return const {};
    return value.whereType<String>().toSet();
  }
}
