import 'dart:convert';

import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/sales_invoice.dart';
import 'package:agency_desktop/phase2/menu_layout.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:agency_desktop/ui/workspace/module_visibility.dart';
import 'package:flutter_test/flutter_test.dart';

/// The phase 2 menu must place every phase 1 screen, once.
///
/// The owner's rule when the menu was redesigned (2026-09-25): no phase 1
/// screen may be lost. Appendix A of `docs/UI_PHASE_2_DESIGN.md` places
/// each one; `MenuLayout` is that appendix as code, and this reads the
/// catalogue rather than a list somebody keeps, so a screen added to the
/// catalogue and forgotten here fails the build the day it merges.
Set<String> _catalogueScreens() => {
      for (final ModuleDefinition module in ModuleCatalog.modules)
        if (module.tabs.isEmpty)
          module.id.name
        else
          for (final ModuleTabDefinition tab in module.tabs)
            // A tab declared unavailable has no workspace behind it.
            if (tab.available) '${module.id.name}/${tab.id}',
    };

PermissionService _holding(List<String> codes) {
  final String payload = base64Url.encode(
    utf8.encode(
      jsonEncode({
        'permissions': <String>[],
        'roles': const <String>[],
        'platform_admin': false,
        'firm_permissions': {
          'firm-1': codes,
        },
      }),
    ),
  );
  return PermissionService()
    ..applyAccessToken('h.$payload.s', activeFirmId: 'firm-1');
}

ModuleVisibility _visibility(List<String> codes) => ModuleVisibility(
      permissions: _holding(codes),
      activeBusinessModules: null,
      salesStages: SalesWorkflowSettings.wholeChain,
      hasActiveFirm: true,
    );

void main() {
  test('every catalogue screen has a place in the menu', () {
    final Set<String> placed = {
      for (final MenuAreaSpec area in MenuLayout.all)
        for (final MenuItemSpec item in area.items) item.path,
    };
    final Set<String> missing = _catalogueScreens().difference(placed);
    expect(missing, isEmpty,
        reason: 'a phase 1 screen with no place in MenuLayout is a screen '
            'nobody can reach from the phase 2 menu -- add it where '
            'UI_PHASE_2_DESIGN.md appendix A puts it');
  });

  test('the menu names no screen the catalogue does not have', () {
    final Set<String> screens = _catalogueScreens();
    final List<String> unknown = [
      for (final MenuAreaSpec area in MenuLayout.all)
        for (final MenuItemSpec item in area.items)
          // A phase 2 screen (Home) has no catalogue module by design.
          if (item.module != null && !screens.contains(item.path)) item.path,
    ];
    expect(unknown, isEmpty);
  });

  test('Home is a phase 2 screen, offered to everybody', () {
    final MenuItemSpec home = MenuLayout.home.items.single;
    expect(home.path, MenuLayout.homeRoute);
    expect(home.module, isNull);
    expect(MenuLayout.visible(MenuLayout.home, _visibility(const [])),
        isNotNull,
        reason: 'phase 1 offered its Dashboard only to a platform '
            'administrator, which left every firm user with no Home');
  });

  test('no screen is placed twice', () {
    final List<String> paths = [
      for (final MenuAreaSpec area in MenuLayout.all)
        for (final MenuItemSpec item in area.items) item.path,
    ];
    expect(paths.length, paths.toSet().length,
        reason: 'one screen, one place; the command box finds it by name');
  });

  test('no two items in one area share a label', () {
    for (final MenuAreaSpec area in MenuLayout.all) {
      final List<String> labels = [
        for (final MenuItemSpec item in area.items) item.label,
      ];
      expect(labels.length, labels.toSet().length, reason: area.label);
    }
  });

  test('eight areas across the bar, as decided in section 8', () {
    expect(MenuLayout.areas.map((area) => area.label), [
      'Home',
      'Sell',
      'Buy',
      'Stock',
      'Accounts',
      'Masters',
      'Reports',
      'Admin',
    ]);
  });

  group('the menu follows permissions (4.12)', () {
    test('a customer-only role sees Masters with Customers and nothing else',
        () {
      final ModuleVisibility visibility = _visibility(['CUSTOMER_VIEW']);
      final List<MenuAreaSpec> shown = [
        for (final MenuAreaSpec area in MenuLayout.areas)
          if (MenuLayout.visible(area, visibility) case final MenuAreaSpec a) a,
      ];
      final MenuAreaSpec masters =
          shown.singleWhere((area) => area.id == 'masters');
      expect(masters.items.map((item) => item.label), contains('Customers'));
      expect(
          masters.items.map((item) => item.label), isNot(contains('Vendors')));
      expect(shown.map((area) => area.id), isNot(contains('admin')));
      expect(shown.map((area) => area.id), isNot(contains('buy')));
    });

    test('a group left with no item disappears', () {
      final MenuAreaSpec? masters = MenuLayout.visible(
        MenuLayout.areas.singleWhere((area) => area.id == 'masters'),
        _visibility(['CUSTOMER_VIEW']),
      );
      expect(masters!.groups.map((group) => group.label), ['Parties']);
    });

    test('nobody with no permissions is offered an area', () {
      final ModuleVisibility visibility = _visibility(const []);
      for (final MenuAreaSpec area in MenuLayout.all) {
        final MenuAreaSpec? shown = MenuLayout.visible(area, visibility);
        // The Dashboard is the one module that may open with no codes; any
        // other area offered here is a leak.
        if (shown != null) expect(shown.id, 'home');
      }
    });
  });
}
