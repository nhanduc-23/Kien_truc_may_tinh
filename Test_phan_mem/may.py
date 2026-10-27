import json
import socket
import threading
import time
from datetime import datetime

import customtkinter as ctk
import matplotlib
import minimalmodbus
import serial
from serial.tools import list_ports

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# ==========================================================
# CẤU HÌNH THIẾT BỊ (CHUẨN THEO DOTHONGSO.PY)
# ==========================================================

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

SENSOR_SLAVE_ID = 1
SENSOR_BAUDRATE = 4800

RELAY_SLAVE_ID = 255
RELAY_BAUDRATE = 9600

TIMEOUT = 0.5

TCP_HOST = "0.0.0.0"
TCP_PORT = 5000

MAX_DATA_POINTS = 30

# ==========================================================
# BIẾN TOÀN CỤC & TRẠNG THÁI
# ==========================================================

instrument = None

rs485_connected = False
sensor_online = False
pc2_connected = False

temperature = 0.0
humidity = 0.0

bom_state = False
quat_state = False

client_socket = None
client_address = None

running = True

modbus_lock = threading.Lock()
tcp_lock = threading.Lock()

latest_packet = {}

time_data = []
temp_data = []
humi_data = []

pages = {}
menu_buttons = {}

# ==========================================================
# KHỞI TẠO CỬA SỔ CHÍNH
# ==========================================================

app = ctk.CTk()
app.title("PC1 - Industrial Gateway, Real-time Chart & Control Station")
app.geometry("1450x900")
app.minsize(1250, 750)

BG = "#090E1A"
SIDEBAR = "#111827"
CARD = "#151E2E"
CARD2 = "#1B2638"

TEXT = "#F8FAFC"
TEXT2 = "#94A3B8"

BLUE = "#3B82F6"
CYAN = "#06B6D4"
GREEN = "#22C55E"
RED = "#EF4444"
ORANGE = "#F59E0B"
PURPLE = "#8B5CF6"

# ==========================================================
# HÀM HỖ TRỢ LOG & GIAO DIỆN
# ==========================================================

def gui_call(func):
    app.after(0, func)

def add_log(message, level="INFO"):
    def write_log():
        now = datetime.now().strftime("%H:%M:%S")
        log_box.configure(state="normal")
        log_box.insert("end", f"[{now}] [{level}] {message}\n")
        log_box.see("end")
        log_box.configure(state="disabled")

    gui_call(write_log)

def show_page(page_name):
    for page in pages.values():
        page.pack_forget()

    pages[page_name].pack(fill="both", expand=True)

    for name, button in menu_buttons.items():
        if name == page_name:
            button.configure(fg_color="#1D4ED8")
        else:
            button.configure(fg_color="transparent")

    page_title.configure(text=page_name)

def update_clock():
    now = datetime.now()
    clock_label.configure(text=now.strftime("%H:%M:%S"))
    date_label.configure(text=now.strftime("%d/%m/%Y"))
    app.after(1000, update_clock)

# ==========================================================
# KẾT NỐI RS485 & CHUYỂN ĐỔI MODBUS
# ==========================================================

def scan_ports():
    ports = [port.device for port in list_ports.comports()]
    if not ports:
        ports = ["Không tìm thấy COM"]

    com_menu.configure(values=ports)
    com_menu.set(ports[0])
    rs485_page_port.configure(text=ports[0])
    add_log(f"Scan COM Ports: {ports}")

def connect_rs485():
    global instrument, rs485_connected

    if rs485_connected:
        disconnect_rs485()
        return

    port = com_menu.get()
    if "Không tìm" in port:
        add_log("Không tìm thấy cổng COM hợp lệ!", "ERROR")
        return

    try:
        if instrument is not None:
            try:
                if instrument.serial and instrument.serial.is_open:
                    instrument.serial.close()
            except Exception:
                pass

        instrument = minimalmodbus.Instrument(port, SENSOR_SLAVE_ID)
        instrument.mode = minimalmodbus.MODE_RTU
        instrument.serial.baudrate = SENSOR_BAUDRATE
        instrument.serial.bytesize = 8
        instrument.serial.parity = serial.PARITY_NONE
        instrument.serial.stopbits = 1
        instrument.serial.timeout = TIMEOUT
        instrument.clear_buffers_before_each_transaction = True

        rs485_connected = True

        rs485_status.configure(text="● RS485 ONLINE", text_color=GREEN)
        rs485_button.configure(text="NGẮT RS485", fg_color=RED)
        sidebar_rs485.configure(text="● RS485 BUS ONLINE", text_color=GREEN)
        rs485_page_status.configure(text="ONLINE", text_color=GREEN)

        enable_relay_ui(True)
        add_log(f"Đã mở cổng {port} thành công")

    except Exception as e:
        rs485_connected = False
        add_log(f"Lỗi mở cổng {port}: {e}", "ERROR")

