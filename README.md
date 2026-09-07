# ci-workflows

跨项目复用的 GitHub Actions —— macOS 应用的签名、公证与发布。

仓库需要保持 **public**：个人账号下跨仓库调用 reusable workflow 要求被调用方公开。
这里只有构建逻辑，没有任何凭据，公开无风险。

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

### 调用方需要的凭据

Secrets：`APPLE_CERT_APPLICATION_P12_BASE64`、`APPLE_CERT_APPLICATION_P12_PASSWORD`、
`APPLE_NOTARY_KEY_ID`、`APPLE_NOTARY_ISSUER_ID`、`APPLE_NOTARY_KEY_P8_BASE64`

Variables：`APPLE_TEAM_ID`、`APPLE_SIGN_IDENTITY_APPLICATION`

`.pkg` 分发时另加 `APPLE_CERT_INSTALLER_P12_BASE64`、`APPLE_CERT_INSTALLER_P12_PASSWORD`
与 `APPLE_SIGN_IDENTITY_INSTALLER`。

## 这里固化的几个约定

- **签名顺序内层优先，不用 `--deep`** —— `--deep` 已废弃，且会把外层的签名参数套用到嵌套代码上
- **必须 `--options runtime` + `--timestamp`** —— 前者缺失公证必被拒；后者缺失会让证书过期后已发布的产物失效
- **打包用 `ditto` 而非 `zip`** —— stapled ticket 存在扩展属性里，`zip` 会丢
- **dmg 单独签名、单独公证、单独 staple** —— 容器是独立产物，里面的 app 已公证不代表容器可以免除
- **临时钥匙串密码用 `uuidgen`** —— 用完即弃，没必要占用一个需要跨仓库同步的 secret
- **公证失败自动拉 `notarytool log`** —— Apple 只在这里说明真实原因
- **tag 必须与 `CFBundleShortVersionString` 一致** —— 否则用户下载到的版本号对不上

## 版本

调用方固定 `@v1`。改动后移动 tag：

```bash
git tag -fa v1 -m "..." && git push -f origin v1
```
