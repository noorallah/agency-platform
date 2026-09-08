import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/firms/firm_setup_dialog.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A firm is finished from the platform side, on one panel.
///
/// Creating a firm records the intent; its storage, books, profile, tax and
/// first branch are each a separate act. The panel reads the same readiness
/// list the shell script prints, does the two steps that can be done from the
/// platform side -- provision storage, open the books -- and names the screen
/// for the rest.

Firm _firm({String mode = 'SHARED', bool provisioned = true}) =>
    Firm.fromJson({
      'id': 'firm-1',
      'code': 'ACME',
      'name': 'Acme Distributors',
      'deployment_mode': mode,
      'provisioned_at': provisioned ? '2026-09-08T10:00:00Z' : '',
      'is_active': true,
    });

Map<String, dynamic> _step(
  String key,
  String label,
  String status, {
  required bool required,
  String detail = '',
}) =>
    {
      'key': key,
      'label': label,
      'status': status,
      'detail': detail,
      'required': required,
    };

Map<String, dynamic> _readiness({
  String storage = 'DONE',
  String books = 'MISSING',
  String others = 'MISSING',
}) =>
    {
      'firm_id': 'firm-1',
      'code': 'ACME',
      'name': 'Acme Distributors',
      'deployment_mode': 'SHARED',
      'storage_provisioned': storage == 'DONE',
      'can_post': storage == 'DONE' && books == 'DONE',
      'ready': storage == 'DONE' && books == 'DONE' && others == 'DONE',
      'steps': [
        _step('storage', 'Storage', storage,
            required: true, detail: 'Shared store; nothing to provision.'),
        _step('business_profile', 'Business profile', others,
            required: false, detail: 'None assigned.'),
        _step('books', 'Books', books,
            required: true,
            detail: books == 'DONE'
                ? '24 accounts, all 24 control accounts mapped.'
                : 'No chart of accounts.'),
        _step('tax', 'Tax', others, required: false, detail: 'No tax profiles.'),
        _step('geography', 'Geography', others,
            required: false, detail: 'No country in the store.'),
        _step('branches', 'Branches and warehouses', others,
            required: false, detail: '0 branches, 0 warehouses so far.'),
        _step('members', 'People', others,
            required: false, detail: 'Nobody belongs to this firm yet.'),
      ],
    };

class _Api extends ApiClient {
  _Api({required this.answers, this.refuse})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  /// Successive readiness answers: the panel re-reads after every action.
  final List<Map<String, dynamic>> answers;
  final String? refuse;
  int reads = 0;
  final List<String> opened = [];
  final List<String> provisioned = [];
  final List<String> taxed = [];
  final List<(String, String)> assigned = [];
  int catalogueReads = 0;

  @override
  Future<FirmReadiness> firmReadiness(String firmId) async {
    final Map<String, dynamic> answer =
        answers[reads < answers.length ? reads : answers.length - 1];
    reads += 1;
    return FirmReadiness.fromJson(answer);
  }

  @override
  Future<String> openFirmBooks(String firmId) async {
    if (refuse != null) throw ApiException(refuse!, statusCode: 422);
    opened.add(firmId);
    return 'Books opened for the year starting 2026-04-01.';
  }

  @override
  Future<String> provisionFirmStorage(String firmId) async {
    provisioned.add(firmId);
    return 'Firm storage provisioned.';
  }

  @override
  Future<String> applyFirmTaxTemplate(String firmId) async {
    taxed.add(firmId);
    return 'GST set up: 8 tax profiles and 6 rules.';
  }

  @override
  Future<List<BusinessProfileRecord>> firmProfileCatalogue(
    String firmId,
  ) async {
    catalogueReads += 1;
    return [
      BusinessProfileRecord.fromJson(const {
        'id': 'p-generic',
        'code': 'GENERIC',
        'name': 'Generic',
        'industry_type': 'GENERIC',
        'status': 'ACTIVE',
        'is_default': true,
      }),
      BusinessProfileRecord.fromJson(const {
        'id': 'p-wholesale',
        'code': 'WHOLESALE',
        'name': 'Wholesale',
        'industry_type': 'WHOLESALE',
        'status': 'ACTIVE',
        'is_default': false,
      }),
    ];
  }

  @override
  Future<void> assignBusinessProfileToFirm(
    String firmId,
    String businessProfileId, {
    bool isActive = true,
    String notes = '',
  }) async {
    assigned.add((firmId, businessProfileId));
  }

