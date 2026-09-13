// The whole territory tree in a window of its own.
//
// The Geography screen's side panel is narrow and stacks a dashboard line and
// two rows of buttons above the tree, so a region with its zones and routes
// did not fit (plan item 11.1). The window shows every level at once, folds
// and unfolds it, and hands a node's action back to the screen.

import 'package:agency_desktop/models/sales_territory.dart';
import 'package:agency_desktop/ui/sales/territory_tree_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

List<TerritoryTreeNodeRecord> _tree() => [
      TerritoryTreeNodeRecord.fromJson({
        'id': 'rgn',
        'code': 'WHOLE01-RGN',
        'name': 'Chennai Region',
        'hierarchy_level_name': 'Region',
        'path': 'Chennai Region',
        'children': [
          {
            'id': 'tn',
            'parent_id': 'rgn',
            'code': 'WHOLE01-T-N',
            'name': 'North Zone',
            'hierarchy_level_name': 'Territory',
            'path': 'Chennai Region > North Zone',
            'children': [
              {
                'id': 'rn1',
                'parent_id': 'tn',
                'code': 'WHOLE01-R-N1',
                'name': 'North Sales Beat',
                'hierarchy_level_name': 'Route',
                'path': 'Chennai Region > North Zone > North Sales Beat',
              },
            ],
          },
        ],
      }),
    ];

Future<Future<TerritoryTreeChoice?>> _open(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  late Future<TerritoryTreeChoice?> result;
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () => result = TerritoryTreeDialog.show(
            context,
            tree: _tree(),
            canCreate: true,
            hasParentFilter: false,
          ),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  return result;
}

void main() {
  testWidgets('every level shows at once, and folds away', (tester) async {
    await _open(tester);

    expect(find.text('Chennai Region (Region)'), findsOneWidget);
    expect(find.text('North Zone (Territory)'), findsOneWidget);
    expect(find.text('North Sales Beat (Route)'), findsOneWidget);
    expect(tester.takeException(), isNull);

    await tester.tap(find.text('Collapse all'));
    await tester.pumpAndSettle();
    expect(find.text('North Sales Beat (Route)'), findsNothing);

    await tester.tap(find.text('Expand all'));
    await tester.pumpAndSettle();
    expect(find.text('North Sales Beat (Route)'), findsOneWidget);
  });

  testWidgets("a node's action goes back to the screen", (tester) async {
    final Future<TerritoryTreeChoice?> result = await _open(tester);

    await tester.tap(find.byTooltip('Actions for WHOLE01-R-N1'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Filter list').last);
    await tester.pumpAndSettle();

    final TerritoryTreeChoice? choice = await result;
    expect(choice?.action, TerritoryTreeAction.filterList);
    expect(choice?.nodeId, 'rn1');
  });
}
