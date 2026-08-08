# TikTok Live OBS Controller & Dashboard

## React + Electron Control Room (khuyến dùng)

Chạy `dist/TikTokLiveStudio_Setup.exe` để cài ứng dụng. Bộ cài tạo shortcut trên Desktop và Start Menu; Electron tự chạy `TikTokLiveBackend.exe` ẩn ở phía sau, vì vậy mọi thao tác cấu hình, test quà, queue và mở output đều nằm trong giao diện React mới. Khi cần nguồn cho TikTok Studio, bấm `Mở output` rồi chọn cửa sổ `TikTok Live Output`.

### Chạy nhanh ở chế độ dev

Tạo môi trường Python và cài backend một lần từ thư mục gốc:

```powershell
python -m venv .dev-python
.\.dev-python\Scripts\python.exe -m pip install -r requirements.txt
```

Trong thư mục `electron_output`, chạy Vite bằng `npm run dev`. Ở terminal thứ hai, trỏ Electron vào đúng renderer và Python vừa tạo rồi chạy `npm start`:

```powershell
$env:ELECTRON_RENDERER_URL = "http://127.0.0.1:5173"
$env:PYTHON_EXECUTABLE = (Resolve-Path "..\.dev-python\Scripts\python.exe")
npm start
```

Chế độ mặc định là **TikTok Studio trực tiếp**: preview điều khiển luôn tắt âm, cửa sổ `TikTok Live Output` là nguồn hình/âm duy nhất. Chỉ bật `Đồng bộ OBS` trong phần cài đặt nếu thực sự muốn phát qua OBS; không đưa đồng thời cả OBS và cửa sổ output vào TikTok Studio vì sẽ tạo hai đường audio.

## Cửa sổ Output cho TikTok Studio

1. Chọn tỉ lệ output trong Control Room (`9:16` phù hợp với live dọc).
2. Bấm `Mở output`.
3. Trong TikTok Studio, thêm nguồn cửa sổ và chọn `TikTok Live Stage Output (...)`.
4. Căn nguồn vào canvas. Có thể chuyển sang `Chạy ngầm` sau khi TikTok Studio đã nhận đúng cửa sổ.

Các tỉ lệ hỗ trợ gồm `9:16`, `16:9`, `1:1` và `4:5`. Nhấn `F11` để bật/tắt toàn màn hình hoặc `Esc` để đóng output. Không có file `TikTokLiveOutput.exe` riêng; output là cửa sổ con do `TikTokLiveStudio.exe` quản lý.

Ứng dụng nhận sự kiện TikTok realtime và phát trực tiếp sang TikTok Studio; OBS là tích hợp tùy chọn.

Trong tab `Sự kiện & lệnh`, người dùng có thể gán hành động cho quà tặng, bình luận chứa từ khóa, follow, share, lượt thích, người xem vào live và đăng ký LIVE. Mỗi luật có công tắc bật/tắt và cooldown riêng; luật chỉ được đánh dấu `ACTIVE` khi hành động có ít nhất một file video khả dụng. Mọi action được phát FIFO theo đúng thứ tự nhận sự kiện.

## Tính năng
- Kết nối TikTok Live & OBS WebSocket v5.
- Dashboard Cyber Deck đơn giản: một video nền chạy liên tục và Stream Deck để gọi hành động.
- Browser Overlay dọc chạy nội bộ để TikTok Live Studio nhận hình trực tiếp, không cần quay màn hình hoặc OBS.
- Hàng đợi FIFO: sự kiện đến trước phát trước, sự kiện đến sau xếp phía sau.
- Hỗ trợ Chế độ Giả lập (Mock Mode) để thử nghiệm offline không cần OBS/TikTok.

## Hướng dẫn sử dụng
1. Chạy `dist/TikTokLiveStudio_Setup.exe`, hoàn tất trình cài đặt rồi mở ứng dụng từ shortcut.
2. Ứng dụng Electron sẽ tự khởi động Python backend ở chế độ ẩn.

## Xuất hình trực tiếp sang TikTok Live Studio

Ứng dụng tự mở Browser Overlay tại địa chỉ hiển thị trong ô `BROWSER OVERLAY · TIKTOK STUDIO`.

1. Bấm `COPY URL` trong ứng dụng.
2. Trong TikTok Live Studio, thêm nguồn `Link`, `Web page` hoặc `Browser`.
3. Dán URL overlay và đặt kích thước nguồn thành `1080x1920`.
4. Bấm `BẮT ĐẦU KẾT NỐI`; video nền và action từ queue sẽ tự chuyển trên nguồn này.

Overlay chỉ lắng nghe trên `127.0.0.1`, không mở ra mạng LAN và không cần quyền quay màn hình. Thêm `?muted=1` nếu muốn tắt âm thanh, hoặc `?fit=contain` nếu muốn giữ trọn khung hình thay vì lấp đầy màn hình dọc.

## Thiết lập OBS tùy chọn

OBS chỉ cần hai Media Source trong scene: `Idle_Source` cho video nền lặp liên tục và `Action_Source` cho video hành động. Khi nhận quà, ứng dụng bật `Action_Source`, tạm ẩn nền, rồi tự quay lại `Idle_Source` khi hành động kết thúc.

Chế độ nhiều layer nhân vật (`Idle_Source_N`/`Action_Source_N`) đã được thay bằng luồng hai source dùng chung và không còn được hướng dẫn cho bản hiện tại.

## Build bản phát hành

Chạy `./build_exe.ps1` từ PowerShell. Script tự tạo `.build-python`, cài các phiên bản trong `requirements-build.txt`, chạy test Electron và đóng gói backend cùng Control Room thành bộ cài NSIS tại `dist/TikTokLiveStudio_Setup.exe`.
