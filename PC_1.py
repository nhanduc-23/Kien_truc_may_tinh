import customtkinter as ctk
import tkinter as tk

import minimalmodbus
import serial
from serial.tools import list_ports

import socket
import threading
import json
import time
from datetime import datetime


# ==========================================================
# APP
# ==========================================================

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("PC1 - RS485 Data Gateway")
app.geometry("1400x850")
app.minsize(1200, 720)


# ==========================================================
# COLORS
# ==========================================================

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
# CONFIG
# ==========================================================

SENSOR_SLAVE_ID = 1

BAUDRATE = 9600
TIMEOUT = 0.5

TCP_HOST = "0.0.0.0"
TCP_PORT = 5000


# ==========================================================
# SYSTEM VARIABLES
# ==========================================================

instrument = None

rs485_connected = False
sensor_online = False
pc2_connected = False

temperature = 0.0
humidity = 0.0

client_socket = None
client_address = None

running = True

modbus_lock = threading.Lock()
tcp_lock = threading.Lock()

latest_packet = {}

pages = {}
menu_buttons = {}


# ==========================================================
# GUI SAFE
# ==========================================================

def gui_call(func):
    app.after(0, func)


# ==========================================================
# LOG
# ==========================================================

def add_log(message, level="INFO"):

    def write_log():

        now = datetime.now().strftime("%H:%M:%S")

        log_box.configure(state="normal")
        log_box.insert(
            "end",
            f"[{now}] [{level}] {message}\n"
        )
        log_box.see("end")
        log_box.configure(state="disabled")

    gui_call(write_log)


# ==========================================================
# PAGE SWITCHING
# ==========================================================

def show_page(page_name):

    for page in pages.values():
        page.pack_forget()

    pages[page_name].pack(
        fill="both",
        expand=True
    )

    for name, button in menu_buttons.items():

        if name == page_name:
            button.configure(
                fg_color="#1D4ED8"
            )
        else:
            button.configure(
                fg_color="transparent"
            )

    page_title.configure(
        text=page_name
    )


# ==========================================================
# CLOCK
# ==========================================================

def update_clock():

    now = datetime.now()

    clock_label.configure(
        text=now.strftime("%H:%M:%S")
    )

    date_label.configure(
        text=now.strftime("%d/%m/%Y")
    )

    app.after(
        1000,
        update_clock
    )


# ==========================================================
# SCAN COM
# ==========================================================

def scan_ports():

    ports = [
        port.device
        for port in list_ports.comports()
    ]

    if not ports:
        ports = ["Không tìm thấy COM"]

    com_menu.configure(
        values=ports
    )

    com_menu.set(
        ports[0]
    )

    rs485_page_port.configure(
        text=ports[0]
    )

    add_log(
        f"Scan COM: {ports}"
    )


# ==========================================================
# RS485 CONNECT
# ==========================================================

def connect_rs485():

    global instrument
    global rs485_connected

    if rs485_connected:
        disconnect_rs485()
        return

    port = com_menu.get()

    if "Không tìm" in port:
        return

    try:

        instrument = minimalmodbus.Instrument(
            port,
            SENSOR_SLAVE_ID
        )

        instrument.serial.baudrate = BAUDRATE
        instrument.serial.bytesize = 8
        instrument.serial.parity = serial.PARITY_NONE
        instrument.serial.stopbits = 1
        instrument.serial.timeout = TIMEOUT

        instrument.mode = minimalmodbus.MODE_RTU

        instrument.clear_buffers_before_each_transaction = True

        rs485_connected = True

        rs485_status.configure(
            text="● RS485 ONLINE",
            text_color=GREEN
        )

        rs485_button.configure(
            text="NGẮT RS485",
            fg_color=RED
        )

        sidebar_rs485.configure(
            text="● RS485 BUS ONLINE",
            text_color=GREEN
        )

        rs485_page_status.configure(
            text="ONLINE",
            text_color=GREEN
        )

        add_log(
            f"Đã kết nối {port} @ {BAUDRATE} baud"
        )

    except Exception as e:

        rs485_connected = False

        add_log(
            f"Lỗi RS485: {e}",
            "ERROR"
        )


