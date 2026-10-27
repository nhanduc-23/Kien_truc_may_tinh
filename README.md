# 🌿 Hệ Thống Giám Sát Cảm Biến Môi Trường & Điều Khiển Tự Động Quạt, Máy Bơm

Hệ thống IoT/SCADA đa tầng thu thập dữ liệu cảm biến môi trường (SHT40) chuẩn giao tiếp công nghiệp **Modbus RTU / RS485**, truyền tin qua mạng nội bộ **TCP/IP LAN (JSON)** và hỗ trợ giám sát/điều khiển đa nền tảng từ xa qua **Flask Web Dashboard (Cloudflare Tunnel)** và **Blynk IoT Cloud**.

---

## 🛠️ 1. Cài Đặt Môi Trường & Thư Viện

### Yêu cầu hệ thống
- **Python 3.9+** (Khuyên dùng VS Code hoặc Thonny)[cite: 11].
- **Cáp USB-RS485** đã cài Driver (CH340/CP2102)[cite: 15, 18].

### Lệnh cài đặt thư viện
Mở **Terminal / CMD** trên từng máy tính và gõ câu lệnh sau:

* Trên máy PC1 (Field Gateway):
  ```bash
  pip install pyserial minimalmodbus
  (Dùng để đọc cảm biến SHT40 và kích Module Relay qua RS485)
* Trên máy PC2 (Central Server / Web / Cloud):
  pip install flask requests customtkinter matplotlib
  (Dùng để mở HMI Tkinter, Web Flask và kết nối Blynk API)
⚙️ 2. Hướng Dẫn Vận Hành Hệ Thống
📍 Bước 1: Khởi chạy PC2 Server (Máy chủ trung tâm)
Mở Terminal tại thư mục code trên PC2 và chạy:
  python pc2_server.py
📍 Bước 2: Đẩy Web Dashboard lên Internet (Cloudflare Tunnel)
Mở thêm cửa sổ Terminal thứ hai trên PC2 và gõ:
cloudflared.exe tunnel --url [http://127.0.0.1:5000](http://127.0.0.1:5000)
📌 Lưu ý: Sao chép đường link https://...trycloudflare.com hiển thị ở Terminal 2 gửi sang điện thoại/máy tính để truy cập Web Online.

📍 Bước 3: Khởi chạy PC1 Gateway (Trạm hiện trường)
Cắm USB-RS485 vào PC1, mở Terminal và chạy:
  python pc1_gateway.py
Chọn cổng COM5 (hoặc cổng tương ứng) --> Nhấn KẾT NỐI RS485.
Nhập địa chỉ IP của PC2 (ví dụ: 192.168.1.100) --> Nhấn KẾT NỐI PC2 SERVER.
🔄 3. Kiến Trúc Kết Nối Tóm Tắt
[ Cảm biến SHT40 & Relay ] ──(Modbus RTU / RS485)──► [ PC1 Gateway ]
                                                             │
                                                    (TCP/IP LAN - Port 65432)
                                                             ▼
[ Web / Blynk Cloud ] ◄──(Cloudflare / REST API)── [ PC2 Server ]
Logic tự động

