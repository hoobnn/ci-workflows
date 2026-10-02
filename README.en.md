# ci-workflows: reusable GitHub Actions for signing, notarizing and releasing macOS apps

[简体中文](README.md) · **English**

The release pipeline shared by my macOS apps ([fanfan](https://github.com/hoobnn/fanfan), [LiveTranslateBridge](https://github.com/hoobnn/livetranslate-bridge), [Keyboard Logo Fix](https://github.com/hoobnn/macos-keyboard-logo-fix)): Developer ID signing, Apple notarization, a GitHub Release, then a Homebrew cask bump.

The repo has to stay public: on a personal account, a reusable workflow can only be called from another repo if it's public. There are no credentials here, only build logic; secrets live in the calling repo.

## Usage

```yaml
jobs:
  release:
    uses: hoobnn/ci-workflows/.github/workflows/macos-release.yml@v1
    with:
      app-path: "dist/My App.app"
      build-command: make app
      artifact-basename: My-App
      make-dmg: true
    secrets: inherit
```

### Inputs

| Name | Required | Description |
|---|---|---|
| `app-path` | ✅ | Path to the built `.app` |
| `build-command` | ✅ | Command that produces the `.app` |
| `artifact-basename` | ✅ | Prefix for release file names, e.g. `My-App` |
| `inner-binaries` | | Nested binaries to sign before the outer bundle, relative to the `.app`, one per line |
| `entitlements` | | `.entitlements` file for the outer bundle |
| `make-dmg` | | Also build a dmg, default `false` |
| `dmg-volume-name` | | dmg volume name, defaults to `artifact-basename` |
| `runs-on` | | Runner, default `macos-15` |
| `release-notes-file` | | File to use as the release body; `--generate-notes` if omitted |

### Credentials the caller needs

Secrets: `APPLE_CERT_APPLICATION_P12_BASE64`, `APPLE_CERT_APPLICATION_P12_PASSWORD`,
`APPLE_NOTARY_KEY_ID`, `APPLE_NOTARY_ISSUER_ID`, `APPLE_NOTARY_KEY_P8_BASE64`

Variables: `APPLE_TEAM_ID`, `APPLE_SIGN_IDENTITY_APPLICATION`

For `.pkg` distribution, also `APPLE_CERT_INSTALLER_P12_BASE64`, `APPLE_CERT_INSTALLER_P12_PASSWORD`
and `APPLE_SIGN_IDENTITY_INSTALLER`.

## Bumping a Homebrew cask

After a release is published, `homebrew-cask.yml` reads the `.dmg.sha256` from the release, rewrites `version` and `sha256` in the tap's cask, and pushes. Only call it on tags:

```yaml
  homebrew:
    needs: release
    if: startsWith(github.ref, 'refs/tags/v')
    uses: hoobnn/ci-workflows/.github/workflows/homebrew-cask.yml@v1
    with:
      cask: my-app                                   # Casks/my-app.rb
      artifact-basename: My-App                      # same as macos-release
      version: ${{ needs.release.outputs.version }}
    secrets: inherit
```

| Name | Required | Description |
|---|---|---|
| `cask` | ✅ | Cask name, i.e. the file under `Casks/` without `.rb` |
| `artifact-basename` | ✅ | Same as in `macos-release.yml` |
| `version` | ✅ | Version being released |
| `tap` | | Tap repo, default `hoobnn/homebrew-tap` |

It needs a `HOMEBREW_TAP_TOKEN` secret: a fine-grained token with Contents read/write on the tap repo only. Without it the job fails on purpose. If the cask kept the old sha256, `brew install` would fail its checksum, and silently skipping is harder to debug than an error. Several apps share one tap, so a rejected push is rebased and retried.

## Suggested layout in the calling repo

```text
.github/workflows/ci.yml       push main / PR / workflow_call → unit tests
.github/workflows/release.yml  v* tag → ci.yml → macos-release.yml → homebrew-cask.yml
```

- Define tests once in `ci.yml`; `release.yml` reuses it with `uses: ./.github/workflows/ci.yml`
- Top-level `permissions: contents: read`; only the release job gets `contents: write`
- CI uses per-branch `concurrency` and cancels stale runs; releases don't cancel, because an interrupted notarization is the worst case
- Pin third-party actions to a commit SHA; official `actions/*` use major versions

## Choices made after hitting the problems

- Sign inner binaries first, then the outer bundle, without `--deep`. `--deep` is deprecated and applies the outer signing options to nested code.
- Always pass `--options runtime` and `--timestamp`. Without the first, notarization is rejected; without the second, shipped builds stop validating once the certificate expires.
- Package with `ditto`, not `zip`. The stapled ticket lives in extended attributes, and `zip` drops them.
- Sign, notarize and staple the dmg on its own. A notarized app inside doesn't make the container notarized.
- Generate the temporary keychain password with `uuidgen` and throw it away; it isn't worth a secret that has to be synced across repos.
- On notarization failure, fetch `notarytool log` automatically. It's the only place Apple gives the real reason.
- The tag must match `CFBundleShortVersionString`, or users download a build whose version doesn't match.

## Versioning

Callers pin `@v1`. After a change, move the tag:

```bash
git tag -fa v1 -m "..." && git push -f origin v1
```

## License

[MIT](LICENSE)
