import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../../models/geography.dart';
import '../../models/entities.dart';
import '../../models/audit.dart';
import '../../models/finance.dart';
import '../../models/physical_count.dart';
import '../../models/settlement.dart';
import '../../models/settlement_direction.dart';
import '../../models/batch_serial.dart';
import '../../models/branch_warehouse.dart';
import '../../models/customer.dart';
import '../../models/diagnostics.dart';
import '../../models/document_framework.dart';
import '../../models/print_template.dart';
import '../../models/product.dart';
import '../../models/quotation.dart';
import '../../models/sales_invoice.dart';
import '../../models/sales_return.dart';
import '../../models/goods_receipt.dart';
import '../../models/purchase.dart';
import '../../models/sales_territory.dart';
import '../../models/tax_framework.dart';
import '../../models/uom_packaging.dart';
import '../../models/inventory.dart';
import '../../models/vendor.dart';
import '../preferences/desktop_preferences_service.dart';
import '../preferences/user_preferences.dart';

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode, this.details});
  final String message;
  final int? statusCode;
  final Object? details;
  bool get isForbidden => statusCode == HttpStatus.forbidden;

  /// Somebody else saved this record after we loaded it.
  ///
  /// Only reachable when the request carried an `If-Match` precondition — the
  /// server accepts a write without one, so a caller that does not send the
  /// version it read never sees this and silently overwrites instead.
  bool get isConflict => statusCode == HttpStatus.conflict;
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

  Future<Json> globalSearch({
    required String query,
    String category = 'all',
    int page = 1,
    int pageSize = 20,
    List<String> entityTypes = const [],
    bool includeDeleted = false,
  }) async =>
      _unwrapMap(
        await request(
          'GET',
          '/api/v1/search',
          query: {
            'query': query,
            'category': category,
            'page': '$page',
            'page_size': '$pageSize',
            if (entityTypes.isNotEmpty) 'entity_types': entityTypes.join(','),
            if (includeDeleted) 'include_deleted': 'true',
          },
        ),
      );

  Future<PagedResult<Firm>> firms({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) =>
      _list('/api/v1/firms', Firm.fromJson, page, search,
          sortBy: sortBy, descending: descending);

  /// Sends queued crash reports.
  ///
  /// Returns whether the server accepted the batch, so the caller knows whether
  /// it may delete them. Never throws: reporting a failure must not create one.
  Future<bool> reportClientErrors(List<Map<String, Object?>> reports) async {
    if (reports.isEmpty) return true;
    try {
      await request(
        'POST',
        '/api/v1/diagnostics/client-errors',
        body: {'reports': reports},
      );
      return true;
    } on ApiException {
      return false;
    }
  }

  /// Faults collapsed by fingerprint, most recently seen first.
  ///
  /// Reports live in the **platform** store rather than per firm: a crash is
  /// telemetry for whoever maintains the product, and a fault split across
  /// firm stores could not be counted or ranked. The server resolves that
  /// itself, so no firm header decides what comes back.
  Future<PagedResult<ErrorReportGroup>> errorGroups({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? source,
  }) =>
      _list(
        '/api/v1/diagnostics/errors',
        ErrorReportGroup.fromJson,
        page,
        search,
        pageSize: pageSize,
        additionalQuery: {
          if (source != null && source.isNotEmpty) 'source': source,
        },
      );

  /// The individual occurrences of one fault, newest first.
  Future<List<ErrorReport>> errorOccurrences(String fingerprint) async {
    final Json response = await request(
      'GET',
      '/api/v1/diagnostics/errors/${Uri.encodeComponent(fingerprint)}',
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => ErrorReport.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  /// Build a firm's dedicated database, schema and tables.
  ///
  /// Returns the server's message, which distinguishes a fresh build from a
  /// firm that was already provisioned. Safe to call again after a failure.
  Future<String> provisionFirmStorage(String firmId) async {
    final Json response =
        await request('POST', '/api/v1/firms/$firmId/provision');
    return stringValue(response['message']).isEmpty
        ? 'Firm storage provisioned.'
        : stringValue(response['message']);
  }

  Future<PagedResult<PlatformUser>> users({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) =>
      _list('/api/v1/users', PlatformUser.fromJson, page, search,
          pageSize: pageSize, sortBy: sortBy, descending: descending);
  Future<PagedResult<Role>> roles({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) =>
      _list('/api/v1/roles', Role.fromJson, page, search,
          sortBy: sortBy, descending: descending);

  /// Lists permissions, honouring a caller-chosen page size.
  ///
  /// `pageSize` is an extra optional named parameter, so this still satisfies
  /// the narrower `load` signature every `ResourceDefinition` uses today — the
  /// other list methods keep the server default until they need otherwise.
  Future<PagedResult<Permission>> permissions({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) =>
      _list('/api/v1/permissions', Permission.fromJson, page, search,
          pageSize: pageSize, sortBy: sortBy, descending: descending);

  Future<PagedResult<BusinessProfileRecord>> businessProfiles({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) =>
      _list(
        '/api/v1/business-framework/profiles',
        BusinessProfileRecord.fromJson,
        page,
        search,
        sortBy: sortBy,
        descending: descending,
      );

  Future<PagedResult<BusinessFeatureRecord>> businessFeatures({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) =>
      _list(
        '/api/v1/business-framework/features',
        BusinessFeatureRecord.fromJson,
        page,
        search,
        sortBy: sortBy,
        descending: descending,
      );

  Future<PagedResult<BusinessModuleRecord>> businessModules({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) =>
      _list(
        '/api/v1/business-framework/modules',
        BusinessModuleRecord.fromJson,
        page,
        search,
        sortBy: sortBy,
        descending: descending,
      );

  /// The rules that make an attribute mandatory for a product category.
  Future<PagedResult<CategoryAttributeRuleRecord>> categoryAttributeRules({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) =>
      _list(
        '/api/v1/business-framework/category-attribute-rules',
        CategoryAttributeRuleRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
      );

  Future<PagedResult<AttributeDefinitionRecord>> attributeDefinitions({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) =>
      _list(
        '/api/v1/business-framework/attribute-definitions',
        AttributeDefinitionRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
      );

  Future<PagedResult<TaxSystemRecord>> taxSystems({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    String? status,
  }) =>
      _list(
        '/api/v1/tax-framework/systems',
        TaxSystemRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: {if (status != null) 'status': status},
      );

  Future<TaxSystemRecord> createTaxSystem(Json data) async =>
      TaxSystemRecord.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/tax-framework/systems', body: data)),
      );

  /// [expectedVersion] is the `version` of the record the user opened,
  /// sent as `If-Match`. Omitting it saves with no precondition, which is
  /// what an older backend and a record with no published version get.
  Future<TaxSystemRecord> updateTaxSystem(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      TaxSystemRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/tax-framework/systems/$id',
          body: data,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deleteTaxSystem(String id) =>
      request('DELETE', '/api/v1/tax-framework/systems/$id');

  Future<TaxSystemRecord> restoreTaxSystem(String id) async =>
      TaxSystemRecord.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/tax-framework/systems/$id/restore')),
      );

  Future<PagedResult<TaxComponentRecord>> taxComponents({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    String? taxSystemId,
  }) =>
      _list(
        '/api/v1/tax-framework/components',
        TaxComponentRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: {
          if (taxSystemId != null && taxSystemId.isNotEmpty)
            'tax_system_id': taxSystemId,
        },
      );

  Future<TaxComponentRecord> createTaxComponent(Json data) async =>
      TaxComponentRecord.fromJson(
        _unwrapMap(await request('POST', '/api/v1/tax-framework/components',
            body: data)),
      );

  /// [expectedVersion] is the `version` of the record the user opened,
  /// sent as `If-Match`. Omitting it saves with no precondition, which is
  /// what an older backend and a record with no published version get.
  Future<TaxComponentRecord> updateTaxComponent(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      TaxComponentRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/tax-framework/components/$id',
          body: data,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deleteTaxComponent(String id) =>
      request('DELETE', '/api/v1/tax-framework/components/$id');

  Future<TaxComponentRecord> restoreTaxComponent(String id) async =>
      TaxComponentRecord.fromJson(
        _unwrapMap(await request(
            'POST', '/api/v1/tax-framework/components/$id/restore')),
      );

  Future<PagedResult<TaxProfileRecord>> taxProfiles({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    String? taxSystemId,
  }) =>
      _list(
        '/api/v1/tax-framework/profiles',
        TaxProfileRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: {
          if (taxSystemId != null && taxSystemId.isNotEmpty)
            'tax_system_id': taxSystemId,
        },
      );

  Future<TaxProfileRecord> createTaxProfile(Json data) async =>
      TaxProfileRecord.fromJson(
        _unwrapMap(await request('POST', '/api/v1/tax-framework/profiles',
            body: data)),
      );

  /// [expectedVersion] is the `version` of the record the user opened,
  /// sent as `If-Match`. Omitting it saves with no precondition, which is
  /// what an older backend and a record with no published version get.
  Future<TaxProfileRecord> updateTaxProfile(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      TaxProfileRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/tax-framework/profiles/$id',
          body: data,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deleteTaxProfile(String id) =>
      request('DELETE', '/api/v1/tax-framework/profiles/$id');

  Future<TaxProfileRecord> restoreTaxProfile(String id) async =>
      TaxProfileRecord.fromJson(
        _unwrapMap(await request(
            'POST', '/api/v1/tax-framework/profiles/$id/restore')),
      );

  Future<List<TaxCountryMappingRecord>> taxCountryMappings() async {
    final Json response =
        await request('GET', '/api/v1/tax-framework/country-mappings');
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) =>
            TaxCountryMappingRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<TaxCountryMappingRecord> createTaxCountryMapping(Json data) async =>
      TaxCountryMappingRecord.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/tax-framework/country-mappings',
              body: data),
        ),
      );

  Future<TaxCountryMappingRecord> updateTaxCountryMapping(
          String id, Json data) async =>
      TaxCountryMappingRecord.fromJson(
        _unwrapMap(
          await request('PUT', '/api/v1/tax-framework/country-mappings/$id',
              body: data),
        ),
      );

  Future<void> deleteTaxCountryMapping(String id) =>
      request('DELETE', '/api/v1/tax-framework/country-mappings/$id');

  Future<List<TaxMigrationMappingRecord>> taxMigrationMappings() async {
    final Json response =
        await request('GET', '/api/v1/tax-framework/migration-mappings');
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) =>
            TaxMigrationMappingRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<TaxMigrationMappingRecord> createTaxMigrationMapping(
          Json data) async =>
      TaxMigrationMappingRecord.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/tax-framework/migration-mappings',
              body: data),
        ),
      );

  Future<TaxMigrationMappingRecord> updateTaxMigrationMapping(
          String id, Json data) async =>
      TaxMigrationMappingRecord.fromJson(
        _unwrapMap(
          await request('PUT', '/api/v1/tax-framework/migration-mappings/$id',
              body: data),
        ),
      );

  Future<void> deleteTaxMigrationMapping(String id) =>
      request('DELETE', '/api/v1/tax-framework/migration-mappings/$id');

  Future<List<EffectiveDateRecord>> taxEffectiveDates() async {
    final Json response =
        await request('GET', '/api/v1/tax-framework/effective-dates');
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) =>
            EffectiveDateRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<TaxSettingsRecord> taxSettings() async => TaxSettingsRecord.fromJson(
        _unwrapMap(await request('GET', '/api/v1/tax-framework/settings')),
      );

  Future<TaxSettingsRecord> updateTaxSettings(Json data) async =>
      TaxSettingsRecord.fromJson(
        _unwrapMap(
            await request('PUT', '/api/v1/tax-framework/settings', body: data)),
      );

  Future<List<TaxHistoryRecord>> taxHistory({int limit = 200}) async {
    final Json response = await request(
      'GET',
      '/api/v1/tax-framework/history',
      query: {'limit': '$limit'},
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) =>
            TaxHistoryRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<PagedResult<TaxRuleRecord>> taxRules({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) =>
      _list(
        '/api/v1/tax-framework/rules',
        TaxRuleRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
      );

  Future<TaxRuleRecord> createTaxRule(Json data) async =>
      TaxRuleRecord.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/tax-framework/rules', body: data)),
      );

  /// [expectedVersion] is the `version` of the record the user opened,
  /// sent as `If-Match`. Omitting it saves with no precondition, which is
  /// what an older backend and a record with no published version get.
  Future<TaxRuleRecord> updateTaxRule(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      TaxRuleRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/tax-framework/rules/$id',
          body: data,
          expectedVersion: expectedVersion,
        )),
      );

  Future<TaxRuleRecord> restoreTaxRule(String id) async =>
      TaxRuleRecord.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/tax-framework/rules/$id/restore')),
      );

  Future<void> deleteTaxRule(String id) =>
      request('DELETE', '/api/v1/tax-framework/rules/$id');

  Future<List<TaxRuleConditionRecord>> taxRuleConditions(
      {String? ruleId}) async {
    final Json response = await request(
      'GET',
      '/api/v1/tax-framework/rule-conditions',
      query: {
        if (ruleId != null && ruleId.isNotEmpty) 'rule_id': ruleId,
      },
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) =>
            TaxRuleConditionRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<List<TaxRulePriorityRecord>> taxRulePriorities() async {
    final Json response =
        await request('GET', '/api/v1/tax-framework/rule-priorities');
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) =>
            TaxRulePriorityRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<List<TaxRuleRecord>> taxRuleHistory({String? code}) async {
    final Json response = await request(
      'GET',
      '/api/v1/tax-framework/rule-history',
      query: {if (code != null && code.isNotEmpty) 'code': code},
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => TaxRuleRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<List<TaxRuleExecutionLogRecord>> taxRuleExecutionLogs(
      {int limit = 200}) async {
    final Json response = await request(
      'GET',
      '/api/v1/tax-framework/execution-logs',
      query: {'limit': '$limit'},
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) =>
            TaxRuleExecutionLogRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  /// Reads the whole configuration of one tax system: the system, its
  /// components and its profiles in a single call.
  Future<Json> taxSetup(String systemId) =>
      request('GET', '/api/v1/tax-framework/setup/$systemId');

  Future<Json> createTaxSetup(Json body) =>
      request('POST', '/api/v1/tax-framework/setup', body: body);

  Future<Json> updateTaxSetup(String systemId, Json body) =>
      request('PUT', '/api/v1/tax-framework/setup/$systemId', body: body);

  /// Returns the raw simulation envelope, for the simulator screen that
  /// renders every field the engine reports rather than a parsed subset.
  Future<Json> taxSimulation(Json body) =>
      request('POST', '/api/v1/tax-framework/simulate', body: body);

  Future<TaxRuleSimulationResultRecord> simulateTaxRule(Json data) async =>
      TaxRuleSimulationResultRecord.fromJson(
        _unwrapMap(await request('POST', '/api/v1/tax-framework/simulate',
            body: data)),
      );

  Future<PagedResult<Customer>> customers({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    CustomerQuery filters = const CustomerQuery(),
  }) =>
      _list(
        '/api/v1/customers',
        Customer.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: filters.toQuery(),
      );

  Future<Customer> createCustomer(Json data) async =>
      Customer.fromJson(_unwrapMap(
        await request('POST', '/api/v1/customers', body: data),
      ));

  /// Replace one customer.
  ///
  /// [expectedVersion] is the `version` of the record the user opened. Sent as
  /// `If-Match`, it turns a concurrent edit into a refusal instead of a silent
  /// overwrite — which matters most here, because this update replaces the
  /// whole address and contact collection, so the loser of a race does not
  /// merge badly, they lose every row they entered.
  Future<Customer> updateCustomer(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      Customer.fromJson(_unwrapMap(
        await request(
          'PUT',
          '/api/v1/customers/$id',
          body: data,
          expectedVersion: expectedVersion,
        ),
      ));

  Future<void> deleteCustomer(String id) =>
      request('DELETE', '/api/v1/customers/$id');

  Future<Customer> restoreCustomer(String id) async =>
      Customer.fromJson(_unwrapMap(
        await request('POST', '/api/v1/customers/$id/restore'),
      ));

  Future<String> exportCustomers({String search = ''}) => downloadText(
        '/api/v1/customers/export',
        query: {if (search.isNotEmpty) 'search': search},
      );

  Future<CustomerReceivableSummary> customerReceivableSummary(
          String customerId) async =>
      CustomerReceivableSummary.fromJson(
        _unwrapMap(
          await request(
            'GET',
            '/api/v1/customers/$customerId/receivables/summary',
          ),
        ),
      );

  Future<PagedResult<CustomerReceivableTransaction>>
      customerReceivableTransactions(
    String customerId, {
    int page = 1,
    int pageSize = 20,
  }) =>
          _list(
            '/api/v1/customers/$customerId/receivables/transactions',
            CustomerReceivableTransaction.fromJson,
            page,
            '',
            pageSize: pageSize,
          );

  Future<CustomerReceivableTransaction> postCustomerReceivableTransaction(
    String customerId,
    Json data,
  ) async =>
      CustomerReceivableTransaction.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/customers/$customerId/receivables/transactions',
            body: data,
          ),
        ),
      );

  /// Ask whether one more document fits inside the customer's credit limit.
  ///
  /// [amount] is the value of the document being considered, so the answer is
  /// about the state the save would produce rather than the state it left.
  Future<CustomerCreditStatus> customerCreditStatus(
    String customerId, {
    String amount = '0',
  }) async =>
      CustomerCreditStatus.fromJson(
        _unwrapMap(
          await request(
            'GET',
            '/api/v1/customers/$customerId/credit-status',
            query: {'amount': amount},
          ),
        ),
      );

  Future<CreditControlSettings> creditControlSettings() async =>
      CreditControlSettings.fromJson(
        _unwrapMap(await request('GET', '/api/v1/customers/credit-settings')),
      );

  Future<CreditControlSettings> updateCreditControlSettings(
    CreditControlSettings settings,
  ) async =>
      CreditControlSettings.fromJson(
        _unwrapMap(
          await request(
            'PUT',
            '/api/v1/customers/credit-settings',
            body: settings.toJson(),
          ),
        ),
      );

  /// The firm's vendor categories.
  ///
  /// `sortBy` and `descending` are here because `ResourceDefinition.load`
  /// requires the shape; the endpoint orders by name and offers no choice, so
  /// they are accepted and ignored rather than sent as a parameter nothing
  /// reads.
  Future<PagedResult<VendorClassification>> vendorCategories({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'name',
    bool descending = false,
  }) =>
      _list(
        '/api/v1/vendors/categories',
        VendorClassification.fromJson,
        page,
        search,
        pageSize: pageSize,
      );

  /// The firm's vendor types.
  Future<PagedResult<VendorClassification>> vendorTypes({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'name',
    bool descending = false,
  }) =>
      _list(
        '/api/v1/vendors/types',
        VendorClassification.fromJson,
        page,
        search,
        pageSize: pageSize,
      );

  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) =>
      _list(
        '/api/v1/vendors',
        Vendor.fromJson,
        page,
        search,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: filters.toQuery(),
      );

  Future<Vendor> createVendor(Json data) async => Vendor.fromJson(_unwrapMap(
        await request('POST', '/api/v1/vendors', body: data),
      ));

  /// Replace one vendor.
  ///
  /// [expectedVersion] is the `version` of the record the user opened. This
  /// update replaces six child collections — contacts, addresses, banking, tax
  /// registrations, attachments and notes — so losing a race here costs more
  /// than any other master in the product.
  Future<Vendor> updateVendor(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      Vendor.fromJson(_unwrapMap(
        await request(
          'PUT',
          '/api/v1/vendors/$id',
          body: data,
          expectedVersion: expectedVersion,
        ),
      ));

  Future<void> deleteVendor(String id) =>
      request('DELETE', '/api/v1/vendors/$id');

  Future<Vendor> restoreVendor(String id) async => Vendor.fromJson(_unwrapMap(
        await request('POST', '/api/v1/vendors/$id/restore'),
      ));

  Future<int> bulkDeleteVendors(List<String> ids) async {
    final Json response = await request(
      'POST',
      '/api/v1/vendors/bulk-delete',
      body: {'ids': ids},
    );
    final Json data = _unwrapMap(response);
    return (data['affected'] as num?)?.toInt() ?? 0;
  }

  Future<int> bulkRestoreVendors(List<String> ids) async {
    final Json response = await request(
      'POST',
      '/api/v1/vendors/bulk-restore',
      body: {'ids': ids},
    );
    final Json data = _unwrapMap(response);
    return (data['affected'] as num?)?.toInt() ?? 0;
  }

  Future<String> exportVendors({String search = ''}) => downloadText(
        '/api/v1/vendors/export',
        query: {if (search.isNotEmpty) 'search': search},
      );

  Future<PagedResult<BranchRecord>> branches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BranchQuery filters = const BranchQuery(),
  }) =>
      _list(
        '/api/v1/branches',
        BranchRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: filters.toQuery(),
      );

  Future<BranchRecord> createBranch(Json data) async => BranchRecord.fromJson(
        _unwrapMap(await request('POST', '/api/v1/branches', body: data)),
      );

  /// Create several branches in one request.
  ///
  /// The server writes the batch in a single transaction, so a rejected import
  /// leaves nothing behind and the corrected file can simply be re-sent.
  Future<List<BranchRecord>> importBranches(List<Json> records) async {
    final Json response = await request(
      'POST',
      '/api/v1/branches/import',
      body: {'records': records},
    );
    return _unwrapList(response, BranchRecord.fromJson);
  }

  Future<BranchRecord> updateBranch(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      BranchRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/branches/$id',
          body: data,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deleteBranch(String id) =>
      request('DELETE', '/api/v1/branches/$id');

  Future<BranchRecord> restoreBranch(String id) async => BranchRecord.fromJson(
        _unwrapMap(await request('POST', '/api/v1/branches/$id/restore')),
      );

  Future<int> bulkDeleteBranches(List<String> ids) async {
    final Json response = await request(
      'POST',
      '/api/v1/branches/bulk-delete',
      body: {'ids': ids},
    );
    return (response['data']?['affected'] as num?)?.toInt() ?? 0;
  }

  Future<int> bulkRestoreBranches(List<String> ids) async {
    final Json response = await request(
      'POST',
      '/api/v1/branches/bulk-restore',
      body: {'ids': ids},
    );
    return (response['data']?['affected'] as num?)?.toInt() ?? 0;
  }

  Future<String> exportBranches({String search = ''}) => downloadText(
        '/api/v1/branches/export',
        query: {if (search.isNotEmpty) 'search': search},
      );

  Future<PagedResult<WarehouseRecord>> warehouses({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    WarehouseQuery filters = const WarehouseQuery(),
  }) =>
      _list(
        '/api/v1/warehouses',
        WarehouseRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: filters.toQuery(),
      );

  Future<WarehouseRecord> createWarehouse(Json data) async =>
      WarehouseRecord.fromJson(
        _unwrapMap(await request('POST', '/api/v1/warehouses', body: data)),
      );

  /// Create several warehouses in one request, all or nothing.
  Future<List<WarehouseRecord>> importWarehouses(List<Json> records) async {
    final Json response = await request(
      'POST',
      '/api/v1/warehouses/import',
      body: {'records': records},
    );
    return _unwrapList(response, WarehouseRecord.fromJson);
  }

  Future<WarehouseRecord> updateWarehouse(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      WarehouseRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/warehouses/$id',
          body: data,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deleteWarehouse(String id) =>
      request('DELETE', '/api/v1/warehouses/$id');

  Future<WarehouseRecord> restoreWarehouse(String id) async =>
      WarehouseRecord.fromJson(
        _unwrapMap(await request('POST', '/api/v1/warehouses/$id/restore')),
      );

  Future<int> bulkDeleteWarehouses(List<String> ids) async {
    final Json response = await request(
      'POST',
      '/api/v1/warehouses/bulk-delete',
      body: {'ids': ids},
    );
    return (response['data']?['affected'] as num?)?.toInt() ?? 0;
  }

  Future<int> bulkRestoreWarehouses(List<String> ids) async {
    final Json response = await request(
      'POST',
      '/api/v1/warehouses/bulk-restore',
      body: {'ids': ids},
    );
    return (response['data']?['affected'] as num?)?.toInt() ?? 0;
  }

  Future<String> exportWarehouses({String search = ''}) => downloadText(
        '/api/v1/warehouses/export',
        query: {if (search.isNotEmpty) 'search': search},
      );

  Future<List<TypeRecord>> branchTypes({bool includeDeleted = false}) async {
    final Json response = await request(
      'GET',
      '/api/v1/branch-types',
      query: {if (includeDeleted) 'include_deleted': 'true'},
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => TypeRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<TypeRecord> createBranchType(Json data) async => TypeRecord.fromJson(
        _unwrapMap(await request('POST', '/api/v1/branch-types', body: data)),
      );

  Future<TypeRecord> updateBranchType(String id, Json data) async =>
      TypeRecord.fromJson(
        _unwrapMap(
            await request('PUT', '/api/v1/branch-types/$id', body: data)),
      );

  Future<void> deleteBranchType(String id) =>
      request('DELETE', '/api/v1/branch-types/$id');

  Future<List<TypeRecord>> warehouseTypes({bool includeDeleted = false}) async {
    final Json response = await request(
      'GET',
      '/api/v1/warehouse-types',
      query: {if (includeDeleted) 'include_deleted': 'true'},
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => TypeRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<TypeRecord> createWarehouseType(Json data) async =>
      TypeRecord.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/warehouse-types', body: data)),
      );

  Future<TypeRecord> updateWarehouseType(String id, Json data) async =>
      TypeRecord.fromJson(
        _unwrapMap(
            await request('PUT', '/api/v1/warehouse-types/$id', body: data)),
      );

  Future<void> deleteWarehouseType(String id) =>
      request('DELETE', '/api/v1/warehouse-types/$id');

  Future<List<StorageNodeRecord>> storageNodes(
    String warehouseId, {
    bool includeDeleted = false,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/warehouses/$warehouseId/storage-nodes',
      query: {if (includeDeleted) 'include_deleted': 'true'},
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) =>
            StorageNodeRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<StorageNodeRecord> createStorageNode(Json data) async =>
      StorageNodeRecord.fromJson(
        _unwrapMap(await request('POST', '/api/v1/warehouses/storage-nodes',
            body: data)),
      );

  Future<StorageNodeRecord> updateStorageNode(String id, Json data) async =>
      StorageNodeRecord.fromJson(
        _unwrapMap(
          await request('PUT', '/api/v1/warehouses/storage-nodes/$id',
              body: data),
        ),
      );

  Future<void> deleteStorageNode(String id) =>
      request('DELETE', '/api/v1/warehouses/storage-nodes/$id');

  Future<PagedResult<Product>> products({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    ProductQuery filters = const ProductQuery(),
  }) {
    final int normalizedPageSize = pageSize.clamp(1, 100);
    return _list(
      '/api/v1/products',
      Product.fromJson,
      page,
      search,
      pageSize: normalizedPageSize,
      sortBy: sortBy,
      descending: descending,
      additionalQuery: filters.toQuery(),
    );
  }

  Future<PagedResult<InventoryRecord>> inventory({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'updated_at',
    bool descending = true,
    InventoryQuery filters = const InventoryQuery(),
  }) =>
      _list(
        '/api/v1/inventory',
        InventoryRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: filters.toQuery(),
      );

  Future<InventoryRecord> inventoryRecord(
    String id, {
    bool includeDeleted = false,
  }) async =>
      InventoryRecord.fromJson(
        _unwrapMap(
          await request(
            'GET',
            '/api/v1/inventory/$id',
            query: {if (includeDeleted) 'include_deleted': 'true'},
          ),
        ),
      );

  /// [expectedVersion] is the `version` of the record the user opened,
  /// sent as `If-Match`. Omitting it saves with no precondition, which is
  /// what an older backend and a record with no published version get.
  Future<InventoryRecord> updateInventoryRecord(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      InventoryRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/inventory/$id',
          body: data,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deleteInventoryRecord(String id) =>
      request('DELETE', '/api/v1/inventory/$id');

  // ── Batch & Serial ──────────────────────────────────────────────────────────

  Future<PagedResult<BatchRecord>> batches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BatchQuery filters = const BatchQuery(),
  }) =>
      _list(
        '/api/v1/batch-serial/batches',
        BatchRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: filters.toQueryParams(),
      );

  Future<BatchRecord> batchRecord(String id) async => BatchRecord.fromJson(
        _unwrapMap(await request('GET', '/api/v1/batch-serial/batches/$id')),
      );

  Future<BatchRecord> createBatch(Json data) async => BatchRecord.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/batch-serial/batches', body: data)),
      );

  /// [expectedVersion] is the `version` of the record the user opened,
  /// sent as `If-Match`. Omitting it saves with no precondition, which is
  /// what an older backend and a record with no published version get.
  Future<BatchRecord> updateBatch(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      BatchRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/batch-serial/batches/$id',
          body: data,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deleteBatch(String id) =>
      request('DELETE', '/api/v1/batch-serial/batches/$id');

  Future<BatchSummaryRecord> batchSummary() async =>
      BatchSummaryRecord.fromJson(
        _unwrapMap(
            await request('GET', '/api/v1/batch-serial/batches/summary')),
      );

  Future<ExpiryDashboardRecord> expiryDashboard() async =>
      ExpiryDashboardRecord.fromJson(
        _unwrapMap(
          await request('GET', '/api/v1/batch-serial/batches/expiry-dashboard'),
        ),
      );

  Future<PagedResult<LotRecord>> lots({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    LotQuery filters = const LotQuery(),
  }) =>
      _list(
        '/api/v1/batch-serial/lots',
        LotRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: filters.toQueryParams(),
      );

  Future<LotRecord> lotRecord(String id) async => LotRecord.fromJson(
        _unwrapMap(await request('GET', '/api/v1/batch-serial/lots/$id')),
      );

  Future<LotRecord> createLot(Json data) async => LotRecord.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/batch-serial/lots', body: data)),
      );

  /// [expectedVersion] is the `version` of the record the user opened,
  /// sent as `If-Match`. Omitting it saves with no precondition, which is
  /// what an older backend and a record with no published version get.
  Future<LotRecord> updateLot(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      LotRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/batch-serial/lots/$id',
          body: data,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deleteLot(String id) =>
      request('DELETE', '/api/v1/batch-serial/lots/$id');

  Future<PagedResult<SerialRecord>> serials({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    SerialQuery filters = const SerialQuery(),
  }) =>
      _list(
        '/api/v1/batch-serial/serials',
        SerialRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: filters.toQueryParams(),
      );

  Future<SerialRecord> serialRecord(String id) async => SerialRecord.fromJson(
        _unwrapMap(await request('GET', '/api/v1/batch-serial/serials/$id')),
      );

  Future<SerialRecord> createSerial(Json data) async => SerialRecord.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/batch-serial/serials', body: data)),
      );

  /// [expectedVersion] is the `version` of the record the user opened,
  /// sent as `If-Match`. Omitting it saves with no precondition, which is
  /// what an older backend and a record with no published version get.
  Future<SerialRecord> updateSerial(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      SerialRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/batch-serial/serials/$id',
          body: data,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deleteSerial(String id) =>
      request('DELETE', '/api/v1/batch-serial/serials/$id');

  // ── UOM & Packaging ────────────────────────────────────────────────────────

  Future<List<UomRecord>> uoms({bool includeInactive = false}) async {
    final Json response = await request(
      'GET',
      '/api/v1/uom-framework/uoms',
      query: {if (includeInactive) 'include_inactive': 'true'},
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => UomRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<UomRecord> createUom(Json data) async => UomRecord.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/uom-framework/uoms', body: data)),
      );

  /// [expectedVersion] is the `version` of the record the user opened,
  /// sent as `If-Match`. Omitting it saves with no precondition, which is
  /// what an older backend and a record with no published version get.
  Future<UomRecord> updateUom(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      UomRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/uom-framework/uoms/$id',
          body: data,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deleteUom(String id) =>
      request('DELETE', '/api/v1/uom-framework/uoms/$id');

  Future<List<UomGroupRecord>> uomGroups() async {
    final Json response =
        await request('GET', '/api/v1/uom-framework/uom-groups');
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => UomGroupRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<UomGroupRecord> createUomGroup(Json data) async =>
      UomGroupRecord.fromJson(
        _unwrapMap(await request('POST', '/api/v1/uom-framework/uom-groups',
            body: data)),
      );

  /// [expectedVersion] is the `version` of the record the user opened,
  /// sent as `If-Match`. Omitting it saves with no precondition, which is
  /// what an older backend and a record with no published version get.
  Future<UomGroupRecord> updateUomGroup(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      UomGroupRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/uom-framework/uom-groups/$id',
          body: data,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deleteUomGroup(String id) =>
      request('DELETE', '/api/v1/uom-framework/uom-groups/$id');

  /// The default units the active firm's own business profile carries.
  ///
  /// Keyed off the firm context rather than a profile id, because every route
  /// that reveals a profile id is platform-admin only. Returns null when the
  /// firm's profile has no defaults, or when the caller may not read units.
  Future<BusinessProfileUomDefaults?> firmUomDefaults() async {
    final Json response =
        await request('GET', '/api/v1/uom-framework/profile-defaults');
    final dynamic data = response['data'];
    if (data is! Map) return null;
    return BusinessProfileUomDefaults.fromJson(Map<String, dynamic>.from(data));
  }

  /// The default units a business profile carries, for the active firm.
  ///
  /// Returns null when neither the firm nor the profile has any defaults set.
  /// A returned record with a null `firmId` is the profile-wide default the
  /// firm inherits rather than one it has chosen.
  Future<BusinessProfileUomDefaults?> businessProfileUomDefaults(
      String profileId) async {
    final Json response = await request(
      'GET',
      '/api/v1/uom-framework/profiles/$profileId/defaults',
    );
    final dynamic data = response['data'];
    if (data is! Map) return null;
    return BusinessProfileUomDefaults.fromJson(Map<String, dynamic>.from(data));
  }

  /// Store default units for a business profile.
  ///
  /// [forEveryFirm] writes the row every firm on the profile inherits, which
  /// needs platform settings permission. The default writes only the active
  /// firm's own override.
  Future<BusinessProfileUomDefaults> updateBusinessProfileUomDefaults(
    String profileId,
    Json data, {
    bool forEveryFirm = false,
  }) async =>
      BusinessProfileUomDefaults.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/uom-framework/profiles/$profileId/defaults',
          query: {'apply_to': forEveryFirm ? 'PROFILE' : 'FIRM'},
          body: data,
        )),
      );

  Future<List<PackagingTypeRecord>> packagingTypes() async {
    final Json response =
        await request('GET', '/api/v1/uom-framework/packaging-types');
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) =>
            PackagingTypeRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<PackagingTypeRecord> createPackagingType(Json data) async =>
      PackagingTypeRecord.fromJson(
        _unwrapMap(await request(
            'POST', '/api/v1/uom-framework/packaging-types',
            body: data)),
      );

  /// [expectedVersion] is the `version` of the record the user opened,
  /// sent as `If-Match`. Omitting it saves with no precondition, which is
  /// what an older backend and a record with no published version get.
  Future<PackagingTypeRecord> updatePackagingType(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      PackagingTypeRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/uom-framework/packaging-types/$id',
          body: data,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deletePackagingType(String id) =>
      request('DELETE', '/api/v1/uom-framework/packaging-types/$id');

  Future<List<PackagingLevelRecord>> packagingLevels(String productId) async {
    final Json response = await request(
      'GET',
      '/api/v1/uom-framework/products/$productId/packaging-levels',
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) =>
            PackagingLevelRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<PackagingLevelRecord> createPackagingLevel(
    String productId,
    Json data,
  ) async =>
      PackagingLevelRecord.fromJson(
        _unwrapMap(await request(
          'POST',
          '/api/v1/uom-framework/products/$productId/packaging-levels',
          body: data,
        )),
      );

  /// [expectedVersion] is the `version` of the record the user opened, sent as
  /// `If-Match` so a concurrent edit is refused rather than overwritten.
  Future<PackagingLevelRecord> updatePackagingLevel(
    String productId,
    String levelId,
    Json data, {
    int? expectedVersion,
  }) async =>
      PackagingLevelRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/uom-framework/products/$productId/packaging-levels/$levelId',
          body: data,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deletePackagingLevel(String productId, String levelId) => request(
        'DELETE',
        '/api/v1/uom-framework/products/$productId/packaging-levels/$levelId',
      );

  /// Resolve a scanned code to a product and the stock one scan means.
  Future<BarcodeLookup> lookupBarcode(String code) async =>
      BarcodeLookup.fromJson(_unwrapMap(await request(
        'GET',
        '/api/v1/uom-framework/barcode-lookup'
            '?code=${Uri.encodeQueryComponent(code)}',
      )));

  Future<PagedResult<ConversionRuleRecord>> conversionRules({
    int page = 1,
    int pageSize = 20,
    String productId = '',
  }) =>
      _list(
        '/api/v1/uom-framework/conversion-rules',
        ConversionRuleRecord.fromJson,
        page,
        '',
        pageSize: pageSize,
        additionalQuery: {
          if (productId.isNotEmpty) 'product_id': productId,
        },
      );

  Future<ConversionRuleRecord> createConversionRule(Json data) async =>
      ConversionRuleRecord.fromJson(
        _unwrapMap(await request(
            'POST', '/api/v1/uom-framework/conversion-rules',
            body: data)),
      );

  /// [expectedVersion] is the `version` of the record the user opened,
  /// sent as `If-Match`. Omitting it saves with no precondition, which is
  /// what an older backend and a record with no published version get.
  Future<ConversionRuleRecord> updateConversionRule(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      ConversionRuleRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/uom-framework/conversion-rules/$id',
          body: data,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deleteConversionRule(String id) =>
      request('DELETE', '/api/v1/uom-framework/conversion-rules/$id');

  Future<List<IndustryTemplateRecord>> industryTemplates(
      {bool includeInactive = false}) async {
    final Json response = await request(
      'GET',
      '/api/v1/uom-framework/industry-templates',
      query: {if (includeInactive) 'include_inactive': 'true'},
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) =>
            IndustryTemplateRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<IndustryTemplateRecord> createIndustryTemplate(Json data) async =>
      IndustryTemplateRecord.fromJson(
        _unwrapMap(await request(
          'POST',
          '/api/v1/uom-framework/industry-templates',
          body: data,
        )),
      );

  Future<IndustryTemplateRecord> updateIndustryTemplate(
          String id, Json data) async =>
      IndustryTemplateRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/uom-framework/industry-templates/$id',
          body: data,
        )),
      );

  Future<void> deleteIndustryTemplate(String id) =>
      request('DELETE', '/api/v1/uom-framework/industry-templates/$id');

  Future<InventorySummaryRecord> inventorySummary({
    bool includeDeleted = false,
  }) async =>
      InventorySummaryRecord.fromJson(
        _unwrapMap(
          await request(
            'GET',
            '/api/v1/inventory/summary',
            query: {if (includeDeleted) 'include_deleted': 'true'},
          ),
        ),
      );

  Future<List<InventoryLocationSummaryRecord>> inventoryByFirm() async {
    final Json response =
        await request('GET', '/api/v1/inventory/summary/by-firm');
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => InventoryLocationSummaryRecord.fromJson(
              Map<String, dynamic>.from(item),
            ))
        .toList();
  }

  Future<List<InventoryLocationSummaryRecord>> inventoryByBranch() async {
    final Json response =
        await request('GET', '/api/v1/inventory/summary/by-branch');
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => InventoryLocationSummaryRecord.fromJson(
              Map<String, dynamic>.from(item),
            ))
        .toList();
  }

  Future<List<InventoryLocationSummaryRecord>> inventoryByWarehouse() async {
    final Json response =
        await request('GET', '/api/v1/inventory/summary/by-warehouse');
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => InventoryLocationSummaryRecord.fromJson(
              Map<String, dynamic>.from(item),
            ))
        .toList();
  }

  Future<PagedResult<InventoryTransactionRecord>> inventoryTransactions({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    InventoryTransactionQuery filters = const InventoryTransactionQuery(),
  }) =>
      _list(
        '/api/v1/inventory/transactions',
        InventoryTransactionRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: filters.toQuery(),
      );

  Future<PagedResult<InventoryTransactionRecord>> stockLedger({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    InventoryTransactionQuery filters = const InventoryTransactionQuery(),
  }) =>
      _list(
        '/api/v1/inventory/ledger',
        InventoryTransactionRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: filters.toQuery(),
      );

  Future<PagedResult<OpeningStockBatchRecord>> openingStockBatches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    OpeningStockBatchQuery filters = const OpeningStockBatchQuery(),
  }) =>
      _list(
        '/api/v1/inventory/opening-stock',
        OpeningStockBatchRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: filters.toQuery(),
      );

  Future<OpeningStockBatchRecord> createOpeningStock(Json data) async =>
      OpeningStockBatchRecord.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/inventory/opening-stock', body: data),
        ),
      );

  Future<OpeningStockBatchRecord> updateOpeningStock(
          String id, Json data) async =>
      OpeningStockBatchRecord.fromJson(
        _unwrapMap(
          await request('PUT', '/api/v1/inventory/opening-stock/$id',
              body: data),
        ),
      );

  Future<OpeningStockBatchRecord> postOpeningStock(String id) async =>
      OpeningStockBatchRecord.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/inventory/opening-stock/$id/post')),
      );

  // Counting a warehouse. The sheet is drawn up from what the system holds,
  // walked over hours, and posted once at the end -- so it is a document with
  // a draft the client saves into, not a form that applies on submit.

  Future<PagedResult<PhysicalCountSheet>> physicalCounts({
    int page = 1,
    int pageSize = 20,
    String search = '',
  }) =>
      _list(
        '/api/v1/inventory/counts',
        PhysicalCountSheet.fromJson,
        page,
        search,
        pageSize: pageSize,
      );

  Future<PhysicalCountSheet> physicalCount(String id) async =>
      PhysicalCountSheet.fromJson(
        _unwrapMap(await request('GET', '/api/v1/inventory/counts/$id')),
      );

  /// Open a sheet. Naming no lines draws it up from the whole warehouse.
  Future<PhysicalCountSheet> openPhysicalCount(Json data) async =>
      PhysicalCountSheet.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/inventory/counts', body: data)),
      );

  /// Save what has been counted so far, on a sheet nobody has posted.
  Future<PhysicalCountSheet> recordPhysicalCount(String id, Json data) async =>
      PhysicalCountSheet.fromJson(
        _unwrapMap(
          await request('PUT', '/api/v1/inventory/counts/$id', body: data),
        ),
      );

  /// Turn every difference into a stock adjustment, which reaches the ledger.
  Future<PhysicalCountSheet> postPhysicalCount(String id) async =>
      PhysicalCountSheet.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/inventory/counts/$id/post'),
        ),
      );

  Future<PhysicalCountSheet> cancelPhysicalCount(String id) async =>
      PhysicalCountSheet.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/inventory/counts/$id/cancel'),
        ),
      );

  /// The rows of one report.
  ///
  /// Every report endpoint answers with flat rows in the standard envelope, so
  /// one method serves all of them and the difference between reports is a
  /// path. Six of them answered differently until that was corrected; a client
  /// method per report would have hidden that rather than surfaced it.
  Future<List<Json>> reportRows(String path) async {
    final Json response = await request('GET', path);
    final dynamic data = response['data'];
    return [
      for (final dynamic row in data is List ? data : const [])
        if (row is Map) Map<String, dynamic>.from(row),
    ];
  }

  /// Move stock between warehouses. Returns both movements, out and in.
  ///
  /// Nothing posts: the firm owns the same goods at the same value afterwards.
  Future<List<InventoryTransactionRecord>> transferStock(Json data) async {
    final Json response =
        await request('POST', '/api/v1/inventory/transfers', body: data);
    return _unwrapList(response, InventoryTransactionRecord.fromJson);
  }

  /// Take stock off the books under a reason, which reaches the ledger.
  Future<InventoryTransactionRecord> writeOffStock(Json data) async =>
      InventoryTransactionRecord.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/inventory/write-offs', body: data)),
      );

  /// Hold stock back from sale, or release it. Nothing posts.
  Future<InventoryTransactionRecord> quarantineStock(Json data) async =>
      InventoryTransactionRecord.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/inventory/quarantine', body: data)),
      );

  Future<InventoryTransactionRecord> createInventoryAdjustment(
          Json data) async =>
      InventoryTransactionRecord.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/inventory/adjustments', body: data)),
      );

  Future<String> exportInventory({
    String search = '',
    String dataset = 'inventory',
    String format = 'csv',
  }) =>
      downloadText(
        '/api/v1/inventory/export',
        query: {
          if (search.isNotEmpty) 'search': search,
          if (dataset.isNotEmpty) 'dataset': dataset,
          if (format.isNotEmpty) 'format': format,
        },
      );

  Future<List<int>> exportInventoryBytes({
    String search = '',
    String dataset = 'inventory',
    String format = 'xlsx',
  }) =>
      downloadBytes(
        '/api/v1/inventory/export',
        query: {
          if (search.isNotEmpty) 'search': search,
          if (dataset.isNotEmpty) 'dataset': dataset,
          if (format.isNotEmpty) 'format': format,
        },
      );

  Future<ProductMetadataRecord> productMetadata({String? categoryId}) async =>
      ProductMetadataRecord.fromJson(_unwrapMap(
        await request(
          'GET',
          '/api/v1/products/metadata',
          query: {
            if (categoryId != null && categoryId.isNotEmpty)
              'category_id': categoryId,
          },
        ),
      ));

  Future<List<ProductCategoryRecord>> productCategories() async {
    final Json response = await request('GET', '/api/v1/products/categories');
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) =>
            ProductCategoryRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<Product> createProduct(Json data) async => Product.fromJson(_unwrapMap(
        await request('POST', '/api/v1/products', body: data),
      ));

  Future<Product> updateProduct(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      Product.fromJson(_unwrapMap(
        await request(
          'PUT',
          '/api/v1/products/$id',
          body: data,
          expectedVersion: expectedVersion,
        ),
      ));

  Future<void> deleteProduct(String id) =>
      request('DELETE', '/api/v1/products/$id');

  Future<Product> restoreProduct(String id) async =>
      Product.fromJson(_unwrapMap(
        await request('POST', '/api/v1/products/$id/restore'),
      ));

  Future<Product> duplicateProduct(String id) async =>
      Product.fromJson(_unwrapMap(
        await request('POST', '/api/v1/products/$id/duplicate'),
      ));

  Future<int> bulkDeleteProducts(List<String> ids) async {
    final Json response = await request(
      'POST',
      '/api/v1/products/bulk-delete',
      body: {'ids': ids},
    );
    final Json data = _unwrapMap(response);
    return (data['affected'] as num?)?.toInt() ?? 0;
  }

  Future<int> bulkRestoreProducts(List<String> ids) async {
    final Json response = await request(
      'POST',
      '/api/v1/products/bulk-restore',
      body: {'ids': ids},
    );
    final Json data = _unwrapMap(response);
    return (data['affected'] as num?)?.toInt() ?? 0;
  }

  Future<String> exportProducts({
    String search = '',
    String format = 'csv',
  }) =>
      downloadText(
        '/api/v1/products/export',
        query: {
          if (search.isNotEmpty) 'search': search,
          if (format.isNotEmpty) 'format': format,
        },
      );

  Future<TerritoryHierarchyRecord> territoryHierarchy() async =>
      TerritoryHierarchyRecord.fromJson(_unwrapMap(
        await request('GET', '/api/v1/sales-territories/hierarchy-levels'),
      ));

  Future<PagedResult<SalesTerritory>> territories({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    TerritoryQuery filters = const TerritoryQuery(),
  }) =>
      _list(
        '/api/v1/sales-territories',
        SalesTerritory.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: filters.toQuery(),
      );

  Future<List<TerritoryTreeNodeRecord>> territoryTree({
    bool includeDeleted = false,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/sales-territories/tree',
      query: {if (includeDeleted) 'include_deleted': 'true'},
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => TerritoryTreeNodeRecord.fromJson(
              Map<String, dynamic>.from(item),
            ))
        .toList();
  }

  Future<Json> territoryDashboard() async =>
      _unwrapMap(await request('GET', '/api/v1/sales-territories/dashboard'));

  Future<List<SalesTerritory>> searchTerritories(
    String query, {
    int limit = 100,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/sales-territories/search',
      query: {'q': query, 'limit': '$limit'},
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => SalesTerritory.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<SalesTerritory> copyTerritory(String id, Json body) async =>
      SalesTerritory.fromJson(_unwrapMap(
        await request('POST', '/api/v1/sales-territories/$id/copy', body: body),
      ));

  Future<SalesTerritory> createTerritory(Json data) async =>
      SalesTerritory.fromJson(_unwrapMap(
        await request('POST', '/api/v1/sales-territories', body: data),
      ));

  /// [expectedVersion] is the `version` of the record the user opened,
  /// sent as `If-Match`. Omitting it saves with no precondition, which is
  /// what an older backend and a record with no published version get.
  Future<SalesTerritory> updateTerritory(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      SalesTerritory.fromJson(_unwrapMap(
        await request(
          'PUT',
          '/api/v1/sales-territories/$id',
          body: data,
          expectedVersion: expectedVersion,
        ),
      ));

  /// The kinds of round this firm runs — a sales beat, a collection round.
  Future<List<TerritoryRouteTypeRecord>> territoryRouteTypes() async {
    final Json response =
        await request('GET', '/api/v1/sales-territories/route-types');
    final dynamic data = response['data'];
    if (data is! List) return const <TerritoryRouteTypeRecord>[];
    return <TerritoryRouteTypeRecord>[
      for (final dynamic row in data)
        if (row is Map)
          TerritoryRouteTypeRecord.fromJson(Map<String, dynamic>.from(row)),
    ];
  }

  Future<void> deleteTerritory(String id) =>
      request('DELETE', '/api/v1/sales-territories/$id');

  Future<SalesTerritory> restoreTerritory(String id) async =>
      SalesTerritory.fromJson(_unwrapMap(
        await request('POST', '/api/v1/sales-territories/$id/restore'),
      ));

  /// The customers on a round, in the order it calls them.
  ///
  /// Returns the whole assignment rather than a list of ids: `visit_sequence`
  /// is the call order and was writable long before anything could read it
  /// back, so no screen could show the sequence it was saving.
  Future<List<TerritoryCustomerAssignmentRecord>> territoryCustomers(
    String territoryId,
  ) async {
    final Json response = await request(
        'GET', '/api/v1/sales-territories/$territoryId/customers');
    return _assignments(response['data']);
  }

  /// Replace the customers on a round, in call order.
  ///
  /// [includePotential] is opt-in: only a screen that actually offers the
  /// potential toggle should send the flag, because the server treats it as
  /// absent-means-unchanged and a screen that cannot set it must not clear it.
  Future<List<TerritoryCustomerAssignmentRecord>> setTerritoryCustomers(
    String territoryId,
    List<TerritoryCustomerAssignmentRecord> assignments, {
    bool includePotential = false,
  }) async {
    final Json response = await request(
      'PUT',
      '/api/v1/sales-territories/$territoryId/customers',
      body: {
        'entries': [
          for (final row in assignments)
            row.toJson(includePotential: includePotential),
        ],
      },
    );
    return _assignments(response['data']);
  }

  List<TerritoryCustomerAssignmentRecord> _assignments(dynamic data) {
    if (data is! List) return const <TerritoryCustomerAssignmentRecord>[];
    return <TerritoryCustomerAssignmentRecord>[
      for (final dynamic row in data)
        if (row is Map)
          TerritoryCustomerAssignmentRecord.fromJson(
              Map<String, dynamic>.from(row)),
    ];
  }

  // Route types are written through the generic `create`/`update`/`delete`
  // helpers, which build `/api/v1/sales-territories/route-types[/{id}]` from
  // the `resource` on their `ResourceDefinition`. Named methods here would be
  // a second spelling of the same three paths with nothing calling them.

  Future<PagedResult<BeatPlanRecord>> beatPlans({
    int page = 1,
    int pageSize = 20,
    String search = '',
    bool includeDeleted = false,
  }) =>
      _list(
        '/api/v1/sales-territories/beat-plans',
        BeatPlanRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        additionalQuery:
            includeDeleted ? {'include_deleted': 'true'} : const {},
      );

  Future<BeatPlanRecord> beatPlan(String id) async =>
      BeatPlanRecord.fromJson(_unwrapMap(
        await request('GET', '/api/v1/sales-territories/beat-plans/$id'),
      ));

  Future<BeatPlanRecord> createBeatPlan(Json data) async =>
      BeatPlanRecord.fromJson(_unwrapMap(
        await request('POST', '/api/v1/sales-territories/beat-plans',
            body: data),
      ));

  /// Who should be called on [date] (`yyyy-MM-dd`), across every active plan.
  ///
  /// Computed by the server from the recurrence rule and the assignments, so
  /// it is always current — there are no stored occurrences to go stale.
  Future<CallListRecord> callLists({
    required String date,
    String salesmanId = '',
  }) async =>
      CallListRecord.fromJson(_unwrapMap(
        await request(
          'GET',
          '/api/v1/sales-territories/call-lists',
          query: {
            'date': date,
            if (salesmanId.isNotEmpty) 'salesman_id': salesmanId,
          },
        ),
      ));

  /// The same answer for one plan, used by the preview on the plan editor.
  Future<CallListRecord> beatPlanCallList(String id, String date) async =>
      CallListRecord.fromJson(_unwrapMap(
        await request(
          'GET',
          '/api/v1/sales-territories/beat-plans/$id/call-list',
          query: {'date': date},
        ),
      ));

  /// [expectedVersion] is the `version` of the record the user opened,
  /// sent as `If-Match`. Omitting it saves with no precondition, which is
  /// what an older backend and a record with no published version get.
  Future<BeatPlanRecord> updateBeatPlan(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      BeatPlanRecord.fromJson(_unwrapMap(
        await request(
          'PUT',
          '/api/v1/sales-territories/beat-plans/$id',
          body: data,
          expectedVersion: expectedVersion,
        ),
      ));

  Future<void> deleteBeatPlan(String id) async =>
      request('DELETE', '/api/v1/sales-territories/beat-plans/$id');

  /// The people this firm can put on a route.
  ///
  /// Not `/api/v1/users`: that endpoint is guarded by `USER_VIEW`, a
  /// platform-admin permission, so the roles that actually run territories get
  /// a 403 from it. This one is scoped to the firm and guarded by the assign
  /// permission.
  Future<List<TerritorySalesmanCandidate>> territorySalesmanCandidates() async {
    final Json response =
        await request('GET', '/api/v1/sales-territories/salesman-candidates');
    final dynamic data = response['data'];
    if (data is! List) return const <TerritorySalesmanCandidate>[];
    return <TerritorySalesmanCandidate>[
      for (final dynamic row in data)
        if (row is Map)
          TerritorySalesmanCandidate.fromJson(Map<String, dynamic>.from(row)),
    ];
  }

  Future<List<Json>> territorySalesmen(String territoryId) async {
    final Json response =
        await request('GET', '/api/v1/sales-territories/$territoryId/salesmen');
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  Future<List<Json>> setTerritorySalesmen(
    String territoryId,
    List<Json> assignments,
  ) async {
    final Json response = await request(
      'PUT',
      '/api/v1/sales-territories/$territoryId/salesmen',
      body: {'assignments': assignments},
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  /// Outlets a round could call, narrowed by pin code, street or town.
  ///
  /// Lives on the territory router rather than under customers because it
  /// answers a territory question — who is already on a round — and the
  /// customer module knows nothing about assignments.
  Future<PagedResult<AssignableCustomerRecord>> assignableCustomers({
    int page = 1,
    int pageSize = 50,
    String territoryId = '',
    String search = '',
    String postalCode = '',
    String area = '',
    String city = '',
    bool unassignedOnly = false,
  }) =>
      _list(
        '/api/v1/sales-territories/assignable-customers',
        AssignableCustomerRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        additionalQuery: {
          if (territoryId.isNotEmpty) 'territory_id': territoryId,
          if (postalCode.isNotEmpty) 'postal_code': postalCode,
          if (area.isNotEmpty) 'area': area,
          if (city.isNotEmpty) 'city': city,
          if (unassignedOnly) 'unassigned_only': 'true',
        },
      );

  /// Import a territory hierarchy from CSV.
  ///
  /// The whole file is one transaction server-side, so a row refused anywhere
  /// leaves the firm exactly as it was — which is what lets the dialog say
  /// nothing was written and be telling the truth.
  Future<List<SalesTerritory>> importTerritories({
    required String fileName,
    required List<int> bytes,
  }) async {
    final Json response = await multipartRequest(
      'POST',
      '/api/v1/sales-territories/import',
      fields: {'format': 'csv'},
      fileField: 'file',
      fileName: fileName,
      fileBytes: bytes,
      fileContentType: 'text/csv',
    );
    final dynamic data = response['data'];
    if (data is! List) return const <SalesTerritory>[];
    return data
        .whereType<Map>()
        .map((item) => SalesTerritory.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  /// How much ground each salesperson covers.
  Future<List<TerritoryCoverageRecord>> territoryCoverage() async {
    final Json response = await request(
      'GET',
      '/api/v1/sales-territories/coverage/salesmen',
    );
    final dynamic data = response['data'];
    if (data is! List) return const <TerritoryCoverageRecord>[];
    return <TerritoryCoverageRecord>[
      for (final dynamic row in data)
        if (row is Map)
          TerritoryCoverageRecord.fromJson(Map<String, dynamic>.from(row)),
    ];
  }

  /// The rounds that call one shop, primary first.
  Future<List<CustomerRouteRecord>> customerRoutes(String customerId) async {
    final Json response = await request(
      'GET',
      '/api/v1/sales-territories/customers/$customerId/routes',
    );
    final dynamic data = response['data'];
    if (data is! List) return const <CustomerRouteRecord>[];
    return <CustomerRouteRecord>[
      for (final dynamic row in data)
        if (row is Map)
          CustomerRouteRecord.fromJson(Map<String, dynamic>.from(row)),
    ];
  }

  /// The shared geography masters: country > state > district > city >
  /// postal code > locality.
  ///
  /// Reference data rather than firm data — every firm reads the same rows —
  /// but it is served from the firm store, so these still carry `X-Firm-ID`
  /// like every other call here. Writes are platform-admin only.
  Future<List<GeoPlaceRecord>> geoPlaces(
    GeoLevel level, {
    String parentId = '',
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/sales-territories/geo/${level.path}',
      query: {
        if (parentId.isNotEmpty && level.parentQuery != null)
          level.parentQuery!: parentId,
      },
    );
    final dynamic data = response['data'];
    if (data is! List) return const <GeoPlaceRecord>[];
    return <GeoPlaceRecord>[
      for (final dynamic row in data)
        if (row is Map)
          GeoPlaceRecord.fromJson(level, Map<String, dynamic>.from(row)),
    ];
  }

  Future<GeoPlaceRecord> createGeoPlace(GeoLevel level, Json body) async {
    final Json response = await request(
      'POST',
      '/api/v1/sales-territories/geo/${level.path}',
      body: body,
    );
    return GeoPlaceRecord.fromJson(level, _unwrapMap(response));
  }

  /// [expectedVersion] is the `version` of the record the user opened,
  /// sent as `If-Match`. Omitting it saves with no precondition, which is
  /// what an older backend and a record with no published version get.
  Future<GeoPlaceRecord> updateGeoPlace(
    GeoLevel level,
    String id,
    Json body, {
    int? expectedVersion,
  }) async {
    final Json response = await request(
      'PUT',
      '/api/v1/sales-territories/geo/${level.path}/$id',
      body: body,
      expectedVersion: expectedVersion,
    );
    return GeoPlaceRecord.fromJson(level, _unwrapMap(response));
  }

  Future<void> deleteGeoPlace(GeoLevel level, String id) =>
      request('DELETE', '/api/v1/sales-territories/geo/${level.path}/$id');

  Future<int> bulkTerritoryStatus(Json body) async {
    final Json response = await request(
      'POST',
      '/api/v1/sales-territories/bulk/status',
      body: body,
    );
    final Json data = _unwrapMap(response);
    return (data['affected'] as num?)?.toInt() ?? 0;
  }

  Future<int> bulkTerritoryMove(Json body) async {
    final Json response = await request(
      'POST',
      '/api/v1/sales-territories/bulk/move',
      body: body,
    );
    final Json data = _unwrapMap(response);
    return (data['affected'] as num?)?.toInt() ?? 0;
  }

  /// Apply one customer list to several territories.
  ///
  /// The whole batch commits once server-side, so a run refused on its fifth
  /// territory leaves the first four unwritten — worth knowing, because it is
  /// what lets the dialog say "nothing was changed" and be telling the truth.
  Future<int> bulkTerritoryCustomers(List<Json> items) async {
    final Json response = await request(
      'POST',
      '/api/v1/sales-territories/bulk/customers',
      body: {'items': items},
    );
    final Json data = _unwrapMap(response);
    return (data['affected'] as num?)?.toInt() ?? 0;
  }

  Future<int> bulkTerritorySalesmen(List<Json> items) async {
    final Json response = await request(
      'POST',
      '/api/v1/sales-territories/bulk/salesmen',
      body: {'items': items},
    );
    final Json data = _unwrapMap(response);
    return (data['affected'] as num?)?.toInt() ?? 0;
  }

  Future<String> exportTerritories({
    String search = '',
    String format = 'csv',
    String dataset = 'hierarchy',
  }) =>
      downloadText(
        '/api/v1/sales-territories/export',
        query: {
          if (search.isNotEmpty) 'search': search,
          if (format.isNotEmpty) 'format': format,
          if (dataset.isNotEmpty) 'dataset': dataset,
        },
      );

  /// Load every option for an assignment selector, following pagination.
  ///
  /// The API caps page_size at 100. Fetching a single page silently truncated
  /// any catalogue larger than that: with 163 permissions, 63 of them could not
  /// be granted to a role because the selector never showed them.
  Future<List<AssignmentOption>> options(String resource) async {
    const int pageSize = 100;
    // A catalogue this large is already unusual; the ceiling stops a bad
    // total_records from looping forever.
    const int maxPages = 50;
    final List<AssignmentOption> collected = [];
    for (int page = 1; page <= maxPages; page++) {
      final PagedResult<AssignmentOption> result = await _list(
        '/api/v1/$resource',
        (json) => AssignmentOption(
          id: stringValue(json['id']),
          label: stringValue(json['code'] ?? json['name'] ?? json['email']),
          group:
              json['category'] == null ? null : stringValue(json['category']),
        ),
        page,
        '',
        pageSize: pageSize,
      );
      collected.addAll(result.items);
      if (result.items.length < pageSize || collected.length >= result.total) {
        break;
      }
    }
    return collected;
  }

  Future<PagedResult<PurchaseOrder>> purchases({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    PurchaseQuery filters = const PurchaseQuery(),
  }) =>
      _list(
        '/api/v1/purchases',
        PurchaseOrder.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: filters.toQuery(),
      );

  Future<PagedResult<GoodsReceiptRecord>> goodsReceipts({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> filters = const {},
  }) =>
      _list(
        '/api/v1/goods-receipts',
        GoodsReceiptRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: filters,
      );

  Future<GoodsReceiptRecord> goodsReceipt(String id) async =>
      GoodsReceiptRecord.fromJson(
        _unwrapMap(await request('GET', '/api/v1/goods-receipts/$id')),
      );

  Future<GoodsReceiptRecord> createGoodsReceipt(Json data) async =>
      GoodsReceiptRecord.fromJson(
        _unwrapMap(await request('POST', '/api/v1/goods-receipts', body: data)),
      );

  Future<GoodsReceiptRecord> updateGoodsReceipt(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      GoodsReceiptRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/goods-receipts/$id',
          body: data,
          expectedVersion: expectedVersion,
        )),
      );

  Future<GoodsReceiptRecord> completeGoodsReceipt(String id) async =>
      GoodsReceiptRecord.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/goods-receipts/$id/complete')),
      );

  Future<GoodsReceiptRecord> cancelGoodsReceipt(String id,
          {String reason = ''}) async =>
      GoodsReceiptRecord.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/goods-receipts/$id/cancel',
            body: {'reason': reason.isEmpty ? null : reason},
          ),
        ),
      );

  Future<GoodsReceiptRecord> closeGoodsReceipt(String id,
          {String reason = ''}) async =>
      GoodsReceiptRecord.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/goods-receipts/$id/close',
            body: {'reason': reason.isEmpty ? null : reason},
          ),
        ),
      );

  Future<Json> goodsReceiptSummary() async =>
      _unwrapMap(await request('GET', '/api/v1/goods-receipts/summary'));

  Future<List<DocumentTimelineSnapshot>> goodsReceiptHistory(String id) async {
    final Json response =
        await request('GET', '/api/v1/goods-receipts/$id/history');
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) =>
            DocumentTimelineSnapshot.fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false);
  }

  Future<PurchaseSummaryRecord> purchaseSummary() async =>
      PurchaseSummaryRecord.fromJson(
        _unwrapMap(await request('GET', '/api/v1/purchases/summary')),
      );

  Future<PurchaseOrder> purchaseOrder(
    String id, {
    bool includeDeleted = false,
  }) async =>
      PurchaseOrder.fromJson(
        _unwrapMap(
          await request(
            'GET',
            '/api/v1/purchases/$id',
            query: includeDeleted ? {'include_deleted': 'true'} : null,
          ),
        ),
      );

  Future<PurchaseOrder> createPurchaseOrder(PurchaseOrder order) async =>
      PurchaseOrder.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/purchases',
              body: order.toCreateJson()),
        ),
      );

  Future<PurchaseOrder> updatePurchaseOrder(PurchaseOrder order) async =>
      PurchaseOrder.fromJson(
        _unwrapMap(
          await request(
            'PUT',
            '/api/v1/purchases/${order.id}',
            body: order.toUpdateJson(),
          ),
        ),
      );

  Future<void> deletePurchaseOrder(String id) =>
      request('DELETE', '/api/v1/purchases/$id');

  Future<PurchaseOrder> restorePurchaseOrder(String id) async =>
      PurchaseOrder.fromJson(
        _unwrapMap(await request('POST', '/api/v1/purchases/$id/restore')),
      );

  /// Send a draft purchase order for approval.
  Future<PurchaseOrder> submitPurchaseOrder(String id) async =>
      PurchaseOrder.fromJson(_unwrapMap(
        await request('POST', '/api/v1/purchases/$id/submit'),
      ));

  /// Approve a submitted purchase order, committing the firm to buy.
  Future<PurchaseOrder> approvePurchaseOrder(String id) async =>
      PurchaseOrder.fromJson(_unwrapMap(
        await request('POST', '/api/v1/purchases/$id/approve'),
      ));

  Future<PurchaseOrder> cancelPurchaseOrder(String id,
          {String reason = ''}) async =>
      PurchaseOrder.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/purchases/$id/cancel',
            body: {'reason': reason.isEmpty ? null : reason},
          ),
        ),
      );

  Future<PurchaseOrder> closePurchaseOrder(String id,
          {String reason = ''}) async =>
      PurchaseOrder.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/purchases/$id/close',
            body: {'reason': reason.isEmpty ? null : reason},
          ),
        ),
      );

  Future<List<PurchaseOrderHistoryRecord>> purchaseOrderHistory(
      String id) async {
    final Json response = await request('GET', '/api/v1/purchases/$id/history');
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map(
          (item) => PurchaseOrderHistoryRecord.fromJson(
            Map<String, dynamic>.from(item),
          ),
        )
        .toList();
  }

  Future<List<PurchaseOrder>> importPurchaseOrdersJson(
    List<Json> records,
  ) async {
    final Json response = await multipartRequest(
      'POST',
      '/api/v1/purchases/import',
      fields: {
        'format': 'json',
        'payload': jsonEncode({'records': records}),
      },
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => PurchaseOrder.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<List<PurchaseOrder>> importPurchaseOrdersFile({
    required String format,
    required String fileName,
    required List<int> bytes,
  }) async {
    final Json response = await multipartRequest(
      'POST',
      '/api/v1/purchases/import',
      fields: {'format': format},
      fileField: 'file',
      fileName: fileName,
      fileBytes: bytes,
      fileContentType: format == 'xlsx'
          ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          : 'text/csv',
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => PurchaseOrder.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  // Financial years and their periods. Every posting lands in a period, so a
  // firm with none open cannot book anything -- which had no screen behind it.

  Future<List<FinancialYear>> financialYears() async => _unwrapList(
        await request('GET', '/api/v1/finance/financial-years'),
        FinancialYear.fromJson,
      );

  /// Open or close one period.
  Future<AccountingPeriod> setPeriodStatus(String id, String status) async =>
      AccountingPeriod.fromJson(
        _unwrapMap(
          await request(
            'PATCH',
            '/api/v1/finance/accounting-periods/$id',
            body: {'status': status},
          ),
        ),
      );

  // Document numbering. The rule behind every document number in the system.

  Future<List<NumberingRule>> numberingRules() async => _unwrapList(
        await request('GET', '/api/v1/document-framework/numbering-rules'),
        NumberingRule.fromJson,
      );

  /// What the next number would look like, without consuming it.
  Future<String> previewNumber(String ruleId) async {
    final Json response = await request(
      'GET',
      '/api/v1/document-framework/numbering-rules/$ruleId/preview',
    );
    return stringValue(response['data']);
  }

  // A price offered before anything is sold. The quotation commits nothing,
  // so there is no posting or reservation behind any of these calls -- the
  // only one that changes the world is `convertQuotation`, which creates the
  // order.

  Future<PagedResult<Quotation>> quotations({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? status,
  }) =>
      _list(
        '/api/v1/quotations',
        Quotation.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: 'quotation_date',
        additionalQuery: {if (status != null) 'status': status},
      );

  Future<Quotation> quotation(String id) async => Quotation.fromJson(
        _unwrapMap(await request('GET', '/api/v1/quotations/$id')),
      );

  Future<Quotation> createQuotation(Json data) async => Quotation.fromJson(
        _unwrapMap(await request('POST', '/api/v1/quotations', body: data)),
      );

  /// Replace one quotation.
  ///
  /// The update replaces the whole line collection and the editor writes as
  /// many lines as the offer needs, so a lost race costs every line somebody
  /// typed rather than a single field.
  Future<Quotation> updateQuotation(
    String id,
    Json data, {
    int? expectedVersion,
  }) async =>
      Quotation.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/quotations/$id',
          body: data,
          expectedVersion: expectedVersion,
        )),
      );

  /// Run a lifecycle action: send, accept, decline or cancel.
  Future<Quotation> quotationAction(
    String id,
    String action, {
    String? reason,
  }) async =>
      Quotation.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/quotations/$id/$action',
            body:
                reason == null ? const <String, dynamic>{} : {'reason': reason},
          ),
        ),
      );

  /// Turn an accepted quotation into a sales order.
  ///
  /// Answers with both documents, so the caller can name the order it created
  /// without a second round trip to find it.
  Future<QuotationConversion> convertQuotation(String id, {Json? data}) async =>
      QuotationConversion.fromJson(
        await request(
          'POST',
          '/api/v1/quotations/$id/convert',
          body: data ?? const <String, dynamic>{},
        ),
      );

  // Goods coming back from a customer. The document is its own resource
  // rather than a generic one because completing it moves three books at once
  // -- stock, the customer's account and the ledger -- and the screen has to
  // say which of them have moved.

  Future<PagedResult<SalesReturn>> salesReturns({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? status,
  }) =>
      _list(
        '/api/v1/sales-returns',
        SalesReturn.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: 'return_date',
        additionalQuery: {if (status != null) 'status': status},
      );

  Future<SalesReturn> salesReturn(String id) async => SalesReturn.fromJson(
        _unwrapMap(await request('GET', '/api/v1/sales-returns/$id')),
      );

  Future<SalesReturn> createSalesReturn(Json data) async =>
      SalesReturn.fromJson(
        _unwrapMap(await request('POST', '/api/v1/sales-returns', body: data)),
      );

  /// Run a lifecycle action: approve, complete, cancel or close.
  ///
  /// `cancel` and `close` carry a reason; the other two take no body, and the
  /// server ignores one either way.
  Future<SalesReturn> salesReturnAction(
    String id,
    String action, {
    String? reason,
  }) async =>
      SalesReturn.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/sales-returns/$id/$action',
            body:
                reason == null ? const <String, dynamic>{} : {'reason': reason},
          ),
        ),
      );

  /// The documents a return can be raised against.
  ///
  /// Delivery notes and sales invoices are read together and flattened, so the
  /// editor offers one list rather than making somebody decide which kind of
  /// paperwork they are holding before they can find it. A failure on either
  /// side yields that side's documents only -- half a picker still lets a
  /// return be raised.
  Future<List<ReturnableDocument>> returnableDocuments({int limit = 50}) async {
    final List<List<ReturnableDocument>> both = await Future.wait([
      _returnable(
          '/api/v1/delivery-notes', ReturnableDocument.fromDeliveryNote, limit),
      _returnable(
          '/api/v1/sales-invoices', ReturnableDocument.fromSalesInvoice, limit),
    ]);
    return [...both[0], ...both[1]];
  }

  Future<List<ReturnableDocument>> _returnable(
    String path,
    ReturnableDocument Function(Json) parser,
    int limit,
  ) async {
    try {
      final Json response = await request('GET', path, query: {
        'page': '1',
        'page_size': '$limit',
        'sort_by': 'created_at',
        'sort_direction': 'desc',
      });
      final dynamic data = response['data'];
      return [
        for (final dynamic row in data is List ? data : const [])
          if (row is Map) parser(Map<String, dynamic>.from(row)),
      ];
    } on ApiException {
      return const [];
    }
  }

  // ── Transactional documents ────────────────────────────────────────────
  // The five document workspaces share one shape, so they share these four
  // methods rather than each page spelling out its own paths. `resource` is
  // the collection segment: 'purchase-returns', 'delivery-notes', and so on.

  Future<Json> documentSummary(String resource, {String path = 'summary'}) =>
      request('GET', '/api/v1/$resource/$path');

  Future<Json> documentPage(
    String resource, {
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> additionalQuery = const {},
  }) =>
      request('GET', '/api/v1/$resource', query: {
        'page': '$page',
        'page_size': '$pageSize',
        'search': search,
        'sort_by': sortBy,
        'sort_direction': descending ? 'desc' : 'asc',
        ...additionalQuery,
      });

  Future<Json> documentHistory(String resource, String id) =>
      request('GET', '/api/v1/$resource/$id/history');

  /// Runs a lifecycle action such as approve, cancel or post.
  ///
  /// `action` may be given with or without a leading slash.
  Future<Json> documentAction(String resource, String id, String action) =>
      request(
        'POST',
        '/api/v1/$resource/$id/${action.startsWith('/') ? action.substring(1) : action}',
      );

  Future<Json> create(String resource, Json body) =>
      request('POST', '/api/v1/$resource', body: body);
  /// [expectedVersion] rides along as `If-Match` for the resources that
  /// publish a version -- route types among them, which are written through
  /// this generic helper rather than a named method.
  Future<Json> update(
    String resource,
    String id,
    Json body, {
    bool partial = false,
    int? expectedVersion,
  }) =>
      request(
        partial ? 'PATCH' : 'PUT',
        '/api/v1/$resource/$id',
        body: body,
        expectedVersion: expectedVersion,
      );
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

  Future<Map<String, dynamic>> businessProfileConfigurationValues(
    String profileId,
  ) async {
    final Json response = await request(
      'GET',
      '/api/v1/business-framework/profiles/$profileId/configuration',
    );
    final Json data = _unwrapMap(response);
    return {
      'feature_ids': stringList(data['feature_ids']).join(','),
      'module_ids': stringList(data['module_ids']).join(','),
    };
  }

  Future<void> setBusinessProfileFeatures(String profileId, List<String> ids) =>
      request(
        'PUT',
        '/api/v1/business-framework/profiles/$profileId/features',
        body: {'ids': ids},
      );

  Future<void> setBusinessProfileModules(String profileId, List<String> ids) =>
      request(
        'PUT',
        '/api/v1/business-framework/profiles/$profileId/modules',
        body: {'ids': ids},
      );

  /// Every firm with the business profile it is assigned.
  ///
  /// One call rather than one per row, and it does **not** take `X-Firm-ID`:
  /// assignments live in each firm's own store, so the server iterates them.
  /// Keyed by firm id for the grid to read.
  Future<Map<String, FirmProfileAssignment>> firmProfileAssignments() async {
    final Json response = await request(
        'GET', '/api/v1/business-framework/firm-profile-assignments');
    final dynamic data = response['data'];
    if (data is! List) return <String, FirmProfileAssignment>{};
    return <String, FirmProfileAssignment>{
      for (final dynamic row in data)
        if (row is Map)
          stringValue(Map<String, dynamic>.from(row)['firm_id']):
              FirmProfileAssignment.fromJson(Map<String, dynamic>.from(row)),
    };
  }

  Future<Map<String, dynamic>> firmBusinessProfileAssignmentValues(
    String firmId,
  ) async {
    final Json response = await request(
      'GET',
      '/api/v1/business-framework/firms/$firmId/profile-assignment',
    );
    final dynamic data = response['data'];
    if (data is! Map<String, dynamic>) {
      return {'business_profile_id': '', 'is_active': true, 'notes': ''};
    }
    return {
      'business_profile_id': stringValue(data['business_profile_id']),
      'is_active': boolValue(data['is_active'], fallback: true),
      'notes': stringValue(data['notes']),
    };
  }

  Future<void> assignBusinessProfileToFirm(
    String firmId,
    String businessProfileId, {
    bool isActive = true,
    String notes = '',
  }) =>
      request(
        'PUT',
        '/api/v1/business-framework/firms/$firmId/profile-assignment',
        body: {
          'business_profile_id': businessProfileId,
          'is_active': isActive,
          if (notes.isNotEmpty) 'notes': notes,
        },
      );

  Future<List<String>> activeBusinessModuleCodes() async {
    final Json response = await request(
      'GET',
      '/api/v1/business-framework/active-modules',
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((value) => stringValue(value['code']).toUpperCase())
        .where((code) => code.isNotEmpty)
        .toList();
  }

  /// The feature codes the firm's business profile has switched on.
  ///
  /// Read the same way the active module list is: a failure leaves the caller
  /// with nothing, and every gate treats "nothing" as "show it".
  Future<List<String>> activeBusinessFeatureCodes() async {
    final Json response = await request(
      'GET',
      '/api/v1/business-framework/active-features',
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((value) => stringValue(value['code']).toUpperCase())
        .where((code) => code.isNotEmpty)
        .toList();
  }

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
    Map<String, String> additionalQuery = const {},
  }) async {
    final query = {
      'page': '$page',
      'page_size': '$pageSize',
      if (search.isNotEmpty) 'search': search,
      if (sortBy != null) 'sort_by': sortBy,
      if (sortBy != null) 'sort_direction': descending ? 'desc' : 'asc',
      ...additionalQuery,
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

  // ── Finance ────────────────────────────────────────────────────────────
  // The finance API has been live since `20260809_0042` and every goods
  // receipt, dispatch and invoice posts to it, so the ledger has been filling
  // up with entries no screen could show. These are what the accounting
  // workspace reads.
  //
  // The list endpoints return a plain list rather than a page, so they are
  // wrapped into a `PagedResult` here instead of pretending the server paginates.

  Future<PagedResult<LedgerAccount>> ledgerAccounts({
    String? accountGroupId,
    bool? isActive,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/finance/ledger-accounts',
      query: {
        if (accountGroupId != null) 'account_group_id': accountGroupId,
        if (isActive != null) 'is_active': '$isActive',
      },
    );
    final List<LedgerAccount> items =
        _unwrapList(response, LedgerAccount.fromJson);
    return PagedResult<LedgerAccount>(items: items, total: items.length);
  }

  Future<LedgerAccount> createLedgerAccount(Json data) async =>
      LedgerAccount.fromJson(
        _unwrapMap(await request('POST', '/api/v1/finance/ledger-accounts',
            body: data)),
      );

  Future<LedgerAccount> updateLedgerAccount(String id, Json data) async =>
      LedgerAccount.fromJson(
        _unwrapMap(
          await request('PATCH', '/api/v1/finance/ledger-accounts/$id',
              body: data),
        ),
      );

  Future<List<AccountGroup>> accountGroups() async => _unwrapList(
        await request('GET', '/api/v1/finance/account-groups'),
        AccountGroup.fromJson,
      );

  Future<List<AccountingPeriod>> accountingPeriods(
          {String? financialYearId}) async =>
      _unwrapList(
        await request(
          'GET',
          '/api/v1/finance/accounting-periods',
          query: {
            if (financialYearId != null) 'financial_year_id': financialYearId,
          },
        ),
        AccountingPeriod.fromJson,
      );

  /// The trial balance for one accounting period.
  ///
  /// Whether it balances is the server's answer, carried through rather than
  /// recomputed: two places deciding that is two places that can disagree.
  Future<TrialBalanceReport> trialBalance(String accountingPeriodId) async =>
      TrialBalanceReport.fromJson(
        await request(
          'GET',
          '/api/v1/finance/trial-balance',
          query: {'accounting_period_id': accountingPeriodId},
        ),
      );

  // Receipts and payments. Nothing in the product could record money
  // arriving until these existed: two years of seeded trading left Cash at
  // 0.00 while receivables grew, because invoices were the only document that
  // reached the ledger.

  Future<PagedResult<Settlement>> settlements({
    required SettlementDirection direction,
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? partyId,
  }) =>
      _list(
        '/api/v1/${direction.path}',
        Settlement.fromJson,
        page,
        search,
        pageSize: pageSize,
        additionalQuery: {
          if (partyId != null) direction.partyParameter: partyId,
        },
      );

  /// The party's invoices that still owe something.
  Future<List<OutstandingInvoice>> outstandingInvoices({
    required SettlementDirection direction,
    required String partyId,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/${direction.path}/outstanding',
      query: {direction.partyParameter: partyId},
    );
    return _unwrapList(response, OutstandingInvoice.fromJson);
  }

  /// Record money that has already moved, and post it to the ledger.
  Future<Settlement> recordSettlement({
    required SettlementDirection direction,
    required Json data,
  }) async =>
      Settlement.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/${direction.path}', body: data),
        ),
      );

  /// Take a settlement back. The original stays and a mirror journal cancels
  /// it, so nothing is edited or deleted.
  Future<Settlement> reverseSettlement({
    required SettlementDirection direction,
    required String id,
    String? reason,
  }) async =>
      Settlement.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/${direction.path}/$id/reverse',
            body: {if (reason != null && reason.isNotEmpty) 'reason': reason},
          ),
        ),
      );

  /// One page of the audit trail.
  ///
  /// Which trail depends on the firm header the client already sends: with a
  /// firm it is that firm's own, and there is no cross-firm view because there
  /// is no cross-firm table -- each store holds its own history.
  Future<PagedResult<AuditLogEntry>> auditLogs({
    int page = 1,
    int pageSize = 20,
    String? action,
    String? entityType,
    String? dateFrom,
    String? dateTo,
  }) =>
      _list(
        '/api/v1/audit-logs',
        AuditLogEntry.fromJson,
        page,
        '',
        pageSize: pageSize,
        additionalQuery: {
          if (action != null && action.isNotEmpty) 'action': action,
          if (entityType != null && entityType.isNotEmpty)
            'entity_type': entityType,
          if (dateFrom != null && dateFrom.isNotEmpty) 'date_from': dateFrom,
          if (dateTo != null && dateTo.isNotEmpty) 'date_to': dateTo,
        },
      );

  /// The balance sheet as at one period end.
  Future<BalanceSheetReport> balanceSheet(String accountingPeriodId) async =>
      BalanceSheetReport.fromJson(
        await request(
          'GET',
          '/api/v1/finance/balance-sheet',
          query: {'accounting_period_id': accountingPeriodId},
        ),
      );

  /// The profit and loss for one period, with the year it belongs to.
  Future<ProfitLossReport> profitAndLoss(String accountingPeriodId) async =>
      ProfitLossReport.fromJson(
        await request(
          'GET',
          '/api/v1/finance/profit-loss',
          query: {'accounting_period_id': accountingPeriodId},
        ),
      );

  /// One account's statement for one period.
  ///
  /// The running balance comes down with the lines. It starts from the opening
  /// balance and moves in whichever direction the account type increases in,
  /// so adding the column up here would be a second opinion about the ledger.
  Future<GeneralLedgerReport> generalLedger({
    required String ledgerAccountId,
    required String accountingPeriodId,
  }) async =>
      GeneralLedgerReport.fromJson(
        await request(
          'GET',
          '/api/v1/finance/general-ledger/$ledgerAccountId',
          query: {'accounting_period_id': accountingPeriodId},
        ),
      );

  Future<PagedResult<JournalEntry>> journalEntries({
    int page = 1,
    int pageSize = 20,
    String search = '',
    bool descending = true,
    String? accountingPeriodId,
    String? status,
  }) =>
      _list(
        '/api/v1/finance/journal-entries',
        JournalEntry.fromJson,
        page,
        search,
        pageSize: pageSize,
        descending: descending,
        additionalQuery: {
          if (accountingPeriodId != null)
            'accounting_period_id': accountingPeriodId,
          if (status != null) 'status': status,
        },
      );

  Future<JournalEntry> journalEntry(String id) async => JournalEntry.fromJson(
        _unwrapMap(await request('GET', '/api/v1/finance/journal-entries/$id')),
      );

  Future<JournalEntry> createJournalEntry(Json data) async =>
      JournalEntry.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/finance/journal-entries', body: data),
        ),
      );

  /// Post a draft to the general ledger. There is no unposting: a posted entry
  /// is reversed by another entry, which is what `reverseJournalEntry` raises.
  Future<JournalEntry> postJournalEntry(String id) async =>
      JournalEntry.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/finance/journal-entries/$id/post'),
        ),
      );

  Future<JournalEntry> reverseJournalEntry(String id, Json data) async =>
      JournalEntry.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/finance/journal-entries/$id/reverse',
            body: data,
          ),
        ),
      );

  Future<List<FinanceTypeRef>> journalTypes() async => _unwrapList(
        await request('GET', '/api/v1/finance/journal-types'),
        FinanceTypeRef.fromJson,
      );

  Future<List<FinanceTypeRef>> voucherTypes() async => _unwrapList(
        await request('GET', '/api/v1/finance/voucher-types'),
        FinanceTypeRef.fromJson,
      );

  /// Whether the backend answers at all.
  ///
  /// `/health` is deliberately cheap on the server -- it touches no database --
  /// so this says only that the process is up and reachable. Neither health
  /// call needs a token: they are what a client asks before it has one.
  Future<bool> backendReachable() async {
    try {
      await request('GET', '/health');
      return true;
    } on ApiException {
      return false;
    }
  }

  /// Whether the backend's database answers a trivial query.
  ///
  /// Separate from [backendReachable] because the two fail apart: a server
  /// whose database has gone gives a healthy `/health` and a 503 here, and
  /// showing one light for both would hide exactly the case worth seeing.
  Future<bool> databaseReachable() async {
    try {
      await request('GET', '/health/database');
      return true;
    } on ApiException {
      return false;
    }
  }

  /// Issue one API request.
  ///
  /// [expectedVersion] sends the optimistic-concurrency precondition. Pass the
  /// `version` of the record the user actually loaded and the server refuses
  /// the write if it has moved on, rather than letting this client overwrite
  /// somebody else's edit. Omitting it is accepted and means "no precondition",
  /// which is what every call did before 2026-08-15.
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async {
    final Uri uri = _uri(path, query);
    onRequest?.call();
    if (_developmentLogging) {
      stderr.writeln('API $method $uri');
    }

    try {
      final HttpClientRequest httpRequest =
          await _httpClient.openUrl(method, uri);
      httpRequest.followRedirects = false;
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
      if (expectedVersion != null) {
        // Quoted, which is what an entity tag is. `parse_if_match` on the
        // server tolerates a bare number too, but sending a well-formed tag
        // means anything else in the path — a proxy, a cache — reads it.
        httpRequest.headers
            .set(HttpHeaders.ifMatchHeader, '"$expectedVersion"');
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
          // Carried through the refresh-retry deliberately. Dropping it would
          // turn a protected write into an unprotected one at exactly the
          // moment the request is replayed, which is the last place anybody
          // would look for a lost edit.
          expectedVersion: expectedVersion,
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

  Future<String> downloadText(
    String path, {
    Map<String, String>? query,
    bool retrying = false,
  }) async {
    final Uri uri = _uri(path, query);
    onRequest?.call();
    try {
      final HttpClientRequest httpRequest =
          await _httpClient.openUrl('GET', uri);
      httpRequest.followRedirects = false;
      httpRequest.headers.set(HttpHeaders.acceptHeader, 'text/csv');
      final String? token = accessToken();
      if (token?.isNotEmpty == true) {
        httpRequest.headers.set(
          HttpHeaders.authorizationHeader,
          'Bearer $token',
        );
      }
      final String? firmId = activeFirmId?.call();
      if (firmId?.isNotEmpty == true) {
        httpRequest.headers.set('X-Firm-ID', firmId!);
      }
      final HttpClientResponse response =
          await httpRequest.close().timeout(const Duration(seconds: 30));
      final String text = await utf8.decoder.bind(response).join();
      if (response.statusCode == HttpStatus.unauthorized &&
          !retrying &&
          await refreshAccessToken()) {
        return downloadText(path, query: query, retrying: true);
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        String message = 'The export request failed.';
        try {
          final dynamic decoded = jsonDecode(text);
          if (decoded is Map<String, dynamic>) {
            final dynamic error = decoded['error'];
            message = stringValue(
              error is Map<String, dynamic>
                  ? error['message']
                  : decoded['message'] ?? decoded['detail'],
            );
          }
        } on FormatException {
          // Keep the safe public error when the server did not return JSON.
        }
        throw ApiException(
          message.isEmpty ? 'The export request failed.' : message,
          statusCode: response.statusCode,
        );
      }
      return text;
    } on TimeoutException {
      throw const ApiException('The server did not respond in time.');
    } on SocketException {
      throw const ApiException(
        'Unable to connect to the server. Check the API address.',
      );
    }
  }

  /// How this firm prints one kind of document.
  ///
  /// Answers with the platform defaults where the firm has saved nothing, so a
  /// new firm prints a correct document without configuring anything.
  Future<PrintTemplate> printTemplate(String documentType) async =>
      PrintTemplate.fromJson(
        _unwrapMap(
          await request(
            'GET',
            '/api/v1/document-framework/print-templates/$documentType',
          ),
        ),
      );

  /// Save this firm's print settings for one kind of document.
  Future<PrintTemplate> savePrintTemplate(
    String documentType,
    PrintTemplate template,
  ) async =>
      PrintTemplate.fromJson(
        _unwrapMap(
          await request(
            'PUT',
            '/api/v1/document-framework/print-templates/$documentType',
            body: template.toJson(),
          ),
        ),
      );

  /// The purchase order as the PDF a supplier is sent.
  Future<List<int>> purchaseOrderPdf(String id) =>
      downloadBytes('/api/v1/purchases/$id/print');

  /// The invoice as the PDF a customer is sent.
  ///
  /// Rendered by the backend, so the layout is right in one place and the same
  /// bytes are what an email will attach when that arrives.
  Future<List<int>> salesInvoicePdf(String id) =>
      downloadBytes('/api/v1/sales-invoices/$id/print');

  /// What is still waiting to be billed.
  ///
  /// Asked for rather than derived client-side: only the server knows how much
  /// of a delivery line earlier invoices already took, and a picker that
  /// guessed would offer documents the save then refuses.
  Future<List<BillableDocument>> billableDocuments({int limit = 50}) async {
    final Json response = await request(
      'GET',
      '/api/v1/sales-invoices/billable',
      query: {'limit': '$limit'},
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => BillableDocument.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<Json> createSalesInvoice(Json body) =>
      request('POST', '/api/v1/sales-invoices', body: body);

  Future<Json> salesInvoice(String id) =>
      request('GET', '/api/v1/sales-invoices/$id');

  /// [expectedVersion] rides along as `If-Match`. The update replaces the
  /// whole line collection, so a lost race costs every line somebody entered
  /// rather than a single field.
  Future<Json> updateSalesInvoice(
    String id,
    Json body, {
    int? expectedVersion,
  }) =>
      request(
        'PUT',
        '/api/v1/sales-invoices/$id',
        body: body,
        expectedVersion: expectedVersion,
      );

  Future<List<int>> downloadBytes(
    String path, {
    Map<String, String>? query,
    bool retrying = false,
  }) async {
    final Uri uri = _uri(path, query);
    onRequest?.call();
    try {
      final HttpClientRequest httpRequest =
          await _httpClient.openUrl('GET', uri);
      httpRequest.followRedirects = false;
      final String? token = accessToken();
      if (token?.isNotEmpty == true) {
        httpRequest.headers.set(
          HttpHeaders.authorizationHeader,
          'Bearer $token',
        );
      }
      final String? firmId = activeFirmId?.call();
      if (firmId?.isNotEmpty == true) {
        httpRequest.headers.set('X-Firm-ID', firmId!);
      }
      final HttpClientResponse response =
          await httpRequest.close().timeout(const Duration(seconds: 30));
      final List<int> bytes = await response.fold<List<int>>(
        <int>[],
        (buffer, chunk) => buffer..addAll(chunk),
      );
      if (response.statusCode == HttpStatus.unauthorized &&
          !retrying &&
          await refreshAccessToken()) {
        return downloadBytes(path, query: query, retrying: true);
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        String message = 'The download request failed.';
        try {
          final dynamic decoded = jsonDecode(utf8.decode(bytes));
          if (decoded is Map<String, dynamic>) {
            final dynamic error = decoded['error'];
            message = stringValue(
              error is Map<String, dynamic>
                  ? error['message']
                  : decoded['message'] ?? decoded['detail'],
            );
          }
        } on FormatException {
          // Keep the safe public error when the server did not return JSON.
        }
        throw ApiException(
          message.isEmpty ? 'The download request failed.' : message,
          statusCode: response.statusCode,
        );
      }
      return bytes;
    } on TimeoutException {
      throw const ApiException('The server did not respond in time.');
    } on SocketException {
      throw const ApiException(
        'Unable to connect to the server. Check the API address.',
      );
    }
  }

  Future<Json> multipartRequest(
    String method,
    String path, {
    required Map<String, String> fields,
    String? fileField,
    String? fileName,
    List<int>? fileBytes,
    String? fileContentType,
    bool authenticated = true,
    bool retrying = false,
  }) async {
    final Uri uri = _uri(path, null);
    onRequest?.call();
    final String boundary =
        '----agency-platform-${DateTime.now().microsecondsSinceEpoch}';
    try {
      final HttpClientRequest httpRequest =
          await _httpClient.openUrl(method, uri);
      httpRequest.followRedirects = false;
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
      httpRequest.headers.contentType = ContentType('multipart', 'form-data',
          parameters: {'boundary': boundary});

      for (final MapEntry<String, String> entry in fields.entries) {
        httpRequest.write('--$boundary\r\n');
        httpRequest.write(
          'Content-Disposition: form-data; name="${entry.key}"\r\n\r\n',
        );
        httpRequest.write(entry.value);
        httpRequest.write('\r\n');
      }
      if (fileField != null && fileName != null && fileBytes != null) {
        httpRequest.write('--$boundary\r\n');
        httpRequest.write(
          'Content-Disposition: form-data; name="$fileField"; filename="$fileName"\r\n',
        );
        httpRequest.write(
          'Content-Type: ${fileContentType ?? 'application/octet-stream'}\r\n\r\n',
        );
        httpRequest.add(fileBytes);
        httpRequest.write('\r\n');
      }
      httpRequest.write('--$boundary--\r\n');

      final HttpClientResponse response =
          await httpRequest.close().timeout(const Duration(seconds: 30));
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
        return multipartRequest(
          method,
          path,
          fields: fields,
          fileField: fileField,
          fileName: fileName,
          fileBytes: fileBytes,
          fileContentType: fileContentType,
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
    normalizeServerUrl(baseUrl);
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

/// Read an envelope whose `data` is a list, mapping each row.
List<T> _unwrapList<T>(Json json, T Function(Json) fromJson) {
  final dynamic data = json['data'];
  if (data is! List) return const [];
  return data
      .whereType<Map>()
      .map((item) => fromJson(Map<String, dynamic>.from(item)))
      .toList(growable: false);
}
