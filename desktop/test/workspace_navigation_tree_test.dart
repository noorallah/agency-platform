import 'package:agency_desktop/ui/workspace/workspace_templates.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('workspace navigation tree supports nested selections',
      (tester) async {
    String? selected;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: WorkspaceNavigationTree(
            selectedPath: 'configuration/tax/tax-profiles',
            onSelected: (value) => selected = value,
            nodes: [
              WorkspaceNavigationNode(
                label: 'Configuration',
                icon: Icons.tune_outlined,
                children: [
                  WorkspaceNavigationNode(
                    label: 'Tax Configuration',
                    path: 'configuration/tax',
                    children: const [
                      WorkspaceNavigationNode(
                        label: 'Tax Profiles',
                        path: 'configuration/tax/tax-profiles',
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );

    expect(find.text('Configuration'), findsOneWidget);
    expect(find.text('Tax Profiles'), findsOneWidget);
    await tester.tap(find.text('Tax Profiles'));
    await tester.pump();
    expect(selected, 'configuration/tax/tax-profiles');
  });
}
