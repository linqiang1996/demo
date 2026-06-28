# FOF净值跟踪网站

这个小网站会做三件事：

1. 从本地样例 Excel 或邮箱同步私募产品净值。
2. 展示每个产品的最新净值、当日增长、当周增长、下投以来增长。
3. 允许按产品填写配置金额，自动换算占比并生成 FOF 组合净值和核心指标。

## 本地稳定启动

```bash
cd /Volumes/LEARN/VS_CODE/fof私募研究/fof净值跟踪
./scripts/install_local.sh
./scripts/start_local.sh
```

启动后访问：

`http://127.0.0.1:5050`

查看运行状态：

```bash
./scripts/status_local.sh
```

停止服务：

```bash
./scripts/stop_local.sh
```

这样启动后，服务会在后台常驻运行，不再依赖你当前打开的终端窗口。

如果你希望电脑重启后也自动恢复运行，可执行：

```bash
./scripts/install_launch_agent.sh
```

移除开机自启动：

```bash
./scripts/uninstall_launch_agent.sh
```

## 邮箱自动同步配置

1. 复制 `.env.example` 为 `.env`
2. 填入 QQ 邮箱账号
3. 不要直接填网页登录密码
4. 需要在 QQ 邮箱后台开启 IMAP，并生成 16 位授权码
5. 把授权码填到 `FOF_MAIL_PASSWORD`
6. 如需给网页和小程序加访问保护，可填写 `FOF_ACCESS_CODE`

默认配置：

- IMAP 服务器：`imap.qq.com`
- 端口：`993`
- 协议：`SSL`
- 轮询频率：默认每 `5` 分钟
- 邮件主题关键词：`净值`

## 当前解析能力

目前支持两类净值来源：

1. Excel 附件
   文件中包含 `日期` 和 `单位净值` 这类列即可自动识别。
2. 邮件正文
   例如正文中出现“产品名 + 日期 + 净值”的文本时会尝试解析。

如果你的真实邮件模板更复杂，可以继续补充正文正则或附件解析逻辑，入口文件在：

- `app/mail_sync.py`
- `app/nav_parser.py`

## 组合指标口径

- 组合单位净值：组合净值曲线最新值，起始基准为 `1.0000`
- 累积收益：`组合单位净值 - 1`
- 今年以来收益：以上一年度最后一个净值日到最新净值日计算
- 日度最大回撤：按组合日度净值序列计算
- 周度最大回撤：按每周五重采样后的净值序列计算
- 夏普比率：默认无风险利率 `1.5%`
- 卡玛比率：年化收益 / 最大回撤

如果首次建仓单位净值填成最新净值，该持仓自身收益会接近 `0`，但组合历史仍会从该产品首个可用净值日期纳入。
如果上一年度收益为负，`累积收益` 小于 `今年以来收益` 也可能是正常现象。

## 登录访问

如果 `.env` 中配置了 `FOF_ACCESS_CODE`：

- 网页端会先跳转到 `/login`
- 小程序端会通过请求头 `X-FOF-Access-Code` 自动携带访问口令
- 你可以把小程序里的 `accessCode` 和网站访问口令设置成同一个值

如果没有配置 `FOF_ACCESS_CODE`：

- 公网首页不会真正要求输入口令
- `/login` 看起来像“登录页”，但会直接跳回首页
- 这时任何拿到网址的人都可以访问页面

## 手机端与离线访问

如果手机和电脑在同一 Wi‑Fi 下，手机浏览器可直接访问：

`http://你的电脑局域网IP:5050`

网站首页会直接显示这个局域网地址。

网页已支持离线缓存：

- 首次在手机浏览器打开后，可“添加到主屏幕”
- 即使手机暂时断网，仍可查看最近一次已缓存的数据页面
- 但如果电脑关机，手机端只能看缓存的旧数据，不能继续同步新邮件

这里需要明确区分两种“离线”：

- 手机断网但电脑服务还在运行：可以看缓存，也可恢复网络后继续看最新数据
- 电脑关机或本地服务停止：手机只能看上一次缓存的旧页面，不能获得新数据

如果你要“电脑关闭后仍能稳定查看最新数据”，唯一彻底方案仍然是公网部署。

