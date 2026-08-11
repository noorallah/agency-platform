import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Creating a firm meant filling 22 fields, each on its own full-width row, in
/// a form capped at 1100px -- most of a screen of scrolling for a form whose
/// controls used little more than half the width. Three of those fields have an
/// obvious answer for this deployment and should already be filled in.

class _FirmApi extends ApiClient {
  _FirmApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  @override
  Future<PagedResult<Firm>> firms({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) async =>
      const PagedResult(items: <Firm>[], total: 0);
}

void main() {
  group('financial year default', () {
    test('on or after 1 April it is this year', () {
      expect(
        currentFinancialYearStart(today: DateTime(2026, 8, 11)),
        '2026-04-01',
      );
      expect(
        currentFinancialYearStart(today: DateTime(2026, 4, 1)),
        '2026-04-01',
      );
    });

    test('before 1 April it is last year', () {
      // 31 March still belongs to the financial year that began the previous
      // April -- the boundary is the whole reason this is computed.
      expect(
        currentFinancialYearStart(today: DateTime(2026, 3, 31)),
        '2025-04-01',
      );
      expect(
        currentFinancialYearStart(today: DateTime(2026, 1, 9)),
        '2025-04-01',
      );
    });
  });

  test('a new firm starts with the values this deployment always uses', () {
    final ResourceDefinition<Firm> definition =
        firmDefinition(_FirmApi(), PermissionService(), showFrame: false);

    final Map<String, dynamic> values = definition.initialValues(null);

    expect(values['currency_code'], 'INR');
    expect(values['country'], 'IN');
    expect(values['financial_year_start'], endsWith('-04-01'));
    // Defaults, not decisions: they travel in the payload like any other value
    // and the user can change them first.
    expect(
      definition.payload(values, true)['currency_code'],
      'INR',
    );
  });

  test('editing an existing firm shows its own values, not the defaults', () {
    final ResourceDefinition<Firm> definition =
        firmDefinition(_FirmApi(), PermissionService(), showFrame: false);

    final Map<String, dynamic> values = definition.initialValues(
      Firm.fromJson(const {
        'id': 'firm-1',
        'code': 'GBP01',
        'name': 'London Office',
        'country': 'GB',
        'currency_code': 'GBP',
        'financial_year_start': '2026-01-01',
      }),
    );

    expect(values['currency_code'], 'GBP');
    expect(values['country'], 'GB');
    expect(values['financial_year_start'], '2026-01-01');
  });

  testWidgets('short fields pair up and long ones keep the full row',
      (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1600, 1000);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: CrudWorkspaceDialog(
            title: 'Firms',
            mode: CrudDialogMode.create,
            api: _FirmApi(),
            twoColumn: true,
            values: const {},
            fields: const [
              FieldSpec(key: 'code', label: 'Firm code'),
              FieldSpec(key: 'name', label: 'Display name'),
              FieldSpec(key: 'notes', label: 'Notes', multiline: true),
            ],
            onSave: (_) async {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    double widthOf(String label) => tester
        .getSize(find
            .ancestor(
              of: find.text(label),
              matching: find.byType(SizedBox),
            )
            .first)
        .width;

    // The two short fields share a row; the notes box does not sit beside an
    // empty half-row.
    expect(widthOf('Firm code'), closeTo(widthOf('Display name'), 1));
    expect(widthOf('Notes'), greaterThan(widthOf('Firm code') * 1.8));
  });

  testWidgets('a form can still opt out and stack its fields', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1600, 1000);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: CrudWorkspaceDialog(
            title: 'Users',
            mode: CrudDialogMode.create,
            api: _FirmApi(),
            // Pairing is the default now; a form whose fields are all long
            // enough that pairing would cramp both can still say no.
            twoColumn: false,
            values: const {},
            fields: const [
              FieldSpec(key: 'code', label: 'Firm code'),
              FieldSpec(key: 'name', label: 'Display name'),
            ],
            onSave: (_) async {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // The escape hatch holds: nothing is wrapped, the fields stack.
    expect(find.byType(Wrap), findsNothing);
  });

  test('the two fields nobody can guess explain themselves', () {
    // "A valid E.164 phone number is required." never shows the shape it
    // wants, and a connection profile is a name that exists only in the
    // deployment's configuration. Both had to be asked about.
    final ResourceDefinition<Firm> definition =
        firmDefinition(_FirmApi(), PermissionService(), showFrame: false);

    String helperFor(String key) =>
        definition.fields.firstWhere((field) => field.key == key).helperText ??
        '';

    expect(helperFor('contact_phone'), contains('+91'),
        reason: 'the example is the whole point of the hint');
    expect(helperFor('contact_phone'), contains('country code'));
    expect(helperFor('connection_profile'), contains('REMOTE_A'));
    expect(helperFor('connection_profile'), contains('platform server'));
  });
}
