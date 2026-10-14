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
    this.toolsLabel = 'Check',
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

  /// What a tool's tab says before its label: "Check" for a tool that
  /// checks the steps, "Yours" for one that is the signed-in person's own
  /// rather than the firm's.
  final String toolsLabel;

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

/// The subjects there are: Firm, Selling, Buying and Tax. Each other section
/// of Settings joins by adding an entry here and a route beside
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

  /// Firm (row T2). Financial Years is the one step that can be To do:
  /// nothing posts without an open year. My Branch and Warehouse is the
  /// signed-in person's own, so it stands apart as a tool.
  static const SettingsSubject firm = SettingsSubject(
    section: 'Firm',
    route: MenuLayout.firmSubjectRoute,
    summary: 'Business profile, financial years, numbering, custom fields',
    sectionCode: 'firm',
    steps: [
      SubjectStep(
        path: 'masters/firm-settings',
        label: 'Firm settings',
        code: 'firm-profile',
        summary: "The firm's business profile, which decides the features "
            'and modules it works with.',
        topLine: 'Start here: the business profile decides what the later '
            'steps offer.',
      ),
      SubjectStep(
        path: 'masters/financial-years',
        label: 'Financial years',
        code: 'financial-years',
        summary: 'The years the books are kept in. Nothing can be posted '
            'without an open year.',
        topLine: 'Needs nothing from the steps before. Open the current '
            'year before any bill is raised.',
      ),
      SubjectStep(
        path: 'administration/numbering-series',
        label: 'Numbering',
        code: 'numbering-series',
        summary: 'How each kind of document is numbered, such as '
            'INV/2026-27/0001.',
        topLine: 'A series can carry the financial year from step 2. Leave '
            'the defaults unless the firm numbers its own way.',
      ),
      SubjectStep(
        path: 'administration/goods-types',
        label: 'Goods types',
        code: 'goods-types',
        summary: 'The kinds of goods the firm deals in, and what each one '
            'tracks.',
        topLine: 'Needs nothing from the steps before.',
      ),
      SubjectStep(
        path: 'administration/firm-custom-fields',
        label: 'Custom fields',
        code: 'custom-fields',
        summary: "Extra fields of the firm's own on customers, products and "
            'documents.',
        topLine: 'Needs nothing from the steps before. Add a field here '
            'before a rule in the next step can name it.',
      ),
      SubjectStep(
        path: 'administration/firm-custom-field-rules',
        label: 'Custom field rules',
        code: 'custom-field-rules',
        summary: 'Where a custom field is asked for, and whether it must be '
            'filled.',
        topLine: 'A rule names a field from the step before. Add the field '
            'first if it is not in the list.',
      ),
      SubjectStep(
        path: MenuLayout.messagingRoute,
        label: 'Messaging',
        code: 'messaging',
        summary: "Email, WhatsApp and SMS from the firm's own accounts, and "
            'which events send them.',
        topLine: 'Needs nothing from the steps before. Off until the firm '
            'switches it on.',
      ),
      SubjectStep(
        path: MenuLayout.approvalRulesRoute,
        label: 'Approval levels',
        code: 'approval-levels',
        summary: 'Which documents need approving, and by whom.',
        topLine: 'Needs nothing from the steps before. Without levels, a '
            'document is approved by whoever may approve it.',
      ),
    ],
    toolsLabel: 'Yours',
    tools: [
      SubjectStep(
        path: MenuLayout.workDefaultsRoute,
        label: 'My branch and warehouse',
        summary: "Your own usual branch and warehouse, not the firm's.",
        topLine: "Yours, not the firm's: the branch and warehouse a new "
            'document starts with when you raise it.',
      ),
    ],
    connects: [
      'Business profile',
      'Financial year',
      'Numbering',
      'Documents',
    ],
    connectsNote: 'Your usual branch and warehouse are yours, not the '
        "firm's, so they stand apart from the steps: Yours: My branch and "
        'warehouse.',
    readyNote: 'The firm is ready.',
    readyDetail: 'A financial year is open, so documents can be posted. The '
        'optional steps can wait until the firm needs them.',
  );

  /// Selling (row T2). Salesmen is To do only when Sales Stages makes a
  /// salesman required on a bill.
  static const SettingsSubject selling = SettingsSubject(
    section: 'Selling',
    route: MenuLayout.sellingSubjectRoute,
    summary: 'Sales stages, salesmen, credit, prices, loyalty, TCS',
    sectionCode: 'selling',
    steps: [
      SubjectStep(
        path: MenuLayout.salesStagesRoute,
        label: 'Sales stages',
        code: 'sales-stages',
        summary: 'Which stages of a sale people type, and which the system '
            'raises itself.',
        topLine: 'Start here: the stages decide what the later steps ask '
            'for.',
      ),
      SubjectStep(
        path: 'sales/salesmen',
        label: 'Salesmen',
        code: 'salesmen',
        summary: "The firm's own list of salesmen, named on a bill.",
        topLine: 'To do only when Sales stages makes a salesman required on '
            'a bill.',
      ),
      SubjectStep(
        path: MenuLayout.creditControlRoute,
        label: 'Credit control',
        code: 'credit-control',
        summary: "Whether a customer's credit limit only warns or also "
            'blocks a sale.',
        topLine: 'Needs nothing from the steps before. Warns at 80% until '
            'changed.',
      ),
      SubjectStep(
        path: MenuLayout.priceFloorRoute,
        label: 'Price floor',
        code: 'price-floor',
        summary: 'The lowest price an item may be sold at.',
        topLine: 'Needs nothing from the steps before.',
      ),
      SubjectStep(
        path: MenuLayout.discountLimitsRoute,
        label: 'Discount limits',
        code: 'discount-limits',
        summary: 'The most discount each role may give on a line.',
        topLine: 'Needs nothing from the steps before.',
      ),
      SubjectStep(
        path: MenuLayout.loyaltySchemeRoute,
        label: 'Loyalty scheme',
        code: 'loyalty-scheme',
        summary: 'Points customers earn on a sale and spend on a bill.',
        topLine: 'Needs nothing from the steps before. Off unless the firm '
            'runs a scheme.',
      ),
      SubjectStep(
        path: MenuLayout.tcsSettingsRoute,
        label: 'TCS',
        code: 'tcs',
        summary: 'Tax collected at source on what customers pay.',
        topLine: 'Needs nothing from the steps before. Off unless the firm '
            'collects.',
      ),
    ],
    connects: ['Sales stages', 'Salesman on a bill'],
    readyNote: 'Selling is ready for this firm.',
    readyDetail: 'Nothing here has to be done before a sale. The optional '
        'steps can wait until the firm needs them.',
  );

  /// Buying (row T2).
  static const SettingsSubject buying = SettingsSubject(
    section: 'Buying',
    route: MenuLayout.buyingSubjectRoute,
    summary: 'Purchase settings, approval limits, budgets',
    sectionCode: 'buying',
    steps: [
      SubjectStep(
        path: 'purchases/purchase-settings',
        label: 'Purchase settings',
        code: 'purchase-settings',
        summary: 'How purchase orders and bills behave for this firm.',
        topLine: 'Start here. Needs nothing from the steps before.',
      ),
      SubjectStep(
        path: MenuLayout.approvalLimitsRoute,
        label: 'Approval limits',
        code: 'approval-limits',
        summary: 'How large a purchase order each person may approve.',
        topLine: 'Needs nothing from the steps before.',
      ),
      SubjectStep(
        path: MenuLayout.purchaseBudgetsRoute,
        label: 'Purchase budgets',
        code: 'purchase-budgets',
        summary: 'How much may be bought in a period.',
        topLine: 'Needs nothing from the steps before. Off unless the firm '
            'budgets.',
      ),
    ],
    readyNote: 'Buying is ready for this firm.',
    readyDetail: 'Nothing here has to be done before a purchase. The '
        'optional steps can wait until the firm needs them.',
  );

  static const List<SettingsSubject> all = [firm, selling, buying, tax];

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
