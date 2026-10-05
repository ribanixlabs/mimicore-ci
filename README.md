# mimicore-ci

Workflow-only repository: it runs the automated bug-fixing job for a private project. It is public only because GitHub Actions
minutes are unlimited for public repositories. It contains no application code, and the job never prints ticket or code content in its logs.

## Early builds (`beta.yml`): how the signing key stays safe
Hourly (and on demand) this builds the fixer's merged fixes, signs them and publishes them on the pinned prerelease `beta` of the public
releases repo. Four jobs with separate powers:

| job | sees | does |
|---|---|---|
| `source` | the read/write deploy key (removed from the runner right after checkout) | fetches `develop`, bumps the early-build version, uploads a tarball; runs nothing from it |
| `build` | **nothing**: no secrets, no token, no environment | compiles the code (including whatever the AI fixer wrote), unsigned |
| `sign` | environment `signing` -> `TAURI_SIGNING_PRIVATE_KEY` | runs ONE command from a locked, pinned npm install (`signer/`, `--ignore-scripts`): `tauri signer sign`. No repository code runs here |
| `publish` | environment `publishing` -> `PUBLISH_TOKEN` | uploads installer + `.sig` + `latest.json`, tells the bug queue to e-mail the reporters |

Why it holds: AI-written code only ever runs in `build`, which has nothing to steal. The environments only release their secrets to
workflows running on `main`, there is no `pull_request`/fork trigger, every action is pinned to a commit hash, workflows get read-only
default permissions, and only GitHub's own actions are allowed. Stable releases are still built and signed on the owner's PC.

Setup (once, by the owner; the values are never written to a file):
```
gh secret set TAURI_SIGNING_PRIVATE_KEY --env signing    -R ribanixlabs/mimicore-ci < "$env:USERPROFILE\.mimicore-keys\updater.key"
gh secret set PUBLISH_TOKEN             --env publishing -R ribanixlabs/mimicore-ci      # fine-grained PAT: Contents read/write on ribanixlabs/mimicore-app only
```
Test without publishing: Actions > beta > Run workflow > force=yes, publish=no.
