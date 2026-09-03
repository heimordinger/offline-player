# -*- coding: utf-8 -*-
"""DeepOneRE 新版入口（PySide6）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from project_paths import PROJECT_ROOT, ensure_data_dirs, load_settings

os.chdir(PROJECT_ROOT)
ensure_data_dirs()


def main() -> int:
    from PySide6.QtWidgets import QApplication, QMessageBox

    from app.core.startup import StartupWorker
    from app.ui.main_window import MainWindow
    from app.ui.splash_screen import SplashScreen

    app = QApplication(sys.argv)
    app.setApplicationName("DeepOneRE")

    settings = load_settings()
    w = int(settings.get("窗口宽度", 1300))
    h = int(settings.get("窗口高度", 960))

    splash = SplashScreen(w, h)
    splash.show()
    app.processEvents()

    worker = StartupWorker()
    main_window: MainWindow | None = None

    def on_progress(phase: str, progress: float, detail: str, sub_detail: str = ""):
        splash.set_progress(phase, progress, detail, sub_detail)

    def on_ready(result):
        nonlocal main_window
        main_window = MainWindow(result)
        main_window.show()
        splash.close_splash()

    def on_failed(msg: str):
        splash.set_progress("启动失败", 1.0, msg, "请查看控制台错误信息")
        QMessageBox.critical(splash, "启动失败", msg)

    worker.progress.connect(on_progress)
    worker.finished_ok.connect(on_ready)
    worker.failed.connect(on_failed)
    worker.start()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
