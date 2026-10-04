import 'package:agency_desktop/models/document_framework.dart';
import 'package:agency_desktop/models/firm_member.dart';
import 'package:agency_desktop/phase2/display_dates.dart';
import 'package:agency_desktop/ui/document_framework/document_framework_widgets.dart';
import 'package:agency_desktop/ui/document_framework/history_words.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const String _manager = 'ed451637-fbce-4f8e-9f4b-b2bad6cb4794';
const String _outsider = '11111111-2222-3333-4444-555555555555';
const String _stamp = '2026-10-04T17:38:51.002872+05:30';

String _expectedWhen() {
  final DateTime local = DateTime.parse(_stamp).toLocal();
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(local.day)}-${two(local.month)}-${local.year} '
      '${two(local.hour)}:${two(local.minute)}';
}

Widget _screen(List<DocumentTimelineSnapshot> a,
        [List<DocumentTimelineSnapshot> b = const []]) =>
    MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: Column(
            children: [
              EnterpriseTimeline(entries: a),
              if (b.isNotEmpty) EnterpriseTimeline(entries: b),
            ],
          ),
        ),
      ),
    );

void main() {
  late int reads;

  setUp(() {
    reads = 0;
    DisplayDates.use('dd-MM-yyyy');
    FirmPeople.reset();
    FirmPeople.configure(
      load: () async {
        reads++;
        return const [
          FirmMember(userId: _manager, fullName: 'Purchase Manager (qa)'),
        ];
      },
      firmId: () => 'firm-1',
    );
  });

  tearDown(FirmPeople.reset);

  testWidgets('a row reads in a name, words and the firm date format',
      (tester) async {
    await tester.pumpWidget(_screen(const [
      DocumentTimelineSnapshot(
        occurredAt: _stamp,
        action: 'purchase.approved',
        fromState: 'SUBMITTED',
        toState: 'APPROVED',
        actor: _manager,
      ),
      DocumentTimelineSnapshot(
        occurredAt: _stamp,
        action: 'goods_receipt.completed',
        actor: _outsider,
      ),
    ]));
    await tester.pumpAndSettle();

    expect(find.text('Approved'), findsOneWidget);
    expect(find.text('Completed'), findsOneWidget);
    expect(find.text('Submitted → Approved'), findsOneWidget);
    expect(find.text('Purchase Manager (qa)'), findsOneWidget);
    expect(find.text(unknownHistoryActor), findsOneWidget);
    expect(find.text(_expectedWhen()), findsNWidgets(2));

    expect(find.textContaining(_manager), findsNothing);
    expect(find.textContaining(_outsider), findsNothing);
    expect(find.textContaining('purchase.approved'), findsNothing);
    expect(find.textContaining('SUBMITTED'), findsNothing);
    expect(find.textContaining('T17:38'), findsNothing);
  });

  testWidgets('the date follows the chosen format', (tester) async {
    DisplayDates.use('yyyy-MM-dd');
    await tester.pumpWidget(_screen(const [
      DocumentTimelineSnapshot(occurredAt: _stamp, action: 'Created'),
    ]));
    await tester.pumpAndSettle();
    final DateTime local = DateTime.parse(_stamp).toLocal();
    expect(find.textContaining('${local.year}-'), findsOneWidget);
    DisplayDates.use(null);
  });

  testWidgets('the people are read once for the screen, not per row or panel',
      (tester) async {
    const List<DocumentTimelineSnapshot> rows = [
      DocumentTimelineSnapshot(
          occurredAt: _stamp, action: 'purchase.approved', actor: _manager),
      DocumentTimelineSnapshot(
          occurredAt: _stamp, action: 'purchase.submitted', actor: _manager),
      DocumentTimelineSnapshot(
          occurredAt: _stamp, action: 'purchase.created', actor: _manager),
    ];
    await tester.pumpWidget(_screen(rows, rows));
    await tester.pumpAndSettle();
    expect(reads, 1);

    // A second screen in the same firm reuses the answer.
    await tester.pumpWidget(const SizedBox());
    await tester.pumpWidget(_screen(rows));
    await tester.pumpAndSettle();
    expect(reads, 1);
    expect(find.text('Purchase Manager (qa)'), findsNWidgets(3));
  });

  test('wording helpers', () {
    expect(historyActionWords('purchase.approved'), 'Approved');
    expect(historyActionWords('STATUS CHANGED'), 'Status changed');
    expect(historyStatusWords('PARTIALLY_RECEIVED'), 'Partially received');
    expect(historyWhen('not a date'), 'not a date');
    expect(FirmPeople.nameFor('system'), 'system');
  });
}
