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
# CẤU HÌNH HỆ THỐNG PC1 GATEWAY & CLIENT
# ==========================================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Mặc định cấu hình RS485 Modbus RTU
SENSOR_SLAVE_ID = 1
SENSOR_BAUDRATE = 4800

RELAY_SLAVE_ID = 255
RELAY_BAUDRATE = 9600

TIMEOUT = 0.5
MAX_DATA_POINTS = 30

# Mặc định kết nối TCP LAN sang PC2 Server
DEFAULT_PC2_IP = "192.168.1.100"
DEFAULT_PC2_PORT = 65432

# ==========================================================
# CẤU HÌNH NGƯỠNG ĐIỀU KHIỂN TỰ ĐỘNG
# ==========================================================
TEMP_AUTO_THRESHOLD = 31.0  # Ngưỡng bật quạt (>= 31.0 °C)
HUMI_AUTO_THRESHOLD = 50.0  # Ngưỡng bật bơm (< 65.0 %)
auto_mode_enabled = True     # Mặc định bật chế độ tự động theo ngưỡng

# ==========================================================
# BIẾN TOÀN CỤC & TRẠNG THÁI HỆ THỐNG
# ==========================================================
instrument = None
modbus_lock = threading.Lock()

rs485_connected = False
sensor_online = False

temperature = 0.0
humidity = 0.0

bom_state = False
quat_state = False

running = True

tcp_socket = None
tcp_connected = False
last_tcp_tx_time = "--:--:--"

time_data = []
temp_data = []
humi_data = []

pages = {}
menu_buttons = {}

# Khởi tạo cửa sổ chính
app = ctk.CTk()
app.title("RTU CLIENT - FIELD GATEWAY & MONITORING SYSTEM")
app.geometry("1480x920")
app.minsize(1280, 750)

BG, SIDEBAR, CARD, CARD2 = "#090E1A", "#111827", "#151E2E", "#1B2638"
TEXT, TEXT2 = "#F8FAFC", "#94A3B8"
BLUE, CYAN, GREEN, RED, ORANGE, PURPLE = "#3B82F6", "#06B6D4", "#22C55E", "#EF4444", "#F59E0B", "#8B5CF6"

# ==========================================================
# HÀM HỖ TRỢ HIỂN THỊ LOG & TRAFFIC
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

def add_sensor_traffic(text):
    def write_traffic():
        sensor_traffic_box.configure(state="normal")
        sensor_traffic_box.insert("end", text + "\n")
        sensor_traffic_box.see("end")
        sensor_traffic_box.configure(state="disabled")
    gui_call(write_traffic)

def add_actuator_traffic(text):
    def write_traffic():
        actuator_traffic_box.configure(state="normal")
        actuator_traffic_box.insert("end", text + "\n")
        actuator_traffic_box.see("end")
        actuator_traffic_box.configure(state="disabled")
    gui_call(write_traffic)

def show_page(page_name):
    for page in pages.values():
        page.pack_forget()
    pages[page_name].pack(fill="both", expand=True)
    for name, button in menu_buttons.items():
        button.configure(fg_color="#1D4ED8" if name == page_name else "transparent")
    page_title.configure(text=page_name)

def update_clock():
    now = datetime.now()
    clock_label.configure(text=now.strftime("%H:%M:%S"))
    date_label.configure(text=now.strftime("%d/%m/%Y"))
    app.after(1000, update_clock)

# ==========================================================
# KẾT NỐI MODBUS RS485 (COM5)
# ==========================================================
def on_select_port(choice):
    rs485_page_port.configure(text=choice)
    add_log(f"Đã chọn cổng COM: {choice}")

def scan_ports():
    scanned_ports = [port.device for port in list_ports.comports()]
    default_list = ["COM5", "COM3", "COM4", "COM1", "COM2", "COM6", "COM7"]
    all_ports = list(dict.fromkeys(scanned_ports + default_list))
    all_ports.sort(key=lambda x: int(x.replace("COM", "")) if x.startswith("COM") and x[3:].isdigit() else 999)

    com_menu.configure(values=all_ports)
    target_port = "COM5" if "COM5" in all_ports else all_ports[0]
    com_menu.set(target_port)
    rs485_page_port.configure(text=target_port)
    add_log(f"Quét cổng COM: {all_ports}")

def connect_rs485():
    global instrument, rs485_connected

    if rs485_connected:
        disconnect_rs485()
        return

    port = com_menu.get()
    if not port:
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
        sidebar_rs485.configure(text=f"● RS485 ONLINE ({port})", text_color=GREEN)
        rs485_page_status.configure(text="ONLINE", text_color=GREEN)

        enable_relay_ui(True)
        add_log(f"Đã kết nối Modbus RS485 qua cổng {port}")

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
    add_log("Đã ngắt kết nối RS485 hiện trường")

