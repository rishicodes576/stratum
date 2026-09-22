# Publish Stratum to your GitHub

Publish the **extracted source folder**, not the ZIP file. The repository root must contain `README.md`, `compose.yaml`, `backend/`, `frontend/`, and `.github/`.

## 1. Extract and open the project

Extract `stratum-v1.0.0.zip`, then open a terminal in the extracted `stratum` directory. In PowerShell:

```powershell
cd "C:\path\to\extracted\stratum"
```

Install Git if it is not available. Configure the identity you want on your commits; your GitHub-provided no-reply email is suitable if you prefer not to publish your personal email:

```bash
git config --global user.name "YOUR NAME"
git config --global user.email "YOUR GITHUB EMAIL OR NO-REPLY ADDRESS"
```

Skip these commands if Git is already configured correctly. They change your global Git identity, not your GitHub login.

## 2. Create your first commit

```bash
git init -b main
git add .
git status --short
git commit -m "Build Stratum reliability command center"
```

The package excludes databases, dependency folders, test sessions, caches, and runtime secrets. `.gitignore` protects those files on future runs. Review the staged file list before committing if you have added your own files or configuration.

Do not commit `.env` or `.env.local`. The committed `.env.example` files and explicitly labeled demo credentials are intentional; real deployment secrets are not.

## 3. Publish using GitHub CLI

Install [GitHub CLI](https://cli.github.com/), then run:

```bash
gh auth login
gh repo create stratum --public --source=. --remote=origin --push
```

Follow the browser sign-in instructions from `gh auth login`. Use `--private` instead of `--public` if you want to inspect the repository before making it public. If a repository named `stratum` already exists on your account, choose a different name or use the existing-repository steps below.

These commands follow the [official GitHub instructions for an existing local project](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github) and [the `gh repo create` reference](https://cli.github.com/manual/gh_repo_create).

## Alternative: use the GitHub website

1. Open [Create a new repository](https://github.com/new).
2. Name it `stratum` and choose Public for a visible portfolio.
3. **Leave the repository empty:** do not add another README, license, or `.gitignore`; this project includes them.
4. Create the repository, then run these commands in your committed local project, replacing `YOUR_USERNAME`:

   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/stratum.git
   git push -u origin main
   ```

Use Git Credential Manager/browser sign-in or a suitable token if your Git client requests authentication. GitHub account passwords do not authenticate HTTPS Git operations. Do not paste a token into your repository files.

## 4. Check the first pipeline run

Open the repository's **Actions** tab and select **Verify Stratum**. There are three jobs:

- **backend:** real PostgreSQL and Redis tests, migration drift, API contract drift, Python formatting, and dependency auditing.
- **frontend:** generated type drift, formatting, TypeScript, dependency auditing, and the production build.
- **end-to-end:** Docker builds and startup, seeded data, actual browser workflows, and accessibility checks.

No paid API key or deployment secret is needed for this pipeline. CI generates temporary local secrets and uses an isolated demo database. This delivery includes the workflow definition; your first push is the first remote execution, so wait for its results before claiming GitHub CI is green. Failing jobs retain test reports or container logs in their artifacts.

After the first successful run, create a repository ruleset protecting `main`, requiring pull requests and those successful checks. Enable private vulnerability reporting and dependency security alerts in repository settings.

## 5. Make the repository useful to a reviewer

- **Description:** `Evidence-driven incident response with async FastAPI, Next.js, PostgreSQL, Redis, durable triage, and tested concurrency guarantees.`
- **Topics:** `fastapi`, `nextjs`, `typescript`, `postgresql`, `redis`, `incident-management`, `sre`, `docker`, `github-actions`.
- Pin the repository to your profile.
- Keep the README screenshot, quickstart, demo walkthrough, architecture, and verification report visible.
- Record a short demo showing a signal progressing through triage and resolution, then one failure-mode test.
- Create a `v1.0.0` release after CI passes. Optionally attach the source ZIP and checksum.
- Add a live deployment URL only after you have deployed and verified the app. GitHub Pages alone cannot run the FastAPI/Postgres/Redis backend.

An active portfolio means subsequent real work: identify a limitation, create an issue, implement a focused change, show the tests, and merge it. Do not backdate commits or claim synthetic demo metrics as production impact.

## Future updates

```bash
git switch -c improve-incident-workflow
# Make and test a focused change.
git add .
git commit -m "Describe the actual improvement"
git push -u origin improve-incident-workflow
gh pr create
```

Describe the concrete problem, behavior change, and verification in the PR. The repository includes a review template.
