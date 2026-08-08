import 'dart:convert';

import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:flutter_test/flutter_test.dart';

const String _firmA = '11111111-1111-1111-1111-111111111111';
const String _firmB = '22222222-2222-2222-2222-222222222222';

/// Build an unsigned token whose payload matches what the backend issues.
String _token({
  List<String> permissions = const [],
  Map<String, List<String>> firmPermissions = const {},
  List<String> roles = const [],
}) {
  String segment(Object value) =>
      base64Url.encode(utf8.encode(jsonEncode(value))).replaceAll('=', '');
  return '${segment({'alg': 'none'})}.'
      '${segment({
        'sub': 'user',
        'type': 'access',
        'roles': roles,
        'permissions': permissions,
        'firm_permissions': firmPermissions,
      })}.signature';
}

void main() {
  test('grants are scoped to the active firm, not merged across firms', () {
    // Admin in firm A, read-only in firm B — the shape that made the UI lie.
    final service = PermissionService()
      ..applyAccessToken(
        _token(
          firmPermissions: {
            _firmA: ['CUSTOMER_VIEW', 'CUSTOMER_CREATE', 'CUSTOMER_DELETE'],
            _firmB: ['CUSTOMER_VIEW'],
          },
        ),
        activeFirmId: _firmA,
      );

    expect(service.hasPermission('CUSTOMER_CREATE'), isTrue);

    service.setActiveFirm(_firmB);
    expect(service.hasPermission('CUSTOMER_VIEW'), isTrue);
    expect(
      service.hasPermission('CUSTOMER_CREATE'),
      isFalse,
      reason: 'holding it in firm A must not offer it while working in firm B',
    );
    expect(service.hasPermission('CUSTOMER_DELETE'), isFalse);
  });

  test('switching firm notifies listeners so the shell rebuilds', () {
    int notifications = 0;
    final service = PermissionService()..addListener(() => notifications++);
    service.applyAccessToken(
      _token(
        firmPermissions: {
          _firmA: ['PRODUCT_CREATE'],
          _firmB: ['PRODUCT_VIEW'],
        },
      ),
      activeFirmId: _firmA,
    );
    final int afterToken = notifications;

    service.setActiveFirm(_firmB);
    expect(notifications, greaterThan(afterToken));

    // Re-selecting the same firm changes nothing and must not churn the UI.
    final int afterSwitch = notifications;
    service.setActiveFirm(_firmB);
    expect(notifications, afterSwitch);
  });

  test('global permissions apply in every firm', () {
    final service = PermissionService()
      ..applyAccessToken(
        _token(
          permissions: ['USER_VIEW'],
          firmPermissions: {
            _firmA: ['CUSTOMER_CREATE'],
          },
        ),
        activeFirmId: _firmA,
      );

    expect(service.hasPermission('USER_VIEW'), isTrue);
    service.setActiveFirm(_firmB);
    expect(service.hasPermission('USER_VIEW'), isTrue,
        reason: 'firm-independent roles are not firm scoped');
    expect(service.hasPermission('CUSTOMER_CREATE'), isFalse);
  });

  test('a platform admin keeps every permission with no firm selected', () {
    // The backend gives platform admins the full list and no firm map.
    final service = PermissionService()
      ..applyAccessToken(
        _token(
          roles: ['platform_admin'],
          permissions: ['FIRM_CREATE', 'USER_CREATE', 'ROLE_CREATE'],
        ),
        activeFirmId: null,
      );

    expect(service.hasPermission('FIRM_CREATE'), isTrue);
    expect(service.hasAllPermissions(['USER_CREATE', 'ROLE_CREATE']), isTrue);
  });

  test('no firm selected means only global grants apply', () {
    final service = PermissionService()
      ..applyAccessToken(
        _token(
          firmPermissions: {
            _firmA: ['CUSTOMER_CREATE'],
          },
        ),
        activeFirmId: null,
      );

    expect(service.hasPermission('CUSTOMER_CREATE'), isFalse);
    service.setActiveFirm(_firmA);
    expect(service.hasPermission('CUSTOMER_CREATE'), isTrue);
  });

  test('grants for another firm remain inspectable for explaining a denial', () {
    final service = PermissionService()
      ..applyAccessToken(
        _token(
          firmPermissions: {
            _firmA: ['CUSTOMER_CREATE'],
            _firmB: ['CUSTOMER_VIEW'],
          },
        ),
        activeFirmId: _firmB,
      );

    expect(service.permissionsForFirm(_firmA), contains('CUSTOMER_CREATE'));
    expect(service.hasPermission('CUSTOMER_CREATE'), isFalse);
    expect(service.permissionsForFirm('unknown-firm'), isEmpty);
  });

  test('signing out clears every grant', () {
    final service = PermissionService()
      ..applyAccessToken(
        _token(
          permissions: ['USER_VIEW'],
          firmPermissions: {
            _firmA: ['CUSTOMER_CREATE'],
          },
        ),
        activeFirmId: _firmA,
      );
    expect(service.permissions, isNotEmpty);

    service.applyAccessToken(null);
    expect(service.permissions, isEmpty);
    expect(service.activeFirmId, isNull);
  });

  test('a malformed token grants nothing rather than throwing', () {
    final service = PermissionService()
      ..applyAccessToken('not-a-token', activeFirmId: _firmA);
    expect(service.permissions, isEmpty);

    service.applyAccessToken('a.!!!not-base64!!!.c', activeFirmId: _firmA);
    expect(service.permissions, isEmpty);
  });

  test('canUseAction requires every listed permission in the active firm', () {
    final service = PermissionService()
      ..applyAccessToken(
        _token(
          firmPermissions: {
            _firmA: ['CUSTOMER_VIEW', 'CUSTOMER_UPDATE'],
          },
        ),
        activeFirmId: _firmA,
      );

    expect(service.canUseAction(['CUSTOMER_VIEW', 'CUSTOMER_UPDATE']), isTrue);
    expect(service.canUseAction(['CUSTOMER_VIEW', 'CUSTOMER_DELETE']), isFalse);
    expect(service.canAccess(['CUSTOMER_VIEW', 'CUSTOMER_DELETE'],
        requiresAny: true), isTrue);
  });
}
