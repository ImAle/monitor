import threading
import psutil
import wmi
import socket
import pythoncom
import time
from datetime import datetime
from collections import deque
import mysql.connector
import requests
import config

# Inicialización
lock = threading.Lock()
log_deque = deque(maxlen=config.MAX_LOG_ENTRIES)

# --- Configuración de Base de Datos ---
def setup_database():
    conn = mysql.connector.connect(
        host=config.DB_CONFIG["host"],
        user=config.DB_CONFIG["user"],
        password=config.DB_CONFIG["password"]
    )
    cursor = conn.cursor()

    cursor.execute("CREATE DATABASE IF NOT EXISTS system_monitor")
    conn.commit()

    conn.database = "system_monitor"
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

# --- Funciones Utilitarias ---
def get_ip():
    return socket.gethostbyname(socket.gethostname())

def valores(lista):
    return sum(lista) / len(lista) if lista else 0

def get_temperatures():
    """
    Obtiene las temperaturas de CPU y GPU utilizando OpenHardwareMonitor.
    """
    pythoncom.CoInitialize()
    try:
        w = wmi.WMI(namespace="root\\OpenHardwareMonitor")
        sensors = w.Sensor()
        cpu_temps = []
        gpu_temp = 0

        for sensor in sensors:
            if hasattr(sensor, 'SensorType') and hasattr(sensor, 'Name'):
                if sensor.SensorType == 'Temperature' and 'GPU' not in sensor.Name:
                    cpu_temps.append(float(sensor.Value))
                elif sensor.SensorType == 'Temperature' and 'GPU' in sensor.Name:
                    gpu_temp = sensor.Value

        return valores(cpu_temps), gpu_temp
    except Exception as e:
        print(f"Error al obtener temperaturas: {e}")
        return None, None

def send_telegram_message(message):
    """
    Envía un mensaje al bot de Telegram.
    """
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": message
    }
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Error al enviar mensaje de Telegram: {e}")

# --- Escritura de Logs ---
def write_log(log_type, message):
    """
    Escribe un mensaje en el archivo log, limitado a las últimas 5 entradas.
    """
    with lock:
        timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        formatted_message = f"{timestamp} | {log_type} | {message}"
        log_deque.append(formatted_message)
        with open(config.LOG_FILE, "w") as log_file:
            log_file.write("\n".join(log_deque))

def insert_mysql(timestamp, cpu_temp, gpu_temp, memory_usage, ip, tasks):
    """
    Inserta un registro en la base de datos MySQL.
    """
    conn = mysql.connector.connect(**config.DB_CONFIG)
    cursor = conn.cursor()
    query = """
        INSERT INTO system_logs (timestamp, cpu_temp, gpu_temp, memory_usage, ip_address, tasks)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    cursor.execute(query, (timestamp, cpu_temp, gpu_temp, memory_usage, ip, ", ".join(tasks)))
    conn.commit()
    conn.close()

# --- Monitores ---
def monitor_system():
    """
    Monitorea temperaturas, uso de memoria y tareas actuales, registrando todo en logs y base de datos.
    """
    while True:
        try:
            # Obtener datos del sistema
            cpu_temp, gpu_temp = get_temperatures()
            memory_usage = psutil.virtual_memory().percent
            tasks = [p.info["name"] for p in list(psutil.process_iter(attrs=["name"]))[:5]]
            ip = get_ip()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Crear mensajes de log
            if cpu_temp:
                cpu_message = f"Control de temperatura de la CPU: {cpu_temp:.2f}°C"
                write_log("CPU", cpu_message)

            if gpu_temp:
                gpu_message = f"Control de temperatura de la GPU: {gpu_temp:.2f}°C"
                write_log("GPU", gpu_message)

            memory_message = f"Utilización de memoria: {memory_usage}%"
            write_log("Memoria", memory_message)

            tasks_message = f"Tareas actuales: {', '.join(tasks)}"
            write_log("Tareas", tasks_message)

            # Enviar datos a la base de datos
            insert_mysql(timestamp, cpu_temp, gpu_temp, memory_usage, ip, tasks)

            # Enviar mensaje a Telegram
            telegram_message = (
                f"📊 Monitoreo del Sistema\n\n"
                f"📅 Fecha: {timestamp}\n"
                f"🌡️ CPU Temp: {cpu_temp:.2f}°C\n"
                f"🌡️ GPU Temp: {gpu_temp:.2f}°C\n"
                f"💾 Uso de Memoria: {memory_usage}%\n"
                f"🖥️ IP: {ip}\n"
                f"📋 Tareas: {', '.join(tasks)}"
            )
            send_telegram_message(telegram_message)

        except Exception as e:
            print(f"Error en monitorización: {e}")

        time.sleep(5)

# --- Main ---
def main():
    setup_database()
    threading.Thread(target=monitor_system, daemon=True).start()
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
