# Kimi 备用站 · 提示词

> 用途：万一教室机本地环境出问题，用公网静态站兜底放讲稿（**只放讲稿，不放现场演示平台**）。

> **已部署**：https://unn6vtiejhyvk.ok.kimi.link/#1（Kimi 托管，按流量计费；2026-11-07 夜验证 200，标题正确）
> 仓库已就绪：`https://github.com/TonaliNoHitsuzi/cyber-pulse`，讲稿在 `slides/`（已推送，116 页按钮已改为静态提示）。

把下面整段复制给 Kimi：

```text
你是我的部署助手。帮我把一个纯静态网页讲稿部署成临时公网站点，作为明天下午课程汇报的备用方案。只部署讲稿，不部署实时演示平台。

仓库：https://github.com/TonaliNoHitsuzi/cyber-pulse
站点根目录：仓库里的 slides/（里面有 index.html）

任务：
1. clone 仓库，确认 slides/index.html 存在。
2. 用任意静态 HTTP 服务把 slides/ 作为站点根发布（例如 python -m http.server 8080 --directory slides）。不能用 file:// 打开：页面是 ES Module + fetch，必须走 HTTP。
3. 给我一个 https 公网地址，并保证从现在到明天 18:00（北京时间）持续可访问。
4. 部署后自测并逐项回报：
   - 首页能打开；
   - 深链 <你的地址>/#1、/#57、/#115、/#116 能直达对应页；
   - 翻页正常：→ / ← / 空格 / 单击 / 滚轮；
   - 图表、环形图、视频能显示（资源都在仓库里，无外链依赖）；
   - 用手机浏览器也能打开。
5. 第 116 页按钮已改成静态提示「现场演示仅限本地环境」，不要恢复成 /demo/launch 链接，也不要改其他页面。
6. 把网址、失效时间、重启命令发给我；如果服务重启，尽量保持同一网址。

如果临时服务器给不了公网地址，改用 GitHub Pages：仓库 Settings → Pages，Source 选 master / (root)，地址是 https://tonalinohitsuzi.github.io/cyber-pulse/slides/ （仓库已公开）。

注意：路径里有中文，保持原样；页面之间用相对路径，站点根必须是 index.html 所在目录。
```

## 部署后自己验收（3 分钟）

1. 手机 4G（不连教室 Wi-Fi）打开备用站，能翻到 #116。
2. 点 #116 的按钮位置，确认不会跳 404（应显示「现场演示仅限本地环境」，不是链接）。
3. 随机抽 #57、#93、#115 三页，确认图表/环形图正常。
4. 记下网址和失效时间，写进上场前的检查清单。

## 已知边界

- 备用站只有讲稿；现场演示（8100）依赖教室机 + 板子 + 手机，不上公网。
- 静态站不需要 Node/Python，GitHub Pages 也够用；Kimi 的临时服务只是更快。
