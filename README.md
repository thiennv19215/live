# TikTok Live OBS Controller & Dashboard

Ứng dụng điều khiển OBS Studio tự động thông qua sự kiện quà tặng TikTok Live realtime.

## Tính năng
- Kết nối TikTok Live & OBS WebSocket v5.
- Dashboard Cyber Deck đơn giản: một video nền chạy liên tục và Stream Deck để gọi hành động.
- Hàng đợi FIFO: quà đến trước phát trước, quà đến sau xếp phía sau.
- Hỗ trợ Chế độ Giả lập (Mock Mode) để thử nghiệm offline không cần OBS/TikTok.

## Hướng dẫn sử dụng
1. Cài đặt thư viện: `pip install -r requirements.txt`
2. Chạy ứng dụng giao diện: `python tiktok_obs_gui.py`

## Thiết lập OBS theo layer nhân vật

Để thay riêng từng nhân vật mà không chồng hình, tạo các source trong cùng Scene theo thứ tự từ trên xuống:

1. `Action_Source_4`, `Idle_Source_4`
2. `Action_Source_3`, `Idle_Source_3`
3. `Action_Source_2`, `Idle_Source_2`
4. `Action_Source_1`, `Idle_Source_1`
5. Background cố định, có thể là Image hoặc Media Source bất kỳ

Mỗi `Idle_Source_N` và `Action_Source_N` nên dùng WebM VP9 có alpha hoặc MOV ProRes 4444 nền trong suốt. Background không được chứa sẵn nhân vật.

OBS chỉ cần hai Media Source trong scene: `Idle_Source` cho video nền lặp liên tục và `Action_Source` cho video hành động. Khi nhận quà, ứng dụng bật `Action_Source`, tạm ẩn nền, rồi tự quay lại `Idle_Source` khi hành động kết thúc.
