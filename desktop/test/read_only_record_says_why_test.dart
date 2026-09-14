import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A record that cannot be edited says why on the dialog that opens.
///
/// Double-clicking a system role opened its read-only view with no word
/// about why: the refusal was wired to Edit, and a double-click opens View
/// (manual plan item 13.9, 2026-09-15).

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );
}

const Permission _system = Permission(
  id: 'r-1',
  code: 'SALES_MANAGER',
  name: 'Sales Manager',
  description: '',
  isActive: true,
);
const Permission _custom = Permission(
  id: 'r-2',
  code: 'manual-test-role',
  name: 'Manual test role',
  description: '',
  isActive: true,
);

ResourceDefinition<Permission> _definition() => ResourceDefinition<Permission>(
      title: 'Roles',
      resource: 'roles',
      headers: const ['Code', 'Name'],
      cells: (role) => [role.code, role.name],
      id: (role) => role.id,
      load: ({
        int page = 1,
        int pageSize = 20,
        String search = '',
        String sortBy = 'created_at',
        bool descending = true,
      }) async =>
          const PagedResult(items: [_system, _custom], total: 2),
      fields: const [FieldSpec(key: 'name', label: 'Name', required: true)],
      initialValues: (role) => {'name': role?.name ?? ''},
      payload: (values, _) => values,
      canEdit: (role) => role.id != _system.id,
      editRefusal: (role) =>
          role.id == _system.id ? 'System roles cannot be modified.' : null,
      dialogSubtitle: (role) => role.code,
    );

Future<void> _open(WidgetTester tester, String code) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1600, 900);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: ResourceManagementPage<Permission>(
        api: _Api(),
        definition: _definition(),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  final Finder row = find.text(code).first;
  await tester.tap(row);
  await tester.pump(const Duration(milliseconds: 50));
  await tester.tap(row);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('double-clicking a system role says it cannot be modified',
      (tester) async {
    await _open(tester, 'SALES_MANAGER');

    expect(
      find.text('SALES_MANAGER  ·  System roles cannot be modified.'),
      findsOneWidget,
    );
  });

  testWidgets('a record that can be edited says nothing of the kind',
      (tester) async {
    await _open(tester, 'manual-test-role');

    expect(find.textContaining('cannot be modified'), findsNothing);
    expect(find.text('manual-test-role'), findsWidgets);
  });
}
