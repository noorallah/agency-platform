import 'dart:convert';
import 'dart:io';

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
    final Set<String> missing = _catalogueScreens()
        .difference(placed)
        .difference(MenuLayout.notOffered.keys.toSet());
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

    test('Customer Groups follows whoever may open Customers', () {
      List<String> parties(List<String> codes) => [
            for (final MenuItemSpec item in MenuLayout.visible(
                  MenuLayout.areas.singleWhere((area) => area.id == 'masters'),
                  _visibility(codes),
                )?.items ??
                const <MenuItemSpec>[])
              item.label,
          ];
      expect(parties(['CUSTOMER_VIEW']), contains('Customer Groups'));
      expect(parties(['VENDOR_VIEW']), isNot(contains('Customer Groups')));
    });

    test('a group left with no item disappears', () {
      final MenuAreaSpec? masters = MenuLayout.visible(
        MenuLayout.areas.singleWhere((area) => area.id == 'masters'),
        _visibility(['CUSTOMER_VIEW']),
      );
      // Customers, and Customer Groups under CONFIGURATION; nothing else.
      expect(masters!.groups.map((group) => group.label),
          ['Parties', 'Parties']);
      expect(masters.groups.map((group) => group.configuration),
          [false, true]);
    });

    test('nobody with no permissions is offered an area', () {
      final ModuleVisibility visibility = _visibility(const []);
      for (final MenuAreaSpec area in MenuLayout.all) {
        final MenuAreaSpec? shown = MenuLayout.visible(area, visibility);
        // The Dashboard is the one module that may open with no codes; any
        // other area offered here is a leak.
        if (shown != null && shown.id == 'settings') {
          // Backlog 44: My Branch and Warehouse is every member's own
          // preference, so it is the one setting that needs no code.
          expect(
            [for (final g in shown.groups) ...g.items.map((i) => i.label)],
            ['My Branch and Warehouse'],
          );
        } else if (shown != null) {
          expect(shown.id, 'home');
        }
      }
    });
  });

  group('Settings > Selling (backlog 57)', () {
    MenuGroupSpec selling() => MenuLayout.settings.groups
        .singleWhere((group) => group.label == 'Selling');

    test('holds the six settings that were only behind a screen', () {
      expect(selling().items.map((item) => item.label), [
        'Sales Stages',
        'Credit Control',
        'Price Floor',
        'Discount Limits',
        'Loyalty Scheme',
        'TCS Settings',
      ]);
      expect(selling().items.every((item) => item.isSetting), isTrue);
      expect(selling().items.map((item) => item.path), [
        MenuLayout.salesStagesRoute,
        MenuLayout.creditControlRoute,
        MenuLayout.priceFloorRoute,
        MenuLayout.discountLimitsRoute,
        MenuLayout.loyaltySchemeRoute,
        MenuLayout.tcsSettingsRoute,
      ]);
    });

    test('each is gated by the permission its own screen asks', () {
      expect(selling().items.map((item) => item.permission), [
        'SALES_VIEW',
        'CUSTOMER_VIEW',
        'SALES_VIEW',
        'SALES_VIEW',
        'LOYALTY_VIEW',
        'TCS_MANAGE',
      ]);
    });

    List<String> offered(List<String> codes, {bool firm = true}) {
      final ModuleVisibility visibility = ModuleVisibility(
        permissions: _holding(codes),
        activeBusinessModules: null,
        salesStages: SalesWorkflowSettings.wholeChain,
        hasActiveFirm: firm,
      );
      final MenuAreaSpec? shown =
          MenuLayout.visible(MenuLayout.settings, visibility);
      return [
        for (final MenuGroupSpec group in shown?.groups ?? const [])
          if (group.label == 'Selling')
            for (final MenuItemSpec item in group.items) item.label,
      ];
    }

    test('an item appears only for whoever holds its code', () {
      expect(offered(const []), isEmpty);
      expect(offered(['SALES_VIEW']),
          ['Sales Stages', 'Price Floor', 'Discount Limits']);
      expect(offered(['CUSTOMER_VIEW']), ['Credit Control']);
      expect(offered(['LOYALTY_VIEW']), ['Loyalty Scheme']);
      expect(offered(['TCS_MANAGE']), ['TCS Settings']);
      // Viewing TCS is not changing it, and the dialog has no read-only form.
      expect(offered(['TCS_VIEW']), isEmpty);
      expect(
        offered(
            ['SALES_VIEW', 'CUSTOMER_VIEW', 'LOYALTY_VIEW', 'TCS_MANAGE']),
        hasLength(6),
      );
    });

    test('a firm-scoped setting is not offered with no firm chosen', () {
      expect(
        offered(['SALES_VIEW', 'CUSTOMER_VIEW'], firm: false),
        isEmpty,
      );
    });

    test('the menu comment no longer says these are waiting', () {
      final String source =
          File('lib/phase2/menu_layout.dart').readAsStringSync();
      expect(source, isNot(contains('join [settings] when the Settings page')));
    });
  });
}
