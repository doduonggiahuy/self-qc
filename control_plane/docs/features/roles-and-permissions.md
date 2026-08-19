# Roles and permissions

**Status:** Implemented baseline for Annotation workflow.

| Capability | AI Admin (Root) | Data Annotator | QA/QC Engineer |
| --- | --- | --- | --- |
| Create/delete Project | Yes | No | No |
| Create/manage Project labels, attributes, skeleton | Yes | No | No |
| Create/manage Project rules | Yes | No | No |
| Create Task inside an existing Project | Yes | Yes | No |
| Assign annotators/reviewer on Task | Yes | Yes | No |
| Upload/delete Task data | Yes | Task member/creator | No |
| Open/save assigned Job Canvas | Yes | Assigned/creator | Reviewer |

Backend authorization is authoritative; hiding UI controls is not treated as a
security boundary. Root is Django `is_superuser`. Data Annotator starts at Task
and cannot POST Project/Label/Rule endpoints.
