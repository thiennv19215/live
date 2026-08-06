# Khả năng tương tác người dùng của TikTok Live repo

## Tổng quan

Phiên bản hiện tại là hệ thống **nhận quà TikTok → xếp hàng → phát video và âm thanh**. Ứng dụng đã hỗ trợ khá đầy đủ việc vận hành nội dung theo quà tặng, nhưng chưa hỗ trợ các tương tác sâu hơn như bình luận, like, follow hoặc trả lời người xem.

## Tương tác TikTok đã hỗ trợ

- Kết nối vào phòng live bằng TikTok username.
- Theo dõi trạng thái kết nối và tự thử kết nối lại khi mất kết nối.
- Nhận sự kiện quà tặng theo thời gian thực.
- Với quà dạng streak, chỉ tạo action khi chuỗi quà kết thúc để tránh phát lặp từng nhịp.
- Ánh xạ tên quà thành một hoặc nhiều video hành động.
- Gán âm thanh riêng cho từng quà.
- Chọn ngẫu nhiên một video khi quà được gán nhiều video.
- Bỏ qua những quà chưa được cấu hình.
- Đưa action vào hàng đợi FIFO: quà đến trước được phát trước.
- Phát nội dung qua cửa sổ output, Browser Overlay và OBS tùy chọn.

Handler TikTok hiện chỉ đăng ký ba loại sự kiện:

- `ConnectEvent`
- `DisconnectEvent`
- `GiftEvent`

## Thao tác dành cho người vận hành

- Bắt đầu hoặc ngắt hệ thống.
- Chọn TikTok trực tiếp hoặc chế độ giả lập offline.
- Bật/tắt đồng bộ OBS.
- Nhập TikTok username và cấu hình OBS WebSocket.
- Thêm, sửa và xóa mapping quà.
- Gán nhiều video và một file audio cho mỗi quà.
- Phát thử quà trong preview, lặp tối đa 20 lần.
- Chọn video nền và quản lý thư viện video.
- Xem action đang phát, tiến trình và thời gian còn lại.
- Bỏ qua action hiện tại hoặc xóa hàng đợi.
- Chọn tỷ lệ output `9:16`, `16:9`, `1:1` hoặc `4:5`.
- Chọn cách hiển thị crop, nguyên bản hoặc contain.
- Bật/tắt âm thanh preview.
- Mở cửa sổ output hoặc sao chép Browser Overlay URL.
- Theo dõi trạng thái backend, TikTok, OBS, overlay và log.

## Chưa được hỗ trợ

- Nhận hoặc xử lý bình luận/chat.
- Trigger theo từ khóa trong bình luận.
- Like hoặc tổng số like.
- Follow mới.
- Share live.
- Subscribe.
- Sự kiện người xem vào hoặc rời phòng.
- Poll hoặc vote.
- Gửi tin nhắn hay phản hồi trực tiếp cho người xem.
- Hiển thị tên người tặng trên output.
- Phân biệt người gửi quà.
- Lưu số lượng quà hoặc tổng diamond thực tế.
- Trigger theo username hoặc cấp độ người xem.

## Lưu ý kỹ thuật

### Tên người xem và diamond chưa được sử dụng

Giao diện giả lập có ô nhập tên người xem và diamond, nhưng request backend hiện chỉ sử dụng trường `gift`. Vì vậy hai giá trị này chưa được lưu vào job, hàng đợi hoặc output.

### Priority chưa ảnh hưởng thứ tự phát

Mỗi mapping có trường `priority`, nhưng hàng đợi hiện dùng `append` và `popleft`. Do đó đây vẫn là FIFO thuần túy; quà có priority cao không được phát trước.

## Hướng mở rộng đề xuất

1. Truyền metadata người tặng, số lượng và diamond vào `GiftJob`.
2. Hiển thị tên người tặng và thông tin quà trên overlay.
3. Bổ sung `CommentEvent` và hệ thống lệnh chat.
4. Bổ sung trigger cho like, follow, share và subscribe.
5. Xác định rõ priority chỉ dùng để hiển thị hay phải thay đổi thứ tự queue.
6. Lưu lịch sử sự kiện để thống kê người tương tác và tổng giá trị quà.

## Các file chính

- `tiktok_obs_controller.py`: kết nối TikTok, nhận quà, quản lý queue và phát action.
- `tiktok_backend.py`: API cho giao diện Electron.
- `tiktok_overlay.py`: Browser Overlay phát video và âm thanh.
- `electron_output/renderer/src/App.jsx`: bố cục giao diện chính.
- `electron_output/renderer/src/components/GiftMatrix.jsx`: cấu hình mapping quà.
- `electron_output/renderer/src/components/QuickSimulator.jsx`: giả lập sự kiện quà.
- `electron_output/renderer/src/components/OutputStage.jsx`: preview và điều khiển output.
