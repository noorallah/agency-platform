import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter_test/flutter_test.dart';

/// Every screen under Administration used to render the same heading and the
/// same trail -- "Workspace / Administration / Administration" above the module's
/// one general sentence -- because the header was built from the module and the
/// breadcrumb was a `const`. Opening Users, Roles or Permissions looked
/// identical, so nothing on the page said which one you were on.

void main() {
  test('the heading names the screen, not the module', () {
    expect(administrationHeaderFor('users').title, 'Users');
    expect(administrationHeaderFor('roles').title, 'Roles');
    expect(administrationHeaderFor('permissions').title, 'Permissions');
  });

  test('the trail ends at the screen, so it changes as you move', () {
    expect(
      administrationHeaderFor('roles').breadcrumbs,
      ['Workspace', 'Administration', 'Roles'],
    );
    expect(
      administrationHeaderFor('users').breadcrumbs,
      isNot(administrationHeaderFor('roles').breadcrumbs),
    );
  });

  test('the description describes the screen', () {
    final String users = administrationHeaderFor('users').description;
    final String permissions =
        administrationHeaderFor('permissions').description;

    expect(users, isNot(permissions));
    expect(permissions, contains('permissions'));
  });

  test('every Administration screen gets a header of its own', () {
    // The real guarantee: no two tabs render the same heading, which is the
    // defect restated.
    final List<String> titles = ModuleCatalog.byId(AppModule.administration)
        .tabs
        .where((tab) => tab.available)
        .map((tab) => administrationHeaderFor(tab.id).title)
        .toList();

    expect(titles.toSet(), hasLength(titles.length));
  });

  test('an unknown tab falls back to the module rather than showing nothing',
      () {
    final AdministrationHeader header = administrationHeaderFor('not-a-tab');

    expect(header.title, 'Administration');
    expect(header.description, isNotEmpty);
  });
}
