import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/entities.dart';
import '../workspace/paged_fetch.dart';

/// Who to hire, and into which job.
class HireExistingPerson {
  const HireExistingPerson({required this.person, required this.templateId});

  final UserLookupResult person;

  /// The job to apply once they are in the firm, or empty for none.
  final String templateId;
}

/// Find a user who already has an account and bring them into this firm.
///
/// The dialog owns its controller and its state. A caller that creates a
/// controller, awaits `showDialog` and then disposes it disposes it
/// *mid-animation*, and the field rebuilding during the exit throws "A
/// TextEditingController was used after being disposed" -- written twice in
/// this repository before `askForReason` existed.
///
/// `listsEveryone` is the platform caller's version: the directory is theirs
/// anyway, so the dialog opens already listing everybody not yet in the firm
/// and the box filters it. A firm caller must type at least three characters,
/// because the people outside their firm are other firms' staff -- the server
/// enforces both and this only decides what the screen asks for.
///
/// Returns null for a dismissal.
Future<HireExistingPerson?> findPersonToHire(
  BuildContext context,
  ApiClient api, {
  bool listsEveryone = false,
}) =>
    showDialog<HireExistingPerson>(
      context: context,
      builder: (_) => _FindPersonDialog(api: api, listsEveryone: listsEveryone),
    );

class _FindPersonDialog extends StatefulWidget {
  const _FindPersonDialog({required this.api, required this.listsEveryone});

  final ApiClient api;
  final bool listsEveryone;

  @override
  State<_FindPersonDialog> createState() => _FindPersonDialogState();
}

class _FindPersonDialogState extends State<_FindPersonDialog> {
  /// What the server refuses a firm caller below. Checked here too, so
  /// somebody typing two letters gets guidance rather than a 422 rendered as
  /// a failure. Zero for a platform caller, whose empty term is a request.
  int get _minimumTerm => widget.listsEveryone ? 0 : 3;

  final TextEditingController _term = TextEditingController();
  Timer? _debounce;
  List<UserLookupResult> _results = const [];
  String? _selectedId;
  String _templateId = '';
  List<UserTemplate> _templates = const [];
  bool _searching = false;
  String? _error;
  bool _searched = false;

  /// Which search is the latest. The opening list can run to several pages
  /// while a typed filter answers in one, so without this a slow, earlier
  /// answer could land on top of a faster, later one.
  int _searchSeq = 0;

  @override
  void initState() {
    super.initState();
    unawaited(_loadTemplates());
    if (widget.listsEveryone) unawaited(_search(''));
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _term.dispose();
    super.dispose();
  }

  Future<void> _loadTemplates() async {
    try {
      final PagedResult<UserTemplate> page =
          await widget.api.userTemplates(pageSize: 100);
      if (!mounted) return;
      setState(() =>
          _templates = page.items.where((template) => template.isActive).toList());
    } catch (_) {
      // A template is optional -- somebody can be added with no job and given
      // roles afterwards. Failing the whole dialog over it would be worse.
    }
  }

