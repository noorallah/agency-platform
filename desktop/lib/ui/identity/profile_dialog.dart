import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/entities.dart';

/// What the platform holds about the signed-in person, shown to them.
///
/// Read-only, and reachable by anybody signed in: the details are theirs to
/// see without holding `USER_VIEW`, which most people do not, and changing
/// them stays an administrator's job -- the dialog says so rather than
/// offering boxes that would not save. Read fresh from `GET /me` on open,
/// with the session's copy as the fallback while the read is in flight.
///
/// The one thing on it a person *can* change is their password, through
/// [onChangePassword]. Answers true when that happened: the caller then ends
/// the session, since the server has already revoked it.
Future<bool> showProfileDialog(
  BuildContext context, {
  required ApiClient api,
  required List<AssignedFirm> firms,
  CurrentUser? known,
  Future<bool> Function(BuildContext context)? onChangePassword,
}) =>
    showDialog<bool>(
      context: context,
      builder: (_) => ProfileDialog(
        api: api,
        firms: firms,
        known: known,
        onChangePassword: onChangePassword,
      ),
    ).then((changed) => changed ?? false);

class ProfileDialog extends StatefulWidget {
  const ProfileDialog({
    super.key,
    required this.api,
    required this.firms,
    this.known,
    this.onChangePassword,
  });

  final ApiClient api;

  /// The firms this person belongs to, with the primary marked.
  final List<AssignedFirm> firms;

  /// What the session already knows, shown until the fresh read lands.
  final CurrentUser? known;

  /// Opens the change-password dialog and answers whether it succeeded. Null
  /// hides the button, for a caller with nowhere to send the person after.
  final Future<bool> Function(BuildContext context)? onChangePassword;

  @override
  State<ProfileDialog> createState() => _ProfileDialogState();
}

class _ProfileDialogState extends State<ProfileDialog> {
  late CurrentUser? _user = widget.known;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final CurrentUser fresh = await widget.api.me();
      if (!mounted) return;
      setState(() => _user = fresh);
    } on ApiException catch (error) {
      if (!mounted) return;
      // The session's copy is still on screen; say the refresh failed rather
      // than hiding what is known.
      setState(() => _error = error.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final CurrentUser? user = _user;
    return AlertDialog(
      title: const Text('My profile'),
      content: SizedBox(
        width: 560,
        height: 480,
        child: user == null
            ? Center(
                child: _error == null
                    ? const CircularProgressIndicator()
                    : Text(_error!, style: theme.textTheme.bodyMedium),
              )
            : _body(theme, user),
      ),
      actions: [
        if (widget.onChangePassword != null)
          OutlinedButton.icon(
            icon: const Icon(Icons.password_outlined),
            label: const Text('Change password'),
            onPressed: () async {
              final bool changed = await widget.onChangePassword!(context);
              if (!context.mounted) return;
              // Close this dialog too: the session is about to end, and a
              // profile left open over the login screen is a stale window.
              if (changed) Navigator.of(context).pop(true);
            },
          ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Close'),
        ),
      ],
    );
  }

  // A plain scroll view rather than a lazy list: the content is a screenful
  // of short rows, and a lazy list builds only what is on screen, which is
  // how a section can be present in the data and absent from the widget
  // tree a test or a screen reader asks about.
  Widget _body(ThemeData theme, CurrentUser user) => SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(
                'Showing what was known at sign-in; the refresh failed: '
                '$_error',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.error),
              ),
            ),
          Text(
            user.fullName.isEmpty ? user.email : user.fullName,
            style: theme.textTheme.titleLarge,
          ),
          Text(user.email, style: theme.textTheme.bodyMedium),
          if (user.isPlatformAdmin)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Chip(
                label: const Text('Platform administrator'),
                avatar: const Icon(Icons.shield_outlined, size: 16),
                visualDensity: VisualDensity.compact,
              ),
            ),
          const SizedBox(height: 12),
          _section(theme, 'Work', [
            ('Employee code', user.employeeCode),
            ('Designation', user.designation),
            ('Department', user.department),
            ('Reports to', user.reportingManager),
            ('Employment type', user.employmentType),
            ('Joined', _date(user.joiningDate)),
          ]),
          _section(theme, 'Contact', [
            ('Mobile', user.personalMobile),
            ('Alternate mobile', user.alternateMobile),
            ('Office email', user.officeEmail),
            ('Personal email', user.personalEmail),
          ]),
          _firms(theme),
          _roles(theme, user),
          _section(theme, 'Sign-in', [
            ('Last signed in', _dateTime(user.lastLoginAt)),
          ]),
          const SizedBox(height: 8),
          Text(
            'These details are held by your administrator. Ask them to '
            'change anything here; your appearance, primary firm and '
            'password are yours to set.',
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
          ],
        ),
      );

  Widget _section(
    ThemeData theme,
    String title,
    List<(String, String)> rows,
  ) =>
      Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: theme.textTheme.titleSmall),
            const SizedBox(height: 4),
            for (final (String label, String value) in rows)
              _row(theme, label, value),
          ],
        ),
      );

  Widget _row(ThemeData theme, String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 150,
              child: Text(
                label,
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
              ),
            ),
            Expanded(
              child: Text(
                // "Not set" rather than a blank: a blank reads as a field
                // that failed to load, and this one simply holds nothing.
                value.isEmpty ? 'Not set' : value,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: value.isEmpty
                      ? theme.colorScheme.onSurfaceVariant
                      : theme.colorScheme.onSurface,
                ),
              ),
            ),
          ],
        ),
      );

  Widget _firms(ThemeData theme) => _section(theme, 'Firms', [
        if (widget.firms.isEmpty) ('Member of', ''),
        for (final AssignedFirm firm in widget.firms)
          (
            firm.isPrimary ? 'Primary' : 'Member of',
            '${firm.name} (${firm.code})',
          ),
      ]);

  /// The global tier first, then each firm's own, so the reader sees what
  /// applies everywhere before what applies in one place.
  Widget _roles(ThemeData theme, CurrentUser user) {
    final List<MyRole> global =
        user.roles.where((role) => role.firmId == null).toList();
    final Map<String, List<MyRole>> byFirm = {};
    for (final MyRole role in user.roles.where((role) => role.firmId != null)) {
      byFirm.putIfAbsent(role.firmCode ?? role.firmId!, () => []).add(role);
    }
    String names(List<MyRole> roles) =>
        roles.map((role) => role.name.isEmpty ? role.code : role.name).join(', ');
    return _section(theme, 'Access', [
      if (user.roles.isEmpty) ('Roles', ''),
      if (global.isNotEmpty) ('In every firm', names(global)),
      for (final MapEntry<String, List<MyRole>> entry in byFirm.entries)
        ('In ${entry.key}', names(entry.value)),
    ]);
  }

  static String _date(String iso) => iso.length >= 10 ? iso.substring(0, 10) : iso;

  static String _dateTime(String iso) {
    if (iso.length < 16) return iso;
    return '${iso.substring(0, 10)} ${iso.substring(11, 16)} UTC';
  }
}
