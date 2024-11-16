import threading
import psutil
import pynvml
import wmi
import cpuinfo
import platform
import socket
import pythoncom
import time
from datetime import datetime
from collections import deque
import mysql.connector
from telegram import Bot

# Configuración
LOG_FILE = "activity.log"
TELEGRAM_TOKEN = "TU_TELEGRAM_TOKEN"
TELEGRAM_CHAT_ID = "TU_CHAT_ID"
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "system_monitor"
}
MAX_LOG_ENTRIES = 5

# Inicialización
lock = threading.Lock()
log_deque = deque(maxlen=MAX_LOG_ENTRIES)
bot = Bot(token=TELEGRAM_TOKEN)

# Crear base de datos y tabla
def setup_database():
    conn = mysql.connector.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"]
    )
    cursor = conn.cursor()

    # Crear la base de datos si no existe
    cursor.execute("CREATE DATABASE IF NOT EXISTS system_monitor")
    conn.commit()

    # Conectarse a la base de datos creada
    conn.database = "system_monitor"

    # Crear la tabla si no existe
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            timestamp DATETIME,
            cpu_temp FLOAT,
            gpu_temp FLOAT,
            memory_usage FLOAT,
            ip_address VARCHAR(50),
            tasks TEXT
        )
    """)
    conn.commit()
    conn.close()

# Obtener dirección IP
def get_ip():
    return socket.gethostbyname(socket.gethostname())

# Escribir en archivo log
def write_log(message):
    with lock:
        log_deque.append(message)
        with open(LOG_FILE, "w") as log_file:
            log_file.write("\n".join(log_deque))

# Insertar en MySQL
def insert_mysql(timestamp, cpu_temp, gpu_temp, memory_usage, ip, tasks):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    query = """
        INSERT INTO system_logs (timestamp, cpu_temp, gpu_temp, memory_usage, ip_address, tasks)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    cursor.execute(query, (timestamp, cpu_temp, gpu_temp, memory_usage, ip, ", ".join(tasks)))
    conn.commit()
    conn.close()

# Enviar mensaje por Telegram
def send_telegram_message(message):
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

# Obtener temperatura de CPU
def get_cpu_temperature():
    try:
        system_os = platform.system()
        if system_os == "Windows":
            # Usa WMI o py-cpuinfo para obtener la temperatura
            w = wmi.WMI(namespace="root\\wmi")
            temperature_info = w.MSAcpi_ThermalZoneTemperature()[0]
            return (temperature_info.CurrentTemperature / 10) - 273.15
        elif system_os == "Linux":
            temps = psutil.sensors_temperatures()
            if "coretemp" in temps:
                return temps["coretemp"][0].current
        return None
    except Exception as e:
        print(f"Error obteniendo temperatura de CPU: {e}")
        return None

# Obtener temperatura de GPU (NVIDIA)
def get_gpu_temperature():
    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        pynvml.nvmlShutdown()
        return temp
    except Exception as e:
        print(f"Error obteniendo temperatura de GPU: {e}")
        return None

# Monitor de CPU
def monitor_cpu():
    while True:
        pythoncom.CoInitialize()  # Inicializa COM en el hilo actual
        cpu_temp = get_cpu_temperature()
        if cpu_temp and cpu_temp > 70:  # Alerta de temperatura
            timestamp = datetime.now()
            ip = get_ip()
            cpu_message = f"{timestamp} | CPU Temp: {cpu_temp}°C | IP: {ip}"
            threading.Thread(target=write_log, args=(cpu_message,)).start()
            threading.Thread(target=insert_mysql, args=(timestamp, cpu_temp, 0, 0, ip, [])).start()
        time.sleep(5)

# Monitor de GPU
def monitor_gpu():
    while True:
        gpu_temp = get_gpu_temperature()
        if gpu_temp and gpu_temp > 70:  # Alerta de temperatura
            timestamp = datetime.now()
            ip = get_ip()
            gpu_message = f"{timestamp} | GPU Temp: {gpu_temp}°C | IP: {ip}"
            threading.Thread(target=write_log, args=(gpu_message,)).start()
            threading.Thread(target=insert_mysql, args=(timestamp, 0, gpu_temp, 0, ip, [])).start()
        time.sleep(5)

# Monitor de memoria
def monitor_memory():
    while True:
        memory_usage = psutil.virtual_memory().percent
        if memory_usage > 80:
            timestamp = datetime.now()
            ip = get_ip()
            memory_message = f"{timestamp} | Mem Usage: {memory_usage}% | IP: {ip}"
            threading.Thread(target=write_log, args=(memory_message,)).start()
            threading.Thread(target=insert_mysql, args=(timestamp, 0, 0, memory_usage, ip, [])).start()
        time.sleep(5)

# Monitor de tareas
def monitor_tasks():
    while True:
        tasks = [p.info["name"] for p in list(psutil.process_iter(attrs=["name"]))[:5]]
        timestamp = datetime.now()
        ip = get_ip()
        tasks_message = f"{timestamp} | Tasks: {', '.join(tasks)} | IP: {ip}"
        threading.Thread(target=write_log, args=(tasks_message,)).start()
        threading.Thread(target=insert_mysql, args=(timestamp, 0, 0, 0, ip, tasks)).start()
        time.sleep(5)

# Iniciar monitores
def start_monitoring():
    threading.Thread(target=monitor_cpu, daemon=True).start()
    threading.Thread(target=monitor_gpu, daemon=True).start()
    threading.Thread(target=monitor_memory, daemon=True).start()
    threading.Thread(target=monitor_tasks, daemon=True).start()

# Main
def main():
    setup_database()
    start_monitoring()
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
