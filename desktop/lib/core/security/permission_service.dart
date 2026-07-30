import 'dart:convert';

import 'package:flutter/foundation.dart';

/// Decodes access-token claims for UI visibility only; the API remains authoritative.
class PermissionService extends ChangeNotifier {
  Set<String> _permissions = const {};

  Set<String> get permissions => Set.unmodifiable(_permissions);

  void applyAccessToken(String? token) {
    final Map<String, dynamic>? claims = _decodePayload(token);
    final Set<String> permissions = _stringClaims(claims?['permissions']);
    if (setEquals(_permissions, permissions)) {
      return;
    }
    _permissions = permissions;
    notifyListeners();
  }

  bool hasPermission(String permission) => _permissions.contains(permission);

  bool hasAllPermissions(Iterable<String> permissions) =>
      permissions.every(_permissions.contains);

  bool hasAnyPermission(Iterable<String> permissions) =>
      permissions.any(_permissions.contains);

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
