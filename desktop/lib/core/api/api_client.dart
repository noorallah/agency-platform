import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../../models/entities.dart';
import '../preferences/user_preferences.dart';

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode, this.details});
  final String message;
  final int? statusCode;
  final Object? details;
  bool get isForbidden => statusCode == HttpStatus.forbidden;
  @override
  String toString() => message;
}

class AuthTokens {
  const AuthTokens({
    required this.accessToken,
    required this.refreshToken,
    required this.forcePasswordChange,
  });
  final String accessToken, refreshToken;
  final bool forcePasswordChange;

  factory AuthTokens.fromJson(Json json, {String? previousRefreshToken}) {
    final Json payload = _unwrapMap(json);
    return AuthTokens(
      accessToken: stringValue(payload['access_token']),
      refreshToken: stringValue(payload['refresh_token']).isEmpty
          ? previousRefreshToken ?? ''
          : stringValue(payload['refresh_token']),
      forcePasswordChange: boolValue(
        payload['force_password_change'] ?? payload['must_change_password'],
      ),
    );
  }
}

class ApiClient {
  ApiClient({
    required this.baseUrl,
    required this.accessToken,
    required this.refreshAccessToken,
    this.activeFirmId,
    this.onRequest,
  });

  final String baseUrl;
  final String? Function() accessToken;
  final Future<bool> Function() refreshAccessToken;
  final String? Function()? activeFirmId;
  final void Function()? onRequest;
  final HttpClient _httpClient = HttpClient();
  static const bool _developmentLogging =
      bool.fromEnvironment('API_DEBUG_LOGGING', defaultValue: false);

  Future<AuthTokens> login(String email, String password) async {
    final response = await request(
      'POST',
      '/api/v1/auth/login',
      authenticated: false,
      body: {'email': email, 'password': password},
    );
    return AuthTokens.fromJson(response);
  }

  Future<AuthTokens> refresh(String refreshToken) async {
    final response = await request(
      'POST',
      '/api/v1/auth/refresh',
      authenticated: false,
      body: {'refresh_token': refreshToken},
    );
    return AuthTokens.fromJson(response, previousRefreshToken: refreshToken);
  }

  Future<void> logout(String refreshToken) async {
    await request(
      'POST',
      '/api/v1/auth/logout',
      body: {'refresh_token': refreshToken},
    );
  }

  Future<void> changePassword(
      String currentPassword, String newPassword) async {
    await request(
      'POST',
      '/api/v1/auth/change-password',
      body: {
        'current_password': currentPassword,
        'new_password': newPassword,
      },
    );
  }

  Future<UserPreferences> getUserPreferences() async {
    final Json response = await request('GET', '/api/v1/me/preferences');
    return UserPreferences.fromJson(_unwrapMap(response));
  }

  Future<UserPreferences> updateUserPreferences(Json changes) async {
    final Json response = await request(
      'PATCH',
      '/api/v1/me/preferences',
      body: changes,
    );
    return UserPreferences.fromJson(_unwrapMap(response));
  }

  Future<UserPreferences> resetUserPreferences() async {
    final Json response = await request('POST', '/api/v1/me/preferences/reset');
    return UserPreferences.fromJson(_unwrapMap(response));
  }

  Future<List<AssignedFirm>> myFirms() async {
    final Json response = await request('GET', '/api/v1/me/firms');
    final dynamic data = response['data'];
    if (data is! List) {
      throw const ApiException('The API returned an invalid firm list.');
    }
    return data
        .whereType<Map>()
        .map((value) => AssignedFirm.fromJson(Map<String, dynamic>.from(value)))
        .toList();
  }

