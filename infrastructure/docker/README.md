# Docker

Development Dockerfiles live with each deployable application:

- `backend/Dockerfile`
- `frontend/Dockerfile`
- `dashboard/Dockerfile`
- `infrastructure/nginx/Dockerfile`

The root `.dockerignore` keeps local dependencies, build output, secrets, and repository metadata out of build contexts.
