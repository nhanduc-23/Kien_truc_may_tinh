import time
import threading
import tkinter as tk
from tkinter import messagebox
import minimalmodbus

class ModbusRelayGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Điều khiển Bơm & Quạt Modbus RS485")
        self.root.geometry("450x520")
        self.root.resizable(False, False)
        
        self.instrument = None
        self.is_connected = False
        
        # Trạng thái hiện tại của Bơm & Quạt
        self.bom_state = False
        self.quat_state = False
        
        self.setup_ui()

    def setup_ui(self):
        # --- FRAME 1: Cấu hình kết nối ---
        frame_conn = tk.LabelFrame(self.root, text=" Cấu hình kết nối RS485 ", font=("Arial", 10, "bold"), padx=10, pady=10)
        frame_conn.pack(fill="x", padx=15, pady=10)

        tk.Label(frame_conn, text="Cổng COM:", font=("Arial", 10)).grid(row=0, column=0, sticky="w", padx=5)
        self.ent_com = tk.Entry(frame_conn, width=10, font=("Arial", 10))
        self.ent_com.insert(0, "COM5")
        self.ent_com.grid(row=0, column=1, padx=5)

        tk.Label(frame_conn, text="Slave ID:", font=("Arial", 10)).grid(row=0, column=2, sticky="w", padx=5)
        self.ent_id = tk.Entry(frame_conn, width=8, font=("Arial", 10))
        self.ent_id.insert(0, "255")
        self.ent_id.grid(row=0, column=3, padx=5)

        self.btn_connect = tk.Button(frame_conn, text="Kết nối", bg="#4CAF50", fg="white", font=("Arial", 9, "bold"), command=self.toggle_connection)
        self.btn_connect.grid(row=1, column=0, columnspan=4, sticky="we", pady=(10, 0))

        # Trạng thái kết nối
        self.lbl_status = tk.Label(self.root, text="Trạng thái: Chưa kết nối", fg="red", font=("Arial", 10, "italic"))
        self.lbl_status.pack(pady=2)

        # --- FRAME 2: Điều khiển Bơm 12V (Relay 1) ---
        frame_bom = tk.LabelFrame(self.root, text=" Relay 1 - Bơm 12V ", font=("Arial", 10, "bold"), padx=10, pady=10)
        frame_bom.pack(fill="x", padx=15, pady=8)

        self.lbl_bom_status = tk.Label(frame_bom, text="ĐANG TẮT", bg="#f44336", fg="white", font=("Arial", 11, "bold"), width=12, pady=5)
        self.lbl_bom_status.pack(side="left", padx=10)

        self.btn_bom_toggle = tk.Button(frame_bom, text="BẬT BƠM", font=("Arial", 10, "bold"), width=12, pady=5, command=self.toggle_bom, state="disabled")
        self.btn_bom_toggle.pack(side="right", padx=10)

        # --- FRAME 3: Điều khiển Quạt 12V (Relay 2) ---
        frame_quat = tk.LabelFrame(self.root, text=" Relay 2 - Quạt 12V ", font=("Arial", 10, "bold"), padx=10, pady=10)
        frame_quat.pack(fill="x", padx=15, pady=8)

        self.lbl_quat_status = tk.Label(frame_quat, text="ĐANG TẮT", bg="#f44336", fg="white", font=("Arial", 11, "bold"), width=12, pady=5)
        self.lbl_quat_status.pack(side="left", padx=10)

        self.btn_quat_toggle = tk.Button(frame_quat, text="BẬT QUẠT", font=("Arial", 10, "bold"), width=12, pady=5, command=self.toggle_quat, state="disabled")
        self.btn_quat_toggle.pack(side="right", padx=10)

        # --- FRAME 4: Tự động & Tắt tất cả ---
        frame_auto = tk.Frame(self.root, pady=10)
        frame_auto.pack(fill="x", padx=15)

        self.btn_auto = tk.Button(frame_auto, text="🔄 Chạy kịch bản tự động (Quạt -> Bơm)", bg="#2196F3", fg="white", font=("Arial", 10, "bold"), pady=6, command=self.run_auto_sequence, state="disabled")
        self.btn_auto.pack(fill="x", pady=2)

        self.btn_off_all = tk.Button(frame_auto, text="⛔ Tắt Bơm & Quạt", bg="#ff9800", fg="white", font=("Arial", 10, "bold"), pady=6, command=self.turn_off_all, state="disabled")
        self.btn_off_all.pack(fill="x", pady=4)

    # --- HÀM KẾT NỐI / NGẮT KẾT NỐI ---
    def toggle_connection(self):
        if not self.is_connected:
            port = self.ent_com.get().strip()
            try:
                slave_id = int(self.ent_id.get().strip())
                self.instrument = minimalmodbus.Instrument(port, slaveaddress=slave_id)
                self.instrument.serial.baudrate = 9600
                self.instrument.serial.bytesize = 8
                self.instrument.serial.parity = minimalmodbus.serial.PARITY_NONE
                self.instrument.serial.stopbits = 1
                self.instrument.serial.timeout = 0.5
                self.instrument.mode = minimalmodbus.MODE_RTU
                
                # Test giao tiếp an toàn
                self.instrument.write_bit(0, 0)
                
                self.is_connected = True
                self.lbl_status.config(text=f"Trạng thái: Đã kết nối {port} (ID: {slave_id})", fg="green")
                self.btn_connect.config(text="Ngắt kết nối", bg="#f44336")
                self.enable_controls(True)
                
            except Exception as e:
                messagebox.showerror("Lỗi kết nối", f"Không thể kết nối cổng {port}:\n{e}")
        else:
            self.turn_off_all()
            self.is_connected = False
            self.lbl_status.config(text="Trạng thái: Đã ngắt kết nối", fg="red")
            self.btn_connect.config(text="Kết nối", bg="#4CAF50")
            self.enable_controls(False)

    def enable_controls(self, enable):
        state = "normal" if enable else "disabled"
        self.btn_bom_toggle.config(state=state)
        self.btn_quat_toggle.config(state=state)
        self.btn_auto.config(state=state)
        self.btn_off_all.config(state=state)

    # --- ĐIỀU KHIỂN BƠM (RELAY 1) ---
    def toggle_bom(self):
        if not self.is_connected: return
        try:
            new_state = not self.bom_state
            self.instrument.write_bit(0, 1 if new_state else 0)
            self.bom_state = new_state
            
            if new_state:
                self.lbl_bom_status.config(text="BƠM ĐANG BẬT", bg="#4CAF50")
                self.btn_bom_toggle.config(text="TẮT BƠM")
            else:
                self.lbl_bom_status.config(text="ĐANG TẮT", bg="#f44336")
                self.btn_bom_toggle.config(text="BẬT BƠM")
        except Exception as e:
            messagebox.showerror("Lỗi truyền thông", f"Lỗi điều khiển Bơm: {e}")

    # --- ĐIỀU KHIỂN QUẠT (RELAY 2) ---
    def toggle_quat(self):
        if not self.is_connected: return
        try:
            new_state = not self.quat_state
            self.instrument.write_bit(1, 1 if new_state else 0)
            self.quat_state = new_state
            
            if new_state:
                self.lbl_quat_status.config(text="QUẠT ĐANG BẬT", bg="#4CAF50")
                self.btn_quat_toggle.config(text="TẮT QUẠT")
            else:
                self.lbl_quat_status.config(text="ĐANG TẮT", bg="#f44336")
                self.btn_quat_toggle.config(text="BẬT QUẠT")
        except Exception as e:
            messagebox.showerror("Lỗi truyền thông", f"Lỗi điều khiển Quạt: {e}")

    # --- TẮT TẤT CẢ ---
    def turn_off_all(self):
        if not self.is_connected: return
        try:
            self.instrument.write_bit(0, 0)
            self.instrument.write_bit(1, 0)
            self.bom_state = False
            self.quat_state = False
            
            self.lbl_bom_status.config(text="ĐANG TẮT", bg="#f44336")
            self.btn_bom_toggle.config(text="BẬT BƠM")
            self.lbl_quat_status.config(text="ĐANG TẮT", bg="#f44336")
            self.btn_quat_toggle.config(text="BẬT QUẠT")
        except Exception as e:
            messagebox.showerror("Lỗi truyền thông", f"Lỗi ngắt thiết bị: {e}")

    # --- CHẠY KỊCH BẢN TỰ ĐỘNG ---
    def run_auto_sequence(self):
        def auto_thread():
            self.enable_controls(False)
            try:
                # 1. Bật Quạt làm mát trước (3s)
                if not self.quat_state: self.toggle_quat()
                time.sleep(3)

                # 2. Bật Bơm tưới (5s)
                if not self.bom_state: self.toggle_bom()
                time.sleep(5)

                # 3. Tắt Bơm
                if self.bom_state: self.toggle_bom()
                time.sleep(2)

                # 4. Tắt Quạt
                if self.quat_state: self.toggle_quat()

            except Exception as e:
                messagebox.showerror("Lỗi", f"Lỗi chạy kịch bản: {e}")
            finally:
                self.enable_controls(True)

        threading.Thread(target=auto_thread, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = ModbusRelayGUI(root)
    root.mainloop()