def disconnect_rs485():

    global rs485_connected
    global sensor_online

    rs485_connected = False
    sensor_online = False

    try:
        if instrument:
            instrument.serial.close()
    except:
        pass

    rs485_status.configure(
        text="● RS485 OFFLINE",
        text_color=RED
    )

    rs485_button.configure(
        text="KẾT NỐI RS485",
        fg_color=BLUE
    )

    sidebar_rs485.configure(
        text="● RS485 BUS OFFLINE",
        text_color=RED
    )

    rs485_page_status.configure(
        text="OFFLINE",
        text_color=RED
    )

    sensor_status.configure(
        text="● SENSOR OFFLINE",
        text_color=RED
    )

    add_log(
        "Đã ngắt RS485"
    )


# ==========================================================
# READ SENSOR
# ==========================================================

def read_sensor():

    global temperature
    global humidity
    global sensor_online

    if not rs485_connected:
        return

    try:

        with modbus_lock:

            instrument.address = SENSOR_SLAVE_ID

            raw_temp = instrument.read_register(
                0x0000,
                0,
                functioncode=3
            )

            raw_humi = instrument.read_register(
                0x0001,
                0,
                functioncode=3
            )

        temperature = raw_temp / 10.0
        humidity = raw_humi / 10.0

        sensor_online = True

        gui_call(
            update_sensor_ui
        )

        gui_call(
            lambda: add_rs485_traffic(
                f"[{datetime.now().strftime('%H:%M:%S')}] "
                f"RX | Slave={SENSOR_SLAVE_ID} | "
                f"FC03 | T={temperature:.1f}°C | "
                f"H={humidity:.1f}%"
            )
        )

    except Exception as e:

        sensor_online = False

        gui_call(
            lambda: sensor_status.configure(
                text="● SENSOR ERROR",
                text_color=RED
            )
        )

        gui_call(
            lambda: add_rs485_traffic(
                f"[{datetime.now().strftime('%H:%M:%S')}] "
                f"ERROR | {e}"
            )
        )

        add_log(
            f"Lỗi đọc sensor: {e}",
            "ERROR"
        )


def update_sensor_ui():

    temp_value.configure(
        text=f"{temperature:.1f} °C"
    )

    humi_value.configure(
        text=f"{humidity:.1f} %"
    )

    temp_progress.set(
        max(
            0,
            min(
                temperature / 50,
                1
            )
        )
    )

    humi_progress.set(
        max(
            0,
            min(
                humidity / 100,
                1
            )
        )
    )

    sensor_status.configure(
        text="● SENSOR ONLINE",
        text_color=GREEN
    )

    sensor_update.configure(
        text=
        "Update: "
        + datetime.now().strftime(
            "%H:%M:%S"
        )
    )

    rs485_page_temp.configure(
        text=f"{temperature:.1f} °C"
    )

    rs485_page_humi.configure(
        text=f"{humidity:.1f} %"
    )


# ==========================================================
# RS485 TRAFFIC
# ==========================================================

def add_rs485_traffic(text):

    rs485_monitor_box.configure(
        state="normal"
    )

    rs485_monitor_box.insert(
        "end",
        text + "\n"
    )

    rs485_monitor_box.see("end")

    rs485_monitor_box.configure(
        state="disabled"
    )


# ==========================================================
# BUILD PACKET
# ==========================================================

def build_packet():

    global latest_packet

    latest_packet = {

        "source": "PC1",

        "temperature":
            round(
                temperature,
                1
            ),

        "humidity":
            round(
                humidity,
                1
            ),

        "sensor_online":
            sensor_online,

        "rs485_online":
            rs485_connected,

        "timestamp":
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
    }

    packet_text = json.dumps(
        latest_packet,
        ensure_ascii=False,
        indent=4
    )

    def update_packet_boxes():

        packet_box.configure(
            state="normal"
        )

        packet_box.delete(
            "1.0",
            "end"
        )

        packet_box.insert(
            "end",
            packet_text
        )

        packet_box.configure(
            state="disabled"
        )


        packet_page_box.configure(
            state="normal"
        )

        packet_page_box.delete(
            "1.0",
            "end"
        )

        packet_page_box.insert(
            "end",
            packet_text
        )

        packet_page_box.configure(
            state="disabled"
        )

    gui_call(
        update_packet_boxes
    )

    return latest_packet


