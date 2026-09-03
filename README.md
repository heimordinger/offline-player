# 离线播放器

离线 ADV 播放器。**程序代码**在仓库根目录；**游戏资源**统一放在 `data/`（默认不上传 Git）。

| 路径 | 说明 |
|------|------|
| `games.json` | 游戏列表与各游戏 `root` |
| `data/` | 全部资源（见 `data/README.md`） |
| `settings.json` | 窗口等本地配置（不上传；可从 `settings.example.json` 复制） |

界面层级：选择游戏 → 分类 → 场景列表 → 播放。

## 目录结构

```
离线播放器/
├── app/                 # 新版客户端（PySide6）
├── legacy/              # 旧版 pygame
├── tools/               # 维护脚本
├── data/                # 本地资源（gitignore）
├── games.json
├── project_paths.py
├── run_app.py
└── start.bat
```

## 启动

```bat
start.bat           # 新版 PySide6
py -3.13 run_app.py # 同上，保留控制台输出
start_legacy.bat    # 旧版 pygame（功能完整）
```

依赖安装：

```bat
pip install -r requirements.txt
```

## 导入 Telegram 导出

```bat
py -3.13 tools\import_telegram_export.py
```

将 `ChatExport_*` 放在项目根目录；仅导入项目中尚不存在的 JSON，新 JSON 会出现在「最新更新」。

## 孤儿的工作（Minashigo ADV）

从 MinashigoViewer 迁移 Ren'Py 台本，按**角色 ID**分类，场景卡片显示**日文标签**（角色名 · 场景类型）。

```bat
py -3.13 tools\migrate_minashigo.py
py -3.13 run_app.py
```

资源默认**硬链接**到 Viewer 的 CG/语音（不占双倍空间）。Telegram 录屏在独立游戏区 **孤儿的工作 · 录屏**。

## 孤儿的工作 · Telegram 录屏

```bat
py -3.13 tools\build_orphan_catalog.py
```


比官方「导出聊天记录」更快。同一相册（`grouped_id`）或同一条消息的图/视频归为一组，用消息里的 `#标签` 建分类索引。

```bat
copy tools\tg_config.example.json tools\tg_config.json
rem 若 my.telegram.org 一直 ERROR，example 里已含 Telegram Desktop 官方凭证，可直接用
rem 按需改 proxy 端口（你梯子的 SOCKS5 端口，常见 7890 / 1080）
py -3.13 -m pip install telethon PySocks
py -3.13 tools\tg_download_classify.py
```

输出在 `tg_library/`：
- `files/<group_key>/`：一组媒体 + `meta.json`（标签、message_ids、caption）
- `by_tag/<标签>/`：按 `#塔尔及玻斯` 等分类索引
- `catalog.json`：总目录

若官方导出已下完一部分，可只做归类（不联网）：

```bat
py -3.13 tools\tg_download_classify.py --from-export ChatExport_2026-08-24
```

## 导出 SillyTavern 角色卡 / 世界书

从已下载的台本按分类（角色）导出，需先有 `category_names.json` 与 `resource/` 内文本：

```bat
py -3.13 tools\export_sillytavern.py --mode both
py -3.13 tools\export_sillytavern.py --mode card --category 1029
py -3.13 tools\export_sillytavern.py --per-name --mode both
```

输出目录默认 `sillytavern_export/`：
- `cards/`：`chara_card_v2` 角色卡（含嵌入 `character_book`）
- `worldbooks/`：可单独导入的 World Info JSON

在 SillyTavern 中：优先导入 `cards/*.png`（自带头像与数据）；纯 JSON 需手动上传头像。

指定自定义头像：`--avatar 路径/to/image.png`

## 打包（legacy）

```bat
package.bat
```

生成 `DeepOne.exe`（基于 `legacy/do_main.py`）。
