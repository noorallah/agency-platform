import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';

/// Per-firm business configuration, kept out of the firm master record.
///
/// The business profile decides which features and modules a firm operates, and
/// its catalogue is a firm-owned table -- there is no copy in the platform
/// schema. It therefore cannot be read without a firm context, which is why it
/// used to fail with a 503 as a dropdown inside the platform-level Firms
/// dialog. Here the firm context is the page's precondition rather than an
/// assumption, so the requirement is visible instead of being a stack trace.
class FirmSettingsPage extends StatefulWidget {
  const FirmSettingsPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    required this.activeFirmId,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final String? activeFirmId;

  @override
  State<FirmSettingsPage> createState() => _FirmSettingsPageState();
}

/// Says what an unset profile actually costs.
///
/// The framework falls back to the platform default rather than failing, so a
/// firm with no profile keeps working while operating as GENERIC — it runs the
/// wrong feature set quietly, which is exactly the kind of gap nobody goes
/// looking for.
class _UnassignedProfileWarning extends StatelessWidget {
  const _UnassignedProfileWarning();

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final Color warning = context.semanticColors.warning;
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: warning.withValues(alpha: 0.10),
        borderRadius: AppRadius.medium,
        border: Border.all(color: warning.withValues(alpha: 0.45)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.warning_amber_rounded, color: warning, size: 20),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'No business profile assigned',
                  style: theme.textTheme.titleSmall?.copyWith(color: warning),
                ),
                const SizedBox(height: 2),
                Text(
                  'This firm is running on the platform default, so it may be '
                  'operating the wrong feature and module set. Choose a profile '
                  'below to correct it.',
                  style: theme.textTheme.bodySmall,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _FirmSettingsPageState extends State<FirmSettingsPage> {
  List<BusinessProfileRecord> _profiles = const [];
  String _assignedProfileId = '';
  String _selectedProfileId = '';
  bool _loading = false;
  bool _saving = false;
  String? _error;

  bool get _canAssign => widget.permissions.hasPermission('FIRM_UPDATE');
  bool get _dirty =>
      _selectedProfileId.isNotEmpty && _selectedProfileId != _assignedProfileId;

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm) _load();
  }

  @override
  void didUpdateWidget(covariant FirmSettingsPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.activeFirmId != oldWidget.activeFirmId && widget.hasActiveFirm) {
      _load();
    }
  }

  Future<void> _load() async {
    final String? firmId = widget.activeFirmId;
    if (firmId == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final PagedResult<BusinessProfileRecord> profiles =
          await widget.api.businessProfiles(page: 1, sortBy: 'code');
      final Map<String, dynamic> assignment =
          await widget.api.firmBusinessProfileAssignmentValues(firmId);
      if (!mounted) return;
      setState(() {
        _profiles = profiles.items;
        _assignedProfileId = stringValue(assignment['business_profile_id']);
        _selectedProfileId = _assignedProfileId;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _save() async {
    final String? firmId = widget.activeFirmId;
    if (firmId == null || _selectedProfileId.isEmpty) return;
    setState(() => _saving = true);
    try {
      await widget.api.assignBusinessProfileToFirm(firmId, _selectedProfileId);
      if (!mounted) return;
      setState(() => _assignedProfileId = _selectedProfileId);
      NotificationService.show(
        context,
        'Business profile updated for the active firm.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.isForbidden
            ? 'You are not authorized to change the business profile.'
            : exception.message,
        kind: AppNotificationKind.error,
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        message: 'Select a firm from the header to configure its business '
            'settings. These settings are stored per firm.',
      );
    }
    if (_loading && _profiles.isEmpty) return const WorkspaceLoadingState();
    if (_error != null) {
      return WorkspaceErrorState(message: _error!, onRetry: _load);
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(
            title: 'Business profile',
            description:
                'Decides which features and modules the active firm operates. '
                'A firm without one falls back to the platform default.',
          ),
          const SizedBox(height: AppSpacing.md),
          if (_assignedProfileId.isEmpty) ...[
            const _UnassignedProfileWarning(),
            const SizedBox(height: AppSpacing.md),
          ],
          if (_profiles.isEmpty)
            const StandardEmptyState(
              type: EmptyStateType.noRecords,
              message: 'No business profiles are configured.',
            )
          else
            Card(
              child: Padding(
                padding: const EdgeInsets.all(AppSpacing.lg),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 520),
                      child: DropdownButtonFormField<String>(
                        initialValue: _selectedProfileId.isEmpty
                            ? null
                            : _selectedProfileId,
                        decoration: const InputDecoration(
                          labelText: 'Business profile',
                        ),
                        items: [
                          for (final BusinessProfileRecord profile in _profiles)
                            DropdownMenuItem(
                              value: profile.id,
                              child: Text('${profile.code} — ${profile.name}'),
                            ),
                        ],
                        onChanged: _canAssign && !_saving
                            ? (value) => setState(
                                  () => _selectedProfileId = value ?? '',
                                )
                            : null,
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    // Wrap, not Row: the permission hint beside the button
                    // overflows a narrow workspace column otherwise.
                    Wrap(
                      spacing: AppSpacing.md,
                      runSpacing: AppSpacing.sm,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        FilledButton.icon(
                          onPressed:
                              _canAssign && _dirty && !_saving ? _save : null,
                          icon: _saving
                              ? const SizedBox(
                                  height: 16,
                                  width: 16,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Icon(Icons.check),
                          label: Text(_saving ? 'Saving…' : 'Apply profile'),
                        ),
                        if (!_canAssign)
                          Text(
                            'FIRM_UPDATE is required to change this.',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
