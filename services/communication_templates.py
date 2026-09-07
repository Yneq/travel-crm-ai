import re


class TemplateRenderError(ValueError):
    pass


ALLOWED_TEMPLATE_FIELDS = {
    "member_name",
    "reminder_title",
    "recommended_action",
}
PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-z_]+)\s*}}")


def render_template(value: str, context: dict[str, str]) -> str:
    placeholders = set(PLACEHOLDER_PATTERN.findall(value))
    unknown = placeholders - ALLOWED_TEMPLATE_FIELDS
    if unknown:
        raise TemplateRenderError(
            f"Unsupported template fields: {', '.join(sorted(unknown))}"
        )

    missing = placeholders - context.keys()
    if missing:
        raise TemplateRenderError(
            f"Missing template values: {', '.join(sorted(missing))}"
        )

    return PLACEHOLDER_PATTERN.sub(lambda match: str(context[match.group(1)]), value)
