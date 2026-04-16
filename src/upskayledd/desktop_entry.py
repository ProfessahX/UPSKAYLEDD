from __future__ import annotations

import sys

from upskayledd.core.paths import repo_root


def _import_desktop_runner():
    try:
        from pyside_app.window import run_desktop_app

        return run_desktop_app
    except ModuleNotFoundError:
        desktop_apps = repo_root() / "apps" / "desktop"
        desktop_apps_text = str(desktop_apps)
        if desktop_apps_text not in sys.path:
            sys.path.insert(0, desktop_apps_text)
        from pyside_app.window import run_desktop_app

        return run_desktop_app


def main(argv: list[str] | None = None) -> int:
    return int(_import_desktop_runner()(argv))


if __name__ == "__main__":
    raise SystemExit(main())
