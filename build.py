import shutil
import os
import subprocess

APP_NAME = "AugerSmapleFeed"
SPEC_FILE = "AugerSmapleFeed.spec"


def get_version(path=None):
    if path is None:
        with open("version.txt") as f:
            return f.read().strip()
    else:
        with open(os.path.join(path, "version.txt")) as f:
            return f.read().strip()


def create_version_file(version: str, filename="file_version_info.txt"):
    content = f"""
# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({version.replace('.', ',')}, 0),
    prodvers=({version.replace('.', ',')}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'ВМК-Оптоэлектроника'),
         StringStruct('FileDescription', '{APP_NAME}'),
         StringStruct('FileVersion', '{version}'),
         StringStruct('InternalName', '{APP_NAME}'),
         StringStruct('LegalCopyright', '© ВМК-Оптоэлектроника 2025'),
         StringStruct('OriginalFilename', '{APP_NAME}.exe'),
         StringStruct('ProductName', '{APP_NAME}'),
         StringStruct('ProductVersion', '{version}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    return filename


def create_common_version_file(ver_1: str, ver_2: str, dirname):
    full_path = os.path.join(dirname, "version.txt")
    content = f"exporExcel v.{ver_1}\nexporExcelConfigurator v.{ver_2}"
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    return full_path


def copytree_merge(src, dst):
    """Копирование src → dst с заменой (поверх существующего)."""
    os.makedirs(dst, exist_ok=True)
    for root, dirs, files in os.walk(src):
        rel_path = os.path.relpath(root, src)
        target_dir = os.path.join(dst, rel_path) if rel_path != "." else dst
        os.makedirs(target_dir, exist_ok=True)
        for file in files:
            shutil.copy2(os.path.join(root, file), os.path.join(target_dir, file))


def git_push(version: str):
    try:
        # Проверяем, есть ли изменения
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():  # если есть изменения
            subprocess.run(["git", "add", "."], check=True)
            subprocess.run(["git", "commit", "-m", f"Release v{version}"], check=True)
            subprocess.run(["git", "push"], check=True)
            print("✅ Изменения закоммичены и запушены")
        else:
            print("ℹ️ Нет изменений для коммита, пропускаем commit/push")

        # В любом случае создаём тег и пушим его
        subprocess.run(["git", "tag", f"v{version}"], check=True)
        subprocess.run(["git", "push", "--tags"], check=True)
        print(f"🏷 Тег v{version} создан и запушен")

    except subprocess.CalledProcessError as e:
        print("⚠️ Ошибка при git операции:", e)


def build():
    version = get_version()
    dist_dir = os.path.join("dist", f"v{version}")
    latest_dir = os.path.join("dist", "latest")

    # Удалим build/dist, чтобы не было мусора
    if os.path.exists("build"):
        shutil.rmtree("build")
    if os.path.exists("dist"):
        shutil.rmtree("dist")

    # Сгенерируем файл с версией
    create_version_file(version)

    # Собираем по .spec
    subprocess.run(["pyinstaller", SPEC_FILE], check=True)

    # Создаем папку для этой версии
    os.makedirs(dist_dir, exist_ok=True)

    # Перемещаем exe (он будет в dist/AugerSmapleFeed v*.*.*/AugerSmapleFeed.exe)
    exe_path = os.path.join("dist", f"{APP_NAME}.exe")
    shutil.move(exe_path, os.path.join(dist_dir, f"{APP_NAME}.exe"))
    # Перемещаем _internal (он будет в dist/ExportAtomExcel v*.*.*/_internal)
    # internal_path = os.path.join("dist", APP_NAME, "_internal")
    # shutil.move(internal_path, os.path.join(dist_dir, "_internal"))

    # Обновляем latest
    if os.path.exists(latest_dir):
        shutil.rmtree(latest_dir)
    shutil.copytree(dist_dir, latest_dir)

    print(f"\n✅ Сборка завершена: {dist_dir}")
    print(f"📌 Последняя версия обновлена: {latest_dir}")

    # Заливаем в git
    git_push(version)


if __name__ == "__main__":
    build()
