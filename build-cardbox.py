from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

APP_NAME = "cardbox"
APP_VERSION = "v1.0.0"
ROOT_DIR = Path(__file__).resolve().parent
SOURCE_SCRIPT = ROOT_DIR / f"{APP_NAME}.py"
OUTPUT_DIR = ROOT_DIR / APP_NAME
ZIP_PATH = ROOT_DIR / f"{APP_NAME}-{APP_VERSION}.zip"
BUILD_DIR = ROOT_DIR / "build"
DIST_DIR = ROOT_DIR / "dist"
SPEC_PATH = ROOT_DIR / f"{APP_NAME}.spec"
RESOURCES_DIR = ROOT_DIR / "resources"
EXE_ICON = RESOURCES_DIR / "icons" / "app.ico"
WINDOW_ICON = RESOURCES_DIR / "icons" / "window.png"
PYINSTALLER_CACHE_DIR = ROOT_DIR / f".pyinstaller-cache-{APP_VERSION}"
APP_GENERATED_ICON = BUILD_DIR / "cardbox.ico"
LAUNCHER_SOURCE = ROOT_DIR / "cardbox-open.c"
LAUNCHER_RESOURCE = ROOT_DIR / "cardbox-open.rc"
LAUNCHER_EXE_NAME = "cardbox-open.exe"
LAUNCHER_ROOT_EXE = ROOT_DIR / LAUNCHER_EXE_NAME
LAUNCHER_ROOT_RES = ROOT_DIR / "cardbox-open.res"
LAUNCHER_ROOT_RES_OBJ = ROOT_DIR / "cardbox-open-resource.o"
LAUNCHER_GENERATED_ICON = DIST_DIR / "cardbox-open.ico"
LAUNCHER_GENERATED_RESOURCE = DIST_DIR / "cardbox-open-generated.rc"
RELEASE_TEXT_FILES = ["readme.txt", "LICENSE"]


def log(message: str) -> None:
    print(message, flush=True)


def fail(message: str, code: int = 1) -> None:
    log(f"[ERROR] {message}")
    raise SystemExit(code)


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_module(package_name: str, import_name: str | None = None) -> None:
    import_name = import_name or package_name
    try:
        __import__(import_name)
        return
    except Exception:
        pass

    log(f"[INFO] {package_name} was not found. Installing...")
    install = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", package_name])
    if install.returncode != 0:
        fail(f"Failed to install {package_name}.")


def ensure_pyinstaller() -> None:
    check = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if check.returncode == 0:
        return

    log("[INFO] PyInstaller was not found. Installing...")
    install = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"])
    if install.returncode != 0:
        fail("Failed to install PyInstaller.")


def find_source_script() -> Path:
    if SOURCE_SCRIPT.exists():
        return SOURCE_SCRIPT
    fail(f"Source script was not found: {SOURCE_SCRIPT.name}")
    raise AssertionError("unreachable")