def disconnect_rs485():
    global rs485_connected, sensor_online

    rs485_connected = False
    sensor_online = False

    try:
        if instrument and instrument.serial and instrument.serial.is_open:
            instrument.serial.close()
    except Exception:
        pass

    rs485_status.configure(text="● RS485 OFFLINE", text_color=RED)
    rs485_button.configure(text="KẾT NỐI RS485", fg_color=BLUE)
    sidebar_rs485.configure(text="● RS485 BUS OFFLINE", text_color=RED)
    rs485_page_status.configure(text="OFFLINE", text_color=RED)
    sensor_status.configure(text="● SENSOR OFFLINE", text_color=RED)

    enable_relay_ui(False)
    add_log("Đã ngắt kết nối RS485")

def safe_modbus_switch(slave_id, baudrate):
    """Xóa đệm cổng nối tiếp và đổi Baudrate an toàn chuẩn theo dothongso.py"""
    if instrument is None or instrument.serial is None:
        raise Exception("Chưa khởi tạo RS485")

    if not instrument.serial.is_open:
        instrument.serial.open()

    if instrument.serial.baudrate != baudrate:
        instrument.serial.baudrate = baudrate
        time.sleep(0.1)

    instrument.address = slave_id
    
    if instrument.serial.is_open:
        instrument.serial.reset_input_buffer()
        instrument.serial.reset_output_buffer()

# ==========================================================
# ĐỌC CẢM BIẾN (SLAVE ID: 1, BAUDRATE: 4800)
# ==========================================================

def read_sensor():
    global temperature, humidity, sensor_online

    if not rs485_connected or instrument is None:
        return

    try:
        with modbus_lock:
            safe_modbus_switch(slave_id=SENSOR_SLAVE_ID, baudrate=SENSOR_BAUDRATE)

            registers = instrument.read_registers(
                registeraddress=0,
                number_of_registers=2,
                functioncode=3
            )
            raw_humi = registers[0]
            raw_temp = registers[1]

        if raw_temp > 32767:
            raw_temp -= 65536

        temperature = raw_temp / 10.0
        humidity = raw_humi / 10.0
        sensor_online = True

        now_str = datetime.now().strftime("%H:%M:%S")
        time_data.append(now_str)
        temp_data.append(temperature)
        humi_data.append(humidity)

        if len(time_data) > MAX_DATA_POINTS:
            time_data.pop(0)
            temp_data.pop(0)
            humi_data.pop(0)

        gui_call(update_sensor_ui)
        gui_call(update_graph_ui)

        gui_call(
            lambda: add_rs485_traffic(
                f"[{now_str}] RX | Slave={SENSOR_SLAVE_ID} (4800) | FC03 | "
                f"T={temperature:.1f}°C | H={humidity:.1f}%"
            )
        )

    except Exception as e:
        sensor_online = False
        gui_call(lambda: sensor_status.configure(text="● SENSOR ERROR", text_color=RED))
        gui_call(lambda: add_rs485_traffic(f"[{datetime.now().strftime('%H:%M:%S')}] SENSOR ERROR | {e}"))
    

def update_sensor_ui():
    temp_value.configure(text=f"{temperature:.1f} °C")
    humi_value.configure(text=f"{humidity:.1f} %")

    temp_progress.set(max(0.0, min(temperature / 50.0, 1.0)))
    humi_progress.set(max(0.0, min(humidity / 100.0, 1.0)))

    sensor_status.configure(text="● SENSOR ONLINE", text_color=GREEN)
    sensor_update.configure(text="Update: " + datetime.now().strftime("%H:%M:%S"))

    rs485_page_temp.configure(text=f"{temperature:.1f} °C")
    rs485_page_humi.configure(text=f"{humidity:.1f} %")

def add_rs485_traffic(text):
    rs485_monitor_box.configure(state="normal")
    rs485_monitor_box.insert("end", text + "\n")
    rs485_monitor_box.see("end")
    rs485_monitor_box.configure(state="disabled")

# ==========================================================
# ĐIỀU KHIỂN RELAY (SLAVE ID: 255, BAUDRATE: 9600)
# ==========================================================

def enable_relay_ui(enable):
    state = "normal" if enable else "disabled"
    btn_bom_toggle.configure(state=state)
    btn_quat_toggle.configure(state=state)
    btn_auto.configure(state=state)
    btn_off_all.configure(state=state)

def toggle_bom():
    global bom_state
    if not rs485_connected or instrument is None:
        return

    try:
        new_state = not bom_state
        with modbus_lock:
            safe_modbus_switch(slave_id=RELAY_SLAVE_ID, baudrate=RELAY_BAUDRATE)
            instrument.write_bit(registeraddress=0, value=1 if new_state else 0)

        bom_state = new_state
        gui_call(update_relay_ui)
        add_log(f"Bơm 12V (Relay 1) -> {'BẬT' if bom_state else 'TẮT'}")
        add_rs485_traffic(f"[{datetime.now().strftime('%H:%M:%S')}] TX | Slave={RELAY_SLAVE_ID} (9600) | Write Bit 0 = {1 if bom_state else 0}")
    except Exception as e:
        add_log(f"Lỗi điều khiển Bơm: {e}", "ERROR")

