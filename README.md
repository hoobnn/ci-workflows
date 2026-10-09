# ci-workflows：macOS 应用签名、公证与发布的复用 GitHub Actions

**简体中文** · [English](README.en.md)

可复用的 macOS 应用发布流程，依次完成 Developer ID 签名、Apple 公证、发布 GitHub Release、同步 Homebrew cask，以及生成 Sparkle 应用内更新的 appcast。目前用于 [fanfan](https://github.com/hoobnn/fanfan)、[LiveTranslateBridge](https://github.com/hoobnn/livetranslate-bridge) 和 [Keyboard Logo Fix](https://github.com/hoobnn/macos-keyboard-logo-fix)。

个人账号下跨仓库调用 reusable workflow 时，被调用的仓库必须公开，因此本仓库保持公开。仓库中只包含构建逻辑，凭据均保存在调用方的 secrets 中。

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

### 输入

| 名称 | 必填 | 说明 |
|---|---|---|
| `app-path` | ✅ | 构建产物 `.app` 的路径 |
| `build-command` | ✅ | 产出 `.app` 的命令 |
| `artifact-basename` | ✅ | 发布文件名前缀，如 `My-App` |
| `inner-binaries` | | 需先于外层签名的嵌套二进制，相对 `.app` 的路径，换行分隔 |
| `entitlements` | | 外层 bundle 的 `.entitlements` 路径 |
| `make-dmg` | | 是否额外产出 dmg，默认 `false` |
| `dmg-volume-name` | | dmg 卷名，默认取 `artifact-basename` |
| `runs-on` | | runner，默认 `macos-15` |
| `release-notes-file` | | 指定 release 正文文件，缺省用 `--generate-notes` |
| `sparkle` | | 为 Sparkle 更新签名 zip，并随 Release 发布 `.zip.sparkle.json`，默认 `false`；需要 secret `SPARKLE_ED_PRIVATE_KEY` |

### 调用方需要的凭据

Secrets：`APPLE_CERT_APPLICATION_P12_BASE64`、`APPLE_CERT_APPLICATION_P12_PASSWORD`、
`APPLE_NOTARY_KEY_ID`、`APPLE_NOTARY_ISSUER_ID`、`APPLE_NOTARY_KEY_P8_BASE64`

Variables：`APPLE_TEAM_ID`、`APPLE_SIGN_IDENTITY_APPLICATION`

`.pkg` 分发时另加 `APPLE_CERT_INSTALLER_P12_BASE64`、`APPLE_CERT_INSTALLER_P12_PASSWORD`
与 `APPLE_SIGN_IDENTITY_INSTALLER`。

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

## 实践中确定的做法

- 先签内层二进制，再签外层，不用 `--deep`。`--deep` 已经废弃，还会把外层的签名参数套到嵌套代码上。
- 一定带 `--options runtime` 和 `--timestamp`。少了前者公证直接被拒；少了后者，证书过期后已经发出去的包会失效。
- 打包用 `ditto`，不用 `zip`。staple 进去的公证票据存在扩展属性里，`zip` 会把它丢掉。
- dmg 要单独签名、单独公证、单独 staple。里面的 app 公证过了，不代表外面的 dmg 也算公证过。
- 临时钥匙串的密码用 `uuidgen` 现生成，用完即弃，无需为此额外维护一个跨仓库同步的 secret。
- 公证失败时自动获取 `notarytool log`，具体失败原因只能在这里看到。
- tag 必须和 `CFBundleShortVersionString` 一致，否则用户下载到的版本号会不一致。

## 版本

调用方固定 `@v1`。改动后移动 tag：

```bash
git tag -fa v1 -m "..." && git push -f origin v1
```

## 许可

[MIT](LICENSE)
