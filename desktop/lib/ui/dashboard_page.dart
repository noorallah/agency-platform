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