def toggle_quat():
    global quat_state
    if not rs485_connected or instrument is None:
        return

    try:
        new_state = not quat_state
        with modbus_lock:
            safe_modbus_switch(slave_id=RELAY_SLAVE_ID, baudrate=RELAY_BAUDRATE)
            instrument.write_bit(registeraddress=1, value=1 if new_state else 0)

        quat_state = new_state
        gui_call(update_relay_ui)
        add_log(f"Quạt 12V (Relay 2) -> {'BẬT' if quat_state else 'TẮT'}")
        add_rs485_traffic(f"[{datetime.now().strftime('%H:%M:%S')}] TX | Slave={RELAY_SLAVE_ID} (9600) | Write Bit 1 = {1 if quat_state else 0}")
    except Exception as e:
        add_log(f"Lỗi điều khiển Quạt: {e}", "ERROR")

def turn_off_all():
    global bom_state, quat_state
    if not rs485_connected or instrument is None:
        return

    try:
        with modbus_lock:
            safe_modbus_switch(slave_id=RELAY_SLAVE_ID, baudrate=RELAY_BAUDRATE)
            instrument.write_bit(registeraddress=0, value=0)
            instrument.write_bit(registeraddress=1, value=0)

        bom_state = False
        quat_state = False
        gui_call(update_relay_ui)
        add_log("Tắt toàn bộ Bơm & Quạt")
        add_rs485_traffic(f"[{datetime.now().strftime('%H:%M:%S')}] TX | Slave={RELAY_SLAVE_ID} (9600) | Turn OFF All")
    except Exception as e:
        add_log(f"Lỗi ngắt thiết bị: {e}", "ERROR")

def run_auto_sequence():
    def auto_thread():
        gui_call(lambda: enable_relay_ui(False))
        try:
            add_log("🔄 Chạy kịch bản tự động...")
            if not quat_state:
                toggle_quat()
            time.sleep(3)

            if not bom_state:
                toggle_bom()
            time.sleep(5)

            if bom_state:
                toggle_bom()
            time.sleep(2)

            if quat_state:
                toggle_quat()

            add_log("✅ Hoàn thành kịch bản tự động")
        except Exception as e:
            add_log(f"Lỗi kịch bản tự động: {e}", "ERROR")
        finally:
            gui_call(lambda: enable_relay_ui(True))

    threading.Thread(target=auto_thread, daemon=True).start()

def update_relay_ui():
    if bom_state:
        lbl_bom_status.configure(text="BƠM ĐANG BẬT", fg_color=GREEN)
        btn_bom_toggle.configure(text="TẮT BƠM", fg_color=RED)
        lbl_dash_bom.configure(text="BƠM: BẬT", text_color=GREEN)
    else:
        lbl_bom_status.configure(text="ĐANG TẮT", fg_color=RED)
        btn_bom_toggle.configure(text="BẬT BƠM", fg_color=BLUE)
        lbl_dash_bom.configure(text="BƠM: TẮT", text_color=TEXT2)

    if quat_state:
        lbl_quat_status.configure(text="QUẠT ĐANG BẬT", fg_color=GREEN)
        btn_quat_toggle.configure(text="TẮT QUẠT", fg_color=RED)
        lbl_dash_quat.configure(text="QUẠT: BẬT", text_color=GREEN)
    else:
        lbl_quat_status.configure(text="ĐANG TẮT", fg_color=RED)
        btn_quat_toggle.configure(text="BẬT QUẠT", fg_color=BLUE)
        lbl_dash_quat.configure(text="QUẠT: TẮT", text_color=TEXT2)

# ==========================================================
# TCP SERVER (TRUYỀN SANG PC2)
# ==========================================================

