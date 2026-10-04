import 'package:agency_desktop/phase2/document_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Backlog 83, "Copy from every screen": a value in a dialog and in a
/// document tab can be selected and copied, Ctrl+C on a grid puts its
/// selected rows on the clipboard with a heading line, a right-click offers
/// Copy cell, and a document's number carries a copy icon. Selection must
/// not cost the screens their typing, buttons or taps.

/// Intercept the platform clipboard and hand back whatever was copied.
String? Function() _captureClipboard(WidgetTester tester) {
  String? copied;
  tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
    SystemChannels.platform,
    (MethodCall call) async {
      if (call.method == 'Clipboard.setData') {
        copied = (call.arguments as Map)['text'] as String?;
      }
      return null;
    },
  );
  addTearDown(
    () => tester.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null),
  );
  return () => copied;
}

/// Drag the mouse across [text], as somebody selecting it would.
Future<void> _dragAcross(WidgetTester tester, Finder text) async {
  final Rect rect = tester.getRect(text);
  final TestGesture gesture = await tester.startGesture(
    rect.centerLeft + const Offset(1, 0),
    kind: PointerDeviceKind.mouse,
  );
  await tester.pump();
  await gesture.moveTo(rect.centerRight + const Offset(4, 0));
  await tester.pump();
  await gesture.up();
  await tester.pumpAndSettle();
}

Future<void> _ctrlC(WidgetTester tester) async {
  await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
  await tester.sendKeyEvent(LogicalKeyboardKey.keyC);
  await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
  await tester.pumpAndSettle();
}