如果要让手机端、电脑端在你电脑关闭后也能继续实时查看最新数据，必须把后端部署到持续在线的公网 HTTPS 服务，然后把小程序 API 地址改成公网域名：

1. 复制 [site.config.example.js](/Volumes/LEARN/VS_CODE/fof私募研究/fof净值跟踪/miniprogram/site.config.example.js) 为 `miniprogram/site.config.js`
2. 把 `apiBase` 改成 Render 分配给你的固定地址，例如 `https://your-service-name.onrender.com`
3. 把 `accessCode` 改成与你后端 `FOF_ACCESS_CODE` 相同的访问口令
4. 在微信小程序后台把这个 HTTPS 域名加入合法请求域名

## 云端稳定运行

项目已经补好了云端部署文件：

- [Dockerfile](/Volumes/LEARN/VS_CODE/fof私募研究/fof净值跟踪/Dockerfile)
- [render.yaml](/Volumes/LEARN/VS_CODE/fof私募研究/fof净值跟踪/render.yaml)
- [wsgi.py](/Volumes/LEARN/VS_CODE/fof私募研究/fof净值跟踪/wsgi.py)

`render.yaml` 已经包含：

- 持久化磁盘挂载，避免 SQLite 数据因重启丢失
- 默认的 QQ IMAP 环境参数
- 手动填写的敏感变量占位：`FOF_MAIL_ADDRESS`、`FOF_MAIL_PASSWORD`、`FOF_ACCESS_CODE`

### Render 最短部署步骤

1. 把当前项目上传到一个 GitHub 仓库
2. 登录 Render，点击 `New +`
3. 选择 `Blueprint`
4. 连接你的 GitHub 仓库
5. 选择当前仓库根目录下的 `render.yaml`
6. 在 Render 界面补齐这 3 个变量：
   - `FOF_MAIL_ADDRESS`
   - `FOF_MAIL_PASSWORD`
   - `FOF_ACCESS_CODE`
7. 点击 `Apply`
8. 等待 Render 首次构建完成

部署完成后，Render 会自动分配一个固定的 `https://xxxx.onrender.com` 网址。

根据 Render 官方文档：
- Web Service 默认会分配一个固定的 `onrender.com` 子域名
- `render.yaml` 可以直接作为 Blueprint 部署入口
- `sync: false` 的变量需要你在 Render Dashboard 里手动填写
- Render 会为默认域名自动提供 HTTPS/TLS

参考文档：
- Render Web Services: https://render.com/docs/web-services
- Render Blueprint YAML: https://render.com/docs/blueprint-spec
- Render 环境变量: https://render.com/docs/configure-environment-variables
- Render TLS: https://render.com/docs/tls

部署到持续在线的云服务器后：

- 即使你的电脑关闭，网站和小程序也能继续访问
- 即使你没有登录网页邮箱，只要 QQ 邮箱 IMAP 授权码仍然有效，云端服务也会继续自动同步邮件净值
- 手机端和电脑端看到的是云端已经同步到数据库里的数据，不依赖你的本地电脑是否开机
- 后端健康检查地址为 `/healthz`

### 公开仓库与隐私

当前这种 `GitHub 公开仓库 + Render 公网网址` 的方式，源码任何人都能看到，所以不适合作为最私密的长期方案。

需要分清两件事：

- 如果你没有把 `.env`、授权码、数据库文件提交到仓库，别人通常看不到你的邮箱授权码和历史数据
- 但别人能看到你的系统代码结构、接口路径、页面逻辑；如果公网又没设置 `FOF_ACCESS_CODE`，别人还可以直接访问你的看板

更稳妥的做法有三种：

1. GitHub 改成私有仓库，再继续用 Render
2. 改用你自己的云服务器，直接从本地打包上传，不经过公开仓库
3. 用国内云厂商的轻量服务器长期托管，这样数据、代码、访问口令都只在你自己控制的机器里

如果你要“永久、稳定、尽量私密”，推荐顺序是：

1. 私有 GitHub 仓库 + 云端访问口令 + 持久磁盘
2. 腾讯云 Lighthouse / 阿里云轻量应用服务器，自建 Docker 部署

第二种最私密，因为：

- 不需要公开 GitHub 仓库
- 不依赖第三方从公开仓库拉代码
- 邮箱授权码、SQLite 数据库、组合配置都只保存在你自己的服务器上
- 服务器可以设置固定 IP、登录白名单、Nginx Basic Auth 或 HTTPS 访问口令