def create_multisize_icon(output_path: Path, label: str) -> Path:
    """Create a multi-size ICO from resources/icons/app.ico for EXE embedding."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not ensure_optional_pillow():
        return EXE_ICON

    try:
        from PIL import Image

        image = Image.open(EXE_ICON)
        try:
            sizes = sorted(image.ico.sizes())  # type: ignore[attr-defined]
            if sizes:
                image = image.ico.getimage(sizes[-1])  # type: ignore[attr-defined]
            else:
                image.load()
        except Exception:
            image.load()

        image = image.convert("RGBA")
        icon_sizes = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]
        image.save(str(output_path), format="ICO", sizes=icon_sizes)
        if output_path.exists():
            log(f"[INFO] {label} multi-size icon: {output_path}")
            return output_path
    except Exception as exc:
        log(f"[WARN] Failed to create {label} multi-size icon: {exc}")

    return EXE_ICON


def build_exe(source_script: Path) -> None:
    env = os.environ.copy()
    env["PYINSTALLER_CONFIG_DIR"] = str(PYINSTALLER_CACHE_DIR)

    app_icon = create_multisize_icon(APP_GENERATED_ICON, "Main EXE")

    add_data_arg = f"{RESOURCES_DIR}{os.pathsep}resources"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        APP_NAME,
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        "--specpath",
        str(ROOT_DIR),
        "--icon",
        str(app_icon),
        "--add-data",
        add_data_arg,
        "--hidden-import",
        "cv2",
        "--collect-all",
        "cv2",
        str(source_script),
    ]

    log("[INFO] Building EXE with PyInstaller...")
    result = subprocess.run(command, env=env)
    if result.returncode != 0:
        fail("PyInstaller build failed.")



def ensure_optional_pillow() -> bool:
    try:
        __import__("PIL")
        return True
    except Exception:
        pass

    log("[INFO] Pillow was not found. Installing for launcher multi-size icon generation...")
    install = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "Pillow"])
    if install.returncode != 0:
        log("[WARN] Failed to install Pillow. Launcher will use the original ICO.")
        return False
    try:
        __import__("PIL")
        return True
    except Exception:
        log("[WARN] Pillow is still unavailable. Launcher will use the original ICO.")
        return False


def create_launcher_multisize_icon() -> Path:
    """Create a multi-size ICO for cardbox-open.exe."""
    return create_multisize_icon(LAUNCHER_GENERATED_ICON, "Launcher")


def write_launcher_resource(icon_path: Path) -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    icon_text = str(icon_path.resolve()).replace("\\", "\\\\")
    LAUNCHER_GENERATED_RESOURCE.write_text(f'IDI_ICON1 ICON "{icon_text}"\n', encoding="utf-8")
    return LAUNCHER_GENERATED_RESOURCE


def build_launcher() -> None:
    if not LAUNCHER_SOURCE.exists():
        log(f"[INFO] Launcher source was not found, skipping: {LAUNCHER_SOURCE.name}")
        return

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    launcher_exe = DIST_DIR / LAUNCHER_EXE_NAME
    compiler_cl = shutil.which("cl")
    compiler_gcc = shutil.which("gcc")
    rc_exe = shutil.which("rc")
    windres_exe = shutil.which("windres")
    launcher_res = DIST_DIR / "cardbox-open.res"
    launcher_res_obj = DIST_DIR / "cardbox-open-resource.o"
    launcher_icon = create_launcher_multisize_icon()
    launcher_resource = write_launcher_resource(launcher_icon)

    if compiler_cl:
        resource_arg: list[str] = []
        if launcher_resource.exists() and rc_exe:
            rc_result = subprocess.run([rc_exe, "/nologo", f"/fo{launcher_res}", str(launcher_resource)])
            if rc_result.returncode == 0 and launcher_res.exists():
                resource_arg = [str(launcher_res)]
            else:
                log("[WARN] Launcher resource compile failed. Launcher icon may be missing.")
        elif launcher_resource.exists():
            log("[WARN] rc.exe was not found. Launcher icon may be missing.")
        command = [
            compiler_cl,
            "/nologo",
            "/O2",
            "/DUNICODE",
            "/D_UNICODE",
            f"/Fe:{launcher_exe}",
            str(LAUNCHER_SOURCE),
            *resource_arg,
            "shell32.lib",
            "user32.lib",
            "/link",
            "/SUBSYSTEM:WINDOWS",
        ]
    elif compiler_gcc:
        resource_arg = []
        if launcher_resource.exists() and windres_exe:
            rc_result = subprocess.run([windres_exe, str(launcher_resource), str(launcher_res_obj)])
            if rc_result.returncode == 0 and launcher_res_obj.exists():
                resource_arg = [str(launcher_res_obj)]
            else:
                log("[WARN] Launcher resource compile failed. Launcher icon may be missing.")
        elif launcher_resource.exists():
            log("[WARN] windres was not found. Launcher icon may be missing.")
        command = [
            compiler_gcc,
            "-O2",
            "-municode",
            "-mwindows",
            "-o",
            str(launcher_exe),
            str(LAUNCHER_SOURCE),
            *resource_arg,
            "-lshell32",
            "-luser32",
        ]
    else:
        log("[WARN] cl/gcc was not found. Launcher EXE will not be included in the release ZIP.")
        log("[WARN] You can build it manually with build-cardbox-open.bat.")
        return

    log("[INFO] Building lightweight launcher...")
    result = subprocess.run(command)
    if result.returncode != 0 or not launcher_exe.exists():
        log("[WARN] Launcher build failed. Release ZIP will continue without cardbox-open.exe.")


def copy_release_text_files() -> None:
    """Copy plain text files that should be bundled next to the EXE."""
    for filename in RELEASE_TEXT_FILES:
        source = ROOT_DIR / filename
        if source.exists() and source.is_file():
            shutil.copy2(source, OUTPUT_DIR / filename)
            log(f"[INFO] Included {filename} in release ZIP.")
        else:
            log(f"[WARN] {filename} was not found. Release ZIP will continue without it.")


def create_zip() -> None:
    exe_path = DIST_DIR / f"{APP_NAME}.exe"
    if not exe_path.exists():
        fail(f"EXE was not created: {exe_path}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe_path, OUTPUT_DIR / f"{APP_NAME}.exe")
    launcher_exe = DIST_DIR / LAUNCHER_EXE_NAME
    if launcher_exe.exists():
        shutil.copy2(launcher_exe, OUTPUT_DIR / LAUNCHER_EXE_NAME)

    copy_release_text_files()

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for file_path in sorted(OUTPUT_DIR.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(ROOT_DIR))


def clean_generated_build_files_after_zip() -> None:
    for path in [
        OUTPUT_DIR,
        BUILD_DIR,
        DIST_DIR,
        SPEC_PATH,
        PYINSTALLER_CACHE_DIR,
        LAUNCHER_ROOT_EXE,
        LAUNCHER_ROOT_RES,
        LAUNCHER_ROOT_RES_OBJ,
    ]:
        remove_path(path)


def main() -> int:
    os.chdir(ROOT_DIR)
    log("")
    log("========================================")
    log(f"CardBox build {APP_VERSION}")
    log("========================================")
    log("")
    log(f"[INFO] Python: {sys.executable}")
    log(f"[INFO] Python version: {sys.version.split()[0]}")

    source_script = find_source_script()
    log(f"[INFO] Source: {source_script}")

    if not EXE_ICON.exists():
        fail(f"EXE icon was not found: {EXE_ICON}")
    if not WINDOW_ICON.exists():
        fail(f"Window icon was not found: {WINDOW_ICON}")
    if not RESOURCES_DIR.exists():
        fail(f"Resources folder was not found: {RESOURCES_DIR}")

    log(f"[INFO] EXE icon: {EXE_ICON}")
    log(f"[INFO] Window icon: {WINDOW_ICON}")
    log(f"[INFO] EXE icon SHA256: {sha256(EXE_ICON)}")

    ensure_pyinstaller()
    ensure_module("opencv-python", "cv2")

    log("")
    log("[INFO] Cleaning old build files...")
    for path in [
        OUTPUT_DIR,
        ZIP_PATH,
        BUILD_DIR,
        DIST_DIR,
        SPEC_PATH,
        PYINSTALLER_CACHE_DIR,
        LAUNCHER_ROOT_EXE,
        LAUNCHER_ROOT_RES,
        LAUNCHER_ROOT_RES_OBJ,
    ]:
        remove_path(path)

    log("")
    build_exe(source_script)
    build_launcher()

    log("")
    log("[INFO] Creating ZIP...")
    create_zip()

    log("")
    log("[INFO] Cleaning generated build files after ZIP creation...")
    clean_generated_build_files_after_zip()

    log("")
    log("========================================")
    log("Build complete")
    log("========================================")
    log(f"ZIP: {ZIP_PATH}")
    log("Contents:")
    try:
        with zipfile.ZipFile(ZIP_PATH) as zf:
            for name in sorted(zf.namelist()):
                log(f"  {name}")
    except Exception:
        log(f"  {APP_NAME}/{APP_NAME}.exe")
    log("")
    log("Generated build folders were cleaned. Only the ZIP is left as the build output.")
    log("If Explorer still shows an old icon, extract the ZIP to a new folder.")
    log("Windows may cache icons by path and exe name.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