def safe_modbus_switch(slave_id, baudrate):
    if instrument is None or instrument.serial is None:
        raise Exception("Chưa kết nối RS485")

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
# THUẬT TOÁN ĐIỀU KHIỂN TỰ ĐỘNG THEO NGƯỠNG
# ==========================================================
def process_auto_control():
    """Kiểm tra ngưỡng và tự động đóng/ngắt quạt và bơm"""
    global auto_mode_enabled, TEMP_AUTO_THRESHOLD, HUMI_AUTO_THRESHOLD

    if not auto_mode_enabled or not rs485_connected:
        return

    # 1. Tự động điều khiển QUẠT dựa theo Nhiệt độ
    if temperature >= TEMP_AUTO_THRESHOLD and not quat_state:
        add_log(f"🔥 Nhiệt độ ({temperature:.1f}°C) >= Ngưỡng ({TEMP_AUTO_THRESHOLD}°C) ➔ Tự động BẬT QUẠT")
        toggle_quat()
    elif temperature < TEMP_AUTO_THRESHOLD and quat_state:
        add_log(f"❄️ Nhiệt độ ({temperature:.1f}°C) < Ngưỡng ({TEMP_AUTO_THRESHOLD}°C) ➔ Tự động TẮT QUẠT")
        toggle_quat()

    # 2. Tự động điều khiển BƠM dựa theo Độ ẩm
    if humidity < HUMI_AUTO_THRESHOLD and not bom_state:
        add_log(f"🌵 Độ ẩm ({humidity:.1f}%) < Ngưỡng ({HUMI_AUTO_THRESHOLD}%) ➔ Tự động BẬT BƠM")
        toggle_bom()
    elif humidity >= HUMI_AUTO_THRESHOLD and bom_state:
        add_log(f"💧 Độ ẩm ({humidity:.1f}%) >= Ngưỡng ({HUMI_AUTO_THRESHOLD}%) ➔ Tự động TẮT BƠM")
        toggle_bom()

# ==========================================================
# THAO TÁC MODBUS RTU: CẢM BIẾN SHT40 (SLAVE 1)
# ==========================================================
def read_sensor():
    global temperature, humidity, sensor_online

    if not rs485_connected or instrument is None:
        return

    now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    try:
        with modbus_lock:
            safe_modbus_switch(slave_id=SENSOR_SLAVE_ID, baudrate=SENSOR_BAUDRATE)

            tx_hex = f"{SENSOR_SLAVE_ID:02X} 03 00 00 00 02 CRC16"
            add_sensor_traffic(f"[{now_str}] ➢ GỬI ĐI (TX - REQUEST) | Slave ID: {SENSOR_SLAVE_ID} | FC03\n    Frame Hex: [ {tx_hex} ] | Read Regs: 0x0000 - 0x0001")

            registers = instrument.read_registers(registeraddress=0, number_of_registers=2, functioncode=3)
            raw_humi = registers[0]
            raw_temp = registers[1]

        if raw_temp > 32767:
            raw_temp -= 65536

        temperature = raw_temp / 10.0
        humidity = raw_humi / 10.0
        sensor_online = True

        rx_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        rx_hex = f"{SENSOR_SLAVE_ID:02X} 03 04 {raw_humi:04X} {raw_temp:04X} CRC16"
        add_sensor_traffic(f"[{rx_time}] ◄ NHẬN VỀ (RX - RESPONSE) | Frame: [ {rx_hex} ]\n    => Giải mã: Nhiệt độ = {temperature:.1f} °C | Độ ẩm = {humidity:.1f} %\n" + "-"*65)

        time_str = datetime.now().strftime("%H:%M:%S")
        time_data.append(time_str)
        temp_data.append(temperature)
        humi_data.append(humidity)

        if len(time_data) > MAX_DATA_POINTS:
            time_data.pop(0)
            temp_data.pop(0)
            humi_data.pop(0)

        gui_call(update_sensor_ui)
        gui_call(update_graph_ui)

        # Kích hoạt kiểm tra logic tự động sau khi cập nhật dữ liệu cảm biến mới
        process_auto_control()

    except Exception as e:
        sensor_online = False
        gui_call(lambda: sensor_status.configure(text="● SENSOR ERROR", text_color=RED))
        add_sensor_traffic(f"[{now_str}] ❌ LỖI ĐỌC CẢM BIẾN | {e}\n" + "-"*65)

# ==========================================================
# THAO TÁC MODBUS RTU: CƠ CẤU CHẤP HÀNH (SLAVE 255)
# ==========================================================
def toggle_bom():
    global bom_state
    if not rs485_connected or instrument is None: return
    now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    try:
        new_state = not bom_state
        val = 1 if new_state else 0
        with modbus_lock:
            safe_modbus_switch(slave_id=RELAY_SLAVE_ID, baudrate=RELAY_BAUDRATE)
            tx_hex = f"{RELAY_SLAVE_ID:02X} 05 00 00 {'FF 00' if val else '00 00'} CRC16"
            add_actuator_traffic(f"[{now_str}] ➢ GỬI ĐI LỆNH BƠM (TX) | Slave ID: {RELAY_SLAVE_ID} | Bit 0 = {val}\n    Frame Hex: [ {tx_hex} ]")

            instrument.write_bit(registeraddress=0, value=val)

        bom_state = new_state
        rx_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        add_actuator_traffic(f"[{rx_time}] ◄ PHẢN HỒI OK (RX) | Bơm 12V -> {'BẬT' if bom_state else 'TẮT'}\n" + "-"*65)

        gui_call(update_relay_ui)
        add_log(f"Bơm 12V (Relay 1) -> {'BẬT' if bom_state else 'TẮT'}")
    except Exception as e:
        add_actuator_traffic(f"[{now_str}] ❌ LỖI ĐIỀU KHIỂN BƠM | {e}\n" + "-"*65)

