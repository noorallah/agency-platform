import 'package:flutter/material.dart';

import '../core/api/api_client.dart';
import '../core/security/permission_service.dart';
import '../models/entities.dart';
import 'workspace/workspace_components.dart';

class DashboardPage extends StatefulWidget {
  const DashboardPage({
    super.key,
    required this.api,
    required this.permissions,
  });
  final ApiClient api;
  final PermissionService permissions;
  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  Json? _data;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final Json response = await widget.api.dashboard();
      if (mounted) {
        setState(() => _data = response);
      }
    } on ApiException catch (exception) {
      if (mounted) {
        setState(() => _error = exception.isForbidden
            ? 'You are not authorized to view the dashboard.'
            : exception.message);
      }
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final Json data = _data ?? const {};
    final Widget content;
    if (_loading) {
      content = const WorkspaceLoadingState();
    } else if (_error != null) {
      content = WorkspaceErrorState(message: _error!, onRetry: _load);
    } else {
      final List<dynamic> recentFirmsRaw = data['recent_firms'] is List
          ? data['recent_firms'] as List<dynamic>
          : const [];
      final List<dynamic> activityRaw = data['system_activity'] is List
          ? data['system_activity'] as List<dynamic>
          : const [];
      content = SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(
            spacing: 16,
            runSpacing: 16,
            children: [
              if (widget.permissions.canViewPage(const ['FIRM_VIEW']))
                SummaryMetricCard(
                  label: 'Firms',
                  value: stringValue(data['firms'] ?? '—'),
                  icon: Icons.business_outlined,
                ),
              if (widget.permissions.canViewPage(const ['USER_VIEW']))
                SummaryMetricCard(
                  label: 'Users',
                  value: stringValue(data['users'] ?? '—'),
                  icon: Icons.people_outline,
                ),
              if (widget.permissions.canViewPage(const ['ROLE_VIEW']))
                SummaryMetricCard(
                  label: 'Roles',
                  value: stringValue(data['roles'] ?? '—'),
                  icon: Icons.badge_outlined,
                ),
              if (widget.permissions.canViewPage(const ['PERMISSION_VIEW']))
                SummaryMetricCard(
                  label: 'Permissions',
                  value: stringValue(data['permissions'] ?? '—'),
                  icon: Icons.key_outlined,
                ),
            ],
          ),
          const SizedBox(height: 20),
          LayoutBuilder(
            builder: (context, constraints) {
              final bool stacked = constraints.maxWidth < 1120;
              final Widget recentFirmsCard = _DashboardListCard(
                title: 'Recent Firms',
                icon: Icons.apartment_outlined,
                emptyMessage: 'No recent firm activity available.',
                items: recentFirmsRaw
                    .whereType<Map>()
                    .map((entry) => Map<String, dynamic>.from(entry))
                    .map(
                      (entry) => _DashboardListItem(
                        primary: stringValue(entry['name']).isEmpty
                            ? stringValue(entry['code'])
                            : stringValue(entry['name']),
                        secondary: stringValue(entry['status']).isEmpty
                            ? 'No status'
                            : stringValue(entry['status']),
                      ),
                    )
                    .toList(),
              );
              final Widget activityCard = _DashboardListCard(
                title: 'System Activity',
                icon: Icons.timeline_outlined,
                emptyMessage: 'No recent system activity available.',
                items: activityRaw
                    .whereType<Map>()
                    .map((entry) => Map<String, dynamic>.from(entry))
                    .map(
                      (entry) => _DashboardListItem(
                        primary: stringValue(entry['title']).isEmpty
                            ? stringValue(entry['event'])
                            : stringValue(entry['title']),
                        secondary: stringValue(entry['at']).isEmpty
                            ? stringValue(entry['subtitle'])
                            : stringValue(entry['at']),
                      ),
                    )
                    .toList(),
              );
              if (stacked) {
                return Column(
                  children: [
                    recentFirmsCard,
                    const SizedBox(height: 16),
                    activityCard,
                  ],
                );
              }
              return Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(child: recentFirmsCard),
                  const SizedBox(width: 16),
                  Expanded(child: activityCard),
                ],
              );
            },
          ),
          const SizedBox(height: 20),
          _DashboardFutureWidgetsCard(
            permissions: widget.permissions,
          ),
        ]),
      );
    }
    return ModuleWorkspaceFrame(
      title: 'Dashboard',
      description: 'Platform administration at a glance.',
      breadcrumbs: const ['Workspace', 'Dashboard'],
      status: WorkspaceStatusBar(
        total: 0,
        selected: false,
        message: _loading ? 'Loading dashboard...' : null,
      ),
      child: content,
    );
  }
}

class _DashboardListItem {
  const _DashboardListItem({
    required this.primary,
    required this.secondary,
  });

  final String primary;
  final String secondary;
}

class _DashboardListCard extends StatelessWidget {
  const _DashboardListCard({
    required this.title,
    required this.icon,
    required this.items,
    required this.emptyMessage,
  });

  final String title;
  final IconData icon;
  final List<_DashboardListItem> items;
  final String emptyMessage;

  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(icon, size: 18),
                  const SizedBox(width: 8),
                  Text(title, style: Theme.of(context).textTheme.titleMedium),
                ],
              ),
              const SizedBox(height: 12),
              if (items.isEmpty)
                Text(emptyMessage)
              else
                for (final _DashboardListItem item in items.take(8))
                  Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(item.primary),
                        Text(
                          item.secondary,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
            ],
          ),
        ),
      );
}

class _DashboardFutureWidgetsCard extends StatelessWidget {
  const _DashboardFutureWidgetsCard({
    required this.permissions,
  });

  final PermissionService permissions;

  @override
  Widget build(BuildContext context) {
    final List<String> widgets = [
      if (permissions.canViewPage(const ['PURCHASE_VIEW'])) 'Purchase summary',
      if (permissions.canViewPage(const ['SALES_VIEW'])) 'Sales summary',
      if (permissions.canViewPage(const ['INVENTORY_VIEW']))
        'Inventory summary',
      if (permissions.canViewPage(const ['SALES_VIEW'])) 'Receivables',
      if (permissions.canViewPage(const ['PURCHASE_VIEW'])) 'Payables',
      'Alerts',
    ];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Planned Widgets',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: widgets
                  .map((label) => Chip(label: Text(label)))
                  .toList(growable: false),
            ),
          ],
        ),
      ),
    );
  }
}