### 云端组合配置持久化

为了避免“公网服务重建后组合字段为空”，现在代码支持可选环境变量：

- `FOF_PORTFOLIO_JSON`

你可以把当前默认组合配置导出成一段 JSON，放进云端环境变量。这样即使云端数据库重建，只要这段变量还在，系统也会自动恢复默认组合配置。

另外还支持：

- `FOF_DASHBOARD_CACHE_SECONDS`

默认 `30` 秒，用来缓存首页计算结果，减少公网登录后首屏等待时间。

注意：

- 目前项目已经具备上线所需代码，但“真正给你一个公网网址”仍然需要外部云平台账号或服务器
- 微信小程序不能直接访问本地 `127.0.0.1`，必须使用已备案/已配置到小程序后台的 HTTPS 域名

### 自定义域名

如果你不想使用默认的 `onrender.com` 网址，可以在 Render 的服务设置页里添加自定义域名。

根据 Render 官方文档：
- 自定义域名在 Dashboard 里添加
- Render 会自动签发和续期 HTTPS 证书

参考文档：
- https://render.com/docs/custom-domains

### 一键校验与创建

本地已经补好了两个 Render 脚本：

```bash
cd /Volumes/LEARN/VS_CODE/fof私募研究/fof净值跟踪

export RENDER_API_KEY=你的RenderAPIKey
export RENDER_OWNER_ID=你的WorkspaceID
export RENDER_REPO_URL=https://github.com/你的GitHub用户名/你的仓库名

./scripts/render_precheck.sh
./scripts/render_validate.sh
./scripts/render_create_service.sh
```

说明：

- `render_precheck.sh` 会一次输出 Workspace、`render.yaml`、仓库可访问性三项结果
- `render_validate.sh` 会校验 `render.yaml`
- `render_create_service.sh` 会读取本地 `.env`，把邮箱同步参数一并带到云端服务
- 默认会创建名为 `fof-nav-tracker` 的 `starter` 计划 Web Service，并挂载持久化磁盘
- 如果仓库分支不是默认分支，可额外设置 `RENDER_BRANCH`
- 如果你想自定义服务名，可额外设置 `RENDER_SERVICE_NAME`
- 如果项目不在仓库根目录，可额外设置 `RENDER_ROOT_DIR`
- 注意：`RENDER_ROOT_DIR` 只能使用 ASCII 路径，不能直接填写中文目录名

两种部署模式：

1. 测试公网模式
   适合先验证公网访问链路

```bash
export RENDER_PLAN=free
export RENDER_ENABLE_DISK=false
./scripts/render_create_service.sh
```

这个模式的特点：

- 如果仓库可访问，理论上更容易先拿到一个临时公网网址
- 数据库会落到 `/tmp/fof_nav.db`
- 服务重启或重新部署后数据可能丢失
- 不适合长期稳定运行

2. 正式稳定模式
   适合你最终要的“电脑关机后也能长期稳定访问”

```bash
export RENDER_PLAN=starter
export RENDER_ENABLE_DISK=true
./scripts/render_create_service.sh
```

这个模式的特点：

- 数据库会落到持久化磁盘
- 更适合长期自动同步邮箱
- 需要 Render 工作区补齐支付信息

当前我已经实际验证过两点：

- Render API Key 可正常访问你的 Workspace
- 当前创建公网服务的真实阻塞点只剩两个平台条件

当前阻塞条件：

- Render 校验 `render.yaml` 时返回 `need_payment_info`
- Render 创建服务时返回仓库 `invalid or unfetchable`

这两个返回意味着：

- 你当前 Render 工作区还没有补齐支付信息，因此 `starter + disk` 这种可持续在线方案还不能真正创建
- 你提供的 GitHub 仓库当前对 Render 不可抓取，可能是仓库不存在、私有仓库未授权给 Render，或仓库地址还没准备好

要真正拿到“电脑关机后也能稳定访问”的固定公网网址，这一步只需要把下面两项补齐：

1. 在 Render 工作区补齐支付信息
2. 让 Render 能访问这个 GitHub 仓库

让 Render 能访问仓库的最短做法：

