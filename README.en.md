# ci-workflows: reusable GitHub Actions for signing, notarizing and releasing macOS apps

[简体中文](README.md) · **English**

A reusable release pipeline for macOS apps: Developer ID signing, Apple notarization, a GitHub Release, a Homebrew cask bump, and a Sparkle appcast for in-app updates. It currently serves [fanfan](https://github.com/hoobnn/fanfan), [LiveTranslateBridge](https://github.com/hoobnn/livetranslate-bridge) [Keyboard Logo Fix](https://github.com/hoobnn/macos-keyboard-logo-fix) and [Plein](https://github.com/hoobnn/plein) (Electron).

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
| `build-command` | one of | Command that produces the `.app` |
| `app-artifact` | one of | Name of an artifact uploaded earlier in the same run holding the `.app` as a single tar; see "Build it yourself, sign it here" |
| `artifact-basename` | ✅ | Prefix for release file names, e.g. `My-App` |
| `inner-binaries` | | Nested binaries to sign before the outer bundle, relative to the `.app`, one per line; `auto` finds all nested code and signs it innermost first |
| `inner-entitlements` | | `.entitlements` file applied to every inner binary (Electron helpers need it) |
| `entitlements` | | `.entitlements` file for the outer bundle |
| `make-dmg` | | Also build a dmg, default `false` |
| `dmg-volume-name` | | dmg volume name, defaults to `artifact-basename` |
| `arch-suffix` | | Append the architecture to file names (`-arm64`, `-x64` or `-universal`, read from the main executable with `lipo`), default `false` |
| `sign` | | `false` makes a dry run: ad-hoc signature, no notarization, no Sparkle signature, no release, just the artifacts, and no credentials needed; default `true` |
| `runs-on` | | Runner, default `macos-15` |
| `release-notes-file` | | File to use as the release body; `--generate-notes` if omitted |
| `sparkle` | | Sign the zip for Sparkle updates and publish a `.zip.sparkle.json` with the release; default `false`; needs the `SPARKLE_ED_PRIVATE_KEY` secret |

Outputs: `version` (`CFBundleShortVersionString`) and `artifact-suffix` (what follows `-macOS` in file names, empty unless `arch-suffix`; pass it to `homebrew-cask.yml` and `sparkle-appcast`).

### Credentials the caller needs

Secrets: `APPLE_CERT_APPLICATION_P12_BASE64`, `APPLE_CERT_APPLICATION_P12_PASSWORD`,
`APPLE_NOTARY_KEY_ID`, `APPLE_NOTARY_ISSUER_ID`, `APPLE_NOTARY_KEY_P8_BASE64`

Variables: `APPLE_TEAM_ID`, `APPLE_SIGN_IDENTITY_APPLICATION`

For `.pkg` distribution, also `APPLE_CERT_INSTALLER_P12_BASE64`, `APPLE_CERT_INSTALLER_P12_PASSWORD`
and `APPLE_SIGN_IDENTITY_INSTALLER`.

They are checked before anything is built, and every missing one is listed at once. A new repo without credentials can start with `sign: false` to get packaging working first.

## Build it yourself, sign it here

The reusable workflow only checks out and runs `build-command`, so it can't use actions such as `setup-node` or `actions/cache`. Apps that need a runtime or large cached dependencies, Electron for one, build in their own job, upload the `.app` as a tar, and hand it over for signing, notarization and release:

```yaml
jobs:
  build:
    runs-on: macos-15
    steps:
      - uses: actions/checkout@v7
      # setup-node, caches, build… producing dist/mac-arm64/My App.app, signed or not
      - run: tar -cf app.tar -C dist/mac-arm64 "My App.app"
      - uses: actions/upload-artifact@v7
        with:
          name: app
          path: app.tar
          retention-days: 1

  release:
    needs: build
    permissions:
      contents: write
    uses: hoobnn/ci-workflows/.github/workflows/macos-release.yml@v1
    with:
      app-path: "dist/mac-arm64/My App.app"
      app-artifact: app
      artifact-basename: My-App
      inner-binaries: auto
      inner-entitlements: build/entitlements.mac.plist
      entitlements: build/entitlements.mac.plist
      arch-suffix: true
      make-dmg: true
    secrets: inherit
```

- Upload a tar, not the `.app` itself: upload-artifact's zip drops the symlinks and executable bits inside frameworks.
- `inner-binaries: auto` signs by path depth, innermost first: Mach-O files (dylibs, `.node` native modules, each bundle's executable), then `.framework`, helper `.app`, `.xpc`, `.appex` and `.bundle` dirs that carry code. The main executable is left to the outer signature. An Electron app has twenty-odd items; a hand-written list misses some and goes stale with every Electron upgrade.
- Electron helpers need `allow-jit` and `allow-unsigned-executable-memory` under the hardened runtime, so don't skip `inner-entitlements` or the renderer crashes on launch. Add `disable-library-validation` when loading third-party native modules (sharp, better-sqlite3 and the like).
- electron-builder needs no certificate here; everything is re-signed with `--force`.

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
| `artifact-suffix` | | The `artifact-suffix` output of `macos-release.yml`; required with `arch-suffix` |
| `tap` | | Tap repo, default `hoobnn/homebrew-tap` |

It needs a `HOMEBREW_TAP_TOKEN` secret: a fine-grained token with Contents read/write on the tap repo only. Without it the job fails on purpose. If the cask kept the old sha256, `brew install` would fail its checksum, and silently skipping is harder to debug than an error. Several apps share one tap, so a rejected push is rebased and retried.

## Sparkle in-app updates

The appcast is not committed. It is built from GitHub Releases whenever Pages deploys:

1. With `sparkle: true`, `macos-release.yml` signs the zip with `SPARKLE_ED_PRIVATE_KEY` (EdDSA) and
   publishes the signature, length and bundle versions as `<basename>-<version>-macOS.zip.sparkle.json`
   next to it. The Sparkle tools are pinned to 2.10.0 and checked by SHA-256; the key only goes in via stdin.
2. The caller's Pages workflow runs the `sparkle-appcast` action to write `appcast.xml` from all releases:

```yaml
      - uses: hoobnn/ci-workflows/.github/actions/sparkle-appcast@v1
        with:
          output: _site/appcast.xml
          artifact-basename: My-App          # same as macos-release
          title: My App
```

| Name | Required | Description |
|---|---|---|
| `output` | ✅ | Where to write the appcast |
| `artifact-basename` | ✅ | Same as `macos-release.yml` |
| `title` | ✅ | Feed title, normally the app name |
| `artifact-suffix` | | The `artifact-suffix` output of `macos-release.yml`; required with `arch-suffix` |
| `max-items` | | Newest N releases to list, default `10` |
| `include-prereleases` | | Include prereleases, default `false` |

3. Call the Pages workflow once after releasing (give it a `workflow_call` trigger) so the feed updates
   right away. Releases and pushes made with `GITHUB_TOKEN` do not trigger other workflows, so
   `release: published` cannot be relied on.

Releases without a `.zip.sparkle.json` are skipped; deleting a release drops its item.
Point the app's `SUFeedURL` at `appcast.xml` on Pages (`*.github.io` is usually reachable from mainland
China where `raw.githubusercontent.com` often is not) and set `SUPublicEDKey` to the matching public key.
Use one key pair per app: `generate_keys --account <app>`, then `generate_keys --account <app> -x <file>`
to export the private key into the secret.

## Suggested layout in the calling repo

```text
.github/workflows/ci.yml       push main / PR / workflow_call → unit tests
.github/workflows/release.yml  v* tag → ci.yml → macos-release.yml → homebrew-cask.yml
```

- Define tests once in `ci.yml`; `release.yml` reuses it with `uses: ./.github/workflows/ci.yml`
- Top-level `permissions: contents: read`; only the release job gets `contents: write`
- CI uses per-branch `concurrency` and cancels stale runs; releases don't cancel, because an interrupted notarization is the worst case
- Pin third-party actions to a commit SHA; official `actions/*` use major versions
- Give manual runs a `sign` switch, so environments without a certificate can still check packaging with `sign: false`

## Lessons learned

- Sign inner binaries first, then the outer bundle, without `--deep`. `--deep` is deprecated and applies the outer signing options to nested code.
- Give inner code its own entitlements. Each executable only honors the entitlements in its own signature; the outer ones are not inherited, and an Electron helper without `allow-jit` crashes.
- Pass a `.app` between jobs as a tar. upload-artifact's zip drops symlinks and executable bits, and the signature with them.
- Check credentials before building and list every missing one at once. An empty secret otherwise surfaces as an opaque base64 or keychain error.
- Always pass `--options runtime` and `--timestamp`. Without the first, notarization is rejected; without the second, shipped builds stop validating once the certificate expires.
- Package with `ditto`, not `zip`. The stapled ticket lives in extended attributes, and `zip` drops them.
- Sign, notarize and staple the dmg on its own. A notarized app inside doesn't make the container notarized.
- Generate the temporary keychain password with `uuidgen` and discard it after use; it doesn't warrant a secret synced across repos.
- On notarization failure, fetch `notarytool log` automatically. It's the only place Apple gives the real reason.
- The tag must match `CFBundleShortVersionString`, or users download a build whose version doesn't match.

## Versioning

Callers pin `@v1`. After a change, move the tag:

```bash
git tag -fa v1 -m "..." && git push -f origin v1
```

## License

[MIT](LICENSE)