Future<void> _size(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

class _Row {
  const _Row(this.id, this.code, this.name, this.status);

  final String id;
  final String code;
  final String name;
  final String status;
}

const List<_Row> _rows = [
  _Row('a', 'C-1', 'Anand Agencies', 'ACTIVE'),
  _Row('b', 'C-2', 'Bharat Traders', 'ON_HOLD'),
  _Row('c', 'C-3', 'Chola Stores', 'ACTIVE'),
];

/// A grid of three rows, selection kept by the test.
Widget _grid({
  String? selectedId,
  Set<String> selectedIds = const {},
  ValueChanged<_Row>? onSelect,
  List<WorkspaceContextAction> actions = const [],
  void Function(WorkspaceContextAction, _Row)? onAction,
}) =>
    EnterpriseDataGrid<_Row>(
      items: _rows,
      total: _rows.length,
      pageOffset: 0,
      columns: const [
        GridColumn(key: 'code', label: 'Code'),
        GridColumn(key: 'name', label: 'Name'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (row) => row.id,
      cells: (row) => [row.code, row.name, row.status],
      onSelect: onSelect ?? (_) {},
      onPageChanged: (_) {},
      selectedId: selectedId,
      selectedIds: selectedIds,
      contextActions: actions,
      onContextAction: onAction,
    );

void main() {
  testWidgets('a value in a dialog can be selected and copied', (
    tester,
  ) async {
    await _size(tester);
    final String? Function() clipboard = _captureClipboard(tester);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () => showDialog<void>(
              context: context,
              builder: (_) => const WorkspaceDialog(
                title: 'Goods receipt',
                body: Center(child: Text('GRN-2026-000123')),
              ),
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    await _dragAcross(tester, find.text('GRN-2026-000123'));
    await _ctrlC(tester);
    expect(clipboard(), 'GRN-2026-000123');
  });

  testWidgets('a confirmation can be selected, title included', (
    tester,
  ) async {
    await _size(tester);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () => showWorkspaceConfirmDialog(
              context,
              title: 'Cancel PO-2026-000009?',
              message: 'Nothing has been received against it.',
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(
      find.ancestor(
        of: find.text('Cancel PO-2026-000009?'),
        matching: find.byType(SelectionArea),
      ),
      findsOneWidget,
    );
  });

  testWidgets('a value in a document tab can be selected and copied, and '
      'its fields and buttons still work', (tester) async {
    await _size(tester);
    final String? Function() clipboard = _captureClipboard(tester);
    final DocumentTabsController tabs = DocumentTabsController();
    addTearDown(tabs.dispose);
    final TextEditingController remarks = TextEditingController();
    addTearDown(remarks.dispose);
    int saved = 0;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: DocumentTabsScope(
          controller: tabs,
          child: AnimatedBuilder(
            animation: tabs,
            builder: (context, _) => Stack(children: [
              const Text('the list'),
              for (final OpenDocument document in tabs.documents)
                DocumentNavigator(
                  key: ValueKey(document.id),
                  document: document,
                ),
            ]),
          ),
        ),
      ),
    ));
    showDocument<void>(
      tester.element(find.text('the list')),
      title: 'PO',
      // A plain page, not a WorkspaceDialog: the tab's own SelectionArea is
      // what is being shown to work.
      builder: (context) => Material(
        child: Column(children: [
          const Text('PO-2026-000777'),
          SizedBox(
            width: 300,
            child: TextField(
              key: const ValueKey('remarks'),
              controller: remarks,
            ),
          ),
          FilledButton(
            onPressed: () => saved++,
            child: const Text('Save'),
          ),
        ]),
      ),
    );
    await tester.pumpAndSettle();

    await _dragAcross(tester, find.text('PO-2026-000777'));
    await _ctrlC(tester);
    expect(clipboard(), 'PO-2026-000777');

    // Typing, a tap and a button are unaffected by the selection area.
    await tester.tap(find.byKey(const ValueKey('remarks')));
    await tester.enterText(find.byKey(const ValueKey('remarks')), 'urgent');
    expect(remarks.text, 'urgent');
    await tester.tap(find.text('Save'));
    await tester.pump();
    expect(saved, 1);
  });

  testWidgets('Ctrl+C on a grid copies the selected rows under a heading', (
    tester,
  ) async {
    await _size(tester);
    final String? Function() clipboard = _captureClipboard(tester);
    String? selected;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: StatefulBuilder(
          builder: (context, setState) => _grid(
            selectedId: selected,
            onSelect: (row) => setState(() => selected = row.id),
          ),
        ),
      ),
    ));

    await tester.tap(find.text('Bharat Traders'));
    await tester.pumpAndSettle();
    await _ctrlC(tester);
    expect(clipboard(), 'Code\tName\tStatus\nC-2\tBharat Traders\tON_HOLD');
    expect(find.text('Row copied.'), findsOneWidget);
  });

  testWidgets('Ctrl+C copies every ticked row of the page, in page order', (
    tester,
  ) async {
    await _size(tester);
    final String? Function() clipboard = _captureClipboard(tester);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(child: _grid(selectedIds: const {'c', 'a'})),
      ),
    ));

    await tester.tap(find.text('Chola Stores'));
    await tester.pumpAndSettle();
    await _ctrlC(tester);
    // Phase 2 shows a status in words, and copies it so.
    expect(
      clipboard(),
      'Code\tName\tStatus\nC-1\tAnand Agencies\tActive\n'
      'C-3\tChola Stores\tActive',
    );
  });

  testWidgets('a screen that binds Ctrl+C itself keeps it', (tester) async {
    await _size(tester);
    final String? Function() clipboard = _captureClipboard(tester);
    int ownCopy = 0;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: WorkspaceShortcuts(
          bindings: WorkspaceShortcutBindings(copy: () => ownCopy++),
          child: _grid(selectedId: 'a'),
        ),
      ),
    ));

    await tester.tap(find.text('Anand Agencies'));
    await tester.pumpAndSettle();
    await _ctrlC(tester);
    expect(ownCopy, 1);
    expect(clipboard(), isNull);
  });

  testWidgets('right-click offers Copy cell beside the row actions', (
    tester,
  ) async {
    await _size(tester);
    final String? Function() clipboard = _captureClipboard(tester);
    final List<String> acted = [];
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: _grid(
          actions: const [WorkspaceContextAction.view],
          onAction: (action, row) => acted.add('${action.name} ${row.id}'),
        ),
      ),
    ));

    await tester.tap(
      find.text('Chola Stores'),
      buttons: kSecondaryMouseButton,
    );
    await tester.pumpAndSettle();
    expect(find.text('View'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('grid-copy-cell')));
    await tester.pumpAndSettle();
    expect(clipboard(), 'Chola Stores');

    // The screen's own actions are still there and still reach it.
    await tester.tap(find.text('C-1'), buttons: kSecondaryMouseButton);
    await tester.pumpAndSettle();
    await tester.tap(find.text('View'));
    await tester.pumpAndSettle();
    expect(acted, ['view a']);
  });

  testWidgets("a saved document's number has a copy icon; a preview has none",
      (tester) async {
    await _size(tester);
    final String? Function() clipboard = _captureClipboard(tester);
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: Column(children: [
          DocumentPageBand(
            title: 'Goods receipt',
            number: 'GRN-2026-000042',
            chips: ['Draft'],
          ),
          DocumentPageBand(
            title: 'New purchase order',
            chips: ['PO-2026-000050 (new)', 'Draft'],
          ),
        ]),
      ),
    ));
    expect(find.byKey(const ValueKey('document-number-copy')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('document-number-copy')));
    await tester.pump();
    expect(clipboard(), 'GRN-2026-000042');
    await tester.pump(const Duration(seconds: 2));
  });

  testWidgets("a party's GSTIN has a copy icon", (tester) async {
    await _size(tester);
    final String? Function() clipboard = _captureClipboard(tester);
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: SizedBox(
          width: 400,
          child: DocumentGstinLine(
            gstin: '29ABCDE1234F1Z5',
            leading: ['SUP-1'],
            trailing: ['9876543210'],
          ),
        ),
      ),
    ));
    expect(find.text('SUP-1  ·  GSTIN 29ABCDE1234F1Z5'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('document-gstin-copy')));
    await tester.pump();
    expect(clipboard(), '29ABCDE1234F1Z5');
    await tester.pump(const Duration(seconds: 2));
  });
}
