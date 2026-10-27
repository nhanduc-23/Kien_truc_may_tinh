import time
import minimalmodbus

# 1. Cấu hình kết nối cổng COM5 và Slave ID = 255
instrument = minimalmodbus.Instrument('COM5', slaveaddress=255)
instrument.serial.baudrate = 9600
instrument.serial.bytesize = 8
instrument.serial.parity = minimalmodbus.serial.PARITY_NONE
instrument.serial.stopbits = 1
instrument.serial.timeout = 0.5
instrument.mode = minimalmodbus.MODE_RTU

# Địa chỉ Coil:
# Relay 1 (Bơm)  -> Coil 0
# Relay 2 (Quạt) -> Coil 1

def bat_bom():
    print("[+] Bật Bơm (Relay 1)...")
    instrument.write_bit(0, 1)

def tat_bom():
    print("[-] Tắt Bơm (Relay 1)...")
    instrument.write_bit(0, 0)

def bat_quat():
    print("[+] Bật Quạt (Relay 2)...")
    instrument.write_bit(1, 1)

def tat_quat():
    print("[-] Tắt Quạt (Relay 2)...")
    instrument.write_bit(1, 0)

# --- CHƯƠNG TRÌNH THỦ NGHIỆM ---
if __name__ == '__main__':
    try:
        # Bật quạt trong 3 giây
        bat_quat()
        time.sleep(3)

        # Bật bơm trong 3 giây
        bat_bom()
        time.sleep(3)

        # Tắt toàn bộ
        tat_bom()
        tat_quat()
        print("\n[OK] Thử nghiệm hoàn toàn thành công!")

    except Exception as e:
        print(f"[LỖI]: {e}")