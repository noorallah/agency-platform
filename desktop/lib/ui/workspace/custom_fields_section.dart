import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/entities.dart';
import '../../models/product.dart';
import 'attribute_form_fields.dart';

/// The custom fields one record carries, loaded for its entity type.
///
/// The product form resolved its fields through `/products/metadata`; the
/// customer and vendor forms ask `/attribute-definitions/applicable` for the
/// same answer without a product in it. One controller for every form: it
/// loads the applicable definitions, holds one `AttributeFieldController` per
/// definition seeded from the stored values, and answers the payload. A form
/// sends `attributes` **only when the load succeeded** -- the server treats an
/// absent list as "leave them alone" and an empty one as "clear them", so a
/// form that could not read the definitions must not send the empty one.
class CustomFieldsController extends ChangeNotifier {
  CustomFieldsController({
    required this.load,
    List<AttributeValueRecord> stored = const [],
  }) : _stored = {for (final AttributeValueRecord v in stored) v.attributeDefinitionId: _storedValue(v)};

  /// Reads the applicable definitions for the entity type.
  final Future<ApplicableAttributesRecord> Function() load;
  Map<String, String> _stored;

  /// Hands the controller the values a document already carries, for a form
  /// that learns them after it was built (the document is read over the wire
  /// once the editor is open). Fields already built are re-seeded.
  void seed(List<AttributeValueRecord> stored) {
    _stored = {
      for (final AttributeValueRecord v in stored)
        v.attributeDefinitionId: _storedValue(v),
    };
    for (final MapEntry<String, AttributeFieldController> entry
        in controllers.entries) {
      entry.value.clear();
      final String? value = _stored[entry.key];
      if (value == null) continue;
      if (entry.value.definition.isBoolean) {
        entry.value.boolean = value == 'true' ? true : (value == 'false' ? false : null);
      } else {
        entry.value.text.text = value;
      }
    }
    notifyListeners();
  }

  /// Every definition the server returned, shown or not.
  List<AttributeDefinitionRecord> definitions = const [];
  Set<String> mandatoryIds = const {};
  List<KindRuleRecord> kindRules = const [];

  String? _customerGroupId;
  String? _vendorTypeId;

  /// Tells the controller which kind the record is now: the form passes the
  /// selected customer group or supplier type on load and on every change, and
  /// the fields are re-evaluated here without another server call. A form with
  /// no kind (any document) never calls it, so fields tied to a kind stay hidden.
  void setKind({String? customerGroupId, String? vendorTypeId}) {
    final String? group =
        customerGroupId == null || customerGroupId.isEmpty ? null : customerGroupId;
    final String? type =
        vendorTypeId == null || vendorTypeId.isEmpty ? null : vendorTypeId;
    if (group == _customerGroupId && type == _vendorTypeId) return;
    _customerGroupId = group;
    _vendorTypeId = type;
    if (!_disposed) notifyListeners();
  }

  Iterable<KindRuleRecord> _rulesFor(String definitionId) =>
      kindRules.where((rule) => rule.attributeDefinitionId == definitionId);

  bool _matches(KindRuleRecord rule) =>
      (_customerGroupId != null && rule.customerGroupId == _customerGroupId) ||
      (_vendorTypeId != null && rule.vendorTypeId == _vendorTypeId);

  /// Whether the field is tied to a kind of record by any rule.
  bool isTied(String definitionId) => _rulesFor(definitionId).isNotEmpty;

  /// A field in no kind rule is always shown; a tied one is shown when a rule
  /// matches the record's kind, or when the record already holds a value for it
  /// (the server keeps accepting a value the record carries).
  bool isVisible(AttributeDefinitionRecord definition) {
    if (!isTied(definition.id)) return true;
    if (_rulesFor(definition.id).any(_matches)) return true;
    return (_stored[definition.id] ?? '').isNotEmpty;
  }

  /// Required whatever the kind, or by the rule matching the record's kind.
  bool isRequired(String definitionId) =>
      mandatoryIds.contains(definitionId) ||
      _rulesFor(definitionId).any((rule) => rule.isMandatory && _matches(rule));

  List<AttributeDefinitionRecord> get visibleDefinitions =>
      [for (final AttributeDefinitionRecord d in definitions) if (isVisible(d)) d];
  final Map<String, AttributeFieldController> controllers = {};
  bool loaded = false;
  bool loading = false;
  String? error;

  static String _storedValue(AttributeValueRecord value) {
    if (value.valueBoolean != null) return value.valueBoolean! ? 'true' : 'false';
    if (value.valueDate.isNotEmpty) return value.valueDate;
    if (value.valueNumber.isNotEmpty) return value.valueNumber;
    return value.valueText;
  }

  Future<void> start() async {
    if (loading || loaded) return;
    loading = true;
    error = null;
    notifyListeners();
    try {
      final ApplicableAttributesRecord answer = await load();
      // The form may have closed while the answer was on its way.
      if (_disposed) return;
      definitions = answer.definitions;
      mandatoryIds = answer.mandatoryIds.toSet();
      kindRules = answer.kindRules;
      for (final AttributeDefinitionRecord definition in definitions) {
        controllers.putIfAbsent(
          definition.id,
          () => AttributeFieldController(
            definition,
            initialValue: _stored[definition.id],
          ),
        );
      }
      loaded = true;
    } on ApiException catch (exception) {
      error = exception.message;
      loaded = false;
    } on Object {
      // An answer that could not be read is the same as no answer: the form
      // says so and sends nothing, rather than failing in the background.
      error = 'the answer could not be read';
      loaded = false;
    } finally {
      loading = false;
      if (!_disposed) notifyListeners();
    }
  }

