import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/firms/firm_settings_page.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The business profile decides which features and modules a firm operates, and
/// its catalogue is a firm-owned table with no copy in the platform schema.
///
/// It used to be a dropdown inside the platform-level Firms dialog, which had
/// no firm context to read the catalogue with: the request resolved to the
/// platform schema and answered 503 every time the form was opened. It now
/// lives on the Firm Settings tab, where an active firm is the page's stated
/// precondition.
///
/// The cost of the move is real and deliberate: firm creation no longer asks
/// for a profile, so a new firm falls back to the platform default until
/// someone sets one. That is why the Firm Settings tab exists rather than the
/// field simply being deleted.

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

class _FirmApi extends ApiClient {
  _FirmApi({String? firmId, this.assignedProfile = 'profile-generic'})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => firmId,
        );

  final String assignedProfile;
  String? assignedFirmId;
  String? assignedProfileId;
  int profileCatalogueReads = 0;

  @override
  Future<List<AssignmentOption>> options(String resource) async {
    fail('the firm form must not read $resource without a firm context');
  }

  @override
  Future<PagedResult<Firm>> firms({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) async =>
      const PagedResult(items: <Firm>[], total: 0);

  @override
  Future<PagedResult<BusinessProfileRecord>> businessProfiles({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) async {
    profileCatalogueReads++;
    return const PagedResult(
      items: <BusinessProfileRecord>[
        BusinessProfileRecord(
          id: 'profile-generic',
          code: 'GENERIC',
          name: 'Generic',
          industryType: 'GENERIC',
          status: 'ACTIVE',
          isDefault: true,
          description: '',
        ),
        BusinessProfileRecord(
          id: 'profile-wholesale',
          code: 'WHOLESALE',
          name: 'Wholesale',
          industryType: 'WHOLESALE',
          status: 'ACTIVE',
          isDefault: false,
          description: '',
        ),
      ],
      total: 2,
    );
  }

  @override
  Future<void> assignBusinessProfileToFirm(
    String firmId,
    String businessProfileId, {
    bool isActive = true,
    String notes = '',
  }) async {
    assignedFirmId = firmId;
    assignedProfileId = businessProfileId;
  }

  @override
  Future<Map<String, dynamic>> firmBusinessProfileAssignmentValues(
    String firmId,
  ) async =>
      {'business_profile_id': assignedProfile, 'is_active': true, 'notes': ''};
}

Widget _page(_FirmApi api, PermissionService permissions, {String? firmId}) =>
    MaterialApp(
      home: Scaffold(
        body: FirmSettingsPage(
          api: api,
          permissions: permissions,
          hasActiveFirm: firmId != null,
          activeFirmId: firmId,
        ),
      ),
    );

void main() {
  test('the firm form no longer asks for a business profile', () {
    final api = _FirmApi();
    final ResourceDefinition<Firm> definition =
        firmDefinition(api, PermissionService(), showFrame: false);

    // The catalogue cannot be read from a platform-level page, so offering the
    // field here could only ever produce a 503.
    expect(
      definition.fields.any((field) => field.key == 'business_profile_id'),
      isFalse,
    );
    expect(definition.loadAssignments, isNull);
    expect(definition.saveAssignments, isNull);
  });

  test('the profile never travels in the firms API body', () {
    // /api/v1/firms forbids unknown fields, so leaking it would break creation.
    final api = _FirmApi();
    final ResourceDefinition<Firm> definition =
        firmDefinition(api, PermissionService(), showFrame: false);

    final Json body = definition.payload(
      {
        'code': 'WHOLE02',
        'name': 'Wholesale Two',
        'country': 'IN',
        'currency_code': 'INR',
        'deployment_mode': 'SHARED',
        'database_type': 'postgresql',
        'connection_profile': 'NODE_A',
      },
      true,
    );

    expect(body.containsKey('business_profile_id'), isFalse);
    expect(body['code'], 'WHOLE02');
    expect(body['deployment_mode'], 'SHARED');
    expect(body['connection_profile'], 'NODE_A');
  });

  testWidgets('firm settings asks for a firm before reading the catalogue',
      (tester) async {
    final api = _FirmApi();

    await tester
        .pumpWidget(_page(api, _withPermissions(const ['FIRM_UPDATE'])));
    await tester.pumpAndSettle();

    expect(find.byType(StandardEmptyState), findsOneWidget);
    expect(find.textContaining('Select a firm'), findsOneWidget);
    // The 503 this replaces came from asking anyway.
    expect(api.profileCatalogueReads, 0);
  });

  testWidgets('firm settings loads the catalogue for the active firm',
      (tester) async {
    final api = _FirmApi(firmId: 'firm-1');

    await tester.pumpWidget(
      _page(api, _withPermissions(const ['FIRM_UPDATE']), firmId: 'firm-1'),
    );
    await tester.pumpAndSettle();

    expect(api.profileCatalogueReads, 1);
    expect(find.text('GENERIC — Generic'), findsOneWidget);
  });

  testWidgets('choosing a profile assigns it to the active firm',
      (tester) async {
    final api = _FirmApi(firmId: 'firm-1');

    await tester.pumpWidget(
      _page(api, _withPermissions(const ['FIRM_UPDATE']), firmId: 'firm-1'),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('WHOLESALE — Wholesale').last);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Apply profile'));
    await tester.pumpAndSettle();

    expect(api.assignedFirmId, 'firm-1');
    expect(api.assignedProfileId, 'profile-wholesale');
  });

  testWidgets('a firm with no profile is warned, not left silent',
      (tester) async {
    // The framework falls back to the platform default instead of failing, so
    // an unassigned firm keeps working while running as GENERIC.
    final api = _FirmApi(firmId: 'firm-1', assignedProfile: '');

    await tester.pumpWidget(
      _page(api, _withPermissions(const ['FIRM_UPDATE']), firmId: 'firm-1'),
    );
    await tester.pumpAndSettle();

    expect(find.text('No business profile assigned'), findsOneWidget);
    // Says the consequence, not just the state.
    expect(
      find.textContaining('operating the wrong feature and module set'),
      findsOneWidget,
    );
  });

  testWidgets('an assigned firm shows no warning', (tester) async {
    final api = _FirmApi(firmId: 'firm-1');

    await tester.pumpWidget(
      _page(api, _withPermissions(const ['FIRM_UPDATE']), firmId: 'firm-1'),
    );
    await tester.pumpAndSettle();

    expect(find.text('No business profile assigned'), findsNothing);
  });

  test('creating a firm names the profile step it could not perform', () {
    final api = _FirmApi();
    final ResourceDefinition<Firm> definition =
        firmDefinition(api, PermissionService(), showFrame: false);

    final String? followUp = definition.createFollowUp?.call(const {});

    expect(followUp, isNotNull);
    expect(followUp, contains('Firm Settings'));
  });

  testWidgets('assignment is read-only without FIRM_UPDATE', (tester) async {
    final api = _FirmApi(firmId: 'firm-1');

    await tester.pumpWidget(
      _page(api, _withPermissions(const ['FIRM_VIEW']), firmId: 'firm-1'),
    );
    await tester.pumpAndSettle();

    final FilledButton apply = tester.widget(
      find.widgetWithText(FilledButton, 'Apply profile'),
    );
    expect(apply.onPressed, isNull);
    expect(find.textContaining('FIRM_UPDATE is required'), findsOneWidget);
  });
}
