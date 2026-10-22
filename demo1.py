import minimalmodbus
import serial
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox

# --- CẤU HÌNH RS485 ---
PORT = 'COM5'
BAUDRATE = 4800
SENSOR_SLAVE_ID = 1    # Cảm biến SHT40
RELAY_SLAVE_ID = 2     # Mạch Relay 2 kênh (Đã đổi sang ID 2)

# --- KHỞI TẠO MODBUS ---
try:
    sensor = minimalmodbus.Instrument(PORT, SENSOR_SLAVE_ID)
    sensor.serial.baudrate = BAUDRATE
    sensor.serial.bytesize = 8
    sensor.serial.parity = serial.PARITY_NONE
    sensor.serial.stopbits = 1
    sensor.serial.timeout = 0.5
    sensor.mode = minimalmodbus.MODE_RTU

    relay = minimalmodbus.Instrument(PORT, RELAY_SLAVE_ID)
    relay.serial.baudrate = BAUDRATE
    relay.serial.bytesize = 8
    relay.serial.parity = serial.PARITY_NONE
    relay.serial.stopbits = 1
    relay.serial.timeout = 0.5
    relay.mode = minimalmodbus.MODE_RTU
    
    MODBUS_CONNECTED = True
except Exception as e:
    MODBUS_CONNECTED = False
    print(f"Lỗi khởi tạo Modbus: {e}")