def build_packet():
    global latest_packet

    latest_packet = {
        "source": "PC1",
        "temperature": round(temperature, 1),
        "humidity": round(humidity, 1),
        "bom_status": bom_state,
        "quat_status": quat_state,
        "sensor_online": sensor_online,
        "rs485_online": rs485_connected,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    packet_text = json.dumps(latest_packet, ensure_ascii=False, indent=4)

    def update_packet_boxes():
        packet_box.configure(state="normal")
        packet_box.delete("1.0", "end")
        packet_box.insert("end", packet_text)
        packet_box.configure(state="disabled")

        packet_page_box.configure(state="normal")
        packet_page_box.delete("1.0", "end")
        packet_page_box.insert("end", packet_text)
        packet_page_box.configure(state="disabled")

    gui_call(update_packet_boxes)
    return latest_packet

def send_packet_to_pc2():
    global pc2_connected

    if not pc2_connected:
        return

    packet = build_packet()
    message = json.dumps(packet, ensure_ascii=False) + "\n"

    try:
        with tcp_lock:
            client_socket.sendall(message.encode("utf-8"))

        now_str = datetime.now().strftime("%H:%M:%S")
        gui_call(lambda: packet_counter_label.configure(text="Last TX: " + now_str))
        gui_call(lambda: lan_last_tx.configure(text=now_str))

    except Exception as e:
        pc2_connected = False
        add_log(f"Mất kết nối PC2: {e}", "ERROR")
        gui_call(update_pc2_status)

def tcp_server():
    global client_socket, client_address, pc2_connected

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((TCP_HOST, TCP_PORT))
    server.listen(1)

    add_log(f"TCP Server chạy tại port {TCP_PORT}")

    while running:
        try:
            client_socket, client_address = server.accept()
            pc2_connected = True

            add_log(f"PC2 connected: {client_address[0]}:{client_address[1]}")
            gui_call(update_pc2_status)

            while running and pc2_connected:
                send_packet_to_pc2()
                time.sleep(1)

        except Exception as e:
            if running:
                add_log(f"TCP Error: {e}", "ERROR")

        finally:
            pc2_connected = False
            try:
                if client_socket:
                    client_socket.close()
            except Exception:
                pass
            gui_call(update_pc2_status)

def update_pc2_status():
    if pc2_connected:
        pc2_status.configure(text="● PC2 CONNECTED", text_color=GREEN)
        sidebar_lan.configure(text="● LAN CONNECTED", text_color=GREEN)
        lan_page_status.configure(text="CONNECTED", text_color=GREEN)

        if client_address:
            address = f"{client_address[0]}:{client_address[1]}"
            pc2_address.configure(text=address)
            lan_pc2_address.configure(text=address)
    else:
        pc2_status.configure(text="● WAITING PC2", text_color=ORANGE)
        sidebar_lan.configure(text="● LAN WAITING", text_color=ORANGE)
        lan_page_status.configure(text="WAITING", text_color=ORANGE)
        pc2_address.configure(text="--")
        lan_pc2_address.configure(text="--")

# ==========================================================
# POLLING LOOP (ĐỌC ĐỊNH KỲ)
# ==========================================================

def polling_loop():
    while running:
        if rs485_connected:
            read_sensor()
        build_packet()
        time.sleep(1.5)

# ==========================================================
# GIAO DIỆN CHÍNH
# ==========================================================

sidebar = ctk.CTkFrame(app, width=220, corner_radius=0, fg_color=SIDEBAR)
sidebar.pack(side="left", fill="y")
sidebar.pack_propagate(False)

ctk.CTkLabel(sidebar, text="NEXUS", text_color=CYAN, font=ctk.CTkFont(size=30, weight="bold")).pack(pady=(30, 0))
ctk.CTkLabel(sidebar, text="DATA GATEWAY", font=ctk.CTkFont(size=13, weight="bold")).pack()
ctk.CTkLabel(sidebar, text="PC1 INDUSTRIAL NODE", text_color=TEXT2, font=ctk.CTkFont(size=10)).pack(pady=(5, 25))

right = ctk.CTkFrame(app, fg_color=BG, corner_radius=0)
right.pack(side="left", fill="both", expand=True)

header = ctk.CTkFrame(right, height=80, fg_color="transparent")
header.pack(fill="x", padx=30, pady=(10, 0))
header.pack_propagate(False)

header_left = ctk.CTkFrame(header, fg_color="transparent")
header_left.pack(side="left")

page_title = ctk.CTkLabel(header_left, text="Gateway Monitor", font=ctk.CTkFont(size=28, weight="bold"))
page_title.pack(anchor="w")

ctk.CTkLabel(header_left, text="RS485  ➔  PC1 Gateway  ➔  TCP/IP  ➔  PC2", text_color=TEXT2).pack(anchor="w")

clock_frame = ctk.CTkFrame(header, fg_color="transparent")
clock_frame.pack(side="right")

clock_label = ctk.CTkLabel(clock_frame, text="00:00:00", font=ctk.CTkFont(size=22, weight="bold"))
clock_label.pack()

date_label = ctk.CTkLabel(clock_frame, text="", text_color=TEXT2)
date_label.pack()

comm_bar = ctk.CTkFrame(right, height=55, corner_radius=15, fg_color=CARD)
comm_bar.pack(fill="x", padx=30, pady=(0, 10))

rs485_status = ctk.CTkLabel(comm_bar, text="● RS485 OFFLINE", text_color=RED, font=ctk.CTkFont(size=12, weight="bold"))
rs485_status.pack(side="left", padx=20)

com_menu = ctk.CTkOptionMenu(comm_bar, width=110, values=["COM5"])
com_menu.pack(side="left", padx=5)

ctk.CTkButton(comm_bar, text="SCAN", width=70, fg_color="#334155", command=scan_ports).pack(side="left", padx=5)

# ĐÃ SỬA: Tách riêng nút bấm và .pack()
rs485_button = ctk.CTkButton(comm_bar, text="KẾT NỐI RS485", width=140, fg_color=BLUE, command=connect_rs485)
rs485_button.pack(side="left", padx=10)

pc2_status = ctk.CTkLabel(comm_bar, text="● WAITING PC2", text_color=ORANGE, font=ctk.CTkFont(size=12, weight="bold"))
pc2_status.pack(side="right", padx=20)

page_container = ctk.CTkFrame(right, fg_color=BG, corner_radius=0)
page_container.pack(fill="both", expand=True)

page_names = ["Gateway Monitor", "Real-time Chart", "Relay Control", "RS485 Monitor", "TCP / LAN", "Data Packet"]
for page_name in page_names:
    pages[page_name] = ctk.CTkFrame(page_container, fg_color=BG)

menu_data = [
    ("Gateway Monitor", "📊"),
    ("Real-time Chart", "📈"),
    ("Relay Control", "⚡"),
    ("RS485 Monitor", "🔌"),
    ("TCP / LAN", "🌐"),
    ("Data Packet", "📦")
]

for name, icon in menu_data:
    button = ctk.CTkButton(
        sidebar,
        text=f"{icon}     {name}",
        height=42,
        anchor="w",
        corner_radius=10,
        fg_color="transparent",
        hover_color="#1E293B",
        command=lambda n=name: show_page(n)
    )
    button.pack(fill="x", padx=15, pady=4)
    menu_buttons[name] = button

side_bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
side_bottom.pack(side="bottom", fill="x", padx=20, pady=20)

ctk.CTkLabel(side_bottom, text="COMMUNICATION", text_color=TEXT2, font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w")

sidebar_rs485 = ctk.CTkLabel(side_bottom, text="● RS485 BUS OFFLINE", text_color=RED, font=ctk.CTkFont(size=11, weight="bold"))
sidebar_rs485.pack(anchor="w", pady=4)

sidebar_lan = ctk.CTkLabel(side_bottom, text="● LAN WAITING", text_color=ORANGE, font=ctk.CTkFont(size=11, weight="bold"))
sidebar_lan.pack(anchor="w")

# PAGE 1 - GATEWAY MONITOR
gateway = pages["Gateway Monitor"]

top_cards = ctk.CTkFrame(gateway, fg_color="transparent")
top_cards.pack(fill="x", padx=20, pady=10)
top_cards.grid_columnconfigure((0, 1, 2), weight=1)

temp_card = ctk.CTkFrame(top_cards, fg_color=CARD, corner_radius=20)
temp_card.grid(row=0, column=0, padx=10, sticky="nsew")
ctk.CTkLabel(temp_card, text="🌡️  NHIỆT ĐỘ", text_color=TEXT2, font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(20, 5))
temp_value = ctk.CTkLabel(temp_card, text="--.- °C", text_color=ORANGE, font=ctk.CTkFont(size=36, weight="bold"))
temp_value.pack(pady=5)
temp_progress = ctk.CTkProgressBar(temp_card, width=200, progress_color=ORANGE)
temp_progress.set(0)
temp_progress.pack(pady=10)
ctk.CTkLabel(temp_card, text="Register 0x0001 • FC03", text_color=TEXT2, font=ctk.CTkFont(size=10)).pack(pady=(0, 15))

humi_card = ctk.CTkFrame(top_cards, fg_color=CARD, corner_radius=20)
humi_card.grid(row=0, column=1, padx=10, sticky="nsew")
ctk.CTkLabel(humi_card, text="💧  ĐỘ ẨM", text_color=TEXT2, font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(20, 5))
humi_value = ctk.CTkLabel(humi_card, text="--.- %", text_color=CYAN, font=ctk.CTkFont(size=36, weight="bold"))
humi_value.pack(pady=5)
humi_progress = ctk.CTkProgressBar(humi_card, width=200, progress_color=CYAN)
humi_progress.set(0)
humi_progress.pack(pady=10)
ctk.CTkLabel(humi_card, text="Register 0x0000 • FC03", text_color=TEXT2, font=ctk.CTkFont(size=10)).pack(pady=(0, 15))

sensor_card = ctk.CTkFrame(top_cards, fg_color=CARD, corner_radius=20)
sensor_card.grid(row=0, column=2, padx=10, sticky="nsew")
ctk.CTkLabel(sensor_card, text="FIELD DEVICE STATUS", text_color=TEXT2, font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(20, 5))
sensor_status = ctk.CTkLabel(sensor_card, text="● SENSOR OFFLINE", text_color=RED, font=ctk.CTkFont(size=14, weight="bold"))
sensor_status.pack(pady=2)

lbl_dash_bom = ctk.CTkLabel(sensor_card, text="BƠM: TẮT", text_color=TEXT2, font=ctk.CTkFont(size=12, weight="bold"))
lbl_dash_bom.pack()
lbl_dash_quat = ctk.CTkLabel(sensor_card, text="QUẠT: TẮT", text_color=TEXT2, font=ctk.CTkFont(size=12, weight="bold"))
lbl_dash_quat.pack()

sensor_update = ctk.CTkLabel(sensor_card, text="Update: --:--:--", text_color=TEXT2, font=ctk.CTkFont(size=11))
sensor_update.pack(pady=(5, 15))

gateway_bottom = ctk.CTkFrame(gateway, fg_color="transparent")
gateway_bottom.pack(fill="both", expand=True, padx=20, pady=10)
gateway_bottom.grid_columnconfigure((0, 1), weight=1)

packet_card = ctk.CTkFrame(gateway_bottom, fg_color=CARD, corner_radius=20)
packet_card.grid(row=0, column=0, padx=10, sticky="nsew")
packet_counter_label = ctk.CTkLabel(packet_card, text="Last TX: --:--:--", text_color=TEXT2)
packet_counter_label.pack(anchor="e", padx=20, pady=(12, 0))
packet_box = ctk.CTkTextbox(packet_card, fg_color="#0B1220", font=ctk.CTkFont(family="Consolas", size=11))
packet_box.pack(fill="both", expand=True, padx=15, pady=12)
packet_box.configure(state="disabled")

network_card = ctk.CTkFrame(gateway_bottom, fg_color=CARD, corner_radius=20)
network_card.grid(row=0, column=1, padx=10, sticky="nsew")
ctk.CTkLabel(network_card, text="LAN / TCP SERVER", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=20, pady=15)

def info_row(parent, title, value):
    row = ctk.CTkFrame(parent, fg_color=CARD2, corner_radius=10)
    row.pack(fill="x", padx=20, pady=5)
    ctk.CTkLabel(row, text=title, text_color=TEXT2).pack(side="left", padx=15, pady=8)
    label = ctk.CTkLabel(row, text=value, font=ctk.CTkFont(weight="bold"))
    label.pack(side="right", padx=15)
    return label

info_row(network_card, "Listen", "0.0.0.0")
info_row(network_card, "TCP Port", str(TCP_PORT))
pc2_address = info_row(network_card, "PC2 Client", "--")
info_row(network_card, "Protocol", "TCP / JSON")

# PAGE 2 - REAL-TIME CHART
chart_page = pages["Real-time Chart"]
chart_frame = ctk.CTkFrame(chart_page, fg_color=CARD, corner_radius=20)
chart_frame.pack(fill="both", expand=True, padx=20, pady=20)

fig = Figure(figsize=(10, 5), facecolor=CARD)
ax1 = fig.add_subplot(211)
ax2 = fig.add_subplot(212)
fig.subplots_adjust(hspace=0.4, left=0.08, right=0.95, top=0.92, bottom=0.12)

def setup_axes():
    ax1.set_facecolor("#0B1220")
    ax1.set_title("Nhiệt độ (°C) Theo Thời Gian", color="white", fontsize=11, fontweight="bold")
    ax1.tick_params(colors=TEXT2, labelsize=8)
    ax1.grid(True, linestyle="--", alpha=0.3, color="#334155")

    ax2.set_facecolor("#0B1220")
    ax2.set_title("Độ ẩm (%) Theo Thời Gian", color="white", fontsize=11, fontweight="bold")
    ax2.tick_params(colors=TEXT2, labelsize=8)
    ax2.grid(True, linestyle="--", alpha=0.3, color="#334155")

setup_axes()

canvas = FigureCanvasTkAgg(fig, master=chart_frame)
canvas.get_tk_widget().pack(fill="both", expand=True, padx=15, pady=15)

def update_graph_ui():
    if not time_data:
        return

    ax1.clear()
    ax2.clear()

    setup_axes()

    ax1.plot(time_data, temp_data, color=ORANGE, marker="o", linewidth=2, markersize=4, label="Nhiệt độ (°C)")
    ax1.legend(loc="upper left", facecolor="#0B1220", edgecolor="none", labelcolor="white", fontsize=9)

    ax2.plot(time_data, humi_data, color=CYAN, marker="s", linewidth=2, markersize=4, label="Độ ẩm (%)")
    ax2.legend(loc="upper left", facecolor="#0B1220", edgecolor="none", labelcolor="white", fontsize=9)

    ax1.tick_params(axis='x', rotation=30)
    ax2.tick_params(axis='x', rotation=30)

    canvas.draw_idle()

# PAGE 3 - RELAY CONTROL
relay_page = pages["Relay Control"]

relay_container = ctk.CTkFrame(relay_page, fg_color="transparent")
relay_container.pack(fill="both", expand=True, padx=30, pady=20)
relay_container.grid_columnconfigure((0, 1), weight=1)

bom_frame = ctk.CTkFrame(relay_container, fg_color=CARD, corner_radius=20)
bom_frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")

ctk.CTkLabel(bom_frame, text="🚰  RELAY 1 - BƠM 12V", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(25, 15))

# ĐÃ SỬA: Tách riêng nhãn trạng thái và .pack()
lbl_bom_status = ctk.CTkLabel(bom_frame, text="ĐANG TẮT", fg_color=RED, text_color="white", font=ctk.CTkFont(size=16, weight="bold"), corner_radius=10, width=160, height=45)
lbl_bom_status.pack(pady=15)

btn_bom_toggle = ctk.CTkButton(bom_frame, text="BẬT BƠM", font=ctk.CTkFont(size=15, weight="bold"), height=45, width=180, fg_color=BLUE, command=toggle_bom, state="disabled")
btn_bom_toggle.pack(pady=15)

ctk.CTkLabel(bom_frame, text=f"Slave ID: {RELAY_SLAVE_ID} • Baudrate: {RELAY_BAUDRATE}", text_color=TEXT2).pack(pady=(0, 20))

quat_frame = ctk.CTkFrame(relay_container, fg_color=CARD, corner_radius=20)
quat_frame.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")

ctk.CTkLabel(quat_frame, text="🌀  RELAY 2 - QUẠT 12V", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(25, 15))

# ĐÃ SỬA: Tách riêng nhãn trạng thái và .pack()
lbl_quat_status = ctk.CTkLabel(quat_frame, text="ĐANG TẮT", fg_color=RED, text_color="white", font=ctk.CTkFont(size=16, weight="bold"), corner_radius=10, width=160, height=45)
lbl_quat_status.pack(pady=15)

btn_quat_toggle = ctk.CTkButton(quat_frame, text="BẬT QUẠT", font=ctk.CTkFont(size=15, weight="bold"), height=45, width=180, fg_color=BLUE, command=toggle_quat, state="disabled")
btn_quat_toggle.pack(pady=15)

ctk.CTkLabel(quat_frame, text=f"Slave ID: {RELAY_SLAVE_ID} • Baudrate: {RELAY_BAUDRATE}", text_color=TEXT2).pack(pady=(0, 20))

auto_frame = ctk.CTkFrame(relay_page, fg_color=CARD, corner_radius=20)
auto_frame.pack(fill="x", padx=45, pady=(0, 20))

ctk.CTkLabel(auto_frame, text="ĐIỀU KHIỂN KỊCH BẢN TỰ ĐỘNG", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 10))

btn_auto = ctk.CTkButton(auto_frame, text="🔄 Chạy Kịch Bản Tự Động (Quạt 3s ➔ Bơm 5s ➔ Tắt)", fg_color="#2563EB", hover_color="#1D4ED8", font=ctk.CTkFont(size=15, weight="bold"), height=50, command=run_auto_sequence, state="disabled")
btn_auto.pack(fill="x", padx=30, pady=10)

btn_off_all = ctk.CTkButton(auto_frame, text="⛔ Tắt Tất Cả Bơm & Quạt", fg_color="#D97706", hover_color="#B45309", font=ctk.CTkFont(size=15, weight="bold"), height=50, command=turn_off_all, state="disabled")
btn_off_all.pack(fill="x", padx=30, pady=(0, 20))

# PAGE 4 - RS485 MONITOR
rs485_page = pages["RS485 Monitor"]

rs485_cards = ctk.CTkFrame(rs485_page, fg_color="transparent")
rs485_cards.pack(fill="x", padx=20, pady=15)
rs485_cards.grid_columnconfigure((0, 1, 2, 3), weight=1)

def stat_card(parent, column, title, value, color):
    card = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=18)
    card.grid(row=0, column=column, padx=8, sticky="nsew")
    ctk.CTkLabel(card, text=title, text_color=TEXT2).pack(pady=(15, 5))
    label = ctk.CTkLabel(card, text=value, text_color=color, font=ctk.CTkFont(size=22, weight="bold"))
    label.pack(pady=(5, 15))
    return label

