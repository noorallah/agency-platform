// The shared place picker, on its own.
//
// The cascade is the whole point of the control, and it was broken in a way no
// screen test caught: `_pick` told the parent about the new choice and then
// immediately loaded the rung below, reading `widget.value` — which the parent
// had not rebuilt yet. So it saw the country still blank, stopped, and offered
// no states at all. Vendors and branches shipped with it because their tests
// only ever chose one rung.

import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/ui/workspace/geo_area_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

GeoPlaceRecord _place(GeoLevel level, String id, String code, String name) =>
    GeoPlaceRecord.fromJson(level, <String, dynamic>{
      'id': id,
      'code': code,
      'name': name,
      'postal_code': code,
    });

class _Harness extends StatefulWidget {
  const _Harness({required this.requested});

  /// Every (level, parentId) the picker asked for, in order.
  final List<String> requested;

  @override
  State<_Harness> createState() => _HarnessState();
}

class _HarnessState extends State<_Harness> {
  Map<GeoLevel, String> _value = const <GeoLevel, String>{};

  Future<List<GeoPlaceRecord>> _load(
    GeoLevel level, {
    String parentId = '',
  }) async {
    widget.requested.add('${level.name}:$parentId');
    return switch (level) {
      GeoLevel.country => <GeoPlaceRecord>[
          _place(level, 'c-in', 'IN', 'India'),
        ],
      GeoLevel.state => parentId == 'c-in'
          ? <GeoPlaceRecord>[_place(level, 's-tn', 'TN', 'Tamil Nadu')]
          : const <GeoPlaceRecord>[],
      _ => const <GeoPlaceRecord>[],
    };
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
        home: Scaffold(
          body: GeoAreaPicker(
            loadPlaces: _load,
            value: _value,
            onChanged: (value) => setState(() => _value = value),
          ),
        ),
      );
}

Future<void> _choose(WidgetTester tester, int rung, String name) async {
  await tester.tap(find.byType(DropdownButtonFormField<String>).at(rung));
  await tester.pumpAndSettle();
  await tester.tap(find.text(name).last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('choosing a rung loads the one below it', (tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final List<String> requested = <String>[];
    await tester.pumpWidget(_Harness(requested: requested));
    await tester.pumpAndSettle();

    await _choose(tester, 0, 'India');

    // The country's id has to reach the request, not the empty value the
    // parent was still holding when the choice was made.
    expect(requested, contains('state:c-in'));
    await _choose(tester, 1, 'Tamil Nadu');
    expect(find.text('Tamil Nadu'), findsWidgets);
  });

  testWidgets('clearing a rung empties the ones below it', (tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(_Harness(requested: <String>[]));
    await tester.pumpAndSettle();

    await _choose(tester, 0, 'India');
    await _choose(tester, 1, 'Tamil Nadu');
    await _choose(tester, 0, 'None');

    // Anything below a changed rung stops meaning anything.
    expect(find.text('Tamil Nadu'), findsNothing);
  });
}
