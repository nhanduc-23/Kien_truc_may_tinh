import csv
import json
import os
import socket
import threading
import time
from datetime import datetime

import customtkinter as ctk
import matplotlib
import requests
from flask import Flask, jsonify, render_template_string, request

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

# Cấu hình mặc định Blynk Cloud API
BLYNK_TEMPLATE_ID = "TMPLxxxxxx"
BLYNK_AUTH_TOKEN = "YOUR_BLYNK_AUTH_TOKEN"  # Thay Token Blynk tại đây
BLYNK_API_URL = "https://sgp1.blynk.cloud/external/api/"

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

time_history = []
temp_history = []
humi_history = []
MAX_POINTS = 30

blynk_sync_enabled = False
blynk_last_sync = "--:--:--"

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
                if running: add_log(f"Lỗi chấp nhận kết nối TCP: {e}", "ERROR")
    except Exception as e:
        add_log(f"Lỗi khởi chạy TCP Server: {e}", "ERROR")

def handle_pc1_connection(client_sock):
    global pc1_connected, latest_data
    buffer = ""
    while running and pc1_connected:
        try:
            data = client_sock.recv(1024)
            if not data: break
            buffer += data.decode('utf-8')
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if not line.strip(): continue
                try:
                    pkt = json.loads(line)
                    latest_data.update(pkt)

                    # Lưu lịch sử biểu đồ
                    t_str = datetime.now().strftime("%H:%M:%S")
                    time_history.append(t_str)
                    temp_history.append(latest_data.get("temperature", 0.0))
                    humi_history.append(latest_data.get("humidity", 0.0))

                    if len(time_history) > MAX_POINTS:
                        time_history.pop(0)
                        temp_history.pop(0)
                        humi_history.pop(0)

                    gui_call(update_hmi_ui)
                    gui_call(update_chart_ui)

                    # Đồng bộ sang Blynk Cloud nếu được bật
                    if blynk_sync_enabled:
                        sync_to_blynk_cloud()

                except Exception as e:
                    add_log(f"Lỗi giải mã JSON từ PC1: {e}", "ERROR")
        except Exception:
            break

    pc1_connected = False
    gui_call(lambda: lan_client_status.configure(text="● PC1 CLIENT OFFLINE", text_color=RED))
    add_log("PC1 Client đã ngắt kết nối LAN!")

