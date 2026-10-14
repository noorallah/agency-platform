import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/firm_member.dart';
import '../../models/salesman.dart';
import '../resource_management_page.dart';
import '../workspace/desktop_framework.dart';
import 'firm_salesmen.dart';

/// The permission that changes the list. Reading it needs only membership.
const String salesmanManagePermission = 'SALESMAN_MANAGE';

/// The firm's own list of salesmen (P2): who takes orders, makes bills and
/// earns commission, whether or not they ever sign in.
///
/// An entry may be tied to a user account, so that person's new documents
/// start on their own name; one tied to nobody stands for a salesman who
/// never uses the program. Every Salesman box reads this list through
/// [FirmSalesmen], which this screen tells to read again after any change.
///
/// Deleting somebody a document names makes them inactive instead -- the
/// server decides, and the screen says which happened. A real delete can be
/// undone from **Restore deleted** for as long as the screen is open: the
/// list endpoint does not answer deleted rows, so nothing else could find
/// them.
class SalesmenPage extends StatefulWidget {
  const SalesmenPage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<SalesmenPage> createState() => _SalesmenPageState();
}

class _SalesmenPageState extends State<SalesmenPage> {
  /// The firm's people, for tying an entry to a user account.
  List<FirmMember> _members = const [];

  /// User ids named by a row on screen that are not among [_members] --
  /// somebody who has left the firm -- so the form can still show them.
  final Set<String> _strayUsers = {};

  /// Entries really deleted while the screen is open, for Restore deleted.
  final List<Salesman> _deleted = [];

  bool get _canManage =>
      widget.permissions.hasPermission(salesmanManagePermission);

  @override
  void initState() {
    super.initState();
    _readMembers();
  }

  Future<void> _readMembers() async {
    try {
      final List<FirmMember> people = await widget.api.firmMembers();
      if (!mounted) return;
      setState(() => _members = people);
    } on ApiException {
      // The tie stays offerable as "nobody"; the list itself still works.
    }
  }

  String _userLabel(String userId) {
    if (userId.isEmpty) return '';
    for (final FirmMember person in _members) {
      if (person.userId == userId) return person.label;
    }
    return 'A user no longer in this firm';
  }

  Future<PagedResult<Salesman>> _loadPage({
    int page = 1,
    int pageSize = 25,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> filters = const {},
  }) async {
    // Reading the grid is the moment this screen knows the list may have
    // changed -- after a save, a delete, a restore -- so the shared copy
    // every Salesman box reads is dropped here as well as at each call.
    FirmSalesmen.invalidate();
    final String status = filters['status'] ?? '';
    // By name unless a column was clicked: the grid's own default is the
    // newest first, which is no order for a list of people.
    final bool byDefault = sortBy == 'created_at';
    final PagedResult<Salesman> result = await widget.api.salesmenPage(
      page: page,
      pageSize: pageSize,
      search: search,
      sortBy: byDefault ? 'name' : sortBy,
      descending: byDefault ? false : descending,
      active: status.isEmpty ? null : status == 'active',
    );
    final Set<String> known = {for (final FirmMember m in _members) m.userId};
    final Iterable<String> stray = result.items
        .map((row) => row.userId)
        .where((id) => id.isNotEmpty && !known.contains(id))
        .where((id) => !_strayUsers.contains(id));
    if (stray.isNotEmpty && mounted) {
      setState(() => _strayUsers.addAll(stray));
    }
    return result;
  }

  Future<Json> _update(Salesman item, Json body) async {
    final Salesman saved = await widget.api.updateSalesman(
      item.id,
      body,
      expectedVersion: item.version,
    );
    FirmSalesmen.invalidate();
    return <String, dynamic>{
      'data': <String, dynamic>{'id': saved.id},
    };
  }

  Future<void> _delete(Salesman item) async {
    await widget.api.deleteSalesman(item.id);
    FirmSalesmen.invalidate();
    // The server deletes an entry nothing names and makes one in use
    // inactive instead; reading it back says which happened.
    bool stillThere = true;
    try {
      await widget.api.salesman(item.id);
    } on ApiException catch (error) {
      stillThere = error.statusCode != 404;
    }
    if (!mounted) return;
    if (stillThere) {
      NotificationService.show(
        context,
        '${item.label} is named on documents, so they were made inactive '
        'instead. They stay on those documents and are no longer offered.',
        kind: AppNotificationKind.information,
      );
    } else {
      setState(() => _deleted.add(item));
      NotificationService.show(
        context,
        '${item.label} was deleted. Restore deleted brings them back.',
        kind: AppNotificationKind.success,
      );
    }
  }

