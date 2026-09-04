离线播放器 · Windows 发布包
========================

1. 解压 offline-player-win64.zip
2. 双击 OfflinePlayer.exe

目录说明
--------
OfflinePlayer.exe   轻量入口（转到 runtime\python.exe）
runtime\            嵌入式 Python（完整标准库）
_deps\              PySide6 / Shiboken
run_app.py          程序入口
app\                主程序代码
games.json
data\               游戏资源（自行准备，更新包不会覆盖）

后续更新
--------
解压 offline-player-update.zip 覆盖到本目录即可。
保留 OfflinePlayer.exe、runtime\、_deps\、data\、settings.json。

源码：https://github.com/heimordinger/offline-player
