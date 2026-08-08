# Khả năng tương tác người dùng của TikTok Live repo

## Tổng quan

Phiên bản hiện tại là hệ thống **nhận tương tác TikTok → khớp luật → xếp hàng → phát video và âm thanh**. Ngoài quà tặng, ứng dụng hỗ trợ bình luận theo từ khóa, follow, share, like theo ngưỡng, người xem vào phòng và đăng ký LIVE.

## Tương tác TikTok đã hỗ trợ

- Kết nối vào phòng live bằng TikTok username.
- Theo dõi trạng thái kết nối và tự thử kết nối lại khi mất kết nối.
- Nhận sự kiện quà tặng, bình luận, follow, share, like, join và subscribe theo thời gian thực.
- Với quà dạng streak, chỉ tạo action khi chuỗi quà kết thúc để tránh phát lặp từng nhịp.
- Ánh xạ từng loại tương tác thành một hoặc nhiều video hành động.
- Đặt từ khóa cho bình luận, ngưỡng cho like và cooldown riêng cho từng luật.
- Gán âm thanh riêng cho từng hành động.
- Luân phiên các video theo thứ tự khi một hành động được gán nhiều video.
- Bỏ qua những sự kiện chưa được cấu hình hoặc luật đã tắt.
- Đưa action vào hàng đợi FIFO theo đúng thứ tự nhận sự kiện.
- Phát nội dung qua cửa sổ output, Browser Overlay và OBS tùy chọn.

Handler TikTok đăng ký các loại sự kiện:

- `ConnectEvent`
- `DisconnectEvent`
- `GiftEvent`
- `CommentEvent`
- `FollowEvent`
- `ShareEvent`
- `LikeEvent`
- `JoinEvent`
- `SubNotifyEvent`

## Thao tác dành cho người vận hành

- Bắt đầu hoặc ngắt hệ thống.
- Chọn TikTok trực tiếp hoặc chế độ giả lập offline.
- Bật/tắt đồng bộ OBS.
- Nhập TikTok username và cấu hình OBS WebSocket.
- Thêm, bật/tắt và xóa luật tương tác TikTok.
- Gán video cho quà, follow, like, share, bình luận, join và subscribe.
- Phát thử từng luật tương tác trong preview.
- Chọn video nền và quản lý thư viện video.
- Xem action đang phát, tiến trình và thời gian còn lại.
- Bỏ qua action hiện tại hoặc xóa hàng đợi.
- Chọn tỷ lệ output `9:16`, `16:9`, `1:1` hoặc `4:5`.
- Chọn cách hiển thị crop, nguyên bản hoặc contain.
- Bật/tắt âm thanh preview.
- Mở cửa sổ output hoặc sao chép Browser Overlay URL.
- Theo dõi trạng thái backend, TikTok, OBS, overlay và log.

## Chưa được hỗ trợ

- Sự kiện người xem rời phòng.
- Poll hoặc vote.
- Gửi tin nhắn hay phản hồi trực tiếp cho người xem.
- Hiển thị tên người tương tác dưới dạng chữ trên output.
- Trigger theo username hoặc cấp độ người xem.

## Lưu ý kỹ thuật

Tên người xem, số lần lặp, diamond, loại sự kiện và giá trị sự kiện được lưu trong job và lịch sử. Với like, `LikeEvent.count` được so với ngưỡng của luật; với bình luận, nội dung được so khớp không phân biệt hoa thường.

## Hướng mở rộng đề xuất

1. Hiển thị tên người tương tác và thông tin sự kiện trên overlay.
2. Bổ sung trigger theo username hoặc cấp độ người xem.
3. Bổ sung thống kê riêng cho từng loại tương tác.
4. Bổ sung poll/vote và sự kiện rời phòng nếu TikTok cung cấp ổn định.

## Các file chính

- `tiktok_obs_controller.py`: kết nối TikTok, nhận quà và điều phối phát action.
- `tiktok_event_rules.py`: chuẩn hóa và so khớp luật sự kiện.
- `tiktok_playback_queue.py`: model job và hàng đợi FIFO.
- `tiktok_media_catalog.py`: model hành động và helper danh sách media.
- `tiktok_backend.py`: API cho giao diện Electron.
- `tiktok_overlay.py`: Browser Overlay phát video và âm thanh.
- `electron_output/renderer/src/App.jsx`: bố cục giao diện chính.
- `electron_output/renderer/src/components/GiftMatrix.jsx`: cấu hình luật tương tác TikTok.
- `electron_output/renderer/src/components/QuickSimulator.jsx`: giả lập các loại sự kiện.
- `electron_output/renderer/src/components/OutputStage.jsx`: preview và điều khiển output.
