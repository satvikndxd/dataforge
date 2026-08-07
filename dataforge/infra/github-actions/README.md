# GitHub Actions CI

`ci.yml` runs the backend test suite (unit + integration) and the web
lint/build on every change under `dataforge/**`.

It lives here instead of `.github/workflows/` because pushing workflow files
requires a git credential with the `workflow` OAuth scope. To enable CI,
copy it into place from a client that has that scope (or via the GitHub UI):

```bash
cp dataforge/infra/github-actions/ci.yml .github/workflows/dataforge-v2.yml
git add .github/workflows/dataforge-v2.yml && git commit -m "Enable DataForge V2 CI"
```