def toggle_quat():
    global quat_state
    if not rs485_connected or instrument is None: return
    now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    try:
        new_state = not quat_state
        val = 1 if new_state else 0
        with modbus_lock:
            safe_modbus_switch(slave_id=RELAY_SLAVE_ID, baudrate=RELAY_BAUDRATE)
            tx_hex = f"{RELAY_SLAVE_ID:02X} 05 00 01 {'FF 00' if val else '00 00'} CRC16"
            add_actuator_traffic(f"[{now_str}] ➢ GỬI ĐI LỆNH QUẠT (TX) | Slave ID: {RELAY_SLAVE_ID} | Bit 1 = {val}\n    Frame Hex: [ {tx_hex} ]")

            instrument.write_bit(registeraddress=1, value=val)

        quat_state = new_state
        rx_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        add_actuator_traffic(f"[{rx_time}] ◄ PHẢN HỒI OK (RX) | Quạt 12V -> {'BẬT' if quat_state else 'TẮT'}\n" + "-"*65)

        gui_call(update_relay_ui)
        add_log(f"Quạt 12V (Relay 2) -> {'BẬT' if quat_state else 'TẮT'}")
    except Exception as e:
        add_actuator_traffic(f"[{now_str}] ❌ LỖI ĐIỀU KHIỂN QUẠT | {e}\n" + "-"*65)

def turn_off_all():
    global bom_state, quat_state
    if not rs485_connected or instrument is None: return
    now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    try:
        with modbus_lock:
            safe_modbus_switch(slave_id=RELAY_SLAVE_ID, baudrate=RELAY_BAUDRATE)
            instrument.write_bit(registeraddress=0, value=0)
            instrument.write_bit(registeraddress=1, value=0)
        bom_state = False
        quat_state = False
        add_actuator_traffic(f"[{now_str}] ⛔ LỆNH TẮT TẤT CẢ CƠ CẤU CHẤP HÀNH THÀNH CÔNG\n" + "-"*65)
        gui_call(update_relay_ui)
        add_log("Tắt toàn bộ Bơm & Quạt tại hiện trường")
    except Exception as e:
        add_actuator_traffic(f"[{now_str}] ❌ LỖI TẮT THIẾT BỊ | {e}\n" + "-"*65)

def calibrate_sensor(new_slave_id, new_baudrate):
    global SENSOR_SLAVE_ID, SENSOR_BAUDRATE
    if not rs485_connected or instrument is None:
        add_log("Chưa mở kết nối RS485!", "ERROR")
        return False

    try:
        baud_code_map = {2400: 0, 4800: 1, 9600: 2}
        if new_baudrate not in baud_code_map:
            add_log(f"Baudrate {new_baudrate} không hợp lệ! Vui lòng chọn 2400, 4800, 9600", "ERROR")
            return False

        now_str = datetime.now().strftime("%H:%M:%S")
        with modbus_lock:
            safe_modbus_switch(slave_id=SENSOR_SLAVE_ID, baudrate=SENSOR_BAUDRATE)
            instrument.write_register(registeraddress=0x07D0, value=new_slave_id, functioncode=6)
            time.sleep(0.1)
            instrument.write_register(registeraddress=0x07D1, value=baud_code_map[new_baudrate], functioncode=6)

        SENSOR_SLAVE_ID = new_slave_id
        SENSOR_BAUDRATE = new_baudrate
        add_log(f"✅ Ghi cấu hình thành công! ID mới: {new_slave_id}, Baudrate: {new_baudrate}")
        add_sensor_traffic(f"[{now_str}] ⚙️ HIỆU CHỈNH FC06 OK | New Slave ID = {new_slave_id} | Baudrate = {new_baudrate}\n" + "-"*65)
        return True
    except Exception as e:
        add_log(f"Lỗi ghi cấu hình cảm biến: {e}", "ERROR")
        return False

# ==========================================================
# TRUYỀN NHẬN MẠNG LAN TCP/IP VỚI PC2 SERVER
# ==========================================================
def connect_tcp_lan():
    global tcp_socket, tcp_connected
    if tcp_connected:
        disconnect_tcp_lan()
        return

    ip = entry_pc2_ip.get().strip()
    try:
        port = int(entry_pc2_port.get().strip())
    except ValueError:
        add_log("Port máy chủ PC2 không hợp lệ!", "ERROR")
        return

    def lan_thread():
        global tcp_socket, tcp_connected
        try:
            tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_socket.settimeout(4.0)
            tcp_socket.connect((ip, port))
            tcp_connected = True

            gui_call(lambda: btn_tcp_connect.configure(text="NGẮT MẠNG LAN", fg_color=RED))
            gui_call(lambda: lan_status_label.configure(text=f"● TCP LAN ONLINE ({ip})", text_color=GREEN))
            gui_call(lambda: sidebar_web.configure(text=f"● PC2 SERVER ONLINE", text_color=GREEN))
            add_log(f"Đã kết nối LAN thành công sang PC2 Server ({ip}:{port})")

            listen_pc2_commands()
        except Exception as e:
            tcp_connected = False
            tcp_socket = None
            gui_call(lambda: btn_tcp_connect.configure(text="KẾT NỐI PC2 SERVER", fg_color=BLUE))
            gui_call(lambda: lan_status_label.configure(text="● TCP LAN OFFLINE", text_color=RED))
            gui_call(lambda: sidebar_web.configure(text="● PC2 SERVER OFFLINE", text_color=RED))
            add_log(f"Lỗi kết nối LAN sang PC2: {e}", "ERROR")

    threading.Thread(target=lan_thread, daemon=True).start()

def disconnect_tcp_lan():
    global tcp_socket, tcp_connected
    tcp_connected = False
    try:
        if tcp_socket: tcp_socket.close()
    except Exception: pass
    tcp_socket = None
    btn_tcp_connect.configure(text="KẾT NỐI PC2 SERVER", fg_color=BLUE)
    lan_status_label.configure(text="● TCP LAN OFFLINE", text_color=RED)
    sidebar_web.configure(text="● PC2 SERVER OFFLINE", text_color=RED)
    add_log("Đã ngắt kết nối LAN với PC2 Server")