1. 确认仓库真实存在，且地址形如 `https://github.com/用户名/仓库名`
2. 如果仓库是私有仓库，在 Render Dashboard 中连接 GitHub，并给该仓库授权
3. 如果只是临时部署，也可以先把仓库设为公开，再执行上面的创建脚本

## 本地封装包

如果你想把当前本地版整体打包：

```bash
./scripts/package_local.sh
```

生成文件：

`runtime/fof_local_bundle.tar.gz`

## GitHub 发布目录

如果你要把当前 FOF 项目推到 GitHub 仓库根目录，而不是推本地数据库、缓存和运行文件，可以直接执行：

```bash
cd /Volumes/LEARN/VS_CODE/fof私募研究/fof净值跟踪
./scripts/export_github_release.sh
```

生成目录：

`runtime/github_release`

这个目录已经默认做好了发布整理：

- 保留 `app/`、`miniprogram/`、`scripts/`、`tests/`
- 保留 `Dockerfile`、`render.yaml`、`requirements.txt`、`wsgi.py`
- 保留 `.env.example`，不会带上你真实 `.env`
- 自动排除 `data/`、`runtime/`、`__pycache__/`、`.pyc`

如果你的 GitHub 仓库根目录就是这个 `runtime/github_release` 里的内容，那么 Render 就能直接从仓库根目录构建。

### GitHub 仓库根目录应包含哪些内容

你的 GitHub 仓库根目录最终应至少包含这些文件和目录：

```text
.dockerignore
.env.example
.gitignore
Dockerfile
README.md
app/
fof净值.py
miniprogram/
render.yaml
requirements.txt
scripts/
tests/
wsgi.py
```

更完整的发布版根目录文件清单可以直接对照：

```text
.dockerignore
.env.example
.gitignore
Dockerfile
README.md
app/__init__.py
app/analytics.py
app/bootstrap.py
app/config.py
app/db.py
app/mail_sync.py
app/nav_parser.py
app/product_names.py
app/static/sw.js
app/templates/index.html
app/templates/login.html
app/web.py
fof净值.py
miniprogram/app.js
miniprogram/app.json
miniprogram/app.wxss
miniprogram/pages/index/index.js
miniprogram/pages/index/index.wxml
miniprogram/pages/index/index.wxss
miniprogram/project.config.json
miniprogram/site.config.example.js
miniprogram/sitemap.json
miniprogram/utils/api.js
render.yaml
requirements.txt
scripts/export_github_release.sh
scripts/install_launch_agent.sh
scripts/install_local.sh
scripts/package_local.sh
scripts/render_create_service.sh
scripts/render_precheck.sh
scripts/render_validate.sh
scripts/run_server.py
scripts/start_local.sh
scripts/status_local.sh
scripts/stop_local.sh
scripts/uninstall_launch_agent.sh
tests/test_analytics.py
wsgi.py
```

### 当前 `linqiang1996/demo` 仓库还缺什么

我已经核对过你当前 `linqiang1996/demo` 仓库，它现在只有：

```text
._helloworld.py
.gitignore
README.md
helloworld.py
```

这意味着当前仓库还缺少：

- `Dockerfile`
- `render.yaml`
- `requirements.txt`
- `wsgi.py`
- `app/`
- `miniprogram/`
- `scripts/`
- `tests/`
- `fof净值.py`

所以当前 Render 固定公网服务虽然已经创建，但还不能构建成功。

### 最短上传步骤

你现在可以直接按这个顺序做：

1. 运行：

```bash
cd /Volumes/LEARN/VS_CODE/fof私募研究/fof净值跟踪
./scripts/export_github_release.sh
```

2. 打开生成目录：

`/Volumes/LEARN/VS_CODE/fof私募研究/fof净值跟踪/runtime/github_release`

3. 把这个目录里的全部内容上传或覆盖到 GitHub 仓库 `linqiang1996/demo` 的根目录

4. 上传完成后告诉我，我会继续直接帮你：
   - 重新触发 Render 部署
   - 检查构建日志
   - 验证固定网址是否可打开
   - 再决定要不要切到带持久化磁盘的正式模式

## 样例数据

项目会自动导入上级目录 `基金净值数据/` 中的 Excel 作为初始演示数据，所以即使还没接邮箱，网页也能先跑起来。
