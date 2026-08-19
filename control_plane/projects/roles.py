from django.contrib.auth.models import Group, Permission


ROLE_GROUPS = {
    "DATA_ANNOTATOR": "Data Annotator",
    "AI_MODEL_ENGINEER": "AI Model Engineer",
    "AI_RULE_ENGINEER": "AI Rule Engineer",
    "AI_OPS_ENGINEER": "AI Ops Engineer",
    "QA_QC_ENGINEER": "QA/QC Engineer",
}


def _permissions(*app_labels):
    return Permission.objects.filter(content_type__app_label__in=app_labels)


def ensure_platform_roles():
    """Create the platform role catalog and assign its current MVP permissions."""
    legacy_names = {"Data Annotator": "QC Annotator", "QA/QC Engineer": "QC Reviewer"}
    groups = {}
    for code, name in ROLE_GROUPS.items():
        group, _ = Group.objects.get_or_create(name=name)
        legacy = Group.objects.filter(name=legacy_names.get(name, "")).first()
        if legacy:
            group.user_set.add(*legacy.user_set.all())
        groups[code] = group

    annotation_base = Permission.objects.filter(content_type__app_label="annotations", codename__in=[
        "add_project", "view_project", "change_project", "view_labelclass", "add_labelclass",
        "change_labelclass", "view_boxannotation", "add_boxannotation", "change_boxannotation", "delete_boxannotation",
        "add_annotationtask", "change_annotationtask", "view_annotationtask",
    ])
    groups["DATA_ANNOTATOR"].permissions.set(annotation_base)
    groups["AI_MODEL_ENGINEER"].permissions.set(_permissions("training"))
    groups["AI_RULE_ENGINEER"].permissions.set(_permissions("ai_rules"))
    groups["AI_OPS_ENGINEER"].permissions.set(_permissions("platform_control"))
    groups["QA_QC_ENGINEER"].permissions.set(
        _permissions("quality") | annotation_base | Permission.objects.filter(
            content_type__app_label="annotations", codename__in=["edit_all_projects", "review_annotations"],
        )
    )
    return groups


def set_platform_role(user, role_code):
    groups = ensure_platform_roles()
    user.groups.remove(*groups.values())
    user.groups.add(groups[role_code])


def platform_roles_for(user):
    names = set(user.groups.values_list("name", flat=True))
    return [name for name in ROLE_GROUPS.values() if name in names]