import json
import socket

def listen_pc2_commands():
    global tcp_socket, tcp_connected
    buffer = ""
    
    # Đặt timeout ngắn (2 giây) để socket không bị treo và vẫn có thể kiểm tra cờ tcp_connected
    if tcp_socket:
        tcp_socket.settimeout(2.0)

    while tcp_connected and tcp_socket:
        try:
            data = tcp_socket.recv(1024)
            if not data:
                # PC2 Server chủ động đóng kết nối
                add_log("PC2 Server đã đóng kết nối TCP.", "WARNING")
                break
                
            buffer += data.decode('utf-8', errors='ignore')
            
            # Cắt chuỗi theo ký tự xuống dòng '\n' để xử lý từng gói tin JSON
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                
                try:
                    cmd_pkt = json.loads(line)
                    action = cmd_pkt.get("action")
                    add_log(f"Nhận lệnh từ PC2 Server: {action}")

                    if action == "toggle_bom":
                        toggle_bom()
                    elif action == "toggle_quat":
                        toggle_quat()
                    elif action == "off_all":
                        turn_off_all()
                    elif action == "calibrate_sensor":
                        new_slave = int(cmd_pkt.get("new_slave_id", SENSOR_SLAVE_ID))
                        new_baud = int(cmd_pkt.get("new_baudrate", SENSOR_BAUDRATE))
                        calibrate_sensor(new_slave, new_baud)
                except Exception as e:
                    add_log(f"Lỗi giải mã JSON/Thực thi lệnh PC2: {e}", "ERROR")

        except (socket.timeout, TimeoutError):
            # Hết 2 giây không nhận được gói tin mới -> Tiếp tục vòng lặp chờ, KHÔNG ngắt mạng
            continue
            
        except Exception as e:
            if tcp_connected:
                add_log(f"Lỗi kết nối Socket LAN: {e}", "ERROR")
            break

    # Tự động dọn dẹp trạng thái kết nối khi thoát vòng lặp
    disconnect_tcp_lan()

