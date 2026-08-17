import 'dart:convert';

/// A fake access token carrying [permissions].
///
/// `PermissionService` reads its claims out of the payload segment, so a test
/// needs a real three-part token even though nothing verifies the signature.
/// Several test files had built this inline; it is one helper now.
String accessTokenFor(List<String> permissions, {List<String>? roles}) {
  final String claims = base64Url
      .encode(utf8.encode(jsonEncode(<String, dynamic>{
        'roles': roles ?? const <String>['user'],
        'permissions': permissions,
      })))
      .replaceAll('=', '');
  return 'header.$claims.sig';
}
