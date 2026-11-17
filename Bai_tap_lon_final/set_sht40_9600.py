import time
import minimalmodbus
import serial

PORT = "COM5"          # Đổi thành cổng COM thực tế của mạch USB-RS485 nếu khác
SLAVE_ID = 1           # Địa chỉ Slave ID hiện tại của cảm biến SHT40
OLD_BAUDRATE = 4800    # Tốc độ hiện tại của SHT40
NEW_BAUDRATE = 9600    # Tốc độ mục tiêu đồng bộ toàn hệ thống

# Bảng mã thanh ghi 0x07D1 của cảm biến SHT40 Modbus RTU:
# 0 = 2400 bps | 1 = 4800 bps | 2 = 9600 bps
BAUD_CODE_9600 = 2

def test_read(port, slave_id, baud):
    inst = minimalmodbus.Instrument(port, slave_id)
    inst.mode = minimalmodbus.MODE_RTU
    inst.serial.baudrate = baud
    inst.serial.bytesize = 8
    inst.serial.parity = serial.PARITY_NONE
    inst.serial.stopbits = 1
    inst.serial.timeout = 0.6
    inst.clear_buffers_before_each_transaction = True
    try:
        regs = inst.read_registers(registeraddress=0, number_of_registers=2, functioncode=3)
        humi = regs[0] / 10.0
        temp = (regs[1] - 65536 if regs[1] > 32767 else regs[1]) / 10.0
        return True, temp, humi
    finally:
        if inst.serial and inst.serial.is_open:
            inst.serial.close()

def main():
    print("=" * 65)
    print(f"CẤU HÌNH ĐỒNG BỘ CẢM BIẾN SHT40 LÊN {NEW_BAUDRATE} BPS (CỔNG {PORT})")
    print("=" * 65)

    # Bước 1: Kiểm tra xem cảm biến đã ở 9600 bps sẵn chưa
    try:
        ok, t, h = test_read(PORT, SLAVE_ID, NEW_BAUDRATE)
        if ok:
            print(f"[OK] Cảm biến SHT40 ĐÃ Ở SẴN MỨC {NEW_BAUDRATE} BPS! (T = {t:.1f}°C, H = {h:.1f}%)")
            print("     Bạn có thể chạy trực tiếp file PC1.py ngay bây giờ.")
            return
    except Exception:
        pass

    # Bước 2: Kết nối ở mức 4800 bps và gửi lệnh FC06 ghi vào thanh ghi 0x07D1
    try:
        ok, t, h = test_read(PORT, SLAVE_ID, OLD_BAUDRATE)
        print(f"[1/3] Đã kết nối SHT40 ở {OLD_BAUDRATE} bps -> Nhiệt độ: {t:.1f}°C | Độ ẩm: {h:.1f}%")
    except Exception as e:
        print(f"[X] Không tìm thấy SHT40 ở {OLD_BAUDRATE} bps lẫn {NEW_BAUDRATE} bps: {e}")
        print("    -> Kiểm tra lại cổng COM, dây A+/B- và nguồn cấp 12V cho cảm biến (nhớ tắt PC1.py trước khi chạy).")
        return

    try:
        inst = minimalmodbus.Instrument(PORT, SLAVE_ID)
        inst.mode = minimalmodbus.MODE_RTU
        inst.serial.baudrate = OLD_BAUDRATE
        inst.serial.bytesize = 8
        inst.serial.parity = serial.PARITY_NONE
        inst.serial.stopbits = 1
        inst.serial.timeout = 0.6
        inst.clear_buffers_before_each_transaction = True

        print(f"[2/3] Đang gửi lệnh Modbus FC06 ghi giá trị 2 vào thanh ghi 0x07D1...")
        inst.write_register(registeraddress=0x07D1, value=BAUD_CODE_9600, functioncode=6)
        if inst.serial and inst.serial.is_open:
            inst.serial.close()
        print("      Đã gửi lệnh cấu hình thành công!")
    except Exception as e:
        print(f"[X] Lỗi khi ghi thanh ghi 0x07D1: {e}")
        return

    # Bước 3: Kiểm tra lại ở tốc độ 9600 bps mới
    time.sleep(0.5)
    try:
        ok, t, h = test_read(PORT, SLAVE_ID, NEW_BAUDRATE)
        if ok:
            print(f"[3/3] [OK] XÁC NHẬN THÀNH CÔNG! SHT40 đã phản hồi ở {NEW_BAUDRATE} bps (T = {t:.1f}°C, H = {h:.1f}%).")
            return
    except Exception:
        pass

    print("\n[!] Lưu ý phần cứng: Cảm biến SHT40 cần khởi động lại nguồn để áp dụng tốc độ mới.")
    input("    Hãy RÚT NGUỒN cảm biến SHT40, cắm lại rồi nhấn phím ENTER để kiểm tra...")

    try:
        ok, t, h = test_read(PORT, SLAVE_ID, NEW_BAUDRATE)
        if ok:
            print(f"[3/3] [OK] XÁC NHẬN THÀNH CÔNG! SHT40 đã chạy ổn định ở {NEW_BAUDRATE} bps (T = {t:.1f}°C, H = {h:.1f}%).")
    except Exception as e:
        print(f"[X] Vẫn chưa đọc được ở {NEW_BAUDRATE} bps: {e}")

if __name__ == "__main__":
    main()