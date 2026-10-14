import 'menu_layout.dart';

/// One tab of a Settings subject: a step in the order the subject is set up
/// in, or a tool for checking it.
///
/// It **declares no screen**. [path] names an item already in
/// [MenuLayout.settings], so what the tab opens, who is offered it and what
/// search calls it are all still said there, once.
class SubjectStep {
  const SubjectStep({
    required this.path,
    required this.label,
    required this.summary,
    required this.topLine,
    this.code,
  });

  /// The path of the [MenuLayout.settings] item this tab shows.
  final String path;

  /// What the tab says, which is shorter than the item's own label.
  final String label;

  /// One line saying what it is, for its row on Start here.
  final String summary;

  /// Said above the screen: what it is for, and what it needs from the step
  /// before.
  final String topLine;

  /// The server's code for the step's state; null for a tool, which has none.
  final String? code;

  /// The item it opens, read from the menu catalogue.
  MenuItemSpec get item => MenuLayout.settings.item(path)!;
}

/// A section of Settings that opens as one screen (backlog 148): a Start here
/// tab, its steps in order, and its checking tools set apart.
class SettingsSubject {
  const SettingsSubject({
    required this.section,
    required this.route,
    required this.summary,
    required this.sectionCode,
    required this.steps,
    this.tools = const [],
    this.connects = const [],
    this.connectsNote = '',
    required this.readyNote,
    required this.readyDetail,
  });

  /// The label of the [MenuLayout.settings] section it stands for.
  final String section;

  /// Its open-screen tab's address.
  final String route;

  /// One line for its card on the Settings page.
  final String summary;

  /// What the server calls the section.
  final String sectionCode;

  final List<SubjectStep> steps;
  final List<SubjectStep> tools;

  /// "How they connect", link by link.
  final List<String> connects;

  /// Said after [connects].
  final String connectsNote;

  /// Said on Start here when no step is left to do.
  final String readyNote;
  final String readyDetail;

  /// The page as an item, for its tab's label.
  MenuItemSpec get page => MenuLayout.itemFor(route)!;

  /// Steps then tools: every tab but Start here.
  Iterable<SubjectStep> get entries => [...steps, ...tools];

  /// A step's number, which is its place in the full list whoever is asking.
  int numberOf(SubjectStep step) => steps.indexOf(step) + 1;
}

/// The subjects there are. Only Tax so far; each other section of Settings
/// joins by adding an entry here and a route beside
/// [MenuLayout.taxSubjectRoute].
abstract final class SettingsSubjects {
  static const SettingsSubject tax = SettingsSubject(
    section: 'Tax',
    route: MenuLayout.taxSubjectRoute,
    summary: 'GST rates and rules, GST on documents, TDS',
    sectionCode: 'tax',
    steps: [
      SubjectStep(
        path: 'administration/tax-configuration',
        label: 'Rates and profiles',
        code: 'rates-and-profiles',
        summary: 'The tax rates (CGST, SGST, IGST, cess) and the profiles '
            'that put them together, such as GST 18%.',
        topLine: 'Start here: a rule in step 2 can only pick a profile that '
            'exists.',
      ),
      SubjectStep(
        path: 'administration/tax-rules-page',
        label: 'Tax rules',
        code: 'tax-rules',
        summary: "Which profile applies to a line: by the product's tax "
            "group, HSN, the customer's state and so on. The first rule that "
            'matches wins.',
        topLine: 'A rule picks one profile from step 1 for a line. Add the '
            'profile first if it is not in the list.',
      ),
      SubjectStep(
        path: 'administration/tax-settings',
        label: 'Tax settings',
        code: 'tax-settings',
        summary: 'How tax is rounded and shown for this firm.',
        topLine: 'Needs nothing from the steps before. Leave it as it comes '
            'unless your accountant asks.',
      ),
      SubjectStep(
        path: MenuLayout.gstDocumentsRoute,
        label: 'GST on documents',
        code: 'gst-documents',
        summary: 'E-invoice and e-way bill for this firm.',
        topLine: 'Needs nothing from the steps before. Switch on only when '
            'the firm must raise them.',
      ),
      SubjectStep(
        path: MenuLayout.tds194qSettingsRoute,
        label: 'TDS on purchases',
        code: 'tds-purchases',
        summary: 'Tax deducted when you pay a supplier (194Q, 194C, 194J).',
        topLine: 'Needs nothing from the steps before. Off unless the firm '
            'deducts.',
      ),
    ],
    tools: [
      SubjectStep(
        path: 'administration/tax-rule-simulator',
        label: 'Rule simulator',
        summary: 'See which rule a bill would take.',
        topLine: 'See which rule a bill would take.',
      ),
      SubjectStep(
        path: 'administration/tax-execution-log',
        label: 'Execution log',
        summary: 'What the rules did on real documents.',
        topLine: 'What the rules did on real documents.',
      ),
    ],
    connects: [
      'Rate',
      'Profile (GST 18%)',
      'Rule picks the profile',
      'Line on a bill',
    ],
    connectsNote: 'To see which rule a bill would take before raising it, '
        'use Check: Rule simulator.',
    readyNote: 'Tax is ready for this firm.',
    readyDetail: 'Nothing here has to be done before a bill is raised. The '
        'optional steps can wait until the firm needs them.',
  );

  static const List<SettingsSubject> all = [tax];

  /// The subject that stands for the Settings section called [label].
  static SettingsSubject? forSection(String label) {
    for (final SettingsSubject subject in all) {
      if (subject.section == label) return subject;
    }
    return null;
  }

  /// The subject whose screen [path] addresses.
  static SettingsSubject? forRoute(String path) {
    for (final SettingsSubject subject in all) {
      if (subject.route == path) return subject;
    }
    return null;
  }
}
