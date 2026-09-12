import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/entities.dart';

/// What a firm still needs before it can trade, with the two steps that can be
/// done from here done from here.
///
/// Creating a firm records the intent. Its storage, business profile, chart of
/// accounts, tax and first branch are each a separate act in a different
/// place, and until 2026-09-08 the chart of accounts existed only as a script
/// -- a firm created in the product could not be finished in the product, and
/// nothing said so until its first invoice approval was refused. This reads
/// `GET /firms/{id}/readiness`, the same list the shell script prints, and
/// offers **Provision storage** and **Open the books** in place. The other
/// steps name the screen they are done on.
///
/// **Apply GST template** on the Tax row and **Assign** on the Business
/// profile row joined the same day: with them a fresh firm goes from created
/// to able to trade without leaving the panel.
///
/// Returns true when something was changed, so the grid can reload.
Future<bool> showFirmSetupDialog(
  BuildContext context, {
  required ApiClient api,
  required Firm firm,
}) =>
    showDialog<bool>(
      context: context,
      builder: (_) => FirmSetupDialog(api: api, firm: firm),
    ).then((changed) => changed ?? false);

/// Where each step that has no button here is done, for the step's row.
///
/// Every one of these lives in the firm's own store, so the way there is
/// **Open this firm** on the grid and then the screen named.
const Map<String, String> firmSetupHints = {
  'geography': 'Open this firm, then Territories → Geography Masters. '
      'Applying the GST template adds the country.',
  'members': 'Administration → Users → Add existing user, or '
      'User-Firm Assignments.',
};

class FirmSetupDialog extends StatefulWidget {
  const FirmSetupDialog({super.key, required this.api, required this.firm});

  final ApiClient api;
  final Firm firm;

  @override
  State<FirmSetupDialog> createState() => _FirmSetupDialogState();
}

