import minimalmodbus
import serial
import time

# --- CẤU HÌNH THEO KẾT QUẢ QUÉT THỰC TẾ ---
PORT = 'COM5'          # Cổng USB CH340
SLAVE_ADDRESS = 1      # Slave ID tìm thấy
BAUDRATE = 9600        # Baudrate thực tế của cảm biến

# Khởi tạo đối tượng Modbus
sensor = minimalmodbus.Instrument(PORT, SLAVE_ADDRESS)

# Cấu hình nối tiếp RS485
sensor.serial.baudrate = BAUDRATE
sensor.serial.bytesize = 8
sensor.serial.parity = serial.PARITY_NONE
sensor.serial.stopbits = 1
sensor.serial.timeout = 0.5          # Thời gian chờ phản hồi (giây)
sensor.serial.write_timeout = 1.0    # Tránh kẹt đệm ghi
sensor.mode = minimalmodbus.MODE_RTU

def read_sht40():
    try:
        # Đọc 2 thanh ghi từ 0x0000 (0: Độ ẩm, 1: Nhiệt độ)
        registers = sensor.read_registers(registeraddress=0, number_of_registers=2, functioncode=3)
        
        # Đáo thứ tự thanh ghi
        hum_raw = registers[0]   # Thanh ghi 0 là ĐỘ ẨM
        temp_raw = registers[1]  # Thanh ghi 1 là NHIỆT ĐỘ
        
        # Xử lý số âm cho nhiệt độ (16-bit signed)
        if temp_raw > 32767:
            temp_raw -= 65536
            
        hum = hum_raw / 10.0
        temp = temp_raw / 10.0

        print(f"[{time.strftime('%H:%M:%S')}] Nhiệt độ: {temp:.1f} °C | Độ ẩm: {hum:.1f} %RH")

    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Lỗi đọc cảm biến: {e}")

if __name__ == '__main__':
    print(f"Đang đọc cảm biến SHT40 (COM5 | Baud: {BAUDRATE} | ID: {SLAVE_ADDRESS})...")
    while True:
        read_sht40()
        time.sleep(2)  # Đọc định kỳ 2 giây/lần