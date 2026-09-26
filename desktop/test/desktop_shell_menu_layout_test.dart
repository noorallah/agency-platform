import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/auth/session_controller.dart';
import 'package:agency_desktop/core/branding/branding_config.dart';
import 'package:agency_desktop/core/design/design_tokens.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:agency_desktop/phase2/home_page.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/phase2/app_menu_bar.dart';
import 'package:agency_desktop/ui/workspace/enterprise_sidebar.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The whole shell, built for real, in the phase 2 frame.
///
/// Until this file no test instantiated `DesktopShell` at all -- every guard
/// read the catalogue or pumped one page -- so the shell could compile, pass
/// every test, and still throw on the first frame a user saw. This builds it
/// the way `app.dart` does, with a platform administrator and no firm chosen
/// (which needs no server: every request fails and every screen must survive
/// that), and walks the frame: the menu bar, opening a screen, the tab it
/// leaves, and the switch back to phase 1.
String _token() {
  final Set<String> codes = {
    for (final ModuleDefinition module in ModuleCatalog.modules) ...[
      ...module.requiredPermissions,
      for (final ModuleTabDefinition tab in module.tabs)
        ...tab.requiredPermissions,
    ],
  };
  final String payload = base64Url.encode(utf8.encode(jsonEncode({
    'permissions': codes.toList(),
    'roles': const <String>[],
    'platform_admin': true,
    'platform_admin_scope': 'ALL_FIRMS',
    'firm_permissions': const <String, List<String>>{},
  })));
  return 'h.$payload.s';
}

Future<DesktopPreferencesService> _preferences(String? workspace) async {
  final Directory temp =
      Directory.systemTemp.createTempSync('shell_menu_layout_');
  addTearDown(() => temp.deleteSync(recursive: true));
  final DesktopPreferencesService preferences =
      DesktopPreferencesService(directory: temp);
  if (workspace != null) await preferences.saveLastWorkspace(workspace);
  return preferences;
}

Future<DesktopPreferencesService> _pumpShell(
  WidgetTester tester, {
  bool phase2 = true,
  String? workspace = 'administration/users',
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  late DesktopPreferencesService preferences;
  await tester.runAsync(() async {
    preferences = await _preferences(workspace);
  });
  final PermissionService permissions = PermissionService()
    ..applyAccessToken(_token());
  final SessionController session = SessionController(
    baseUrl: 'http://127.0.0.1:9',
    preferences: preferences,
    isPlatformAdmin: () => permissions.isPlatformAdmin,
  );
  final ThemeManager themes = ThemeManager(preferences);
  await tester.pumpWidget(MaterialApp(
    theme: themes.lightTheme,
    home: DesktopShell(
      phase2: phase2,
      session: session,
      preferences: preferences,
      branding: BrandingConfig.defaults,
      themes: themes,
      permissions: permissions,
    ),
  ));
  await tester.pump(const Duration(milliseconds: 100));
  return preferences;
}

/// Take the shell down so its health timer does not outlive the test.
Future<void> _unmount(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox());
  await tester.pump();
}

