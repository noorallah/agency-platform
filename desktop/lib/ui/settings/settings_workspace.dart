import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/module_catalog.dart';
import 'audit_log_page.dart';
import 'diagnostics_page.dart';

/// The settings workspace.
///
/// Two tabs are real, and both exist because the server had been recording
/// something nothing could read: the audit trail, written by every mutation
/// and held append-only by a database trigger in every store, and the error
/// reports the desktop has been queueing to disk and flushing since the crash
/// reporter was written.
class SystemSettingsWorkspace extends StatelessWidget {
  const SystemSettingsWorkspace({
    super.key,
    required this.api,
    required this.permissions,
    required this.tabId,
    required this.firmLabel,
  });

  final ApiClient api;
  final PermissionService permissions;
  final String tabId;

  /// The firm whose trail is in scope, or null for the platform trail.
  final String? firmLabel;

  @override
  Widget build(BuildContext context) => ModuleWorkspaceFrame(
        title: ModuleCatalog.byId(AppModule.settings).label,
        description: 'What the system recorded, and how it is configured.',
        breadcrumbs: const ['Workspace', 'Settings'],
        child: switch (tabId) {
          'audit-logs' => AuditLogPage(
              api: api,
              permissions: permissions,
              firmLabel: firmLabel,
            ),
          'diagnostics' => DiagnosticsPage(
              api: api,
              permissions: permissions,
            ),
          _ => const StandardEmptyState(
              type: EmptyStateType.noRecords,
              title: 'Not built yet',
              message: 'Background jobs, system settings and API monitoring '
                  'have no endpoint behind them, so there is nothing to show '
                  'rather than something to hide.',
            ),
        },
      );
}
