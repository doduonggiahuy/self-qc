def ensure_annotation_roles():
    """Backward-compatible name for the former annotation-only role bootstrap."""
    from control_plane.projects.roles import ensure_platform_roles

    roles = ensure_platform_roles()
    return roles["DATA_ANNOTATOR"], roles["QA_QC_ENGINEER"]