# ==========================================================
# SEND TO PC2
# ==========================================================

def send_packet_to_pc2():

    global pc2_connected

    if not pc2_connected:
        return

    packet = build_packet()

    message = (
        json.dumps(
            packet,
            ensure_ascii=False
        )
        + "\n"
    )

    try:

        with tcp_lock:

            client_socket.sendall(
                message.encode("utf-8")
            )

        gui_call(
            lambda:
            packet_counter_label.configure(
                text=
                "Last TX: "
                + datetime.now().strftime(
                    "%H:%M:%S"
                )
            )
        )

        gui_call(
            lambda:
            lan_last_tx.configure(
                text=
                datetime.now().strftime(
                    "%H:%M:%S"
                )
            )
        )

    except Exception as e:

        pc2_connected = False

        add_log(
            f"Mất kết nối PC2: {e}",
            "ERROR"
        )

        gui_call(
            update_pc2_status
        )


# ==========================================================
# TCP SERVER
# ==========================================================

def tcp_server():

    global client_socket
    global client_address
    global pc2_connected

    server = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )

    server.bind(
        (
            TCP_HOST,
            TCP_PORT
        )
    )

    server.listen(1)

    add_log(
        f"TCP Server chạy tại port {TCP_PORT}"
    )

    while running:

        try:

            client_socket, client_address = (
                server.accept()
            )

            pc2_connected = True

            add_log(
                f"PC2 connected: "
                f"{client_address[0]}:"
                f"{client_address[1]}"
            )

            gui_call(
                update_pc2_status
            )

            while running and pc2_connected:

                send_packet_to_pc2()

                time.sleep(1)

        except Exception as e:

            if running:

                add_log(
                    f"TCP error: {e}",
                    "ERROR"
                )

        finally:

            pc2_connected = False

            try:
                if client_socket:
                    client_socket.close()
            except:
                pass

            gui_call(
                update_pc2_status
            )


# ==========================================================
# TCP STATUS
# ==========================================================

def update_pc2_status():

    if pc2_connected:

        pc2_status.configure(
            text="● PC2 CONNECTED",
            text_color=GREEN
        )

        sidebar_lan.configure(
            text="● LAN CONNECTED",
            text_color=GREEN
        )

        lan_page_status.configure(
            text="CONNECTED",
            text_color=GREEN
        )

        if client_address:

            address = (
                f"{client_address[0]}:"
                f"{client_address[1]}"
            )

            pc2_address.configure(
                text=address
            )

            lan_pc2_address.configure(
                text=address
            )

    else:

        pc2_status.configure(
            text="● WAITING PC2",
            text_color=ORANGE
        )

        sidebar_lan.configure(
            text="● LAN WAITING",
            text_color=ORANGE
        )

        lan_page_status.configure(
            text="WAITING",
            text_color=ORANGE
        )

        pc2_address.configure(
            text="--"
        )

        lan_pc2_address.configure(
            text="--"
        )


# ==========================================================
# POLLING
# ==========================================================

def polling_loop():

    while running:

        if rs485_connected:
            read_sensor()

        build_packet()

        time.sleep(1)


# ==========================================================
# MAIN LAYOUT
# ==========================================================

sidebar = ctk.CTkFrame(
    app,
    width=220,
    corner_radius=0,
    fg_color=SIDEBAR
)

sidebar.pack(
    side="left",
    fill="y"
)

sidebar.pack_propagate(False)


# ==========================================================
# SIDEBAR LOGO
# ==========================================================

ctk.CTkLabel(
    sidebar,
    text="NEXUS",
    text_color=CYAN,
    font=ctk.CTkFont(
        size=30,
        weight="bold"
    )
).pack(
    pady=(35, 0)
)