void main() {
  testWidgets('the shell opens in the menu layout and keeps the last screen',
      (tester) async {
    await _pumpShell(tester);

    expect(find.byType(AppMenuBar), findsOneWidget);
    expect(find.byType(EnterpriseSidebar), findsNothing);
    expect(find.byKey(const ValueKey('menu-area-admin')), findsOneWidget);
    // No firm is chosen, so the firm-owned areas are not offered (4.12).
    expect(find.byKey(const ValueKey('menu-area-sell')), findsNothing);
    // The screen it was left on is open as a tab.
    expect(find.byKey(const ValueKey('open-screen-administration/users')),
        findsOneWidget);
    expect(tester.takeException(), isNull);
    await _unmount(tester);
  });

  testWidgets('choosing from a panel opens the screen in a new tab',
      (tester) async {
    await _pumpShell(tester);

    await tester.tap(find.byKey(const ValueKey('menu-area-admin')));
    await tester.pump(const Duration(milliseconds: 300));
    await tester
        .tap(find.byKey(const ValueKey('menu-item-administration/firms')));
    // A menu item runs its action after the frame that closes the menu, so
    // the shell redraws a frame later than the tap.
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byKey(const ValueKey('open-screen-administration/users')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('open-screen-administration/firms')),
        findsOneWidget);
    expect(tester.takeException(), isNull);
    await _unmount(tester);
  });

  testWidgets('the phase 1 app keeps its sidebar and offers no switch',
      (tester) async {
    // The owner chose separate apps (2026-09-26): phase 1 must look exactly
    // as it did, with nothing of phase 2 inside it.
    await _pumpShell(tester, phase2: false);

    expect(find.byType(EnterpriseSidebar), findsOneWidget);
    expect(find.byType(AppMenuBar), findsNothing);
    expect(find.byType(OpenScreenTabs), findsNothing);
    await tester.tap(find.byTooltip('Profile'));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.textContaining('layout'), findsNothing);
    expect(tester.takeException(), isNull);
    await _unmount(tester);
  });

  testWidgets('a first session opens on Home', (tester) async {
    await _pumpShell(tester, workspace: null);
    expect(find.byKey(const ValueKey('open-screen-home')), findsOneWidget);
    expect(find.byType(Phase2HomePage), findsOneWidget);
    expect(tester.takeException(), isNull);
    await _unmount(tester);
  });

  testWidgets('the firm is readable on the bar, and Appearance is there',
      (tester) async {
    await _pumpShell(tester);
    // Dark text on the dark bar was the owner's "firm switch not
    // displaying": the name took the page's text colour.
    final Finder firm = find.text('Platform');
    expect(firm, findsOneWidget);
    final BuildContext context = tester.element(firm);
    expect(tester.widget<Text>(firm).style?.color,
        context.semanticColors.onChrome);
    // The wireframe's box: as tall as the search box beside it.
    expect(tester.getSize(find.byKey(const ValueKey('firm-on-bar'))).height,
        tester.getSize(find.byKey(const ValueKey('menu-search'))).height);
    // Phase 1 kept Appearance at the foot of its sidebar.
    expect(find.byTooltip('Appearance'), findsOneWidget);
    await _unmount(tester);
  });

  testWidgets('a document is a tab: kept while away, closed by its own save',
      (tester) async {
    await _pumpShell(tester, workspace: null);
    final BuildContext home = tester.element(find.byType(Phase2HomePage));
    bool? saved;
    showDocument<bool>(
      home,
      title: 'New sales order',
      builder: (context) => WorkspaceDialog(
        title: 'New sales order',
        body: const Padding(
          padding: EdgeInsets.all(16),
          child: TextField(key: ValueKey('order-remarks')),
        ),
        onSave: () => Navigator.of(context).pop(true),
        saveLabel: 'Create draft',
      ),
    ).then((value) => saved = value);
    await tester.pump();
    await tester.pump();

    // Its own tab, on show; the screen beneath is kept, not shown.
    expect(find.byKey(const ValueKey('open-screen-doc:1')), findsOneWidget);
    expect(find.byType(Phase2HomePage), findsNothing);
    await tester.enterText(
        find.byKey(const ValueKey('order-remarks')), 'deliver by Friday');

    // Away and back: what was typed is still there.
    await tester.tap(find.byKey(const ValueKey('open-screen-home')));
    await tester.pump();
    expect(find.byType(Phase2HomePage), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('open-screen-doc:1')));
    await tester.pump();
    expect(find.text('deliver by Friday'), findsOneWidget);

    // Its own Save closes the tab and hands the result back.
    await tester.tap(find.text('Create draft'));
    await tester.pump();
    await tester.pump();
    expect(saved, isTrue);
    expect(find.byKey(const ValueKey('open-screen-doc:1')), findsNothing);
    expect(find.byType(Phase2HomePage), findsOneWidget);
    expect(tester.takeException(), isNull);
    await _unmount(tester);
  });

  testWidgets("one bottom bar, as the wireframe: the role left, online right",
      (tester) async {
    await _pumpShell(tester, workspace: null);
    final Finder bar = find.byKey(const ValueKey('phase2-status-bar'));
    expect(bar, findsOneWidget);
    // The connection is at the bottom right, and no longer on the top bar.
    expect(find.descendant(of: bar, matching: find.byType(ConnectionDot)),
        findsOneWidget);
    expect(
        find.descendant(
            of: find.byType(AppMenuBar), matching: find.byType(ConnectionDot)),
        findsNothing);
    expect(tester.getCenter(find.byType(ConnectionDot)).dx,
        greaterThan(tester.getCenter(bar).dx));
    // Home says whose home it is -- the wireframe's "Owner".
    expect(
        find.descendant(
            of: bar, matching: find.text('Platform administrator')),
        findsOneWidget);
    await _unmount(tester);
  });
}
