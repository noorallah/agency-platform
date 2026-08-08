import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A firm that is created without a business profile silently falls back to the
/// platform default, so a wholesale business can end up running as GENERIC. The
/// creation form must therefore ask for one and assign it.
class _FirmApi extends ApiClient {
  _FirmApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  Json? createdFirmBody;
  String? assignedFirmId;
  String? assignedProfileId;

  @override
  Future<List<AssignmentOption>> options(String resource) async {
    expect(
      resource,
      'business-framework/profiles',
      reason: 'the selector must read the real profile catalogue',
    );
    return const [
      AssignmentOption(id: 'profile-generic', label: 'GENERIC'),
      AssignmentOption(id: 'profile-wholesale', label: 'WHOLESALE'),
    ];
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
  Future<Json> create(String resource, Json body) async {
    createdFirmBody = body;
    return {
      'data': {
        'id': 'firm-new',
        'code': 'WHOLE02',
        'name': 'Wholesale Two',
        'country': 'IN',
        'currency_code': 'INR',
        'is_active': true,
      }
    };
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
      {'business_profile_id': '', 'is_active': true, 'notes': ''};
}

void main() {
  testWidgets('the firm form offers a business profile selector',
      (tester) async {
    final api = _FirmApi();
    final permissions = PermissionService();

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ResourceManagementPage<Firm>(
            api: api,
            definition: firmDefinition(api, permissions, showFrame: false),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final ResourceDefinition<Firm> definition =
        firmDefinition(api, permissions, showFrame: false);
    final FieldSpec profileField = definition.fields
        .firstWhere((field) => field.key == 'business_profile_id');

    expect(profileField.label, 'Business profile');
    expect(profileField.optionsResource, 'business-framework/profiles');
    expect(profileField.singleSelection, isTrue);
    expect(
      profileField.requiredOnCreate,
      isTrue,
      reason: 'a firm created without one silently becomes GENERIC',
    );
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
        'business_profile_id': 'profile-wholesale',
      },
      true,
    );

    expect(body.containsKey('business_profile_id'), isFalse);
    expect(body['code'], 'WHOLE02');
    expect(body['deployment_mode'], 'SHARED');
  });

  test('saving assigns the chosen profile to the new firm', () async {
    final api = _FirmApi();
    final ResourceDefinition<Firm> definition =
        firmDefinition(api, PermissionService(), showFrame: false);

    await definition.saveAssignments!(
      'firm-new',
      {'business_profile_id': 'profile-wholesale'},
    );

    expect(api.assignedFirmId, 'firm-new');
    expect(api.assignedProfileId, 'profile-wholesale');
  });

  test('an unselected profile is skipped rather than sent empty', () async {
    final api = _FirmApi();
    final ResourceDefinition<Firm> definition =
        firmDefinition(api, PermissionService(), showFrame: false);

    await definition.saveAssignments!('firm-new', {'business_profile_id': ''});

    expect(api.assignedProfileId, isNull);
  });
}