class _FirmSetupDialogState extends State<FirmSetupDialog> {
  FirmReadiness? _readiness;
  bool _loading = true;
  bool _busy = false;
  bool _changed = false;
  String? _error;
  String? _notice;
  List<BusinessProfileRecord> _profiles = const [];
  String? _chosenProfile;

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
      final FirmReadiness readiness =
          await widget.api.firmReadiness(widget.firm.id);
      // The catalogue lives in the firm's own store, so it can only be read
      // once that store exists; and only the row that needs it asks for it.
      final bool needsProfiles = readiness.steps
          .any((step) => step.key == 'business_profile' && step.isMissing);
      final List<BusinessProfileRecord> profiles = needsProfiles
          ? await widget.api.firmProfileCatalogue(widget.firm.id)
          : const [];
      if (!mounted) return;
      setState(() {
        _readiness = readiness;
        _profiles = profiles;
        if (!profiles.any((profile) => profile.id == _chosenProfile)) {
          _chosenProfile = null;
        }
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = error.message;
      });
    }
  }

  /// Runs one of the two actions and re-reads the list, so the row the
  /// action was about shows the result rather than a stale MISSING.
  Future<void> _run(Future<String> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      final String message = await action();
      if (!mounted) return;
      _changed = true;
      setState(() => _notice = message);
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget? _actionFor(FirmReadinessStep step) {
    if (!step.isMissing) return null;
    return switch (step.key) {
      'storage' => FilledButton.tonalIcon(
          onPressed: _busy
              ? null
              : () => _run(
                  () => widget.api.provisionFirmStorage(widget.firm.id)),
          icon: const Icon(Icons.dns_outlined, size: 18),
          label: const Text('Provision storage'),
        ),
      'books' => FilledButton.icon(
          onPressed: _busy
              ? null
              : () => _run(() => widget.api.openFirmBooks(widget.firm.id)),
          icon: const Icon(Icons.menu_book_outlined, size: 18),
          label: const Text('Open the books'),
        ),
      'tax' => FilledButton.tonalIcon(
          onPressed: _busy
              ? null
              : () =>
                  _run(() => widget.api.applyFirmTaxTemplate(widget.firm.id)),
          icon: const Icon(Icons.percent_outlined, size: 18),
          label: const Text('Apply GST template'),
        ),
      'business_profile' => _profilePicker(),
      // A branch and a warehouse are the firm's own to name, so this is a
      // default and not a decision: HO and MAIN, renamed on their own
      // screens afterwards. Stock cannot move until both exist.
      'branches' => FilledButton.tonalIcon(
          onPressed: _busy
              ? null
              : () => _run(
                  () => widget.api.createFirmDefaultBranch(widget.firm.id)),
          icon: const Icon(Icons.store_outlined, size: 18),
          label: const Text('Create head office and main warehouse'),
        ),
      _ => null,
    };
  }

  /// The catalogue and an Assign button, on the row itself. A dropdown
  /// rather than a second dialog: there are a dozen profiles and choosing one
  /// is the whole step.
  Widget _profilePicker() {
    if (_profiles.isEmpty) {
      return const Text("No profiles in this firm's store.");
    }
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: 200,
          child: DropdownButtonFormField<String>(
            isExpanded: true,
            key: const ValueKey('firm-setup-profile'),
            initialValue: _chosenProfile,
            isDense: true,
            decoration: const InputDecoration(
              labelText: 'Profile',
              isDense: true,
            ),
            items: [
              for (final BusinessProfileRecord profile in _profiles)
                DropdownMenuItem(
                  value: profile.id,
                  child: Text(profile.name, overflow: TextOverflow.ellipsis),
                ),
            ],
            onChanged:
                _busy ? null : (value) => setState(() => _chosenProfile = value),
          ),
        ),
        const SizedBox(width: 8),
        FilledButton.tonal(
          onPressed: _busy || _chosenProfile == null
              ? null
              : () => _run(() async {
                    await widget.api.assignBusinessProfileToFirm(
                      widget.firm.id,
                      _chosenProfile!,
                    );
                    final String name = _profiles
                        .firstWhere((profile) => profile.id == _chosenProfile)
                        .name;
                    return 'Business profile set to $name.';
                  }),
          child: const Text('Assign'),
        ),
      ],
    );
  }

  Widget _step(BuildContext context, FirmReadinessStep step) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme colors = theme.colorScheme;
    final (IconData icon, Color color) = switch (step.status) {
      'DONE' => (Icons.check_circle_outline, colors.primary),
      'BLOCKED' => (Icons.block_outlined, colors.outline),
      _ => (
          step.required ? Icons.error_outline : Icons.radio_button_unchecked,
          step.required ? colors.error : colors.tertiary,
        ),
    };
    final Widget? action = _actionFor(step);
    final String? hint =
        step.isMissing && action == null ? firmSetupHints[step.key] : null;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Icon(icon, size: 20, color: color),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(step.label, style: theme.textTheme.titleSmall),
                    const SizedBox(width: 8),
                    Text(
                      step.required ? 'Required' : 'Recommended',
                      style: theme.textTheme.labelSmall
                          ?.copyWith(color: colors.onSurfaceVariant),
                    ),
                  ],
                ),
                const SizedBox(height: 2),
                Text(step.detail, style: theme.textTheme.bodySmall),
                if (hint != null) ...[
                  const SizedBox(height: 2),
                  Text(
                    hint,
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: colors.onSurfaceVariant),
                  ),
                ],
                // Under the text rather than beside it: the profile picker
                // is a dropdown and a button, which beside a sentence of
                // detail overflowed the 800x600 window by 73px.
                if (action != null) ...[
                  const SizedBox(height: 6),
                  Align(alignment: Alignment.centerLeft, child: action),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _verdict(BuildContext context, FirmReadiness readiness) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme colors = theme.colorScheme;
    final (String text, Color color) = readiness.ready
        ? ('Finished. Every step is done.', colors.primary)
        : readiness.canPost
            ? (
                'Can post documents. The recommended steps are still open.',
                colors.tertiary,
              )
            : ('Cannot post documents yet.', colors.error);
    return Text(
      text,
      style: theme.textTheme.titleSmall?.copyWith(color: color),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final FirmReadiness? readiness = _readiness;
    return AlertDialog(
      title: Text('Set up ${widget.firm.code}'),
      content: SizedBox(
        width: 720,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                widget.firm.name,
                style: theme.textTheme.bodyMedium,
              ),
              const SizedBox(height: 8),
              if (_loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 24),
                  child: Center(child: CircularProgressIndicator()),
                )
              else ...[
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Text(
                      _error!,
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.error),
                    ),
                  ),
                if (_notice != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Text(_notice!, style: theme.textTheme.bodySmall),
                  ),
                if (readiness != null) ...[
                  _verdict(context, readiness),
                  const Divider(height: 16),
                  for (final FirmReadinessStep step in readiness.steps)
                    _step(context, step),
                ],
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton.icon(
          onPressed: _loading || _busy ? null : _load,
          icon: const Icon(Icons.refresh, size: 18),
          label: const Text('Refresh'),
        ),
        TextButton(
          onPressed:
              _busy ? null : () => Navigator.of(context).pop(_changed),
          child: const Text('Close'),
        ),
      ],
    );
  }
}
