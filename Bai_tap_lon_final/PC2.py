import csv
import json
import os
import platform
import re
import socket
import subprocess
import threading
import time
from datetime import datetime

import customtkinter as ctk
import matplotlib
import numpy as np
import requests
from flask import Flask, jsonify, render_template_string, request

# Vá lỗi thiếu os.uname trên Windows cho thư viện BlynkLib
if not hasattr(os, "uname"):
    os.uname = platform.uname

# Nạp thư viện Blynk Socket (giữ thiết bị luôn ONLINE)
try:
    import BlynkLib
except ImportError:
    BlynkLib = None

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# ==========================================================
# CẤU HÌNH HỆ THỐNG PC2 SERVER & HOST
# ==========================================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

TCP_HOST = "0.0.0.0"      # Lắng nghe tất cả card mạng LAN
TCP_PORT = 65432          # Cổng TCP Socket nhận dữ liệu từ PC1

WEB_PORT = 5000           # Cổng Web Dashboard Local (HTTP)
AUTO_CSV_INTERVAL_SEC = 600  # Tự động xuất và ghi đè báo cáo CSV sau mỗi 10 phút (600 giây)

# Cấu hình mặc định Blynk Cloud API
BLYNK_TEMPLATE_ID = "TMPL6Es9WsaUS"
BLYNK_AUTH_TOKEN = "8fsTAgKNzJkw2TrPx-nkEUHIu_r0wgbB"

# Cấu hình đồ thị thời gian thực mượt
MAX_POINTS = 40
CHART_WINDOW_SEC = 45.0     # Cửa sổ trượt liên tục 45 giây
ANIM_TRANSITION_SEC = 0.45  # Thời gian chuyển tiếp mượt khi nhận giá trị mới
CHART_FPS_MS = 40           # Tốc độ làm tươi đồ thị ~25 FPS

# ==========================================================
# BIẾN TOÀN CỤC & DỮ LIỆU HỆ THỐNG
# ==========================================================
pc1_client_socket = None
pc1_connected = False
running = True

latest_data = {
    "temperature": 0.0,
    "humidity": 0.0,
    "bom_status": False,
    "quat_status": False,
    "auto_mode": True,
    "temp_threshold": 31.0,
    "humi_threshold": 65.0,
    "sensor_online": False,
    "rs485_online": False,
    "timestamp": "--:--:--"
}

# Cửa sổ trượt phục vụ vẽ đồ thị Real-time Chart mượt
ts_history = []
temp_history = []
humi_history = []
prev_temp_val = None
prev_humi_val = None
last_sample_ts = 0.0

cur_ylim_temp = None
cur_ylim_humi = None
last_thresh_state = None
last_pc1_t_th = None
last_pc1_h_th = None
thresh_hold_until = 0.0
current_page_name = "Màn Hình HMI Host"

# Danh sách lưu trữ toàn bộ lịch sử từ lúc bật hệ thống cho đến khi tắt (xuất CSV không giới hạn)
full_session_history = []
history_lock = threading.Lock()

# Quản lý tự động xuất và ghi đè báo cáo CSV mỗi 10 phút
auto_csv_filepath = None
auto_csv_last_export_str = None
auto_csv_timer_start = None

# Biến quản lý Blynk Socket Client
blynk_client = None
blynk_active = False
blynk_lock = threading.Lock()

# Quản lý tiến trình Cloudflare Tunnel ngầm
cloudflare_proc = None
cloudflare_url = ""

# ==========================================================
# KHỞI TẠO CỬA SỔ HMI MAIN
# ==========================================================
app = ctk.CTk()
app.title("PC2 CENTRAL SERVER - HMI HOST & IOT GATEWAY")
app.geometry("1480x920")
app.minsize(1280, 750)

BG, SIDEBAR, CARD, CARD2 = "#090E1A", "#111827", "#151E2E", "#1B2638"
TEXT, TEXT2 = "#F8FAFC", "#94A3B8"
BLUE, CYAN, GREEN, RED, ORANGE, PURPLE = "#3B82F6", "#06B6D4", "#22C55E", "#EF4444", "#F59E0B", "#8B5CF6"

pages = {}
menu_buttons = {}

# ==========================================================
# HÀM HỖ TRỢ GUI LOG & CẬP NHẬT
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
    global current_page_name
    current_page_name = page_name
    for page in pages.values():
        page.pack_forget()
    pages[page_name].pack(fill="both", expand=True)
    for name, button in menu_buttons.items():
        button.configure(fg_color="#1D4ED8" if name == page_name else "transparent")
    page_title.configure(text=page_name)
    if page_name == "Real-time Chart":
        render_smooth_chart()

def update_clock():
    now = datetime.now()
    clock_label.configure(text=now.strftime("%H:%M:%S"))
    date_label.configure(text=now.strftime("%d/%m/%Y"))
    app.after(1000, update_clock)

# ==========================================================
# ĐIỀU KHIỂN CHẾ ĐỘ TỰ ĐỘNG & NGƯỠNG TỪ PC2
# ==========================================================
def toggle_auto_mode():
    """Bật / Tắt chế độ Auto từ máy chủ PC2 và bắn lệnh xuống PC1"""
    is_auto = switch_auto_mode.get() == 1
    latest_data["auto_mode"] = is_auto
    send_command_to_pc1("set_auto_mode", {"enabled": is_auto})
    state_str = "BẬT" if is_auto else "TẮT"
    if current_page_name == "Real-time Chart":
        render_smooth_chart()
    add_log(f"PC2 Host: Chế độ Tự Động (Auto Mode) -> {state_str}")

def update_thresholds():
    """Cập nhật 2 ngưỡng nhiệt độ/độ ẩm từ PC2 và đồng bộ xuống PC1"""
    global last_pc1_t_th, last_pc1_h_th, thresh_hold_until
    try:
        t_val = float(entry_temp_thresh.get().strip())
        h_val = float(entry_humi_thresh.get().strip())
        latest_data["temp_threshold"] = t_val
        latest_data["humi_threshold"] = h_val
        last_pc1_t_th = t_val
        last_pc1_h_th = h_val
        thresh_hold_until = time.time() + 3.0

        # Gửi gói tin cập nhật ngưỡng sang PC1 qua TCP LAN
        send_command_to_pc1("set_thresholds", {"temp_threshold": t_val, "humi_threshold": h_val})
        lbl_auto_title.configure(text=f"⚙️ CÀI ĐẶT NGƯỠNG TỰ ĐỘNG (BẬT QUẠT ≥ {t_val:.1f}°C | BẬT BƠM < {h_val:.1f}%)")
        if current_page_name == "Real-time Chart":
            render_smooth_chart()
        add_log(f"✅ Đã lưu cấu hình ngưỡng mới: Bật quạt >= {t_val}°C | Bật bơm < {h_val}%")
    except ValueError:
        add_log("Giá trị ngưỡng nhập vào không hợp lệ!", "ERROR")

# ==========================================================
# TCP SOCKET SERVER (NHẬN DỮ LIỆU TỪ PC1 & GỬI LỆNH)
# ==========================================================
def send_command_to_pc1(action, extra_params=None):
    global pc1_client_socket, pc1_connected
    if not pc1_connected or pc1_client_socket is None:
        add_log("Không thể gửi lệnh: PC1 Client chưa kết nối LAN!", "ERROR")
        return False

    try:
        cmd = {"action": action}
        if extra_params:
            cmd.update(extra_params)
        msg = json.dumps(cmd) + "\n"
        pc1_client_socket.sendall(msg.encode('utf-8'))
        add_log(f"Đã gửi lệnh sang PC1: {action}")
        return True
    except Exception as e:
        add_log(f"Lỗi gửi lệnh sang PC1: {e}", "ERROR")
        pc1_connected = False
        return False

