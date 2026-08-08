import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../models/entities.dart';

/// Editing state for one configurable attribute.
///
/// Attribute definitions are configured by an administrator at runtime, so the
/// form cannot know its fields ahead of time. This holds whatever the matching
/// input needs and produces the value the API expects, keeping the typing rules
/// in one place rather than in every module that gains custom fields.
class AttributeFieldController {
  AttributeFieldController(this.definition, {String? initialValue}) {
    text = TextEditingController(
      text: definition.isBoolean ? '' : (initialValue ?? ''),
    );
    if (definition.isBoolean) {
      boolean = switch ((initialValue ?? '').toLowerCase()) {
        'true' => true,
        'false' => false,
        _ => null,
      };
    }
  }

  final AttributeDefinitionRecord definition;
  late final TextEditingController text;

  /// Populated only for BOOLEAN attributes; null means "not answered".
  bool? boolean;

  bool get isEmpty =>
      definition.isBoolean ? boolean == null : text.text.trim().isEmpty;

  /// The value to send, typed so the backend stores it in the right column.
  Object? get payloadValue {
    if (isEmpty) return null;
    if (definition.isBoolean) return boolean;
    return text.text.trim();
  }

  /// Returns a message when the entered value cannot be stored, else null.
  ///
  /// The backend validates this too and remains authoritative; catching it here
  /// only spares the user a round trip.
  String? validate() {
    if (isEmpty) return null;
    final String raw = text.text.trim();
    if (definition.isNumber && num.tryParse(raw) == null) {
      return '${definition.name} must be a number.';
    }
    if (definition.isDate && DateTime.tryParse(raw) == null) {
      return '${definition.name} must be a date.';
    }
    return null;
  }

  /// Reset to unanswered, including the boolean the text field does not hold.
  void clear() {
    text.clear();
    boolean = null;
  }

  void dispose() => text.dispose();
}

/// Renders the input that matches an attribute's configured data type.
///
/// Stateful because it mutates its controller: a checkbox or date picker must
/// reflect the interaction itself rather than depending on a parent rebuild.
class AttributeFormField extends StatefulWidget {
  const AttributeFormField({
    super.key,
    required this.controller,
    required this.required,
    this.readOnly = false,
    this.onChanged,
    this.width = 280,
  });

  final AttributeFieldController controller;
  final bool required;
  final bool readOnly;
  final VoidCallback? onChanged;
  final double width;

  @override
  State<AttributeFormField> createState() => _AttributeFormFieldState();
}

class _AttributeFormFieldState extends State<AttributeFormField> {
  AttributeFieldController get controller => widget.controller;
  bool get required => widget.required;
  bool get readOnly => widget.readOnly;
  double get width => widget.width;

  String get _label =>
      required ? '${controller.definition.name} *' : controller.definition.name;

  /// Refresh this field and let the parent record that the form is dirty.
  void _changed() {
    if (mounted) setState(() {});
    widget.onChanged?.call();
  }

  @override
  Widget build(BuildContext context) {
    final AttributeDefinitionRecord definition = controller.definition;
    if (definition.isBoolean) return _boolean(context);
    if (definition.isDate) return _date(context);
    return _text(numeric: definition.isNumber);
  }

  Widget _text({required bool numeric}) => SizedBox(
        width: width,
        child: TextField(
          key: ValueKey('attribute-${controller.definition.id}'),
          controller: controller.text,
          readOnly: readOnly,
          keyboardType:
              numeric ? const TextInputType.numberWithOptions(decimal: true) : null,
          inputFormatters: numeric
              ? <TextInputFormatter>[
                  FilteringTextInputFormatter.allow(RegExp(r'[0-9.\-]')),
                ]
              : null,
          onChanged: (_) => _changed(),
          decoration: InputDecoration(
            labelText: _label,
            helperText: numeric ? 'Number' : null,
          ),
        ),
      );

  Widget _date(BuildContext context) => SizedBox(
        width: width,
        child: TextField(
          key: ValueKey('attribute-${controller.definition.id}'),
          controller: controller.text,
          readOnly: true,
          onTap: readOnly ? null : () => _pickDate(context),
          decoration: InputDecoration(
            labelText: _label,
            helperText: 'Date',
            suffixIcon: IconButton(
              tooltip: 'Pick a date',
              icon: const Icon(Icons.calendar_today_outlined),
              onPressed: readOnly ? null : () => _pickDate(context),
            ),
          ),
        ),
      );

  Widget _boolean(BuildContext context) => SizedBox(
        width: width,
        child: InputDecorator(
          decoration: InputDecoration(
            labelText: _label,
            border: InputBorder.none,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Checkbox(
                key: ValueKey('attribute-${controller.definition.id}'),
                // Always tristate, including when required. Defaulting a
                // required flag to "No" would let it be submitted without ever
                // being answered, which for something like PRESCRIPTION_REQUIRED
                // is a wrong answer rather than a missing one. Leaving it unset
                // lets the save-time required check refuse it instead.
                tristate: true,
                value: controller.boolean,
                // Flutter's own tristate order would make the first tap mean
                // "No". Ticking a box reads as yes, so cycle unset -> yes -> no.
                onChanged: readOnly
                    ? null
                    : (_) {
                        controller.boolean = switch (controller.boolean) {
                          null => true,
                          true => false,
                          false => null,
                        };
                        _changed();
                      },
              ),
              Text(switch (controller.boolean) {
                true => 'Yes',
                false => 'No',
                null => 'Not set',
              }),
            ],
          ),
        ),
      );

  Future<void> _pickDate(BuildContext context) async {
    final DateTime? current = DateTime.tryParse(controller.text.text.trim());
    final DateTime now = DateTime.now();
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: current ?? now,
      firstDate: DateTime(now.year - 20),
      lastDate: DateTime(now.year + 20),
    );
    if (picked == null) return;
    // ISO-8601 is what the API parses; never surface a locale-formatted string.
    controller.text.text = picked.toIso8601String().split('T').first;
    _changed();
  }
}
