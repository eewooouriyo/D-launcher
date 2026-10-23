from datetime import datetime
import json
import os
import subprocess
import sys
import traceback
import tkinter as tk
from tkinter import filedialog

CONFIG_FILE = "config.json"
LOGS_DIR = "logs"

if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file_path = os.path.join(LOGS_DIR, f"log_{timestamp}.txt")


def log(msg):
    """Imprime en consola y guarda en el archivo físico."""
    formatted_msg = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(formatted_msg)
    try:
        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write(formatted_msg + "\n")
    except Exception as e:
        print(f"[ERROR LOGGER] No se pudo escribir en el log: {e}")


def load_config():
    if not os.path.exists(CONFIG_FILE):
        log(f"ERROR CRÍTICO: No se encontró el archivo {CONFIG_FILE}.")
        sys.exit(1)

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as error:
        log(f"ERROR CRÍTICO: config.json está mal formado:\n{error}")
        sys.exit(1)


def save_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=4, ensure_ascii=False)


def expand_path(path):
    return os.path.abspath(os.path.expandvars(os.path.expanduser(path)))


def choose_directory():
    selected = filedialog.askdirectory(
        title="Selecciona tu directorio de Minecraft"
    )

    if selected:
        config["minecraft"]["directory"] = selected
        save_config()
        directory_label.config(text=f"Directorio:\n{selected}")
        log(f"Nuevo directorio guardado: {selected}")


def collect_libraries_from_json(json_path, minecraft_dir):
    """Recorre un JSON de versión o Forge y extrae la ruta de sus librerías."""
    libs = []
    if not os.path.exists(json_path):
        return libs

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for lib in data.get("libraries", []):
            downloads = lib.get("downloads", {})
            artifact = downloads.get("artifact", {})
            
            if "path" in artifact:
                jar_path = os.path.join(minecraft_dir, "libraries", artifact["path"])
                if os.path.exists(jar_path):
                    libs.append(jar_path)
            else:
                lib_name = lib.get("name")
                if lib_name:
                    parts = lib_name.split(":")
                    if len(parts) >= 3:
                        domain, name_lib, version_lib = parts[0], parts[1], parts[2]
                        rel_path = os.path.join(
                            *domain.split("."),
                            name_lib,
                            version_lib,
                            f"{name_lib}-{version_lib}.jar"
                        )
                        jar_path = os.path.join(minecraft_dir, "libraries", rel_path)
                        if os.path.exists(jar_path):
                            libs.append(jar_path)

    except Exception as e:
        log(f"Error al procesar librerías de {json_path}: {e}")

    return libs


def build_classpath(minecraft_dir, forge_json_path, vanilla_json_path):
    """Construye el Classpath uniendo Forge + Vainilla (sin duplicar el JAR base)."""
    cp_set = set()

    # 1. Librerías de Forge
    for jar in collect_libraries_from_json(forge_json_path, minecraft_dir):
        cp_set.add(jar)

    # 2. Librerías de Vainilla
    for jar in collect_libraries_from_json(vanilla_json_path, minecraft_dir):
        cp_set.add(jar)

    # ELIMINAMOS el bloque que agregaba '1.20.1.jar' manualmente para evitar duplicación de módulos com.mojang.blaze3d

    return os.pathsep.join(list(cp_set))

def encontrar_java_17():
# Carpetas típicas donde se instalan las versiones de Java 17
    rutas_base = [
        r"C:\Program Files\Eclipse Adoptium",
        r"C:\Program Files\Java",
        r"C:\Program Files\Amazon Corretto",
        r"C:\Program Files (x86)\Java"
    ]
    
    for base in rutas_base:
        if os.path.exists(base):
            for carpeta in os.listdir(base):
                # Busca cualquier carpeta que empiece con jdk-17 o jdk17
                if "17" in carpeta:
                    java_exe = os.path.join(base, carpeta, "bin", "java.exe")
                    if os.path.exists(java_exe):
                        return java_exe
                       
    # Si no encuentra ninguna versión 17 específica, usa el java del sistema
#    return "java"

# Tu script usará esto automáticamente:
JAVA_EXE_PATH = encontrar_java_17()