  @override
  Future<PagedResult<Firm>> firms({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) async =>
      PagedResult(items: [_firm()], total: 1);
}

/// Opens the panel and returns a sink the dialog's answer lands in when it
/// closes, so a test can close it later and then read what it said.
Future<List<bool>> _open(WidgetTester tester, _Api api, {Firm? firm}) async {
  final List<bool> answers = [];
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () async => answers.add(await showFirmSetupDialog(
            context,
            api: api,
            firm: firm ?? _firm(),
          )),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  return answers;
}

void main() {
  group('the panel', () {
    testWidgets('lists every step with its verdict and where to do it',
        (tester) async {
      await _open(tester, _Api(answers: [_readiness()]));

      expect(find.text('Set up ACME'), findsOneWidget);
      expect(find.text('Cannot post documents yet.'), findsOneWidget);
      for (final String label in [
        'Storage',
        'Business profile',
        'Books',
        'Tax',
        'Geography',
        'Branches and warehouses',
        'People',
      ]) {
        expect(find.text(label), findsOneWidget, reason: label);
      }
      // Required and recommended are told apart on the row.
      expect(find.text('Required'), findsNWidgets(2));
      expect(find.text('Recommended'), findsNWidgets(5));
      // A step with no button here says where it is done.
      expect(find.text(firmSetupHints['branches']!), findsOneWidget);
      expect(find.text(firmSetupHints['members']!), findsOneWidget);
      // And the ones with a button offer it.
      expect(find.widgetWithText(FilledButton, 'Open the books'), findsOneWidget);
      expect(
        find.widgetWithText(FilledButton, 'Apply GST template'),
        findsOneWidget,
      );
      expect(find.byKey(const ValueKey('firm-setup-profile')), findsOneWidget);
    });

    testWidgets('Apply GST template calls the route and re-reads',
        (tester) async {
      final _Api api = _Api(answers: [_readiness(), _readiness(others: 'DONE')]);
      await _open(tester, api);

      await tester.ensureVisible(find.widgetWithText(FilledButton, 'Apply GST template'));
      await tester.tap(find.widgetWithText(FilledButton, 'Apply GST template'));
      await tester.pumpAndSettle();

      expect(api.taxed, ['firm-1']);
      expect(find.textContaining('8 tax profiles'), findsOneWidget);
      expect(
        find.widgetWithText(FilledButton, 'Apply GST template'),
        findsNothing,
      );
    });

    testWidgets("the profile is chosen from the firm's own catalogue",
        (tester) async {
      final _Api api = _Api(answers: [_readiness(), _readiness(others: 'DONE')]);
      await _open(tester, api);
      expect(api.catalogueReads, 1);
      // Nothing chosen yet, so nothing to assign.
      final FilledButton assign = tester.widget(
        find.widgetWithText(FilledButton, 'Assign'),
      );
      expect(assign.onPressed, isNull);

      await tester.ensureVisible(find.byKey(const ValueKey('firm-setup-profile')));
      await tester.tap(find.byKey(const ValueKey('firm-setup-profile')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Wholesale').last);
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.widgetWithText(FilledButton, 'Assign'));
      await tester.tap(find.widgetWithText(FilledButton, 'Assign'));
      await tester.pumpAndSettle();

      expect(api.assigned, [('firm-1', 'p-wholesale')]);
      expect(find.text('Business profile set to Wholesale.'), findsOneWidget);
      expect(find.byKey(const ValueKey('firm-setup-profile')), findsNothing,
          reason: 'the row is done, so the picker is gone');
    });

    testWidgets('the catalogue is not read when the profile is already set',
        (tester) async {
      final _Api api = _Api(answers: [_readiness(others: 'DONE')]);
      await _open(tester, api);
      expect(api.catalogueReads, 0);
    });

    testWidgets('Open the books calls the route and re-reads the list',
        (tester) async {
      final _Api api = _Api(answers: [
        _readiness(),
        _readiness(books: 'DONE'),
      ]);
      final List<bool> answers = await _open(tester, api);

      await tester.ensureVisible(find.widgetWithText(FilledButton, 'Open the books'));
      await tester.tap(find.widgetWithText(FilledButton, 'Open the books'));
      await tester.pumpAndSettle();

      expect(api.opened, ['firm-1']);
      expect(api.reads, 2, reason: 're-read after the action');
      expect(find.textContaining('Books opened for the year'), findsOneWidget);
      // The row shows the result rather than a stale MISSING, and the button
      // is gone because there is nothing left to do on it.
      expect(find.text('24 accounts, all 24 control accounts mapped.'),
          findsOneWidget);
      expect(find.widgetWithText(FilledButton, 'Open the books'), findsNothing);
      expect(
        find.text(
            'Can post documents. The recommended steps are still open.'),
        findsOneWidget,
      );

      await tester.tap(find.text('Close'));
      await tester.pumpAndSettle();
      expect(answers, [true], reason: 'something changed');
    });

    testWidgets('closing without doing anything says so', (tester) async {
      final List<bool> answers =
          await _open(tester, _Api(answers: [_readiness()]));

      await tester.tap(find.text('Close'));
      await tester.pumpAndSettle();

      expect(answers, [false]);
    });

    testWidgets('a refusal is shown and the panel stays', (tester) async {
      final _Api api = _Api(
        answers: [_readiness()],
        refuse: "Provision the firm's storage before opening its books.",
      );
      await _open(tester, api);

      await tester.ensureVisible(find.widgetWithText(FilledButton, 'Open the books'));
      await tester.tap(find.widgetWithText(FilledButton, 'Open the books'));
      await tester.pumpAndSettle();

      expect(find.textContaining('before opening its books'), findsOneWidget);
      expect(find.text('Set up ACME'), findsOneWidget);
      expect(find.widgetWithText(FilledButton, 'Open the books'), findsOneWidget);
    });

    testWidgets('an unprovisioned firm offers Provision storage and nothing else',
        (tester) async {
      // Every store-side step is BLOCKED: nothing can be counted, so nothing
      // is offered on them -- and no hint either, since the hint would send
      // somebody into a firm that has no tables.
      final _Api api = _Api(answers: [
        _readiness(storage: 'MISSING', books: 'BLOCKED', others: 'BLOCKED'),
        _readiness(),
      ]);
      await _open(tester, api, firm: _firm(mode: 'SCHEMA', provisioned: false));

      expect(find.widgetWithText(FilledButton, 'Provision storage'),
          findsOneWidget);
      expect(find.widgetWithText(FilledButton, 'Open the books'), findsNothing);
      expect(
        find.widgetWithText(FilledButton, 'Apply GST template'),
        findsNothing,
      );
      expect(find.text(firmSetupHints['branches']!), findsNothing);
      expect(api.catalogueReads, 0, reason: 'no store to read it from');

      await tester.ensureVisible(find.widgetWithText(FilledButton, 'Provision storage'));
      await tester.tap(find.widgetWithText(FilledButton, 'Provision storage'));
      await tester.pumpAndSettle();

      expect(api.provisioned, ['firm-1']);
      // Now the store can be read, so the books step is offered.
      expect(find.widgetWithText(FilledButton, 'Open the books'), findsOneWidget);
    });

    testWidgets('a finished firm says so and offers nothing', (tester) async {
      await _open(tester, _Api(answers: [_readiness(books: 'DONE', others: 'DONE')]));

      expect(find.text('Finished. Every step is done.'), findsOneWidget);
      expect(find.byType(FilledButton), findsNothing);
    });

    testWidgets('fits an 800x600 window', (tester) async {
      // The default test window. Seven rows with detail and hints is the
      // tallest the panel gets; it scrolls rather than overflows.
      await _open(tester, _Api(answers: [_readiness()]));
      expect(tester.takeException(), isNull);
    });
  });

  group('on the Firms grid', () {
    test('Set up is offered when the shell supplies a context', () {
      // A definition built without a tree cannot open a dialog, and an
      // action that can do nothing is worse than an absent one.
      final ResourceDefinition<Firm> without =
          firmDefinition(_Api(answers: const []), PermissionService());
      expect(without.customActions.map((a) => a.label), isNot(contains('Set up')));
    });

    testWidgets('the toolbar holds it without overflowing', (tester) async {
      final _Api api = _Api(answers: [_readiness()]);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => ResourceManagementPage<Firm>(
              api: api,
              definition: firmDefinition(
                api,
                PermissionService(),
                showFrame: false,
                onOpenFirm: (_) async => 'switched',
                context: context,
              ),
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();

      expect(find.text('Set up'), findsOneWidget);
      expect(find.text('Provision storage'), findsOneWidget);
      expect(find.text('Open this firm'), findsOneWidget);
      expect(tester.takeException(), isNull, reason: 'no overflow at 800x600');
    });

    testWidgets('and pressing it opens the panel for the selected firm',
        (tester) async {
      final _Api api = _Api(answers: [_readiness()]);
      late ResourceAction<Firm> setUp;
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) {
              setUp = firmDefinition(api, PermissionService(), context: context)
                  .customActions
                  .firstWhere((action) => action.label == 'Set up');
              return const SizedBox.shrink();
            },
          ),
        ),
      ));

      expect(setUp.needsSelection, isTrue, reason: 'it is about one firm');
      final Future<String> outcome = setUp.onInvoke(_firm());
      await tester.pumpAndSettle();

      expect(find.text('Set up ACME'), findsOneWidget);
      await tester.tap(find.text('Close'));
      await tester.pumpAndSettle();
      // The panel reports its own outcomes, so the grid shows no toast.
      expect(await outcome, isEmpty);
    });
  });
}
