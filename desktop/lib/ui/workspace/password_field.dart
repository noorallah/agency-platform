// A password box with a show/hide eye.
//
// Written once because the sign-in box had one and the other password boxes
// (change, reset, clone-user, first-sign-in change) did not: typing a
// 12-character password with upper, lower, digit and symbol blind is how a
// confirmation box gets a typo the person cannot see (D-DLG-9).

import 'package:flutter/material.dart';

/// A [TextFormField] that hides its text until the eye is pressed.
class PasswordField extends StatefulWidget {
  const PasswordField({
    required this.controller,
    this.decoration = const InputDecoration(),
    this.validator,
    this.autofocus = false,
    this.onFieldSubmitted,
    super.key,
  });

  final TextEditingController controller;
  final InputDecoration decoration;
  final FormFieldValidator<String>? validator;
  final bool autofocus;
  final ValueChanged<String>? onFieldSubmitted;

  @override
  State<PasswordField> createState() => _PasswordFieldState();
}

class _PasswordFieldState extends State<PasswordField> {
  bool _obscure = true;

  @override
  Widget build(BuildContext context) => TextFormField(
        controller: widget.controller,
        obscureText: _obscure,
        autofocus: widget.autofocus,
        validator: widget.validator,
        onFieldSubmitted: widget.onFieldSubmitted,
        decoration: widget.decoration.copyWith(
          suffixIcon: IconButton(
            tooltip: _obscure ? 'Show password' : 'Hide password',
            onPressed: () => setState(() => _obscure = !_obscure),
            icon: Icon(
              _obscure
                  ? Icons.visibility_outlined
                  : Icons.visibility_off_outlined,
            ),
          ),
        ),
      );
}