def start_tcp_server():
    global pc1_client_socket, pc1_connected
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_sock.bind((TCP_HOST, TCP_PORT))
        server_sock.listen(5)
        add_log(f"TCP Server đã mở tại port {TCP_PORT}. Chờ PC1 kết nối...")
        gui_call(lambda: server_status_label.configure(text=f"● TCP SERVER LISTENING ({TCP_PORT})", text_color=GREEN))

        while running:
            try:
                client, addr = server_sock.accept()
                pc1_client_socket = client
                pc1_connected = True
                add_log(f"✅ PC1 Client đã kết nối từ địa chỉ: {addr[0]}:{addr[1]}")
                gui_call(lambda: lan_client_status.configure(text=f"● PC1 CLIENT ONLINE ({addr[0]})", text_color=GREEN))

                handle_pc1_connection(client)
            except Exception as e:
                if running:
                    add_log(f"Lỗi chấp nhận kết nối TCP: {e}", "ERROR")
    except Exception as e:
        add_log(f"Lỗi khởi chạy TCP Server: {e}", "ERROR")

def handle_pc1_connection(client_sock):
    global pc1_connected, latest_data, prev_temp_val, prev_humi_val, last_sample_ts
    buffer = ""
    while running and pc1_connected:
        try:
            data = client_sock.recv(1024)
            if not data:
                break
            buffer += data.decode('utf-8')
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if not line.strip():
                    continue
                try:
                    pkt = json.loads(line)
                    latest_data.update(pkt)

                    now_dt = datetime.now()
                    now_ts = time.time()
                    full_ts = now_dt.strftime("%Y-%m-%d %H:%M:%S")

                    t_val = latest_data.get("temperature", 0.0)
                    h_val = latest_data.get("humidity", 0.0)
                    bom_str = "ON" if latest_data.get("bom_status", False) else "OFF"
                    quat_str = "ON" if latest_data.get("quat_status", False) else "OFF"
                    mode_str = "AUTO" if latest_data.get("auto_mode", True) else "MANUAL"

                    with history_lock:
                        # 1. Lưu toàn bộ bản ghi từ lúc bật đến lúc tắt hệ thống (không giới hạn)
                        full_session_history.append((full_ts, t_val, h_val, bom_str, quat_str, mode_str))

                        # 2. Cập nhật bộ đệm chuỗi thời gian cho đồ thị mượt
                        if ts_history and (now_ts - ts_history[-1] > 15.0):
                            ts_history.clear()
                            temp_history.clear()
                            humi_history.clear()

                        prev_temp_val = temp_history[-1] if temp_history else t_val
                        prev_humi_val = humi_history[-1] if humi_history else h_val
                        last_sample_ts = now_ts

                        ts_history.append(now_ts)
                        temp_history.append(t_val)
                        humi_history.append(h_val)

                        if len(ts_history) > MAX_POINTS:
                            ts_history.pop(0)
                            temp_history.pop(0)
                            humi_history.pop(0)

                    gui_call(update_hmi_ui)

                    # Bắn số liệu lên Blynk Cloud qua Socket tức thời
                    if blynk_active:
                        sync_to_blynk_cloud()

                except Exception as e:
                    add_log(f"Lỗi giải mã JSON từ PC1: {e}", "ERROR")
        except Exception:
            break

    pc1_connected = False
    gui_call(lambda: lan_client_status.configure(text="● PC1 CLIENT OFFLINE", text_color=RED))
    add_log("PC1 Client đã ngắt kết nối LAN!")

# ==========================================================
# FLASK WEB SERVER (CHO WEB DASHBOARD NỘI BỘ VÀ CLOUDFLARE)
# ==========================================================
flask_app = Flask(__name__)

