# 离线播放器

离线 ADV / 录屏播放器（PySide6）。**程序代码**在仓库根目录；**游戏资源**统一放在 `data/`（默认不上传 Git）。

当前版本：**v1.0.2**

| 路径 | 说明 |
|------|------|
| `games.json` | 游戏列表与各游戏 `root` / `kind` |
| `data/` | 全部资源（见 `data/README.md`） |
| `settings.json` | 窗口等本地配置（不上传；可从 `settings.example.json` 复制） |
| `VERSION` | 程序版本号 |

界面层级：选择游戏 → 分类 → 场景列表 → 播放。

## 更新说明

### v1.0.2

- 窗口标题统一为「离线播放器」
- 游戏选择页可选「双端 · 局域网」入口（本机若有对应模块则可用）
- 设置读写辅助（`save_settings` / `update_settings`）
- ADV 剧本文本下载超时缩短，避免 CDN 不通时长时间卡住
- 依赖增加 `qrcode[pil]`；补充 Windows 发布说明 `release/README.txt`

### v1.0.1

- 多游戏适配器（`adv` / `renpy` / `telegram` / `purchased`）
- Ren'Py 离线包导入
- 分类卡面副标题等界面修正

## 从 GitHub 获取

- 源码：https://github.com/heimordinger/offline-player
- Release：https://github.com/heimordinger/offline-player/releases

Windows 发布包解压后双击 `OfflinePlayer.exe`。增量更新请覆盖 `offline-player-update.zip` 内容，**不要覆盖** `data/`、`settings.json`、`runtime/`、`_deps/`（详见 `release/README.txt`）。

## 目录结构

```
离线播放器/
├── app/                 # 新版客户端（PySide6）
│   └── core/adapters/   # 多游戏适配器（按 kind）
├── legacy/              # 旧版 pygame
├── tools/               # 维护脚本
├── data/                # 本地资源（gitignore）
├── release/             # 发布说明
├── games.json
├── VERSION
├── project_paths.py
├── run_app.py
└── start.bat
```

## 多游戏适配器（万能壳）

壳只负责：选游戏 → 分类 → 列表 → 播放。每种内容源是一个 **adapter**（`app/core/adapters/`），由 `games.json` 的 `kind` 选择：

| kind | 适配器 | 说明 |
|------|--------|------|
| `adv`（默认） | ADV 台本 | DeepOne / 孤儿等：JSON + resource，可节拍播放 |
| `renpy` | Ren'Py 离线包 | 导入后同 ADV；见下方导入命令 |
| `telegram` | Telegram 录屏 | ChatExport 图/视频 |
| `purchased` | 自购库 | 本地文件夹浏览 |

新增游戏优先复用已有 kind；新形态再加适配器文件并注册到 `registry.py`。

### ADV 播放要点

- **边下边看**：剧本就绪即可开播，其余资源后台按台本进度优先下载
- **动态标签**：场景资源含 mp4 时，二级列表显示「动态」
- **动态 CG 预热**：临近段落预缓冲短 mp4，未就绪时会暂缓点击/快进

### 导入 Ren'Py 包

支持：

1. **DeepOne 系**（`game/json` + `game/resource`，与本播放器格式一致）
2. **孤儿 Viewer 系**（`game/scripts/scene_*.rpy` → 转 ADV 台本）

```bat
py -3.13 tools\import_renpy_pack.py --pack "D:\path\to\DeepOne（renpy）" --detect-only
py -3.13 tools\import_renpy_pack.py --pack "D:\path\to\DeepOne（renpy）" --game-id deepone_renpy --apply
py -3.13 tools\import_renpy_pack.py --pack "D:\path\to\DeepOne（renpy）" --mount --apply
```

`--apply` 会导入（默认硬链接）并写入 `games.json`；`--mount` 不复制，直接指向包内 `game/`。

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

从 MinashigoViewer 迁移 Ren'Py 台本到 `data/orphan_order`，按**角色 ID**分类，场景卡片显示**日文标签**（角色名 · 场景类型）。

```bat
py -3.13 tools\migrate_minashigo.py
py -3.13 run_app.py
```

默认 Viewer 路径：`..\孤儿离线\MinashigoViewer-1.2-pc\MinashigoViewer-1.2-pc`  
资源默认**硬链接**到 Viewer 的 CG/语音（不占双倍空间）。若换过盘符/目录或发现缺图缺语音：

```bat
py -3.13 tools\repair_orphan_assets.py
```

只补缺失文件，不重写台本。仍异常时可再跑全量 `tools\migrate_minashigo.py`（已有文件会跳过）。

Telegram 录屏在独立游戏区 **孤儿的工作 · 录屏**。

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

生成基于 `legacy/do_main.py` 的旧版 exe。新版 Windows 包请使用仓库 Release 中的 `OfflinePlayer.exe` 方案。
