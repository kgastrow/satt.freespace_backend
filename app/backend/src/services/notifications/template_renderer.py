"""
Template rendering service for notifications.

Provides variable substitution for notification templates using a simple
{variable} placeholder syntax.
"""

import re
from string import Template
from typing import TYPE_CHECKING, Any, Optional

from src.logger.logger import Logger as logger


if TYPE_CHECKING:
    from src.models.organization import Organization


class TemplateRenderer:
    """
    Render notification templates with variable substitution.

    Supports two template syntaxes:
    1. Simple braces: {variable_name}
    2. Python Template style: $variable_name or ${variable_name}

    The simple braces syntax is preferred for user-facing templates
    as it's more intuitive.

    Note: double braces ({{variable_name}}) are NOT supported. The pattern
    matches the inner {variable_name} and the outer braces survive into the
    rendered output. render() logs a warning whenever a placeholder is left
    unresolved, which is the usual symptom of double-brace templates.
    """

    # Regex pattern to find {variable} placeholders
    _VARIABLE_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

    def render(
        self,
        template_body: str,
        variables: dict[str, Any],
        strict: bool = False,
    ) -> str:
        """
        Render a plain text template with variable substitution.

        Args:
            template_body: Template string with {variable} placeholders
            variables: Dictionary of variable names to values
            strict: If True, raises KeyError for missing variables.
                   If False (default), leaves missing variables as-is.

        Returns:
            Rendered template string with variables substituted.

        Example:
            >>> renderer.render("Hello {name}!", {"name": "World"})
            "Hello World!"
        """
        if not template_body:
            return ""

        unresolved: list[str] = []

        def replace_variable(match):
            var_name = match.group(1)
            if var_name in variables:
                return str(variables[var_name])
            elif strict:
                raise KeyError(f"Missing template variable: {var_name}")
            else:
                # Leave the placeholder as-is if variable not provided
                unresolved.append(var_name)
                return match.group(0)

        try:
            rendered = self._VARIABLE_PATTERN.sub(replace_variable, template_body)
        except Exception as e:
            logger.error(f"Template rendering error: {e}")
            if strict:
                raise
            return template_body

        self._warn_unresolved(unresolved, rendered)
        return rendered

    def render_html(
        self,
        template_html: Optional[str],
        variables: dict[str, Any],
        strict: bool = False,
        escape_html: bool = True,
    ) -> Optional[str]:
        """
        Render an HTML template with variable substitution.

        Args:
            template_html: HTML template string with {variable} placeholders
            variables: Dictionary of variable names to values
            strict: If True, raises KeyError for missing variables.
            escape_html: If True (default), escapes HTML special characters
                        in variable values to prevent XSS.

        Returns:
            Rendered HTML string with variables substituted, or None if
            template_html is None.

        Example:
            >>> renderer.render_html("<p>Hello {name}!</p>", {"name": "World"})
            "<p>Hello World!</p>"
        """
        if template_html is None:
            return None

        if not template_html:
            return ""

        # Escape HTML in variable values if requested
        if escape_html:
            safe_variables = {
                key: self._escape_html(str(value)) for key, value in variables.items()
            }
        else:
            safe_variables = variables

        unresolved: list[str] = []

        def replace_variable(match):
            var_name = match.group(1)
            if var_name in safe_variables:
                return str(safe_variables[var_name])
            elif strict:
                raise KeyError(f"Missing template variable: {var_name}")
            else:
                unresolved.append(var_name)
                return match.group(0)

        try:
            rendered = self._VARIABLE_PATTERN.sub(replace_variable, template_html)
        except Exception as e:
            logger.error(f"HTML template rendering error: {e}")
            if strict:
                raise
            return template_html

        self._warn_unresolved(unresolved, rendered, is_html=True)
        return rendered

    def _warn_unresolved(
        self,
        unresolved: list[str],
        rendered: str,
        is_html: bool = False,
    ) -> None:
        """
        Log a warning for placeholders that survived rendering.

        An unresolved placeholder means the recipient sees a literal
        "{variable_name}" in their notification. The most common cause is an
        author following double-brace ({{name}}) documentation: the renderer
        substitutes the inner {name} and leaves the outer braces behind, so
        the rendered body still contains a brace pair.

        This is intentionally a warning and not an error - rendering stays
        non-strict so a missing variable degrades a notification's wording
        rather than dropping the notification entirely.
        """
        if not unresolved:
            return

        kind = "HTML template" if is_html else "Template"
        names = ", ".join(sorted(set(unresolved)))
        hint = ""
        if "{{" in rendered or "}}" in rendered:
            hint = (
                " The rendered output still contains double braces - templates use "
                "single-brace {variable_name} syntax, not {{variable_name}}."
            )
        logger.warning(
            f"{kind} rendered with unresolved placeholder(s): {names}."
            f" The recipient will see the literal placeholder text.{hint}"
        )

    def validate_variables(
        self,
        template: str,
        variables: dict[str, Any],
    ) -> bool:
        """
        Validate that all required template variables are provided.

        Args:
            template: Template string with {variable} placeholders
            variables: Dictionary of variable names to values

        Returns:
            True if all template variables have corresponding values in
            the variables dict, False otherwise.

        Example:
            >>> renderer.validate_variables("Hello {name}!", {"name": "World"})
            True
            >>> renderer.validate_variables("Hello {name}!", {})
            False
        """
        if not template:
            return True

        required_vars = self.extract_variables(template)
        provided_vars = set(variables.keys())

        missing = required_vars - provided_vars
        if missing:
            logger.warning(f"Missing template variables: {missing}")
            return False

        return True

    def extract_variables(self, template: str) -> set[str]:
        """
        Extract all variable names from a template.

        Args:
            template: Template string with {variable} placeholders

        Returns:
            Set of variable names found in the template.

        Example:
            >>> renderer.extract_variables("Hello {first_name} {last_name}!")
            {"first_name", "last_name"}
        """
        if not template:
            return set()

        matches = self._VARIABLE_PATTERN.findall(template)
        return set(matches)

    def get_missing_variables(
        self,
        template: str,
        variables: dict[str, Any],
    ) -> list[str]:
        """
        Get a list of missing variables that are required by the template.

        Args:
            template: Template string with {variable} placeholders
            variables: Dictionary of variable names to values

        Returns:
            List of variable names that are in the template but not in variables.

        Example:
            >>> renderer.get_missing_variables("Hello {name} from {city}!", {"name": "Alice"})
            ["city"]
        """
        required_vars = self.extract_variables(template)
        provided_vars = set(variables.keys())
        return list(required_vars - provided_vars)

    def _escape_html(self, text: str) -> str:
        """
        Escape HTML special characters to prevent XSS.

        Escapes: & < > " '
        """
        if not isinstance(text, str):
            text = str(text)

        # Order matters - escape & first
        replacements = [
            ("&", "&amp;"),
            ("<", "&lt;"),
            (">", "&gt;"),
            ('"', "&quot;"),
            ("'", "&#x27;"),
        ]

        for old, new in replacements:
            text = text.replace(old, new)

        return text

    def render_with_python_template(
        self,
        template_body: str,
        variables: dict[str, Any],
        safe: bool = True,
    ) -> str:
        """
        Render a template using Python's string.Template syntax.

        This is an alternative to the {variable} syntax, using $variable
        or ${variable} placeholders.

        Args:
            template_body: Template string with $variable placeholders
            variables: Dictionary of variable names to values
            safe: If True (default), uses safe_substitute which leaves
                 missing variables as-is. If False, uses substitute which
                 raises KeyError for missing variables.

        Returns:
            Rendered template string.

        Example:
            >>> renderer.render_with_python_template("Hello $name!", {"name": "World"})
            "Hello World!"
        """
        if not template_body:
            return ""

        try:
            template = Template(template_body)
            if safe:
                return template.safe_substitute(variables)
            else:
                return template.substitute(variables)
        except Exception as e:
            logger.error(f"Python template rendering error: {e}")
            if not safe:
                raise
            return template_body