  void _onTermChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () => _search(value));
  }

  Future<void> _search(String value) async {
    final String term = value.trim();
    if (term.length < _minimumTerm) {
      setState(() {
        _results = const [];
        _searched = false;
        _error = null;
      });
      return;
    }
    final int seq = ++_searchSeq;
    setState(() {
      _searching = true;
      _error = null;
    });
    try {
      // Every page: a platform caller's empty term can run to a few hundred
      // people, and a list that silently stops at page one is a list somebody
      // will conclude a person is missing from. A firm caller's answer is
      // capped at ten server-side, so for them this is one page.
      final List<UserLookupResult> found = await fetchAllPages(
        (page) => widget.api.lookupUsers(term, page: page),
      );
      if (!mounted || seq != _searchSeq) return;
      setState(() {
        _results = found;
        _searching = false;
        _searched = true;
        // A result that scrolled away must not stay selected.
        if (!found.any((row) => row.id == _selectedId)) _selectedId = null;
      });
    } on ApiException catch (exception) {
      if (!mounted || seq != _searchSeq) return;
      setState(() {
        _searching = false;
        _searched = true;
        _results = const [];
        _error = exception.message;
      });
    }
  }

  UserLookupResult? get _selected =>
      _results.where((row) => row.id == _selectedId).firstOrNull;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: const Text('Add existing user'),
      // An AlertDialog gives its content unbounded height, so a stretched
      // Column with no width overflows by tens of thousands of pixels instead
      // of laying out. Both dimensions are bounded on purpose.
      content: SizedBox(
        width: 540,
        height: 420,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.listsEveryone
                  ? 'Everyone with an account who is not yet in this firm. '
                      'Type to filter by name or email. Adding them here does '
                      'not change anything in any other firm they work in.'
                  : 'Search by name or email for somebody who already has an '
                      'account. Adding them here does not change anything in '
                      'any other firm they work in.',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _term,
              autofocus: true,
              onChanged: _onTermChanged,
              decoration: InputDecoration(
                labelText: 'Name or email',
                helperText: widget.listsEveryone
                    ? 'Leave blank to list everyone not yet in this firm.'
                    : 'At least $_minimumTerm characters.',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _searching
                    ? const Padding(
                        padding: EdgeInsets.all(12),
                        child: SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      )
                    : null,
              ),
            ),
            const SizedBox(height: 8),
            Expanded(child: _results.isEmpty ? _emptyState(theme) : _resultList()),
            if (_selected != null && !_selected!.alreadyAMember) ...[
              const Divider(),
              DropdownButtonFormField<String>(
                isExpanded: true,
                initialValue: _templateId.isEmpty ? null : _templateId,
                decoration: const InputDecoration(
                  labelText: 'Job template',
                  helperText: 'Optional. You can set their roles afterwards.',
                ),
                items: [
                  const DropdownMenuItem<String>(
                    value: '',
                    child: Text('No job yet', overflow: TextOverflow.ellipsis),
                  ),
                  for (final UserTemplate template in _templates)
                    DropdownMenuItem<String>(
                      value: template.id,
                      child: Text(template.name, overflow: TextOverflow.ellipsis),
                    ),
                ],
                onChanged: (value) =>
                    setState(() => _templateId = value ?? ''),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          // Nothing to do for somebody already here, so the button says so by
          // being dead rather than by failing on the server.
          onPressed: _selected == null || _selected!.alreadyAMember
              ? null
              : () => Navigator.of(context).pop(
                    HireExistingPerson(
                      person: _selected!,
                      templateId: _templateId,
                    ),
                  ),
          child: const Text('Add to this firm'),
        ),
      ],
    );
  }

  Widget _emptyState(ThemeData theme) {
    final String message = _error ??
        (!_searched
            ? (widget.listsEveryone
                ? 'Loading everyone not yet in this firm…'
                : 'Type a name or email to search.')
            : (widget.listsEveryone && _term.text.trim().isEmpty
                // An empty list with nothing typed means the firm already
                // holds every account there is -- a different fact from a
                // filter that matched nobody, and a different next step.
                ? 'Everyone with an account is already in this firm. Use New '
                    'to create somebody.'
                : 'Nobody matches. They may not have an account yet — use New '
                    'to create one.'));
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Text(
          message,
          textAlign: TextAlign.center,
          style: theme.textTheme.bodySmall,
        ),
      ),
    );
  }

  Widget _resultList() => ListView.builder(
        itemCount: _results.length,
        itemBuilder: (context, index) {
          final UserLookupResult row = _results[index];
          final bool chosen = row.id == _selectedId;
          return ListTile(
            selected: chosen,
            // Somebody already here cannot be added again, and saying so is
            // better than omitting them and leaving the searcher to wonder
            // whether the person exists at all.
            enabled: !row.alreadyAMember,
            onTap: () => setState(() => _selectedId = row.id),
            leading: Icon(
              chosen
                  ? Icons.radio_button_checked
                  : Icons.radio_button_unchecked,
            ),
            title: Text(row.fullName.isEmpty ? row.email : row.fullName),
            subtitle: Text(row.email),
            trailing: row.alreadyAMember
                ? const Text('Already in this firm')
                : null,
          );
        },
      );
}