rs485_page_port = stat_card(rs485_cards, 0, "PORT", "COM5", BLUE)
stat_card(rs485_cards, 1, "BAUDRATE", f"S:{SENSOR_BAUDRATE}/R:{RELAY_BAUDRATE}", GREEN)
stat_card(rs485_cards, 2, "SLAVE ID", f"S:{SENSOR_SLAVE_ID}/R:{RELAY_SLAVE_ID}", CYAN)
rs485_page_status = stat_card(rs485_cards, 3, "BUS STATUS", "OFFLINE", RED)

sensor_live_card = ctk.CTkFrame(rs485_page, fg_color=CARD, corner_radius=18)
sensor_live_card.pack(fill="x", padx=28, pady=5)

ctk.CTkLabel(sensor_live_card, text="LIVE REGISTER DATA", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=20, pady=10)

live_inner = ctk.CTkFrame(sensor_live_card, fg_color="transparent")
live_inner.pack(fill="x", padx=20, pady=(0, 15))

rs485_page_temp = ctk.CTkLabel(live_inner, text="--.- °C", text_color=ORANGE, font=ctk.CTkFont(size=26, weight="bold"))
rs485_page_temp.pack(side="left", expand=True)

rs485_page_humi = ctk.CTkLabel(live_inner, text="--.- %", text_color=CYAN, font=ctk.CTkFont(size=26, weight="bold"))
rs485_page_humi.pack(side="left", expand=True)