ctk.CTkLabel(
    sidebar,
    text="DATA GATEWAY",
    font=ctk.CTkFont(
        size=13,
        weight="bold"
    )
).pack()


ctk.CTkLabel(
    sidebar,
    text="PC1 INDUSTRIAL NODE",
    text_color=TEXT2,
    font=ctk.CTkFont(
        size=10
    )
).pack(
    pady=(5, 35)
)


# ==========================================================
# RIGHT
# ==========================================================

right = ctk.CTkFrame(
    app,
    fg_color=BG,
    corner_radius=0
)

right.pack(
    side="left",
    fill="both",
    expand=True
)


# ==========================================================
# HEADER
# ==========================================================

header = ctk.CTkFrame(
    right,
    height=90,
    fg_color="transparent"
)

header.pack(
    fill="x",
    padx=30,
    pady=(10, 0)
)


header.pack_propagate(False)


header_left = ctk.CTkFrame(
    header,
    fg_color="transparent"
)

header_left.pack(
    side="left"
)


page_title = ctk.CTkLabel(
    header_left,
    text="Gateway Monitor",
    font=ctk.CTkFont(
        size=29,
        weight="bold"
    )
)

page_title.pack(
    anchor="w"
)


ctk.CTkLabel(
    header_left,
    text=(
        "RS485 → PC1 Gateway → TCP/IP → PC2"
    ),
    text_color=TEXT2
).pack(
    anchor="w"
)


clock_frame = ctk.CTkFrame(
    header,
    fg_color="transparent"
)

clock_frame.pack(
    side="right"
)


clock_label = ctk.CTkLabel(
    clock_frame,
    text="00:00:00",
    font=ctk.CTkFont(
        size=23,
        weight="bold"
    )
)

clock_label.pack()


date_label = ctk.CTkLabel(
    clock_frame,
    text="",
    text_color=TEXT2
)

date_label.pack()


# ==========================================================
# COMMUNICATION BAR
# ==========================================================

comm_bar = ctk.CTkFrame(
    right,
    height=60,
    corner_radius=15,
    fg_color=CARD
)

comm_bar.pack(
    fill="x",
    padx=30,
    pady=(0, 10)
)


rs485_status = ctk.CTkLabel(
    comm_bar,
    text="● RS485 OFFLINE",
    text_color=RED,
    font=ctk.CTkFont(
        size=12,
        weight="bold"
    )
)

rs485_status.pack(
    side="left",
    padx=20
)


com_menu = ctk.CTkOptionMenu(
    comm_bar,
    width=110,
    values=["COM3"]
)

com_menu.pack(
    side="left",
    padx=5
)


ctk.CTkButton(
    comm_bar,
    text="SCAN",
    width=70,
    fg_color="#334155",
    command=scan_ports
).pack(
    side="left",
    padx=5
)


rs485_button = ctk.CTkButton(
    comm_bar,
    text="KẾT NỐI RS485",
    width=140,
    fg_color=BLUE,
    command=connect_rs485
)

rs485_button.pack(
    side="left",
    padx=10
)


pc2_status = ctk.CTkLabel(
    comm_bar,
    text="● WAITING PC2",
    text_color=ORANGE,
    font=ctk.CTkFont(
        size=12,
        weight="bold"
    )
)

pc2_status.pack(
    side="right",
    padx=20
)


# ==========================================================
# PAGE CONTAINER
# ==========================================================

page_container = ctk.CTkFrame(
    right,
    fg_color=BG,
    corner_radius=0
)

page_container.pack(
    fill="both",
    expand=True
)


for page_name in [
    "Gateway Monitor",
    "RS485 Monitor",
    "TCP / LAN",
    "Data Packet"
]:

    pages[page_name] = ctk.CTkFrame(
        page_container,
        fg_color=BG
    )


# ==========================================================
# SIDEBAR BUTTONS
# ==========================================================

menu_data = [
    ("Gateway Monitor", "⌂"),
    ("RS485 Monitor", "◉"),
    ("TCP / LAN", "⇄"),
    ("Data Packet", "▦")
]


