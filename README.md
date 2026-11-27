# 🌿 Hệ thống làm mát Cooling Pad kết hợp quạt hút trong công nghiệp ứng dụng truyền thông Modbus RTU, TCP/IP LAN, Web Dashboard và Blynk Cloud

Hệ thống IoT/SCADA đa tầng thu thập dữ liệu cảm biến môi trường (SHT40) chuẩn giao tiếp công nghiệp **Modbus RTU / RS485**, truyền tin qua mạng nội bộ **TCP/IP LAN (JSON)** và hỗ trợ giám sát/điều khiển đa nền tảng từ xa qua **Flask Web Dashboard (Cloudflare Tunnel)** và **Blynk IoT Cloud**.

---

## 🛠️ 1. Cài Đặt Môi Trường & Thư Viện

### Yêu cầu hệ thống
- **Python 3.9+** (Khuyên dùng VS Code hoặc Thonny).
- **Cáp USB-RS485** đã cài Driver (CH340 / CP2102).

### Lệnh cài đặt thư viện
Mở **Terminal / CMD** trên từng máy tính và gõ câu lệnh tương ứng:

* **Trên máy PC1 (Field Gateway):** *(Dùng để đọc cảm biến SHT40 và kích Module Relay qua RS485)*
  ```bash
  pip install pyserial minimalmodbus
  ```

* **Trên máy PC2 (Central Server / Web / Cloud):** *(Dùng để mở HMI Tkinter, Web Flask và kết nối Blynk API)*
  ```bash
  pip install flask requests customtkinter matplotlib
  ```

---

## ⚙️ 2. Hướng Dẫn Vận Hành Hệ Thống

### 📍 Bước 1: Khởi chạy PC2 Server (Máy chủ trung tâm)
Mở Terminal tại thư mục code trên PC2 và chạy:
```bash
python pc2_server.py
```

### 📍 Bước 2: Đẩy Web Dashboard lên Internet (Cloudflare Tunnel)
Mở thêm cửa sổ Terminal thứ hai trên PC2 và gõ:
```bash
cloudflared.exe tunnel --url http://127.0.0.1:5000
```
> 📌 **Lưu ý:** Sao chép đường link `[https://...trycloudflare.com](https://...trycloudflare.com)` hiển thị ở Terminal 2 gửi sang điện thoại hoặc máy tính khác để truy cập Web Online.

### 📍 Bước 3: Khởi chạy PC1 Gateway (Trạm hiện trường)
1. Cắm cáp USB-RS485 vào PC1, mở Terminal và chạy:
   ```bash
   python pc1_gateway.py
   ```
2. Chọn cổng **COM5** (hoặc cổng COM tương ứng trên máy) $\rightarrow$ Nhấn **KẾT NỐI RS485**.
3. Nhập địa chỉ **IP của PC2** (ví dụ: `192.168.1.100`) $\rightarrow$ Nhấn **KẾT NỐI PC2 SERVER**.

---

## 🔄 3. Kiến Trúc Kết Nối Tóm Tắt

```text
┌─────────────────────────────┐
│  Cảm biến SHT40 & Relay     │
│  (Bơm Cooling Pad / Quạt)   │
└──────────────┬──────────────┘
               │  Modbus RTU / RS485 (Half-Duplex)
               ▼
┌─────────────────────────────┐
│        PC1 Gateway          │
│ (RTU Master & Edge Control) │
└──────────────┬──────────────┘
               │  TCP/IP LAN - JSON (Port 65432)
               ▼
┌─────────────────────────────┐
│         PC2 Server          │
│ (HMI Tkinter + Flask Web)   │
└──────┬───────────────┬──────┘
       │               │
       │ HTTP/HTTPS    │ TCP Socket / REST API
       ▼               ▼
┌─────────────┐ ┌─────────────┐
│  Web Local  │ │ Blynk Cloud │
│ & Cloudflare│ │ (App Mobile)│
└─────────────┘ └─────────────┘
```

---

## 🤖 4. Logic Điều Khiển Tự Động (Auto Mode)

Khi chế độ **Auto** được kích hoạt và cảm biến SHT40 hoạt động ổn định, trạm biên **PC1 Gateway** tự động điều khiển vòng kín theo ngưỡng cài đặt (có thể thay đổi trực tiếp từ PC1, PC2 hoặc Web Dashboard):

- **Điều khiển Quạt hút (Nhiệt độ):**
  - Khi $T \ge 31.0^\circ\text{C}$ (vượt ngưỡng nhiệt độ): **Tự động BẬT Quạt hút** để thông gió, giảm nhiệt nhà xưởng.
  - Khi $T < 31.0^\circ\text{C}$: **Tự động TẮT Quạt hút**.
- **Điều khiển Bơm nước tuần hoàn Cooling Pad (Độ ẩm):**
  - Khi $H < 65.0\%$ (độ ẩm thấp, không khí khô nóng): **Tự động BẬT Bơm nước** làm ướt tấm Cooling Pad để tăng hiệu quả làm mát bay hơi.
  - Khi $H \ge 65.0\%$: **Tự động TẮT Bơm nước** để tránh dư ẩm.
- **Cơ chế an toàn (Fail-safe):** Nếu mất kết nối cảm biến trên đường truyền RS485, hệ thống tự động khóa kích hoạt Relay theo giá trị cũ và hiển thị cảnh báo mất tín hiệu lên giao diện HMI/Web.
