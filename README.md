# ci-workflows：macOS 应用签名、公证与发布的复用 GitHub Actions

**简体中文** · [English](README.en.md)

**ci-workflows** 是免费开源（MIT）的 GitHub Actions reusable workflow 集合，用来给 macOS 应用做 Developer ID 签名、Apple 公证（notarization）并发布到 GitHub Release；可选同步 Homebrew cask，并生成 Sparkle 应用内更新的 appcast。支持原生 Xcode 应用和 Electron 应用，调用方用 `uses: hoobnn/ci-workflows/.github/workflows/macos-release.yml@v1` 引用。流程依次完成 Developer ID 签名、Apple 公证、发布 GitHub Release、同步 Homebrew cask，以及生成 Sparkle 应用内更新的 appcast。目前用于 [fanfan](https://github.com/hoobnn/fanfan)、[LiveTranslateBridge](https://github.com/hoobnn/livetranslate-bridge)、[Keyboard Logo Fix](https://github.com/hoobnn/macos-keyboard-logo-fix) 和 [Plein](https://github.com/hoobnn/plein)（Electron）。

个人账号下跨仓库调用 reusable workflow 时，被调用的仓库必须公开，因此本仓库保持公开。仓库中只包含构建逻辑，凭据均保存在调用方的 secrets 中。

## 包含什么

| 组件 | 类型 | 作用 |
|---|---|---|
| `macos-release.yml` | reusable workflow | 构建（或接收已构建的 `.app`）、由内向外签名、公证并 staple、打包 zip / dmg、发布 GitHub Release |
| `homebrew-cask.yml` | reusable workflow | Release 发布后更新 tap 里 cask 的 `version` 与 `sha256` |
| `.github/actions/sparkle-appcast` | composite action | 从 GitHub Releases 生成 Sparkle `appcast.xml` |
| `.github/actions/apple-signing` | composite action | 把 Developer ID 证书导入临时钥匙串（`macos-release.yml` 内部使用，也可单独调用） |
| `.github/actions/apple-notarize` | composite action | 提交 Apple 公证、等待结果并 staple，失败时取回公证日志（同上） |

## 用法

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

调用方的 job 或 workflow 需要授予 `contents: write`（发布 Release 用，见下文完整示例）。

### 输入

| 名称 | 必填 | 说明 |
|---|---|---|
| `app-path` | ✅ | 构建产物 `.app` 的路径 |
| `build-command` | 二选一 | 产出 `.app` 的命令 |
| `app-artifact` | 二选一 | 同一次运行里先上传的 artifact 名，内含 `.app` 的单个 tar，见「自行构建，再交给复用工作流签名」 |
| `artifact-basename` | ✅ | 发布文件名前缀，如 `My-App` |
| `inner-binaries` | | 需先于外层签名的嵌套二进制，相对 `.app` 的路径，换行分隔；写 `auto` 时自动找出全部嵌套代码，由内向外签名 |
| `inner-entitlements` | | 内层代码统一使用的 `.entitlements` 路径（Electron 的 Helper 需要） |
| `entitlements` | | 外层 bundle 的 `.entitlements` 路径 |
| `make-dmg` | | 是否额外产出 dmg，默认 `false` |
| `dmg-volume-name` | | dmg 卷名，默认取 `artifact-basename` |
| `arch-suffix` | | 文件名加架构后缀（`-arm64`、`-x64` 或 `-universal`，用 `lipo` 读主可执行文件），默认 `false` |
| `sign` | | 设为 `false` 时试运行：ad-hoc 签名，不公证、不做 Sparkle 签名、不发布，只上传 Artifacts，不需要任何凭据；默认 `true` |
| `runs-on` | | runner，默认 `macos-15` |
| `release-notes-file` | | 指定 release 正文文件，缺省用 `--generate-notes` |
| `sparkle` | | 为 Sparkle 更新签名 zip，并随 Release 发布 `.zip.sparkle.json`，默认 `false`；需要 secret `SPARKLE_ED_PRIVATE_KEY` |

输出：`version`（`CFBundleShortVersionString`）和 `artifact-suffix`（文件名里 `-macOS` 之后的部分，未开 `arch-suffix` 时为空，传给 `homebrew-cask.yml` 和 `sparkle-appcast`）。

### 调用方需要的凭据

Secrets：`APPLE_CERT_APPLICATION_P12_BASE64`、`APPLE_CERT_APPLICATION_P12_PASSWORD`、
`APPLE_NOTARY_KEY_ID`、`APPLE_NOTARY_ISSUER_ID`、`APPLE_NOTARY_KEY_P8_BASE64`

Variables：`APPLE_TEAM_ID`、`APPLE_SIGN_IDENTITY_APPLICATION`

开启 `sparkle` 时另需 secret `SPARKLE_ED_PRIVATE_KEY`；同步 Homebrew cask 需 `HOMEBREW_TAP_TOKEN`（见下文）。

`.pkg` 分发时另加 `APPLE_CERT_INSTALLER_P12_BASE64`、`APPLE_CERT_INSTALLER_P12_PASSWORD`
与 `APPLE_SIGN_IDENTITY_INSTALLER`。

构建之前会先检查这些凭据，缺哪些一次列全并直接失败。新仓库还没配凭据时，可以先用 `sign: false` 跑通打包。

## 自行构建，再交给复用工作流签名

复用工作流只做 checkout 再运行 `build-command`，用不了 `setup-node`、`actions/cache` 这类 action。Electron 等需要准备运行时、缓存大依赖的应用，在自己的 job 里构建，把 `.app` 打成 tar 上传，再交给复用工作流签名、公证和发布：

```yaml
jobs:
  build:
    runs-on: macos-15
    steps:
      - uses: actions/checkout@v7
      # setup-node、缓存、构建……产出 dist/mac-arm64/My App.app，签不签名都行
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

- 用 tar 而不是直接上传 `.app`：upload-artifact 打 zip 时会丢掉 framework 里的符号链接和可执行权限。
- `inner-binaries: auto` 按路径深度由内向外签：先签 Mach-O 文件（dylib、`.node` 原生模块、各 bundle 的可执行文件），再签 `.framework`、Helper `.app`、`.xpc`、`.appex` 和带代码的 `.bundle`；主可执行文件留给外层签名。Electron 应用通常有二三十项，手写清单容易漏，升级 Electron 后也会失效。
- Electron 的 Helper 在 hardened runtime 下需要 `allow-jit`、`allow-unsigned-executable-memory`，`inner-entitlements` 不能省，否则渲染进程一启动就崩溃。加载第三方原生模块（sharp、better-sqlite3 等）时再加 `disable-library-validation`。
- electron-builder 那一步不需要证书，这里会用 `--force` 全部重签。

## 同步 Homebrew cask

`homebrew-cask.yml` 在 Release 发布后，用 Release 里的 `.dmg.sha256` 改写 tap 中 cask 的
`version` 与 `sha256` 并推送。只应在打标签时调用：

```yaml
  homebrew:
    needs: release
    if: startsWith(github.ref, 'refs/tags/v')
    uses: hoobnn/ci-workflows/.github/workflows/homebrew-cask.yml@v1
    with:
      cask: my-app                                   # Casks/my-app.rb
      artifact-basename: My-App                      # 与 macos-release 相同
      version: ${{ needs.release.outputs.version }}
    secrets: inherit
```

| 名称 | 必填 | 说明 |
|---|---|---|
| `cask` | ✅ | cask 名，即 `Casks/` 下的文件名（不含 `.rb`） |
| `artifact-basename` | ✅ | 与 `macos-release.yml` 相同 |
| `version` | ✅ | 发布的版本号 |
| `artifact-suffix` | | `macos-release.yml` 输出的 `artifact-suffix`，开了 `arch-suffix` 时必填 |
| `tap` | | tap 仓库，默认 `hoobnn/homebrew-tap` |

需要 secret `HOMEBREW_TAP_TOKEN`：fine-grained token，只授权 tap 仓库的 Contents 读写。
未配置该 secret 时流程会直接失败，这是有意为之：cask 保留旧版本的 sha256 会导致 `brew install` 校验失败，静默跳过比直接报错更难排查。
多个应用共用一个 tap，推送被拒时会 rebase 后重试。

## Sparkle 应用内更新

appcast 不提交进仓库，而是在部署 Pages 时从 GitHub Releases 生成：

1. `macos-release.yml` 设 `sparkle: true` 后，用 `SPARKLE_ED_PRIVATE_KEY` 给 zip 做 EdDSA 签名，
   把签名、长度和 bundle 版本写进 `<basename>-<版本>-macOS.zip.sparkle.json`，随 Release 一起发布。
   Sparkle 工具锁定 2.10.0 并校验 SHA-256，私钥只经 stdin 传入。
2. 调用方的 Pages workflow 用 `sparkle-appcast` action 读取所有 Release，写出 `appcast.xml`：

```yaml
      - uses: hoobnn/ci-workflows/.github/actions/sparkle-appcast@v1
        with:
          output: _site/appcast.xml
          artifact-basename: My-App          # 与 macos-release 相同
          title: My App
```

| 名称 | 必填 | 说明 |
|---|---|---|
| `output` | ✅ | appcast 输出路径 |
| `artifact-basename` | ✅ | 与 `macos-release.yml` 相同 |
| `title` | ✅ | feed 标题，一般用应用名 |
| `artifact-suffix` | | `macos-release.yml` 输出的 `artifact-suffix`，开了 `arch-suffix` 时必填 |
| `max-items` | | 列出最近几个版本，默认 `10` |
| `include-prereleases` | | 是否包含预发布版本，默认 `false` |

3. 发版后调用一次 Pages workflow（给它加 `workflow_call` 触发器），让 appcast 立即更新。
   用 `GITHUB_TOKEN` 发布的 Release 和推送不会触发其他 workflow，所以不能依赖 `release: published`。

没有 `.zip.sparkle.json` 的旧 Release 会被跳过；删除某个 Release，它对应的更新条目也随之消失。
应用里 `SUFeedURL` 指向 Pages 上的 `appcast.xml`（`*.github.io` 在国内通常比 `raw.githubusercontent.com` 可达），
`SUPublicEDKey` 是对应的公钥。每个应用用独立的密钥对，生成方法：
`generate_keys --account <应用名>`，再用 `generate_keys --account <应用名> -x <文件>` 导出私钥写入 secret。

## 调用方的推荐结构

```text
.github/workflows/ci.yml       push main / PR / workflow_call → 单元测试
.github/workflows/release.yml  v* 标签 → ci.yml → macos-release.yml → homebrew-cask.yml
```

- 测试只在 `ci.yml` 定义一次，`release.yml` 以 `uses: ./.github/workflows/ci.yml` 复用
- 顶层 `permissions: contents: read`，只给发布任务 `contents: write`
- CI 按分支设 `concurrency` 并取消旧的运行；发布不取消，避免公证中途被打断
- 第三方 action 钉到 commit SHA，官方 `actions/*` 用大版本号
- 手动触发时给 `sign` 留一个开关，没有证书的环境也能用 `sign: false` 验证打包

## 实践中确定的做法

- 先签内层二进制，再签外层，不用 `--deep`。`--deep` 已经废弃，还会把外层的签名参数套到嵌套代码上。
- 内层代码的 entitlements 要单独给。每个可执行文件只认自己签名里的 entitlements，外层的不会传下去；Electron Helper 缺了 `allow-jit` 就会崩溃。
- 在 job 之间传 `.app` 要先打成 tar，upload-artifact 的 zip 会丢掉符号链接和可执行权限，签名也随之失效。
- 凭据在构建之前就检查，一次列出所有缺失项。空的 secret 否则会在 base64 解码或导入钥匙串时报出看不懂的错误。
- 一定带 `--options runtime` 和 `--timestamp`。少了前者公证直接被拒；少了后者，证书过期后已经发出去的包会失效。
- 打包用 `ditto`，不用 `zip`。staple 进去的公证票据存在扩展属性里，`zip` 会把它丢掉。
- dmg 要单独签名、单独公证、单独 staple。里面的 app 公证过了，不代表外面的 dmg 也算公证过。
- 临时钥匙串的密码用 `uuidgen` 现生成，用完即弃，无需为此额外维护一个跨仓库同步的 secret。
- 公证失败时自动获取 `notarytool log`，具体失败原因只能在这里看到。
- tag 必须和 `CFBundleShortVersionString` 一致，否则用户下载到的版本号会不一致。

## 常见问题

**能用于哪些应用？** 原生 Xcode / Swift 应用和 Electron 应用都可以。Electron 这类需要自己准备运行时的，先在自己的 job 里构建并把 `.app` 打成 tar 上传，再用 `app-artifact` 交给 `macos-release.yml` 签名，见「自行构建，再交给复用工作流签名」。

**没有 Apple 开发者证书能试吗？** 可以，传 `sign: false` 做试运行：ad-hoc 签名，不公证、不发布，只上传 Artifacts，不需要任何凭据。

**为什么本仓库是公开的，会泄露凭据吗？** 个人账号下，被跨仓库调用的 reusable workflow 必须公开。仓库里只有构建逻辑，证书和密钥都存在调用方的 secrets 里。

**公证失败或超时怎么办？** 公证失败时流程会自动取回 `notarytool log` 并打印原因；staple 和 validate 遇到网络断开会退避重试。常见原因是缺 `--options runtime` / `--timestamp`，或 Electron Helper 没给 `inner-entitlements`，见「实践中确定的做法」。

**调用方一定要固定 `@v1` 吗？** 建议。`v1` 是随改动移动的 tag（见「版本」），固定它可以拿到修复又不会跨大版本。

**和别的方案比？** 如果只需要在一个应用里签名公证，直接写一份 workflow 或用社区现成的 Action 也够了；这套的价值在于多个应用共用同一份流程，并带 Sparkle appcast 和 Homebrew cask 同步。

## 版本

调用方固定 `@v1`。改动后移动 tag：

```bash
git tag -fa v1 -m "..." && git push -f origin v1
```

## 许可

[MIT](LICENSE)