for name, icon in menu_data:

    button = ctk.CTkButton(
        sidebar,
        text=f"{icon}     {name}",
        height=46,
        anchor="w",
        corner_radius=10,
        fg_color="transparent",
        hover_color="#1E293B",

        command=lambda n=name:
            show_page(n)
    )

    button.pack(
        fill="x",
        padx=18,
        pady=5
    )

    menu_buttons[name] = button


# ==========================================================
# SIDEBAR BOTTOM
# ==========================================================

side_bottom = ctk.CTkFrame(
    sidebar,
    fg_color="transparent"
)

side_bottom.pack(
    side="bottom",
    fill="x",
    padx=20,
    pady=25
)


ctk.CTkLabel(
    side_bottom,
    text="COMMUNICATION",
    text_color=TEXT2,
    font=ctk.CTkFont(
        size=10,
        weight="bold"
    )
).pack(
    anchor="w"
)


sidebar_rs485 = ctk.CTkLabel(
    side_bottom,
    text="● RS485 BUS OFFLINE",
    text_color=RED,
    font=ctk.CTkFont(
        size=11,
        weight="bold"
    )
)

sidebar_rs485.pack(
    anchor="w",
    pady=4
)


sidebar_lan = ctk.CTkLabel(
    side_bottom,
    text="● LAN WAITING",
    text_color=ORANGE,
    font=ctk.CTkFont(
        size=11,
        weight="bold"
    )
)

sidebar_lan.pack(
    anchor="w"
)


# ==========================================================
# PAGE 1 - GATEWAY MONITOR
# ==========================================================

gateway = pages["Gateway Monitor"]


top_cards = ctk.CTkFrame(
    gateway,
    fg_color="transparent"
)

top_cards.pack(
    fill="x",
    padx=20,
    pady=10
)


top_cards.grid_columnconfigure(
    (0, 1, 2),
    weight=1
)


# TEMP

temp_card = ctk.CTkFrame(
    top_cards,
    fg_color=CARD,
    corner_radius=20
)

temp_card.grid(
    row=0,
    column=0,
    padx=10,
    sticky="nsew"
)


ctk.CTkLabel(
    temp_card,
    text="🌡  NHIỆT ĐỘ",
    text_color=TEXT2,
    font=ctk.CTkFont(
        size=14,
        weight="bold"
    )
).pack(
    pady=(25, 10)
)


temp_value = ctk.CTkLabel(
    temp_card,
    text="--.- °C",
    text_color=ORANGE,
    font=ctk.CTkFont(
        size=40,
        weight="bold"
    )
)

temp_value.pack(
    pady=10
)


temp_progress = ctk.CTkProgressBar(
    temp_card,
    width=230,
    progress_color=ORANGE
)

temp_progress.set(0)

temp_progress.pack(
    pady=15
)


ctk.CTkLabel(
    temp_card,
    text="Register 0x0000 • FC03",
    text_color=TEXT2
).pack(
    pady=(0, 20)
)


# HUMI

humi_card = ctk.CTkFrame(
    top_cards,
    fg_color=CARD,
    corner_radius=20
)

humi_card.grid(
    row=0,
    column=1,
    padx=10,
    sticky="nsew"
)


ctk.CTkLabel(
    humi_card,
    text="💧  ĐỘ ẨM",
    text_color=TEXT2,
    font=ctk.CTkFont(
        size=14,
        weight="bold"
    )
).pack(
    pady=(25, 10)
)


humi_value = ctk.CTkLabel(
    humi_card,
    text="--.- %",
    text_color=CYAN,
    font=ctk.CTkFont(
        size=40,
        weight="bold"
    )
)

humi_value.pack(
    pady=10
)


humi_progress = ctk.CTkProgressBar(
    humi_card,
    width=230,
    progress_color=CYAN
)

humi_progress.set(0)

humi_progress.pack(
    pady=15
)


ctk.CTkLabel(
    humi_card,
    text="Register 0x0001 • FC03",
    text_color=TEXT2
).pack(
    pady=(0, 20)
)


# SENSOR STATUS

