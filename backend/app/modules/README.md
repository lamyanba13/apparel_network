# Backend feature modules

This directory reserves the bounded feature modules defined by the approved architecture.

When a feature is implemented, it adds only the layers it needs:

- `domain/`
- `application/`
- `infrastructure/`
- `presentation/`

Empty layer trees are intentionally not pre-created. Modules communicate through explicit application facades or post-commit events and never import another module's persistence models.

