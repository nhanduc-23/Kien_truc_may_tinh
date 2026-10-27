import time
import minimalmodbus

# 1. Cấu hình kết nối cổng COM5 và Slave ID = 255 (Đã test thành công)
instrument = minimalmodbus.Instrument('COM5', slaveaddress=255)
instrument.serial.baudrate = 9600
instrument.serial.bytesize = 8
instrument.serial.parity = minimalmodbus.serial.PARITY_NONE
instrument.serial.stopbits = 1
instrument.serial.timeout = 0.5
instrument.mode = minimalmodbus.MODE_RTU

# 2. Định nghĩa hàm điều khiển Thiết bị 1 (Đèn chiếu sáng - Coil 0)
def bat_den():
    print("[+] Bật Đèn chiếu sáng (Relay 1)...")
    instrument.write_bit(0, 1)

def tat_den():
    print("[-] Tắt Đèn chiếu sáng (Relay 1)...")
    instrument.write_bit(0, 0)

# 3. Định nghĩa hàm điều khiển Thiết bị 2 (Quạt thông gió - Coil 1)
def bat_quat_thong_gio():
    print("[+] Bật Quạt thông gió (Relay 2)...")
    instrument.write_bit(1, 1)

def tat_quat_thong_gio():
    print("[-] Tắt Quạt thông gió (Relay 2)...")
    instrument.write_bit(1, 0)

# 4. Hàm chạy kịch bản tự động thử nghiệm
def kich_ban_tu_dong():
    print("\n--- Bắt đầu chạy kịch bản tự động ---")
    bat_den()
    time.sleep(2)

    bat_quat_thong_gio()
    time.sleep(3)

    tat_den()
    time.sleep(1)

    tat_quat_thong_gio()
    print("--- Hoàn tất kịch bản ---\n")

# --- CHƯƠNG TRÌNH CHÍNH (MENU TƯƠNG TÁC) ---
if __name__ == '__main__':
    try:
        while True:
            print("==========================================")
            print("  BẢNG ĐIỀU KHIỂN THIẾT BỊ RS485 MODBUS   ")
            print("==========================================")
            print(" 1. Bật Đèn chiếu sáng (Relay 1)")
            print(" 2. Tắt Đèn chiếu sáng (Relay 1)")
            print(" 3. Bật Quạt thông gió (Relay 2)")
            print(" 4. Tắt Quạt thông gió (Relay 2)")
            print(" 5. Chạy kịch bản bật/tắt tự động")
            print(" 0. Tắt hết & Thao thoát")
            print("==========================================")
            
            chon = input("Nhập lựa chọn của bạn (0-5): ").strip()

            if chon == '1':
                bat_den()
            elif chon == '2':
                tat_den()
            elif chon == '3':
                bat_quat_thong_gio()
            elif chon == '4':
                tat_quat_thong_gio()
            elif chon == '5':
                kich_ban_tu_dong()
            elif chon == '0':
                print("[!] Đang tắt toàn bộ thiết bị trước khi thoát...")
                tat_den()
                tat_quat_thong_gio()
                print("[OK] Đã thoát chương trình.")
                break
            else:
                print("[X] Lựa chọn không hợp lệ, vui lòng thử lại!")
            
            time.sleep(0.5)

    except Exception as e:
        print(f"\n[LỖI]: Không thể giao tiếp với thiết bị trên COM5: {e}")