  bool _disposed = false;

  /// Whether the form has something to send. False until the definitions
  /// arrived, so a save cannot clear values it never saw.
  bool get canSend => loaded;

  /// Whether a document has anything to send: the definitions arrived and
  /// the firm defined at least one. A document sends no `attributes` at all
  /// otherwise, so a firm that never used the feature sees no change on the
  /// wire.
  bool get hasFields => loaded && visibleDefinitions.isNotEmpty;

  /// The `attributes` list for the payload: every filled field that is shown.
  /// A hidden field with no stored value is never sent.
  List<Json> payload() => [
        for (final AttributeDefinitionRecord definition in visibleDefinitions)
          if (!(controllers[definition.id]?.isEmpty ?? true))
            {
              'attribute_definition_id': definition.id,
              'value': controllers[definition.id]!.payloadValue,
            },
      ];

  /// The first validation message across the fields, or null.
  String? validate() {
    for (final AttributeDefinitionRecord definition in visibleDefinitions) {
      final AttributeFieldController? controller = controllers[definition.id];
      if (controller == null) continue;
      if (isRequired(definition.id) && controller.isEmpty) {
        return '${definition.name} is required.';
      }
      final String? message = controller.validate();
      if (message != null) return '${definition.name}: $message';
    }
    return null;
  }

  @override
  void dispose() {
    _disposed = true;
    for (final AttributeFieldController controller in controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }
}

/// The stored values out of a document's `attributes`, read defensively: a
/// response from before MST-6 has none, and an odd entry is skipped.
List<AttributeValueRecord> attributeValuesFrom(Object? raw) => raw is List
    ? [
        for (final Object? item in raw)
          if (item is Map)
            ProductAttributeValueRecord.fromJson(
              Map<String, dynamic>.from(item),
            ),
      ]
    : const [];

/// The "Additional details" block a document editor shows (MST-6): nothing at
/// all while the definitions load or when the firm defined none for this kind
/// of document, so a firm that never used custom fields sees no change.
class AdditionalDetailsSection extends StatelessWidget {
  const AdditionalDetailsSection({
    super.key,
    required this.controller,
    required this.noun,
    this.readOnly = false,
    this.onChanged,
    this.maxHeight,
    this.padding = const EdgeInsets.only(top: 16),
  });

  final CustomFieldsController controller;

  /// What the document is called, plural: "sales orders".
  final String noun;
  final bool readOnly;
  final VoidCallback? onChanged;

  /// A one-screen document page has no spare height, so its block scrolls
  /// inside this limit rather than pushing the lines table off the screen.
  final double? maxHeight;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: controller,
        builder: (context, _) {
          if (controller.loading) return const SizedBox.shrink();
          if (controller.error == null &&
              (!controller.loaded || controller.visibleDefinitions.isEmpty)) {
            return const SizedBox.shrink();
          }
          Widget block = Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Additional details',
                style: Theme.of(context).textTheme.titleSmall,
              ),
              const SizedBox(height: 8),
              CustomFieldsSection(
                controller: controller,
                noun: noun,
                readOnly: readOnly,
                onChanged: onChanged,
              ),
            ],
          );
          final double? limit = maxHeight;
          if (limit != null) {
            block = ConstrainedBox(
              constraints: BoxConstraints(maxHeight: limit),
              child: SingleChildScrollView(child: block),
            );
          }
          return Padding(
            key: const ValueKey('additional-details'),
            padding: padding,
            child: block,
          );
        },
      );
}

/// The section a form places on its Custom fields tab.
class CustomFieldsSection extends StatelessWidget {
  const CustomFieldsSection({
    super.key,
    required this.controller,
    required this.noun,
    this.readOnly = false,
    this.onChanged,
  });

  final CustomFieldsController controller;

  /// What the record is called in the empty message: "customers".
  final String noun;
  final bool readOnly;
  final VoidCallback? onChanged;

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: controller,
        builder: (context, _) {
          final ThemeData theme = Theme.of(context);
          if (controller.loading) {
            return const Padding(
              padding: EdgeInsets.all(24),
              child: Center(child: CircularProgressIndicator()),
            );
          }
          if (controller.error != null) {
            return Padding(
              padding: const EdgeInsets.all(8),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      'Could not read the custom fields: ${controller.error}. '
                      'Saving will leave the stored values as they are.',
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.error),
                    ),
                  ),
                  TextButton(
                    onPressed: controller.start,
                    child: const Text('Retry'),
                  ),
                ],
              ),
            );
          }
          if (controller.visibleDefinitions.isEmpty) {
            return Padding(
              padding: const EdgeInsets.all(8),
              child: Text(
                'No custom fields are defined for $noun in this firm. An '
                'administrator adds them under Configuration → Business '
                'Profiles → Dynamic Attributes.',
                style: theme.textTheme.bodySmall,
              ),
            );
          }
          return Wrap(
            spacing: 16,
            runSpacing: 12,
            children: [
              for (final AttributeDefinitionRecord definition
                  in controller.visibleDefinitions)
                AttributeFormField(
                  controller: controller.controllers[definition.id]!,
                  required: controller.isRequired(definition.id),
                  readOnly: readOnly,
                  onChanged: onChanged,
                ),
            ],
          );
        },
      );
}
