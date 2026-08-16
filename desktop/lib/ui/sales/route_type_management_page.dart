import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/sales_territory.dart';
import '../resource_management_page.dart';
import '../workspace/desktop_framework.dart';

/// The kinds of round this firm runs — a sales beat, a collection round.
///
/// The API has accepted a `POST /route-types` since the module was written and
/// nothing called it, so the only route types a firm ever had were the two the
/// demo seeder created. A firm that wanted a third — a merchandising round, a
/// van-sales beat — had no way to add one, and the route type dropdown on the
/// territory editor apologised for a screen that did not exist.
///
/// Expressed as a `ResourceDefinition` rather than a bespoke page: it is a flat
/// code/name/description/active list with no tree, no nested form and no
/// assignments, which is exactly what that framework is for.
ResourceDefinition<TerritoryRouteTypeRecord> routeTypeDefinition(
  ApiClient api,
  PermissionService permissions, {
  bool showFrame = true,
}) =>
    ResourceDefinition<TerritoryRouteTypeRecord>(
      title: 'Route Types',
      // Builds `/api/v1/sales-territories/route-types[/{id}]` through the
      // generic create/update/delete helpers.
      resource: 'sales-territories/route-types',
      showFrame: showFrame,
      description: 'The kinds of round this firm runs.',
      searchHint: 'Search route types by code or name',
      headers: const ['Code', 'Name', 'Description', 'Status'],
      cells: (type) => [
        type.code,
        type.name,
        type.description,
        type.isActive ? 'Active' : 'Inactive',
      ],
      id: (type) => type.id,
      load: ({
        int page = 1,
        String search = '',
        String sortBy = 'created_at',
        bool descending = true,
      }) async {
        // The endpoint answers with a plain list, not a page — a firm has a
        // handful of these. Filtering here rather than sending `search` keeps
        // the request honest: the server would ignore it.
        final List<TerritoryRouteTypeRecord> all =
            await api.territoryRouteTypes();
        final String term = search.trim().toLowerCase();
        final List<TerritoryRouteTypeRecord> matching = term.isEmpty
            ? all
            : all
                .where((type) =>
                    type.code.toLowerCase().contains(term) ||
                    type.name.toLowerCase().contains(term))
                .toList();
        return PagedResult<TerritoryRouteTypeRecord>(
          items: matching,
          total: matching.length,
        );
      },
      canUseAction: (action, _) {
        final bool canView = permissions.hasPermission('TERRITORY_VIEW');
        return switch (action) {
          ToolbarAction.newItem =>
            permissions.hasPermission('TERRITORY_CREATE'),
          ToolbarAction.edit => permissions.hasPermission('TERRITORY_UPDATE'),
          ToolbarAction.delete => permissions.hasPermission('TERRITORY_DELETE'),
          _ => canView,
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
          key: 'description',
          label: 'Description',
          multiline: true,
          fullWidth: true,
        ),
        FieldSpec(
          key: 'is_active',
          label: 'Active',
          boolean: true,
          helperText: 'An inactive type stays on the routes already using it.',
        ),
      ],
      initialValues: (type) => <String, dynamic>{
        'code': type?.code ?? '',
        'name': type?.name ?? '',
        'description': type?.description ?? '',
        'is_active': type?.isActive ?? true,
      },
      payload: (values, isCreating) => <String, dynamic>{
        'code': (values['code'] as String? ?? '').trim().toUpperCase(),
        'name': (values['name'] as String? ?? '').trim(),
        'description': (values['description'] as String? ?? '').trim().isEmpty
            ? null
            : (values['description'] as String).trim(),
        'is_active': values['is_active'] == true,
      },
    );

/// The Route Types tab.
class RouteTypeManagementPage extends StatelessWidget {
  const RouteTypeManagementPage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  Widget build(BuildContext context) =>
      ResourceManagementPage<TerritoryRouteTypeRecord>(
        api: api,
        definition: routeTypeDefinition(api, permissions, showFrame: false),
      );
}
