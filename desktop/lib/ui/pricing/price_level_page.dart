import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/pricing.dart';
import '../resource_management_page.dart';
import '../workspace/desktop_framework.dart';

/// The named price levels a firm sells at -- "Dealer", "Retail", "Export".
///
/// A product carries one rate per level; a customer, or a customer group, is
/// put on one level. Which price a line gets is decided by the server, in this
/// order: a price list, then the customer's level (else their group's), then
/// the product's own price.
///
/// Expressed as a `ResourceDefinition` because it is a flat list with no tree
/// and no nested form.
ResourceDefinition<PriceLevelRecord> priceLevelDefinition(
  ApiClient api,
  PermissionService permissions, {
  bool showFrame = true,
}) =>
    ResourceDefinition<PriceLevelRecord>(
      title: 'Price Levels',
      // Builds `/api/v1/price-levels[/{id}]` through the generic helpers.
      resource: 'price-levels',
      showFrame: showFrame,
      // The version the row was read at rides along as If-Match, on save and
      // on delete (D-PRC-13).
      recordNoun: 'price level',
      updateRecord: (level, body) => api.updatePriceLevel(
        level.id,
        body,
        expectedVersion: preconditionFor(level.version),
      ),
      deleteRecord: (level) => api.deletePriceLevel(
        level.id,
        expectedVersion: preconditionFor(level.version),
      ),
      description: 'The named levels a customer can be put on.',
      searchHint: 'Search price levels by code or name',
      headers: const ['Code', 'Name', 'Order', 'Status'],
      cells: (level) => [
        level.code,
        level.name,
        '${level.sortOrder}',
        level.isActive ? 'Active' : 'Inactive',
      ],
      id: (level) => level.id,
      load: ({
        int page = 1,
        String search = '',
        String sortBy = 'created_at',
        bool descending = true,
      }) async {
        // The endpoint answers with a plain list; filter here so the request
        // does not carry a `search` the server would ignore.
        final List<PriceLevelRecord> all = await api.priceLevels();
        final String term = search.trim().toLowerCase();
        final List<PriceLevelRecord> matching = term.isEmpty
            ? all
            : all
                .where((level) =>
                    level.code.toLowerCase().contains(term) ||
                    level.name.toLowerCase().contains(term))
                .toList();
        return PagedResult<PriceLevelRecord>(
          items: matching,
          total: matching.length,
        );
      },
      canUseAction: (action, _) {
        final bool canManage = permissions.hasPermission('PRICE_LIST_MANAGE');
        return switch (action) {
          ToolbarAction.newItem ||
          ToolbarAction.edit ||
          ToolbarAction.delete =>
            canManage,
          _ => permissions.hasPermission('PRICE_LIST_VIEW'),
        };
      },
      fields: const [
        FieldSpec(
          key: 'code',
          label: 'Code',
          requiredOnCreate: true,
          helperText: 'Letters, digits, _ and - only. Stored in upper case.',
        ),
        FieldSpec(key: 'name', label: 'Name', requiredOnCreate: true),
        FieldSpec(
          key: 'sort_order',
          label: 'Order',
          helperText: 'Levels are listed in this order, lowest first.',
        ),
        FieldSpec(
          key: 'is_active',
          label: 'Active',
          boolean: true,
          helperText: 'An inactive level stays on the customers using it.',
        ),
      ],
      initialValues: (level) => <String, dynamic>{
        'code': level?.code ?? '',
        'name': level?.name ?? '',
        'sort_order': '${level?.sortOrder ?? 0}',
        'is_active': level?.isActive ?? true,
      },
      payload: (values, isCreating) => <String, dynamic>{
        'code': (values['code'] as String? ?? '').trim().toUpperCase(),
        'name': (values['name'] as String? ?? '').trim(),
        'sort_order':
            int.tryParse((values['sort_order'] as String? ?? '').trim()) ?? 0,
        'is_active': values['is_active'] == true,
      },
    );

/// The Price Levels tab.
class PriceLevelPage extends StatelessWidget {
  const PriceLevelPage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  Widget build(BuildContext context) => ResourceManagementPage<PriceLevelRecord>(
        api: api,
        definition: priceLevelDefinition(api, permissions, showFrame: false),
      );
}