sensor_card = ctk.CTkFrame(
    top_cards,
    fg_color=CARD,
    corner_radius=20
)

sensor_card.grid(
    row=0,
    column=2,
    padx=10,
    sticky="nsew"
)


ctk.CTkLabel(
    sensor_card,
    text="FIELD DEVICE",
    text_color=TEXT2,
    font=ctk.CTkFont(
        size=14,
        weight="bold"
    )
).pack(
    pady=(30, 15)
)


sensor_status = ctk.CTkLabel(
    sensor_card,
    text="● SENSOR OFFLINE",
    text_color=RED,
    font=ctk.CTkFont(
        size=15,
        weight="bold"
    )
)

sensor_status.pack(
    pady=10
)


ctk.CTkLabel(
    sensor_card,
    text=f"Slave ID: {SENSOR_SLAVE_ID}",
    text_color=TEXT2
).pack()


sensor_update = ctk.CTkLabel(
    sensor_card,
    text="Update: --:--:--",
    text_color=TEXT2
)

sensor_update.pack(
    pady=10
)


# BOTTOM

gateway_bottom = ctk.CTkFrame(
    gateway,
    fg_color="transparent"
)

gateway_bottom.pack(
    fill="both",
    expand=True,
    padx=20,
    pady=10
)


gateway_bottom.grid_columnconfigure(
    (0, 1),
    weight=1
)


packet_card = ctk.CTkFrame(
    gateway_bottom,
    fg_color=CARD,
    corner_radius=20
)

packet_card.grid(
    row=0,
    column=0,
    padx=10,
    sticky="nsew"
)


packet_counter_label = ctk.CTkLabel(
    packet_card,
    text="Last TX: --:--:--",
    text_color=TEXT2
)

packet_counter_label.pack(
    anchor="e",
    padx=20,
    pady=(15, 0)
)


packet_box = ctk.CTkTextbox(
    packet_card,
    fg_color="#0B1220",
    font=ctk.CTkFont(
        family="Consolas",
        size=12
    )
)

packet_box.pack(
    fill="both",
    expand=True,
    padx=15,
    pady=15
)

packet_box.configure(
    state="disabled"
)


network_card = ctk.CTkFrame(
    gateway_bottom,
    fg_color=CARD,
    corner_radius=20
)

network_card.grid(
    row=0,
    column=1,
    padx=10,
    sticky="nsew"
)


ctk.CTkLabel(
    network_card,
    text="LAN / TCP SERVER",
    font=ctk.CTkFont(
        size=16,
        weight="bold"
    )
).pack(
    anchor="w",
    padx=20,
    pady=20
)


def info_row(parent, title, value):

    row = ctk.CTkFrame(
        parent,
        fg_color=CARD2,
        corner_radius=10
    )

    row.pack(
        fill="x",
        padx=20,
        pady=6
    )

    ctk.CTkLabel(
        row,
        text=title,
        text_color=TEXT2
    ).pack(
        side="left",
        padx=15,
        pady=12
    )

    label = ctk.CTkLabel(
        row,
        text=value,
        font=ctk.CTkFont(
            weight="bold"
        )
    )

    label.pack(
        side="right",
        padx=15
    )

    return label


info_row(
    network_card,
    "Listen",
    "0.0.0.0"
)

info_row(
    network_card,
    "TCP Port",
    str(TCP_PORT)
)

pc2_address = info_row(
    network_card,
    "PC2 Client",
    "--"
)

info_row(
    network_card,
    "Protocol",
    "TCP / JSON"
)


# ==========================================================
# PAGE 2 - RS485 MONITOR
# ==========================================================

rs485_page = pages["RS485 Monitor"]


rs485_cards = ctk.CTkFrame(
    rs485_page,
    fg_color="transparent"
)

rs485_cards.pack(
    fill="x",
    padx=20,
    pady=20
)

rs485_cards.grid_columnconfigure(
    (0, 1, 2, 3),
    weight=1
)


