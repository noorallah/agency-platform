import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../../models/geography.dart';
import '../../models/entities.dart';
import '../../models/audit.dart';
import '../../models/bulk_action.dart';
import '../../models/finance.dart';
import '../../models/physical_count.dart';
import '../../models/expense.dart';
import '../../models/gst_payment.dart';
import '../../models/settlement.dart';
import '../../models/settlement_direction.dart';
import '../../models/batch_serial.dart';
import '../../models/branch_warehouse.dart';
import '../../models/customer.dart';
import '../../models/customer_opening_bill.dart';
import '../../models/customer_records.dart';
import '../../models/backup.dart';
import '../../models/diagnostics.dart';
import '../../models/document_framework.dart';
import '../../models/print_template.dart';
import '../../models/product.dart';
import '../../models/file_import.dart';
import '../../models/quotation.dart';
import '../../models/pricing.dart';
import '../../models/commission.dart';
import '../../models/credit_note.dart';
import '../../models/customer_debit_note.dart';
import '../../models/debit_note.dart';
import '../../models/party_adjustment.dart';
import '../../models/contra_voucher.dart';
import '../../models/tds_challan.dart';
import '../../models/post_dated_cheque.dart';
import '../../models/bank_account_details.dart';
import '../../models/einvoice.dart';
import '../../models/proforma.dart';
import '../../models/tcs.dart';
import '../../models/firm_member.dart';
import '../../models/messaging.dart';
import '../../models/price_floor.dart';
import '../../models/batch_sale_settings.dart';
import '../../models/gst_documents.dart';
import '../../models/sales_invoice.dart';
import '../../models/sales_analysis.dart';
import '../../models/sales_return.dart';
import '../../models/goods_receipt.dart';
import '../../models/purchase.dart';
import '../../models/sales_territory.dart';
import '../../models/tax_framework.dart';
import '../../models/uom_packaging.dart';
import '../../models/inventory.dart';
import '../../models/vendor.dart';
import '../../models/vendor_opening_bill.dart';
import '../../models/vendor_rating.dart';
import '../../models/report.dart';
import '../../models/trade_licence.dart';
import '../preferences/desktop_preferences_service.dart';
import '../preferences/user_preferences.dart';

class ApiException implements Exception {
  const ApiException(
    this.message, {
    this.statusCode,
    this.details,
    this.code,
  });
  final String message;
  final int? statusCode;
  final Object? details;

  /// The server's stable error code (`error.code` in the envelope), when the
  /// response carried one. Messages are for people; this is for deciding.
  final String? code;
  bool get isForbidden => statusCode == HttpStatus.forbidden;

  /// A bill the firm must e-invoice has no IRN yet, so the server will not
  /// print it as a tax invoice (`details.reason == irn_required`). The caller
  /// may offer a reference copy instead (GST backlog 77.6).
  bool get isIrnRequired {
    final Object? d = details;
    return d is Map && d['reason'] == 'irn_required';
  }