# --- LỚP GIAO DIỆN CHÍNH ---
class SmartControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HỆ THỐNG GIÁM SÁT & ĐIỀU KHIỂN SHT40 / RS485")
        self.root.geometry("620x580")
        self.root.configure(bg="#f0f2f5")

        # Mặc định Auto = False để người dùng kiểm tra bấm BẬT/TẮT trước
        self.auto_mode = tk.BooleanVar(value=False)
        self.fan_state = False
        self.pump_state = False
        self.running = True

        self.setup_ui()

        # Luồng đọc ngầm
        self.thread = threading.Thread(target=self.update_loop, daemon=True)
        self.thread.start()

    def setup_ui(self):
        # 1. Tiêu đề
        title_frame = tk.Frame(self.root, bg="#1e293b", pady=12)
        title_frame.pack(fill="x")
        title_label = tk.Label(
            title_frame, text="BẢNG ĐIỀU KHIỂN MÁY BƠM & QUẠT RS485", 
            font=("Arial", 16, "bold"), fg="white", bg="#1e293b"
        )
        title_label.pack()

        # 2. Thông số cảm biến
        sensor_frame = tk.LabelFrame(
            self.root, text=" THÔNG SỐ CẢM BIẾN SHT40 ", 
            font=("Arial", 11, "bold"), bg="#f0f2f5", fg="#334155", padx=15, pady=10
        )
        sensor_frame.pack(fill="x", padx=20, pady=10)

        # Nhiệt độ
        temp_card = tk.Frame(sensor_frame, bg="#ffe4e6", relief="groove", bd=1, padx=20, pady=10)
        temp_card.pack(side="left", expand=True, fill="both", padx=5)
        tk.Label(temp_card, text="Nhiệt Độ", font=("Arial", 11), bg="#ffe4e6", fg="#e11d48").pack()
        self.lbl_temp = tk.Label(temp_card, text="--.- °C", font=("Arial", 22, "bold"), bg="#ffe4e6", fg="#9f1239")
        self.lbl_temp.pack()

        # Độ ẩm
        hum_card = tk.Frame(sensor_frame, bg="#e0f2fe", relief="groove", bd=1, padx=20, pady=10)
        hum_card.pack(side="right", expand=True, fill="both", padx=5)
        tk.Label(hum_card, text="Độ Ẩm", font=("Arial", 11), bg="#e0f2fe", fg="#0284c7").pack()
        self.lbl_hum = tk.Label(hum_card, text="--.- %RH", font=("Arial", 22, "bold"), bg="#e0f2fe", fg="#075985")
        self.lbl_hum.pack()

        # 3. Chế độ Auto
        mode_frame = tk.Frame(self.root, bg="#f0f2f5")
        mode_frame.pack(fill="x", padx=20, pady=5)
        
        chk_auto = tk.Checkbutton(
            mode_frame, text="Kích hoạt Chế độ Tự Động (Auto Mode)", 
            variable=self.auto_mode, font=("Arial", 11, "bold"), 
            bg="#f0f2f5", fg="#0f172a", activebackground="#f0f2f5",
            command=self.toggle_mode
        )
        chk_auto.pack(anchor="w")

        # 4. Bảng điều khiển thiết bị
        control_frame = tk.LabelFrame(
            self.root, text=" TRẠNG THÁI & ĐIỀU KHIỂN THIẾT BỊ ", 
            font=("Arial", 11, "bold"), bg="#f0f2f5", fg="#334155", padx=15, pady=10
        )
        control_frame.pack(fill="x", padx=20, pady=10)

        # Quạt
        fan_box = tk.Frame(control_frame, bg="#ffffff", relief="flat", padx=10, pady=8)
        fan_box.pack(fill="x", pady=5)
        tk.Label(fan_box, text="QUẠT TẢN NHIỆT (NO1):", font=("Arial", 11, "bold"), bg="#ffffff").pack(side="left")
        self.lbl_fan_status = tk.Label(fan_box, text=" OFF ", font=("Arial", 10, "bold"), bg="#64748b", fg="white", width=6)
        self.lbl_fan_status.pack(side="left", padx=15)
        self.btn_fan_on = tk.Button(fan_box, text="BẬT", bg="#16a34a", fg="white", font=("Arial", 9, "bold"), width=8, command=lambda: self.manual_control_fan(True))
        self.btn_fan_on.pack(side="left", padx=2)
        self.btn_fan_off = tk.Button(fan_box, text="TẮT", bg="#dc2626", fg="white", font=("Arial", 9, "bold"), width=8, command=lambda: self.manual_control_fan(False))
        self.btn_fan_off.pack(side="left", padx=2)

        # Máy Bơm
        pump_box = tk.Frame(control_frame, bg="#ffffff", relief="flat", padx=10, pady=8)
        pump_box.pack(fill="x", pady=5)
        tk.Label(pump_box, text="MÁY BƠM NƯỚC (NO2):", font=("Arial", 11, "bold"), bg="#ffffff").pack(side="left")
        self.lbl_pump_status = tk.Label(pump_box, text=" OFF ", font=("Arial", 10, "bold"), bg="#64748b", fg="white", width=6)
        self.lbl_pump_status.pack(side="left", padx=15)
        self.btn_pump_on = tk.Button(pump_box, text="BẬT", bg="#16a34a", fg="white", font=("Arial", 9, "bold"), width=8, command=lambda: self.manual_control_pump(True))
        self.btn_pump_on.pack(side="left", padx=2)
        self.btn_pump_off = tk.Button(pump_box, text="TẮT", bg="#dc2626", fg="white", font=("Arial", 9, "bold"), width=8, command=lambda: self.manual_control_pump(False))
        self.btn_pump_off.pack(side="left", padx=2)

        # 5. Nhật ký
        log_frame = tk.LabelFrame(
            self.root, text=" NHẬT KÝ HỆ THỐNG ", 
            font=("Arial", 10, "bold"), bg="#f0f2f5", fg="#334155"
        )
        log_frame.pack(fill="both", expand=True, padx=20, pady=5)

        self.txt_log = tk.Text(log_frame, height=6, font=("Consolas", 9), bg="#0f172a", fg="#38edf8")
        self.txt_log.pack(fill="both", expand=True, padx=5, pady=5)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.toggle_mode()

    def log(self, message):
        timestamp = time.strftime('%H:%M:%S')
        self.txt_log.insert(tk.END, f"[{timestamp}] {message}\n")
        self.txt_log.see(tk.END)

    def toggle_mode(self):
        state = tk.DISABLED if self.auto_mode.get() else tk.NORMAL
        self.btn_fan_on.config(state=state)
        self.btn_fan_off.config(state=state)
        self.btn_pump_on.config(state=state)
        self.btn_pump_off.config(state=state)

        if self.auto_mode.get():
            self.log("Đã chuyển sang chế độ TỰ ĐỘNG.")
        else:
            self.log("Đã chuyển sang chế độ THỦ CÔNG (Manual).")

    def set_relay(self, channel, state):
        if not MODBUS_CONNECTED:
            return
        try:
            relay.write_bit(channel, 1 if state else 0, functioncode=5)
        except Exception as e:
            self.log(f"Lỗi ghi Relay {channel + 1}: {e}")

    def update_fan_ui(self, state):
        self.fan_state = state
        self.lbl_fan_status.config(text=" ON " if state else " OFF ", bg="#22c55e" if state else "#64748b")

    def update_pump_ui(self, state):
        self.pump_state = state
        self.lbl_pump_status.config(text=" ON " if state else " OFF ", bg="#22c55e" if state else "#64748b")

    def manual_control_fan(self, state):
        self.set_relay(0, state)
        self.update_fan_ui(state)
        self.log(f"Thủ công: {'BẬT' if state else 'TẮT'} Quạt")

    def manual_control_pump(self, state):
        self.set_relay(1, state)
        self.update_pump_ui(state)
        self.log(f"Thủ công: {'BẬT' if state else 'TẮT'} Bơm")

    def update_loop(self):
        while self.running:
            if MODBUS_CONNECTED:
                try:
                    registers = sensor.read_registers(registeraddress=0, number_of_registers=2, functioncode=3)
                    hum_raw = registers[0]
                    temp_raw = registers[1]
                    if temp_raw > 32767:
                        temp_raw -= 65536
                    
                    hum = hum_raw / 10.0
                    temp = temp_raw / 10.0

                    self.root.after(0, lambda: self.lbl_temp.config(text=f"{temp:.1f} °C"))
                    self.root.after(0, lambda: self.lbl_hum.config(text=f"{hum:.1f} %RH"))

                    if self.auto_mode.get():
                        fan_req = temp > 30.0
                        if fan_req != self.fan_state:
                            self.set_relay(0, fan_req)
                            self.root.after(0, lambda f=fan_req: self.update_fan_ui(f))
                            self.root.after(0, lambda f=fan_req: self.log(f"Auto: {'BẬT' if f else 'TẮT'} Quạt (T = {temp:.1f}°C)"))

                        pump_req = hum < 60.0
                        if pump_req != self.pump_state:
                            self.set_relay(1, pump_req)
                            self.root.after(0, lambda p=pump_req: self.update_pump_ui(p))
                            self.root.after(0, lambda p=pump_req: self.log(f"Auto: {'BẬT' if p else 'TẮT'} Bơm (H = {hum:.1f}%RH)"))

                except Exception as e:
                    self.root.after(0, lambda err=e: self.log(f"Lỗi đọc RS485: {err}"))
            else:
                self.root.after(0, lambda: self.log("Chưa kết nối phần cứng Modbus RS485!"))

            time.sleep(2)

    def on_closing(self):
        self.running = False
        self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    app = SmartControlApp(root)
    root.mainloop()