  Future<String> _restore(Salesman? _) async {
    final Salesman? chosen = _deleted.length == 1
        ? _deleted.single
        : await showDialog<Salesman>(
            context: context,
            builder: (context) => SimpleDialog(
              title: const Text('Restore which salesman?'),
              children: [
                for (final Salesman item in _deleted)
                  SimpleDialogOption(
                    onPressed: () => Navigator.of(context).pop(item),
                    child: Text(item.label),
                  ),
              ],
            ),
          );
    // Closing the question restores nobody and needs no message.
    if (chosen == null) return '';
    final Salesman restored = await widget.api.restoreSalesman(chosen.id);
    FirmSalesmen.invalidate();
    if (mounted) {
      setState(() => _deleted.removeWhere((item) => item.id == chosen.id));
    }
    return '${restored.label} is back on the list.';
  }

  ResourceDefinition<Salesman> _definition() {
    final List<String> userChoices = [
      '',
      for (final FirmMember person in _members) person.userId,
      for (final String id in _strayUsers) id,
    ];
    return ResourceDefinition<Salesman>(
      title: 'Salesmen',
      resource: 'salesmen',
      showFrame: false,
      recordNoun: 'salesman',
      description: 'Who takes orders, makes bills and earns commission.',
      searchHint: 'Search salesmen by name, code or phone',
      headers: const [
        'Code',
        'Name',
        'User account',
        'Phone',
        'Commission',
        'Status',
      ],
      sortFields: const ['code', 'name'],
      cells: (item) => [
        item.code,
        item.name,
        item.userId.isEmpty ? 'Not tied to a user' : _userLabel(item.userId),
        item.phone,
        item.earnsCommission ? 'Earns' : 'Does not earn',
        item.isActive ? 'Active' : 'Inactive',
      ],
      id: (item) => item.id,
      load: ({
        int page = 1,
        String search = '',
        String sortBy = 'created_at',
        bool descending = true,
      }) =>
          _loadPage(
        page: page,
        search: search,
        sortBy: sortBy,
        descending: descending,
      ),
      loadPage: _loadPage,
      filters: const [
        ResourceFilter(
          key: 'status',
          label: 'Status',
          options: [
            ResourceFilterOption(value: 'active', label: 'Active'),
            ResourceFilterOption(value: 'inactive', label: 'Inactive'),
          ],
        ),
      ],
      partialUpdate: true,
      updateRecord: _update,
      deleteRecord: _delete,
      canUseAction: (action, _) => switch (action) {
        ToolbarAction.newItem ||
        ToolbarAction.edit ||
        ToolbarAction.delete =>
          _canManage,
        _ => true,
      },
      customActions: [
        ResourceAction<Salesman>(
          label: 'Restore deleted',
          icon: Icons.restore_from_trash_outlined,
          needsSelection: false,
          isVisible: (_) => _canManage && _deleted.isNotEmpty,
          onInvoke: _restore,
        ),
      ],
      fields: [
        const FieldSpec(
          key: 'name',
          label: 'Name',
          requiredOnCreate: true,
          helperText: 'As it is printed on a bill. Up to 120 letters.',
        ),
        const FieldSpec(
          key: 'code',
          label: 'Code',
          helperText: 'Optional, up to 30 letters. Stored in capitals.',
        ),
        FieldSpec(
          key: 'user_id',
          label: 'User account',
          choices: userChoices,
          choiceLabels: {
            '': 'Not tied to a user',
            for (final String id in userChoices)
              if (id.isNotEmpty) id: _userLabel(id),
          },
          helperText: 'Tie the entry to the person who signs in as this '
              'salesman, so their new orders and bills start on their name. '
              'Leave untied for somebody who never signs in.',
        ),
        const FieldSpec(key: 'phone', label: 'Phone'),
        const FieldSpec(
          key: 'earns_commission',
          label: 'Earns commission',
          boolean: true,
        ),
        const FieldSpec(
          key: 'is_active',
          label: 'Active',
          boolean: true,
          helperText: 'An inactive salesman stays on the documents that name '
              'them and is no longer offered on new ones.',
        ),
        const FieldSpec(
          key: 'notes',
          label: 'Notes',
          multiline: true,
          fullWidth: true,
        ),
      ],
      initialValues: (item) => <String, dynamic>{
        'name': item?.name ?? '',
        'code': item?.code ?? '',
        'user_id': item?.userId ?? '',
        'phone': item?.phone ?? '',
        'earns_commission': item?.earnsCommission ?? true,
        'is_active': item?.isActive ?? true,
        'notes': item?.notes ?? '',
      },
      payload: (values, isCreating) {
        String? text(String key) {
          final String value = (values[key] as String? ?? '').trim();
          return value.isEmpty ? null : value;
        }

        return <String, dynamic>{
          'name': text('name') ?? '',
          'code': text('code'),
          'user_id': text('user_id'),
          'phone': text('phone'),
          'earns_commission': values['earns_commission'] == true,
          'is_active': values['is_active'] == true,
          'notes': text('notes'),
        };
      },
    );
  }

  @override
  Widget build(BuildContext context) => ResourceManagementPage<Salesman>(
        api: widget.api,
        definition: _definition(),
      );
}
