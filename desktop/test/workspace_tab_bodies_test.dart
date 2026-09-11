import 'dart:io';

import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter_test/flutter_test.dart';

/// Every tab a module declares must have a body in the workspace that module
/// opens.
///
/// A workspace renders its tab by `switch (tabId)`, and the switch falls back
/// to a "coming soon" placeholder for an id it does not name. The catalog and
/// the shell are two files, so a tab can be declared under one module and
/// given its body under another -- which is what happened to Vendor
/// Categories and Vendor Types on 2026-08-22: declared as tabs of Masters,
/// dispatched inside the Administration workspace, and so unreachable from
/// the sidebar from the day they were written until manual testing opened one
/// on 2026-09-11. The widget test for the screen passed throughout, because
/// it built the `ResourceDefinition` directly and never asked which workspace
/// would show it.
///
/// A source check rather than a behavioural one because the workspaces are
/// private widgets: nothing in this suite can build one to ask what it shows.
/// Single-tab workspaces have no switch and are skipped.
void main() {
  test('every catalog tab has a body case in its module\'s workspace', () {
    final String shell = File('lib/ui/desktop_shell.dart').readAsStringSync();

    final List<RegExpMatch> classStarts =
        RegExp(r'class (_\w+Workspace) extends').allMatches(shell).toList();
    String bodyOf(String className) {
      for (int i = 0; i < classStarts.length; i++) {
        if (classStarts[i].group(1) != className) continue;
        final int end =
            i + 1 < classStarts.length ? classStarts[i + 1].start : shell.length;
        return shell.substring(classStarts[i].start, end);
      }
      fail('$className is named in _page but no such class exists');
    }

    final Iterable<RegExpMatch> mapping =
        RegExp(r'AppModule\.(\w+) => (_\w+Workspace)\(').allMatches(shell);
    expect(mapping, isNotEmpty,
        reason: 'the module-to-workspace mapping in _page was not found; '
            'update the pattern if it moved');

    final List<String> missing = <String>[];
    for (final RegExpMatch m in mapping) {
      final AppModule module = AppModule.values.byName(m.group(1)!);
      final String className = m.group(2)!;
      final String body = bodyOf(className);
      if (!body.contains('switch (tabId)')) continue;
      for (final ModuleTabDefinition tab in ModuleCatalog.byId(module).tabs) {
        // A case may share a body with a sibling through an or-pattern,
        // `'roles' || 'permissions' =>`, so the id may be followed by either.
        final RegExp named = RegExp(
          r"(?:^|\|\|)\s*'" +
              RegExp.escape(tab.id) +
              r"'\s*(?:=>|\|\|)",
          multiLine: true,
        );
        if (!named.hasMatch(body)) {
          missing.add('${module.name} / ${tab.id} has no case in $className');
        }
      }
    }
    expect(
      missing,
      isEmpty,
      reason: 'A tab with no case in its workspace renders "coming soon". '
          'Give it a body in the workspace its module opens, not in another.',
    );
  });
}
