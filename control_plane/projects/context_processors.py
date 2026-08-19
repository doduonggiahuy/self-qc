from .roles import ROLE_GROUPS


def platform_access(request):
    user = request.user
    if not getattr(user, "is_authenticated", False):
        return {"access": {}}
    roles = set(user.groups.values_list("name", flat=True))
    root = user.is_superuser
    return {"access": {
        "root": root,
        "annotation": root or ROLE_GROUPS["DATA_ANNOTATOR"] in roles or ROLE_GROUPS["QA_QC_ENGINEER"] in roles,
        "quality": root or ROLE_GROUPS["QA_QC_ENGINEER"] in roles,
        "rules": root or ROLE_GROUPS["AI_RULE_ENGINEER"] in roles,
        "training": root or ROLE_GROUPS["AI_MODEL_ENGINEER"] in roles,
        "platform": root or ROLE_GROUPS["AI_OPS_ENGINEER"] in roles,
    }}