  /// The refusal names the *account's* state -- locked, inactive, expired --
  /// rather than the credential. A wrong password answers the one message
  /// whatever the cause, so nothing about an address is disclosed; these
  /// three disclose it on purpose, because the person holding the right
  /// password needs to know what to do next (docs/BACKLOG.md 18.1, 18.2).
  bool get namesAccountState => const <String>{
        'account_locked',
        'account_inactive',
        'account_expired',
      }.contains(code);

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

/// How many records a paged list response holds in all, not on this page.
///
/// The server names it `pagination.total_records`. Three document screens read
/// `pagination.total`, which is never sent, fell back to the rows on the page,
/// and so reported "20 records" and offered no second page: FOOD01's 49
/// delivery notes showed as 20 (manual plan item 13.9c3, 2026-09-15).
int pagedTotal(Json page, {required int fallback}) {
  final dynamic pagination = page['pagination'];
  if (pagination is! Map) return fallback;
  return (pagination['total_records'] as num?)?.toInt() ??
      (pagination['total'] as num?)?.toInt() ??
      fallback;
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

  /// Who is signed in: name, email, designation and primary firm.
  ///
  /// The login response carries tokens only and the token carries no name,
  /// so this is the one read the user menu has. Gated on being signed in and
  /// nothing else.
  Future<CurrentUser> me() async =>
      CurrentUser.fromJson(_unwrapMap(await request('GET', '/api/v1/me')));

  /// Choose the firm to land in at sign-in, among the ones this user belongs
  /// to. Self-service; the administrator's route is `setUserFirms`.
  Future<CurrentUser> setPrimaryFirm(String firmId) async =>
      CurrentUser.fromJson(_unwrapMap(await request(
        'PUT',
        '/api/v1/me/primary-firm',
        body: {'firm_id': firmId},
      )));

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

  /// The backups on the server's disk and the run in progress, if any.
  ///
  /// A platform path: no firm header decides what comes back.
  Future<BackupOverview> getBackups() async => BackupOverview.fromJson(
        _unwrapMap(await request('GET', '/api/v1/backups')),
      );

  /// Starts a backup and returns at once; the answer says it is running, and
  /// [getBackups] says when it is done. A 409 means one is already running.
  Future<BackupOverview> startBackup() async => BackupOverview.fromJson(
        _unwrapMap(await request('POST', '/api/v1/backups')),
      );

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

  /// Where a firm's setup stands: storage, profile, books, tax, geography,
  /// branches and people, each read from wherever it lives.
  Future<FirmReadiness> firmReadiness(String firmId) async =>
      FirmReadiness.fromJson(
        _unwrapMap(await request('GET', '/api/v1/firms/$firmId/readiness')),
      );

  /// Give a firm its chart of accounts, financial year, periods and every
  /// control-account mapping -- the one setup step that had no screen.
  ///
  /// Returns the server's message, which says which year was opened or that
  /// the books were already open. Safe to call again.
  Future<String> openFirmBooks(String firmId) async {
    final Json response =
        await request('POST', '/api/v1/firms/$firmId/open-books');
    return stringValue(response['message']).isEmpty
        ? 'Books opened.'
        : stringValue(response['message']);
  }

  /// Give a firm its whole tax setup from a template -- Indian GST today.
  ///
  /// Returns the server's message, which counts what was created or says
  /// the firm already had a tax system. Safe to call again.
  Future<String> applyFirmTaxTemplate(String firmId) async {
    final Json response = await request(
      'POST',
      '/api/v1/firms/$firmId/apply-tax-template',
      body: const {'template': 'IN_GST'},
    );
    return stringValue(response['message']).isEmpty
        ? 'GST set up.'
        : stringValue(response['message']);
  }

  /// The business profiles one firm may be assigned, from that firm's own
  /// store -- `businessProfiles()` reads the caller's, which in platform
  /// mode is none.
  Future<List<BusinessProfileRecord>> firmProfileCatalogue(
    String firmId,
  ) async {
    final Json response = await request(
      'GET',
      '/api/v1/business-framework/firms/$firmId/profiles',
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) =>
            BusinessProfileRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  /// Give a firm a head office and a main warehouse with default names,
  /// renamed later on their own screens. Idempotent per half.
  Future<String> createFirmDefaultBranch(String firmId) async {
    final Json response = await request(
      'POST',
      '/api/v1/firms/$firmId/create-default-branch',
    );
    return stringValue(response['message']).isEmpty
        ? 'Created.'
        : stringValue(response['message']);
  }

  /// List users, optionally narrowed to one firm's active members.
  ///
  /// `firmId` answers "who works at this firm?" without switching into it --
  /// a question only a platform administrator can ask across firms, and one
  /// the server refuses for a firm caller naming anybody else's firm.
  Future<PagedResult<PlatformUser>> users({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    String firmId = '',
    bool deletedOnly = false,
    bool inactiveOnly = false,
    bool activeOnly = false,
  }) =>
      _list('/api/v1/users', PlatformUser.fromJson, page, search,
          pageSize: pageSize,
          sortBy: sortBy,
          descending: descending,
          additionalQuery: {
            if (firmId.isNotEmpty) 'firm_id': firmId,
            // Deleted rows instead of live ones. Honoured for a platform
            // administrator only; the server keeps a firm caller's list to
            // live rows whatever is sent.
            if (deletedOnly) 'deleted_only': 'true',
            // Only the live rows with Active unticked, or only those with it
            // set -- the Status filter's Inactive and Active. Mutually
            // exclusive: the dropdown sends at most one.
            if (inactiveOnly) 'inactive_only': 'true',
            if (activeOnly) 'active_only': 'true',
          });

  /// Set somebody else's password without knowing the current one.
  ///
  /// Platform administrators only. Clears a login lock and revokes every
  /// session; `forceChange` makes the person choose their own at the next
  /// sign-in, which is the default and the point.
  Future<PlatformUser> resetUserPassword(
    String id,
    String newPassword, {
    bool forceChange = true,
  }) async =>
      PlatformUser.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/users/$id/password',
        body: {
          'new_password': newPassword,
          'force_password_change': forceChange,
        },
      )));

  /// Bring a soft-deleted user back with their old firms and roles.
  /// Platform administrators only.
  Future<PlatformUser> restoreUser(String id) async =>
      PlatformUser.fromJson(_unwrapMap(
        await request('POST', '/api/v1/users/$id/restore'),
      ));
  Future<PagedResult<Role>> roles({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) =>
      _list('/api/v1/roles', Role.fromJson, page, search,
          pageSize: pageSize, sortBy: sortBy, descending: descending);

  /// Lists the job templates this caller may offer.
  ///
  /// A firm sees the platform's eleven **and** its own. Platform-owned like
  /// `/roles` and `/users`, so it resolves against the platform schema.
  Future<PagedResult<UserTemplate>> userTemplates({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'code',
    bool descending = false,
  }) =>
      _list('/api/v1/user-templates', UserTemplate.fromJson, page, search,
          pageSize: pageSize, sortBy: sortBy, descending: descending);

  /// Finds somebody who already has an account, to hire them into this firm.
  ///
  /// Two callers, two answers. For a **firm** caller it is a lookup, not a
  /// directory: the server refuses a term under three characters, caps the
  /// result at ten whatever the page says, and never says which firms
  /// somebody belongs to. For a **platform** caller an empty term lists
  /// everybody not yet in the firm on `X-Firm-ID`, paged, and a term filters
  /// it. `list_users` stays scoped to the caller's own firm.
  Future<PagedResult<UserLookupResult>> lookupUsers(
    String term, {
    int page = 1,
    int pageSize = 100,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/users/lookup',
      query: {'q': term, 'page': '$page', 'page_size': '$pageSize'},
    );
    return parsePagedResponse(response, UserLookupResult.fromJson);
  }

  /// Hires somebody to do what an existing person does.
  ///
  /// Only access crosses over. The new person starts without the source's
  /// mobile number, employee code, joining date, photo, password, login
  /// history or audit trail -- those belong to the person, not to the job.
  Future<PlatformUser> cloneUser(
    String sourceId, {
    required String email,
    required String fullName,
    required String password,
  }) async =>
      PlatformUser.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/users/$sourceId/clone',
        body: {
          'email': email,
          'full_name': fullName,
          'password': password,
        },
      )));

  /// Gives a user the roles a template bundles.
  ///
  /// What they hold afterwards is an ordinary role set, editable in the
  /// ordinary way -- a template is where an administrator starts, not
  /// somewhere the user stays.
  /// Apply a job template, optionally in one named firm.
  ///
  /// A platform caller who names no firm grants the job **globally** -- in
  /// every firm the person belongs to and every firm they are added to later.
  /// That is rarely what "hire this person as a cashier" means, so the create
  /// form asks which, and passes it here.
  Future<void> applyUserTemplate(
    String userId,
    String templateId, {
    String firmId = '',
  }) =>
      request('POST', '/api/v1/users/$userId/apply-template', body: {
        'template_id': templateId,
        if (firmId.isNotEmpty) 'firm_id': firmId,
      });

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

  /// The custom fields a form should offer for one entity type, resolved
  /// for the current firm the way a save resolves them.
  Future<ApplicableAttributesRecord> applicableAttributeDefinitions(
    String entityType,
  ) async =>
      ApplicableAttributesRecord.fromJson(_unwrapMap(await request(
        'GET',
        '/api/v1/business-framework/attribute-definitions/applicable',
        query: {'entity_type': entityType},
      )));

  Future<PagedResult<TaxSystemRecord>> taxSystems({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    String? status,

    /// Retired rows are hidden by default, which is right for a picker.
    /// A screen offering to bring one back has to be able to show it.
    bool includeDeleted = false,
  }) =>
      _list(
        '/api/v1/tax-framework/systems',
        TaxSystemRecord.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: sortBy,
        descending: descending,
        additionalQuery: {
          if (status != null) 'status': status,
          if (includeDeleted) 'include_deleted': 'true',
        },
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

    /// Retired rows are hidden by default, which is right for a picker.
    /// A screen offering to bring one back has to be able to show it.
    bool includeDeleted = false,
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
          if (includeDeleted) 'include_deleted': 'true',
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

    /// Retired rows are hidden by default, which is right for a picker.
    /// A screen offering to bring one back has to be able to show it.
    bool includeDeleted = false,
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
          if (includeDeleted) 'include_deleted': 'true',
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

  /// One customer, with the addresses a document can ship to.
  Future<Customer> customer(String id) async => Customer.fromJson(
        _unwrapMap(await request('GET', '/api/v1/customers/$id')),
      );

  /// The sentence naming the other customers that hold this GSTIN or PAN, or
  /// null when none does (decision A7: a repeat is allowed, so the form asks
  /// before saving rather than being refused). [excludingId] is the customer
  /// being edited.
  Future<String?> customerIdentityCheck({
    String gstNumber = '',
    String panNumber = '',
    String? excludingId,
  }) async {
    final Json data = _unwrapMap(
      await request(
        'GET',
        '/api/v1/customers/identity-check',
        query: {
          if (gstNumber.isNotEmpty) 'gst_number': gstNumber,
          if (panNumber.isNotEmpty) 'pan_number': panNumber,
          if (excludingId != null) 'excluding_id': excludingId,
        },
      ),
    );
    final dynamic message = data['message'];
    return message is String && message.isNotEmpty ? message : null;
  }

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

  /// Approve a customer waiting for office approval (SEL-15); it becomes
  /// ACTIVE and can be billed. Needs `CUSTOMER_APPROVE`.
  Future<Customer> approveCustomer(String id) async =>
      Customer.fromJson(_unwrapMap(
        await request('POST', '/api/v1/customers/$id/approve'),
      ));

  /// Approve several waiting customers in one call; per row, so some can be
  /// refused while others succeed.
  Future<BulkActionResult> bulkApproveCustomers(List<BulkRow> rows) =>
      _bulk('/api/v1/customers/bulk-approve', rows);

  Future<void> deleteCustomer(String id) =>
      request('DELETE', '/api/v1/customers/$id');

  Future<Customer> restoreCustomer(String id) async =>
      Customer.fromJson(_unwrapMap(
        await request('POST', '/api/v1/customers/$id/restore'),
      ));

  /// The bank accounts held against a customer (MST-4). The number comes
  /// masked unless the caller may manage bank details.
  Future<List<CustomerBankAccount>> customerBankAccounts(
    String customerId,
  ) async =>
      _unwrapList(
        await request('GET', '/api/v1/customers/$customerId/bank-accounts'),
        CustomerBankAccount.fromJson,
      );

  /// Replace the customer's whole list of bank accounts; empty clears it.
  Future<List<CustomerBankAccount>> saveCustomerBankAccounts(
    String customerId,
    List<Json> accounts,
  ) async =>
      _unwrapList(
        await request(
          'PUT',
          '/api/v1/customers/$customerId/bank-accounts',
          body: {'accounts': accounts},
        ),
        CustomerBankAccount.fromJson,
      );

  /// The files kept with a customer (MST-4).
  Future<List<CustomerAttachment>> customerAttachments(
    String customerId,
  ) async =>
      _unwrapList(
        await request('GET', '/api/v1/customers/$customerId/attachments'),
        CustomerAttachment.fromJson,
      );

  /// Keep files with a customer, referenced by path.
  Future<List<CustomerAttachment>> addCustomerAttachments(
    String customerId,
    List<Json> files,
  ) async =>
      _unwrapList(
        await request(
          'POST',
          '/api/v1/customers/$customerId/attachments',
          body: {'files': files},
        ),
        CustomerAttachment.fromJson,
      );

  /// Take one file off a customer.
  Future<void> removeCustomerAttachment(
    String customerId,
    String attachmentId,
  ) async {
    await request(
      'DELETE',
      '/api/v1/customers/$customerId/attachments/$attachmentId',
    );
  }

  /// What this customer owed the firm on its first day here, bill by bill.
  Future<List<CustomerOpeningBill>> customerOpeningBills(
    String customerId,
  ) async =>
      _unwrapList(
        await request('GET', '/api/v1/customers/$customerId/opening-bills'),
        CustomerOpeningBill.fromJson,
      );

  /// Record one bill the customer owed at cutover, and post it.
  Future<CustomerOpeningBill> createCustomerOpeningBill(
    String customerId,
    Json data,
  ) async =>
      CustomerOpeningBill.fromJson(_unwrapMap(
        await request(
          'POST',
          '/api/v1/customers/$customerId/opening-bills',
          body: data,
        ),
      ));

  /// Take back an opening bill entered in error; refused once anything has
  /// been received against it.
  Future<CustomerOpeningBill> cancelCustomerOpeningBill(
    String billId,
    String reason,
  ) async =>
      CustomerOpeningBill.fromJson(_unwrapMap(
        await request(
          'POST',
          '/api/v1/customers/opening-bills/$billId/cancel',
          body: {'reason': reason},
        ),
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

  /// Which stages of a sale this firm fills in by hand.
  ///
  /// Readable with `SALES_VIEW` -- somebody whose screens the setting moves
  /// should be able to see the rule behind it -- and writable only with
  /// `SALES_MANAGE_SETTINGS`.
  Future<SalesWorkflowSettings> salesWorkflowSettings() async =>
      SalesWorkflowSettings.fromJson(
        _unwrapMap(
          await request('GET', '/api/v1/sales-orders/workflow-settings'),
        ),
      );

  Future<SalesWorkflowSettings> updateSalesWorkflowSettings(
    SalesWorkflowSettings settings,
  ) async =>
      SalesWorkflowSettings.fromJson(
        _unwrapMap(
          await request(
            'PUT',
            '/api/v1/sales-orders/workflow-settings',
            body: settings.toJson(),
          ),
        ),
      );

  /// The firm's price-floor policy (backlog 64 row 2): readable by any sales
  /// viewer, writable only with `SALES_MANAGE_SETTINGS`.
  Future<PriceFloorSettings> priceFloorSettings() async =>
      PriceFloorSettings.fromJson(
        _unwrapMap(
          await request('GET', '/api/v1/sales-orders/price-floor-settings'),
        ),
      );

  Future<PriceFloorSettings> updatePriceFloorSettings(
    PriceFloorSettings settings,
  ) async =>
      PriceFloorSettings.fromJson(
        _unwrapMap(
          await request(
            'PUT',
            '/api/v1/sales-orders/price-floor-settings',
            body: settings.toJson(),
          ),
        ),
      );

  /// The most each role may discount by hand (backlog 64 row 3). Readable by
  /// any sales viewer.
  Future<List<RoleDiscountLimit>> discountLimits() async => _limitsFrom(
        _unwrapMap(
          await request('GET', '/api/v1/sales-orders/discount-limits'),
        ),
      );

  /// Replaces the whole list: a role left out has no limit. Needs
  /// `SALES_MANAGE_SETTINGS`.
  Future<List<RoleDiscountLimit>> updateDiscountLimits(
    List<RoleDiscountLimit> limits,
  ) async =>
      _limitsFrom(
        _unwrapMap(
          await request(
            'PUT',
            '/api/v1/sales-orders/discount-limits',
            body: <String, dynamic>{
              'limits': [for (final limit in limits) limit.toJson()],
            },
          ),
        ),
      );

  static List<RoleDiscountLimit> _limitsFrom(Json data) {
    final Object? raw = data['limits'];
    return raw is List
        ? [
            for (final item in raw)
              if (item is Map)
                RoleDiscountLimit.fromJson(Map<String, dynamic>.from(item)),
          ]
        : const <RoleDiscountLimit>[];
  }

  // ── Messaging (backlog 51) ─────────────────────────────────────────────
  // Whether anything is sent, through which accounts, for which events, and
  // the log of what was. Reading needs SETTINGS_VIEW; changing it needs
  // SETTINGS_UPDATE; sending and resending need DOCUMENT_SEND.

  Future<MessagingSettings> messagingSettings() async =>
      MessagingSettings.fromJson(
        _unwrapMap(await request('GET', '/api/v1/messaging/settings')),
      );

  Future<MessagingSettings> updateMessagingSettings(
    MessagingSettings settings,
  ) async =>
      MessagingSettings.fromJson(
        _unwrapMap(
          await request(
            'PUT',
            '/api/v1/messaging/settings',
            body: settings.toJson(),
          ),
        ),
      );

  /// The services a channel can use, with the fields each one's account form
  /// is drawn from.
  Future<List<MessagingProvider>> messagingProviders() async => _unwrapList(
        await request('GET', '/api/v1/messaging/providers'),
        MessagingProvider.fromJson,
      );

  Future<List<MessagingEvent>> messagingEvents() async => _unwrapList(
        await request('GET', '/api/v1/messaging/events'),
        MessagingEvent.fromJson,
      );

  Future<List<MessagingChannel>> messagingChannels() async => _unwrapList(
        await request('GET', '/api/v1/messaging/channels'),
        MessagingChannel.fromJson,
      );

  /// Saves the account for [channel]. A secret left blank keeps the saved one.
  Future<ChannelOutcome> saveMessagingChannel(
    String channel,
    String provider,
    Map<String, String> settings,
  ) async =>
      ChannelOutcome.fromEnvelope(
        await request(
          'PUT',
          '/api/v1/messaging/channels/$channel',
          body: <String, dynamic>{'provider': provider, 'settings': settings},
        ),
      );

  /// The result's message says whether the test passed or why it failed.
  Future<ChannelOutcome> testMessagingChannel(String channel) async =>
      ChannelOutcome.fromEnvelope(
        await request('POST', '/api/v1/messaging/channels/$channel/test'),
      );

  Future<ChannelOutcome> enableMessagingChannel(String channel) async =>
      ChannelOutcome.fromEnvelope(
        await request('POST', '/api/v1/messaging/channels/$channel/enable'),
      );

  Future<ChannelOutcome> disableMessagingChannel(String channel) async =>
      ChannelOutcome.fromEnvelope(
        await request('POST', '/api/v1/messaging/channels/$channel/disable'),
      );

  Future<List<EventConfig>> messagingEventConfigs() async => _unwrapList(
        await request('GET', '/api/v1/messaging/event-configs'),
        EventConfig.fromJson,
      );

  /// Replaces the event's channel list; its order is the fallback order and
  /// an empty list switches the event off.
  Future<EventConfig> updateMessagingEventConfig(
    String eventCode,
    List<EventChannelRule> channels,
  ) async =>
      EventConfig.fromJson(
        _unwrapMap(
          await request(
            'PUT',
            '/api/v1/messaging/event-configs/$eventCode',
            body: <String, dynamic>{
              'channels': [for (final rule in channels) rule.toJson()],
            },
          ),
        ),
      );

  Future<PagedResult<MessageLogEntry>> messagingMessages({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String status = '',
    String channel = '',
  }) =>
      _list(
        '/api/v1/messaging/messages',
        MessageLogEntry.fromJson,
        page,
        search,
        pageSize: pageSize,
        additionalQuery: {
          if (status.isNotEmpty) 'status': status,
          if (channel.isNotEmpty) 'channel': channel,
        },
      );

  Future<void> resendMessagingMessage(String messageId) => request(
        'POST',
        '/api/v1/messaging/messages/$messageId/resend',
      );

  /// Queues a sales invoice to go to its customer, or to [recipient].
  Future<void> sendSalesInvoiceMessage(
    String invoiceId,
    String channel, {
    String? recipient,
    String? message,
  }) =>
      sendDocumentMessage(
        'SALES_INVOICE',
        invoiceId,
        channel,
        recipient: recipient,
        message: message,
      );

  /// Queues a document to go out by hand (MSG-4): [documentType] is
  /// `SALES_INVOICE`, or -- by email only -- `SALES_QUOTATION`,
  /// `SALES_ORDER`, `CUSTOMER_STATEMENT` (the id is the customer's),
  /// `RECEIPT` or `PURCHASE_ORDER`.
  Future<void> sendDocumentMessage(
    String documentType,
    String documentId,
    String channel, {
    String? recipient,
    String? message,
  }) =>
      request(
        'POST',
        '/api/v1/messaging/send',
        body: <String, dynamic>{
          'document_type': documentType,
          'document_id': documentId,
          'channel': channel,
          if (recipient != null && recipient.isNotEmpty) 'recipient': recipient,
          if (message != null && message.isNotEmpty) 'message': message,
        },
      );

  /// Whom to share an approved bill with on WhatsApp by hand, and what to
  /// say (MSG-1). Needs no messaging account.
  Future<HandShare> salesInvoiceHandShare(String invoiceId) async {
    final Json response = await request(
      'GET',
      '/api/v1/messaging/share/sales-invoices/$invoiceId',
    );
    return HandShare.fromJson(response['data'] as Json);
  }

  /// Whom to remind on WhatsApp by hand, and what to say (MSG-3).
  Future<HandShare> customerStatementShare(String customerId) async {
    final Json response = await request(
      'GET',
      '/api/v1/messaging/share/customer-statements/$customerId',
    );
    return HandShare.fromJson(response['data'] as Json);
  }

  /// Emails a customer their statement as a payment reminder (MSG-3).
  Future<void> remindCustomer(
    String customerId, {
    String? recipient,
    String? message,
  }) =>
      request(
        'POST',
        '/api/v1/messaging/remind',
        body: <String, dynamic>{
          'customer_id': customerId,
          if (recipient != null && recipient.isNotEmpty) 'recipient': recipient,
          if (message != null && message.isNotEmpty) 'message': message,
        },
      );

  /// A customer's statement of account with their unpaid bills, as a PDF:
  /// what a reminder attaches.
  Future<List<int>> customerStatementPdf(String customerId) =>
      downloadBytes('/api/v1/customers/$customerId/statement/print');

  /// Barcode labels for chosen products (STK-16): [items] are
  /// `{product_id, copies}`; [skip] is how many labels of a part-used sheet
  /// are already gone.
  Future<List<int>> productLabelsPdf({
    required List<Map<String, Object?>> items,
    String layout = 'A4_65',
    int skip = 0,
    bool showPrice = true,
  }) =>
      downloadBytes(
        '/api/v1/products/labels',
        method: 'POST',
        body: <String, dynamic>{
          'items': items,
          'layout': layout,
          'skip': skip,
          'show_price': showPrice,
        },
      );

  /// One label for every piece a goods receipt brought in (STK-16).
  Future<List<int>> goodsReceiptLabelsPdf(
    String receiptId, {
    String layout = 'A4_65',
    int skip = 0,
    bool showPrice = true,
  }) =>
      downloadBytes(
        '/api/v1/goods-receipts/$receiptId/labels',
        query: {
          'layout': layout,
          'skip': '$skip',
          'show_price': '$showPrice',
        },
      );

  /// Every bank account's saved cheque layout (ACC-12).
  Future<List<ChequeLayout>> chequeLayouts() async => _unwrapList(
        await request('GET', '/api/v1/payments/cheque-layouts'),
        ChequeLayout.fromJson,
      );

  /// One bank account's layout: zeros and A/c Payee on when never saved.
  Future<ChequeLayout> chequeLayout(String ledgerAccountId) async =>
      ChequeLayout.fromJson(
        await request(
          'GET',
          '/api/v1/payments/cheque-layouts/$ledgerAccountId',
        ),
      );

  /// Saves how far the bank's leaf prints off the standard positions.
  Future<ChequeLayout> saveChequeLayout(
    String ledgerAccountId, {
    required String offsetXMm,
    required String offsetYMm,
    required bool printAcPayee,
  }) async =>
      ChequeLayout.fromJson(
        await request(
          'PUT',
          '/api/v1/payments/cheque-layouts/$ledgerAccountId',
          body: <String, dynamic>{
            'offset_x_mm': offsetXMm,
            'offset_y_mm': offsetYMm,
            'print_ac_payee': printAcPayee,
          },
        ),
      );

  /// A sample cheque drawn with the saved offsets, to line the leaf up.
  Future<List<int>> chequeTestPdf(String ledgerAccountId) =>
      downloadBytes('/api/v1/payments/cheque-layouts/$ledgerAccountId/test');

  /// A bank payment on the bank's cheque leaf; a blank [payee] prints the
  /// supplier's legal name.
  Future<List<int>> paymentChequePdf(String paymentId, {String? payee}) =>
      downloadBytes(
        '/api/v1/payments/$paymentId/cheque',
        query: {
          if (payee != null && payee.trim().isNotEmpty) 'payee': payee.trim(),
        },
      );

  /// Records a share made by hand: on the bill's timeline, or in the
  /// customer's trail for a statement sent as a reminder.
  Future<void> recordHandShare(
    String documentId, {
    String? recipient,
    String documentType = 'SALES_INVOICE',
  }) =>
      request(
        'POST',
        '/api/v1/messaging/shared',
        body: <String, dynamic>{
          'document_type': documentType,
          'document_id': documentId,
          'channel': 'WHATSAPP',
          if (recipient != null && recipient.isNotEmpty) 'recipient': recipient,
        },
      );

  /// What the approval would say about a sales order's prices, before it is
  /// asked to.
  Future<PriceFloorCheck> salesOrderPriceCheck(String id) async =>
      PriceFloorCheck.fromJson(
        _unwrapMap(
          await request('GET', '/api/v1/sales-orders/$id/price-check'),
        ),
      );

  /// The same for a sales invoice.
  Future<PriceFloorCheck> salesInvoicePriceCheck(String id) async =>
      PriceFloorCheck.fromJson(
        _unwrapMap(
          await request('GET', '/api/v1/sales-invoices/$id/price-check'),
        ),
      );

  /// Which stages of buying this firm fills in by hand (backlog §38).
  ///
  /// Readable with `PURCHASE_VIEW` and writable only with
  /// `PURCHASE_MANAGE_SETTINGS`, as the sales twin above.
  Future<PurchaseWorkflowSettings> purchaseWorkflowSettings() async =>
      PurchaseWorkflowSettings.fromJson(
        _unwrapMap(
          await request('GET', '/api/v1/purchases/workflow-settings'),
        ),
      );

  Future<PurchaseWorkflowSettings> updatePurchaseWorkflowSettings(
    PurchaseWorkflowSettings settings,
  ) async =>
      PurchaseWorkflowSettings.fromJson(
        _unwrapMap(
          await request(
            'PUT',
            '/api/v1/purchases/workflow-settings',
            body: settings.toJson(),
          ),
        ),
      );

  /// How the below-reorder list decides what is short (backlog 69 row 12):
  /// `LEVELS` (typed per product) or `SALES` (derived from what sold). Readable
  /// with `PURCHASE_VIEW` or `REPORT_VIEW`.
  Future<Json> reorderPlanning() async =>
      _unwrapMap(await request('GET', '/api/v1/purchases/reorder-planning'));

  /// All five fields are always sent; the server refuses extra keys and needs
  /// `PURCHASE_MANAGE_SETTINGS`.
  Future<Json> updateReorderPlanning(Json settings) async => _unwrapMap(
        await request(
          'PUT',
          '/api/v1/purchases/reorder-planning',
          body: settings,
        ),
      );

  /// The largest order each role may approve (backlog 68 row 4). Readable by
  /// any purchase viewer.
  Future<List<RolePurchaseApprovalLimit>> purchaseApprovalLimits() async =>
      _approvalLimitsFrom(
        _unwrapMap(
          await request('GET', '/api/v1/purchases/approval-limits'),
        ),
      );

  /// Replaces the whole list: a role left out has no limit. Needs
  /// `PURCHASE_MANAGE_SETTINGS`.
  Future<List<RolePurchaseApprovalLimit>> updatePurchaseApprovalLimits(
    List<RolePurchaseApprovalLimit> limits,
  ) async =>
      _approvalLimitsFrom(
        _unwrapMap(
          await request(
            'PUT',
            '/api/v1/purchases/approval-limits',
            body: <String, dynamic>{
              'limits': [for (final limit in limits) limit.toJson()],
            },
          ),
        ),
      );

  static List<RolePurchaseApprovalLimit> _approvalLimitsFrom(Json data) {
    final Object? raw = data['limits'];
    return raw is List
        ? [
            for (final item in raw)
              if (item is Map)
                RolePurchaseApprovalLimit.fromJson(
                  Map<String, dynamic>.from(item),
                ),
          ]
        : const <RolePurchaseApprovalLimit>[];
  }

  /// The segments this firm sells to.
  ///
  /// Readable with `CUSTOMER_VIEW` -- a segment decides a price, so anyone
  /// raising a document should be able to see which one a shop is in -- and
  /// writable with `CUSTOMER_MANAGE_SETTINGS`.
  Future<PagedResult<CustomerGroup>> customerGroups({
    int page = 1,
    int pageSize = 100,
    String search = '',
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/customers/groups',
      query: {
        'page': '$page',
        'page_size': '$pageSize',
        if (search.trim().isNotEmpty) 'search': search.trim(),
      },
    );
    final dynamic data = response['data'];
    return PagedResult<CustomerGroup>(
      items: data is List
          ? data
              .whereType<Map>()
              .map((item) =>
                  CustomerGroup.fromJson(Map<String, dynamic>.from(item)))
              .toList()
          : const [],
      total: _totalOf(response),
    );
  }

  Future<CustomerGroup> createCustomerGroup(Json body) async =>
      CustomerGroup.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/customers/groups', body: body)),
      );

  Future<CustomerGroup> updateCustomerGroup(
    String id,
    Json body, {
    int? expectedVersion,
  }) async =>
      CustomerGroup.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/customers/groups/$id',
          body: body,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deleteCustomerGroup(String id) =>
      request('DELETE', '/api/v1/customers/groups/$id');

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

  /// What people think of a supplier (BUY-15): averages, every rating and
  /// the caller's own.
  Future<VendorRatings> vendorRatings(String vendorId) async =>
      VendorRatings.fromJson(_unwrapMap(
        await request('GET', '/api/v1/vendors/$vendorId/ratings'),
      ));

  /// Save the caller's rating of a supplier, replacing an earlier one.
  Future<VendorRating> saveMyVendorRating(String vendorId, Json body) async =>
      VendorRating.fromJson(_unwrapMap(
        await request(
          'PUT',
          '/api/v1/vendors/$vendorId/ratings/mine',
          body: body,
        ),
      ));

  /// Withdraw the caller's rating of a supplier.
  Future<void> withdrawMyVendorRating(String vendorId) =>
      request('DELETE', '/api/v1/vendors/$vendorId/ratings/mine');

  /// What this supplier was owed on the firm's first day here.
  Future<List<VendorOpeningBill>> vendorOpeningBills(String vendorId) async =>
      _unwrapList(
        await request('GET', '/api/v1/vendors/$vendorId/opening-bills'),
        VendorOpeningBill.fromJson,
      );

  /// Record one bill the supplier was owed at cutover, and post it.
  Future<VendorOpeningBill> createVendorOpeningBill(
    String vendorId,
    Json data,
  ) async =>
      VendorOpeningBill.fromJson(_unwrapMap(
        await request(
          'POST',
          '/api/v1/vendors/$vendorId/opening-bills',
          body: data,
        ),
      ));

  /// Take back an opening bill entered in error; refused once it is paid.
  Future<VendorOpeningBill> cancelVendorOpeningBill(
    String billId,
    String reason,
  ) async =>
      VendorOpeningBill.fromJson(_unwrapMap(
        await request(
          'POST',
          '/api/v1/vendors/opening-bills/$billId/cancel',
          body: {'reason': reason},
        ),
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

  /// The signed-in person's usual branch and warehouse in this firm
  /// (backlog 44). Any member may read and set their own.
  Future<WorkDefaults> myWorkDefaults() async => WorkDefaults.fromJson(
        _unwrapMap(await request('GET', '/api/v1/branches/my-work-defaults')),
      );

  /// Set, or with both null clear, the person's own defaults.
  Future<WorkDefaults> setMyWorkDefaults({
    String? branchId,
    String? warehouseId,
  }) async =>
      WorkDefaults.fromJson(
        _unwrapMap(
          await request(
            'PUT',
            '/api/v1/branches/my-work-defaults',
            body: {'branch_id': branchId, 'warehouse_id': warehouseId},
          ),
        ),
      );

  /// Another member's usual branch and warehouse, for an administrator
  /// (backlog 44): `USER_VIEW` to read, held to this firm's members.
  Future<WorkDefaults> memberWorkDefaults(String userId) async =>
      WorkDefaults.fromJson(
        _unwrapMap(await request(
            'GET', '/api/v1/branches/work-defaults/$userId')),
      );

  /// Set, or with both null clear, another member's defaults
  /// (`USER_UPDATE`).
  Future<WorkDefaults> setMemberWorkDefaults(
    String userId, {
    String? branchId,
    String? warehouseId,
  }) async =>
      WorkDefaults.fromJson(
        _unwrapMap(
          await request(
            'PUT',
            '/api/v1/branches/work-defaults/$userId',
            body: {'branch_id': branchId, 'warehouse_id': warehouseId},
          ),
        ),
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

  /// Every batch of a product in a warehouse with what a dispatch may take
  /// from each, nearest expiry first (the delivery note's batch picker).
  Future<List<BatchAvailabilityRecord>> batchAvailability({
    required String productId,
    required String warehouseId,
    String? storageNodeId,
    String? asOf,
    num? quantity,
    String? salesOrderLineId,
    String? customerId,
  }) async =>
      _unwrapList(
        await request(
          'GET',
          '/api/v1/batch-serial/batches/availability',
          query: {
            'product_id': productId,
            'warehouse_id': warehouseId,
            if (storageNodeId != null) 'storage_node_id': storageNodeId,
            if (asOf != null) 'as_of': asOf,
            if (quantity != null) 'quantity': '$quantity',
            if (salesOrderLineId != null && salesOrderLineId.isNotEmpty)
              'sales_order_line_id': salesOrderLineId,
            if (customerId != null && customerId.isNotEmpty)
              'customer_id': customerId,
          },
        ),
        BatchAvailabilityRecord.fromJson,
      );

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

  Future<void> deletePackagingLevel(String productId, String levelId) =>
      request(
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

  /// Stock per product with what is coming in and going out (STK-10).
  Future<List<InventoryLocationSummaryRecord>> inventoryByProduct() async {
    final Json response =
        await request('GET', '/api/v1/inventory/summary/by-product');
    return ((response['data'] as List?) ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(InventoryLocationSummaryRecord.fromJson)
        .toList(growable: false);
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

  /// The blank opening stock import file, as bytes: xlsx (with notes and the
  /// firm's warehouses and products) or csv.
  Future<List<int>> openingStockImportTemplate({String format = 'xlsx'}) =>
      downloadBytes(
        '/api/v1/inventory/opening-stock/import-template',
        query: {'format': format},
      );

  /// Check (`apply: false`, writes nothing) or import a stock count: one
  /// opening stock document per warehouse, created and posted on
  /// [postingDate] (`yyyy-mm-dd`).
  Future<FileImportReport> checkOpeningStockImportFile({
    required String fileName,
    required List<int> bytes,
    required String postingDate,
    required bool apply,
    Map<String, String?>? mapping,
  }) async {
    final Json response = await multipartRequest(
      'POST',
      '/api/v1/inventory/opening-stock/import-file',
      fields: {
        'posting_date': postingDate,
        'apply': apply ? 'true' : 'false',
        if (mapping != null) 'mapping': jsonEncode(mapping),
      },
      fileField: 'file',
      fileName: fileName,
      fileBytes: bytes,
      fileContentType: fileName.toLowerCase().endsWith('.xlsx')
          ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          : 'text/csv',
    );
    return FileImportReport.fromJson(_unwrapMap(response));
  }

  /// What an import file holds and how it would be read, before any check
  /// (B3). [kind] is `products`, `customers`, `vendors`,
  /// `customer-opening-bills`, `vendor-opening-bills` or `opening-stock`.
  /// Writes nothing.
  Future<ImportPreview> importPreview({
    required String kind,
    required String fileName,
    required List<int> bytes,
  }) async {
    final Json response = await multipartRequest(
      'POST',
      '/api/v1/imports/$kind/preview',
      fields: const <String, String>{},
      fileField: 'file',
      fileName: fileName,
      fileBytes: bytes,
      fileContentType: fileName.toLowerCase().endsWith('.xlsx')
          ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          : 'text/csv',
    );
    return ImportPreview.fromJson(_unwrapMap(response));
  }

  /// The mappings saved for one kind of import.
  Future<List<ImportMapping>> importMappings(String kind) async =>
      _unwrapList(
        await request('GET', '/api/v1/imports/$kind/mappings'),
        ImportMapping.fromJson,
      );

  /// Save a mapping under [name]; one of the same name is replaced.
  Future<ImportMapping> saveImportMapping(
    String kind,
    String name,
    Map<String, String?> mapping,
  ) async =>
      ImportMapping.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/imports/$kind/mappings',
        body: {'name': name, 'mapping': mapping},
      )));

  Future<void> deleteImportMapping(String id) =>
      request('DELETE', '/api/v1/imports/mappings/$id');

  /// The blank opening-bills import file for one side of the books --
  /// `customers` or `vendors` -- as bytes: xlsx (with notes and the firm's
  /// parties) or csv (D-GOLIVE-1).
  Future<List<int>> openingBillImportTemplate(
    String side, {
    String format = 'xlsx',
  }) =>
      downloadBytes(
        side == 'vendors'
            ? '/api/v1/vendors/opening-bills/import-template'
            : '/api/v1/customers/opening-bills/import-template',
        query: {'format': format},
      );

  /// Check (`apply: false`, writes nothing) or import a file of opening bills
  /// for `customers` or `vendors`, every bill posted on [postingDate]
  /// (`yyyy-mm-dd`), all of them or none.
  Future<FileImportReport> checkOpeningBillImportFile(
    String side, {
    required String fileName,
    required List<int> bytes,
    required String postingDate,
    required bool apply,
    Map<String, String?>? mapping,
  }) async {
    final Json response = await multipartRequest(
      'POST',
      side == 'vendors'
          ? '/api/v1/vendors/opening-bills/import-file'
          : '/api/v1/customers/opening-bills/import-file',
      fields: {
        'posting_date': postingDate,
        'apply': apply ? 'true' : 'false',
        if (mapping != null) 'mapping': jsonEncode(mapping),
      },
      fileField: 'file',
      fileName: fileName,
      fileBytes: bytes,
      fileContentType: fileName.toLowerCase().endsWith('.xlsx')
          ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          : 'text/csv',
    );
    return FileImportReport.fromJson(_unwrapMap(response));
  }

  // Counting a warehouse. The sheet is drawn up from what the system holds,
  // walked over hours, and posted once at the end -- so it is a document with
  // a draft the client saves into, not a form that applies on submit.

  Future<PagedResult<PhysicalCountSheet>> physicalCounts({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? countFrom,
    String? countTo,
  }) =>
      _list(
        '/api/v1/inventory/counts',
        PhysicalCountSheet.fromJson,
        page,
        search,
        pageSize: pageSize,
        additionalQuery: {
          // The Period filter (owner, 2026-09-27): count dates, inclusive.
          if (countFrom != null) 'count_from': countFrom,
          if (countTo != null) 'count_to': countTo,
        },
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

  // Photos and documents kept with a movement or a count sheet (STK-9).

  Future<List<StockAttachmentRecord>> listMovementAttachments(
    String transactionId,
  ) async =>
      _unwrapList(
        await request(
            'GET', '/api/v1/inventory/transactions/$transactionId/attachments'),
        StockAttachmentRecord.fromJson,
      );

  Future<List<StockAttachmentRecord>> attachToMovement(
    String transactionId,
    List<Json> files,
  ) async =>
      _unwrapList(
        await request(
          'POST',
          '/api/v1/inventory/transactions/$transactionId/attachments',
          body: {'attachments': files},
        ),
        StockAttachmentRecord.fromJson,
      );

  Future<List<StockAttachmentRecord>> listCountAttachments(
    String countId,
  ) async =>
      _unwrapList(
        await request('GET', '/api/v1/inventory/counts/$countId/attachments'),
        StockAttachmentRecord.fromJson,
      );

  Future<List<StockAttachmentRecord>> attachToCount(
    String countId,
    List<Json> files,
  ) async =>
      _unwrapList(
        await request(
          'POST',
          '/api/v1/inventory/counts/$countId/attachments',
          body: {'attachments': files},
        ),
        StockAttachmentRecord.fromJson,
      );

  Future<void> removeStockAttachment(String id) async {
    await request('DELETE', '/api/v1/inventory/attachments/$id');
  }

  /// The rows of one report.
  ///
  /// Every report endpoint answers with flat rows in the standard envelope, so
  /// one method serves all of them and the difference between reports is a
  /// path. Six of them answered differently until that was corrected; a client
  /// method per report would have hidden that rather than surfaced it.
  ///
  /// `rowsKey` reads the rows out of an endpoint that answers with one object
  /// (the commission report); `query` carries a period where one is required.
  /// One quarter's Form 26Q as a file to prepare the return from (53.1): a
  /// workbook by default, or the deductee rows alone with `format: 'csv'`.
  Future<List<int>> tds26qFile({
    required String financialYear,
    required String quarter,
    String format = 'xlsx',
  }) =>
      downloadBytes(
        '/api/v1/finance/tds-returns/26q',
        query: {
          'financial_year': financialYear,
          'quarter': quarter,
          'format': format,
        },
      );

  Future<ReportPage> reportRows(
    String path, {
    Map<String, String>? query,
    String? rowsKey,
  }) async {
    final Json response = await request('GET', path, query: query);
    final dynamic envelope = response['data'];
    final dynamic data =
        rowsKey != null && envelope is Map ? envelope[rowsKey] : envelope;
    final List<Json> rows = [
      for (final dynamic row in data is List ? data : const [])
        if (row is Map) Map<String, dynamic>.from(row),
    ];
    // A dated report says how many matched in all (D-RPT-18): beside the
    // page in `pagination`, or beside `rows` where the report is one object.
    final dynamic pagination = response['pagination'];
    final dynamic total = pagination is Map
        ? pagination['total_records']
        : envelope is Map
            ? envelope['total_records']
            : null;
    return ReportPage(
      rows: rows,
      total: total is num ? total.toInt() : rows.length,
    );
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

  /// Every category, inactive ones too, as one page for the categories screen.
  ///
  /// The endpoint returns the whole tree unpaged and has no search, so the
  /// search is applied here. `sortBy` and `descending` are accepted because
  /// `ResourceDefinition.load` requires the shape; the tree is ordered by path.
  Future<PagedResult<ProductCategoryRecord>> productCategoryPage({
    int page = 1,
    String search = '',
    String sortBy = 'path',
    bool descending = false,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/products/categories',
      query: const {'include_inactive': 'true'},
    );
    final dynamic data = response['data'];
    final String needle = search.trim().toLowerCase();
    final List<ProductCategoryRecord> rows = (data is List ? data : const [])
        .whereType<Map>()
        .map((item) =>
            ProductCategoryRecord.fromJson(Map<String, dynamic>.from(item)))
        .where((row) =>
            needle.isEmpty ||
            row.code.toLowerCase().contains(needle) ||
            row.name.toLowerCase().contains(needle))
        .toList()
      ..sort((a, b) => a.path.compareTo(b.path));
    return PagedResult(items: rows, total: rows.length);
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

  /// The blank product import file, as bytes: xlsx (with notes and lists) or csv.
  Future<List<int>> productImportTemplate({String format = 'xlsx'}) =>
      downloadBytes(
        '/api/v1/products/import-template',
        query: {'format': format},
      );

  /// Check (`apply: false`, writes nothing) or import a product file.
  Future<FileImportReport> checkProductImportFile({
    required String fileName,
    required List<int> bytes,
    required bool updateExisting,
    required bool apply,
    Map<String, String?>? mapping,
  }) async {
    final Json response = await multipartRequest(
      'POST',
      '/api/v1/products/import-file',
      fields: {
        'existing': updateExisting ? 'update' : 'refuse',
        'apply': apply ? 'true' : 'false',
        if (mapping != null) 'mapping': jsonEncode(mapping),
      },
      fileField: 'file',
      fileName: fileName,
      fileBytes: bytes,
      fileContentType: fileName.toLowerCase().endsWith('.xlsx')
          ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          : 'text/csv',
    );
    return FileImportReport.fromJson(_unwrapMap(response));
  }

  /// The blank customer import file, as bytes: xlsx (with notes and lists) or csv.
  Future<List<int>> customerImportTemplate({String format = 'xlsx'}) =>
      downloadBytes(
        '/api/v1/customers/import-template',
        query: {'format': format},
      );

  /// Check (`apply: false`, writes nothing) or import a customer file.
  Future<FileImportReport> checkCustomerImportFile({
    required String fileName,
    required List<int> bytes,
    required bool updateExisting,
    required bool apply,
    Map<String, String?>? mapping,
  }) async {
    final Json response = await multipartRequest(
      'POST',
      '/api/v1/customers/import-file',
      fields: {
        'existing': updateExisting ? 'update' : 'refuse',
        'apply': apply ? 'true' : 'false',
        if (mapping != null) 'mapping': jsonEncode(mapping),
      },
      fileField: 'file',
      fileName: fileName,
      fileBytes: bytes,
      fileContentType: fileName.toLowerCase().endsWith('.xlsx')
          ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          : 'text/csv',
    );
    return FileImportReport.fromJson(_unwrapMap(response));
  }

  /// The blank vendor import file, as bytes: xlsx (with notes and lists) or csv.
  Future<List<int>> vendorImportTemplate({String format = 'xlsx'}) =>
      downloadBytes(
        '/api/v1/vendors/import-template',
        query: {'format': format},
      );

  /// Check (`apply: false`, writes nothing) or import a vendor file.
  Future<FileImportReport> checkVendorImportFile({
    required String fileName,
    required List<int> bytes,
    required bool updateExisting,
    required bool apply,
    Map<String, String?>? mapping,
  }) async {
    final Json response = await multipartRequest(
      'POST',
      '/api/v1/vendors/import-file',
      fields: {
        'existing': updateExisting ? 'update' : 'refuse',
        'apply': apply ? 'true' : 'false',
        if (mapping != null) 'mapping': jsonEncode(mapping),
      },
      fileField: 'file',
      fileName: fileName,
      fileBytes: bytes,
      fileContentType: fileName.toLowerCase().endsWith('.xlsx')
          ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          : 'text/csv',
    );
    return FileImportReport.fromJson(_unwrapMap(response));
  }

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

  /// The people who belong to this firm.
  ///
  /// Not `/api/v1/users`: that is guarded by `USER_VIEW`, a platform-admin
  /// permission none of the roles that need this list hold. Membership of the
  /// firm is the only gate -- a firm's own directory of names is not a
  /// privilege, and what needs a permission is *acting* on a person. There
  /// were three of these behind three different permissions before
  /// 2026-08-23, and the sales-order form could call none of them.
  Future<List<FirmMember>> firmMembers() async => _unwrapList(
        await request('GET', '/api/v1/firm-members'),
        FirmMember.fromJson,
      );

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

  /// The India Post places pack the server ships with, state by state.
  Future<List<PlacesPackState>> placesPack() async => _unwrapList(
        await request('GET', '/api/v1/sales-territories/geo/places-pack'),
        PlacesPackState.fromJson,
      );

  /// Loads the pack for the named states into this firm's store. Platform
  /// administrator only; may take several seconds.
  Future<List<PlacesPackResult>> loadPlacesPack(List<String> states) async =>
      _unwrapList(
        await request(
          'POST',
          '/api/v1/sales-territories/geo/places-pack/load',
          body: <String, dynamic>{'states': states},
        ),
        PlacesPackResult.fromJson,
      );

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
  /// The name beside a code, and whether the option can be used at all.
  ///
  /// A business feature the codebase has not built yet (`is_implemented`
  /// false) is listed so the roadmap shows, but the server refuses to enable
  /// it; the only way to learn that was to be refused on save (backlog
  /// 31.6), so the picker says it up front.
  static String? _optionDetail(Json json) {
    final String? name = json['code'] != null &&
            json['name'] != null &&
            stringValue(json['name']) != stringValue(json['code'])
        ? stringValue(json['name'])
        : null;
    if (json['is_implemented'] == false) {
      return name == null ? 'not built yet' : '$name (not built yet)';
    }
    return name;
  }

  Future<List<AssignmentOption>> options(String resource) async {
    // The generic list below returns every row a firm holds, active or not --
    // fine for most catalogues, wrong for a licence type: a picker that
    // offers a retired one lets it be assigned to a fresh product or category
    // as though it were still in use. `tradeLicenceTypes()` carries the flag
    // this generic path throws away, so it is filtered here instead.
    if (resource == 'trade-licences/types') {
      final List<TradeLicenceTypeRecord> types = await tradeLicenceTypes();
      return [
        for (final TradeLicenceTypeRecord type in types)
          if (type.isActive)
            AssignmentOption(
              id: type.id,
              label: type.code,
              detail: type.name == type.code ? null : type.name,
            ),
      ];
    }
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
          detail: _optionDetail(json),
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

  /// Record (or, with null, clear) the supplier's e-way bill on a receipt that
  /// is not cancelled, completed ones included (backlog 78 row 6).
  Future<GoodsReceiptRecord> setGoodsReceiptEwayBill(
    String id,
    String? number,
    String? date,
  ) async =>
      GoodsReceiptRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/goods-receipts/$id/eway-bill',
          body: {'eway_bill_number': number, 'eway_bill_date': date},
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

  /// Price an order as saving it would, and save nothing: what the phase 2
  /// order screen shows while its lines are typed. Sent as a create, without
  /// the order's own number, so a saved order is priced without its number
  /// clashing with itself.
  Future<PurchaseOrderPreviewRecord> previewPurchaseOrder(
    PurchaseOrder order,
  ) async =>
      PurchaseOrderPreviewRecord.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/purchases/preview',
            body: order.toCreateJson()
              ..remove('po_number')
              ..['status'] = 'DRAFT',
          ),
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

  /// Stock at or below its reorder level, per warehouse and product, with
  /// what is on order, the supplier last billed and a suggested quantity
  /// (backlog 42.9). Rows carry no id, so pages are read until a short one.
  Future<List<Json>> belowReorderLevel({String? warehouseId}) async {
    final List<Json> rows = <Json>[];
    for (int page = 1; page <= 50; page++) {
      final Json response = await request(
        'GET',
        '/api/v1/purchases/reports/below-reorder',
        query: <String, String>{
          'page': '$page',
          'page_size': '100',
          if (warehouseId != null) 'warehouse_id': warehouseId,
        },
      );
      final dynamic data = response['data'];
      final List<Json> batch = <Json>[
        for (final dynamic row in data is List ? data : const [])
          if (row is Map) Map<String, dynamic>.from(row),
      ];
      rows.addAll(batch);
      if (batch.length < 100) break;
    }
    return rows;
  }

  /// Raise draft purchase orders for the ticked reorder rows: one per
  /// supplier per warehouse, all or none. Each item names `warehouse_id` and
  /// `product_id`, and may override `quantity` and `supplier_id`.
  Future<Json> raiseReorderDrafts(List<Json> items) async => await request(
        'POST',
        '/api/v1/purchases/reorder-drafts',
        body: <String, dynamic>{'items': items},
      );

  /// Approve several purchase orders in one call. Rows are acted on one by
  /// one, so some can be refused while others succeed.
  Future<BulkActionResult> bulkApprovePurchaseOrders(List<BulkRow> rows) =>
      _bulk('/api/v1/purchases/bulk-approve', rows);

  Future<BulkActionResult> bulkCancelPurchaseOrders(
    List<BulkRow> rows,
    String reason,
  ) =>
      _bulk('/api/v1/purchases/bulk-cancel', rows, reason: reason);

  /// Approve several sales orders in one call.
  Future<BulkActionResult> bulkApproveSalesOrders(List<BulkRow> rows) =>
      _bulk('/api/v1/sales-orders/bulk-approve', rows);

  Future<BulkActionResult> bulkCancelSalesOrders(
    List<BulkRow> rows,
    String reason,
  ) =>
      _bulk('/api/v1/sales-orders/bulk-cancel', rows, reason: reason);

  /// Approve or cancel several documents of one kind in one call; rows are
  /// acted on one by one, so some can be refused while others succeed.
  Future<BulkActionResult> bulkApproveSalesInvoices(List<BulkRow> rows) =>
      _bulk('/api/v1/sales-invoices/bulk-approve', rows);

  Future<BulkActionResult> bulkCancelSalesInvoices(
    List<BulkRow> rows,
    String reason,
  ) =>
      _bulk('/api/v1/sales-invoices/bulk-cancel', rows, reason: reason);

  Future<BulkActionResult> bulkApprovePurchaseInvoices(List<BulkRow> rows) =>
      _bulk('/api/v1/purchase-invoices/bulk-approve', rows);

  Future<BulkActionResult> bulkCancelPurchaseInvoices(
    List<BulkRow> rows,
    String reason,
  ) =>
      _bulk('/api/v1/purchase-invoices/bulk-cancel', rows, reason: reason);

  Future<BulkActionResult> bulkApproveDeliveryNotes(List<BulkRow> rows) =>
      _bulk('/api/v1/delivery-notes/bulk-approve', rows);

  Future<BulkActionResult> bulkCancelDeliveryNotes(
    List<BulkRow> rows,
    String reason,
  ) =>
      _bulk('/api/v1/delivery-notes/bulk-cancel', rows, reason: reason);

  /// Record that a dispatched note's goods arrived (backlog 67 row 6): when,
  /// who signed for them, a remark and optionally the signed copy.
  ///
  /// Recording on a DISPATCHED note also completes it; the server refuses a
  /// note in any other state. [deliveredAt] goes as UTC with its offset, and
  /// the attachment as the file's name, type and path -- the server sets its
  /// kind.
  Future<Json> recordDeliveryProof(
    String noteId, {
    required DateTime deliveredAt,
    required String receivedBy,
    String? remarks,
    Json? attachment,
  }) =>
      request(
        'POST',
        '/api/v1/delivery-notes/$noteId/proof-of-delivery',
        body: <String, dynamic>{
          'delivered_at': deliveredAt.toUtc().toIso8601String(),
          'received_by': receivedBy,
          'remarks': remarks,
          'attachment': attachment,
        },
      );

  /// What dispatching this note before it has an invoice would do under the
  /// firm's GST policy (backlog 77.1). A null message means nothing to say.
  Future<DispatchCheck> deliveryNoteDispatchCheck(String noteId) async =>
      DispatchCheck.fromJson(
        _unwrapMap(
          await request(
            'GET',
            '/api/v1/delivery-notes/$noteId/dispatch-check',
          ),
        ),
      );

  /// Dispatch an approved note and raise and approve its invoice in one
  /// transaction. Returns the whole envelope: its `message` names the invoice.
  ///
  /// [batchReason] answers the firm's batch rules where they ask why a
  /// near-expiry batch is left behind (backlog 79 row 6).
  Future<Json> dispatchAndInvoiceDeliveryNote(
    String noteId, {
    String? batchReason,
  }) =>
      request(
        'POST',
        '/api/v1/delivery-notes/$noteId/dispatch-and-invoice',
        body: const <String, dynamic>{},
        query: batchReason == null ? null : {'batch_reason': batchReason},
      );

  /// What the firm's batch rules say about dispatching this note: near-expiry
  /// batches left behind, earlier-expiring batches skipped (backlog 79 row 6).
  Future<DispatchBatchCheck> deliveryNoteBatchCheck(String noteId) async =>
      DispatchBatchCheck.fromJson(
        _unwrapMap(
          await request('GET', '/api/v1/delivery-notes/$noteId/batch-check'),
        ),
      );

  /// The firm's rules for selling batches: readable by stock and sales
  /// viewers, writable only with `SALES_MANAGE_SETTINGS`.
  Future<BatchSaleSettings> batchSaleSettings() async =>
      BatchSaleSettings.fromJson(
        _unwrapMap(
          await request('GET', '/api/v1/batch-serial/sale-settings'),
        ),
      );

  Future<BatchSaleSettings> updateBatchSaleSettings(
    BatchSaleSettings settings,
  ) async =>
      BatchSaleSettings.fromJson(
        _unwrapMap(
          await request(
            'PUT',
            '/api/v1/batch-serial/sale-settings',
            body: settings.toJson(),
          ),
        ),
      );

  /// The firm's GST document policy (backlog 77.1): readable with `TAX_VIEW`,
  /// writable only with `TAX_MANAGE_SETTINGS`.
  Future<GstComplianceSettings> gstComplianceSettings() async =>
      GstComplianceSettings.fromJson(
        _unwrapMap(
          await request(
            'GET',
            '/api/v1/tax-framework/gst-compliance-settings',
          ),
        ),
      );

  Future<GstComplianceSettings> updateGstComplianceSettings(
    GstComplianceSettings settings,
  ) async =>
      GstComplianceSettings.fromJson(
        _unwrapMap(
          await request(
            'PUT',
            '/api/v1/tax-framework/gst-compliance-settings',
            body: settings.toJson(),
          ),
        ),
      );

  Future<BulkActionResult> bulkApproveCreditNotes(List<BulkRow> rows) =>
      _bulk('/api/v1/credit-notes/bulk-approve', rows);

  Future<BulkActionResult> bulkApproveCustomerDebitNotes(List<BulkRow> rows) =>
      _bulk('/api/v1/customer-debit-notes/bulk-approve', rows);

  Future<BulkActionResult> bulkApproveSalesReturns(List<BulkRow> rows) =>
      _bulk('/api/v1/sales-returns/bulk-approve', rows);

  Future<BulkActionResult> bulkCancelSalesReturns(
    List<BulkRow> rows,
    String reason,
  ) =>
      _bulk('/api/v1/sales-returns/bulk-cancel', rows, reason: reason);

  Future<BulkActionResult> bulkApprovePurchaseReturns(List<BulkRow> rows) =>
      _bulk('/api/v1/purchase-returns/bulk-approve', rows);

  Future<BulkActionResult> bulkCancelPurchaseReturns(
    List<BulkRow> rows,
    String reason,
  ) =>
      _bulk('/api/v1/purchase-returns/bulk-cancel', rows, reason: reason);

  Future<BulkActionResult> bulkPostJournalEntries(List<BulkRow> rows) =>
      _bulk('/api/v1/finance/journal-entries/bulk-post', rows);

  /// `version` is left out when unknown: the server rejects unknown fields but
  /// accepts an item without one.
  Future<BulkActionResult> _bulk(
    String path,
    List<BulkRow> rows, {
    String? reason,
  }) async =>
      BulkActionResult.fromJson(_unwrapMap(await request(
        'POST',
        path,
        body: <String, dynamic>{
          'items': [
            for (final BulkRow row in rows)
              <String, dynamic>{
                'id': row.id,
                if (row.version != null) 'version': row.version,
              },
          ],
          if (reason != null) 'reason': reason,
        },
      )));

  /// Record that an approved order reached the supplier, and how: EMAIL,
  /// PRINT, WHATSAPP or OTHER (backlog 69 row 6).
  Future<PurchaseOrder> markPurchaseOrderSent(String id, String via) async =>
      PurchaseOrder.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/purchases/$id/mark-sent',
            body: {'via': via},
          ),
        ),
      );

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

  /// Close a financial year: nothing can be posted into it afterwards. The
  /// server refuses while a period is open or a draft journal is dated in it.
  Future<FinancialYear> closeFinancialYear(String id) async =>
      FinancialYear.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/finance/financial-years/$id/close'),
        ),
      );

  /// Reopen a closed year. The periods inside it stay closed.
  Future<FinancialYear> reopenFinancialYear(String id, String reason) async =>
      FinancialYear.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/finance/financial-years/$id/reopen',
            body: {'reason': reason},
          ),
        ),
      );

  /// Delete a period nothing was written into (D-FIN-15).
  Future<void> deleteAccountingPeriod(String id) =>
      request('DELETE', '/api/v1/finance/accounting-periods/$id');

  /// What is unfinished in a period before it is closed (ACC-5): `items`,
  /// each with `label`, `count`, `blocks` and `examples`, and `refuses`
  /// when the firm's policy would refuse the close.
  Future<Json> periodCloseChecks(String id) async => _unwrapMap(
        await request(
          'GET',
          '/api/v1/finance/accounting-periods/$id/close-checks',
        ),
      );

  /// The firm's policy on closing a month with work left: WARN or BLOCK.
  Future<String> periodCloseSetting() async => stringValue(
        _unwrapMap(
          await request('GET', '/api/v1/finance/period-close-settings'),
        )['close_check'],
      );

  Future<String> setPeriodCloseSetting(String value) async => stringValue(
        _unwrapMap(
          await request(
            'PUT',
            '/api/v1/finance/period-close-settings',
            body: {'close_check': value},
          ),
        )['close_check'],
      );

  /// The firm's ageing columns (ACC-6): `bucket_days`, the boundaries, and
  /// `bands`, each with `from_days`, `to_days` and `label`.
  Future<Json> ageingSettings() async => _unwrapMap(
        await request('GET', '/api/v1/finance/ageing-settings'),
      );

  Future<Json> updateAgeingSettings(List<int> bucketDays) async => _unwrapMap(
        await request(
          'PUT',
          '/api/v1/finance/ageing-settings',
          body: {'bucket_days': bucketDays},
        ),
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

  /// A firm's own numbering series, which it administers itself.
  ///
  /// These need `SETTINGS_UPDATE`, seeded to `FIRM_ADMIN` alone. They used to
  /// need platform admin, so a firm could not change the prefix on its own
  /// invoice series -- what a firm calls its documents is its business, where
  /// the lifecycle those documents move through stays the platform's.
  Future<NumberingRule> createNumberingRule(Json body) async =>
      NumberingRule.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/document-framework/numbering-rules',
            body: body,
          ),
        ),
      );

  Future<NumberingRule> updateNumberingRule(String id, Json body) async =>
      NumberingRule.fromJson(
        _unwrapMap(
          await request(
            'PUT',
            '/api/v1/document-framework/numbering-rules/$id',
            body: body,
          ),
        ),
      );

  Future<void> deleteNumberingRule(String id) =>
      request('DELETE', '/api/v1/document-framework/numbering-rules/$id');

  /// The document types a numbering series can be attached to.
  Future<List<DocumentTypeRecord>> documentTypes() async => _unwrapList(
        await request(
          'GET',
          '/api/v1/document-framework/document-types?page_size=100',
        ),
        DocumentTypeRecord.fromJson,
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
    String? quotationFrom,
    String? quotationTo,
  }) =>
      _list(
        '/api/v1/quotations',
        Quotation.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: 'quotation_date',
        additionalQuery: {
          if (status != null) 'status': status,
          if (quotationFrom != null) 'quotation_from': quotationFrom,
          if (quotationTo != null) 'quotation_to': quotationTo,
        },
      );

  Future<Quotation> quotation(String id) async => Quotation.fromJson(
        _unwrapMap(await request('GET', '/api/v1/quotations/$id')),
      );

  /// Price an order as saving it would, and save nothing: what the order
  /// screen shows while its lines are typed.
  Future<SalesOrderPreviewRecord> previewSalesOrder(Json data) async =>
      SalesOrderPreviewRecord.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/sales-orders/preview', body: data),
        ),
      );

  /// Price an invoice as saving it would, and save nothing: what the
  /// invoice screen shows while its lines are typed.
  Future<SalesInvoicePreviewRecord> previewSalesInvoice(Json data) async =>
      SalesInvoicePreviewRecord.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/sales-invoices/preview', body: data),
        ),
      );

  /// Price an offer as saving it would, and save nothing: what the
  /// new-quotation screen shows while its lines are typed.
  Future<QuotationPreviewRecord> previewQuotation(Json data) async =>
      QuotationPreviewRecord.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/quotations/preview', body: data),
        ),
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
    String? returnFrom,
    String? returnTo,
  }) =>
      _list(
        '/api/v1/sales-returns',
        SalesReturn.fromJson,
        page,
        search,
        pageSize: pageSize,
        sortBy: 'return_date',
        additionalQuery: {
          if (status != null) 'status': status,
          if (returnFrom != null) 'return_from': returnFrom,
          if (returnTo != null) 'return_to': returnTo,
        },
      );

  Future<SalesReturn> salesReturn(String id) async => SalesReturn.fromJson(
        _unwrapMap(await request('GET', '/api/v1/sales-returns/$id')),
      );

  /// Price a sales return as saving it would, and save nothing: the credit
  /// the phase 2 return screen shows while its lines are typed.
  Future<SalesReturnPreviewRecord> previewSalesReturn(Json data) async =>
      SalesReturnPreviewRecord.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/sales-returns/preview', body: data),
        ),
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

  /// The serialised units a return line against one source line may name:
  /// those sold on it and still out with the customer. A product nobody
  /// tracks by serial answers `serialTracked: false` (D-STK-4).
  Future<ReturnableSerials> returnableSerials({
    required String sourceType,
    required String sourceLineId,
  }) async =>
      ReturnableSerials.fromJson(
        _unwrapMap(
          await request(
            'GET',
            '/api/v1/sales-returns/returnable-serials',
            query: {
              'source_document_type': sourceType,
              'source_document_line_id': sourceLineId,
            },
          ),
        ),
      );

  /// The largest page any list endpoint serves -- `MAX_PAGE_SIZE` on the
  /// server, `maxApiPageSize` beside `fetchAllPages`.
  static const int _pageCap = 100;

  /// A backstop on reading every page, so a server (or a fake) that keeps
  /// answering can never spin the client for ever.
  static const int _pageBackstop = 50;

  /// Read every page of a list endpoint, in its own order.
  ///
  /// Stops at the reported total, at an empty page, or at a page that adds
  /// nothing new -- whichever comes first.
  Future<List<Json>> _everyRow(String path, Map<String, String> query) async {
    final List<Json> rows = <Json>[];
    final Set<String> seen = <String>{};
    for (int page = 1; page <= _pageBackstop; page++) {
      final Json response = await request('GET', path, query: {
        ...query,
        'page': '$page',
        'page_size': '$_pageCap',
      });
      final dynamic data = response['data'];
      final List<Json> batch = <Json>[
        for (final dynamic row in data is List ? data : const [])
          if (row is Map) Map<String, dynamic>.from(row),
      ];
      final int before = rows.length;
      for (final Json row in batch) {
        if (seen.add(stringValue(row['id']))) rows.add(row);
      }
      final dynamic pagination = response['pagination'];
      final int total = pagination is Map
          ? (pagination['total_records'] as num?)?.toInt() ?? -1
          : -1;
      if (batch.isEmpty || rows.length == before) break;
      if (total >= 0 && rows.length >= total) break;
      // A plain list says nothing of its total, but a short page is the last.
      if (total < 0 && batch.length < _pageCap) break;
    }
    return rows;
  }

  /// The documents a return can be raised against: every dispatched delivery
  /// note and every approved or closed invoice, however old.
  ///
  /// Delivery notes and sales invoices are read together and flattened, so the
  /// editor offers one list rather than making somebody decide which kind of
  /// paperwork they are holding before they can find it. A failure on either
  /// side yields that side's documents only -- half a picker still lets a
  /// return be raised.
  ///
  /// This read the newest 50 of each kind in any status, so an older note or
  /// bill could not be returned against from the desktop at all, and a draft
  /// or cancelled one was offered and then refused (D-SELL-18). Only goods
  /// that left can come back, so a closed note is offered only if it was
  /// dispatched first -- the same test the server applies.
  Future<List<ReturnableDocument>> returnableDocuments() async {
    final List<List<ReturnableDocument>> parts = await Future.wait([
      for (final String status in const <String>[
        'DISPATCHED',
        'COMPLETED',
        'CLOSED',
      ])
        _returnable(
          '/api/v1/delivery-notes',
          status,
          ReturnableDocument.fromDeliveryNote,
          keep: (Json row) =>
              status != 'CLOSED' ||
              stringValue(row['dispatched_at']).isNotEmpty,
        ),
      for (final String status in const <String>['APPROVED', 'CLOSED'])
        _returnable(
          '/api/v1/sales-invoices',
          status,
          ReturnableDocument.fromSalesInvoice,
        ),
    ]);
    // Once each, whatever a list answered: a document appears in one status.
    final Set<String> seen = <String>{};
    return [
      for (final List<ReturnableDocument> part in parts)
        for (final ReturnableDocument document in part)
          if (seen.add('${document.sourceType.name}:${document.id}')) document,
    ];
  }

  Future<List<ReturnableDocument>> _returnable(
    String path,
    String status,
    ReturnableDocument Function(Json) parser, {
    bool Function(Json row)? keep,
  }) async {
    try {
      final List<Json> rows = await _everyRow(path, {
        'status': status,
        'sort_by': 'created_at',
        'sort_direction': 'desc',
      });
      return [
        for (final Json row in rows)
          // The status asked for, checked on the row as well: the picker must
          // never offer a draft or a cancelled document, whatever answered.
          if ((row['status'] == null || stringValue(row['status']) == status) &&
              (keep == null || keep(row)))
            parser(row),
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
  /// Run one lifecycle action -- approve, dispatch, cancel, close -- on a
  /// document.
  ///
  /// Always sends a JSON object. Cancel and close on sales orders, sales
  /// invoices, delivery notes, purchase invoices and purchase returns declare
  /// a body carrying an optional reason, so a request with no body at all was
  /// refused with 422 "body: Field required" and those buttons had never
  /// worked from the desktop (plan item 9.9, 2026-09-13). An action that takes
  /// no body ignores the empty object.
  ///
  /// [query] carries a query-string parameter a lifecycle action takes beside
  /// its (always empty) body -- `licence_override_reason` on the sales
  /// approve endpoints (backlog 54) and `price_override_reason` (backlog 64)
  /// are the examples today.
  Future<Json> documentAction(
    String resource,
    String id,
    String action, {
    Map<String, String>? query,
  }) =>
      request(
        'POST',
        '/api/v1/$resource/$id/${action.startsWith('/') ? action.substring(1) : action}',
        body: const <String, dynamic>{},
        query: query,
      );

  /// Price a supplier bill as saving it would, and save nothing: what the
  /// phase 2 bill screen shows while its lines are typed.
  Future<PurchaseInvoicePreviewRecord> previewPurchaseInvoice(
    Json data,
  ) async =>
      PurchaseInvoicePreviewRecord.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/purchase-invoices/preview',
              body: data),
        ),
      );

  /// Price a return to the supplier as saving it would, and save nothing:
  /// what the phase 2 return screen shows while its lines are typed.
  Future<PurchaseReturnPreviewRecord> previewPurchaseReturn(
    Json data,
  ) async =>
      PurchaseReturnPreviewRecord.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/purchase-returns/preview', body: data),
        ),
      );

  /// Raise a supplier bill against a completed goods receipt.
  ///
  /// Named rather than reached through the generic `create`, because the
  /// generic helpers are how this route read as called for a year while no
  /// screen could reach it (BL-31.9): the orphan-route guard matches the
  /// literal `'purchase-invoices'` in `documentPage` and stops looking.
  Future<Json> createPurchaseInvoice(Json body) =>
      request('POST', '/api/v1/purchase-invoices', body: body);

  /// Record (or, with null, clear) the supplier's IRN on a bill that is not
  /// cancelled -- the way to put it on an approved bill, whose editor is
  /// read-only (backlog 78 row 5).
  Future<Json> setPurchaseInvoiceSupplierIrn(String id, String? irn) =>
      request('PUT', '/api/v1/purchase-invoices/$id/supplier-irn',
          body: {'supplier_irn': irn});

  // ---- price lists ---------------------------------------------------

  Future<PagedResult<PriceListRecord>> priceLists({
    int page = 1,
    int pageSize = 20,
    String search = '',
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/price-lists',
      query: {
        'page': '$page',
        'page_size': '$pageSize',
        if (search.trim().isNotEmpty) 'search': search.trim(),
      },
    );
    final dynamic data = response['data'];
    return PagedResult<PriceListRecord>(
      items: data is List
          ? data
              .whereType<Map>()
              .map((item) =>
                  PriceListRecord.fromJson(Map<String, dynamic>.from(item)))
              .toList()
          : const [],
      total: _totalOf(response),
    );
  }

  Future<PriceListRecord> createPriceList(Json body) async =>
      PriceListRecord.fromJson(
        _unwrapMap(await request('POST', '/api/v1/price-lists', body: body)),
      );

  /// [expectedVersion] rides along as `If-Match`. The rates are replaced by
  /// what is sent, so a lost race costs every rate somebody entered.
  Future<PriceListRecord> updatePriceList(
    String id,
    Json body, {
    int? expectedVersion,
  }) async =>
      PriceListRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/price-lists/$id',
          body: body,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deletePriceList(String id) =>
      request('DELETE', '/api/v1/price-lists/$id');

  // ---- price levels ----------------------------------------------------
  // Created, updated and deleted through the generic `create`/`update`/
  // `delete` helpers, whose `resource` on the definition is `price-levels`.

  Future<List<PriceLevelRecord>> priceLevels() async {
    final Json response = await request('GET', '/api/v1/price-levels');
    final dynamic data = response['data'];
    return <PriceLevelRecord>[
      if (data is List)
        for (final dynamic row in data)
          if (row is Map)
            PriceLevelRecord.fromJson(Map<String, dynamic>.from(row)),
    ];
  }

  /// One product's rate at each level it has one.
  Future<List<ProductLevelRate>> productLevelRates(String productId) async {
    final Json response =
        await request('GET', '/api/v1/price-levels/products/$productId');
    final dynamic data = response['data'];
    return <ProductLevelRate>[
      if (data is List)
        for (final dynamic row in data)
          if (row is Map)
            ProductLevelRate.fromJson(Map<String, dynamic>.from(row)),
    ];
  }

  /// Replaces the whole list of a product's level rates.
  Future<void> saveProductLevelRates(
    String productId,
    List<Map<String, dynamic>> rates,
  ) =>
      request(
        'PUT',
        '/api/v1/price-levels/products/$productId',
        body: {'rates': rates},
      );

  /// What the server would charge for each of [productIds], and from which
  /// arrangement. Keyed by product id.
  Future<Map<String, UnitPriceQuote>> unitPrices({
    required List<String> productIds,
    required String on,
    String customerId = '',
    String territoryId = '',
  }) async {
    // `product_ids` repeats once per product, which a `Map<String, String>`
    // query cannot say, so the query string is built here and rides on the path.
    final String queryString = Uri(queryParameters: <String, dynamic>{
      'product_ids': productIds,
      'on': on,
      if (customerId.isNotEmpty) 'customer_id': customerId,
      if (territoryId.isNotEmpty) 'territory_id': territoryId,
    }).query;
    final Json response = await request(
      'GET',
      '/api/v1/price-levels/unit-prices?$queryString',
    );
    final dynamic data = response['data'];
    final dynamic prices = data is Map ? data['prices'] : null;
    return <String, UnitPriceQuote>{
      if (prices is List)
        for (final dynamic row in prices)
          if (row is Map)
            stringValue(row['product_id']):
                UnitPriceQuote.fromJson(Map<String, dynamic>.from(row)),
    };
  }

  // ---- promotions ----------------------------------------------------

  Future<PagedResult<PromotionRecord>> promotions({
    int page = 1,
    int pageSize = 20,
    String search = '',
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/promotions',
      query: {
        'page': '$page',
        'page_size': '$pageSize',
        if (search.trim().isNotEmpty) 'search': search.trim(),
      },
    );
    final dynamic data = response['data'];
    return PagedResult<PromotionRecord>(
      items: data is List
          ? data
              .whereType<Map>()
              .map((item) =>
                  PromotionRecord.fromJson(Map<String, dynamic>.from(item)))
              .toList()
          : const [],
      total: _totalOf(response),
    );
  }

  Future<PromotionRecord> createPromotion(Json body) async =>
      PromotionRecord.fromJson(
        _unwrapMap(await request('POST', '/api/v1/promotions', body: body)),
      );

  /// [expectedVersion] rides along as `If-Match`. A live promotion is
  /// superseded rather than edited, so the answer may be a new revision.
  Future<PromotionRecord> updatePromotion(
    String id,
    Json body, {
    int? expectedVersion,
  }) async =>
      PromotionRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/promotions/$id',
          body: body,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deletePromotion(String id) =>
      request('DELETE', '/api/v1/promotions/$id');

  /// Copy offers as drafts with a new window and a suffix on each code
  /// (SEL-8); returns the copies.
  Future<List<PromotionRecord>> copyPromotions(
    List<String> ids, {
    required DateTime effectiveFrom,
    required DateTime effectiveTo,
    required String codeSuffix,
  }) async {
    String day(DateTime date) => date.toIso8601String().substring(0, 10);
    final Json response = await request(
      'POST',
      '/api/v1/promotions/copy',
      body: <String, dynamic>{
        'promotion_ids': ids,
        'effective_from': day(effectiveFrom),
        'effective_to': day(effectiveTo),
        'code_suffix': codeSuffix,
      },
    );
    final dynamic data = response['data'];
    return data is List
        ? data
            .whereType<Map>()
            .map((item) =>
                PromotionRecord.fromJson(Map<String, dynamic>.from(item)))
            .toList()
        : <PromotionRecord>[];
  }

  Future<PagedResult<PromotionCouponRecord>> promotionCoupons({
    int page = 1,
    int pageSize = 20,
    String search = '',
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/promotions/coupons',
      query: {
        'page': '$page',
        'page_size': '$pageSize',
        if (search.trim().isNotEmpty) 'search': search.trim(),
      },
    );
    final dynamic data = response['data'];
    return PagedResult<PromotionCouponRecord>(
      items: data is List
          ? data
              .whereType<Map>()
              .map((item) => PromotionCouponRecord.fromJson(
                  Map<String, dynamic>.from(item)))
              .toList()
          : const [],
      total: _totalOf(response),
    );
  }

  Future<PromotionCouponRecord> createPromotionCoupon(Json body) async =>
      PromotionCouponRecord.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/promotions/coupons', body: body),
        ),
      );

  /// The code itself is fixed once minted -- it is on a leaflet somebody is
  /// holding -- so only the limits, the window and the status may change.
  Future<PromotionCouponRecord> updatePromotionCoupon(
    String id,
    Json body, {
    int? expectedVersion,
  }) async =>
      PromotionCouponRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/promotions/coupons/$id',
          body: body,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deletePromotionCoupon(String id) =>
      request('DELETE', '/api/v1/promotions/coupons/$id');

  /// Mint [count] single-use codes for one offer (SEL-5); returns the codes.
  /// Blank [prefix], [description] and dates are left out.
  Future<List<String>> generateCoupons(
    String promotionId, {
    required int count,
    String prefix = '',
    String description = '',
    String effectiveFrom = '',
    String effectiveTo = '',
  }) async {
    final Json data = _unwrapMap(
      await request(
        'POST',
        '/api/v1/promotions/$promotionId/coupons/generate',
        body: <String, dynamic>{
          'count': count,
          'prefix': prefix,
          if (description.isNotEmpty) 'description': description,
          if (effectiveFrom.isNotEmpty) 'effective_from': effectiveFrom,
          if (effectiveTo.isNotEmpty) 'effective_to': effectiveTo,
        },
      ),
    );
    final Object? codes = data['codes'];
    return codes is List ? codes.map((code) => '$code').toList() : <String>[];
  }

  /// Every code of one offer, as a CSV file.
  Future<List<int>> exportCouponsCsv(String promotionId) =>
      downloadBytes('/api/v1/promotions/$promotionId/coupons/export');

  /// What a document would earn, and why each offer did or did not apply.
  /// Saves and claims nothing.
  Future<PromotionTryResult> simulatePromotions(Json body) async =>
      PromotionTryResult.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/promotions/simulate', body: body)),
      );

  // ---- sales targets --------------------------------------------------

  Future<PagedResult<SalesTargetRecord>> salesTargets({
    int page = 1,
    int pageSize = 50,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/sales-targets',
      query: {'page': '$page', 'page_size': '$pageSize'},
    );
    final dynamic data = response['data'];
    return PagedResult<SalesTargetRecord>(
      items: data is List
          ? data
              .whereType<Map>()
              .map((item) =>
                  SalesTargetRecord.fromJson(Map<String, dynamic>.from(item)))
              .toList()
          : const [],
      total: _totalOf(response),
    );
  }

  /// Every target overlapping the window, against what it took.
  ///
  /// Each is measured over its own period and on its own basis; the window
  /// only chooses which targets are worth reporting.
  Future<List<SalesTargetAchievementRecord>> salesTargetAchievement({
    required String fromDate,
    required String toDate,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/sales-targets/achievement',
      query: {'from_date': fromDate, 'to_date': toDate},
    );
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => SalesTargetAchievementRecord.fromJson(
            Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<SalesTargetRecord> createSalesTarget(Json body) async =>
      SalesTargetRecord.fromJson(
        _unwrapMap(await request('POST', '/api/v1/sales-targets', body: body)),
      );

  Future<SalesTargetRecord> updateSalesTarget(
    String id,
    Json body, {
    int? expectedVersion,
  }) async =>
      SalesTargetRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/sales-targets/$id',
          body: body,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deleteSalesTarget(String id) =>
      request('DELETE', '/api/v1/sales-targets/$id');

  // ---- e-invoice and e-way bill ---------------------------------------

  Future<PagedResult<EInvoiceRegistrationRecord>> einvoiceRegistrations({
    int page = 1,
    int pageSize = 50,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/einvoice/registrations',
      query: {'page': '$page', 'page_size': '$pageSize'},
    );
    final dynamic data = response['data'];
    return PagedResult<EInvoiceRegistrationRecord>(
      items: data is List
          ? data
              .whereType<Map>()
              .map((item) => EInvoiceRegistrationRecord.fromJson(
                  Map<String, dynamic>.from(item)))
              .toList()
          : const [],
      total: _totalOf(response),
    );
  }

  /// What the portal knows about one invoice, or null where it knows nothing.
  Future<EInvoiceRegistrationRecord?> einvoiceRegistration(
      String invoiceId) async {
    final Json response =
        await request('GET', '/api/v1/einvoice/invoices/$invoiceId');
    final dynamic data = response['data'];
    return data is Map
        ? EInvoiceRegistrationRecord.fromJson(Map<String, dynamic>.from(data))
        : null;
  }

  Future<EInvoiceRegistrationRecord> registerEInvoice(String invoiceId) async =>
      EInvoiceRegistrationRecord.fromJson(_unwrapMap(
        await request('POST', '/api/v1/einvoice/invoices/$invoiceId/register'),
      ));

  /// How this firm's e-invoices reach the portal (A42): the chosen provider
  /// and the ones the server offers.
  Future<EInvoiceSettings> einvoiceSettings() async => EInvoiceSettings.fromJson(
        _unwrapMap(await request('GET', '/api/v1/einvoice/settings')),
      );

  Future<EInvoiceSettings> updateEinvoiceSettings(String provider) async =>
      EInvoiceSettings.fromJson(_unwrapMap(await request(
        'PUT',
        '/api/v1/einvoice/settings',
        body: <String, dynamic>{'provider': provider},
      )));

  /// The portal's bulk-upload JSON for [invoiceIds] and the approved credit
  /// and debit notes named; each becomes a registration waiting for its IRN.
  Future<List<int>> exportOfflineEinvoices(
    List<String> invoiceIds, {
    List<String> creditNoteIds = const [],
    List<String> debitNoteIds = const [],
    List<String> salesReturnIds = const [],
  }) =>
      downloadBytes(
        '/api/v1/einvoice/offline/export',
        method: 'POST',
        body: <String, dynamic>{
          'invoice_ids': invoiceIds,
          if (creditNoteIds.isNotEmpty) 'credit_note_ids': creditNoteIds,
          if (debitNoteIds.isNotEmpty) 'debit_note_ids': debitNoteIds,
          if (salesReturnIds.isNotEmpty) 'sales_return_ids': salesReturnIds,
        },
      );

  /// A credit note's (`credit-notes`) or customer debit note's
  /// (`debit-notes`) registration, or null where the portal knows nothing.
  Future<EInvoiceRegistrationRecord?> einvoiceNoteRegistration(
      String kind, String noteId) async {
    final Json response =
        await request('GET', '/api/v1/einvoice/$kind/$noteId/registration');
    final dynamic data = response['data'];
    return data is Map
        ? EInvoiceRegistrationRecord.fromJson(Map<String, dynamic>.from(data))
        : null;
  }

  Future<EInvoiceRegistrationRecord> registerEInvoiceNote(
          String kind, String noteId) async =>
      EInvoiceRegistrationRecord.fromJson(_unwrapMap(
        await request('POST', '/api/v1/einvoice/$kind/$noteId/register'),
      ));

  Future<EInvoiceRegistrationRecord> cancelEInvoiceNote(
    String kind,
    String noteId, {
    required String reason,
  }) async =>
      EInvoiceRegistrationRecord.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/einvoice/$kind/$noteId/cancel',
        body: <String, dynamic>{'reason': reason},
      )));

  /// Post the portal's result file (.json, .csv or .xlsx).
  Future<OfflineEInvoiceImport> importOfflineEinvoiceResult({
    required String fileName,
    required List<int> bytes,
  }) async {
    final String lower = fileName.toLowerCase();
    final Json response = await multipartRequest(
      'POST',
      '/api/v1/einvoice/offline/import',
      fields: const <String, String>{},
      fileField: 'file',
      fileName: fileName,
      fileBytes: bytes,
      fileContentType: lower.endsWith('.xlsx')
          ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          : lower.endsWith('.json')
              ? 'application/json'
              : 'text/csv',
    );
    return OfflineEInvoiceImport.fromJson(_unwrapMap(response));
  }

  Future<EInvoiceRegistrationRecord> cancelEInvoice(
    String invoiceId, {
    required String reason,
  }) async =>
      EInvoiceRegistrationRecord.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/einvoice/invoices/$invoiceId/cancel',
        body: <String, dynamic>{'reason': reason},
      )));

  Future<EWayBillRecord?> ewayBill(String invoiceId) async {
    final Json response =
        await request('GET', '/api/v1/einvoice/invoices/$invoiceId/eway-bill');
    final dynamic data = response['data'];
    return data is Map
        ? EWayBillRecord.fromJson(Map<String, dynamic>.from(data))
        : null;
  }

  Future<EWayBillRecord> generateEwayBill(String invoiceId, Json body) async =>
      EWayBillRecord.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/einvoice/invoices/$invoiceId/eway-bill',
        body: body,
      )));

  Future<EWayBillRecord> cancelEwayBill(
    String invoiceId, {
    required String reason,
  }) async =>
      EWayBillRecord.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/einvoice/invoices/$invoiceId/eway-bill/cancel',
        body: <String, dynamic>{'reason': reason},
      )));

  /// A delivery note's e-way bill, or null: only for a note no invoice bills.
  Future<EWayBillRecord?> deliveryNoteEwayBill(String noteId) async {
    final Json response = await request(
        'GET', '/api/v1/einvoice/delivery-notes/$noteId/eway-bill');
    final dynamic data = response['data'];
    return data is Map
        ? EWayBillRecord.fromJson(Map<String, dynamic>.from(data))
        : null;
  }

  Future<EWayBillRecord> generateDeliveryNoteEwayBill(
    String noteId,
    Json body,
  ) async =>
      EWayBillRecord.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/einvoice/delivery-notes/$noteId/eway-bill',
        body: body,
      )));

  Future<EWayBillRecord> cancelDeliveryNoteEwayBill(
    String noteId, {
    required String reason,
  }) async =>
      EWayBillRecord.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/einvoice/delivery-notes/$noteId/eway-bill/cancel',
        body: <String, dynamic>{'reason': reason},
      )));

  /// Record an e-way bill raised by hand on the portal. [body] names one of
  /// `sales_invoice_id` / `delivery_note_id` and the bill's number.
  Future<EWayBillRecord> recordEwayBill(Json body) async =>
      EWayBillRecord.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/einvoice/eway-bills/record',
        body: body,
      )));

  /// Consignments of the last 30 days above the firm's limit with no live
  /// e-way bill.
  Future<EWayBillDueList> ewayBillsDue() async {
    final Json response =
        await request('GET', '/api/v1/einvoice/eway-bills/due');
    final dynamic data = response['data'];
    return data is Map
        ? EWayBillDueList.fromJson(Map<String, dynamic>.from(data))
        : const EWayBillDueList(limit: '', items: <EWayBillDue>[]);
  }

  /// Approved B2B documents with no IRN yet, oldest first, each with its
  /// last day under the 30-day rule (77 row 7).
  Future<EInvoicePendingList> pendingEInvoiceRegistrations() async {
    final Json response =
        await request('GET', '/api/v1/einvoice/pending');
    final dynamic data = response['data'];
    return data is Map
        ? EInvoicePendingList.fromJson(Map<String, dynamic>.from(data))
        : const EInvoicePendingList(
            thirtyDayRuleApplies: false,
            dueSoonDays: 5,
            items: <EInvoicePending>[],
          );
  }

  // ---- tax collected at source ----------------------------------------

  Future<TcsSettings> tcsSettings() async => TcsSettings.fromJson(
      _unwrapMap(await request('GET', '/api/v1/tcs/settings')));

  /// Save the policy. An omitted field is left alone server-side, so only
  /// what the form actually edits is sent.
  Future<TcsSettings> saveTcsSettings(Json body) async =>
      TcsSettings.fromJson(_unwrapMap(
        await request('PUT', '/api/v1/tcs/settings', body: body),
      ));

  Future<PagedResult<TcsCollectionRecord>> tcsCollections({
    int page = 1,
    int pageSize = 50,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/tcs/collections',
      query: {'page': '$page', 'page_size': '$pageSize'},
    );
    final dynamic data = response['data'];
    return PagedResult<TcsCollectionRecord>(
      items: data is List
          ? data
              .whereType<Map>()
              .map((item) =>
                  TcsCollectionRecord.fromJson(Map<String, dynamic>.from(item)))
              .toList()
          : const [],
      total: _totalOf(response),
    );
  }

  // ---- proforma invoices -----------------------------------------------

  Future<PagedResult<ProformaRecord>> proformaInvoices({
    int page = 1,
    int pageSize = 50,
    String? status,
    String? search,
    String? proformaFrom,
    String? proformaTo,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/proforma-invoices',
      query: <String, String>{
        'page': '$page',
        'page_size': '$pageSize',
        if (status != null) 'document_status': status,
        if (search != null && search.isNotEmpty) 'search': search,
        if (proformaFrom != null) 'proforma_from': proformaFrom,
        if (proformaTo != null) 'proforma_to': proformaTo,
      },
    );
    final dynamic data = response['data'];
    return PagedResult<ProformaRecord>(
      items: data is List
          ? data
              .whereType<Map>()
              .map((item) =>
                  ProformaRecord.fromJson(Map<String, dynamic>.from(item)))
              .toList()
          : const [],
      total: _totalOf(response),
    );
  }

  Future<ProformaRecord> createProformaInvoice(Json body) async =>
      ProformaRecord.fromJson(_unwrapMap(
        await request('POST', '/api/v1/proforma-invoices', body: body),
      ));

  Future<ProformaRecord> issueProformaInvoice(String id) async =>
      ProformaRecord.fromJson(_unwrapMap(
        await request('POST', '/api/v1/proforma-invoices/$id/issue'),
      ));

  Future<ProformaRecord> cancelProformaInvoice(
    String id, {
    required String reason,
  }) async =>
      ProformaRecord.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/proforma-invoices/$id/cancel',
        body: <String, dynamic>{'reason': reason},
      )));

  // ---- loyalty ---------------------------------------------------------

  /// What one customer holds, and whether they can spend it.
  ///
  /// `redeemable` is answered by the server, so this screen never offers a
  /// redemption the service would refuse.
  Future<Json> loyaltyBalance(String customerId) async =>
      _unwrapMap(await request('GET', '/api/v1/loyalty/$customerId'));

  Future<Json> loyaltySettings() async =>
      _unwrapMap(await request('GET', '/api/v1/loyalty/settings'));

  /// Change the firm's scheme. Send only what is being changed.
  ///
  /// The server dumps with `exclude_unset`, so an omitted key means *leave it
  /// alone* -- which matters here more than usual, because a full write would
  /// reset a conversion rate the firm had agreed with its customers. An
  /// **explicit null** on `expiry_months` is a real instruction: points do not
  /// expire. Zero would mean they expire the day they are earned, so the two
  /// are not the same value and the caller has to be able to say which.
  Future<Json> updateLoyaltySettings(Json changes) async => _unwrapMap(
        await request('PUT', '/api/v1/loyalty/settings', body: changes),
      );

  Future<List<Json>> loyaltyEntries({String? customerId}) async {
    final Json response = await request(
      'GET',
      '/api/v1/loyalty/entries',
      query: <String, String>{
        'page': '1',
        'page_size': '100',
        if (customerId != null) 'customer_id': customerId,
      },
    );
    final dynamic data = response['data'];
    return data is List
        ? data.whereType<Map>().map(Map<String, dynamic>.from).toList()
        : const <Json>[];
  }

  /// Spend a customer's credit against one of their bills.
  Future<Json> redeemLoyalty({
    required String invoiceId,
    required String points,
  }) async =>
      _unwrapMap(await request(
        'POST',
        '/api/v1/loyalty/redeem',
        body: <String, dynamic>{
          'sales_invoice_id': invoiceId,
          'points': points,
        },
      ));

  /// Correct a customer's balance by hand: signed [points], and why.
  Future<Json> adjustLoyalty({
    required String customerId,
    required String points,
    required String reason,
  }) async =>
      _unwrapMap(await request(
        'POST',
        '/api/v1/loyalty/adjust',
        body: <String, dynamic>{
          'customer_id': customerId,
          'points': points,
          'reason': reason,
        },
      ));

  /// Write off points that have run out of time. Safe to run twice.
  Future<Json> expireLoyalty() async =>
      _unwrapMap(await request('POST', '/api/v1/loyalty/expire'));

  /// What a receipt of this size from this buyer would attract in TCS.
  ///
  /// Answered before the receipt exists, so the figure is known when the
  /// money is asked for rather than discovered after it has been taken.
  Future<Json> tcsPreview({
    required String customerId,
    required String amount,
    required String on,
  }) async =>
      _unwrapMap(await request(
        'GET',
        '/api/v1/tcs/preview',
        query: <String, String>{
          'customer_id': customerId,
          'amount': amount,
          'on': on,
        },
      ));

  /// The firm's 194Q policy: whether it deducts, and the threshold and rates.
  Future<Json> tds194qSettings() async =>
      _unwrapMap(await request('GET', '/api/v1/finance/tds-194q/settings'));

  Future<Json> saveTds194qSettings(Json body) async => _unwrapMap(
        await request('PUT', '/api/v1/finance/tds-194q/settings', body: body),
      );

  /// What this supplier has been bought from this Income-tax year, what is
  /// due under 194Q, what is already deducted, and so what to deduct now.
  Future<Json> tds194qSupplier(String vendorId, {required String on}) async =>
      _unwrapMap(await request(
        'GET',
        '/api/v1/finance/tds-194q/suppliers/$vendorId',
        query: <String, String>{'on': on},
      ));

  // ---- customer statement and ageing -----------------------------------

  /// One customer's account movement over a period.
  Future<Json> customerStatement(
    String customerId, {
    required String fromDate,
    required String toDate,
  }) async =>
      _unwrapMap(await request(
        'GET',
        '/api/v1/customers/$customerId/statement',
        query: {'from_date': fromDate, 'to_date': toDate},
      ));

  /// A customer and the supplier that is the same business, on one page, net
  /// of each other (ACC-11). Refused when no supplier is linked.
  Future<Json> customerCombinedStatement(
    String customerId, {
    required String fromDate,
    required String toDate,
  }) async =>
      _unwrapMap(await request(
        'GET',
        '/api/v1/customers/$customerId/combined-statement',
        query: {'from_date': fromDate, 'to_date': toDate},
      ));

  /// The customer that is the same business as this supplier (ACC-11), as
  /// `{customer_id, code, name}`, or null when there is none.
  Future<Json?> linkedCustomerOfVendor(String vendorId) async {
    final Json response =
        await request('GET', '/api/v1/vendors/$vendorId/linked-customer');
    final dynamic data = response['data'];
    return data is Map ? Map<String, dynamic>.from(data) : null;
  }

  /// What every customer still owes, by how long they have owed it.
  Future<List<Json>> customerAgeing({String? customerId, String? asOf}) async {
    final Json response = await request(
      'GET',
      '/api/v1/customers/ageing',
      query: <String, String>{
        if (customerId != null) 'customer_id': customerId,
        if (asOf != null) 'as_of': asOf,
      },
    );
    final dynamic data = response['data'];
    return data is List
        ? data.whereType<Map>().map(Map<String, dynamic>.from).toList()
        : const <Json>[];
  }

  /// Bills a receipt dated [on] may take an early-payment discount on
  /// (SEL-14). Advice for the cashier, never applied by itself.
  Future<List<Json>> cashDiscountOffers({
    required String customerId,
    required String on,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/receipts/cash-discounts',
      query: <String, String>{'customer_id': customerId, 'on': on},
    );
    final dynamic data = response['data'];
    return data is List
        ? data.whereType<Map>().map(Map<String, dynamic>.from).toList()
        : const <Json>[];
  }

  /// What the customer's overdue bills have accrued in interest as of a date
  /// (SEL-14).
  Future<List<Json>> customerOverdueInterest(
    String customerId, {
    required String asOf,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/customers/$customerId/overdue-interest',
      query: <String, String>{'as_of': asOf},
    );
    final dynamic data = response['data'];
    return data is List
        ? data.whereType<Map>().map(Map<String, dynamic>.from).toList()
        : const <Json>[];
  }

  /// Raises a draft debit note for one bill's overdue interest (SEL-14);
  /// answers `{id, debit_note_number}`.
  Future<Json> raiseOverdueInterestDebitNote(
    String customerId, {
    required String invoiceId,
    required String asOf,
  }) async =>
      _unwrapMap(await request(
        'POST',
        '/api/v1/customers/$customerId/overdue-interest/debit-note',
        body: <String, dynamic>{'invoice_id': invoiceId, 'as_of': asOf},
      ));

  // ---- supplier statement and balance confirmations ------------------

  /// One supplier's account movement over a period. A positive balance is
  /// what the firm owes them; a negative one is an advance with them.
  Future<Json> supplierStatement(
    String vendorId, {
    required String fromDate,
    required String toDate,
  }) async =>
      _unwrapMap(await request(
        'GET',
        '/api/v1/vendors/$vendorId/statement',
        query: {'from_date': fromDate, 'to_date': toDate},
      ));

  /// The letter asking one customer to confirm their balance, as a PDF.
  Future<List<int>> customerBalanceConfirmation(
    String customerId, {
    required String asOf,
  }) =>
      downloadBytes(
        '/api/v1/customers/$customerId/balance-confirmation',
        query: {'as_of': asOf},
      );

  /// The letter asking one supplier to confirm their balance, as a PDF.
  Future<List<int>> supplierBalanceConfirmation(
    String vendorId, {
    required String asOf,
  }) =>
      downloadBytes(
        '/api/v1/vendors/$vendorId/balance-confirmation',
        query: {'as_of': asOf},
      );

  /// One letter per customer with a balance, zipped. The server refuses with
  /// a message when nobody has one.
  Future<List<int>> customerBalanceConfirmations({required String asOf}) =>
      downloadBytes(
        '/api/v1/customers/balance-confirmations',
        query: {'as_of': asOf},
      );

  /// One letter per supplier with a balance, zipped.
  Future<List<int>> supplierBalanceConfirmations({required String asOf}) =>
      downloadBytes(
        '/api/v1/vendors/balance-confirmations',
        query: {'as_of': asOf},
      );

  // ---- sales analysis -------------------------------------------------

  /// Billed sales pivoted by one or two dimensions, net of returns by default.
  Future<SalesAnalysis> salesAnalysis({
    required String rows,
    String? columns,
    required String fromDate,
    required String toDate,
    bool netOfReturns = true,
    Map<String, String> filters = const {},
  }) async =>
      SalesAnalysis.fromJson(_unwrapMap(await request(
        'GET',
        '/api/v1/sales-invoices/reports/analysis',
        query: {
          'rows': rows,
          if (columns != null && columns.isNotEmpty) 'columns': columns,
          'from_date': fromDate,
          'to_date': toDate,
          'net_of_returns': netOfReturns ? 'true' : 'false',
          ...filters,
        },
      )));

  /// The invoices behind one cell of the analysis.
  Future<List<AnalysisInvoice>> salesAnalysisInvoices({
    required String fromDate,
    required String toDate,
    Map<String, String> filters = const {},
  }) async =>
      _unwrapList(
        await request(
          'GET',
          '/api/v1/sales-invoices/reports/analysis/invoices',
          query: {'from_date': fromDate, 'to_date': toDate, ...filters},
        ),
        AnalysisInvoice.fromJson,
      );

  // ---- purchase analysis ----------------------------------------------

  /// Purchases pivoted by one or two dimensions; the same shape as the sales
  /// analysis.
  Future<SalesAnalysis> purchaseAnalysis({
    required String rows,
    String? columns,
    required String fromDate,
    required String toDate,
    bool netOfReturns = true,
    Map<String, String> filters = const {},
  }) async =>
      SalesAnalysis.fromJson(_unwrapMap(await request(
        'GET',
        '/api/v1/purchase-invoices/reports/analysis',
        query: {
          'rows': rows,
          if (columns != null && columns.isNotEmpty) 'columns': columns,
          'from_date': fromDate,
          'to_date': toDate,
          'net_of_returns': netOfReturns ? 'true' : 'false',
          ...filters,
        },
      )));

  /// The bills behind one cell of the purchase analysis.
  Future<List<AnalysisBill>> purchaseAnalysisBills({
    required String fromDate,
    required String toDate,
    Map<String, String> filters = const {},
  }) async =>
      _unwrapList(
        await request(
          'GET',
          '/api/v1/purchase-invoices/reports/analysis/bills',
          query: {'from_date': fromDate, 'to_date': toDate, ...filters},
        ),
        AnalysisBill.fromJson,
      );

  /// One bill's lines charged at a rate other than their receipt's (backlog
  /// 65 row 5): the price variance report, narrowed to the bill, in any
  /// status -- the bill's own screen and the report give one answer.
  Future<List<Json>> purchaseInvoicePriceVariance(String invoiceId) async {
    final Json response = await request(
      'GET',
      '/api/v1/purchase-invoices/reports/price-variance',
      query: <String, String>{
        'purchase_invoice_id': invoiceId,
        'page': '1',
        'page_size': '100',
      },
    );
    final dynamic data = response['data'];
    return data is List
        ? data.whereType<Map>().map(Map<String, dynamic>.from).toList()
        : const <Json>[];
  }

  // ---- GST returns ----------------------------------------------------

  /// Outward supplies for a period, section by section.
  ///
  /// Nothing is stored, so there is no id to hold on to: the answer is built
  /// from the invoices and credit notes on every read.
  Future<Json> gstr1({
    required String fromDate,
    required String toDate,
  }) async =>
      _unwrapMap(await request(
        'GET',
        '/api/v1/gst-returns/gstr1',
        query: {'from_date': fromDate, 'to_date': toDate},
      ));

  // ---- quarterly filers, QRMP (GST-7) ----------------------------------

  /// How the firm files (monthly or quarterly) and its cash ledger balance.
  Future<Json> gstFilingPlan() async =>
      _unwrapMap(await request('GET', '/api/v1/gst-returns/filing-plan'));

  /// The PMT-06 deposits recorded, newest first.
  Future<List<Json>> gstCashDeposits() async {
    final Json response =
        await request('GET', '/api/v1/gst-returns/cash-deposits');
    final dynamic data = response['data'];
    return data is List
        ? data.whereType<Map>().map(Map<String, dynamic>.from).toList()
        : const <Json>[];
  }

  /// What the month's PMT-06 deposit should be, by the chosen method.
  Future<Json> gstCashDepositSuggestion({
    required String returnPeriod,
    String? method,
  }) async =>
      _unwrapMap(await request(
        'GET',
        '/api/v1/gst-returns/cash-deposits/suggestion',
        query: {
          'return_period': returnPeriod,
          if (method != null) 'method': method,
        },
      ));

  /// Record a PMT-06 deposit; posts the bank to cash-ledger journal.
  Future<Json> recordGstCashDeposit(Json data) async => _unwrapMap(
        await request('POST', '/api/v1/gst-returns/cash-deposits', body: data),
      );

  /// Take a PMT-06 deposit back with a mirror journal.
  Future<Json> reverseGstCashDeposit(String id, String reason) async =>
      _unwrapMap(await request(
        'POST',
        '/api/v1/gst-returns/cash-deposits/$id/reverse',
        body: {'reason': reason},
      ));

  /// The optional invoice furnishing facility for a quarter's month 1 or 2.
  Future<Json> gstIff(String returnPeriod) async => _unwrapMap(await request(
        'GET',
        '/api/v1/gst-returns/iff',
        query: {'return_period': returnPeriod},
      ));

  /// A quarter's GSTR-1, named by its last month.
  Future<Json> gstr1Quarterly(String returnPeriod) async =>
      _unwrapMap(await request(
        'GET',
        '/api/v1/gst-returns/gstr1-quarterly',
        query: {'return_period': returnPeriod},
      ));

  /// The outward half of the summary return for the same period.
  Future<Json> gstr3b({
    required String fromDate,
    required String toDate,
  }) async =>
      _unwrapMap(await request(
        'GET',
        '/api/v1/gst-returns/gstr3b',
        query: {'from_date': fromDate, 'to_date': toDate},
      ));

  // ---- GSTR-2B matching (backlog 78 row 3) -----------------------------

  /// Read a GSTR-2B file the portal produced; re-importing a month replaces it.
  Future<Json> importGstr2b({
    required String returnPeriod,
    required String content,
    String? sourceName,
  }) async =>
      _unwrapMap(await request(
        'POST',
        '/api/v1/gst-returns/gstr2b/imports',
        body: {
          'return_period': returnPeriod,
          'content': content,
          'source_name': sourceName,
        },
      ));

  /// The month's 2B documents against the supplier bills, and the bills 2B
  /// lacks.
  Future<Json> gstr2bReconciliation(String returnPeriod) async =>
      _unwrapMap(await request(
        'GET',
        '/api/v1/gst-returns/gstr2b/reconciliation',
        query: {'return_period': returnPeriod},
      ));

  /// Match one 2B invoice row to a bill by hand, or undo it with null.
  Future<Json> matchGstr2bDocument(
    String documentId,
    String? purchaseInvoiceId,
  ) async =>
      _unwrapMap(await request(
        'POST',
        '/api/v1/gst-returns/gstr2b/documents/$documentId/match',
        body: {'purchase_invoice_id': purchaseInvoiceId},
      ));

  // ---- GST checks before filing (GST-5) ----------------------------------

  /// What would be wrong in a return for the window (at most three months).
  Future<Json> getGstFilingChecks({
    required DateTime from,
    required DateTime to,
  }) async {
    String iso(DateTime v) => '${v.year.toString().padLeft(4, '0')}-'
        '${v.month.toString().padLeft(2, '0')}-'
        '${v.day.toString().padLeft(2, '0')}';
    return _unwrapMap(await request(
      'GET',
      '/api/v1/gst-returns/checks',
      query: {'from_date': iso(from), 'to_date': iso(to)},
    ));
  }

  // ---- rule 37: bills unpaid 180 days (backlog 78 row 4) ---------------

  /// Credit to reverse on bills unpaid 180 days after their date, and to
  /// reclaim as they are paid, as of [asOf] (YYYY-MM-DD).
  Future<Json> rule37(String asOf) async => _unwrapMap(await request(
        'GET',
        '/api/v1/gst-returns/rule37',
        query: {'as_of': asOf},
      ));

  /// Post the reversals and reclaims; the server refuses unless the firm's
  /// mode is POST. Null [purchaseInvoiceIds] posts every row.
  Future<Json> postRule37(String asOf, {List<String>? purchaseInvoiceIds}) async =>
      _unwrapMap(await request(
        'POST',
        '/api/v1/gst-returns/rule37/post',
        body: {
          'as_of': asOf,
          if (purchaseInvoiceIds != null)
            'purchase_invoice_ids': purchaseInvoiceIds,
        },
      ));

  // ---- rule 42: common credit for exempt sales (GST-4) -----------------

  /// The month's exempt share and the common credit it takes back.
  Future<Json> rule42Period(String returnPeriod) async =>
      _unwrapMap(await request(
        'GET',
        '/api/v1/gst-returns/rule42',
        query: {'return_period': returnPeriod},
      ));

  /// Post the month's reversal; [postingDate] (YYYY-MM-DD) defaults to the
  /// period's last day on the server.
  Future<Json> postRule42Period(
    String returnPeriod, {
    String? postingDate,
  }) async =>
      _unwrapMap(await request(
        'POST',
        '/api/v1/gst-returns/rule42',
        body: {
          'return_period': returnPeriod,
          if (postingDate != null) 'posting_date': postingDate,
        },
      ));

  /// The year's true-up against what the months already gave back.
  Future<Json> rule42Annual(String financialYear) async =>
      _unwrapMap(await request(
        'GET',
        '/api/v1/gst-returns/rule42/annual',
        query: {'financial_year': financialYear},
      ));

  /// Post the annual true-up on [postingDate] (YYYY-MM-DD).
  Future<Json> postRule42Annual(
    String financialYear,
    String postingDate,
  ) async =>
      _unwrapMap(await request(
        'POST',
        '/api/v1/gst-returns/rule42/annual',
        body: {'financial_year': financialYear, 'posting_date': postingDate},
      ));

  /// Every rule 42 reversal posted.
  Future<List<Json>> rule42Posted() async => _unwrapList(
        await request('GET', '/api/v1/gst-returns/rule42/posted'),
        (Json row) => row,
      );

  /// Take a posted rule 42 reversal back, with the reason the trail keeps.
  Future<Json> reverseRule42(String id, String reason) async =>
      _unwrapMap(await request(
        'POST',
        '/api/v1/gst-returns/rule42/$id/reverse',
        body: {'reason': reason},
      ));

  // ---- paying the tax (backlog 63) -------------------------------------

  /// A month's set-off and cash payable, by the statutory order; writes
  /// nothing. [openingCredit] is the first month's credit brought forward,
  /// keyed igst/cgst/sgst/cess.
  Future<GstPaymentPreview> gstPaymentPreview({
    required String returnPeriod,
    String? paymentDate,
    Map<String, String> openingCredit = const {},
  }) async =>
      GstPaymentPreview.fromJson(await request(
        'GET',
        '/api/v1/gst-returns/payments/preview',
        query: {
          'return_period': returnPeriod,
          if (paymentDate != null) 'payment_date': paymentDate,
          for (final MapEntry<String, String> entry in openingCredit.entries)
            if (entry.value.trim().isNotEmpty)
              'opening_credit_${entry.key}': entry.value.trim(),
        },
      ));

  /// Every month recorded as settled, newest first.
  Future<List<GstPaymentRecord>> gstPayments() async => _unwrapList(
        await request('GET', '/api/v1/gst-returns/payments'),
        GstPaymentRecord.fromJson,
      );

  /// Record a month's challan; posts the set-off and the cash in one journal.
  Future<GstPaymentRecord> recordGstPayment(Json data) async =>
      GstPaymentRecord.fromJson(await request(
        'POST',
        '/api/v1/gst-returns/payments',
        body: data,
      ));

  /// Take back the latest month's settlement.
  Future<GstPaymentRecord> reverseGstPayment(String id, String reason) async =>
      GstPaymentRecord.fromJson(await request(
        'POST',
        '/api/v1/gst-returns/payments/$id/reverse',
        body: {'reason': reason},
      ));

  /// The tax calendar (backlog 63 item 4): what each return and deposit owes,
  /// when, and whether it is done -- latest month first.
  Future<List<Json>> gstTaxCalendar() async {
    final Json response =
        await request('GET', '/api/v1/gst-returns/calendar');
    final dynamic data = response['data'];
    return data is List
        ? data.whereType<Map>().map(Map<String, dynamic>.from).toList()
        : const <Json>[];
  }

  /// Record that a month's GSTR-1 or GSTR-3B was filed on the portal.
  Future<Json> markGstReturnFiled(Json data) async => _unwrapMap(
        await request('POST', '/api/v1/gst-returns/filings', body: data),
      );

  /// Withdraw a filing recorded in error.
  Future<void> withdrawGstReturnFiling(String id) =>
      request('DELETE', '/api/v1/gst-returns/filings/$id');

  // ---- credit notes ---------------------------------------------------

  Future<PagedResult<CreditNoteRecord>> creditNotes({
    int page = 1,
    int pageSize = 50,
    String? status,
    String? search,
    String? creditNoteFrom,
    String? creditNoteTo,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/credit-notes',
      query: {
        'page': '$page',
        'page_size': '$pageSize',
        if (status != null && status.isNotEmpty) 'status': status,
        if (search != null && search.isNotEmpty) 'search': search,
        if (creditNoteFrom != null) 'credit_note_from': creditNoteFrom,
        if (creditNoteTo != null) 'credit_note_to': creditNoteTo,
      },
    );
    final dynamic data = response['data'];
    return PagedResult<CreditNoteRecord>(
      items: data is List
          ? data
              .whereType<Map>()
              .map((item) =>
                  CreditNoteRecord.fromJson(Map<String, dynamic>.from(item)))
              .toList()
          : const [],
      total: _totalOf(response),
    );
  }

  /// Price a credit note as raising it would, and save nothing: the tax the
  /// phase 2 screen shows coming off while the amounts are typed.
  Future<CreditNoteRecord> previewCreditNote(Json body) async =>
      CreditNoteRecord.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/credit-notes/preview', body: body),
        ),
      );

  Future<CreditNoteRecord> createCreditNote(Json body) async =>
      CreditNoteRecord.fromJson(
        _unwrapMap(await request('POST', '/api/v1/credit-notes', body: body)),
      );

  Future<CreditNoteRecord> approveCreditNote(
    String id, {
    int? expectedVersion,
  }) async =>
      CreditNoteRecord.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/credit-notes/$id/approve',
        expectedVersion: expectedVersion,
      )));

  Future<CreditNoteRecord> cancelCreditNote(
    String id, {
    int? expectedVersion,
  }) async =>
      CreditNoteRecord.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/credit-notes/$id/cancel',
        expectedVersion: expectedVersion,
      )));

  // ---- customer debit notes -------------------------------------------

  Future<PagedResult<CustomerDebitNoteRecord>> customerDebitNotes({
    int page = 1,
    int pageSize = 50,
    String? status,
    String? search,
    String? customerId,
    String? salesInvoiceId,
    String? debitNoteFrom,
    String? debitNoteTo,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/customer-debit-notes',
      query: {
        'page': '$page',
        'page_size': '$pageSize',
        if (status != null && status.isNotEmpty) 'status': status,
        if (search != null && search.isNotEmpty) 'search': search,
        if (customerId != null && customerId.isNotEmpty)
          'customer_id': customerId,
        if (salesInvoiceId != null && salesInvoiceId.isNotEmpty)
          'sales_invoice_id': salesInvoiceId,
        if (debitNoteFrom != null) 'debit_note_from': debitNoteFrom,
        if (debitNoteTo != null) 'debit_note_to': debitNoteTo,
      },
    );
    final dynamic data = response['data'];
    return PagedResult<CustomerDebitNoteRecord>(
      items: data is List
          ? data
              .whereType<Map>()
              .map((item) => CustomerDebitNoteRecord.fromJson(
                  Map<String, dynamic>.from(item)))
              .toList()
          : const [],
      total: _totalOf(response),
    );
  }

  /// Price a customer debit note as raising it would, and save nothing: the
  /// tax the phase 2 screen shows going on while the amounts are typed.
  Future<CustomerDebitNoteRecord> previewCustomerDebitNote(Json body) async =>
      CustomerDebitNoteRecord.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/customer-debit-notes/preview',
              body: body),
        ),
      );

  Future<CustomerDebitNoteRecord> createCustomerDebitNote(Json body) async =>
      CustomerDebitNoteRecord.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/customer-debit-notes', body: body)),
      );

  Future<CustomerDebitNoteRecord> approveCustomerDebitNote(
    String id, {
    int? expectedVersion,
  }) async =>
      CustomerDebitNoteRecord.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/customer-debit-notes/$id/approve',
        expectedVersion: expectedVersion,
      )));

  Future<CustomerDebitNoteRecord> cancelCustomerDebitNote(
    String id, {
    int? expectedVersion,
  }) async =>
      CustomerDebitNoteRecord.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/customer-debit-notes/$id/cancel',
        expectedVersion: expectedVersion,
      )));

  // ---- debit notes ----------------------------------------------------

  Future<PagedResult<DebitNoteRecord>> debitNotes({
    int page = 1,
    int pageSize = 50,
    String? status,
    String? search,
    String? vendorId,
    String? purchaseInvoiceId,
    String? debitNoteFrom,
    String? debitNoteTo,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/debit-notes',
      query: {
        'page': '$page',
        'page_size': '$pageSize',
        if (status != null && status.isNotEmpty) 'status': status,
        if (search != null && search.isNotEmpty) 'search': search,
        if (vendorId != null && vendorId.isNotEmpty) 'vendor_id': vendorId,
        if (purchaseInvoiceId != null && purchaseInvoiceId.isNotEmpty)
          'purchase_invoice_id': purchaseInvoiceId,
        if (debitNoteFrom != null) 'debit_note_from': debitNoteFrom,
        if (debitNoteTo != null) 'debit_note_to': debitNoteTo,
      },
    );
    final dynamic data = response['data'];
    return PagedResult<DebitNoteRecord>(
      items: data is List
          ? data
              .whereType<Map>()
              .map((item) =>
                  DebitNoteRecord.fromJson(Map<String, dynamic>.from(item)))
              .toList()
          : const [],
      total: _totalOf(response),
    );
  }

  /// Price a debit note as raising it would, and save nothing.
  Future<DebitNoteRecord> previewDebitNote(Json body) async =>
      DebitNoteRecord.fromJson(
        _unwrapMap(
          await request('POST', '/api/v1/debit-notes/preview', body: body),
        ),
      );

  Future<DebitNoteRecord> createDebitNote(Json body) async =>
      DebitNoteRecord.fromJson(
        _unwrapMap(await request('POST', '/api/v1/debit-notes', body: body)),
      );

  Future<DebitNoteRecord> debitNote(String id) async =>
      DebitNoteRecord.fromJson(
        _unwrapMap(await request('GET', '/api/v1/debit-notes/$id')),
      );

  /// What each line of a bill can still be claimed on. [excludingNoteId] is
  /// the note being edited, whose own claim must not count against it.
  Future<List<DebitNoteClaimableLine>> debitNoteClaimableLines(
    String purchaseInvoiceId, {
    String? excludingNoteId,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/debit-notes/claimable-lines',
      query: {
        'purchase_invoice_id': purchaseInvoiceId,
        if (excludingNoteId != null && excludingNoteId.isNotEmpty)
          'excluding_note_id': excludingNoteId,
      },
    );
    final dynamic data = response['data'];
    return [
      for (final dynamic row in data is List ? data : const [])
        if (row is Map)
          DebitNoteClaimableLine.fromJson(Map<String, dynamic>.from(row)),
    ];
  }

  Future<DebitNoteRecord> updateDebitNote(
    String id,
    Json body, {
    int? expectedVersion,
  }) async =>
      DebitNoteRecord.fromJson(_unwrapMap(await request(
        'PUT',
        '/api/v1/debit-notes/$id',
        body: body,
        expectedVersion: expectedVersion,
      )));

  Future<DebitNoteRecord> approveDebitNote(
    String id, {
    int? expectedVersion,
  }) async =>
      DebitNoteRecord.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/debit-notes/$id/approve',
        expectedVersion: expectedVersion,
      )));

  /// Cancel a note; the server refuses a cancel with no [reason].
  Future<DebitNoteRecord> cancelDebitNote(
    String id,
    String reason, {
    int? expectedVersion,
  }) async =>
      DebitNoteRecord.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/debit-notes/$id/cancel',
        body: {'reason': reason},
        expectedVersion: expectedVersion,
      )));

  // ---- party adjustments ----------------------------------------------

  Future<PagedResult<PartyAdjustment>> partyAdjustments({
    int page = 1,
    int pageSize = 50,
    String? kind,
    String? status,
    String? customerId,
    String? vendorId,
    String? search,
    String? dateFrom,
    String? dateTo,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/party-adjustments',
      query: {
        'page': '$page',
        'page_size': '$pageSize',
        if (kind != null && kind.isNotEmpty) 'kind': kind,
        if (status != null && status.isNotEmpty) 'status': status,
        if (customerId != null && customerId.isNotEmpty)
          'customer_id': customerId,
        if (vendorId != null && vendorId.isNotEmpty) 'vendor_id': vendorId,
        if (search != null && search.isNotEmpty) 'search': search,
        if (dateFrom != null) 'date_from': dateFrom,
        if (dateTo != null) 'date_to': dateTo,
      },
    );
    final dynamic data = response['data'];
    return PagedResult<PartyAdjustment>(
      items: data is List
          ? data
              .whereType<Map>()
              .map((item) =>
                  PartyAdjustment.fromJson(Map<String, dynamic>.from(item)))
              .toList()
          : const [],
      total: _totalOf(response),
    );
  }

  /// Draft one adjustment; nothing is posted until it is approved.
  Future<PartyAdjustment> createPartyAdjustment(Json body) async =>
      PartyAdjustment.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/party-adjustments', body: body)),
      );

  Future<PartyAdjustment> partyAdjustment(String id) async =>
      PartyAdjustment.fromJson(
        _unwrapMap(await request('GET', '/api/v1/party-adjustments/$id')),
      );

  /// Change a draft. Send only the keys the server declares: the kind and the
  /// status are not among them.
  Future<PartyAdjustment> updatePartyAdjustment(
    String id,
    Json body, {
    int? expectedVersion,
  }) async =>
      PartyAdjustment.fromJson(_unwrapMap(await request(
        'PUT',
        '/api/v1/party-adjustments/$id',
        body: body,
        expectedVersion: expectedVersion,
      )));

  Future<PartyAdjustment> approvePartyAdjustment(
    String id, {
    int? expectedVersion,
  }) async =>
      PartyAdjustment.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/party-adjustments/$id/approve',
        expectedVersion: expectedVersion,
      )));

  /// Withdraw an adjustment; the server refuses a cancel with no [reason].
  Future<PartyAdjustment> cancelPartyAdjustment(
    String id,
    String reason, {
    int? expectedVersion,
  }) async =>
      PartyAdjustment.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/party-adjustments/$id/cancel',
        body: {'reason': reason},
        expectedVersion: expectedVersion,
      )));

  /// The bills an adjustment can clear for the party or parties named.
  Future<PartyAdjustmentOpenBills> partyAdjustmentOpenBills({
    String? customerId,
    String? vendorId,
  }) async =>
      PartyAdjustmentOpenBills.fromJson(_unwrapMap(await request(
        'GET',
        '/api/v1/party-adjustments/open-bills',
        query: {
          if (customerId != null && customerId.isNotEmpty)
            'customer_id': customerId,
          if (vendorId != null && vendorId.isNotEmpty) 'vendor_id': vendorId,
        },
      )));

  Future<PartyAdjustmentSettings> partyAdjustmentSettings() async =>
      PartyAdjustmentSettings.fromJson(
        _unwrapMap(await request('GET', '/api/v1/party-adjustments/settings')),
      );

  Future<PartyAdjustmentSettings> savePartyAdjustmentSettings(
    Json body,
  ) async =>
      PartyAdjustmentSettings.fromJson(_unwrapMap(
        await request('PUT', '/api/v1/party-adjustments/settings', body: body),
      ));

  // ---- contra vouchers ------------------------------------------------

  Future<PagedResult<ContraVoucher>> contraVouchers({
    int page = 1,
    int pageSize = 50,
    String? kind,
    String? status,
    String? accountId,
    String? search,
    String? dateFrom,
    String? dateTo,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/contra-vouchers',
      query: {
        'page': '$page',
        'page_size': '$pageSize',
        if (kind != null && kind.isNotEmpty) 'kind': kind,
        if (status != null && status.isNotEmpty) 'status': status,
        if (accountId != null && accountId.isNotEmpty)
          'account_id': accountId,
        if (search != null && search.isNotEmpty) 'search': search,
        if (dateFrom != null) 'date_from': dateFrom,
        if (dateTo != null) 'date_to': dateTo,
      },
    );
    final dynamic data = response['data'];
    return PagedResult<ContraVoucher>(
      items: data is List
          ? data
              .whereType<Map>()
              .map((item) =>
                  ContraVoucher.fromJson(Map<String, dynamic>.from(item)))
              .toList()
          : const [],
      total: _totalOf(response),
    );
  }

  /// The cash and bank accounts a voucher may move money between.
  Future<List<MoneyAccount>> contraMoneyAccounts() async {
    final Json response =
        await request('GET', '/api/v1/contra-vouchers/money-accounts');
    final dynamic data = response['data'];
    return data is List
        ? data
            .whereType<Map>()
            .map((item) =>
                MoneyAccount.fromJson(Map<String, dynamic>.from(item)))
            .toList()
        : const <MoneyAccount>[];
  }

  /// Post one voucher. The save succeeds even when the From account goes
  /// below zero; that shows as [ContraVoucher.balanceWarning].
  Future<ContraVoucher> createContraVoucher(Json body) async =>
      ContraVoucher.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/contra-vouchers', body: body)),
      );

  Future<ContraVoucher> contraVoucher(String id) async =>
      ContraVoucher.fromJson(
        _unwrapMap(await request('GET', '/api/v1/contra-vouchers/$id')),
      );

  /// Reverse a voucher; the server refuses a cancel with no [reason].
  Future<ContraVoucher> cancelContraVoucher(
    String id,
    String reason, {
    int? expectedVersion,
  }) async =>
      ContraVoucher.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/contra-vouchers/$id/cancel',
        body: {'reason': reason},
        expectedVersion: expectedVersion,
      )));

  /// The voucher as a PDF.
  Future<List<int>> contraVoucherPdf(String id) =>
      downloadBytes('/api/v1/contra-vouchers/$id/print');

  // ---- TDS challans (ACC-7) -------------------------------------------

  /// Deductions on posted payments and expenses that no live challan has
  /// paid, oldest first.
  Future<List<TdsOpenDeduction>> tdsOpenDeductions({
    String? section,
    String? fromDate,
    String? toDate,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/finance/tds-challans/open-deductions',
      query: {
        if (section != null && section.isNotEmpty) 'section': section,
        if (fromDate != null) 'from_date': fromDate,
        if (toDate != null) 'to_date': toDate,
      },
    );
    final dynamic data = response['data'];
    return data is List
        ? data
            .whereType<Map>()
            .map((item) =>
                TdsOpenDeduction.fromJson(Map<String, dynamic>.from(item)))
            .toList()
        : const <TdsOpenDeduction>[];
  }

  Future<PagedResult<TdsChallan>> tdsChallans({
    int page = 1,
    int pageSize = 50,
    String? section,
    String? status,
    String? fromDate,
    String? toDate,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/finance/tds-challans',
      query: {
        'page': '$page',
        'page_size': '$pageSize',
        if (section != null && section.isNotEmpty) 'section': section,
        if (status != null && status.isNotEmpty) 'status': status,
        if (fromDate != null) 'from_date': fromDate,
        if (toDate != null) 'to_date': toDate,
      },
    );
    final dynamic data = response['data'];
    return PagedResult<TdsChallan>(
      items: data is List
          ? data
              .whereType<Map>()
              .map((item) =>
                  TdsChallan.fromJson(Map<String, dynamic>.from(item)))
              .toList()
          : const [],
      total: _totalOf(response),
    );
  }

  Future<TdsChallan> tdsChallan(String id) async => TdsChallan.fromJson(
        _unwrapMap(await request('GET', '/api/v1/finance/tds-challans/$id')),
      );

  /// Record a deposit and tick off the deductions it paid.
  Future<TdsChallan> createTdsChallan(Json body) async => TdsChallan.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/finance/tds-challans', body: body)),
      );

  /// Reverse a challan; the deductions it paid become open again.
  Future<TdsChallan> cancelTdsChallan(
    String id,
    String reason, {
    int? expectedVersion,
  }) async =>
      TdsChallan.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/finance/tds-challans/$id/cancel',
        body: {'reason': reason},
        expectedVersion: expectedVersion,
      )));

  // ---- firm bank details printed on bills (ACC-4) ----------------------

  /// The firm's kept bank details, the printed one first.
  Future<List<BankAccountDetails>> listBankDetails() async => _unwrapList(
        await request('GET', '/api/v1/finance/bank-details'),
        BankAccountDetails.fromJson,
      );

  /// Saved whole; saving one marked for printing moves the mark to it.
  Future<BankAccountDetails> saveBankDetails(
    String ledgerAccountId,
    Json body,
  ) async =>
      BankAccountDetails.fromJson(_unwrapMap(await request(
        'PUT',
        '/api/v1/finance/bank-details/$ledgerAccountId',
        body: body,
      )));

  /// Removes the details; the ledger account stays.
  Future<void> removeBankDetails(String ledgerAccountId) => request(
        'DELETE',
        '/api/v1/finance/bank-details/$ledgerAccountId',
      );

  // ---- post-dated cheques (ACC-2) --------------------------------------

  /// The register's path: a customer's cheques, or the firm's own.
  String _pdcPath(bool issued) =>
      '/api/v1/post-dated-cheques/${issued ? 'issued' : 'received'}';

  /// [dueOn] lists only held cheques dated on or before that day.
  Future<PagedResult<PostDatedCheque>> listPostDatedCheques({
    required bool issued,
    int page = 1,
    int pageSize = 50,
    String? search,
    String? status,
    String? partyId,
    String? dueOn,
    String? chequeFrom,
    String? chequeTo,
  }) async {
    final Json response = await request(
      'GET',
      _pdcPath(issued),
      query: {
        'page': '$page',
        'page_size': '$pageSize',
        if (search != null && search.isNotEmpty) 'search': search,
        if (status != null && status.isNotEmpty) 'status': status,
        if (partyId != null && partyId.isNotEmpty) 'party_id': partyId,
        if (dueOn != null) 'due_on': dueOn,
        if (chequeFrom != null) 'cheque_from': chequeFrom,
        if (chequeTo != null) 'cheque_to': chequeTo,
      },
    );
    final dynamic data = response['data'];
    return PagedResult<PostDatedCheque>(
      items: data is List
          ? data
              .whereType<Map>()
              .map((item) =>
                  PostDatedCheque.fromJson(Map<String, dynamic>.from(item)))
              .toList()
          : const [],
      total: _totalOf(response),
    );
  }

  Future<PostDatedCheque> createPostDatedCheque({
    required bool issued,
    required Json body,
  }) async =>
      PostDatedCheque.fromJson(
        _unwrapMap(await request('POST', _pdcPath(issued), body: body)),
      );

  /// Bank the cheque; the server raises the receipt or payment.
  Future<PostDatedCheque> depositPostDatedCheque({
    required bool issued,
    required String id,
    required Json body,
    int? expectedVersion,
  }) async =>
      PostDatedCheque.fromJson(_unwrapMap(await request(
        'POST',
        '${_pdcPath(issued)}/$id/deposit',
        body: body,
        expectedVersion: expectedVersion,
      )));

  Future<PostDatedCheque> clearPostDatedCheque({
    required bool issued,
    required String id,
    required Json body,
    int? expectedVersion,
  }) async =>
      PostDatedCheque.fromJson(_unwrapMap(await request(
        'POST',
        '${_pdcPath(issued)}/$id/clear',
        body: body,
        expectedVersion: expectedVersion,
      )));

  /// A bounce reverses the receipt or payment the cheque raised.
  Future<PostDatedCheque> bouncePostDatedCheque({
    required bool issued,
    required String id,
    required Json body,
    int? expectedVersion,
  }) async =>
      PostDatedCheque.fromJson(_unwrapMap(await request(
        'POST',
        '${_pdcPath(issued)}/$id/bounce',
        body: body,
        expectedVersion: expectedVersion,
      )));

  Future<PostDatedCheque> cancelPostDatedCheque({
    required bool issued,
    required String id,
    required String reason,
    int? expectedVersion,
  }) async =>
      PostDatedCheque.fromJson(_unwrapMap(await request(
        'POST',
        '${_pdcPath(issued)}/$id/cancel',
        body: {'reason': reason},
        expectedVersion: expectedVersion,
      )));

  // ---- commission payouts ---------------------------------------------

  Future<PagedResult<CommissionPayoutRecord>> commissionPayouts({
    int page = 1,
    int pageSize = 50,
    String? status,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/commission/payouts',
      query: {
        'page': '$page',
        'page_size': '$pageSize',
        if (status != null && status.isNotEmpty) 'status': status,
      },
    );
    final dynamic data = response['data'];
    return PagedResult<CommissionPayoutRecord>(
      items: data is List
          ? data
              .whereType<Map>()
              .map((item) => CommissionPayoutRecord.fromJson(
                  Map<String, dynamic>.from(item)))
              .toList()
          : const [],
      total: _totalOf(response),
    );
  }

  /// Turn what a period earned into draft payouts, one per person.
  Future<List<CommissionPayoutRecord>> accrueCommissionPayouts(
      Json body) async {
    final Json response =
        await request('POST', '/api/v1/commission/payouts/accrue', body: body);
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) =>
            CommissionPayoutRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<CommissionPayoutRecord> updateCommissionPayout(
    String id,
    Json body, {
    int? expectedVersion,
  }) async =>
      CommissionPayoutRecord.fromJson(_unwrapMap(await request(
        'PUT',
        '/api/v1/commission/payouts/$id',
        body: body,
        expectedVersion: expectedVersion,
      )));

  Future<CommissionPayoutRecord> approveCommissionPayout(
    String id, {
    int? expectedVersion,
  }) async =>
      CommissionPayoutRecord.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/commission/payouts/$id/approve',
        expectedVersion: expectedVersion,
      )));

  Future<CommissionPayoutRecord> payCommissionPayout(
    String id,
    Json body, {
    int? expectedVersion,
  }) async =>
      CommissionPayoutRecord.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/commission/payouts/$id/pay',
        body: body,
        expectedVersion: expectedVersion,
      )));

  Future<CommissionPayoutRecord> cancelCommissionPayout(
    String id, {
    int? expectedVersion,
  }) async =>
      CommissionPayoutRecord.fromJson(_unwrapMap(await request(
        'POST',
        '/api/v1/commission/payouts/$id/cancel',
        expectedVersion: expectedVersion,
      )));

  // ---- commission ----------------------------------------------------

  Future<PagedResult<CommissionRuleRecord>> commissionRules({
    int page = 1,
    int pageSize = 20,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/commission/rules',
      query: {'page': '$page', 'page_size': '$pageSize'},
    );
    final dynamic data = response['data'];
    return PagedResult<CommissionRuleRecord>(
      items: data is List
          ? data
              .whereType<Map>()
              .map((item) => CommissionRuleRecord.fromJson(
                  Map<String, dynamic>.from(item)))
              .toList()
          : const [],
      total: _totalOf(response),
    );
  }

  Future<CommissionRuleRecord> createCommissionRule(Json body) async =>
      CommissionRuleRecord.fromJson(
        _unwrapMap(
            await request('POST', '/api/v1/commission/rules', body: body)),
      );

  Future<CommissionRuleRecord> updateCommissionRule(
    String id,
    Json body, {
    int? expectedVersion,
  }) async =>
      CommissionRuleRecord.fromJson(
        _unwrapMap(await request(
          'PUT',
          '/api/v1/commission/rules/$id',
          body: body,
          expectedVersion: expectedVersion,
        )),
      );

  Future<void> deleteCommissionRule(String id) =>
      request('DELETE', '/api/v1/commission/rules/$id');

  /// What each salesman collected in a period, and what it earned them.
  Future<CommissionReport> commissionReport({
    required String fromDate,
    required String toDate,
  }) async =>
      CommissionReport.fromJson(_unwrapMap(await request(
        'GET',
        '/api/v1/commission/report',
        query: {'from_date': fromDate, 'to_date': toDate},
      )));

  /// Read the record count a paginated envelope reports.
  int _totalOf(Json response) {
    final dynamic pagination = response['pagination'];
    if (pagination is Map) {
      return (pagination['total_records'] as num?)?.toInt() ?? 0;
    }
    return 0;
  }

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

  /// The roles one user holds **in one firm**.
  ///
  /// A firm-tier role always names its firm, so this is how the Roles-by-firm
  /// editor reads and writes. `PUT /users/{id}/roles` now carries only the
  /// platform-tier roles, which belong to no firm at all.
  Future<List<String>> userFirmRoles(String userId, String firmId) async {
    final Json response =
        await request('GET', '/api/v1/users/$userId/firms/$firmId/roles');
    final dynamic data = response['data'];
    final dynamic ids = data is Map ? data['ids'] : null;
    return ids is List
        ? ids.map(stringValue).where((id) => id.isNotEmpty).toList()
        : <String>[];
  }

  /// The roles one user holds in **every** firm.
  ///
  /// Readable by a firm administrator and not writable by them: a global
  /// grant applies in their firm, so hiding it would under-report what the
  /// person can do there, and editing one would undo a platform decision.
  Future<List<String>> userGlobalRoles(String userId) async {
    final Json response =
        await request('GET', '/api/v1/users/$userId/global-roles');
    final dynamic data = response['data'];
    final dynamic ids = data is Map ? data['ids'] : null;
    return ids is List
        ? ids.map(stringValue).where((id) => id.isNotEmpty).toList()
        : <String>[];
  }

  /// Replace what one user does in one firm. Other firms are untouched.
  Future<void> setUserFirmRoles(
    String userId,
    String firmId,
    List<String> roleIds,
  ) =>
      request(
        'PUT',
        '/api/v1/users/$userId/firms/$firmId/roles',
        body: {'ids': roleIds},
      );
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

  /// [notes] null leaves the stored notes alone -- the Set up panel assigns a
  /// profile without knowing them -- while an empty string clears them. The
  /// server keeps what is not sent, so the panel no longer wipes the notes
  /// the Profile Assignment screen wrote (D-CFG-21).
  Future<void> assignBusinessProfileToFirm(
    String firmId,
    String businessProfileId, {
    bool isActive = true,
    String? notes,
  }) =>
      request(
        'PUT',
        '/api/v1/business-framework/firms/$firmId/profile-assignment',
        body: {
          'business_profile_id': businessProfileId,
          'is_active': isActive,
          if (notes != null) 'notes': notes.trim().isEmpty ? null : notes,
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

  /// The global roles a user holds, as readable codes.
  ///
  /// For the read-only line on the user form: a firm administrator needs to
  /// see that a platform grant applies in *their* firm, or the form reports
  /// less than the person can do. Ids alone would say nothing, so they are
  /// resolved against the role catalogue; a role the caller cannot see -- a
  /// platform-tier one -- is counted rather than named, which is the honest
  /// answer when the name is not theirs to read.
  Future<String> userGlobalRoleLabels(String userId) async {
    final List<String> ids = await userGlobalRoles(userId);
    if (ids.isEmpty) return '';
    final List<AssignmentOption> catalogue = await options('roles');
    final Map<String, String> byId = {
      for (final AssignmentOption role in catalogue) role.id: role.label,
    };
    final List<String> named = [
      for (final String id in ids)
        if (byId.containsKey(id)) byId[id]!,
    ]..sort();
    final int unnamed = ids.length - named.length;
    if (named.isEmpty) return '$unnamed role(s) set platform-wide';
    return unnamed == 0
        ? named.join(', ')
        : '${named.join(', ')} and $unnamed more';
  }

  /// What a user holds firm by firm, as one readable line.
  ///
  /// The mirror of [userGlobalRoleLabels], for the caller who edits the other
  /// tier: a platform administrator's Roles field is the global set, so
  /// without this the user page says nothing about the firm grants and the
  /// same blind spot points the other way.
  ///
  /// One read per firm the person belongs to. That is the shape of the data --
  /// a grant is per firm -- and it happens once when the form opens.
  Future<String> userFirmRoleLabels(String userId) async {
    final Map<String, dynamic> membership =
        await userFirmAssignmentValues(userId);
    final List<String> firmIds = (membership['firm_ids'] as String? ?? '')
        .split(',')
        .where((id) => id.isNotEmpty)
        .toList();
    if (firmIds.isEmpty) return '';

    final List<AssignmentOption> firms = await options('firms');
    final List<AssignmentOption> roles = await options('roles');
    final Map<String, String> firmName = {
      for (final AssignmentOption firm in firms) firm.id: firm.label,
    };
    final Map<String, String> roleName = {
      for (final AssignmentOption role in roles) role.id: role.label,
    };

    final List<String> parts = [];
    for (final String firmId in firmIds) {
      final List<String> held = await userFirmRoles(userId, firmId);
      if (held.isEmpty) continue;
      final List<String> named = [
        for (final String id in held)
          if (roleName.containsKey(id)) roleName[id]!,
      ]..sort();
      if (named.isEmpty) continue;
      parts.add('${firmName[firmId] ?? firmId}: ${named.join(", ")}');
    }
    return parts.join('  ·  ');
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

  /// [openToHandJournals] asks the server to leave out every account a
  /// hand journal is refused on -- the sub-ledger and CONTROL accounts -- so
  /// the journal editor offers only what it can save (D-FIN-20).
  Future<PagedResult<LedgerAccount>> ledgerAccounts({
    String? accountGroupId,
    bool? isActive,
    bool openToHandJournals = false,
  }) async {
    final Json response = await request(
      'GET',
      '/api/v1/finance/ledger-accounts',
      query: {
        if (accountGroupId != null) 'account_group_id': accountGroupId,
        if (isActive != null) 'is_active': '$isActive',
        if (openToHandJournals) 'open_to_hand_journals': 'true',
      },
    );
    final List<LedgerAccount> items =
        _unwrapList(response, LedgerAccount.fromJson);
    return PagedResult<LedgerAccount>(items: items, total: items.length);
  }

  /// Every posting purpose and the account it lands in, gaps included.
  Future<List<ControlAccountMapping>> controlAccounts() async => _unwrapList(
        await request('GET', '/api/v1/finance/control-accounts'),
        ControlAccountMapping.fromJson,
      );

  /// Map one purpose to one account. Returns the server's message; refused
  /// by name once lines have posted to the current account.
  Future<String> assignControlAccount(
    String purpose,
    String ledgerAccountId,
  ) async {
    final Json response = await request(
      'PUT',
      '/api/v1/finance/control-accounts/$purpose',
      body: {'ledger_account_id': ledgerAccountId},
    );
    return stringValue(response['message']).isEmpty
        ? 'Mapped.'
        : stringValue(response['message']);
  }

  /// The firm's cost centres. A list, not a page: a firm has a handful.
  Future<PagedResult<FinanceCentre>> costCenters() async {
    final List<FinanceCentre> items = _unwrapList(
      await request('GET', '/api/v1/finance/cost-centers'),
      FinanceCentre.fromJson,
    );
    return PagedResult<FinanceCentre>(items: items, total: items.length);
  }

  /// The firm's profit centres.
  Future<PagedResult<FinanceCentre>> profitCenters() async {
    final List<FinanceCentre> items = _unwrapList(
      await request('GET', '/api/v1/finance/profit-centers'),
      FinanceCentre.fromJson,
    );
    return PagedResult<FinanceCentre>(items: items, total: items.length);
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

  // ── Trade Licences ────────────────────────────────────────────────────
  // Backlog 54. Every list here is a plain list, not a page -- a firm holds
  // a handful of its own licences and one or two per customer or vendor -- so
  // each is wrapped into a `PagedResult` here rather than pretending the
  // server paginates. Types and licences are both written through the
  // generic `create`/`update`/`delete` (`resource: 'trade-licences/types'`
  // and `resource: 'trade-licences'`), so no named write methods are needed;
  // `options('trade-licences/types')` serves the type dropdown the same way.

  Future<List<TradeLicenceTypeRecord>> tradeLicenceTypes() async => _unwrapList(
        await request('GET', '/api/v1/trade-licences/types'),
        TradeLicenceTypeRecord.fromJson,
      );

  /// The types register as one page, for `ResourceDefinition.load`. The
  /// endpoint has no search, so it is applied here, as `productCategoryPage`
  /// does for the same reason.
  Future<PagedResult<TradeLicenceTypeRecord>> tradeLicenceTypesPage({
    int page = 1,
    String search = '',
    String sortBy = 'code',
    bool descending = false,
  }) async {
    final List<TradeLicenceTypeRecord> rows = await tradeLicenceTypes();
    final String needle = search.trim().toLowerCase();
    final List<TradeLicenceTypeRecord> filtered = rows
        .where((row) =>
            needle.isEmpty ||
            row.code.toLowerCase().contains(needle) ||
            row.name.toLowerCase().contains(needle))
        .toList()
      ..sort((a, b) => a.code.compareTo(b.code));
    return PagedResult(items: filtered, total: filtered.length);
  }

  Future<List<TradeLicenceRecord>> tradeLicences({
    String? holderType,
    String? branchId,
    String? customerId,
    String? vendorId,
    String? licenceTypeId,
  }) async =>
      _unwrapList(
        await request(
          'GET',
          '/api/v1/trade-licences',
          query: {
            if (holderType != null) 'holder_type': holderType,
            if (branchId != null) 'branch_id': branchId,
            if (customerId != null) 'customer_id': customerId,
            if (vendorId != null) 'vendor_id': vendorId,
            if (licenceTypeId != null) 'licence_type_id': licenceTypeId,
          },
        ),
        TradeLicenceRecord.fromJson,
      );

  /// The whole register as one page, for `ResourceDefinition.load`.
  Future<PagedResult<TradeLicenceRecord>> tradeLicencesPage({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) async {
    final List<TradeLicenceRecord> rows = await tradeLicences();
    final String needle = search.trim().toLowerCase();
    final List<TradeLicenceRecord> filtered = needle.isEmpty
        ? rows
        : rows
            .where((row) =>
                row.licenceNumber.toLowerCase().contains(needle) ||
                row.holderName.toLowerCase().contains(needle) ||
                row.licenceTypeName.toLowerCase().contains(needle))
            .toList();
    return PagedResult(items: filtered, total: filtered.length);
  }

  /// Licences that ran out or run out soon, the firm's own first -- what the
  /// Home alert counts and, on a tap, opens the register to show.
  Future<List<TradeLicenceRecord>> expiringTradeLicences(
          {int? withinDays}) async =>
      _unwrapList(
        await request(
          'GET',
          '/api/v1/trade-licences/expiring',
          query: {
            if (withinDays != null) 'within_days': '$withinDays',
          },
        ),
        TradeLicenceRecord.fromJson,
      );

  /// What a missing or lapsed licence does to a sale, and to a purchase.
  /// Needs `TRADE_LICENCE_VIEW`.
  Future<TradeLicenceSettingsRecord> licenceSettings() async =>
      TradeLicenceSettingsRecord.fromJson(
        _unwrapMap(await request('GET', '/api/v1/trade-licences/settings')),
      );

  /// Replace the firm's policy. Needs `TRADE_LICENCE_MANAGE_SETTINGS`; the
  /// server refuses `BLOCK` on the purchase side.
  Future<TradeLicenceSettingsRecord> updateLicenceSettings(
    TradeLicenceSettingsRecord settings,
  ) async =>
      TradeLicenceSettingsRecord.fromJson(
        _unwrapMap(
          await request(
            'PUT',
            '/api/v1/trade-licences/settings',
            body: settings.toJson(),
          ),
        ),
      );

  /// Say, before approving, what a document's lines need and who lacks it --
  /// the same judgement the approval itself makes, on the document's own
  /// date. [document] is one of SALES_ORDER, DELIVERY_NOTE, SALES_INVOICE,
  /// PURCHASE_ORDER or GOODS_RECEIPT. Needs `TRADE_LICENCE_VIEW`.
  Future<LicenceCheckRecord> checkLicences(
    String document,
    String documentId,
  ) async =>
      LicenceCheckRecord.fromJson(
        _unwrapMap(
          await request(
            'GET',
            '/api/v1/trade-licences/check/$document/$documentId',
          ),
        ),
      );

  /// The trial balance for one accounting period.
  ///
  /// Whether it balances is the server's answer, carried through rather than
  /// recomputed: two places deciding that is two places that can disagree.
  ///
  /// With [toPeriodId], every month from [accountingPeriodId] to it, in one
  /// financial year (backlog 50 item 5).
  Future<TrialBalanceReport> trialBalance(
    String accountingPeriodId, {
    String? toPeriodId,
  }) async =>
      TrialBalanceReport.fromJson(
        await request(
          'GET',
          '/api/v1/finance/trial-balance',
          query: {
            'accounting_period_id': accountingPeriodId,
            if (toPeriodId != null) 'to_period_id': toPeriodId,
          },
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
    String? settlementFrom,
    String? settlementTo,
  }) =>
      _list(
        '/api/v1/${direction.path}',
        Settlement.fromJson,
        page,
        search,
        pageSize: pageSize,
        additionalQuery: {
          if (partyId != null) direction.partyParameter: partyId,
          // The Period filter (owner, 2026-09-27): settlement dates, inclusive.
          if (settlementFrom != null) 'settlement_from': settlementFrom,
          if (settlementTo != null) 'settlement_to': settlementTo,
        },
      );

  /// Who money can be taken from or paid to, for the party picker.
  ///
  /// **Not the customer or vendor master.** Those are gated on
  /// `CUSTOMER_VIEW` / `VENDOR_VIEW`, and `CASHIER` holds neither — it holds
  /// the four receipt and payment codes and nothing else. Reading the master
  /// here made the wrong permission the real gate on recording a receipt: the
  /// refusal arrived at the party lookup, before the receipt the cashier was
  /// authorised for had been attempted. This route is gated on the settlement
  /// permissions instead, and answers id, code and name.
  Future<List<PartyOption>> settlementParties({
    required SettlementDirection direction,
    String search = '',
  }) async {
    // Every page: the route stopped at the first 200 by code, so a firm with
    // more could not take money from the rest (D-SELL-18).
    final List<Json> rows = await _everyRow(
      '/api/v1/${direction.path}/parties',
      {if (search.isNotEmpty) 'search': search},
    );
    return [
      for (final Json row in rows)
        PartyOption(
          id: stringValue(row['id']),
          code: stringValue(row['code']),
          name: stringValue(row['name']),
          defaultTdsSection: stringValue(row['default_tds_section']),
        ),
    ];
  }

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

  /// Set money already received against an invoice raised since.
  ///
  /// The missing half of an advance: a deposit taken before the bill existed
  /// could sit on the customer's account with no way to say which bill it
  /// settled. Nothing is posted to the ledger — the money moved when the
  /// receipt was recorded, and this decides which invoice it clears.
  Future<Settlement> allocateReceipt({
    required String id,
    required String invoiceId,
    required String amount,
  }) async =>
      Settlement.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/receipts/$id/allocate',
            body: <String, dynamic>{'invoice_id': invoiceId, 'amount': amount},
          ),
        ),
      );

  /// Set money already paid against a bill that arrived since.
  ///
  /// The supplier's advance, the mirror of [allocateReceipt]: a payment
  /// recorded with no allocation could never be set against a bill
  /// afterwards (D-BUY-8). Nothing is posted — the money left when the
  /// payment was recorded, and this decides which bill it clears.
  Future<Settlement> allocatePayment({
    required String id,
    required String invoiceId,
    required String amount,
  }) async =>
      Settlement.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/payments/$id/allocate',
            body: <String, dynamic>{'invoice_id': invoiceId, 'amount': amount},
          ),
        ),
      );

  /// What a supplier owes the firm from goods sent back against a receipt,
  /// not yet set against a bill (D-FIN-19).
  Future<List<SupplierCredit>> supplierCredits(String vendorId) async {
    final Json response = await request(
      'GET',
      '/api/v1/payments/supplier-credits',
      query: {'vendor_id': vendorId},
    );
    return _unwrapList(response, SupplierCredit.fromJson);
  }

  /// Set part of a supplier credit against one of that supplier's bills.
  ///
  /// Nothing is posted: the return debited payables when it completed and
  /// the bill credited them when it was approved. This says which bill the
  /// debit belongs to, so the bill owes that much less.
  Future<SupplierCredit> applySupplierCredit({
    required String sourceId,
    required String invoiceId,
    required String amount,
  }) async =>
      SupplierCredit.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/payments/supplier-credits/$sourceId/apply',
            body: <String, dynamic>{'invoice_id': invoiceId, 'amount': amount},
          ),
        ),
      );

  /// What the supplier handed back against a credit whose return came back
  /// as a refund, newest first as the server lists them.
  Future<List<SupplierRefund>> supplierRefunds(String sourceId) async =>
      _unwrapList(
        await request(
          'GET',
          '/api/v1/payments/supplier-credits/$sourceId/refunds',
        ),
        SupplierRefund.fromJson,
      );

  /// Record money received from the supplier against a credit. Posts to the
  /// ledger; only a return whose outcome is REFUND accepts one.
  Future<SupplierRefund> recordSupplierRefund({
    required String sourceId,
    required String amount,
    required String refundedOn,
    required String method,
    String? reference,
    String? remarks,
  }) async =>
      SupplierRefund.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/payments/supplier-credits/$sourceId/refunds',
            body: <String, dynamic>{
              'amount': amount,
              'refunded_on': refundedOn,
              'method': method,
              if (reference != null && reference.isNotEmpty)
                'reference': reference,
              if (remarks != null && remarks.isNotEmpty) 'remarks': remarks,
            },
          ),
        ),
      );

  /// Take a supplier refund back: the original stays and a mirror journal
  /// cancels it.
  Future<SupplierRefund> reverseSupplierRefund({
    required String refundId,
    required String reason,
  }) async =>
      SupplierRefund.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/payments/supplier-credits/refunds/$refundId/reverse',
            body: <String, dynamic>{'reason': reason},
          ),
        ),
      );

  /// What a purchase return comes back as: CREDIT, REPLACEMENT or REFUND.
  Future<Json> setPurchaseReturnOutcome({
    required String returnId,
    required String outcome,
  }) async =>
      _unwrapMap(
        await request(
          'POST',
          '/api/v1/purchase-returns/$returnId/outcome',
          body: <String, dynamic>{'outcome': outcome},
        ),
      );

  /// What a customer has paid against one sales order.
  Future<Json> salesOrderAdvances(String orderId) async =>
      _unwrapMap(await request(
        'GET',
        '/api/v1/sales-orders/$orderId/advances',
      ));

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

  /// One page of the firm's expenses -- rent, fuel, salaries -- newest first.
  Future<PagedResult<Expense>> expenses({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? status,
    String? expenseFrom,
    String? expenseTo,
  }) =>
      _list(
        '/api/v1/expenses',
        Expense.fromJson,
        page,
        search,
        pageSize: pageSize,
        additionalQuery: {
          if (status != null && status.isNotEmpty) 'status': status,
          // The Period filter: expense dates, inclusive.
          if (expenseFrom != null) 'expense_from': expenseFrom,
          if (expenseTo != null) 'expense_to': expenseTo,
        },
      );

  /// One expense, as it stands now.
  Future<Expense> expense(String id) async => Expense.fromJson(
        _unwrapMap(await request('GET', '/api/v1/expenses/$id')),
      );

  /// The accounts the expense form offers: the firm's expense accounts no
  /// document posts to, and the cash and bank accounts money is paid from.
  Future<ExpenseAccountChoices> expenseAccountChoices() async =>
      ExpenseAccountChoices.fromJson(
        _unwrapMap(await request('GET', '/api/v1/expenses/accounts')),
      );

  /// Record an expense. The server writes and posts its journal in the same
  /// request: Dr the expense account, Cr the account the money came from.
  Future<Expense> recordExpense(Json data) async => Expense.fromJson(
        _unwrapMap(await request('POST', '/api/v1/expenses', body: data)),
      );

  /// Cancel an expense with a mirror journal; the original stays. A reason
  /// is required.
  Future<Expense> cancelExpense({
    required String id,
    required String reason,
    int? expectedVersion,
  }) async =>
      Expense.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/expenses/$id/cancel',
            body: {'reason': reason},
            expectedVersion: expectedVersion,
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
    String? search,
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
          if (search != null && search.trim().isNotEmpty) 'search': search.trim(),
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

  /// The profit and loss over a run of months in one financial year (50),
  /// month by month, optionally with the previous year's same months.
  Future<ProfitLossRangeReport> profitAndLossRange({
    required String fromPeriodId,
    required String toPeriodId,
    bool comparePreviousYear = false,
  }) async =>
      ProfitLossRangeReport.fromJson(
        await request(
          'GET',
          '/api/v1/finance/profit-loss/range',
          query: {
            'from_period_id': fromPeriodId,
            'to_period_id': toPeriodId,
            'compare': comparePreviousYear ? 'previous_year' : 'none',
          },
        ),
      );

  /// The cash flow statement over a run of months in one financial year
  /// (ACC-9), indirect method.
  Future<CashFlowReport> cashFlow({
    required String fromPeriodId,
    required String toPeriodId,
  }) async =>
      CashFlowReport.fromJson(
        await request(
          'GET',
          '/api/v1/finance/cash-flow',
          query: {'from_period_id': fromPeriodId, 'to_period_id': toPeriodId},
        ),
      );

  /// One account's statement for one period.
  ///
  /// The running balance comes down with the lines. It starts from the opening
  /// balance and moves in whichever direction the account type increases in,
  /// so adding the column up here would be a second opinion about the ledger.
  ///
  /// With [toPeriodId], over every month from [accountingPeriodId] to it, in
  /// one financial year (backlog 50 item 5).
  Future<GeneralLedgerReport> generalLedger({
    required String ledgerAccountId,
    required String accountingPeriodId,
    String? toPeriodId,
  }) async =>
      GeneralLedgerReport.fromJson(
        await request(
          'GET',
          '/api/v1/finance/general-ledger/$ledgerAccountId',
          query: {
            'accounting_period_id': accountingPeriodId,
            if (toPeriodId != null) 'to_period_id': toPeriodId,
          },
        ),
      );

  Future<PagedResult<JournalEntry>> journalEntries({
    int page = 1,
    int pageSize = 20,
    String search = '',
    bool descending = true,
    String? accountingPeriodId,
    String? status,
    String? sourceModule,
    String? journalFrom,
    String? journalTo,
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
          if (sourceModule != null) 'source_module': sourceModule,
          // The Period filter (owner, 2026-09-27): journal dates, inclusive.
          if (journalFrom != null) 'journal_from': journalFrom,
          if (journalTo != null) 'journal_to': journalTo,
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

  /// Edit a hand-written draft; `lines`, when sent, replaces them all.
  Future<JournalEntry> updateJournalEntry(String id, Json data) async =>
      JournalEntry.fromJson(
        _unwrapMap(
          await request(
            'PATCH',
            '/api/v1/finance/journal-entries/$id',
            body: data,
          ),
        ),
      );

  // Files kept with a journal entry, a receipt or a payment (ACC-10): the
  // file stays where it is and the record keeps its path, as with STK-9.

  Future<List<StockAttachmentRecord>> listJournalAttachments(
    String journalId,
  ) async =>
      _unwrapList(
        await request(
          'GET',
          '/api/v1/finance/journal-entries/$journalId/attachments',
        ),
        StockAttachmentRecord.fromJson,
      );

  Future<List<StockAttachmentRecord>> attachToJournal(
    String journalId,
    List<Json> files,
  ) async =>
      _unwrapList(
        await request(
          'POST',
          '/api/v1/finance/journal-entries/$journalId/attachments',
          body: {'attachments': files},
        ),
        StockAttachmentRecord.fromJson,
      );

  Future<void> removeJournalAttachment(
    String journalId,
    String attachmentId,
  ) async {
    await request(
      'DELETE',
      '/api/v1/finance/journal-entries/$journalId/attachments/$attachmentId',
    );
  }

  /// Receipts and payments only: a refund has no files endpoint.
  Future<List<StockAttachmentRecord>> listSettlementAttachments(
    SettlementDirection direction,
    String settlementId,
  ) async =>
      _unwrapList(
        await request(
          'GET',
          '/api/v1/${direction.path}/$settlementId/attachments',
        ),
        StockAttachmentRecord.fromJson,
      );

  Future<List<StockAttachmentRecord>> attachToSettlement(
    SettlementDirection direction,
    String settlementId,
    List<Json> files,
  ) async =>
      _unwrapList(
        await request(
          'POST',
          '/api/v1/${direction.path}/$settlementId/attachments',
          body: {'attachments': files},
        ),
        StockAttachmentRecord.fromJson,
      );

  Future<void> removeSettlementAttachment(
    SettlementDirection direction,
    String settlementId,
    String attachmentId,
  ) async {
    await request(
      'DELETE',
      '/api/v1/${direction.path}/$settlementId/attachments/$attachmentId',
    );
  }

  /// Delete a hand-written draft. Its reference stays taken.
  Future<void> deleteJournalEntry(String id) =>
      request('DELETE', '/api/v1/finance/journal-entries/$id');

  /// Turn a hand-written draft away at review. It stays on record, final.
  Future<JournalEntry> rejectJournalEntry(String id, {String? reason}) async =>
      JournalEntry.fromJson(
        _unwrapMap(
          await request(
            'POST',
            '/api/v1/finance/journal-entries/$id/reject',
            body: {if (reason != null && reason.isNotEmpty) 'reason': reason},
          ),
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

  /// Where the firm's books stood on its cutover date (backlog 36), or the
  /// empty statement if nothing has ever been entered.
  Future<OpeningTrialBalance> getOpeningTrialBalance() async =>
      OpeningTrialBalance.fromJson(
        _unwrapMap(
          await request('GET', '/api/v1/finance/opening-trial-balance'),
        ),
      );

  /// Replace the whole opening trial balance; an empty `lines` list takes it
  /// off. Posts straight to the ledger, so it needs `JOURNAL_POST`.
  ///
  /// Returns the statement now standing alongside the server's message,
  /// which names every row a bad statement was refused on.
  Future<(OpeningTrialBalance, String)> replaceOpeningTrialBalance(
    Json body,
  ) async {
    final Json response = await request(
      'PUT',
      '/api/v1/finance/opening-trial-balance',
      body: body,
    );
    return (
      OpeningTrialBalance.fromJson(_unwrapMap(response)),
      stringValue(response['message']),
    );
  }

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
        return await request(
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
        final String code = stringValue(
          error is Map<String, dynamic> ? error['code'] : null,
        );
        throw ApiException(
          message.isEmpty
              ? 'Request failed (${response.statusCode}).'
              : message,
          statusCode: response.statusCode,
          details: error is Map<String, dynamic> ? error['details'] : null,
          code: code.isEmpty ? null : code,
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
        return await downloadText(path, query: query, retrying: true);
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
  ///
  /// [referenceCopy] prints a bill with no IRN yet, banner-marked "not a valid
  /// tax invoice", instead of being refused.
  Future<List<int>> salesInvoicePdf(String id, {bool referenceCopy = false}) =>
      downloadBytes(
        '/api/v1/sales-invoices/$id/print',
        query: referenceCopy ? <String, String>{'reference_copy': 'true'} : null,
      );

  /// The challan that travels with the goods.
  Future<List<int>> deliveryChallanPdf(String id) =>
      downloadBytes('/api/v1/delivery-notes/$id/print');

  /// What to pick from the shelves for these notes, products and batches
  /// summed over them (SEL-13).
  Future<List<int>> deliveryPickListPdf(List<String> noteIds) => downloadBytes(
        '/api/v1/delivery-notes/pick-list',
        method: 'POST',
        body: <String, dynamic>{'note_ids': noteIds},
      );

  /// What goes on each vehicle for these notes, in round order, with the
  /// amount to collect (SEL-13).
  Future<List<int>> deliveryLoadingSheetPdf(List<String> noteIds) =>
      downloadBytes(
        '/api/v1/delivery-notes/loading-sheet',
        method: 'POST',
        body: <String, dynamic>{'note_ids': noteIds},
      );

  /// The sales order as the PDF a customer is sent (MSG-4).
  Future<List<int>> salesOrderPdf(String id) =>
      downloadBytes('/api/v1/sales-orders/$id/print');

  /// The receipt as the PDF a customer is sent (MSG-4).
  Future<List<int>> receiptPdf(String id) =>
      downloadBytes('/api/v1/receipts/$id/print');

  /// The offer a customer is sent.
  Future<List<int>> quotationPdf(String id) =>
      downloadBytes('/api/v1/quotations/$id/print');

  /// The credit note a customer files.
  Future<List<int>> creditNotePdf(String id, {bool referenceCopy = false}) =>
      downloadBytes(
        '/api/v1/sales-returns/$id/print',
        query: referenceCopy ? <String, String>{'reference_copy': 'true'} : null,
      );

  /// The credit note raised against an invoice, as the PDF the customer files.
  /// Any status prints; a draft carries a DRAFT banner from the server.
  Future<List<int>> printCreditNote(String id, {bool referenceCopy = false}) =>
      downloadBytes(
        '/api/v1/credit-notes/$id/print',
        query: referenceCopy ? <String, String>{'reference_copy': 'true'} : null,
      );

  /// The debit note raised against an invoice, as the PDF the customer files.
  Future<List<int>> printCustomerDebitNote(
    String id, {
    bool referenceCopy = false,
  }) =>
      downloadBytes(
        '/api/v1/customer-debit-notes/$id/print',
        query: referenceCopy ? <String, String>{'reference_copy': 'true'} : null,
      );

  /// What is still waiting to be billed.
  ///
  /// Asked for rather than derived client-side: only the server knows how much
  /// of a delivery line earlier invoices already took, and a picker that
  /// guessed would offer documents the save then refuses.
  ///
  /// Every page of it: this read the newest 50 notes, so an older one still
  /// waiting could not be billed from the desktop at all (D-SELL-18).
  Future<List<BillableDocument>> billableDocuments() async {
    final List<BillableDocument> documents = <BillableDocument>[];
    final Set<String> seen = <String>{};
    for (int page = 1; page <= _pageBackstop; page++) {
      final Json response = await request(
        'GET',
        '/api/v1/sales-invoices/billable',
        query: {'limit': '$_pageCap', 'page': '$page'},
      );
      final dynamic data = response['data'];
      final int before = documents.length;
      for (final dynamic item in data is List ? data : const []) {
        if (item is! Map) continue;
        final BillableDocument document =
            BillableDocument.fromJson(Map<String, dynamic>.from(item));
        final String key =
            '${document.sourceDocumentType}:${document.sourceDocumentId}';
        if (seen.add(key)) documents.add(document);
      }
      if (documents.length == before) break;
    }
    return documents;
  }

  /// Raise a sales order without a quotation behind it.
  ///
  /// An order could only appear by converting a quotation, so a phone order
  /// had to be typed as a quotation and immediately accepted -- two documents
  /// and an acceptance the customer never gave.
  Future<Json> createSalesOrder(Json body) =>
      request('POST', '/api/v1/sales-orders', body: body);

  Future<Json> salesOrder(String id) =>
      request('GET', '/api/v1/sales-orders/$id');

  /// [expectedVersion] rides along as `If-Match`. The update replaces the
  /// whole line collection, so a lost race costs every line somebody entered
  /// rather than a single field.
  Future<Json> updateSalesOrder(
    String id,
    Json body, {
    int? expectedVersion,
  }) =>
      request(
        'PUT',
        '/api/v1/sales-orders/$id',
        body: body,
        expectedVersion: expectedVersion,
      );

  /// Stop an order progressing, without unwinding anything.
  ///
  /// The status is untouched, so releasing puts the order back exactly where
  /// it was. The reason is required rather than optional: the person who hits
  /// the refusal downstream is the one who has to get the hold lifted, and a
  /// blank reason tells them nothing.
  Future<Json> holdSalesOrder(String id, {required String reason}) => request(
        'POST',
        '/api/v1/sales-orders/$id/hold',
        body: <String, dynamic>{'reason': reason},
      );

  Future<Json> releaseSalesOrder(String id, {String? remarks}) => request(
        'POST',
        '/api/v1/sales-orders/$id/release',
        body: <String, dynamic>{if (remarks != null) 'reason': remarks},
      );

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
    String method = 'GET',
    Json? body,
    bool retrying = false,
  }) async {
    final Uri uri = _uri(path, query);
    onRequest?.call();
    try {
      final HttpClientRequest httpRequest =
          await _httpClient.openUrl(method, uri);
      httpRequest.followRedirects = false;
      if (body != null) {
        httpRequest.headers.contentType = ContentType.json;
        httpRequest.write(jsonEncode(body));
      }
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
        return await downloadBytes(path,
            query: query, method: method, body: body, retrying: true);
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        String message = 'The download request failed.';
        Object? details;
        String? code;
        try {
          final dynamic decoded = jsonDecode(utf8.decode(bytes));
          if (decoded is Map<String, dynamic>) {
            final dynamic error = decoded['error'];
            message = stringValue(
              error is Map<String, dynamic>
                  ? error['message']
                  : decoded['message'] ?? decoded['detail'],
            );
            if (error is Map<String, dynamic>) {
              details = error['details'];
              final String errorCode = stringValue(error['code']);
              code = errorCode.isEmpty ? null : errorCode;
            }
          }
        } on FormatException {
          // Keep the safe public error when the server did not return JSON.
        }
        throw ApiException(
          message.isEmpty ? 'The download request failed.' : message,
          statusCode: response.statusCode,
          details: details,
          code: code,
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
        return await multipartRequest(
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
        final String code = stringValue(
          error is Map<String, dynamic> ? error['code'] : null,
        );
        throw ApiException(
          message.isEmpty
              ? 'Request failed (${response.statusCode}).'
              : message,
          statusCode: response.statusCode,
          details: error is Map<String, dynamic> ? error['details'] : null,
          code: code.isEmpty ? null : code,
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
