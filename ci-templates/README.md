# CI Templates

These GitHub Actions workflow definitions live here (instead of `.github/workflows/`)
because the automated push uses a GitHub OAuth App token **without the `workflow`
scope**, which GitHub forbids from creating or updating files under
`.github/workflows/`.

They are ready to use — they just need to be placed in the active workflows
directory. Pick whichever is easier:

## Option A — activate via the GitHub web UI (no extra scopes)
1. In the repo on github.com, click **Add file → Create new file**.
2. Name it `.github/workflows/backend-tests.yml` and paste the contents of
   [`backend-tests.yml`](./backend-tests.yml). Commit.
3. Repeat for `.github/workflows/frontend-tests.yml`.

## Option B — activate via git (needs the `workflow` scope)
Grant the `workflow` scope to the OAuth App / use a PAT that has it, then:

```bash
git mv ci-templates/backend-tests.yml  .github/workflows/backend-tests.yml
git mv ci-templates/frontend-tests.yml .github/workflows/frontend-tests.yml
git commit -m "ci: activate GitHub Actions workflows"
git push
```

## What they do
- **backend-tests.yml** — Python 3.11 + ffmpeg, installs `requirements-dev.txt`,
  runs `pytest --cov`.
- **frontend-tests.yml** — Node 20, `npm ci`, `next lint`, `next build`.

Both trigger on pushes to `main` and on pull requests that touch the relevant
`backend/**` or `frontend/**` paths.