# ==========================================================
# FLASK WEB SERVER (CHO WEB DASHBOARD & INTERNET CLOUDFLARE)
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
        .card { background: #151E2E; padding: 22px; border-radius: 15px; border: 1px solid #1B2638; width: 240px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
        .card h3 { margin-top: 0; color: #94A3B8; font-size: 15px; }
        .value { font-size: 34px; font-weight: bold; color: #F59E0B; margin: 12px 0; }
        .value-blue { color: #06B6D4; }
        .status { padding: 6px 14px; border-radius: 20px; color: white; font-weight: bold; font-size: 13px; display: inline-block; }
        .on { background-color: #22C55E; }
        .off { background-color: #EF4444; }
        .btn { border: none; padding: 10px 18px; margin-top: 12px; border-radius: 8px; cursor: pointer; font-weight: bold; color: white; width: 100%; font-size: 14px; }
        .btn-blue { background-color: #3B82F6; }
        .btn-blue:hover { background-color: #1D4ED8; }
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
        <button class="btn btn-red" style="width: 200px;" onclick="controlDevice('off_all')">⛔ TẮT TẤT CẢ THIẾT BỊ</button>
    </div>

    <script>
        function updateWeb() {
            fetch('/api/data')
                .then(res => res.json())
                .then(data => {
                    document.getElementById('temp').innerText = data.temperature.toFixed(1);
                    document.getElementById('humi').innerText = data.humidity.toFixed(1);
                    document.getElementById('time').innerText = data.timestamp;
                    document.getElementById('temp_th').innerText = data.temp_threshold;
                    document.getElementById('humi_th').innerText = data.humi_threshold;

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
    req = request.get_json()
    action = req.get("action")
    if action in ["toggle_bom", "toggle_quat", "off_all"]:
        send_command_to_pc1(action)
        return jsonify({"status": "success", "action": action})
    return jsonify({"status": "failed", "reason": "Invalid action"}), 400

def start_flask_web():
    flask_app.run(host='0.0.0.0', port=WEB_PORT, debug=False, use_reloader=False)

# ==========================================================
# ĐỒNG BỘ BLYNK IOT CLOUD (HTTP REST API)
# ==========================================================
def sync_to_blynk_cloud():
    global blynk_last_sync
    token = entry_blynk_token.get().strip() or BLYNK_AUTH_TOKEN
    if not token or token == "YOUR_BLYNK_AUTH_TOKEN":
        return

    try:
        # V0: Nhiệt độ, V1: Độ ẩm, V2: Trạng thái Bơm (0/1), V3: Trạng thái Quạt (0/1)
        url_temp = f"{BLYNK_API_URL}update?token={token}&v0={latest_data.get('temperature', 0.0)}"
        url_humi = f"{BLYNK_API_URL}update?token={token}&v1={latest_data.get('humidity', 0.0)}"
        url_bom  = f"{BLYNK_API_URL}update?token={token}&v2={1 if latest_data.get('bom_status') else 0}"
        url_quat = f"{BLYNK_API_URL}update?token={token}&v3={1 if latest_data.get('quat_status') else 0}"

        requests.get(url_temp, timeout=2.0)
        requests.get(url_humi, timeout=2.0)
        requests.get(url_bom, timeout=2.0)
        requests.get(url_quat, timeout=2.0)

        blynk_last_sync = datetime.now().strftime("%H:%M:%S")
        gui_call(lambda: lbl_blynk_sync_time.configure(text="Last Sync: " + blynk_last_sync))
    except Exception as e:
        pass

def toggle_blynk_sync():
    global blynk_sync_enabled
    blynk_sync_enabled = switch_blynk.get() == 1
    state_str = "BẬT" if blynk_sync_enabled else "TẮT"
    add_log(f"Đồng bộ Blynk Cloud REST API -> {state_str}")

# ==========================================================
# CẬP NHẬT GIAO DIỆN HMI CENTRAL
# ==========================================================
def update_hmi_ui():
    lbl_hmi_temp.configure(text=f"{latest_data.get('temperature', 0.0):.1f} °C")
    lbl_hmi_humi.configure(text=f"{latest_data.get('humidity', 0.0):.1f} %")

    bom_on = latest_data.get('bom_status', False)
    quat_on = latest_data.get('quat_status', False)

    lbl_hmi_bom_status.configure(text="BƠM BẬT" if bom_on else "ĐANG TẮT", fg_color=GREEN if bom_on else RED)
    lbl_hmi_quat_status.configure(text="QUẠT BẬT" if quat_on else "ĐANG TẮT", fg_color=GREEN if quat_on else RED)

    lbl_last_update.configure(text="Update: " + latest_data.get('timestamp', '--:--:--'))

def export_csv_report():
    try:
        filename = f"report_pc2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(filename, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Time", "Temperature (C)", "Humidity (%)"])
            for t, temp, humi in zip(time_history, temp_history, humi_history):
                writer.writerow([t, temp, humi])
        add_log(f"✅ Đã xuất báo cáo CSV thành công: {filename}")
    except Exception as e:
        add_log(f"Lỗi xuất CSV: {e}", "ERROR")

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
lbl_last_update = ctk.CTkLabel(card3, text="Update: --:--:--", text_color=TEXT, font=ctk.CTkFont(size=14, weight="bold"))
lbl_last_update.pack(pady=4)
ctk.CTkButton(card3, text="📊 XUẤT FILE BÁO CÁO CSV", fg_color="#334155", command=export_csv_report).pack(pady=6)

# Bảng Điều Khiển Cơ Cấu Chấp Hành Gửi Lệnh Sang PC1
ctrl_box = ctk.CTkFrame(dash, fg_color=CARD, corner_radius=15)
ctrl_box.pack(fill="x", padx=28, pady=15)

ctk.CTkLabel(ctrl_box, text="BẢNG ĐIỀU KHIỂN THIẾT BỊ TỪ MÁY CHỦ HOST (GỬI TCP LAN SANG PC1)", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 10))

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

def update_chart_ui():
    if not time_history: return
    ax1.clear()
    ax2.clear()
    setup_axes()
    ax1.plot(time_history, temp_history, color=ORANGE, marker="o", linewidth=2)
    ax2.plot(time_history, humi_history, color=CYAN, marker="s", linewidth=2)
    canvas.draw_idle()

# ==========================================================
# TAB 3: WEB DASHBOARD & CLOUDFLARE INSTRUCTIONS
# ==========================================================
web_page = pages["Web Dashboard & Cloudflare"]
web_card = ctk.CTkFrame(web_page, fg_color=CARD, corner_radius=15)
web_card.pack(fill="both", expand=True, padx=25, pady=20)

ctk.CTkLabel(web_card, text="HƯỚNG DẪN ĐẨY WEB DASHBOARD LÊN ONLINE INTERNET (CLOUDFLARE TUNNEL)", font=ctk.CTkFont(size=14, weight="bold"), text_color=CYAN).pack(pady=15)

info_txt = (
    "1. Web Server nội bộ đang hoạt động tại địa chỉ: http://127.0.0.1:5000\n\n"
    "2. Để mở đường truy cập Online cho máy Client từ xa qua Internet (không cần chung Wi-Fi/LAN):\n"
    "   - Mở CMD tại thư mục chứa file 'cloudflared.exe'\n"
    "   - Chạy lệnh sau:\n"
    "         cloudflared.exe tunnel --url http://127.0.0.1:5000\n\n"
    "3. Copy đường link dạng: https://...trycloudflare.com gửi cho máy Client hoặc mở trên điện thoại!"
)

lbl_info = ctk.CTkLabel(web_card, text=info_txt, font=ctk.CTkFont(family="Consolas", size=13), justify="left")
lbl_info.pack(padx=20, pady=10)

# ==========================================================
# TAB 4: BLYNK IOT CONFIG & STATUS
# ==========================================================
blynk_page = pages["Blynk IoT Config"]
blynk_card = ctk.CTkFrame(blynk_page, fg_color=CARD, corner_radius=15)
blynk_card.pack(fill="both", expand=True, padx=25, pady=20)

ctk.CTkLabel(blynk_card, text="CẤU HÌNH ĐỒNG BỘ BLYNK IOT CLOUD (HTTP REST API)", font=ctk.CTkFont(size=15, weight="bold")).pack(pady=15)

f_blynk = ctk.CTkFrame(blynk_card, fg_color="transparent")
f_blynk.pack(pady=10)

ctk.CTkLabel(f_blynk, text="Blynk Auth Token:").grid(row=0, column=0, padx=10, pady=8)
entry_blynk_token = ctk.CTkEntry(f_blynk, width=280, placeholder_text="Nhập Token Blynk tại đây...")
entry_blynk_token.insert(0, BLYNK_AUTH_TOKEN)
entry_blynk_token.grid(row=0, column=1, padx=10, pady=8)

switch_blynk = ctk.CTkSwitch(blynk_card, text="Kích hoạt Sync Blynk REST API", font=ctk.CTkFont(weight="bold"), command=toggle_blynk_sync)
switch_blynk.pack(pady=15)

lbl_blynk_sync_time = ctk.CTkLabel(blynk_card, text="Last Sync: --:--:--", text_color=TEXT2)
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
    global running, pc1_connected
    running = False
    pc1_connected = False
    app.destroy()

app.protocol("WM_DELETE_WINDOW", on_close)

# KHỞI CHẠY SERVER HOST PC2
update_clock()
show_page("Màn Hình HMI Host")
add_log("Hệ thống Máy chủ Host PC2 đã khởi chạy.")

threading.Thread(target=start_tcp_server, daemon=True).start()
threading.Thread(target=start_flask_web, daemon=True).start()

app.mainloop()