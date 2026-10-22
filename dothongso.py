import time
import minimalmodbus
import serial

COM_PORT = "COM5"

# Khởi tạo đối tượng Modbus
instrument = minimalmodbus.Instrument(COM_PORT, 1)
instrument.mode = minimalmodbus.MODE_RTU
instrument.serial.bytesize = 8
instrument.serial.parity = serial.PARITY_NONE
instrument.serial.stopbits = 1
instrument.serial.timeout = 0.5
instrument.clear_buffers_before_each_transaction = True

def safe_modbus_switch(slave_id, baudrate):
    """Xóa đệm cổng nối tiếp và đổi Baudrate an toàn trên COM5"""
    if instrument.serial.baudrate != baudrate:
        instrument.serial.baudrate = baudrate
        time.sleep(0.1)  # Khoảng nghỉ để đường truyền RS485 ổn định sau khi đổi tốc độ

    instrument.address = slave_id
    
    # Xả sạch bộ đệm truyền/nhận rác còn sót lại trên COM5
    if instrument.serial.is_open:
        instrument.serial.reset_input_buffer()
        instrument.serial.reset_output_buffer()

def read_sht40():
    """Đọc Cảm biến SHT40 (Slave ID: 1, Baudrate: 4800)"""
    try:
        safe_modbus_switch(slave_id=1, baudrate=4800)
        
        registers = instrument.read_registers(registeraddress=0, number_of_registers=2, functioncode=3)
        raw_humi = registers[0]
        raw_temp = registers[1]

        if raw_temp > 32767:
            raw_temp -= 65536

        temp = raw_temp / 10.0
        humi = raw_humi / 10.0
        print(f"[CẢM BIẾN - ONLINE] Nhiệt độ: {temp}°C | Độ ẩm: {humi}%")
        return temp, humi
    except Exception as e:
        print(f"[CẢM BIẾN - LỖI]: {e}")
        return None, None

def control_relay(relay_channel, state):
    """Điều khiển Relay Bơm/Quạt (Slave ID: 255, Baudrate: 9600)
       relay_channel: 0 (Relay 1 - Bơm), 1 (Relay 2 - Quạt)
       state: True (Bật), False (Tắt)
    """
    try:
        safe_modbus_switch(slave_id=255, baudrate=9600)
        
        instrument.write_bit(registeraddress=relay_channel, value=1 if state else 0)
        print(f"[RELAY {relay_channel + 1}] -> {'BẬT' if state else 'TẮT'} thành công")
        return True
    except Exception as e:
        print(f"[RELAY {relay_channel + 1} - LỖI]: {e}")
        return False

# ==========================================================
# CHƯƠNG TRÌNH THỬ NGHIỆM TRÊN COM5
# ==========================================================
if __name__ == "__main__":
    print("--- BẮT ĐẦU KIỂM TRA CHUYỂN ĐỔI AN TOÀN TRÊN COM5 ---")
    
    # 1. Đọc Cảm biến
    read_sht40()
    time.sleep(0.5)

    # 2. Thử Bật Bơm (Relay 1)
    control_relay(relay_channel=0, state=True)
    time.sleep(1.0)

    # 3. Đọc lại Cảm biến
    read_sht40()
    time.sleep(0.5)

    # 4. Thử Tắt Bơm (Relay 1)
    control_relay(relay_channel=0, state=False)
    time.sleep(0.5)

    # 5. Thử Bật Quạt (Relay 2)
    control_relay(relay_channel=1, state=True)
    time.sleep(1.0)

    # 6. Tắt Quạt (Relay 2)
    control_relay(relay_channel=1, state=False)