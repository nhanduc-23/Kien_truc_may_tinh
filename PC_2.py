import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from datetime import datetime
import random
import csv

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# ==========================================================
# APP CONFIG
# ==========================================================

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("PC2 - Industrial Smart Control")
app.geometry("1500x900")
app.minsize(1250, 760)

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
PINK = "#EC4899"

app.configure(fg_color=BG)


# ==========================================================
# SYSTEM DATA
# ==========================================================

connected = False
mode = "MANUAL"

fan_state = False
pump_state = False

temperature = 27.5
humidity = 65.0

temp_threshold = 30
humi_threshold = 60

temp_history = []
humi_history = []
time_history = []

history_records = []

current_page = None

blink_state = False


# ==========================================================
# FUNCTIONS
# ==========================================================

def show_page(page_name):

    global current_page
    current_page = page_name

    for frame in pages.values():
        frame.pack_forget()

    pages[page_name].pack(
        fill="both",
        expand=True
    )

    for name, btn in menu_buttons.items():

        if name == page_name:

            btn.configure(
                fg_color="#1D4ED8"
            )

        else:

            btn.configure(
                fg_color="transparent"
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
# CONNECTION
# ==========================================================

def toggle_connection():

    global connected

    connected = not connected

    if connected:

        connection_status.configure(
            text="● ONLINE",
            text_color=GREEN
        )

        connect_button.configure(
            text="NGẮT KẾT NỐI",
            fg_color=RED
        )

        add_log(
            "PC2 đã kết nối với PC1."
        )

        show_toast(
            "✓ Kết nối PC1 thành công",
            GREEN
        )

    else:

        connection_status.configure(
            text="● OFFLINE",
            text_color=RED
        )

        connect_button.configure(
            text="KẾT NỐI",
            fg_color=BLUE
        )

        add_log(
            "Mất kết nối với PC1."
        )

        show_toast(
            "⚠ Đã ngắt kết nối PC1",
            ORANGE
        )


# ==========================================================
# MODE
# ==========================================================

def set_auto_mode():

    global mode

    mode = "AUTO"

    mode_label.configure(
        text="AUTO",
        text_color=GREEN
    )

    control_mode_label.configure(
        text="AUTO MODE",
        text_color=GREEN
    )

    add_log(
        "Chuyển sang chế độ AUTO"
    )

    show_toast(
        "AUTO MODE ACTIVATED",
        GREEN
    )


def set_manual_mode():

    global mode

    mode = "MANUAL"

    mode_label.configure(
        text="MANUAL",
        text_color=BLUE
    )

    control_mode_label.configure(
        text="MANUAL MODE",
        text_color=BLUE
    )

    add_log(
        "Chuyển sang chế độ MANUAL"
    )

    show_toast(
        "MANUAL MODE ACTIVATED",
        BLUE
    )


# ==========================================================
# DEVICE CONTROL
# ==========================================================

def toggle_fan():

    global fan_state

    if mode == "AUTO":

        messagebox.showwarning(
            "AUTO MODE",
            "Không thể điều khiển trực tiếp trong AUTO MODE."
        )

        return

    fan_state = not fan_state

    update_device_ui()

    add_log(
        "Quạt ON"
        if fan_state
        else "Quạt OFF"
    )


def toggle_pump():

    global pump_state

    if mode == "AUTO":

        messagebox.showwarning(
            "AUTO MODE",
            "Không thể điều khiển trực tiếp trong AUTO MODE."
        )

        return

    pump_state = not pump_state

    update_device_ui()

    add_log(
        "Máy bơm ON"
        if pump_state
        else "Máy bơm OFF"
    )


def update_device_ui():

    # dashboard

    dashboard_fan.configure(
        text="ON" if fan_state else "OFF",
        text_color=GREEN if fan_state else RED
    )

    dashboard_pump.configure(
        text="ON" if pump_state else "OFF",
        text_color=GREEN if pump_state else RED
    )

    # control

    fan_control_button.configure(
        text="TURN OFF" if fan_state else "TURN ON",
        fg_color=RED if fan_state else GREEN
    )

    pump_control_button.configure(
        text="TURN OFF" if pump_state else "TURN ON",
        fg_color=RED if pump_state else GREEN
    )

    fan_control_status.configure(
        text="ONLINE • ON" if fan_state else "STANDBY • OFF",
        text_color=GREEN if fan_state else TEXT2
    )

    pump_control_status.configure(
        text="ONLINE • ON" if pump_state else "STANDBY • OFF",
        text_color=GREEN if pump_state else TEXT2
    )


# ==========================================================
# QUICK MODE
# ==========================================================

def quick_cool():

    global mode
    global fan_state

    mode = "MANUAL"
    fan_state = True

    update_device_ui()

    mode_label.configure(
        text="QUICK COOL",
        text_color=CYAN
    )

    add_log(
        "Quick Mode: COOL activated"
    )

    show_toast(
        "❄ Quick Cool activated",
        CYAN
    )


def quick_water():

    global mode
    global pump_state

    mode = "MANUAL"
    pump_state = True

    update_device_ui()

    add_log(
        "Quick Mode: WATER activated"
    )

    show_toast(
        "💧 Quick Water activated",
        BLUE
    )


def quick_stop():

    global fan_state
    global pump_state

    fan_state = False
    pump_state = False

    update_device_ui()

    add_log(
        "Emergency device stop"
    )

    show_toast(
        "■ All devices stopped",
        RED
    )


# ==========================================================
# THRESHOLD
# ==========================================================

def save_threshold():

    global temp_threshold
    global humi_threshold

    try:

        temp_threshold = float(
            control_temp_entry.get()
        )

        humi_threshold = float(
            control_humi_entry.get()
        )

        add_log(
            f"Ngưỡng mới: "
            f"{temp_threshold}°C | "
            f"{humi_threshold}%"
        )

        show_toast(
            "✓ Đã lưu ngưỡng AUTO",
            PURPLE
        )

    except ValueError:

        messagebox.showerror(
            "Lỗi",
            "Ngưỡng phải là số."
        )


# ==========================================================
# LOG
# ==========================================================

def add_log(message):

    now = datetime.now().strftime(
        "%H:%M:%S"
    )

    if "dashboard_log" not in globals():
        return

    dashboard_log.configure(
        state="normal"
    )

    dashboard_log.insert(
        "end",
        f"[{now}] {message}\n"
    )

    dashboard_log.see("end")

    dashboard_log.configure(
        state="disabled"
    )


# ==========================================================
# TOAST NOTIFICATION
# ==========================================================

def show_toast(text, color):

    toast.configure(
        text=text,
        fg_color=color
    )

    toast.place(
        relx=0.98,
        rely=0.04,
        anchor="ne"
    )

    app.after(
        2200,
        lambda: toast.place_forget()
    )


# ==========================================================
# HISTORY
# ==========================================================

def update_history_table():

    if len(history_records) == 0:
        return

    record = history_records[-1]

    history_tree.insert(
        "",
        0,
        values=record
    )

    children = history_tree.get_children()

    if len(children) > 100:

        history_tree.delete(
            children[-1]
        )


def clear_history():

    for item in history_tree.get_children():

        history_tree.delete(item)

    history_records.clear()

    show_toast(
        "Đã xóa lịch sử",
        ORANGE
    )


def export_history():

    if not history_records:

        messagebox.showwarning(
            "Lịch sử",
            "Chưa có dữ liệu để xuất."
        )

        return

    filename = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[
            ("CSV file", "*.csv")
        ]
    )

    if not filename:
        return

    with open(
        filename,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.writer(file)

        writer.writerow([
            "Time",
            "Temperature",
            "Humidity",
            "Fan",
            "Pump",
            "Mode"
        ])

        writer.writerows(
            history_records
        )

    show_toast(
        "✓ Xuất CSV thành công",
        GREEN
    )


# ==========================================================
# CHART UPDATE
# ==========================================================

def update_charts():

    # Dashboard chart

    dashboard_ax.clear()

    dashboard_ax.set_facecolor(
        CARD
    )

    dashboard_ax.plot(
        temp_history,
        label="Temperature",
        linewidth=2
    )

    dashboard_ax.plot(
        humi_history,
        label="Humidity",
        linewidth=2
    )

    dashboard_ax.grid(
        alpha=0.12
    )

    dashboard_ax.tick_params(
        colors=TEXT2
    )

    dashboard_ax.legend(
        loc="upper left",
        fontsize=8
    )

    for spine in dashboard_ax.spines.values():
        spine.set_color("#334155")

    dashboard_canvas.draw_idle()


    # Monitoring chart

    monitor_ax.clear()

    monitor_ax.set_facecolor(
        CARD
    )

    monitor_ax.plot(
        temp_history,
        label="Nhiệt độ °C",
        linewidth=2
    )

    monitor_ax.plot(
        humi_history,
        label="Độ ẩm %",
        linewidth=2
    )

    monitor_ax.grid(
        alpha=0.15
    )

    monitor_ax.tick_params(
        colors=TEXT2
    )

    monitor_ax.legend(
        loc="upper left"
    )

    for spine in monitor_ax.spines.values():
        spine.set_color("#334155")

    monitor_canvas.draw_idle()


# ==========================================================
# SENSOR SIMULATION
# sau này thay bằng dữ liệu TCP từ PC1
# ==========================================================

def simulate_sensor():

    global temperature
    global humidity
    global fan_state
    global pump_state

    temperature += random.uniform(
        -0.3,
        0.3
    )

    humidity += random.uniform(
        -0.5,
        0.5
    )

    temperature = max(
        15,
        min(45, temperature)
    )

    humidity = max(
        20,
        min(95, humidity)
    )

    # AUTO CONTROL

    if mode == "AUTO":

        fan_state = (
            temperature >= temp_threshold
        )

        pump_state = (
            humidity <= humi_threshold
        )

        update_device_ui()


    # UPDATE DASHBOARD

    dashboard_temp.configure(
        text=f"{temperature:.1f} °C"
    )

    dashboard_humi.configure(
        text=f"{humidity:.1f} %"
    )


    # UPDATE MONITOR

    monitor_temp.configure(
        text=f"{temperature:.1f} °C"
    )

    monitor_humi.configure(
        text=f"{humidity:.1f} %"
    )


    # STATUS

    if temperature >= temp_threshold:

        temp_condition.configure(
            text="⚠ NHIỆT ĐỘ CAO",
            text_color=ORANGE
        )

    else:

        temp_condition.configure(
            text="● NORMAL",
            text_color=GREEN
        )


    if humidity <= humi_threshold:

        humi_condition.configure(
            text="⚠ ĐỘ ẨM THẤP",
            text_color=ORANGE
        )

    else:

        humi_condition.configure(
            text="● NORMAL",
            text_color=GREEN
        )


    # HISTORY

    now = datetime.now().strftime(
        "%H:%M:%S"
    )

    temp_history.append(
        temperature
    )

    humi_history.append(
        humidity
    )

    time_history.append(
        now
    )

    if len(temp_history) > 30:

        temp_history.pop(0)
        humi_history.pop(0)
        time_history.pop(0)


    record = (
        datetime.now().strftime(
            "%d/%m/%Y %H:%M:%S"
        ),

        f"{temperature:.1f}",

        f"{humidity:.1f}",

        "ON" if fan_state else "OFF",

        "ON" if pump_state else "OFF",

        mode
    )

    history_records.append(
        record
    )

    update_history_table()

    update_charts()

    update_statistics()

    app.after(
        1500,
        simulate_sensor
    )


# ==========================================================
# STATISTICS
# ==========================================================

def update_statistics():

    if not temp_history:
        return

    max_temp.configure(
        text=f"{max(temp_history):.1f}°C"
    )

    min_temp.configure(
        text=f"{min(temp_history):.1f}°C"
    )

    avg_temp.configure(
        text=f"{sum(temp_history)/len(temp_history):.1f}°C"
    )

    avg_humi.configure(
        text=f"{sum(humi_history)/len(humi_history):.1f}%"
    )


# ==========================================================
# FULL SCREEN
# ==========================================================

def toggle_fullscreen():

    app.attributes(
        "-fullscreen",
        not app.attributes("-fullscreen")
    )


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
# LOGO
# ==========================================================

ctk.CTkLabel(
    sidebar,
    text="NEXUS",
    font=ctk.CTkFont(
        size=30,
        weight="bold"
    ),
    text_color=CYAN
).pack(
    pady=(30, 0)
)

ctk.CTkLabel(
    sidebar,
    text="INDUSTRIAL CONTROL",
    font=ctk.CTkFont(
        size=11,
        weight="bold"
    ),
    text_color=TEXT
).pack()

ctk.CTkLabel(
    sidebar,
    text="PC2 CONTROL STATION",
    font=ctk.CTkFont(
        size=10
    ),
    text_color=TEXT2
).pack(
    pady=(5, 35)
)


# ==========================================================
# MENU
# ==========================================================

menu_buttons = {}

menu_data = [
    ("Dashboard", "⌂"),
    ("Giám sát", "◉"),
    ("Điều khiển", "⚙"),
    ("Lịch sử", "▦"),
    ("Cài đặt", "◌")
]

for name, icon in menu_data:

    button = ctk.CTkButton(
        sidebar,
        text=f"{icon}     {name}",
        anchor="w",
        height=48,
        corner_radius=10,
        font=ctk.CTkFont(
            size=14,
            weight="bold"
        ),
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
    text="SYSTEM STATUS",
    text_color=TEXT2,
    font=ctk.CTkFont(
        size=10,
        weight="bold"
    )
).pack(
    anchor="w"
)

ctk.CTkLabel(
    side_bottom,
    text="● SYSTEM READY",
    text_color=GREEN,
    font=ctk.CTkFont(
        size=11,
        weight="bold"
    )
).pack(
    anchor="w",
    pady=5
)


# ==========================================================
# RIGHT AREA
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
# TOP HEADER
# ==========================================================

top = ctk.CTkFrame(
    right,
    height=90,
    fg_color=BG
)

top.pack(
    fill="x",
    padx=30,
    pady=(15, 0)
)

top.pack_propagate(False)


title_label = ctk.CTkLabel(
    top,
    text="Smart Industrial Dashboard",
    font=ctk.CTkFont(
        size=28,
        weight="bold"
    )
)

title_label.pack(
    side="left",
    pady=20
)


clock_frame = ctk.CTkFrame(
    top,
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
# CONNECTION BAR
# ==========================================================

connection_bar = ctk.CTkFrame(
    right,
    height=55,
    corner_radius=15,
    fg_color=CARD
)

connection_bar.pack(
    fill="x",
    padx=30,
    pady=(5, 10)
)


connection_status = ctk.CTkLabel(
    connection_bar,
    text="● OFFLINE",
    text_color=RED,
    font=ctk.CTkFont(
        size=12,
        weight="bold"
    )
)

connection_status.pack(
    side="left",
    padx=20
)


ctk.CTkLabel(
    connection_bar,
    text="IP PC1",
    text_color=TEXT2
).pack(
    side="left"
)


ip_entry = ctk.CTkEntry(
    connection_bar,
    width=155
)

ip_entry.insert(
    0,
    "192.168.1.100"
)

ip_entry.pack(
    side="left",
    padx=10
)


connect_button = ctk.CTkButton(
    connection_bar,
    text="KẾT NỐI",
    width=130,
    fg_color=BLUE,
    command=toggle_connection
)

connect_button.pack(
    side="left"
)


fullscreen_button = ctk.CTkButton(
    connection_bar,
    text="⛶",
    width=45,
    fg_color="#334155",
    command=toggle_fullscreen
)

fullscreen_button.pack(
    side="right",
    padx=10
)


mode_label = ctk.CTkLabel(
    connection_bar,
    text="MANUAL",
    text_color=BLUE,
    font=ctk.CTkFont(
        size=13,
        weight="bold"
    )
)

mode_label.pack(
    side="right",
    padx=15
)


# ==========================================================
# PAGE CONTAINER
# ==========================================================

page_container = ctk.CTkFrame(
    right,
    fg_color=BG
)

page_container.pack(
    fill="both",
    expand=True
)


pages = {}

for name in [
    "Dashboard",
    "Giám sát",
    "Điều khiển",
    "Lịch sử",
    "Cài đặt"
]:

    pages[name] = ctk.CTkFrame(
        page_container,
        fg_color=BG
    )


# ==========================================================
# ================= DASHBOARD ===============================
# ==========================================================

dashboard = pages["Dashboard"]

dashboard.grid_columnconfigure(
    (0, 1, 2),
    weight=1
)


def create_sensor_card(
    parent,
    column,
    title,
    icon,
    color
):

    frame = ctk.CTkFrame(
        parent,
        corner_radius=18,
        fg_color=CARD
    )

    frame.grid(
        row=0,
        column=column,
        padx=10,
        pady=10,
        sticky="nsew"
    )

    ctk.CTkLabel(
        frame,
        text=f"{icon}  {title}",
        text_color=TEXT2,
        font=ctk.CTkFont(
            size=14,
            weight="bold"
        )
    ).pack(
        pady=(25, 10)
    )

    value = ctk.CTkLabel(
        frame,
        text="--",
        text_color=color,
        font=ctk.CTkFont(
            size=38,
            weight="bold"
        )
    )

    value.pack(
        pady=15
    )

    return value, frame


dashboard_temp, temp_card = create_sensor_card(
    dashboard,
    0,
    "NHIỆT ĐỘ",
    "🌡",
    ORANGE
)

temp_condition = ctk.CTkLabel(
    temp_card,
    text="● NORMAL",
    text_color=GREEN
)

temp_condition.pack(
    pady=(0, 20)
)


dashboard_humi, humi_card = create_sensor_card(
    dashboard,
    1,
    "ĐỘ ẨM",
    "💧",
    CYAN
)

humi_condition = ctk.CTkLabel(
    humi_card,
    text="● NORMAL",
    text_color=GREEN
)

humi_condition.pack(
    pady=(0, 20)
)


device_card = ctk.CTkFrame(
    dashboard,
    corner_radius=18,
    fg_color=CARD
)

device_card.grid(
    row=0,
    column=2,
    padx=10,
    pady=10,
    sticky="nsew"
)


ctk.CTkLabel(
    device_card,
    text="DEVICE STATUS",
    text_color=TEXT2,
    font=ctk.CTkFont(
        size=14,
        weight="bold"
    )
).pack(
    pady=(25, 15)
)


row = ctk.CTkFrame(
    device_card,
    fg_color=CARD2
)

row.pack(
    fill="x",
    padx=20,
    pady=7
)

ctk.CTkLabel(
    row,
    text="🌀  QUẠT"
).pack(
    side="left",
    padx=15,
    pady=10
)

dashboard_fan = ctk.CTkLabel(
    row,
    text="OFF",
    text_color=RED,
    font=ctk.CTkFont(
        weight="bold"
    )
)

dashboard_fan.pack(
    side="right",
    padx=15
)


row2 = ctk.CTkFrame(
    device_card,
    fg_color=CARD2
)

row2.pack(
    fill="x",
    padx=20,
    pady=7
)

ctk.CTkLabel(
    row2,
    text="💧  BƠM"
).pack(
    side="left",
    padx=15,
    pady=10
)

dashboard_pump = ctk.CTkLabel(
    row2,
    text="OFF",
    text_color=RED,
    font=ctk.CTkFont(
        weight="bold"
    )
)

dashboard_pump.pack(
    side="right",
    padx=15
)


# CHART + LOG

dashboard_bottom = ctk.CTkFrame(
    dashboard,
    fg_color="transparent"
)

dashboard_bottom.grid(
    row=1,
    column=0,
    columnspan=3,
    sticky="nsew",
    padx=10,
    pady=10
)

dashboard_bottom.grid_columnconfigure(
    0,
    weight=2
)

dashboard_bottom.grid_columnconfigure(
    1,
    weight=1
)


chart_card = ctk.CTkFrame(
    dashboard_bottom,
    corner_radius=18,
    fg_color=CARD
)

chart_card.grid(
    row=0,
    column=0,
    sticky="nsew",
    padx=(0, 10)
)

ctk.CTkLabel(
    chart_card,
    text="LIVE DATA",
    font=ctk.CTkFont(
        size=15,
        weight="bold"
    )
).pack(
    anchor="w",
    padx=20,
    pady=15
)


dashboard_fig = Figure(
    figsize=(6, 3),
    dpi=100
)

dashboard_fig.patch.set_facecolor(
    CARD
)

dashboard_ax = dashboard_fig.add_subplot(111)

dashboard_canvas = FigureCanvasTkAgg(
    dashboard_fig,
    master=chart_card
)

dashboard_canvas.get_tk_widget().pack(
    fill="both",
    expand=True,
    padx=15,
    pady=(0, 15)
)


log_card = ctk.CTkFrame(
    dashboard_bottom,
    corner_radius=18,
    fg_color=CARD
)

log_card.grid(
    row=0,
    column=1,
    sticky="nsew",
    padx=(10, 0)
)

ctk.CTkLabel(
    log_card,
    text="SYSTEM ACTIVITY",
    font=ctk.CTkFont(
        size=15,
        weight="bold"
    )
).pack(
    anchor="w",
    padx=20,
    pady=15
)

dashboard_log = ctk.CTkTextbox(
    log_card,
    fg_color="#0F172A",
    font=ctk.CTkFont(
        family="Consolas",
        size=11
    )
)

dashboard_log.pack(
    fill="both",
    expand=True,
    padx=15,
    pady=(0, 15)
)

dashboard_log.configure(
    state="disabled"
)


# ==========================================================
# ================= MONITOR ================================
# ==========================================================

monitor = pages["Giám sát"]

ctk.CTkLabel(
    monitor,
    text="Giám sát thời gian thực",
    font=ctk.CTkFont(
        size=25,
        weight="bold"
    )
).pack(
    anchor="w",
    padx=30,
    pady=(20, 5)
)


ctk.CTkLabel(
    monitor,
    text="Live telemetry từ PC1 và hệ thống cảm biến",
    text_color=TEXT2
).pack(
    anchor="w",
    padx=30
)


monitor_cards = ctk.CTkFrame(
    monitor,
    fg_color="transparent"
)

monitor_cards.pack(
    fill="x",
    padx=20,
    pady=20
)

for i in range(4):
    monitor_cards.grid_columnconfigure(
        i,
        weight=1
    )


def monitor_stat_card(
    parent,
    col,
    title,
    color
):

    card = ctk.CTkFrame(
        parent,
        fg_color=CARD,
        corner_radius=15
    )

    card.grid(
        row=0,
        column=col,
        padx=8,
        sticky="ew"
    )

    ctk.CTkLabel(
        card,
        text=title,
        text_color=TEXT2
    ).pack(
        pady=(18, 5)
    )

    value = ctk.CTkLabel(
        card,
        text="--",
        text_color=color,
        font=ctk.CTkFont(
            size=25,
            weight="bold"
        )
    )

    value.pack(
        pady=(0, 18)
    )

    return value


monitor_temp = monitor_stat_card(
    monitor_cards,
    0,
    "NHIỆT ĐỘ",
    ORANGE
)

monitor_humi = monitor_stat_card(
    monitor_cards,
    1,
    "ĐỘ ẨM",
    CYAN
)

avg_temp = monitor_stat_card(
    monitor_cards,
    2,
    "TEMP AVG",
    PURPLE
)

avg_humi = monitor_stat_card(
    monitor_cards,
    3,
    "HUMI AVG",
    GREEN
)


monitor_chart_card = ctk.CTkFrame(
    monitor,
    fg_color=CARD,
    corner_radius=18
)

monitor_chart_card.pack(
    fill="both",
    expand=True,
    padx=30,
    pady=10
)


monitor_fig = Figure(
    figsize=(10, 5),
    dpi=100
)

monitor_fig.patch.set_facecolor(
    CARD
)

monitor_ax = monitor_fig.add_subplot(111)

monitor_canvas = FigureCanvasTkAgg(
    monitor_fig,
    master=monitor_chart_card
)

monitor_canvas.get_tk_widget().pack(
    fill="both",
    expand=True,
    padx=20,
    pady=20
)


stat_bottom = ctk.CTkFrame(
    monitor,
    fg_color="transparent"
)

stat_bottom.pack(
    fill="x",
    padx=30,
    pady=10
)


max_temp = ctk.CTkLabel(
    stat_bottom,
    text="--",
    text_color=RED,
    font=ctk.CTkFont(
        size=16,
        weight="bold"
    )
)

max_temp.pack(
    side="left"
)

ctk.CTkLabel(
    stat_bottom,
    text=" Max temperature     ",
    text_color=TEXT2
).pack(
    side="left"
)


min_temp = ctk.CTkLabel(
    stat_bottom,
    text="--",
    text_color=CYAN,
    font=ctk.CTkFont(
        size=16,
        weight="bold"
    )
)

min_temp.pack(
    side="left"
)

ctk.CTkLabel(
    stat_bottom,
    text=" Min temperature",
    text_color=TEXT2
).pack(
    side="left"
)


# ==========================================================
# ================= CONTROL ================================
# ==========================================================

control = pages["Điều khiển"]

ctk.CTkLabel(
    control,
    text="Control Center",
    font=ctk.CTkFont(
        size=27,
        weight="bold"
    )
).pack(
    anchor="w",
    padx=30,
    pady=(25, 5)
)


control_mode_label = ctk.CTkLabel(
    control,
    text="MANUAL MODE",
    text_color=BLUE,
    font=ctk.CTkFont(
        size=14,
        weight="bold"
    )
)

control_mode_label.pack(
    anchor="w",
    padx=30
)


mode_controls = ctk.CTkFrame(
    control,
    fg_color=CARD,
    corner_radius=18
)

mode_controls.pack(
    fill="x",
    padx=30,
    pady=20
)


ctk.CTkButton(
    mode_controls,
    text="MANUAL",
    fg_color=BLUE,
    height=45,
    command=set_manual_mode
).pack(
    side="left",
    expand=True,
    fill="x",
    padx=20,
    pady=20
)


ctk.CTkButton(
    mode_controls,
    text="AUTO",
    fg_color=GREEN,
    height=45,
    command=set_auto_mode
).pack(
    side="left",
    expand=True,
    fill="x",
    padx=20,
    pady=20
)


devices = ctk.CTkFrame(
    control,
    fg_color="transparent"
)

devices.pack(
    fill="x",
    padx=20
)

devices.grid_columnconfigure(
    (0, 1),
    weight=1
)


fan_big = ctk.CTkFrame(
    devices,
    fg_color=CARD,
    corner_radius=20
)

fan_big.grid(
    row=0,
    column=0,
    padx=10,
    sticky="nsew"
)

ctk.CTkLabel(
    fan_big,
    text="🌀",
    font=ctk.CTkFont(
        size=50
    )
).pack(
    pady=(25, 5)
)

ctk.CTkLabel(
    fan_big,
    text="QUẠT LÀM MÁT",
    font=ctk.CTkFont(
        size=18,
        weight="bold"
    )
).pack()


fan_control_status = ctk.CTkLabel(
    fan_big,
    text="STANDBY • OFF",
    text_color=TEXT2
)

fan_control_status.pack(
    pady=10
)


fan_control_button = ctk.CTkButton(
    fan_big,
    text="TURN ON",
    fg_color=GREEN,
    height=45,
    command=toggle_fan
)

fan_control_button.pack(
    fill="x",
    padx=50,
    pady=(10, 30)
)


pump_big = ctk.CTkFrame(
    devices,
    fg_color=CARD,
    corner_radius=20
)

pump_big.grid(
    row=0,
    column=1,
    padx=10,
    sticky="nsew"
)

ctk.CTkLabel(
    pump_big,
    text="💧",
    font=ctk.CTkFont(
        size=50
    )
).pack(
    pady=(25, 5)
)

ctk.CTkLabel(
    pump_big,
    text="MÁY BƠM",
    font=ctk.CTkFont(
        size=18,
        weight="bold"
    )
).pack()


pump_control_status = ctk.CTkLabel(
    pump_big,
    text="STANDBY • OFF",
    text_color=TEXT2
)

pump_control_status.pack(
    pady=10
)


pump_control_button = ctk.CTkButton(
    pump_big,
    text="TURN ON",
    fg_color=GREEN,
    height=45,
    command=toggle_pump
)

pump_control_button.pack(
    fill="x",
    padx=50,
    pady=(10, 30)
)


# QUICK ACTION

quick = ctk.CTkFrame(
    control,
    fg_color=CARD,
    corner_radius=18
)

quick.pack(
    fill="x",
    padx=30,
    pady=20
)

ctk.CTkLabel(
    quick,
    text="⚡ QUICK ACTION",
    font=ctk.CTkFont(
        size=15,
        weight="bold"
    )
).pack(
    anchor="w",
    padx=20,
    pady=(15, 10)
)


quick_inner = ctk.CTkFrame(
    quick,
    fg_color="transparent"
)

quick_inner.pack(
    fill="x",
    padx=10,
    pady=(0, 15)
)


ctk.CTkButton(
    quick_inner,
    text="❄ QUICK COOL",
    fg_color=CYAN,
    command=quick_cool
).pack(
    side="left",
    expand=True,
    fill="x",
    padx=10
)


ctk.CTkButton(
    quick_inner,
    text="💧 QUICK WATER",
    fg_color=BLUE,
    command=quick_water
).pack(
    side="left",
    expand=True,
    fill="x",
    padx=10
)


ctk.CTkButton(
    quick_inner,
    text="■ STOP ALL",
    fg_color=RED,
    command=quick_stop
).pack(
    side="left",
    expand=True,
    fill="x",
    padx=10
)


# AUTO SETTINGS

threshold = ctk.CTkFrame(
    control,
    fg_color=CARD,
    corner_radius=18
)

threshold.pack(
    fill="x",
    padx=30,
    pady=5
)


ctk.CTkLabel(
    threshold,
    text="AUTO THRESHOLD",
    font=ctk.CTkFont(
        size=15,
        weight="bold"
    )
).pack(
    side="left",
    padx=20
)


control_temp_entry = ctk.CTkEntry(
    threshold,
    width=90
)

control_temp_entry.insert(
    0,
    "30"
)

control_temp_entry.pack(
    side="left",
    padx=10,
    pady=20
)


ctk.CTkLabel(
    threshold,
    text="°C"
).pack(
    side="left"
)


control_humi_entry = ctk.CTkEntry(
    threshold,
    width=90
)

control_humi_entry.insert(
    0,
    "60"
)

control_humi_entry.pack(
    side="left",
    padx=(30, 10)
)


ctk.CTkLabel(
    threshold,
    text="%"
).pack(
    side="left"
)


ctk.CTkButton(
    threshold,
    text="SAVE",
    fg_color=PURPLE,
    command=save_threshold
).pack(
    side="right",
    padx=20
)


# ==========================================================
# ================= HISTORY ================================
# ==========================================================

history = pages["Lịch sử"]

header_history = ctk.CTkFrame(
    history,
    fg_color="transparent"
)

header_history.pack(
    fill="x",
    padx=30,
    pady=20
)


ctk.CTkLabel(
    header_history,
    text="Lịch sử hệ thống",
    font=ctk.CTkFont(
        size=26,
        weight="bold"
    )
).pack(
    side="left"
)


ctk.CTkButton(
    header_history,
    text="XUẤT CSV",
    fg_color=GREEN,
    command=export_history
).pack(
    side="right",
    padx=5
)


ctk.CTkButton(
    header_history,
    text="XÓA LỊCH SỬ",
    fg_color=RED,
    command=clear_history
).pack(
    side="right",
    padx=5
)


table_frame = ctk.CTkFrame(
    history,
    fg_color=CARD,
    corner_radius=18
)

table_frame.pack(
    fill="both",
    expand=True,
    padx=30,
    pady=(0, 30)
)


style = ttk.Style()

style.theme_use(
    "default"
)

style.configure(
    "Treeview",
    background="#111827",
    foreground="white",
    fieldbackground="#111827",
    rowheight=35,
    borderwidth=0
)

style.configure(
    "Treeview.Heading",
    background="#1E293B",
    foreground="white",
    relief="flat"
)


columns = (
    "time",
    "temp",
    "humi",
    "fan",
    "pump",
    "mode"
)


history_tree = ttk.Treeview(
    table_frame,
    columns=columns,
    show="headings"
)


headers = [
    "THỜI GIAN",
    "NHIỆT ĐỘ",
    "ĐỘ ẨM",
    "QUẠT",
    "BƠM",
    "MODE"
]


for col, text in zip(
    columns,
    headers
):

    history_tree.heading(
        col,
        text=text
    )

    history_tree.column(
        col,
        anchor="center",
        width=150
    )


history_tree.pack(
    fill="both",
    expand=True,
    padx=20,
    pady=20
)


# ==========================================================
# ================= SETTINGS ===============================
# ==========================================================

settings = pages["Cài đặt"]


ctk.CTkLabel(
    settings,
    text="Cài đặt hệ thống",
    font=ctk.CTkFont(
        size=27,
        weight="bold"
    )
).pack(
    anchor="w",
    padx=30,
    pady=(25, 5)
)


setting_card = ctk.CTkFrame(
    settings,
    fg_color=CARD,
    corner_radius=18
)

setting_card.pack(
    fill="x",
    padx=30,
    pady=20
)


ctk.CTkLabel(
    setting_card,
    text="NETWORK",
    font=ctk.CTkFont(
        size=15,
        weight="bold"
    )
).grid(
    row=0,
    column=0,
    padx=25,
    pady=20,
    sticky="w"
)


ctk.CTkLabel(
    setting_card,
    text="IP PC1:"
).grid(
    row=1,
    column=0,
    padx=25,
    pady=10,
    sticky="w"
)


setting_ip = ctk.CTkEntry(
    setting_card,
    width=200
)

setting_ip.insert(
    0,
    "192.168.1.100"
)

setting_ip.grid(
    row=1,
    column=1,
    pady=10
)


ctk.CTkLabel(
    setting_card,
    text="TCP Port:"
).grid(
    row=2,
    column=0,
    padx=25,
    pady=10,
    sticky="w"
)


port_entry = ctk.CTkEntry(
    setting_card,
    width=200
)

port_entry.insert(
    0,
    "5000"
)

port_entry.grid(
    row=2,
    column=1,
    pady=10
)


ctk.CTkLabel(
    setting_card,
    text="Sampling:"
).grid(
    row=3,
    column=0,
    padx=25,
    pady=10,
    sticky="w"
)


sample_menu = ctk.CTkOptionMenu(
    setting_card,
    values=[
        "0.5 giây",
        "1 giây",
        "1.5 giây",
        "2 giây",
        "5 giây"
    ]
)

sample_menu.set(
    "1.5 giây"
)

sample_menu.grid(
    row=3,
    column=1,
    pady=10
)


ctk.CTkButton(
    setting_card,
    text="LƯU CẤU HÌNH",
    fg_color=PURPLE
).grid(
    row=4,
    column=0,
    columnspan=2,
    padx=25,
    pady=25,
    sticky="ew"
)


about_card = ctk.CTkFrame(
    settings,
    fg_color=CARD,
    corner_radius=18
)

about_card.pack(
    fill="x",
    padx=30,
    pady=10
)


ctk.CTkLabel(
    about_card,
    text="ABOUT SYSTEM",
    font=ctk.CTkFont(
        size=15,
        weight="bold"
    )
).pack(
    anchor="w",
    padx=25,
    pady=(20, 10)
)


ctk.CTkLabel(
    about_card,
    text=(
        "NEXUS Industrial Control\n"
        "PC2 Supervisory Station\n\n"
        "LAN TCP/IP  •  Modbus RTU  •  RS485\n"
        "Python + CustomTkinter"
    ),
    text_color=TEXT2,
    justify="left"
).pack(
    anchor="w",
    padx=25,
    pady=(0, 20)
)


# ==========================================================
# TOAST
# ==========================================================

toast = ctk.CTkLabel(
    app,
    text="",
    width=280,
    height=45,
    corner_radius=12,
    text_color="white",
    font=ctk.CTkFont(
        size=13,
        weight="bold"
    )
)


# ==========================================================
# START
# ==========================================================

show_page(
    "Dashboard"
)

update_clock()

update_device_ui()

add_log(
    "PC2 Control Station started."
)

add_log(
    "Waiting for PC1 LAN connection..."
)

simulate_sensor()

app.mainloop()