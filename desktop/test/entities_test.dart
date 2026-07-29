import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/core/api/api_client.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('firm parsing maps the backend FirmResponse fields', () {
    final Firm firm = Firm.fromJson({
      'id': 'firm-1',
      'code': 'ACME',
      'name': 'Acme Agency',
      'gst_number': 'GST-123',
      'pan_number': 'PAN-123',
      'country': 'US',
      'currency_code': 'USD',
      'financial_year_start': '2026-01-01',
      'is_active': false,
    });

    expect(firm.id, 'firm-1');
    expect(firm.gstNumber, 'GST-123');
    expect(firm.currencyCode, 'USD');
    expect(firm.financialYearStart, '2026-01-01');
    expect(firm.isActive, isFalse);
    expect(firm.toJson(), containsPair('currency_code', 'USD'));
  });

  test('role and user parsing matches CRUD response fields', () {
    final Role role = Role.fromJson({
      'id': 'role-1',
      'code': 'manager',
      'name': 'Manager',
    });
    final PlatformUser user = PlatformUser.fromJson({
      'id': 'user-1',
      'email': 'manager@acme.test',
      'full_name': 'Agency Manager',
      'expires_at': '2026-12-31T00:00:00Z',
    });

    expect(role.code, 'manager');
    expect(user.expiresAt, '2026-12-31T00:00:00Z');
  });

  test('auth token parsing accepts a wrapped rotating token response', () {
    final AuthTokens tokens = AuthTokens.fromJson({
      'data': {
        'access_token': 'access',
        'refresh_token': 'rotated-refresh',
        'must_change_password': true,
      },
    });

    expect(tokens.accessToken, 'access');
    expect(tokens.refreshToken, 'rotated-refresh');
    expect(tokens.forcePasswordChange, isTrue);
  });

  test('paged response reads the standard pagination total_records value', () {
    final PagedResult<Permission> page = ApiClient.parsePagedResponse(
      {
        'data': [
          {'id': 'permission-1', 'code': 'users.read', 'name': 'Read users'},
        ],
        'pagination': {'total_records': 41},
      },
      Permission.fromJson,
    );

    expect(page.items.single.code, 'users.read');
    expect(page.total, 41);
  });

  test('primary firm is included in the membership assignment payload', () {
    final Json payload = ApiClient.userFirmAssignmentsPayload(
      ['firm-1'],
      'firm-primary',
    );
    final List<dynamic> assignments = payload['assignments'] as List<dynamic>;

    expect(assignments, hasLength(2));
    expect(
      assignments,
      contains(
        {
          'firm_id': 'firm-primary',
          'is_primary': true,
          'is_active': true,
        },
      ),
    );
  });
}