def stat_card(parent, column, title, value, color):

    card = ctk.CTkFrame(
        parent,
        fg_color=CARD,
        corner_radius=18
    )

    card.grid(
        row=0,
        column=column,
        padx=8,
        sticky="nsew"
    )

    ctk.CTkLabel(
        card,
        text=title,
        text_color=TEXT2
    ).pack(
        pady=(20, 5)
    )

    label = ctk.CTkLabel(
        card,
        text=value,
        text_color=color,
        font=ctk.CTkFont(
            size=24,
            weight="bold"
        )
    )

    label.pack(
        pady=(5, 20)
    )

    return label


rs485_page_port = stat_card(
    rs485_cards,
    0,
    "PORT",
    "COM3",
    BLUE
)

stat_card(
    rs485_cards,
    1,
    "BAUDRATE",
    "9600",
    GREEN
)

stat_card(
    rs485_cards,
    2,
    "SLAVE ID",
    "1",
    CYAN
)

rs485_page_status = stat_card(
    rs485_cards,
    3,
    "BUS STATUS",
    "OFFLINE",
    RED
)


sensor_live_card = ctk.CTkFrame(
    rs485_page,
    fg_color=CARD,
    corner_radius=18
)

sensor_live_card.pack(
    fill="x",
    padx=30,
    pady=10
)


ctk.CTkLabel(
    sensor_live_card,
    text="LIVE REGISTER DATA",
    font=ctk.CTkFont(
        size=15,
        weight="bold"
    )
).pack(
    anchor="w",
    padx=20,
    pady=15
)


live_inner = ctk.CTkFrame(
    sensor_live_card,
    fg_color="transparent"
)

live_inner.pack(
    fill="x",
    padx=20,
    pady=(0, 20)
)


rs485_page_temp = ctk.CTkLabel(
    live_inner,
    text="--.- °C",
    text_color=ORANGE,
    font=ctk.CTkFont(
        size=30,
        weight="bold"
    )
)

rs485_page_temp.pack(
    side="left",
    expand=True
)


rs485_page_humi = ctk.CTkLabel(
    live_inner,
    text="--.- %",
    text_color=CYAN,
    font=ctk.CTkFont(
        size=30,
        weight="bold"
    )
)

rs485_page_humi.pack(
    side="left",
    expand=True
)


traffic_card = ctk.CTkFrame(
    rs485_page,
    fg_color=CARD,
    corner_radius=18
)

traffic_card.pack(
    fill="both",
    expand=True,
    padx=30,
    pady=10
)


ctk.CTkLabel(
    traffic_card,
    text="MODBUS TRAFFIC",
    font=ctk.CTkFont(
        size=15,
        weight="bold"
    )
).pack(
    anchor="w",
    padx=20,
    pady=15
)


rs485_monitor_box = ctk.CTkTextbox(
    traffic_card,
    fg_color="#0B1220",
    font=ctk.CTkFont(
        family="Consolas",
        size=12
    )
)

rs485_monitor_box.pack(
    fill="both",
    expand=True,
    padx=15,
    pady=(0, 15)
)

rs485_monitor_box.configure(
    state="disabled"
)


# ==========================================================
# PAGE 3 - TCP / LAN
# ==========================================================

lan_page = pages["TCP / LAN"]


lan_status_card = ctk.CTkFrame(
    lan_page,
    fg_color=CARD,
    corner_radius=20
)

lan_status_card.pack(
    fill="x",
    padx=30,
    pady=25
)


ctk.CTkLabel(
    lan_status_card,
    text="TCP SERVER STATUS",
    font=ctk.CTkFont(
        size=16,
        weight="bold"
    )
).pack(
    pady=(20, 5)
)


lan_page_status = ctk.CTkLabel(
    lan_status_card,
    text="WAITING",
    text_color=ORANGE,
    font=ctk.CTkFont(
        size=32,
        weight="bold"
    )
)

lan_page_status.pack(
    pady=10
)


lan_grid = ctk.CTkFrame(
    lan_page,
    fg_color="transparent"
)

lan_grid.pack(
    fill="x",
    padx=20,
    pady=10
)

lan_grid.grid_columnconfigure(
    (0, 1, 2, 3),
    weight=1
)


