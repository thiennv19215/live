# TikTok Live OBS Controller & Dashboard

Ứng dụng điều khiển OBS Studio tự động thông qua sự kiện quà tặng TikTok Live realtime.

## Tính năng
- Kết nối TikTok Live & OBS WebSocket v5.
- Dashboard Cyber Deck đơn giản: một video nền chạy liên tục và Stream Deck để gọi hành động.
- Browser Overlay dọc chạy nội bộ để TikTok Live Studio nhận hình trực tiếp, không cần quay màn hình hoặc OBS.
- Hàng đợi FIFO: quà đến trước phát trước, quà đến sau xếp phía sau.
- Hỗ trợ Chế độ Giả lập (Mock Mode) để thử nghiệm offline không cần OBS/TikTok.

## Hướng dẫn sử dụng
1. Cài đặt thư viện: `pip install -r requirements.txt`
2. Chạy ứng dụng giao diện: `python tiktok_obs_gui.py`

## Xuất hình trực tiếp sang TikTok Live Studio

Ứng dụng tự mở Browser Overlay tại địa chỉ hiển thị trong ô `BROWSER OVERLAY · TIKTOK STUDIO`.

1. Bấm `COPY URL` trong ứng dụng.
2. Trong TikTok Live Studio, thêm nguồn `Link`, `Web page` hoặc `Browser`.
3. Dán URL overlay và đặt kích thước nguồn thành `1080x1920`.
4. Bấm `BẮT ĐẦU KẾT NỐI`; video nền và action từ queue sẽ tự chuyển trên nguồn này.

Overlay chỉ lắng nghe trên `127.0.0.1`, không mở ra mạng LAN và không cần quyền quay màn hình. Thêm `?muted=1` nếu muốn tắt âm thanh, hoặc `?fit=contain` nếu muốn giữ trọn khung hình thay vì lấp đầy màn hình dọc.

## Thiết lập OBS theo layer nhân vật

Để thay riêng từng nhân vật mà không chồng hình, tạo các source trong cùng Scene theo thứ tự từ trên xuống:

1. `Action_Source_4`, `Idle_Source_4`
2. `Action_Source_3`, `Idle_Source_3`
3. `Action_Source_2`, `Idle_Source_2`
4. `Action_Source_1`, `Idle_Source_1`
5. Background cố định, có thể là Image hoặc Media Source bất kỳ

Mỗi `Idle_Source_N` và `Action_Source_N` nên dùng WebM VP9 có alpha hoặc MOV ProRes 4444 nền trong suốt. Background không được chứa sẵn nhân vật.

OBS chỉ cần hai Media Source trong scene: `Idle_Source` cho video nền lặp liên tục và `Action_Source` cho video hành động. Khi nhận quà, ứng dụng bật `Action_Source`, tạm ẩn nền, rồi tự quay lại `Idle_Source` khi hành động kết thúc.