def get_organization_template_variables(organization: "Organization") -> dict[str, Any]:
    """
    Generate template variables for an organization.

    Provides organization details as template variables for use in notification
    templates. All variables use the 'org_' prefix.

    Args:
        organization: Organization model instance

    Returns:
        Dictionary of template variables with keys:
        - org_name: Organization name (always present)
        - org_display_name: Display name with fallback to name
        - org_address: Formatted full address string
        - org_address_line1: First line of address
        - org_address_line2: Second line of address
        - org_city: City
        - org_state_province: State or province
        - org_postal_code: Postal/ZIP code
        - org_country: Country
        - org_contact_email: Contact email
        - org_contact_phone: Contact phone

    Example:
        >>> vars = get_organization_template_variables(org)
        >>> template_renderer.render("Hello from {org_display_name}!", vars)
        "Hello from Acme Corp!"
    """
    # Build formatted address string
    address_parts = []
    if organization.physical_address_line1:
        address_parts.append(organization.physical_address_line1)
    if organization.physical_address_line2:
        address_parts.append(organization.physical_address_line2)

    city_state_parts = []
    if organization.city:
        city_state_parts.append(organization.city)
    if organization.state_province:
        city_state_parts.append(organization.state_province)
    if city_state_parts:
        address_parts.append(", ".join(city_state_parts))

    if organization.postal_code:
        address_parts.append(organization.postal_code)
    if organization.country:
        address_parts.append(organization.country)

    formatted_address = ", ".join(address_parts) if address_parts else ""

    return {
        "org_name": organization.name or "",
        "org_display_name": organization.display_name or organization.name or "",
        "org_address": formatted_address,
        "org_address_line1": organization.physical_address_line1 or "",
        "org_address_line2": organization.physical_address_line2 or "",
        "org_city": organization.city or "",
        "org_state_province": organization.state_province or "",
        "org_postal_code": organization.postal_code or "",
        "org_country": organization.country or "",
        "org_contact_email": organization.contact_email or "",
        "org_contact_phone": organization.contact_phone or "",
    }


# Singleton instance
template_renderer = TemplateRenderer()