  Future<Json> dashboard() async => _unwrapMap(
        await request('GET', '/api/v1/dashboard'),
      );
  Future<PagedResult<Firm>> firms({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) =>
      _list('/api/v1/firms', Firm.fromJson, page, search,
          sortBy: sortBy, descending: descending);
  Future<PagedResult<PlatformUser>> users({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) =>
      _list('/api/v1/users', PlatformUser.fromJson, page, search,
          sortBy: sortBy, descending: descending);
  Future<PagedResult<Role>> roles({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) =>
      _list('/api/v1/roles', Role.fromJson, page, search,
          sortBy: sortBy, descending: descending);
  Future<PagedResult<Permission>> permissions({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) =>
      _list('/api/v1/permissions', Permission.fromJson, page, search,
          sortBy: sortBy, descending: descending);
  Future<List<AssignmentOption>> options(String resource) async {
    final PagedResult<AssignmentOption> result = await _list(
      '/api/v1/$resource',
      (json) => AssignmentOption(
        id: stringValue(json['id']),
        label: stringValue(json['code'] ?? json['name'] ?? json['email']),
      ),
      1,
      '',
      pageSize: 100,
    );
    return result.items;
  }

  Future<Json> create(String resource, Json body) =>
      request('POST', '/api/v1/$resource', body: body);
  Future<Json> update(
    String resource,
    String id,
    Json body, {
    bool partial = false,
  }) =>
      request(partial ? 'PATCH' : 'PUT', '/api/v1/$resource/$id', body: body);
  Future<void> delete(String resource, String id) =>
      request('DELETE', '/api/v1/$resource/$id');
  Future<void> setUserRoles(String userId, List<String> ids) =>
      request('PUT', '/api/v1/users/$userId/roles', body: {'ids': ids});
  Future<void> setUserFirms(
    String userId,
    List<String> firmIds,
    String primaryFirmId,
  ) =>
      request(
        'PUT',
        '/api/v1/users/$userId/firms',
        body: userFirmAssignmentsPayload(firmIds, primaryFirmId),
      );

  static Json userFirmAssignmentsPayload(
    List<String> firmIds,
    String primaryFirmId,
  ) {
    final Set<String> assignedFirmIds = {...firmIds};
    if (primaryFirmId.isNotEmpty) {
      assignedFirmIds.add(primaryFirmId);
    }
    return {
      'assignments': assignedFirmIds
          .map((firmId) => {
                'firm_id': firmId,
                'is_primary': firmId == primaryFirmId,
                'is_active': true,
              })
          .toList(),
    };
  }

  Future<void> setRolePermissions(String roleId, List<String> ids) =>
      request('PUT', '/api/v1/roles/$roleId/permissions', body: {'ids': ids});

  Future<Json> userAssignmentValues(String userId) async {
    final List<Json> responses = await Future.wait([
      request('GET', '/api/v1/users/$userId/roles'),
      request('GET', '/api/v1/users/$userId/firms'),
    ]);
    final Json roles = _unwrapMap(responses[0]);
    final dynamic firms = responses[1]['data'];
    final List<dynamic> memberships = firms is List ? firms : const [];
    final List<String> firmIds = memberships
        .whereType<Map>()
        .map((membership) => stringValue(membership['firm_id']))
        .where((id) => id.isNotEmpty)
        .toList();
    final List<String> primaryFirmIds = memberships
        .whereType<Map>()
        .where((membership) => boolValue(membership['is_primary']))
        .map((membership) => stringValue(membership['firm_id']))
        .toList();
    return {
      'role_ids': stringList(roles['ids']).join(','),
      'firm_ids': firmIds.join(','),
      'primary_firm_id': primaryFirmIds.isEmpty ? '' : primaryFirmIds.first,
    };
  }

  Future<Map<String, dynamic>> userFirmAssignmentValues(String userId) async {
    final Json response = await request('GET', '/api/v1/users/$userId/firms');
    final dynamic data = response['data'];
    final List<dynamic> memberships = data is List ? data : const [];
    final List<String> firmIds = memberships
        .whereType<Map>()
        .map((membership) => stringValue(membership['firm_id']))
        .where((id) => id.isNotEmpty)
        .toList();
    final List<String> primaryFirmIds = memberships
        .whereType<Map>()
        .where((membership) => boolValue(membership['is_primary']))
        .map((membership) => stringValue(membership['firm_id']))
        .where((id) => id.isNotEmpty)
        .toList();
    return {
      'firm_ids': firmIds.join(','),
      'primary_firm_id': primaryFirmIds.isEmpty ? '' : primaryFirmIds.first,
    };
  }

  Future<Json> roleAssignmentValues(String roleId) async {
    final Json response = await request(
      'GET',
      '/api/v1/roles/$roleId/permissions',
    );
    final Json data = _unwrapMap(response);
    return {'permission_ids': stringList(data['ids']).join(',')};
  }

  Future<PagedResult<T>> _list<T>(
    String path,
    T Function(Json) parser,
    int page,
    String search, {
    int pageSize = 20,
    String? sortBy,
    bool descending = true,
  }) async {
    final query = {
      'page': '$page',
      'page_size': '$pageSize',
      if (search.isNotEmpty) 'search': search,
      if (sortBy != null) 'sort_by': sortBy,
      if (sortBy != null) 'sort_direction': descending ? 'desc' : 'asc',
    };
    final Json response = await request('GET', path, query: query);
    return parsePagedResponse(response, parser);
  }

  static PagedResult<T> parsePagedResponse<T>(
    Json response,
    T Function(Json) parser,
  ) {
    final dynamic data = response['data'] ?? response;
    final List<dynamic> values = data is List
        ? data
        : (data is Map<String, dynamic> ? data['items'] as List? ?? [] : []);
    final dynamic pagination = response['pagination'];
    final int total = pagination is Map<String, dynamic>
        ? (pagination['total_records'] as num?)?.toInt() ?? values.length
        : (data is Map<String, dynamic>
            ? (data['total'] as num?)?.toInt() ?? values.length
            : values.length);
    return PagedResult(
      items: values.whereType<Map>().map((item) {
        return parser(Map<String, dynamic>.from(item));
      }).toList(),
      total: total,
    );
  }

  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
  }) async {
    final Uri uri = _uri(path, query);
    onRequest?.call();
    if (_developmentLogging) {
      stderr.writeln('API $method $uri');
    }
    try {
      final HttpClientRequest httpRequest =
          await _httpClient.openUrl(method, uri);
      httpRequest.headers.set(HttpHeaders.acceptHeader, 'application/json');
      if (authenticated && accessToken()?.isNotEmpty == true) {
        httpRequest.headers.set(
          HttpHeaders.authorizationHeader,
          'Bearer ${accessToken()}',
        );
      }
      final String? token = accessToken();
      if (authenticated && token?.isNotEmpty == true) {
        httpRequest.headers.set(
          HttpHeaders.authorizationHeader,
          'Bearer $token',
        );
      }
      final String? firmId = activeFirmId?.call();
      if (authenticated && firmId?.isNotEmpty == true) {
        httpRequest.headers.set('X-Firm-ID', firmId!);
      }
      if (body != null) {
        httpRequest.headers.contentType = ContentType.json;
        httpRequest.write(jsonEncode(body));
      }
      final HttpClientResponse response =
          await httpRequest.close().timeout(const Duration(seconds: 30));
      if (_developmentLogging) {
        stderr.writeln('API ${response.statusCode} $method $uri');
      }
      final String text = await utf8.decoder.bind(response).join();
      final dynamic decoded =
          text.isEmpty ? <String, dynamic>{} : jsonDecode(text);
      final Json payload = decoded is Map<String, dynamic>
          ? decoded
          : <String, dynamic>{'data': decoded};
      if (response.statusCode == HttpStatus.unauthorized &&
          authenticated &&
          !retrying &&
          await refreshAccessToken()) {
        return request(
          method,
          path,
          body: body,
          query: query,
          authenticated: authenticated,
          retrying: true,
        );
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final dynamic error = payload['error'];
        final String message = stringValue(
          error is Map<String, dynamic>
              ? error['message']
              : payload['message'] ?? payload['detail'],
        );
        throw ApiException(
          message.isEmpty
              ? 'Request failed (${response.statusCode}).'
              : message,
          statusCode: response.statusCode,
          details: error is Map<String, dynamic> ? error['details'] : null,
        );
      }
      return payload;
    } on SocketException {
      throw const ApiException('Cannot reach the API server.');
    } on TimeoutException {
      throw const ApiException('The API request timed out.');
    } on FormatException {
      throw const ApiException('The API returned an invalid JSON response.');
    }
  }

  Uri _uri(String path, Map<String, String>? query) {
    final String root = baseUrl.endsWith('/')
        ? baseUrl.substring(0, baseUrl.length - 1)
        : baseUrl;
    return Uri.parse('$root$path').replace(queryParameters: query);
  }
}

Json _unwrapMap(Json json) {
  final dynamic data = json['data'];
  return data is Map<String, dynamic> ? data : json;
}
