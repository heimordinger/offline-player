# 本地资源目录（勿提交到 Git）

把游戏资源放在本目录。仓库只含程序代码；`data/` 已在 `.gitignore` 中忽略。

## 建议结构

```
data/
  deepone_one/          # Deepone One
    json/
    resource/
    episode/
    custom_videos/
  orphan_order/         # 孤儿的工作 · ADV
    json/
    resource/
    episode/
    videos/
  orphan_recordings/    # 孤儿的工作 · Telegram 录屏
    json/ resource/ episode/ videos/
    catalog.json
    ChatExport_…/       # 若有导出目录
  自购/                 # 自购库：作者/作品
  sillytavern_export/   # 可选
```

路径由项目根目录的 `games.json` 配置（`root` 指向上述子目录）。

朋友克隆仓库后：自行准备 `data/`，或从你这边拷贝整份 `data` 文件夹即可运行。
