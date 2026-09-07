import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/entities.dart';

/// Edit what one person does, firm by firm.
///
/// A firm-tier role always names its firm, so there is no single "roles" set
/// to edit: a person can be a sales manager in one firm and a cashier in
/// another, and each firm's administrator owns their own row. This is the
/// screen that says so — one section per firm the person belongs to, each
/// saved on its own.
///
/// It is deliberately not a `ResourceDefinition` field. The generic form edits
/// one record with one value per key; this edits *n* independent sets, one per
/// firm, and flattening them into a single box is exactly the shape that let a
/// platform administrator's save collapse every firm's roles into one.
class FirmRolesDialog extends StatefulWidget {
  const FirmRolesDialog({
    super.key,
    required this.api,
    required this.userId,
    required this.userLabel,
    required this.firmsResource,
    this.staffableFirmIds,
  });

  final ApiClient api;
  final String userId;
  final String userLabel;

  /// Where the firm names come from: `firms` for a platform administrator,
  /// `me/firms` for anybody else. `/api/v1/firms` is platform-only and
  /// answers 403 to a firm administrator, which left this dialog -- the one
  /// screen the user form sends them to -- showing an error and no firm at
  /// all.
  final String firmsResource;

  /// The firms this caller may write roles in, or null for every firm.
  ///
  /// A firm administrator sees a section per firm the person belongs to
  /// **and** they may staff. The server refuses the rest by name, and a
  /// section whose Save can only be refused is a broken control, not a
  /// choice.
  final Set<String>? staffableFirmIds;

  @override
  State<FirmRolesDialog> createState() => _FirmRolesDialogState();
}

class _FirmRolesDialogState extends State<FirmRolesDialog> {
  bool _loading = true;
  String _error = '';
  String _saving = '';

  /// The firms this person belongs to, in the order the server listed them.
  List<AssignmentOption> _firms = const [];

  /// Every assignable role, and what each firm currently holds.
  List<AssignmentOption> _roles = const [];

  /// The roles held in *every* firm. Shown, never edited here: a global grant
  /// is a platform decision, and it applies in each firm below -- so leaving
  /// it out would show a firm administrator less than the person really has.
  Set<String> _global = const {};
  final Map<String, Set<String>> _selected = {};

  /// What was loaded, so Save can be offered only where something changed.
  final Map<String, Set<String>> _loaded = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final List<AssignmentOption> allFirms =
          await widget.api.options(widget.firmsResource);
      final Map<String, dynamic> membership =
          await widget.api.userFirmAssignmentValues(widget.userId);
      final Set<String> memberOf = (membership['firm_ids'] as String? ?? '')
          .split(',')
          .where((id) => id.isNotEmpty)
          .toSet();
      final List<AssignmentOption> roles = await widget.api.options('roles');
      final List<String> global =
          await widget.api.userGlobalRoles(widget.userId);