stat_card(
    lan_grid,
    0,
    "LISTEN",
    "0.0.0.0",
    BLUE
)

stat_card(
    lan_grid,
    1,
    "PORT",
    "5000",
    PURPLE
)

lan_pc2_address = stat_card(
    lan_grid,
    2,
    "PC2 CLIENT",
    "--",
    CYAN
)

lan_last_tx = stat_card(
    lan_grid,
    3,
    "LAST TX",
    "--:--:--",
    GREEN
)


lan_info = ctk.CTkFrame(
    lan_page,
    fg_color=CARD,
    corner_radius=20
)

lan_info.pack(
    fill="both",
    expand=True,
    padx=30,
    pady=20
)


ctk.CTkLabel(
    lan_info,
    text="NETWORK FLOW",
    font=ctk.CTkFont(
        size=16,
        weight="bold"
    )
).pack(
    anchor="w",
    padx=20,
    pady=20
)


ctk.CTkLabel(
    lan_info,
    text=(
        "PC1 TCP Server\n\n"
        "0.0.0.0 : 5000\n\n"
        "       ↓\n"
        "TCP/IP LAN\n"
        "       ↓\n"
        "PC2 Client\n\n"
        "Protocol: JSON + newline"
    ),
    text_color=TEXT2,
    font=ctk.CTkFont(
        family="Consolas",
        size=16
    )
).pack(
    pady=25
)


# ==========================================================
# PAGE 4 - DATA PACKET
# ==========================================================

packet_page = pages["Data Packet"]


ctk.CTkLabel(
    packet_page,
    text="JSON PACKET PREVIEW",
    font=ctk.CTkFont(
        size=18,
        weight="bold"
    )
).pack(
    anchor="w",
    padx=30,
    pady=(25, 5)
)


ctk.CTkLabel(
    packet_page,
    text="Dữ liệu được PC1 đóng gói và gửi sang PC2 mỗi chu kỳ.",
    text_color=TEXT2
).pack(
    anchor="w",
    padx=30
)


packet_page_card = ctk.CTkFrame(
    packet_page,
    fg_color=CARD,
    corner_radius=20
)

packet_page_card.pack(
    fill="both",
    expand=True,
    padx=30,
    pady=20
)


packet_page_box = ctk.CTkTextbox(
    packet_page_card,
    fg_color="#0B1220",
    font=ctk.CTkFont(
        family="Consolas",
        size=15
    )
)

packet_page_box.pack(
    fill="both",
    expand=True,
    padx=20,
    pady=20
)

packet_page_box.configure(
    state="disabled"
)


# ==========================================================
# GLOBAL LOG
# ==========================================================

log_frame = ctk.CTkFrame(
    right,
    fg_color=CARD,
    corner_radius=15
)

log_frame.pack(
    fill="x",
    padx=30,
    pady=(0, 20)
)


ctk.CTkLabel(
    log_frame,
    text="SYSTEM LOG",
    font=ctk.CTkFont(
        size=13,
        weight="bold"
    )
).pack(
    anchor="w",
    padx=15,
    pady=(10, 5)
)


log_box = ctk.CTkTextbox(
    log_frame,
    height=100,
    fg_color="#0B1220",
    font=ctk.CTkFont(
        family="Consolas",
        size=10
    )
)

log_box.pack(
    fill="x",
    padx=15,
    pady=(0, 10)
)

log_box.configure(
    state="disabled"
)


# ==========================================================
# CLOSE
# ==========================================================

def on_close():

    global running

    running = False

    try:
        if instrument:
            instrument.serial.close()
    except:
        pass

    try:
        if client_socket:
            client_socket.close()
    except:
        pass

    app.destroy()


app.protocol(
    "WM_DELETE_WINDOW",
    on_close
)


# ==========================================================
# START
# ==========================================================

scan_ports()

update_clock()

build_packet()

show_page(
    "Gateway Monitor"
)

add_log(
    "PC1 Gateway started"
)


threading.Thread(
    target=polling_loop,
    daemon=True
).start()


threading.Thread(
    target=tcp_server,
    daemon=True
).start()


app.mainloop()