def launch_minecraft():
    log("Iniciando proceso de lanzamiento...")
    minecraft = config["minecraft"]
    profile = config["profile"]

    directory = expand_path(minecraft["directory"])
    forge_profile = minecraft.get("forge_profile", "1.20.1-forge-47.4.10")
    vanilla_version = minecraft.get("version", "1.20.1")
    username = profile.get("username", "fandedanoarsel")
    user_uuid = profile.get("uuid", "0004c61756e6468657246656e6978000")
    min_ram = minecraft.get("min_ram", "1G")
    max_ram = minecraft.get("max_ram", "3G")

    if not os.path.isdir(directory):
        log(f"ERROR: El directorio especificado no existe: {directory}")
        return

    forge_json_path = os.path.join(directory, "versions", forge_profile, f"{forge_profile}.json")
    vanilla_json_path = os.path.join(directory, "versions", vanilla_version, f"{vanilla_version}.json")

    if not os.path.exists(forge_json_path):
        log(f"ERROR CRÍTICO: No existe el perfil Forge en: {forge_json_path}")
        return

    try:
        log("Construyendo Classpath unificado...")
        classpath = build_classpath(directory, forge_json_path, vanilla_json_path)
        libs_dir = os.path.join(directory, "libraries")
        assets_dir = os.path.join(directory, "assets")

        with open(forge_json_path, "r", encoding="utf-8") as f:
            forge_data = json.load(f)

        main_class = forge_data.get("mainClass", "cpw.mods.bootstraplauncher.BootstrapLauncher")
        raw_jvm = forge_data.get("arguments", {}).get("jvm", [])
        raw_game = forge_data.get("arguments", {}).get("game", [])

        processed_jvm = []
        for arg in raw_jvm:
            arg_str = str(arg)
            arg_str = arg_str.replace("${library_directory}", libs_dir)
            arg_str = arg_str.replace("${classpath_separator}", os.pathsep)
            arg_str = arg_str.replace("${version_name}", forge_profile)
            processed_jvm.append(arg_str)

        # Ruta de los nativos declarada limpiamente antes de armar la lista cmd
        natives_path = r"C:\Users\DanielValentinoRamos\AppData\Roaming\.minecraft\versions\1.20.1-forge-47.4.10\1.20.1-forge-47.4.10-natives-443178511403800"

        cmd = [
            "java",
            f"-Dfml.earlywindow=false",
            f"-Xms{min_ram}",
            f"-Xmx{max_ram}",
            f"-Djava.library.path={natives_path}",
            f"-Dorg.lwjgl.librarypath={natives_path}"
        ] + processed_jvm + [
            "-cp", classpath,
            main_class,
            "--username", username,
            "--version", forge_profile,
            "--gameDir", directory,
            "--assetsDir", assets_dir,
            "--assetIndex", "5",
            "--uuid", user_uuid,
            "--accessToken", "0",
            "--clientId", "NjI5ZjZhNjItMzg2OS00YWFiLWFlNmItODhiYzc1YTM4YWY4",
            "--xuid", "9999999999999999",
            "--userType", "legacy",
            "--versionType", "release"
        ] + raw_game

        log("Comando generado con éxito. Ejecutando Java...")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        root.withdraw()
        log("=== INICIO DE LOGS DE MINECRAFT ===")

        for line in iter(process.stdout.readline, ''):
            if line:
                log(f"[GAME] {line.strip()}")

        process.wait()
        log(f"El proceso de Minecraft finalizó con código de salida: {process.returncode}")

    except Exception as e:
        log("=================== DETALLE DEL ERROR ===================")
        log(f"Ocurrió una excepción de tipo {type(e).__name__}: {e}")
        log("Seguimiento completo de la pila (Traceback):")
        log(traceback.format_exc())
        log("========================================================")

    finally:
        log("Restaurando interfaz del Launcher...")
        root.deiconify()


# --------------------------------------------------
# CONFIGURACIÓN E INICIALIZACIÓN
# --------------------------------------------------

log(f"Archivo de registro creado en: {log_file_path}")
log("Cargando archivo de configuración...")
config = load_config()

launcher_name = config["launcher"]["name"]
launcher_version = config["launcher"]["version"]

username = config["profile"]["username"]
minecraft_version = config["minecraft"]["version"]
loader = config["minecraft"]["loader"]
min_ram = config["minecraft"]["min_ram"]
max_ram = config["minecraft"]["max_ram"]

minecraft_directory = expand_path(config["minecraft"]["directory"])


# --------------------------------------------------
# INTERFAZ GRÁFICA (Tkinter)
# --------------------------------------------------

root = tk.Tk()
root.title(f"{launcher_name} v{launcher_version}")
root.geometry("520x420")
root.resizable(False, False)

title = tk.Label(root, text=launcher_name, font=("Arial", 26, "bold"))
title.pack(pady=(25, 5))

subtitle = tk.Label(root, text=f"Launcher v{launcher_version}")
subtitle.pack()

info_frame = tk.Frame(root)
info_frame.pack(pady=25)

tk.Label(info_frame, text=f"Jugador: {username}", font=("Arial", 12, "bold")).pack(anchor="w", pady=3)
tk.Label(info_frame, text=f"Minecraft: {minecraft_version}", font=("Arial", 12, "bold")).pack(anchor="w", pady=3)
tk.Label(info_frame, text=f"Loader: {loader}", font=("Arial", 12, "bold")).pack(anchor="w", pady=3)
tk.Label(info_frame, text=f"RAM: {min_ram} - {max_ram}", font=("Arial", 12, "bold")).pack(anchor="w", pady=3)

directory_label = tk.Label(root, text=f"Directorio:\n{minecraft_directory}", wraplength=470)
directory_label.pack(pady=10)

button_frame = tk.Frame(root)
button_frame.pack(pady=15)

play_button = tk.Button(
    button_frame,
    text="JUGAR",
    font=("Arial", 16, "bold"),
    width=18,
    height=2,
    command=launch_minecraft
)
play_button.grid(row=0, column=0, padx=5)

directory_button = tk.Button(
    button_frame,
    text="Cambiar directorio",
    width=18,
    command=choose_directory
)
directory_button.grid(row=1, column=0, pady=10)

log("Launcher listo. Esperando interacción del usuario.")
root.mainloop()