      final Set<String>? staffable = widget.staffableFirmIds;
      final List<AssignmentOption> firms = allFirms
          .where((firm) =>
              memberOf.contains(firm.id) &&
              (staffable == null || staffable.contains(firm.id)))
          .toList();
      for (final AssignmentOption firm in firms) {
        final List<String> held =
            await widget.api.userFirmRoles(widget.userId, firm.id);
        _selected[firm.id] = held.toSet();
        _loaded[firm.id] = held.toSet();
      }
      if (!mounted) return;
      setState(() {
        _firms = firms;
        _roles = roles;
        _global = global.toSet();
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  bool _changed(String firmId) =>
      !setEquals(_selected[firmId] ?? const {}, _loaded[firmId] ?? const {});

  static bool setEquals(Set<String> a, Set<String> b) =>
      a.length == b.length && a.containsAll(b);

  Future<void> _save(String firmId) async {
    setState(() => _saving = firmId);
    try {
      await widget.api.setUserFirmRoles(
        widget.userId,
        firmId,
        (_selected[firmId] ?? const <String>{}).toList(),
      );
      if (!mounted) return;
      setState(() {
        _loaded[firmId] = {...?_selected[firmId]};
        _saving = '';
      });
      final String firm =
          _firms.firstWhere((f) => f.id == firmId).label;
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Roles saved for $firm.')),
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      // The server refuses a firm outside the caller's reach by name. Show
      // that rather than a generic failure: whoever hit it needs to know it
      // is not their firm to change.
      setState(() {
        _saving = '';
        _error = error.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Dialog(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 620, maxHeight: 640),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 18, 20, 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Roles by firm', style: theme.textTheme.titleLarge),
                  const SizedBox(height: 4),
                  Text(
                    widget.userLabel,
                    style: theme.textTheme.bodySmall,
                  ),
                ],
              ),
            ),
            const Divider(height: 1),
            Flexible(child: _body(theme)),
            const Divider(height: 1),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 10, 20, 14),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Close'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _body(ThemeData theme) {
    if (_loading) {
      return const Padding(
        padding: EdgeInsets.all(40),
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (_firms.isEmpty) {
      // Two different answers. "No firm yet" is about the person; "no firm
      // you administer" is about the caller's reach, and telling a firm
      // administrator the person belongs nowhere when they belong somewhere
      // else would be false.
      final bool scoped = widget.staffableFirmIds != null;
      return Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              scoped
                  ? 'This person belongs to no firm you administer.'
                  : 'This person belongs to no firm yet.',
              style: theme.textTheme.bodyMedium,
            ),
            const SizedBox(height: 6),
            Text(
              scoped
                  ? 'Add them to your firm first, and their roles there '
                      'can be set here.'
                  : 'A role is held in a firm, so add them to one first.',
              style: theme.textTheme.bodySmall,
              textAlign: TextAlign.center,
            ),
          ],
        ),
      );
    }
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 14),
      children: [
        if (_error.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Text(
              _error,
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: theme.colorScheme.error),
            ),
          ),
        _globalSection(theme),
        for (final AssignmentOption firm in _firms) _firmSection(theme, firm),
      ],
    );
  }

  /// The roles that apply in every firm, disabled.
  Widget _globalSection(ThemeData theme) {
    final List<AssignmentOption> held =
        _roles.where((role) => _global.contains(role.id)).toList();
    return Padding(
      padding: const EdgeInsets.only(bottom: 22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Applies in every firm', style: theme.textTheme.titleSmall),
          const SizedBox(height: 6),
          if (held.isEmpty)
            Text(
              'None. Every role this person has is set firm by firm below.',
              style: theme.textTheme.bodySmall,
            )
          else
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final AssignmentOption role in held)
                  // Disabled rather than absent: it applies here, and a firm
                  // administrator needs to see it to understand what the
                  // person can do -- they simply may not change it.
                  FilterChip(
                    label: Text(role.label),
                    selected: true,
                    onSelected: null,
                  ),
              ],
            ),
          const SizedBox(height: 4),
          Text(
            'Set by a platform administrator on the user form. '
            'These cannot be changed here.',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: 12),
          const Divider(height: 1),
        ],
      ),
    );
  }

  Widget _firmSection(ThemeData theme, AssignmentOption firm) {
    final Set<String> selected = _selected[firm.id] ?? <String>{};
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  firm.label,
                  style: theme.textTheme.titleSmall,
                ),
              ),
              if (_saving == firm.id)
                const SizedBox(
                  height: 16,
                  width: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              else
                TextButton(
                  onPressed: _changed(firm.id) ? () => _save(firm.id) : null,
                  child: const Text('Save'),
                ),
            ],
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final AssignmentOption role in _roles)
                FilterChip(
                  label: Text(role.label),
                  selected: selected.contains(role.id),
                  onSelected: (on) => setState(() {
                    final Set<String> next = {..._selected[firm.id] ?? const {}};
                    if (on) {
                      next.add(role.id);
                    } else {
                      next.remove(role.id);
                    }
                    _selected[firm.id] = next;
                  }),
                ),
            ],
          ),
          if (selected.isEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                'No roles here — a member with nothing to do.',
                style: theme.textTheme.bodySmall,
              ),
            ),
        ],
      ),
    );
  }
}

/// Open the roles-by-firm editor for one person.
Future<void> showFirmRolesDialog(
  BuildContext context, {
  required ApiClient api,
  required String userId,
  required String userLabel,
  required String firmsResource,
  Set<String>? staffableFirmIds,
}) =>
    showDialog<void>(
      context: context,
      builder: (_) => FirmRolesDialog(
        api: api,
        userId: userId,
        userLabel: userLabel,
        firmsResource: firmsResource,
        staffableFirmIds: staffableFirmIds,
      ),
    );