traffic_card = ctk.CTkFrame(rs485_page, fg_color=CARD, corner_radius=18)
traffic_card.pack(fill="both", expand=True, padx=28, pady=10)

ctk.CTkLabel(traffic_card, text="MODBUS TRAFFIC MONITOR", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=20, pady=10)

rs485_monitor_box = ctk.CTkTextbox(traffic_card, fg_color="#0B1220", font=ctk.CTkFont(family="Consolas", size=11))
rs485_monitor_box.pack(fill="both", expand=True, padx=15, pady=(0, 15))
rs485_monitor_box.configure(state="disabled")

# PAGE 5 - TCP / LAN
lan_page = pages["TCP / LAN"]

lan_status_card = ctk.CTkFrame(lan_page, fg_color=CARD, corner_radius=20)
lan_status_card.pack(fill="x", padx=30, pady=20)

ctk.CTkLabel(lan_status_card, text="TCP SERVER STATUS", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(15, 5))
lan_page_status = ctk.CTkLabel(lan_status_card, text="WAITING", text_color=ORANGE, font=ctk.CTkFont(size=28, weight="bold"))
lan_page_status.pack(pady=10)

lan_grid = ctk.CTkFrame(lan_page, fg_color="transparent")
lan_grid.pack(fill="x", padx=20, pady=10)
lan_grid.grid_columnconfigure((0, 1, 2, 3), weight=1)

