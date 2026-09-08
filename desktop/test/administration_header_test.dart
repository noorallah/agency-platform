import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter_test/flutter_test.dart';

/// Every screen under Administration used to render the same heading and the
/// same trail -- "Workspace / Administration / Administration" above the module's
/// one general sentence -- because the header was built from the module and the
/// breadcrumb was a `const`. Opening Users, Roles or Permissions looked
/// identical, so nothing on the page said which one you were on.
///
/// Roles and Permissions have since become one sidebar entry, so those two
/// deliberately share a heading -- the entry's name -- and are told apart by
/// the tab strip inside the page and by their descriptions.

void main() {
  test('the heading names the screen, not the module', () {
    expect(administrationHeaderFor('users').title, 'Users');
    expect(administrationHeaderFor('user-templates').title, 'User Templates');
  });

  test('a grouped tab takes the sidebar entry as its heading', () {
    // The heading names the page somebody opened; the strip inside it names
    // the half. Two headings for one sidebar entry would read as two pages.
    expect(administrationHeaderFor('roles').title, 'Roles & Permissions');
    expect(
        administrationHeaderFor('permissions').title, 'Roles & Permissions');
  });

  test('the trail ends at the screen, so it changes as you move', () {
    expect(
      administrationHeaderFor('roles').breadcrumbs,
      ['Workspace', 'Administration', 'Roles & Permissions'],
    );
    expect(
      administrationHeaderFor('users').breadcrumbs,
      isNot(administrationHeaderFor('roles').breadcrumbs),
    );
  });

  test('the description describes the screen', () {
    final String users = administrationHeaderFor('users').description;
    final String roles = administrationHeaderFor('roles').description;
    final String permissions =
        administrationHeaderFor('permissions').description;

    expect(users, isNot(permissions));
    expect(permissions, contains('permissions'));
    // The two halves of one entry share a heading, so the description is
    // what still tells them apart.
    expect(roles, isNot(permissions));
  });

  test('every Administration entry gets a header of its own', () {
    // The real guarantee: no two sidebar entries render the same heading,
    // which is the defect restated. Tabs sharing an entry share its heading
    // on purpose, so the unit here is the entry, not the tab.
    final Map<String, String> titles = {
      for (final ModuleTabDefinition tab
          in ModuleCatalog.byId(AppModule.administration).tabs)
        if (tab.available)
          tab.group ?? tab.id: administrationHeaderFor(tab.id).title,
    };

    expect(titles.values.toSet(), hasLength(titles.length));
  });

  test('an unknown tab falls back to the module rather than showing nothing',
      () {
    final AdministrationHeader header = administrationHeaderFor('not-a-tab');

    expect(header.title, 'Administration');
    expect(header.description, isNotEmpty);
  });
}
