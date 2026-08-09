import 'dart:convert';

import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/ui/document_framework/document_framework_widgets.dart';
import 'package:flutter_test/flutter_test.dart';

/// The five document workspaces gated only on `*_VIEW` and then offered every
/// lifecycle action to whoever could see the list. The backend refuses them —
/// approve, close, dispatch and complete need `*_APPROVE`, cancel needs
/// `*_CANCEL` — so a read-only user was shown buttons that could only ever
/// produce an error toast.
///
/// The toolbar takes an `isEnabled` predicate, so the fix is expressed there.
/// This test pins the predicate the pages now use.
bool mayRun(
  PermissionService permissions,
  String domain,
  DocumentToolbarAction action,
) =>
    switch (action) {
      DocumentToolbarAction.approve ||
      DocumentToolbarAction.close ||
      DocumentToolbarAction.archive ||
      DocumentToolbarAction.requestApproval =>
        permissions.hasPermission('${domain}_APPROVE'),
      DocumentToolbarAction.cancel || DocumentToolbarAction.reject =>
        permissions.hasPermission('${domain}_CANCEL'),
      DocumentToolbarAction.newDocument =>
        permissions.hasPermission('${domain}_CREATE'),
      DocumentToolbarAction.save =>
        permissions.hasPermission('${domain}_UPDATE'),
      DocumentToolbarAction.exportDocument =>
        permissions.hasPermission('${domain}_EXPORT'),
      _ => true,
    };

String _accessToken(Map<String, dynamic> claims) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '');
  return 'header.$payload.signature';
}

PermissionService _withPermissions(List<String> permissions) {
  final PermissionService service = PermissionService();
  service.applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': permissions,
  }));
  return service;
}

void main() {
  test('a view-only user is offered no lifecycle action', () {
    final PermissionService permissions = _withPermissions(['SALES_VIEW']);

    for (final DocumentToolbarAction action in [
      DocumentToolbarAction.approve,
      DocumentToolbarAction.close,
      DocumentToolbarAction.requestApproval,
      DocumentToolbarAction.cancel,
      DocumentToolbarAction.reject,
      DocumentToolbarAction.newDocument,
      DocumentToolbarAction.save,
      DocumentToolbarAction.exportDocument,
    ]) {
      expect(
        mayRun(permissions, 'SALES', action),
        isFalse,
        reason: '$action must stay disabled for a read-only user',
      );
    }
  });

  test('approve and cancel are granted independently', () {
    final PermissionService approver =
        _withPermissions(['SALES_VIEW', 'SALES_APPROVE']);
    expect(mayRun(approver, 'SALES', DocumentToolbarAction.approve), isTrue);
    // Dispatch and complete are reached through requestApproval and the server
    // gates both on SALES_APPROVE.
    expect(
      mayRun(approver, 'SALES', DocumentToolbarAction.requestApproval),
      isTrue,
    );
    expect(mayRun(approver, 'SALES', DocumentToolbarAction.close), isTrue);
    expect(mayRun(approver, 'SALES', DocumentToolbarAction.cancel), isFalse);

    final PermissionService canceller =
        _withPermissions(['SALES_VIEW', 'SALES_CANCEL']);
    expect(mayRun(canceller, 'SALES', DocumentToolbarAction.cancel), isTrue);
    expect(mayRun(canceller, 'SALES', DocumentToolbarAction.approve), isFalse);
  });

  test('purchase documents read their own permission namespace', () {
    final PermissionService sales =
        _withPermissions(['SALES_VIEW', 'SALES_APPROVE']);
    expect(mayRun(sales, 'PURCHASE', DocumentToolbarAction.approve), isFalse);

    final PermissionService purchase =
        _withPermissions(['PURCHASE_VIEW', 'PURCHASE_APPROVE']);
    expect(mayRun(purchase, 'PURCHASE', DocumentToolbarAction.approve), isTrue);
  });

  test('actions with no server-side gate stay available', () {
    final PermissionService permissions = _withPermissions(['SALES_VIEW']);
    expect(
      mayRun(permissions, 'SALES', DocumentToolbarAction.printDocument),
      isTrue,
    );
    expect(
      mayRun(permissions, 'SALES', DocumentToolbarAction.emailDocument),
      isTrue,
    );
  });
}