stat_card(lan_grid, 0, "LISTEN", "0.0.0.0", BLUE)
stat_card(lan_grid, 1, "PORT", str(TCP_PORT), PURPLE)
lan_pc2_address = stat_card(lan_grid, 2, "PC2 CLIENT", "--", CYAN)
lan_last_tx = stat_card(lan_grid, 3, "LAST TX", "--:--:--", GREEN)

lan_info = ctk.CTkFrame(lan_page, fg_color=CARD, corner_radius=20)
lan_info.pack(fill="both", expand=True, padx=30, pady=15)

ctk.CTkLabel(lan_info, text="NETWORK DATA FLOW", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=20, pady=15)
ctk.CTkLabel(
    lan_info,
    text=(
        "PC1 TCP Server (0.0.0.0 : 5000)\n\n"
        "       ➔  Mạng LAN TCP/IP  ➔\n\n"
        "PC2 Client Node\n\n"
        "Định dạng dữ liệu: JSON + Ký tự xuống dòng (\\n)"
    ),
    text_color=TEXT2,
    font=ctk.CTkFont(family="Consolas", size=15)
).pack(pady=20)

# PAGE 6 - DATA PACKET
packet_page = pages["Data Packet"]

ctk.CTkLabel(packet_page, text="JSON PACKET PREVIEW", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=30, pady=(20, 5))
ctk.CTkLabel(packet_page, text="Gói dữ liệu JSON đóng gói đẩy sang PC2 mỗi 1.5 giây.", text_color=TEXT2).pack(anchor="w", padx=30)