def push_packet_to_pc2():
    global last_tcp_tx_time
    packet = {
        "source": "PC1 Gateway",
        "temperature": round(temperature, 1),
        "humidity": round(humidity, 1),
        "bom_status": bom_state,
        "quat_status": quat_state,
        "auto_mode": auto_mode_enabled,
        "temp_threshold": TEMP_AUTO_THRESHOLD,
        "humi_threshold": HUMI_AUTO_THRESHOLD,
        "sensor_online": sensor_online,
        "rs485_online": rs485_connected,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    packet_text = json.dumps(packet, ensure_ascii=False, indent=4)
    gui_call(lambda: update_packet_boxes(packet_text))

    if tcp_connected and tcp_socket:
        try:
            msg = json.dumps(packet) + "\n"
            tcp_socket.sendall(msg.encode('utf-8'))
            last_tcp_tx_time = datetime.now().strftime("%H:%M:%S")
            gui_call(lambda: packet_counter_label.configure(text="Last LAN TX: " + last_tcp_tx_time))
        except Exception as e:
            add_log(f"Lỗi gửi dữ liệu sang PC2: {e}", "ERROR")

def update_packet_boxes(text):
    packet_box.configure(state="normal")
    packet_box.delete("1.0", "end")
    packet_box.insert("end", text)
    packet_box.configure(state="disabled")

# ==========================================================
# CẬP NHẬT GIAO DIỆN CLIENT HMI
# ==========================================================
def toggle_auto_mode():
    global auto_mode_enabled
    auto_mode_enabled = switch_auto_mode.get() == 1
    state_str = "BẬT" if auto_mode_enabled else "TẮT"
    add_log(f"Chế độ Tự Động theo ngưỡng -> {state_str}")

def update_thresholds():
    global TEMP_AUTO_THRESHOLD, HUMI_AUTO_THRESHOLD
    try:
        t_val = float(entry_temp_thresh.get().strip())
        h_val = float(entry_humi_thresh.get().strip())
        TEMP_AUTO_THRESHOLD = t_val
        HUMI_AUTO_THRESHOLD = h_val
        add_log(f"✅ Cập nhật ngưỡng thành công: Bật quạt >= {TEMP_AUTO_THRESHOLD}°C | Bật bơm < {HUMI_AUTO_THRESHOLD}%")
    except ValueError:
        add_log("Giá trị ngưỡng nhập vào không hợp lệ!", "ERROR")

def enable_relay_ui(enable):
    state = "normal" if enable else "disabled"
    btn_bom_toggle.configure(state=state)
    btn_quat_toggle.configure(state=state)
    btn_off_all.configure(state=state)

def update_sensor_ui():
    temp_value.configure(text=f"{temperature:.1f} °C")
    humi_value.configure(text=f"{humidity:.1f} %")
    temp_progress.set(max(0.0, min(temperature / 50.0, 1.0)))
    humi_progress.set(max(0.0, min(humidity / 100.0, 1.0)))
    sensor_status.configure(text="● SENSOR ONLINE", text_color=GREEN)
    sensor_update.configure(text="Update: " + datetime.now().strftime("%H:%M:%S"))

def update_relay_ui():
    lbl_bom_status.configure(text="BƠM BẬT" if bom_state else "ĐANG TẮT", fg_color=GREEN if bom_state else RED)
    btn_bom_toggle.configure(text="TẮT BƠM" if bom_state else "BẬT BƠM", fg_color=RED if bom_state else BLUE)
    lbl_dash_bom.configure(text=f"BƠM: {'BẬT' if bom_state else 'TẮT'}", text_color=GREEN if bom_state else TEXT2)

    lbl_quat_status.configure(text="QUẠT BẬT" if quat_state else "ĐANG TẮT", fg_color=GREEN if quat_state else RED)
    btn_quat_toggle.configure(text="TẮT QUẠT" if quat_state else "BẬT QUẠT", fg_color=RED if quat_state else BLUE)
    lbl_dash_quat.configure(text=f"QUẠT: {'BẬT' if quat_state else 'TẮT'}", text_color=GREEN if quat_state else TEXT2)

# ==========================================================
# THIẾT KẾ CÁC TAB GIAO DIỆN CLIENT (MÁY CLIENT / PC1)
# ==========================================================
sidebar = ctk.CTkFrame(app, width=240, corner_radius=0, fg_color=SIDEBAR)
sidebar.pack(side="left", fill="y")
sidebar.pack_propagate(False)

ctk.CTkLabel(sidebar, text="RTU CLIENT", text_color=CYAN, font=ctk.CTkFont(size=28, weight="bold")).pack(pady=(25, 0))
ctk.CTkLabel(sidebar, text="FIELD GATEWAY & CONTROL", font=ctk.CTkFont(size=11, weight="bold")).pack()

right = ctk.CTkFrame(app, fg_color=BG, corner_radius=0)
right.pack(side="left", fill="both", expand=True)

header = ctk.CTkFrame(right, height=75, fg_color="transparent")
header.pack(fill="x", padx=25, pady=(10, 0))

header_left = ctk.CTkFrame(header, fg_color="transparent")
header_left.pack(side="left")

page_title = ctk.CTkLabel(header_left, text="Giám Sát & Điều Khiển Client", font=ctk.CTkFont(size=24, weight="bold"))
page_title.pack(anchor="w")
ctk.CTkLabel(header_left, text="RS485 Master (COM5)  ➔  PC1 RTU Client  ➔  TCP/IP LAN  ➔  PC2 Server", text_color=TEXT2).pack(anchor="w")

clock_frame = ctk.CTkFrame(header, fg_color="transparent")
clock_frame.pack(side="right")
clock_label = ctk.CTkLabel(clock_frame, text="00:00:00", font=ctk.CTkFont(size=20, weight="bold"))
clock_label.pack()
date_label = ctk.CTkLabel(clock_frame, text="", text_color=TEXT2)
date_label.pack()

# Thanh Cấu Hình Kết Nối Nhanh
comm_bar = ctk.CTkFrame(right, height=50, corner_radius=12, fg_color=CARD)
comm_bar.pack(fill="x", padx=25, pady=8)

rs485_status = ctk.CTkLabel(comm_bar, text="● RS485 OFFLINE", text_color=RED, font=ctk.CTkFont(size=12, weight="bold"))
rs485_status.pack(side="left", padx=15)

com_menu = ctk.CTkOptionMenu(comm_bar, width=100, values=["COM5"], command=on_select_port)
com_menu.pack(side="left", padx=5)

ctk.CTkButton(comm_bar, text="SCAN", width=60, fg_color="#334155", command=scan_ports).pack(side="left", padx=5)

rs485_button = ctk.CTkButton(comm_bar, text="KẾT NỐI RS485", width=120, fg_color=BLUE, command=connect_rs485)
rs485_button.pack(side="left", padx=8)

lan_status_label = ctk.CTkLabel(comm_bar, text="● TCP LAN OFFLINE", text_color=RED, font=ctk.CTkFont(size=12, weight="bold"))
lan_status_label.pack(side="right", padx=15)

page_container = ctk.CTkFrame(right, fg_color=BG, corner_radius=0)
page_container.pack(fill="both", expand=True)

page_names = [
    "Giám Sát & Điều Khiển", 
    "Real-time Chart", 
    "SHT40 Sensor Traffic", 
    "Actuator Traffic", 
    "Hiệu Chỉnh Modbus FC06", 
    "TCP LAN Connection"
]

for p in page_names:
    pages[p] = ctk.CTkFrame(page_container, fg_color=BG)

menu_data = [
    ("Giám Sát & Điều Khiển", "📊"),
    ("Real-time Chart", "📈"),
    ("SHT40 Sensor Traffic", "🌡️"),
    ("Actuator Traffic", "⚡"),
    ("Hiệu Chỉnh Modbus FC06", "⚙️"),
    ("TCP LAN Connection", "🌐")
]

for name, icon in menu_data:
    btn = ctk.CTkButton(sidebar, text=f"{icon}   {name}", height=42, anchor="w", fg_color="transparent", command=lambda n=name: show_page(n))
    btn.pack(fill="x", padx=12, pady=4)
    menu_buttons[name] = btn

side_bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
side_bottom.pack(side="bottom", fill="x", padx=15, pady=15)
sidebar_rs485 = ctk.CTkLabel(side_bottom, text="● RS485 BUS OFFLINE", text_color=RED, font=ctk.CTkFont(size=11, weight="bold"))
sidebar_rs485.pack(anchor="w", pady=2)
sidebar_web = ctk.CTkLabel(side_bottom, text="● PC2 SERVER OFFLINE", text_color=RED, font=ctk.CTkFont(size=11, weight="bold"))
sidebar_web.pack(anchor="w")

# ==========================================================
# TAB 1: MÀN HÌNH CHÍNH CLIENT - GIÁM SÁT & ĐIỀU KHIỂN
# ==========================================================
dash = pages["Giám Sát & Điều Khiển"]

top_cards = ctk.CTkFrame(dash, fg_color="transparent")
top_cards.pack(fill="x", padx=20, pady=10)
top_cards.grid_columnconfigure((0, 1, 2), weight=1)

temp_card = ctk.CTkFrame(top_cards, fg_color=CARD, corner_radius=15)
temp_card.grid(row=0, column=0, padx=8, sticky="nsew")
ctk.CTkLabel(temp_card, text="🌡️ NHIỆT ĐỘ SHT40", text_color=TEXT2, font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(12, 2))
temp_value = ctk.CTkLabel(temp_card, text="--.- °C", text_color=ORANGE, font=ctk.CTkFont(size=30, weight="bold"))
temp_value.pack()
temp_progress = ctk.CTkProgressBar(temp_card, width=160, progress_color=ORANGE)
temp_progress.set(0)
temp_progress.pack(pady=8)

humi_card = ctk.CTkFrame(top_cards, fg_color=CARD, corner_radius=15)
humi_card.grid(row=0, column=1, padx=8, sticky="nsew")
ctk.CTkLabel(humi_card, text="💧 ĐỘ ẨM SHT40", text_color=TEXT2, font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(12, 2))
humi_value = ctk.CTkLabel(humi_card, text="--.- %", text_color=CYAN, font=ctk.CTkFont(size=30, weight="bold"))
humi_value.pack()
humi_progress = ctk.CTkProgressBar(humi_card, width=160, progress_color=CYAN)
humi_progress.set(0)
humi_progress.pack(pady=8)

sensor_card = ctk.CTkFrame(top_cards, fg_color=CARD, corner_radius=15)
sensor_card.grid(row=0, column=2, padx=8, sticky="nsew")
ctk.CTkLabel(sensor_card, text="TRẠNG THÁI HIỆN TRƯỜNG", text_color=TEXT2, font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(12, 2))
sensor_status = ctk.CTkLabel(sensor_card, text="● SENSOR OFFLINE", text_color=RED, font=ctk.CTkFont(weight="bold"))
sensor_status.pack()
lbl_dash_bom = ctk.CTkLabel(sensor_card, text="BƠM: TẮT", text_color=TEXT2, font=ctk.CTkFont(weight="bold"))
lbl_dash_bom.pack()
lbl_dash_quat = ctk.CTkLabel(sensor_card, text="QUẠT: TẮT", text_color=TEXT2, font=ctk.CTkFont(weight="bold"))
lbl_dash_quat.pack()
sensor_update = ctk.CTkLabel(sensor_card, text="Update: --:--:--", text_color=TEXT2, font=ctk.CTkFont(size=10))
sensor_update.pack(pady=(2, 6))

# Khung Cài Đặt Ngưỡng Tự Động & Bảng Điều Khiển Cơ Cấu Chấp Hành
ctrl_box = ctk.CTkFrame(dash, fg_color=CARD, corner_radius=15)
ctrl_box.pack(fill="x", padx=28, pady=10)

# 1. Thanh Toggle Chế độ Tự Động
auto_header_frame = ctk.CTkFrame(ctrl_box, fg_color="transparent")
auto_header_frame.pack(fill="x", padx=20, pady=(12, 4))

ctk.CTkLabel(auto_header_frame, text="⚙️ CÀI ĐẶT NGƯỠNG TỰ ĐỘNG (BẬT QUẠT ≥ 31.0°C | BẬT BƠM < 65.0%)", font=ctk.CTkFont(size=13, weight="bold"), text_color=CYAN).pack(side="left")

switch_auto_mode = ctk.CTkSwitch(auto_header_frame, text="Kích hoạt Auto Mode", font=ctk.CTkFont(size=12, weight="bold"), command=toggle_auto_mode)
switch_auto_mode.select()  # Mặc định bật
switch_auto_mode.pack(side="right")

# 2. Khung Tùy Chỉnh Ngưỡng
f_thresh = ctk.CTkFrame(ctrl_box, fg_color="#0B1220", corner_radius=10)
f_thresh.pack(fill="x", padx=20, pady=6)

ctk.CTkLabel(f_thresh, text="Ngưỡng Bật Quạt (°C):", font=ctk.CTkFont(size=12)).pack(side="left", padx=(15, 5), pady=8)
entry_temp_thresh = ctk.CTkEntry(f_thresh, width=70)
entry_temp_thresh.insert(0, str(TEMP_AUTO_THRESHOLD))
entry_temp_thresh.pack(side="left", padx=5)

ctk.CTkLabel(f_thresh, text="Ngưỡng Bật Bơm (%):", font=ctk.CTkFont(size=12)).pack(side="left", padx=(20, 5), pady=8)
entry_humi_thresh = ctk.CTkEntry(f_thresh, width=70)
entry_humi_thresh.insert(0, str(HUMI_AUTO_THRESHOLD))
entry_humi_thresh.pack(side="left", padx=5)

btn_set_thresh = ctk.CTkButton(f_thresh, text="LƯU NGƯỠNG", width=110, height=28, fg_color=PURPLE, font=ctk.CTkFont(weight="bold"), command=update_thresholds)
btn_set_thresh.pack(side="left", padx=15)

# 3. Nút Điều Khiển Thủ Công
ctk.CTkLabel(ctrl_box, text="BẢNG ĐIỀU KHIỂN CƠ CẤU CHẤP HÀNH THỦ CÔNG", font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(10, 6))

f_btns = ctk.CTkFrame(ctrl_box, fg_color="transparent")
f_btns.pack(fill="x", padx=20, pady=(0, 12))
f_btns.grid_columnconfigure((0, 1, 2), weight=1)

lbl_bom_status = ctk.CTkLabel(f_btns, text="ĐANG TẮT", fg_color=RED, font=ctk.CTkFont(size=13, weight="bold"), corner_radius=8, width=120, height=35)
lbl_bom_status.grid(row=0, column=0, padx=10, pady=5)
btn_bom_toggle = ctk.CTkButton(f_btns, text="BẬT BƠM 12V", font=ctk.CTkFont(size=13, weight="bold"), height=35, fg_color=BLUE, command=toggle_bom, state="disabled")
btn_bom_toggle.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

lbl_quat_status = ctk.CTkLabel(f_btns, text="ĐANG TẮT", fg_color=RED, font=ctk.CTkFont(size=13, weight="bold"), corner_radius=8, width=120, height=35)
lbl_quat_status.grid(row=0, column=1, padx=10, pady=5)
btn_quat_toggle = ctk.CTkButton(f_btns, text="BẬT QUẠT 12V", font=ctk.CTkFont(size=13, weight="bold"), height=35, fg_color=BLUE, command=toggle_quat, state="disabled")
btn_quat_toggle.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

btn_off_all = ctk.CTkButton(f_btns, text="⛔ TẮT TẤT CẢ", font=ctk.CTkFont(size=13, weight="bold"), height=35, fg_color="#D97706", command=turn_off_all, state="disabled")
btn_off_all.grid(row=1, column=2, padx=10, pady=5, sticky="ew")

# ==========================================================
# TAB 2: REAL-TIME CHART
# ==========================================================
chart_page = pages["Real-time Chart"]
chart_frame = ctk.CTkFrame(chart_page, fg_color=CARD, corner_radius=15)
chart_frame.pack(fill="both", expand=True, padx=20, pady=20)

fig = Figure(figsize=(9, 4), facecolor=CARD)
ax1 = fig.add_subplot(211)
ax2 = fig.add_subplot(212)
fig.subplots_adjust(hspace=0.4, left=0.08, right=0.95, top=0.9, bottom=0.15)

def setup_axes():
    for ax, title in zip([ax1, ax2], ["Nhiệt độ (°C)", "Độ ẩm (%)"]):
        ax.set_facecolor("#0B1220")
        ax.set_title(title, color="white", fontsize=10)
        ax.tick_params(colors=TEXT2, labelsize=8)
        ax.grid(True, linestyle="--", alpha=0.3, color="#334155")

setup_axes()
canvas = FigureCanvasTkAgg(fig, master=chart_frame)
canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

def update_graph_ui():
    if not time_data: return
    ax1.clear()
    ax2.clear()
    setup_axes()
    ax1.plot(time_data, temp_data, color=ORANGE, marker="o", linewidth=2)
    ax2.plot(time_data, humi_data, color=CYAN, marker="s", linewidth=2)
    canvas.draw_idle()

# ==========================================================
# TAB 3: TRUYỀN NHẬN CẢM BIẾN SHT40 TRAFFIC
# ==========================================================
sht40_page = pages["SHT40 Sensor Traffic"]
traffic_sens_card = ctk.CTkFrame(sht40_page, fg_color=CARD, corner_radius=15)
traffic_sens_card.pack(fill="both", expand=True, padx=20, pady=15)

ctk.CTkLabel(traffic_sens_card, text="NHẬT KÝ KHUNG TRUYỀN MODBUS HEX: MASTER ↔ SLAVE ID 1 (SHT40)", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=15, pady=10)
sensor_traffic_box = ctk.CTkTextbox(traffic_sens_card, fg_color="#0B1220", font=ctk.CTkFont(family="Consolas", size=11))
sensor_traffic_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
sensor_traffic_box.configure(state="disabled")

# ==========================================================
# TAB 4: TRUYỀN NHẬN CƠ CẤU CHẤP HÀNH TRAFFIC
# ==========================================================
act_page = pages["Actuator Traffic"]
traffic_act_card = ctk.CTkFrame(act_page, fg_color=CARD, corner_radius=15)
traffic_act_card.pack(fill="both", expand=True, padx=20, pady=15)

ctk.CTkLabel(traffic_act_card, text="NHẬT KÝ KHUNG TRUYỀN MODBUS HEX: MASTER ↔ SLAVE ID 255 (RELAY)", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=15, pady=10)
actuator_traffic_box = ctk.CTkTextbox(traffic_act_card, fg_color="#0B1220", font=ctk.CTkFont(family="Consolas", size=11))
actuator_traffic_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
actuator_traffic_box.configure(state="disabled")

# ==========================================================
# TAB 5: HIỆU CHỈNH MODBUS FC06
# ==========================================================
calib_page = pages["Hiệu Chỉnh Modbus FC06"]
calib_card = ctk.CTkFrame(calib_page, fg_color=CARD, corner_radius=15)
calib_card.pack(fill="both", expand=True, padx=25, pady=20)

ctk.CTkLabel(calib_card, text="HIỆU CHỈNH & GHI THANH GHI CẤU HÌNH CẢM BIẾN (FC06)", font=ctk.CTkFont(size=15, weight="bold")).pack(pady=15)

def on_local_calib():
    try:
        new_id = int(entry_calib_id.get().strip())
        new_baud = int(entry_calib_baud.get().strip())
        calibrate_sensor(new_id, new_baud)
    except ValueError:
        add_log("Giá trị nhập vào không hợp lệ!", "ERROR")

f_calib = ctk.CTkFrame(calib_card, fg_color="transparent")
f_calib.pack(pady=10)

ctk.CTkLabel(f_calib, text="Slave ID Mới (1-247):").grid(row=0, column=0, padx=10, pady=8)
entry_calib_id = ctk.CTkEntry(f_calib, placeholder_text="1")
entry_calib_id.grid(row=0, column=1, padx=10, pady=8)

ctk.CTkLabel(f_calib, text="Baudrate Mới (2400/4800/9600):").grid(row=1, column=0, padx=10, pady=8)
entry_calib_baud = ctk.CTkEntry(f_calib, placeholder_text="4800")
entry_calib_baud.grid(row=1, column=1, padx=10, pady=8)

ctk.CTkButton(calib_card, text="GHI CẤU HÌNH XUỐNG CẢM BIẾN", fg_color=GREEN, font=ctk.CTkFont(weight="bold"), height=42, command=on_local_calib).pack(pady=15)

# ==========================================================
# TAB 6: KẾT NỐI TCP LAN & PACKET JSON
# ==========================================================
lan_page = pages["TCP LAN Connection"]

cfg_container = ctk.CTkFrame(lan_page, fg_color="transparent")
cfg_container.pack(fill="x", padx=20, pady=10)
cfg_container.grid_columnconfigure((0, 1), weight=1)

rs485_cfg_card = ctk.CTkFrame(cfg_container, fg_color=CARD, corner_radius=15)
rs485_cfg_card.grid(row=0, column=0, padx=8, sticky="nsew")

ctk.CTkLabel(rs485_cfg_card, text="BUS RS485 HIỆN TRƯỜNG", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=10)
rs485_page_port = ctk.CTkLabel(rs485_cfg_card, text="COM5", text_color=BLUE, font=ctk.CTkFont(size=22, weight="bold"))
rs485_page_port.pack()
rs485_page_status = ctk.CTkLabel(rs485_cfg_card, text="OFFLINE", text_color=RED, font=ctk.CTkFont(size=14, weight="bold"))
rs485_page_status.pack(pady=5)

network_card = ctk.CTkFrame(cfg_container, fg_color=CARD, corner_radius=15)
network_card.grid(row=0, column=1, padx=8, sticky="nsew")

ctk.CTkLabel(network_card, text="MẠNG TCP LAN SANG PC2 SERVER", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=15, pady=8)

f_ip = ctk.CTkFrame(network_card, fg_color="transparent")
f_ip.pack(fill="x", padx=15, pady=2)
ctk.CTkLabel(f_ip, text="IP PC2:").pack(side="left", padx=5)
entry_pc2_ip = ctk.CTkEntry(f_ip, width=140)
entry_pc2_ip.insert(0, DEFAULT_PC2_IP)
entry_pc2_ip.pack(side="right", padx=5)

f_port = ctk.CTkFrame(network_card, fg_color="transparent")
f_port.pack(fill="x", padx=15, pady=2)
ctk.CTkLabel(f_port, text="Port TCP:").pack(side="left", padx=5)
entry_pc2_port = ctk.CTkEntry(f_port, width=140)
entry_pc2_port.insert(0, str(DEFAULT_PC2_PORT))
entry_pc2_port.pack(side="right", padx=5)

btn_tcp_connect = ctk.CTkButton(network_card, text="KẾT NỐI PC2 SERVER", fg_color=BLUE, font=ctk.CTkFont(weight="bold"), height=35, command=connect_tcp_lan)
btn_tcp_connect.pack(fill="x", padx=15, pady=8)

packet_card = ctk.CTkFrame(lan_page, fg_color=CARD, corner_radius=15)
packet_card.pack(fill="both", expand=True, padx=20, pady=10)
packet_counter_label = ctk.CTkLabel(packet_card, text="Last LAN TX: --:--:--", text_color=TEXT2)
packet_counter_label.pack(anchor="e", padx=15, pady=(8, 0))
packet_box = ctk.CTkTextbox(packet_card, fg_color="#0B1220", font=ctk.CTkFont(family="Consolas", size=11))
packet_box.pack(fill="both", expand=True, padx=12, pady=8)
packet_box.configure(state="disabled")

# SYSTEM LOG
log_frame = ctk.CTkFrame(right, fg_color=CARD, corner_radius=12)
log_frame.pack(fill="x", padx=25, pady=(0, 10))
ctk.CTkLabel(log_frame, text="SYSTEM LOG", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(4, 0))
log_box = ctk.CTkTextbox(log_frame, height=75, fg_color="#0B1220", font=ctk.CTkFont(family="Consolas", size=10))
log_box.pack(fill="x", padx=10, pady=(0, 6))
log_box.configure(state="disabled")

# ==========================================================
# POLLING LOOP & THOÁT
# ==========================================================
def polling_loop():
    while running:
        if rs485_connected:
            read_sensor()
        push_packet_to_pc2()
        time.sleep(1.5)

def on_close():
    global running
    running = False
    disconnect_tcp_lan()
    disconnect_rs485()
    app.destroy()

app.protocol("WM_DELETE_WINDOW", on_close)

# KHỞI CHẠY CLIENT
scan_ports()
update_clock()
show_page("Giám Sát & Điều Khiển")
add_log("Hệ thống RTU Client PC1 đã khởi chạy thành công.")

threading.Thread(target=polling_loop, daemon=True).start()

app.mainloop()