HTML_WEB_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PC2 Web Dashboard - Giám Sát Môi Trường</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #090E1A; color: #F8FAFC; margin: 0; padding: 20px; text-align: center; }
        h1 { color: #06B6D4; margin-bottom: 5px; }
        p { color: #94A3B8; }
        .container { display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; margin-top: 25px; }
        .card { background: #151E2E; padding: 22px; border-radius: 15px; border: 1px solid #1B2638; width: 230px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
        .card h3 { margin-top: 0; color: #94A3B8; font-size: 15px; }
        .value { font-size: 34px; font-weight: bold; color: #F59E0B; margin: 12px 0; }
        .value-blue { color: #06B6D4; }
        .status { padding: 6px 14px; border-radius: 20px; color: white; font-weight: bold; font-size: 13px; display: inline-block; }
        .on { background-color: #22C55E; }
        .off { background-color: #EF4444; }
        .btn { border: none; padding: 10px 18px; margin-top: 12px; border-radius: 8px; cursor: pointer; font-weight: bold; color: white; width: 100%; font-size: 14px; }
        .btn-blue { background-color: #3B82F6; }
        .btn-blue:hover { background-color: #1D4ED8; }
        .btn-purple { background-color: #8B5CF6; }
        .btn-purple:hover { background-color: #7C3AED; }
        .btn-red { background-color: #D97706; }
    </style>
</head>
<body>
    <h1>HỆ THỐNG GIÁM SÁT MÔI TRƯỜNG & ĐIỀU KHIỂN ONLINE</h1>
    <p>Máy Chủ Host PC2 | Cập nhật lần cuối: <span id="time">--:--:--</span></p>

    <div class="container">
        <div class="card">
            <h3>🌡️ NHIỆT ĐỘ (SHT40)</h3>
            <div class="value"><span id="temp">--.-</span> °C</div>
            <small style="color:#94A3B8">Ngưỡng Auto Quạt: <b id="temp_th">31</b>°C</small>
        </div>

        <div class="card">
            <h3>💧 ĐỘ ẨM (SHT40)</h3>
            <div class="value value-blue"><span id="humi">--.-</span> %</div>
            <small style="color:#94A3B8">Ngưỡng Auto Bơm: <b id="humi_th">65</b>%</small>
        </div>

        <div class="card">
            <h3>⚙️ CHẾ ĐỘ AUTO</h3>
            <div style="margin: 10px 0;">
                <span id="auto-status" class="status on">AUTO BẬT</span>
            </div>
            <button class="btn btn-purple" onclick="controlDevice('toggle_auto')">BẬT / TẮT AUTO</button>
        </div>

        <div class="card">
            <h3>⚡ ĐIỀU KHIỂN BƠM 12V</h3>
            <div style="margin: 10px 0;">
                <span id="bom-status" class="status off">ĐANG TẮT</span>
            </div>
            <button class="btn btn-blue" onclick="controlDevice('toggle_bom')">BẬT / TẮT BƠM</button>
        </div>

        <div class="card">
            <h3>🌀 ĐIỀU KHIỂN QUẠT 12V</h3>
            <div style="margin: 10px 0;">
                <span id="quat-status" class="status off">ĐANG TẮT</span>
            </div>
            <button class="btn btn-blue" onclick="controlDevice('toggle_quat')">BẬT / TẮT QUẠT</button>
        </div>
    </div>

    <div style="margin-top: 25px;">
        <button class="btn btn-red" style="width: 220px;" onclick="controlDevice('off_all')">⛔ TẮT TẤT CẢ THIẾT BỊ</button>
    </div>

    <script>
        function updateWeb() {
            fetch('/api/data')
                .then(res => res.json())
                .then(data => {
                    document.getElementById('temp').innerText = Number(data.temperature).toFixed(1);
                    document.getElementById('humi').innerText = Number(data.humidity).toFixed(1);
                    document.getElementById('time').innerText = data.timestamp;
                    document.getElementById('temp_th').innerText = data.temp_threshold;
                    document.getElementById('humi_th').innerText = data.humi_threshold;

                    const autoElem = document.getElementById('auto-status');
                    autoElem.innerText = data.auto_mode ? "AUTO BẬT" : "AUTO TẮT";
                    autoElem.className = data.auto_mode ? "status on" : "status off";

                    const bomElem = document.getElementById('bom-status');
                    bomElem.innerText = data.bom_status ? "BƠM BẬT" : "ĐANG TẮT";
                    bomElem.className = data.bom_status ? "status on" : "status off";

                    const quatElem = document.getElementById('quat-status');
                    quatElem.innerText = data.quat_status ? "QUẠT BẬT" : "ĐANG TẮT";
                    quatElem.className = data.quat_status ? "status on" : "status off";
                })
                .catch(err => console.error("Lỗi cập nhật Web:", err));
        }

        function controlDevice(action) {
            fetch('/api/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: action })
            }).then(() => updateWeb());
        }

        setInterval(updateWeb, 1200);
        updateWeb();
    </script>
</body>
</html>
"""

@flask_app.route('/')
def index():
    return render_template_string(HTML_WEB_TEMPLATE)

@flask_app.route('/api/data', methods=['GET'])
def get_web_data():
    return jsonify(latest_data)

@flask_app.route('/api/control', methods=['POST'])
def control_from_web():
    req = request.get_json() or {}
    action = req.get("action")
    if action in ["toggle_bom", "toggle_quat", "off_all"]:
        send_command_to_pc1(action)
        return jsonify({"status": "success", "action": action})
    elif action == "toggle_auto":
        new_state = not latest_data.get("auto_mode", True)
        latest_data["auto_mode"] = new_state
        gui_call(lambda: switch_auto_mode.select() if new_state else switch_auto_mode.deselect())
        send_command_to_pc1("set_auto_mode", {"enabled": new_state})
        add_log(f"Web điều khiển Auto Mode -> {'BẬT' if new_state else 'TẮT'}")
        return jsonify({"status": "success", "auto_mode": new_state})
    return jsonify({"status": "failed", "reason": "Invalid action"}), 400

def start_flask_web():
    flask_app.run(host='0.0.0.0', port=WEB_PORT, debug=False, use_reloader=False)

# ==========================================================
# ĐỒNG BỘ BLYNK IOT CLOUD (SOCKET DUAL-WAY & TRẠNG THÁI ONLINE)
# ==========================================================
def blynk_socket_worker(token):
    global blynk_client, blynk_active
    try:
        blynk_client = BlynkLib.Blynk(token, server="sgp1.blynk.cloud", port=80)

        def on_connected(*args):
            gui_call(lambda: lbl_blynk_sync_time.configure(text="Blynk Status: ● ONLINE", text_color=GREEN))
            add_log("✅ Blynk Cloud Socket đã kết nối: THIẾT BỊ ONLINE (XANH LÁ)")

        def on_disconnected(*args):
            gui_call(lambda: lbl_blynk_sync_time.configure(text="Blynk Status: ● OFFLINE", text_color=RED))
            add_log("Blynk Socket đã ngắt kết nối!", "WARN")

        # Bắt sự kiện khi bấm công tắc Bơm trên Web/App Blynk (Chân V2)
        def handle_v2(value):
            try:
                target_state = (int(value[0]) == 1) if isinstance(value, (list, tuple)) else (int(value) == 1)
                current_state = latest_data.get('bom_status', False)
                if target_state != current_state:
                    send_command_to_pc1("toggle_bom")
            except Exception as err:
                add_log(f"Lỗi xử lý sự kiện V2 (Bơm): {err}", "ERROR")

        # Bắt sự kiện khi bấm công tắc Quạt trên Web/App Blynk (Chân V3)
        def handle_v3(value):
            try:
                target_state = (int(value[0]) == 1) if isinstance(value, (list, tuple)) else (int(value) == 1)
                current_state = latest_data.get('quat_status', False)
                if target_state != current_state:
                    send_command_to_pc1("toggle_quat")
            except Exception as err:
                add_log(f"Lỗi xử lý sự kiện V3 (Quạt): {err}", "ERROR")

        # Đăng ký sự kiện an toàn (khắc phục lỗi thiếu tham số func trên BlynkLib)
        def reg_event(evt, func):
            try:
                blynk_client.on(evt, func)
            except TypeError:
                blynk_client.on(evt)(func)

        reg_event("connected", on_connected)
        reg_event("disconnected", on_disconnected)
        reg_event("V2", handle_v2)
        reg_event("V3", handle_v3)

        gui_call(lambda: lbl_blynk_sync_time.configure(text="Blynk Status: ● ONLINE", text_color=GREEN))

        # Vòng lặp duy trì Heartbeat và lắng nghe sự kiện
        while blynk_active and running:
            with blynk_lock:
                blynk_client.run()
            time.sleep(0.02)

    except Exception as e:
        add_log(f"Lỗi Blynk Socket: {e}", "ERROR")
        gui_call(lambda: lbl_blynk_sync_time.configure(text="Blynk Status: ● LỖI KẾT NỐI", text_color=RED))

def sync_to_blynk_cloud():
    """Bắn trực tiếp thông số V0, V1, V2, V3 lên Blynk qua kết nối Socket"""
    global blynk_client, blynk_active
    if not blynk_active or not blynk_client:
        return

    def async_send():
        try:
            t_val = round(latest_data.get('temperature', 0.0), 1)
            h_val = round(latest_data.get('humidity', 0.0), 1)
            b_val = 1 if latest_data.get('bom_status', False) else 0
            q_val = 1 if latest_data.get('quat_status', False) else 0

            with blynk_lock:
                blynk_client.virtual_write(0, t_val)
                blynk_client.virtual_write(1, h_val)
                blynk_client.virtual_write(2, b_val)
                blynk_client.virtual_write(3, q_val)
        except Exception:
            pass

    threading.Thread(target=async_send, daemon=True).start()

def toggle_blynk_sync():
    """Điều khiển BẬT/TẮT Socket trực tiếp trên giao diện"""
    global blynk_active, blynk_client
    token = entry_blynk_token.get().strip() or BLYNK_AUTH_TOKEN

    if switch_blynk.get() == 1:
        if not BlynkLib:
            add_log("Chưa cài thư viện blynk-library-python! Hãy chạy: pip install blynk-library-python", "ERROR")
            switch_blynk.deselect()
            return
        blynk_active = True
        lbl_blynk_sync_time.configure(text="Blynk Status: Đang kết nối...", text_color=ORANGE)
        add_log("BẬT đồng bộ: Đang khởi tạo Socket giữ kết nối ONLINE...")
        threading.Thread(target=blynk_socket_worker, args=(token,), daemon=True).start()
    else:
        blynk_active = False
        if blynk_client:
            try:
                blynk_client.disconnect()
            except Exception:
                pass
            blynk_client = None
        lbl_blynk_sync_time.configure(text="Blynk Status: ● OFFLINE", text_color=RED)
        add_log("TẮT đồng bộ: Đã ngắt kết nối Blynk Cloud.")

# ==========================================================
# CẬP NHẬT GIAO DIỆN HMI & XUẤT CSV TOÀN BỘ PHIÊN LÀM VIỆC
# ==========================================================
def update_hmi_ui():
    global last_pc1_t_th, last_pc1_h_th
    lbl_hmi_temp.configure(text=f"{latest_data.get('temperature', 0.0):.1f} °C")
    lbl_hmi_humi.configure(text=f"{latest_data.get('humidity', 0.0):.1f} %")

    bom_on = latest_data.get('bom_status', False)
    quat_on = latest_data.get('quat_status', False)
    auto_on = latest_data.get('auto_mode', True)
    t_th = float(latest_data.get('temp_threshold', 31.0))
    h_th = float(latest_data.get('humi_threshold', 65.0))

    lbl_hmi_bom_status.configure(text="BƠM BẬT" if bom_on else "ĐANG TẮT", fg_color=GREEN if bom_on else RED)
    lbl_hmi_quat_status.configure(text="QUẠT BẬT" if quat_on else "ĐANG TẮT", fg_color=GREEN if quat_on else RED)
    lbl_auto_title.configure(text=f"⚙️ CÀI ĐẶT NGƯỠNG TỰ ĐỘNG (BẬT QUẠT ≥ {t_th:.1f}°C | BẬT BƠM < {h_th:.1f}%)")
    lbl_last_update.configure(text=f"Update: {latest_data.get('timestamp', '--:--:--')} ({len(full_session_history)} mẫu)")

    # Đồng bộ công tắc Auto Mode trên PC2 theo gói tin PC1
    if auto_on and switch_auto_mode.get() == 0:
        switch_auto_mode.select()
    elif not auto_on and switch_auto_mode.get() == 1:
        switch_auto_mode.deselect()

    # Chỉ cập nhật ô nhập ngưỡng khi giá trị từ PC1 thực sự thay đổi và người dùng không đang nhập liệu
    if time.time() >= thresh_hold_until:
        focused = app.focus_get()
        temp_widgets = (entry_temp_thresh, getattr(entry_temp_thresh, "_entry", None))
        humi_widgets = (entry_humi_thresh, getattr(entry_humi_thresh, "_entry", None))

        if last_pc1_t_th != t_th and focused not in temp_widgets:
            entry_temp_thresh.delete(0, "end")
            entry_temp_thresh.insert(0, f"{t_th:.1f}")
            last_pc1_t_th = t_th

        if last_pc1_h_th != h_th and focused not in humi_widgets:
            entry_humi_thresh.delete(0, "end")
            entry_humi_thresh.insert(0, f"{h_th:.1f}")
            last_pc1_h_th = h_th

def write_csv_snapshot(full_path, records_snapshot):
    with open(full_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Temperature (C)", "Humidity (%)", "Bom_12V", "Quat_12V", "Mode"])
        writer.writerows(records_snapshot)

def export_csv_report():
    try:
        with history_lock:
            records_snapshot = list(full_session_history)

        if not records_snapshot:
            add_log("Chưa có dữ liệu lịch sử nào để xuất báo cáo CSV!", "WARN")
            return

        current_dir = os.path.dirname(os.path.abspath(__file__))
        filename = f"report_pc2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        full_path = os.path.join(current_dir, filename)

        write_csv_snapshot(full_path, records_snapshot)

        add_log(f"✅ Đã xuất báo cáo CSV thủ công ({len(records_snapshot)} bản ghi): {filename}")
        add_log(f"📁 Lưu tại: {full_path}")
    except Exception as e:
        add_log(f"Lỗi xuất CSV: {e}", "ERROR")

def auto_export_csv_report(silent=False):
    """Tự động xuất và ghi đè toàn bộ dữ liệu tích lũy vào cùng một file báo cáo của phiên chạy"""
    global auto_csv_filepath, auto_csv_last_export_str
    try:
        with history_lock:
            records_snapshot = list(full_session_history)

        if not records_snapshot:
            return

        if auto_csv_filepath is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            filename = f"report_pc2_auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            auto_csv_filepath = os.path.join(current_dir, filename)

        write_csv_snapshot(auto_csv_filepath, records_snapshot)
        auto_csv_last_export_str = datetime.now().strftime("%H:%M:%S")

        if not silent:
            fname = os.path.basename(auto_csv_filepath)
            add_log(f"⏱️ [Auto CSV 10 phút] Đã ghi đè cập nhật ({len(records_snapshot)} bản ghi) vào: {fname}")
    except PermissionError:
        if not silent:
            add_log("⚠️ Không thể tự động ghi đè file CSV vì file đang mở trong Excel. Sẽ thử lại ở chu kỳ sau!", "WARN")
    except Exception as e:
        if not silent:
            add_log(f"Lỗi tự động xuất CSV: {e}", "ERROR")

def auto_csv_export_loop():
    """Vòng lặp đếm thời gian 10 phút (600s) để tự động xuất và ghi đè báo cáo CSV"""
    global auto_csv_timer_start
    while running:
        time.sleep(1.0)
        if not running:
            break

        with history_lock:
            record_count = len(full_session_history)

        if record_count == 0:
            auto_csv_timer_start = None
            gui_call(lambda: lbl_auto_csv_status.configure(text="⏱️ Auto CSV (10 phút): Chờ dữ liệu từ PC1..."))
            continue

        now_ts = time.time()
        if auto_csv_timer_start is None:
            auto_csv_timer_start = now_ts

        elapsed = now_ts - auto_csv_timer_start
        if elapsed >= AUTO_CSV_INTERVAL_SEC:
            auto_csv_timer_start = now_ts
            auto_export_csv_report(silent=False)
            elapsed = 0.0

        remaining = max(0, int(AUTO_CSV_INTERVAL_SEC - elapsed))
        rem_m, rem_s = divmod(remaining, 60)
        if auto_csv_last_export_str:
            status_txt = f"⏱️ Auto CSV: Đã lưu {auto_csv_last_export_str} | Kế tiếp {rem_m:02d}:{rem_s:02d}"
        else:
            status_txt = f"⏱️ Auto CSV (10 phút): Tự lưu sau {rem_m:02d}:{rem_s:02d}"
        gui_call(lambda t=status_txt: lbl_auto_csv_status.configure(text=t))

# ==========================================================
# TỰ ĐỘNG KHỞI TẠO & QUẢN LÝ CLOUDFLARE TUNNEL
# ==========================================================
def find_cloudflared_executable():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(current_dir, "cloudflared.exe"),
        os.path.join(current_dir, "..", "cloudflared.exe"),
        os.path.join(current_dir, "..", "..", "cloudflared.exe"),
        os.path.join(os.getcwd(), "cloudflared.exe"),
        "cloudflared.exe"
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return "cloudflared.exe"

def start_cloudflare_tunnel():
    global cloudflare_proc, cloudflare_url
    if cloudflare_proc and cloudflare_proc.poll() is None:
        add_log("Cloudflare Tunnel đang hoạt động!", "WARN")
        return

    exe_path = find_cloudflared_executable()
    btn_start_cf.configure(state="disabled", text="⏳ ĐANG KHỞI TẠO...")
    lbl_cf_status.configure(text="● TRẠNG THÁI: ĐANG KẾT NỐI TỚI CLOUDFLARE...", text_color=ORANGE)
    entry_cf_url.delete(0, "end")
    entry_cf_url.insert(0, "Đang thiết lập đường hầm bảo mật HTTPS...")

    def runner():
        global cloudflare_proc, cloudflare_url
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            cmd = [exe_path, "tunnel", "--url", f"http://127.0.0.1:{WEB_PORT}"]
            add_log(f"Khởi chạy tiến trình: {' '.join(cmd)}")

            cloudflare_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                startupinfo=startupinfo
            )

            url_found = False

            def read_stream(stream):
                nonlocal url_found
                global cloudflare_url
                for line in iter(stream.readline, ''):
                    if not line:
                        break
                    match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                    if match and not url_found:
                        url_found = True
                        cloudflare_url = match.group(0)
                        add_log(f"✅ Đã tạo link Cloudflare thành công: {cloudflare_url}")
                        gui_call(on_cloudflare_success)
                stream.close()

            t_err = threading.Thread(target=read_stream, args=(cloudflare_proc.stderr,), daemon=True)
            t_out = threading.Thread(target=read_stream, args=(cloudflare_proc.stdout,), daemon=True)
            t_err.start()
            t_out.start()

            cloudflare_proc.wait()
            gui_call(on_cloudflare_stopped)

        except Exception as e:
            add_log(f"Lỗi khởi chạy Cloudflare: {e}", "ERROR")
            gui_call(on_cloudflare_stopped)

    threading.Thread(target=runner, daemon=True).start()

def on_cloudflare_success():
    btn_start_cf.configure(state="disabled", text="✅ TUNNEL ĐANG CHẠY")
    btn_stop_cf.configure(state="normal")
    btn_copy_cf.configure(state="normal")
    lbl_cf_status.configure(text="● TRẠNG THÁI: ONLINE INTERNET", text_color=GREEN)
    entry_cf_url.delete(0, "end")
    entry_cf_url.insert(0, cloudflare_url)

def on_cloudflare_stopped():
    btn_start_cf.configure(state="normal", text="🌐 TẠO LINK CLOUDFLARE ONLINE")
    btn_stop_cf.configure(state="disabled")
    btn_copy_cf.configure(state="disabled")
    lbl_cf_status.configure(text="● TRẠNG THÁI: OFFLINE", text_color=RED)

def stop_cloudflare_tunnel():
    global cloudflare_proc
    if cloudflare_proc and cloudflare_proc.poll() is None:
        try:
            cloudflare_proc.terminate()
            cloudflare_proc.kill()
        except Exception:
            pass
        add_log("Đã dừng Cloudflare Tunnel.")
    on_cloudflare_stopped()

def copy_cloudflare_url():
    url = entry_cf_url.get().strip()
    if url and "trycloudflare.com" in url:
        app.clipboard_clear()
        app.clipboard_append(url)
        lbl_copy_notify.configure(text="✅ ĐÃ SAO CHÉP LINK VÀO CLIPBOARD!", text_color=GREEN)
        app.after(3000, lambda: lbl_copy_notify.configure(text=""))
    else:
        lbl_copy_notify.configure(text="Chưa có link hợp lệ để copy!", text_color=RED)
        app.after(3000, lambda: lbl_copy_notify.configure(text=""))

# ==========================================================
# THIẾT KẾ CÁC TAB GIAO DIỆN PC2 HMI HOST
# ==========================================================
sidebar = ctk.CTkFrame(app, width=240, corner_radius=0, fg_color=SIDEBAR)
sidebar.pack(side="left", fill="y")
sidebar.pack_propagate(False)

ctk.CTkLabel(sidebar, text="PC2 SERVER", text_color=CYAN, font=ctk.CTkFont(size=28, weight="bold")).pack(pady=(25, 0))
ctk.CTkLabel(sidebar, text="HOST & IOT CENTRAL SYSTEM", font=ctk.CTkFont(size=11, weight="bold")).pack()

right = ctk.CTkFrame(app, fg_color=BG, corner_radius=0)
right.pack(side="left", fill="both", expand=True)

header = ctk.CTkFrame(right, height=75, fg_color="transparent")
header.pack(fill="x", padx=25, pady=(10, 0))

header_left = ctk.CTkFrame(header, fg_color="transparent")
header_left.pack(side="left")

page_title = ctk.CTkLabel(header_left, text="Giám Sát Trung Tâm Server Host", font=ctk.CTkFont(size=24, weight="bold"))
page_title.pack(anchor="w")
ctk.CTkLabel(header_left, text="PC1 Gateway ➔ TCP/IP LAN Server (PC2) ➔ Web Dashboard & Blynk Cloud", text_color=TEXT2).pack(anchor="w")

clock_frame = ctk.CTkFrame(header, fg_color="transparent")
clock_frame.pack(side="right")
clock_label = ctk.CTkLabel(clock_frame, text="00:00:00", font=ctk.CTkFont(size=20, weight="bold"))
clock_label.pack()
date_label = ctk.CTkLabel(clock_frame, text="", text_color=TEXT2)
date_label.pack()

# Thanh Trạng Thái Mạng
comm_bar = ctk.CTkFrame(right, height=50, corner_radius=12, fg_color=CARD)
comm_bar.pack(fill="x", padx=25, pady=8)

server_status_label = ctk.CTkLabel(comm_bar, text="● TCP SERVER OFFLINE", text_color=RED, font=ctk.CTkFont(size=12, weight="bold"))
server_status_label.pack(side="left", padx=15)

lan_client_status = ctk.CTkLabel(comm_bar, text="● PC1 CLIENT OFFLINE", text_color=RED, font=ctk.CTkFont(size=12, weight="bold"))
lan_client_status.pack(side="left", padx=15)

web_host_status = ctk.CTkLabel(comm_bar, text=f"● WEB HOST: http://localhost:{WEB_PORT}", text_color=CYAN, font=ctk.CTkFont(size=12, weight="bold"))
web_host_status.pack(side="right", padx=15)

page_container = ctk.CTkFrame(right, fg_color=BG, corner_radius=0)
page_container.pack(fill="both", expand=True)

page_names = ["Màn Hình HMI Host", "Real-time Chart", "Web Dashboard & Cloudflare", "Blynk IoT Config"]

for p in page_names:
    pages[p] = ctk.CTkFrame(page_container, fg_color=BG)

menu_data = [
    ("Màn Hình HMI Host", "🖥️"),
    ("Real-time Chart", "📈"),
    ("Web Dashboard & Cloudflare", "🌐"),
    ("Blynk IoT Config", "📱")
]

for name, icon in menu_data:
    btn = ctk.CTkButton(sidebar, text=f"{icon}   {name}", height=42, anchor="w", fg_color="transparent", command=lambda n=name: show_page(n))
    btn.pack(fill="x", padx=12, pady=4)
    menu_buttons[name] = btn

# ==========================================================
# TAB 1: MÀN HÌNH HMI CHÍNH CỦA HOST
# ==========================================================
dash = pages["Màn Hình HMI Host"]

top_cards = ctk.CTkFrame(dash, fg_color="transparent")
top_cards.pack(fill="x", padx=20, pady=10)
top_cards.grid_columnconfigure((0, 1, 2), weight=1)

card1 = ctk.CTkFrame(top_cards, fg_color=CARD, corner_radius=15)
card1.grid(row=0, column=0, padx=8, sticky="nsew")
ctk.CTkLabel(card1, text="🌡️ NHIỆT ĐỘ TỪ PC1", text_color=TEXT2, font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(12, 2))
lbl_hmi_temp = ctk.CTkLabel(card1, text="--.- °C", text_color=ORANGE, font=ctk.CTkFont(size=32, weight="bold"))
lbl_hmi_temp.pack(pady=10)

card2 = ctk.CTkFrame(top_cards, fg_color=CARD, corner_radius=15)
card2.grid(row=0, column=1, padx=8, sticky="nsew")
ctk.CTkLabel(card2, text="💧 ĐỘ ẨM TỪ PC1", text_color=TEXT2, font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(12, 2))
lbl_hmi_humi = ctk.CTkLabel(card2, text="--.- %", text_color=CYAN, font=ctk.CTkFont(size=32, weight="bold"))
lbl_hmi_humi.pack(pady=10)

card3 = ctk.CTkFrame(top_cards, fg_color=CARD, corner_radius=15)
card3.grid(row=0, column=2, padx=8, sticky="nsew")
ctk.CTkLabel(card3, text="TRẠNG THÁI & LẦN CẬP NHẬT", text_color=TEXT2, font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(12, 2))
lbl_last_update = ctk.CTkLabel(card3, text="Update: --:--:-- (0 mẫu)", text_color=TEXT, font=ctk.CTkFont(size=14, weight="bold"))
lbl_last_update.pack(pady=4)
ctk.CTkButton(card3, text="📊 XUẤT FILE BÁO CÁO CSV", fg_color="#334155", command=export_csv_report).pack(pady=(4, 2))
lbl_auto_csv_status = ctk.CTkLabel(card3, text="⏱️ Auto CSV (10 phút): Chờ dữ liệu từ PC1...", text_color=TEXT2, font=ctk.CTkFont(size=10))
lbl_auto_csv_status.pack(pady=(0, 6))

# KHUNG ĐIỀU KHIỂN & CÀI ĐẶT TỰ ĐỘNG TRÊN PC2
ctrl_box = ctk.CTkFrame(dash, fg_color=CARD, corner_radius=15)
ctrl_box.pack(fill="x", padx=28, pady=10)

# 1. Thanh Toggle Chế độ Tự Động trên PC2
auto_header_frame = ctk.CTkFrame(ctrl_box, fg_color="transparent")
auto_header_frame.pack(fill="x", padx=20, pady=(12, 4))

lbl_auto_title = ctk.CTkLabel(
    auto_header_frame, 
    text="⚙️ CÀI ĐẶT NGƯỠNG TỰ ĐỘNG (BẬT QUẠT ≥ 31.0°C | BẬT BƠM < 65.0%)", 
    font=ctk.CTkFont(size=13, weight="bold"), 
    text_color=CYAN
)
lbl_auto_title.pack(side="left")

switch_auto_mode = ctk.CTkSwitch(
    auto_header_frame, 
    text="Kích hoạt Auto Mode", 
    font=ctk.CTkFont(size=12, weight="bold"), 
    command=toggle_auto_mode
)
switch_auto_mode.select()  # Mặc định bật
switch_auto_mode.pack(side="right")

# 2. Khung Tùy Chỉnh Ngưỡng trên PC2
f_thresh = ctk.CTkFrame(ctrl_box, fg_color="#0B1220", corner_radius=10)
f_thresh.pack(fill="x", padx=20, pady=6)

ctk.CTkLabel(f_thresh, text="Ngưỡng Bật Quạt (°C):", font=ctk.CTkFont(size=12)).pack(side="left", padx=(15, 5), pady=8)
entry_temp_thresh = ctk.CTkEntry(f_thresh, width=70)
entry_temp_thresh.insert(0, "31.0")
entry_temp_thresh.pack(side="left", padx=5)

ctk.CTkLabel(f_thresh, text="Ngưỡng Bật Bơm (%):", font=ctk.CTkFont(size=12)).pack(side="left", padx=(20, 5), pady=8)
entry_humi_thresh = ctk.CTkEntry(f_thresh, width=70)
entry_humi_thresh.insert(0, "65.0")
entry_humi_thresh.pack(side="left", padx=5)

btn_set_thresh = ctk.CTkButton(
    f_thresh, 
    text="LƯU NGƯỠNG SANG PC1", 
    width=160, 
    height=28, 
    fg_color=PURPLE, 
    font=ctk.CTkFont(weight="bold"), 
    command=update_thresholds
)
btn_set_thresh.pack(side="left", padx=15)

# 3. Nút Điều Khiển Cơ Cấu Chấp Hành Thủ Công
ctk.CTkLabel(ctrl_box, text="BẢNG ĐIỀU KHIỂN CƠ CẤU CHẤP HÀNH THỦ CÔNG (GỬI TCP LAN SANG PC1)", font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(10, 6))

f_btns = ctk.CTkFrame(ctrl_box, fg_color="transparent")
f_btns.pack(fill="x", padx=20, pady=(0, 15))
f_btns.grid_columnconfigure((0, 1, 2), weight=1)

lbl_hmi_bom_status = ctk.CTkLabel(f_btns, text="ĐANG TẮT", fg_color=RED, font=ctk.CTkFont(size=13, weight="bold"), corner_radius=8, width=120, height=35)
lbl_hmi_bom_status.grid(row=0, column=0, padx=10, pady=5)
btn_hmi_bom = ctk.CTkButton(f_btns, text="BẬT / TẮT BƠM 12V", font=ctk.CTkFont(size=13, weight="bold"), height=38, fg_color=BLUE, command=lambda: send_command_to_pc1("toggle_bom"))
btn_hmi_bom.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

lbl_hmi_quat_status = ctk.CTkLabel(f_btns, text="ĐANG TẮT", fg_color=RED, font=ctk.CTkFont(size=13, weight="bold"), corner_radius=8, width=120, height=35)
lbl_hmi_quat_status.grid(row=0, column=1, padx=10, pady=5)
btn_hmi_quat = ctk.CTkButton(f_btns, text="BẬT / TẮT QUẠT 12V", font=ctk.CTkFont(size=13, weight="bold"), height=38, fg_color=BLUE, command=lambda: send_command_to_pc1("toggle_quat"))
btn_hmi_quat.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

btn_hmi_off_all = ctk.CTkButton(f_btns, text="⛔ TẮT TẤT CẢ THIẾT BỊ", font=ctk.CTkFont(size=13, weight="bold"), height=38, fg_color="#D97706", command=lambda: send_command_to_pc1("off_all"))
btn_hmi_off_all.grid(row=1, column=2, padx=10, pady=5, sticky="ew")

# ==========================================================
# TAB 2: REAL-TIME CHART (NỘI SUY MƯỢT & CUỘN LIÊN TỤC 25 FPS)
# ==========================================================
chart_page = pages["Real-time Chart"]
chart_frame = ctk.CTkFrame(chart_page, fg_color=CARD, corner_radius=15)
chart_frame.pack(fill="both", expand=True, padx=20, pady=20)

fig = Figure(figsize=(9, 4), facecolor=CARD)
ax1 = fig.add_subplot(211)
ax2 = fig.add_subplot(212)
fig.subplots_adjust(hspace=0.42, left=0.08, right=0.96, top=0.90, bottom=0.14)

for ax, title in zip([ax1, ax2], ["Nhiệt độ (°C) - Real-time", "Độ ẩm (%) - Real-time"]):
    ax.set_facecolor("#0B1220")
    ax.set_title(title, color="white", fontsize=10, fontweight="bold")
    ax.tick_params(colors=TEXT2, labelsize=8)
    ax.grid(True, linestyle="--", alpha=0.3, color="#334155")

DARK_BLUE = "#1D4ED8"

# Khởi tạo đối tượng đồ họa một lần duy nhất (không dùng ax.clear() để chống giật nháy)
line_temp, = ax1.plot([], [], color=ORANGE, linewidth=2.3, antialiased=True)
pts_temp, = ax1.plot([], [], color=ORANGE, linestyle="none", marker="o", markersize=4, alpha=0.55)
head_temp, = ax1.plot([], [], color="#FDE047", linestyle="none", marker="o", markersize=7, markeredgecolor=ORANGE, markeredgewidth=1.5)
thresh_line_temp = ax1.axhline(y=latest_data["temp_threshold"], color=RED, linestyle="--", linewidth=1.8, alpha=0.95, visible=latest_data["auto_mode"])

line_humi, = ax2.plot([], [], color=CYAN, linewidth=2.3, antialiased=True)
pts_humi, = ax2.plot([], [], color=CYAN, linestyle="none", marker="s", markersize=4, alpha=0.55)
head_humi, = ax2.plot([], [], color="#A5F3FC", linestyle="none", marker="o", markersize=7, markeredgecolor=CYAN, markeredgewidth=1.5)
thresh_line_humi = ax2.axhline(y=latest_data["humi_threshold"], color=DARK_BLUE, linestyle="--", linewidth=1.8, alpha=0.95, visible=latest_data["auto_mode"])

canvas = FigureCanvasTkAgg(fig, master=chart_frame)
canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

def compute_smooth_curve(x_arr, y_arr, points_per_segment=8):
    """Nội suy đường cong Hermite đơn điệu (PCHIP) đi qua chính xác các điểm đo, không vọt lố"""
    n = len(x_arr)
    if n < 2:
        return np.asarray(x_arr, dtype=float), np.asarray(y_arr, dtype=float)
    x = np.asarray(x_arr, dtype=float)
    y = np.asarray(y_arr, dtype=float)
    dx = np.diff(x)
    dy = np.diff(y)
    dx = np.where(dx <= 1e-6, 1e-6, dx)
    m = dy / dx

    d = np.zeros(n)
    d[0] = m[0]
    d[-1] = m[-1]
    for i in range(1, n - 1):
        if m[i - 1] * m[i] <= 0:
            d[i] = 0.0
        else:
            w1 = 2 * dx[i] + dx[i - 1]
            w2 = dx[i] + 2 * dx[i - 1]
            d[i] = (w1 + w2) / (w1 / m[i - 1] + w2 / m[i])

    xs, ys = [], []
    for i in range(n - 1):
        t = np.linspace(0, 1, points_per_segment, endpoint=(i == n - 2))
        h = dx[i]
        t2 = t * t
        t3 = t2 * t
        h00 = 2 * t3 - 3 * t2 + 1
        h10 = t3 - 2 * t2 + t
        h01 = -2 * t3 + 3 * t2
        h11 = t3 - t2
        xs.append(x[i] + t * h)
        ys.append(h00 * y[i] + h10 * h * d[i] + h01 * y[i + 1] + h11 * h * d[i + 1])
    return np.concatenate(xs), np.concatenate(ys)

def sync_chart_thresholds():
    global last_thresh_state
    is_auto = bool(latest_data.get("auto_mode", True))
    t_th = float(latest_data.get("temp_threshold", 31.0))
    h_th = float(latest_data.get("humi_threshold", 65.0))
    cur_state = (is_auto, t_th, h_th)
    if cur_state != last_thresh_state:
        last_thresh_state = cur_state

        thresh_line_temp.set_ydata([t_th, t_th])
        thresh_line_temp.set_visible(is_auto)
        thresh_line_temp.set_label(f"Ngưỡng Bật Quạt ({t_th:.1f}°C)")

        thresh_line_humi.set_ydata([h_th, h_th])
        thresh_line_humi.set_visible(is_auto)
        thresh_line_humi.set_label(f"Ngưỡng Bật Bơm ({h_th:.1f}%)")

        if is_auto:
            ax1.legend(handles=[thresh_line_temp], loc="upper right", facecolor="#111827", edgecolor="#334155", labelcolor="#FCA5A5", fontsize=8.5)
            ax2.legend(handles=[thresh_line_humi], loc="upper right", facecolor="#111827", edgecolor="#334155", labelcolor="#93C5FD", fontsize=8.5)
        else:
            if ax1.get_legend() is not None:
                ax1.get_legend().remove()
            if ax2.get_legend() is not None:
                ax2.get_legend().remove()
        return True
    return False

def render_smooth_chart():
    global cur_ylim_temp, cur_ylim_humi
    thresh_changed = sync_chart_thresholds()
    is_auto = bool(latest_data.get("auto_mode", True))
    t_th = float(latest_data.get("temp_threshold", 31.0))
    h_th = float(latest_data.get("humi_threshold", 65.0))

    with history_lock:
        if not ts_history:
            if thresh_changed:
                if is_auto:
                    ax1.set_ylim(t_th - 2.0, t_th + 2.0)
                    ax2.set_ylim(h_th - 5.0, h_th + 5.0)
                canvas.draw_idle()
            return
        xs = list(ts_history)
        ys_t = list(temp_history)
        ys_h = list(humi_history)
        p_t = prev_temp_val if prev_temp_val is not None else ys_t[-1]
        p_h = prev_humi_val if prev_humi_val is not None else ys_h[-1]
        t_last = last_sample_ts

    now_ts = time.time()

    # 1. Hiệu ứng chuyển tiếp giá trị mượt mà (Ease-out cubic) trong 0.45s đầu khi có mẫu mới
    alpha = min(1.0, max(0.0, (now_ts - t_last) / ANIM_TRANSITION_SEC))
    ease = 1.0 - (1.0 - alpha) ** 3
    cur_t = p_t + (ys_t[-1] - p_t) * ease
    cur_h = p_h + (ys_h[-1] - p_h) * ease
    ys_t[-1] = cur_t
    ys_h[-1] = cur_h

    # Lưu tọa độ các điểm đo thực tế để hiển thị nút chấm
    raw_x = list(xs)
    raw_t = list(ys_t)
    raw_h = list(ys_h)

    # 2. Kéo dài đầu mút trực tuyến mượt mà theo thời gian thực giữa 2 chu kỳ lấy mẫu
    dt_tail = now_ts - xs[-1]
    if dt_tail > 0.01:
        xs.append(xs[-1] + min(dt_tail, 2.0))
        ys_t.append(cur_t)
        ys_h.append(cur_h)

    sx_t, sy_t = compute_smooth_curve(xs, ys_t, points_per_segment=8)
    sx_h, sy_h = compute_smooth_curve(xs, ys_h, points_per_segment=8)

    line_temp.set_data(sx_t, sy_t)
    pts_temp.set_data(raw_x, raw_t)
    head_temp.set_data([xs[-1]], [ys_t[-1]])

    line_humi.set_data(sx_h, sy_h)
    pts_humi.set_data(raw_x, raw_h)
    head_humi.set_data([xs[-1]], [ys_h[-1]])

    # 3. Trượt trục ngang liên tục 45 giây và giữ đúng 12 mốc thời gian cách đều
    x_right = xs[-1]
    x_left = x_right - CHART_WINDOW_SEC
    ticks = np.linspace(x_left, x_right, 12)
    tick_labels = [datetime.fromtimestamp(ts).strftime("%H:%M:%S") for ts in ticks]

    for ax in (ax1, ax2):
        ax.set_xlim(x_left, x_right)
        ax.set_xticks(ticks)
        ax.set_xticklabels(tick_labels)

    # 4. Tự động co giãn trục đứng (Y-axis) có giảm chấn mượt, chống nhảy trục đột ngột
    vis_t = [y for x, y in zip(xs, ys_t) if x >= x_left] or ys_t
    vis_h = [y for x, y in zip(xs, ys_h) if x >= x_left] or ys_h

    if is_auto:
        vis_t = vis_t + [t_th]
        vis_h = vis_h + [h_th]

    t_min, t_max = min(vis_t), max(vis_t)
    t_pad = max(0.6, (t_max - t_min) * 0.25)
    target_t = [t_min - t_pad, t_max + t_pad]
    if cur_ylim_temp is None:
        cur_ylim_temp = list(target_t)
    else:
        cur_ylim_temp[0] += (target_t[0] - cur_ylim_temp[0]) * 0.18
        cur_ylim_temp[1] += (target_t[1] - cur_ylim_temp[1]) * 0.18
    ax1.set_ylim(cur_ylim_temp[0], cur_ylim_temp[1])

    h_min, h_max = min(vis_h), max(vis_h)
    h_pad = max(1.0, (h_max - h_min) * 0.25)
    target_h = [h_min - h_pad, h_max + h_pad]
    if cur_ylim_humi is None:
        cur_ylim_humi = list(target_h)
    else:
        cur_ylim_humi[0] += (target_h[0] - cur_ylim_humi[0]) * 0.18
        cur_ylim_humi[1] += (target_h[1] - cur_ylim_humi[1]) * 0.18
    ax2.set_ylim(cur_ylim_humi[0], cur_ylim_humi[1])

    canvas.draw_idle()

def chart_animation_loop():
    if running:
        if current_page_name == "Real-time Chart":
            render_smooth_chart()
        app.after(CHART_FPS_MS, chart_animation_loop)

# ==========================================================
# TAB 3: WEB DASHBOARD & CLOUDFLARE TỰ ĐỘNG PHÁT LINK
# ==========================================================
web_page = pages["Web Dashboard & Cloudflare"]
web_card = ctk.CTkFrame(web_page, fg_color=CARD, corner_radius=15)
web_card.pack(fill="both", expand=True, padx=25, pady=20)

ctk.CTkLabel(web_card, text="CLOUDFLARE TUNNEL - TỰ ĐỘNG PHÁT LINK TRUY CẬP ONLINE", font=ctk.CTkFont(size=16, weight="bold"), text_color=CYAN).pack(pady=(20, 10))

cf_ctrl_frame = ctk.CTkFrame(web_card, fg_color="transparent")
cf_ctrl_frame.pack(fill="x", padx=40, pady=10)

btn_start_cf = ctk.CTkButton(
    cf_ctrl_frame,
    text="🌐 TẠO LINK CLOUDFLARE ONLINE",
    font=ctk.CTkFont(size=13, weight="bold"),
    height=42,
    fg_color=BLUE,
    hover_color="#1D4ED8",
    command=start_cloudflare_tunnel
)
btn_start_cf.pack(side="left", padx=10, expand=True, fill="x")

btn_stop_cf = ctk.CTkButton(
    cf_ctrl_frame,
    text="⛔ DỪNG TUNNEL",
    font=ctk.CTkFont(size=13, weight="bold"),
    height=42,
    fg_color=RED,
    hover_color="#DC2626",
    state="disabled",
    command=stop_cloudflare_tunnel
)
btn_stop_cf.pack(side="left", padx=10, expand=True, fill="x")

lbl_cf_status = ctk.CTkLabel(web_card, text="● TRẠNG THÁI: OFFLINE", font=ctk.CTkFont(size=13, weight="bold"), text_color=RED)
lbl_cf_status.pack(pady=5)

link_box_frame = ctk.CTkFrame(web_card, fg_color=CARD2, corner_radius=12)
link_box_frame.pack(fill="x", padx=40, pady=15)

ctk.CTkLabel(link_box_frame, text="ĐƯỜNG LINK TRUY CẬP TỪ XA QUA INTERNET:", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT2).pack(anchor="w", padx=15, pady=(10, 4))

entry_row = ctk.CTkFrame(link_box_frame, fg_color="transparent")
entry_row.pack(fill="x", padx=15, pady=(0, 10))

entry_cf_url = ctk.CTkEntry(entry_row, font=ctk.CTkFont(family="Consolas", size=13), height=40, text_color="#38BDF8")
entry_cf_url.insert(0, "Chưa khởi tạo. Nhấn 'TẠO LINK CLOUDFLARE ONLINE' để lấy link...")
entry_cf_url.pack(side="left", fill="x", expand=True, padx=(0, 10))

btn_copy_cf = ctk.CTkButton(
    entry_row,
    text="📋 SAO CHÉP (COPY)",
    font=ctk.CTkFont(size=12, weight="bold"),
    height=40,
    width=140,
    fg_color=GREEN,
    hover_color="#16A34A",
    state="disabled",
    command=copy_cloudflare_url
)
btn_copy_cf.pack(side="right")

lbl_copy_notify = ctk.CTkLabel(link_box_frame, text="", font=ctk.CTkFont(size=11, weight="bold"))
lbl_copy_notify.pack(pady=(0, 5))

info_card = ctk.CTkFrame(web_card, fg_color="#0B1220", corner_radius=10)
info_card.pack(fill="x", padx=40, pady=(10, 20))
desc_text = (
    "ℹ️ Nguyên lý hoạt động:\n"
    "• Hệ thống tự động khởi chạy file 'cloudflared.exe' tạo một đường hầm mã hóa an toàn (Secure Tunnel).\n"
    "• Cổng Web nội bộ (Port 5000) được ánh xạ trực tiếp ra địa chỉ tên miền HTTPS toàn cầu của Cloudflare.\n"
    "• Bất kỳ ai có đường link trên (kể cả dùng 4G/5G hoặc ngoài mạng LAN) đều có thể theo dõi và bật/tắt Bơm & Quạt."
)
ctk.CTkLabel(info_card, text=desc_text, font=ctk.CTkFont(family="Consolas", size=11), text_color=TEXT2, justify="left").pack(anchor="w", padx=15, pady=10)

# ==========================================================
# TAB 4: BLYNK IOT CONFIG & STATUS (DUAL SOCKET ONLINE)
# ==========================================================
blynk_page = pages["Blynk IoT Config"]
blynk_card = ctk.CTkFrame(blynk_page, fg_color=CARD, corner_radius=15)
blynk_card.pack(fill="both", expand=True, padx=25, pady=20)

ctk.CTkLabel(blynk_card, text="CẤU HÌNH ĐỒNG BỘ BLYNK IOT CLOUD (SOCKET)", font=ctk.CTkFont(size=15, weight="bold")).pack(pady=15)

f_blynk = ctk.CTkFrame(blynk_card, fg_color="transparent")
f_blynk.pack(pady=10)

ctk.CTkLabel(f_blynk, text="Blynk Auth Token:").grid(row=0, column=0, padx=10, pady=8)
entry_blynk_token = ctk.CTkEntry(f_blynk, width=280, placeholder_text="Nhập Token Blynk tại đây...")
entry_blynk_token.insert(0, BLYNK_AUTH_TOKEN)
entry_blynk_token.grid(row=0, column=1, padx=10, pady=8)

switch_blynk = ctk.CTkSwitch(blynk_card, text="Kích hoạt Sync Blynk (Online Mode)", font=ctk.CTkFont(weight="bold"), command=toggle_blynk_sync)
switch_blynk.pack(pady=15)

lbl_blynk_sync_time = ctk.CTkLabel(blynk_card, text="Blynk Status: ● OFFLINE", font=ctk.CTkFont(size=13, weight="bold"), text_color=RED)
lbl_blynk_sync_time.pack()

# SYSTEM LOG
log_frame = ctk.CTkFrame(right, fg_color=CARD, corner_radius=12)
log_frame.pack(fill="x", padx=25, pady=(0, 10))
ctk.CTkLabel(log_frame, text="SYSTEM LOG", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(4, 0))
log_box = ctk.CTkTextbox(log_frame, height=75, fg_color="#0B1220", font=ctk.CTkFont(family="Consolas", size=10))
log_box.pack(fill="x", padx=10, pady=(0, 6))
log_box.configure(state="disabled")

# ==========================================================
# KHỞI CHẠY LỒNG THREAD & THOÁT
# ==========================================================
def on_close():
    global running, pc1_connected, cloudflare_proc, blynk_active, blynk_client
    if auto_csv_filepath is not None:
        auto_export_csv_report(silent=True)
    running = False
    pc1_connected = False
    blynk_active = False
    if blynk_client:
        try:
            blynk_client.disconnect()
        except Exception:
            pass
    if cloudflare_proc and cloudflare_proc.poll() is None:
        try:
            cloudflare_proc.terminate()
            cloudflare_proc.kill()
        except Exception:
            pass
    app.destroy()

app.protocol("WM_DELETE_WINDOW", on_close)

# KHỞI CHẠY SERVER HOST PC2
update_clock()
chart_animation_loop()
show_page("Màn Hình HMI Host")
add_log("Hệ thống Máy chủ Host PC2 đã khởi chạy.")

threading.Thread(target=start_tcp_server, daemon=True).start()
threading.Thread(target=start_flask_web, daemon=True).start()
threading.Thread(target=auto_csv_export_loop, daemon=True).start()

app.mainloop()