packet_page_card = ctk.CTkFrame(packet_page, fg_color=CARD, corner_radius=20)
packet_page_card.pack(fill="both", expand=True, padx=30, pady=15)

packet_page_box = ctk.CTkTextbox(packet_page_card, fg_color="#0B1220", font=ctk.CTkFont(family="Consolas", size=14))
packet_page_box.pack(fill="both", expand=True, padx=20, pady=20)
packet_page_box.configure(state="disabled")

# LOG HỆ THỐNG
log_frame = ctk.CTkFrame(right, fg_color=CARD, corner_radius=15)
log_frame.pack(fill="x", padx=30, pady=(0, 15))

ctk.CTkLabel(log_frame, text="SYSTEM LOG", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=15, pady=(8, 2))

log_box = ctk.CTkTextbox(log_frame, height=90, fg_color="#0B1220", font=ctk.CTkFont(family="Consolas", size=10))
log_box.pack(fill="x", padx=15, pady=(0, 8))
log_box.configure(state="disabled")

# THOÁT ỨNG DỤNG
def on_close():
    global running
    running = False

    try:
        if instrument and instrument.serial and instrument.serial.is_open:
            instrument.serial.close()
    except Exception:
        pass

    try:
        if client_socket:
            client_socket.close()
    except Exception:
        pass

    app.destroy()

app.protocol("WM_DELETE_WINDOW", on_close)

# KHỞI CHẠY
scan_ports()
update_clock()
build_packet()
show_page("Gateway Monitor")
add_log("Hệ thống PC1 Gateway đã khởi chạy thành công.")

threading.Thread(target=polling_loop, daemon=True).start()
threading.Thread(target=tcp_server, daemon=True).start()

app.mainloop()