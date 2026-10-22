# Bộ dữ liệu toy

Bộ dữ liệu nhỏ, viết tay, dùng để kiểm thử và minh họa trong báo cáo. Không ghi đè bằng dữ liệu sinh tự động.

## Nội dung

| Thành phần | Chi tiết |
|---|---|
| Lịch thi | 4 ngày (14–17/12/2026), 15 ca. Ngày 15/12 không có ca 2 |
| Phòng | G2-101 (60 ghế, 30 chỗ thi), G2-102 (40 ghế, 20 chỗ thi), G2-LAB1 (15 máy, ghi đè 12 chỗ thi) |
| Sinh viên | 46 sinh viên, mã 22020001 đến 22020049 (không liên tục) |
| Giảng viên | 7 người, trong đó GV07 không tham gia coi thi |
| Ca bận | G2-101 bận ca 1 ngày 14/12; G2-LAB1 bận ca 3 ngày 16/12; GV01 đi công tác cả ngày 14/12; GV03 bận ca 3 ngày 15/12; GV05 bận ca 1 ngày 17/12 |

## Các môn và tình huống mỗi môn kiểm thử

| Môn | Hình thức | Thời lượng | Số SV | Tình huống |
|---|---|---|---|---|
| INT2204 | Thi viết | 90 phút | 40 | Một phòng không đủ, phải dùng cả hai phòng thường |
| MAT1099 | Thi viết | 180 phút | 20 | Lượt chiếm 2 ca; không được bắt đầu ca 1 ngày 15/12 vì ngày đó không có ca 2 |
| INT2211 | Thi máy | 60 phút | 30 | Phòng máy chỉ 12 chỗ nên buộc chia ít nhất 3 lượt (tối đa mặc định 3) |
| INT3306 | Thi máy | 150 phút | 15 | Vừa chiếm 2 ca vừa buộc chia 2 lượt |
| INT3505 | Thi viết | 60 phút | 13 | Môn thi viết được phép chia lượt (thông báo P7) |

## Đáp án tham chiếu

Với `configs/default.json`, giá trị mục tiêu tối ưu là 2391, với điểm phạt:

| A-S1 | A-S2 | A-S3 | A-S4 | A-S5 | A-S6 |
|---|---|---|---|---|---|
| 2 | 50 | 1 | 41 | 0 | 3 |

Kết quả này được tính bằng bản cài đặt thử của `docs/model_spec.md` và xác nhận bằng validator độc lập; lịch đầy đủ ở `output/toy/schedule.json`. Bật `forbid_own_course` cũng cho cùng giá trị tối ưu 2391.

Bài toán có thể có nhiều lịch cùng đạt tối ưu, nên solver khác có thể ra lịch khác nhưng phải đạt đúng giá trị 2391 (kiểm thử `tests/test_exam_solver.py`).
